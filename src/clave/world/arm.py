"""Actuating the manipulator.

The arm is a Universal Robots UR10e, adopted from MuJoCo Menagerie and vendored
under `third_party/mujoco_menagerie_ur10e/`. A validated model outranked the
SCARA that was authored here, and the trade costs something.

It is a six-axis revolute arm operated for a four-axis task: a position over the
belt and a rotation of the tool about the vertical, with the tool held pointing
down. Two degrees of freedom are surplus, which is deliberate and recorded.

**There is no prismatic axis and none can be made.** Locking revolute joints
removes freedom; it never produces translation along a fixed axis. A vertical
descent is therefore a task-space constraint rather than a joint: inverse
kinematics is solved at each waypoint with the tool axis held down, which is
what an industrial linear move does.

One consequence runs through this module. A six-axis arm holding its tool
vertical has no closed-form workspace, so [reaches] applies an annulus measured
by sweeping the compiled model rather than derived from link lengths. The sweep
lives in `docs/measurements.md` and a test re-runs it, because a region that
drifts from the arm it describes is how a proposer and a checker come to
disagree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.errors import ClaveError

ARM_JOINTS = (
    "arm_shoulder_pan_joint",
    "arm_shoulder_lift_joint",
    "arm_elbow_joint",
    "arm_wrist_1_joint",
    "arm_wrist_2_joint",
    "arm_wrist_3_joint",
)
"""The six axes, base outward, as the vendored model names them."""

ARM_ACTUATORS = (
    "arm_shoulder_pan",
    "arm_shoulder_lift",
    "arm_elbow",
    "arm_wrist_1",
    "arm_wrist_2",
    "arm_wrist_3",
)
"""Position actuators, in joint order."""

BASE_BODY = "arm_base"
"""The body bolted to the pedestal, which every trusted bound is measured from.

Not the shoulder-pan anchor, which sits 0.181 m above it. The sweep that set
those bounds measured from the mounting face, so this must too or the vertical
band is wrong by that offset.
"""

GRIPPER_ACTUATOR = "arm_grip_fingers_actuator"
"""The one actuator the jaw has, driving both fingers through a tendon.

Its command range is 0 to 255, which is the scale a real 2F-85 takes over
its own bus rather than a number this project chose. Zero is open.
"""

PINCH_SITE = "arm_grip_pinch"
"""Where the jaw closes, which is 155.8 mm beyond the flange.

Every commanded pose is still expressed against the flange, because that is
what the trusted reach bounds were swept against. This is where the object
ends up, and the offset between the two is what
`configs/runtime/control.yml` carries as the finger length.
"""

TOOL_SITE = "arm_attachment_site"
"""The flange an end effector bolts to, which every target is expressed for."""

REACH_MARGIN_METERS = 0.001
"""How far past the inner radius a projected point is placed, in meters.

Projecting exactly onto the boundary produces a point `reaches` then rejects,
because `math.hypot` of the result lands a few parts in a quadrillion under
the radius it was built from. A millimetre is far below anything the arm
resolves and far above that error.
"""

REACH_MIN_METERS = 0.25
"""Inner radius of the usable annulus, measured about the base column.

A sweep found the tool unreachable inside 0.200 m with the tool held vertical
and reachable at 0.200 m exactly. This sits above that, so the region a caller
trusts is strictly inside the region the arm can serve.
"""

REACH_MAX_METERS = 1.25
"""Outer radius of the usable annulus.

The same sweep put the furthest solvable point between 1.266 m and 1.309 m
depending on bearing. This sits below the smallest of those, for the same
reason.
"""

TOOL_ABOVE_BASE_METERS = (-0.05, 0.45)
"""Vertical band the tool is trusted in, relative to the arm's own base.

Swept at 0.70 m radius, solutions exist from the base plane to 0.55 m above it
and below. The band stops short at both ends so the trusted region stays inside
the measured one.
"""

SHOULDER_PAN_UNLIMITED = True
"""Axis 1 travels plus or minus 360 degrees, so the annulus has no missing wedge.

The arm this replaced stopped at 140 degrees and lost a wedge behind itself,
which halved the pick window on the belt centreline and was invisible to a
closed-form chord. Nothing of that kind applies here, and the constant exists so
a reader does not go looking for it.
"""

GRIPPER_FULLY_CLOSED = 255.0
"""The command that shuts the jaw, on the scale the model declares."""

_DOWN = np.array([0.0, 0.0, -1.0])
"""The tool axis is held along this, which is what makes the task four-axis."""

_DAMPING = 0.06
"""Damping for the least squares solve, which keeps it stable near a singularity."""


class ReachError(ClaveError):
    """A target lies outside the arm's workspace, or no solution was found."""


@dataclass(frozen=True)
class ArmIndices:
    """Where the arm lives inside the model's arrays.

    Attributes:
        joint_ids: Model joint ids of the six axes, base outward.
        dof_indices: Velocity-space indices of those joints.
        actuator_ids: Position actuators driving them, in joint order.
        gripper_actuator: The jaw's single actuator.
        pinch_site: Where the jaw closes.
        tool_site: Site id of the flange.
        tool_body: Body id the flange belongs to, which the Jacobian needs.
        base_position: World position of the arm's mounting face, which is the
            top of its pedestal.
        lower: Lower joint limits.
        upper: Upper joint limits.
    """

    joint_ids: tuple[int, ...]
    dof_indices: tuple[int, ...]
    actuator_ids: tuple[int, ...]
    gripper_actuator: int
    pinch_site: int
    tool_site: int
    tool_body: int
    base_position: NDArray[np.float64]
    lower: NDArray[np.float64]
    upper: NDArray[np.float64]


def reaches(base_xy: tuple[float, float], x: float, y: float) -> bool:
    """Whether a point lies in the annulus the arm is trusted over.

    Pure geometry, so the test the world applies and the one the safety envelope
    applies cannot drift apart. They did once, on an earlier arm, and showed up
    as a 47 percent override rate.

    This is a region proven by sweep rather than a solve. Running inverse
    kinematics per call would cost milliseconds and give a different answer on
    different seeds, since the solve is iterative; a fixed region is cheap,
    deterministic and shared. What keeps it honest is the test that re-sweeps it.

    Args:
        base_xy: Where the arm's base column stands, in world meters.
        x: Target x, in world meters.
        y: Target y, in world meters.

    Returns:
        Whether the point lies between the inner and outer radii.
    """
    radius = math.hypot(x - base_xy[0], y - base_xy[1])
    return REACH_MIN_METERS <= radius <= REACH_MAX_METERS


def locate(model: Any) -> ArmIndices:
    """Find the arm's joints, actuators and flange in a compiled model.

    Args:
        model: The compiled model.

    Returns:
        The indices and the base position the solver needs.

    Raises:
        KeyError: If a joint, actuator or site is absent, naming it.
    """
    import mujoco

    def lookup(kind: Any, name: str, what: str) -> int:
        found = mujoco.mj_name2id(model, kind, name)
        if found < 0:
            raise KeyError(f"{what} {name!r} is not in the model")
        return int(found)

    joint_ids = tuple(
        lookup(mujoco.mjtObj.mjOBJ_JOINT, name, "joint") for name in ARM_JOINTS
    )
    base_body = lookup(mujoco.mjtObj.mjOBJ_BODY, BASE_BODY, "body")
    actuator_ids = tuple(
        lookup(mujoco.mjtObj.mjOBJ_ACTUATOR, name, "actuator") for name in ARM_ACTUATORS
    )
    gripper_actuator = lookup(
        mujoco.mjtObj.mjOBJ_ACTUATOR, GRIPPER_ACTUATOR, "actuator"
    )
    pinch_site = lookup(mujoco.mjtObj.mjOBJ_SITE, PINCH_SITE, "site")
    site = lookup(mujoco.mjtObj.mjOBJ_SITE, TOOL_SITE, "site")

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    return ArmIndices(
        joint_ids=joint_ids,
        dof_indices=tuple(int(model.jnt_dofadr[j]) for j in joint_ids),
        actuator_ids=actuator_ids,
        gripper_actuator=gripper_actuator,
        pinch_site=pinch_site,
        tool_site=site,
        tool_body=int(model.site_bodyid[site]),
        base_position=np.array(data.xpos[base_body], dtype=np.float64),
        lower=np.array([model.jnt_range[j][0] for j in joint_ids]),
        upper=np.array([model.jnt_range[j][1] for j in joint_ids]),
    )


def joint_positions(model: Any, data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Read the arm's joint angles, in radians, base outward.

    This is the proprioception a vision-only policy lacks.

    Args:
        model: The compiled model.
        data: Its state.
        arm: The arm indices.

    Returns:
        Six joint angles in joint order.
    """
    return np.array([float(data.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids])


def end_effector_position_world(data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Read where the flange currently is, in world coordinates."""
    return np.array(data.site_xpos[arm.tool_site], dtype=np.float64)


end_effector_position = end_effector_position_world


def solve(
    model: Any,
    data: Any,
    arm: ArmIndices,
    target_position_world: NDArray[np.float64] | None = None,
    yaw_world: float | None = None,
    attempts: int = 6,
    iterations: int = 300,
    *,
    target: NDArray[np.float64] | None = None,
    yaw: float | None = None,
) -> NDArray[np.float64]:
    """Solve joint angles putting the flange at a target with the tool down.

    Damped least squares on the stacked position and orientation Jacobian. The
    orientation term drives the tool's own z axis onto the world's downward
    vertical, which is the constraint that makes a six-axis arm behave as the
    four-axis task wants. Restarting from random configurations is what gets
    past the local minima an iterative solve on a redundant arm falls into.

    The solve does not touch `data`'s committed state: it works on a scratch
    copy and returns angles, so a caller's simulation is never advanced by
    asking a question.

    Args:
        model: The compiled model.
        data: Its state, read for a warm start and not modified.
        arm: The arm indices.
        target_position_world: Desired flange position in world coordinates.
        yaw_world: Desired tool rotation about the vertical, in radians.
        attempts: Random restarts before giving up. One means warm start only,
            which is what a controller tracking a moving target wants.
        iterations: Descent steps per attempt.
        target: Legacy keyword alias for target_position_world.
        yaw: Legacy keyword alias for yaw_world.

    Returns:
        Six joint angles, every one inside its limit.

    Raises:
        ReachError: If the target lies outside the trusted annulus, or if no
            attempt converged, naming which.
    """
    target_pos = target_position_world if target_position_world is not None else target
    if target_pos is None:
        raise TypeError("solve requires target_position_world or target")
    resolved_yaw = yaw_world if yaw_world is not None else (0.0 if yaw is None else yaw)
    target = target_pos
    yaw = resolved_yaw
    import mujoco

    if not reaches(
        (float(arm.base_position[0]), float(arm.base_position[1])),
        float(target[0]),
        float(target[1]),
    ):
        radius = math.hypot(
            float(target[0]) - float(arm.base_position[0]),
            float(target[1]) - float(arm.base_position[1]),
        )
        raise ReachError(
            f"target is {radius:.3f} m from the base, outside the "
            f"{REACH_MIN_METERS:.2f} m to {REACH_MAX_METERS:.2f} m annulus"
        )

    lowest, highest = TOOL_ABOVE_BASE_METERS
    above = float(target[2]) - float(arm.base_position[2])
    if not lowest <= above <= highest:
        raise ReachError(
            f"target sits {above:+.3f} m from the base, outside the trusted "
            f"{lowest:+.2f} m to {highest:+.2f} m band"
        )

    wanted = np.array(
        [math.cos(yaw), math.sin(yaw), 0.0], dtype=np.float64
    )  # Where the tool's x axis should point once it is facing down.
    scratch = mujoco.MjData(model)
    scratch.qpos[:] = data.qpos
    start = joint_positions(model, data, arm)
    rng = np.random.default_rng(0)

    for attempt in range(attempts):
        seed = (
            start if attempt == 0 else rng.uniform(arm.lower, arm.upper).clip(-2.8, 2.8)
        )
        for slot, joint in enumerate(arm.joint_ids):
            scratch.qpos[model.jnt_qposadr[joint]] = seed[slot]

        for _ in range(iterations):
            mujoco.mj_forward(model, scratch)
            frame = scratch.site_xmat[arm.tool_site].reshape(3, 3)
            position_error = target - scratch.site_xpos[arm.tool_site]
            # Two rotation terms: put the tool axis down, then spin it to yaw.
            axis_error = np.cross(frame[:, 2], _DOWN)
            yaw_error = np.cross(frame[:, 0], wanted) * 0.5
            rotation_error = axis_error + yaw_error

            if (
                np.linalg.norm(position_error) < 1e-3
                and np.linalg.norm(rotation_error) < 1e-2
            ):
                return np.array(
                    [float(scratch.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids]
                )

            jacp = np.zeros((3, model.nv))
            jacr = np.zeros((3, model.nv))
            mujoco.mj_jacSite(model, scratch, jacp, jacr, arm.tool_site)
            columns = list(arm.dof_indices)
            stacked = np.vstack([jacp[:, columns], jacr[:, columns]])
            error = np.concatenate([position_error, rotation_error])
            square = stacked @ stacked.T + (_DAMPING**2) * np.eye(6)
            delta = stacked.T @ np.linalg.solve(square, error)

            current = np.array(
                [float(scratch.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids]
            )
            stepped = np.clip(current + 0.5 * delta, arm.lower, arm.upper)
            for slot, joint in enumerate(arm.joint_ids):
                scratch.qpos[model.jnt_qposadr[joint]] = stepped[slot]

    raise ReachError(
        f"no solution converged for {np.round(target, 3).tolist()} with the tool "
        f"vertical, after {attempts} restarts"
    )


_TRACKING: dict[tuple[int, int], NDArray[np.float64]] = {}
"""The joint angles each model's arm was last commanded toward.

A controller follows a target that moves with the belt, roughly 0.6 mm per
physics step. Solving that afresh every step repeats a global search ten thousand
times a rollout; keying a memo on the target does not help either, because the
target is different every step. What does help is that the previous answer is
almost the next one, so the descent warm starts from it and converges in a few
iterations.

Keyed on the model **and the data**, because those together are one
simulation. The model alone is not enough: two `MjData` over one compiled
model are two simulations, which is the ordinary case in a test file, a
batch of rollouts or a benchmark sweep, and a seed from somebody else's
simulation is not a warm start. Measured when it happened, eight descent
iterations from another run's seed never caught up and the flange trailed a
moving command by 584 mm where it should have trailed 10.7 mm.

Validating the seed against the measured joints was tried instead and is
wrong: during a large move the command legitimately leads the joints by
more than any sane tolerance, so the seed is thrown away every tick, every
step solves afresh, and the restarts land on different inverse-kinematics
branches. The arm then chatters between them.

What remains is that an id can be reused once an `MjData` is collected, so
a new simulation could inherit a dead one's seed. That is the same fault,
much rarer, and it is recorded rather than solved: solving it properly
means the warm start stops being a module global and becomes something the
caller threads through, which is a wider change than this.
"""

_TRACKING_ITERATIONS = 8
"""Descent steps per control call when warm starting.

Enough to follow a target moving under a millimetre a step, and few enough that
a rollout stays affordable. The first call for a model has nothing to warm start
from and pays for a full solve instead.
"""


def step_toward(
    model: Any,
    data: Any,
    arm: ArmIndices,
    target_position_world: NDArray[np.float64] | None = None,
    gain: float = 0.0,
    yaw_world: float | None = None,
    max_joint_step: float | None = None,
    *,
    target: NDArray[np.float64] | None = None,
    yaw: float | None = None,
) -> NDArray[np.float64]:
    """Move the commanded joint angles one step toward a Cartesian target.

    The first call for a model solves properly, with the restarts [solve] uses
    to escape local minima. Every call after that warm starts from the previous
    answer and takes a few descent steps, because a target carried by a belt
    moves well under a millimetre per physics step and the previous answer is
    therefore almost the next one.

    That distinction is the difference between a rollout that records in seconds
    and one that does not finish. Solving per step ran a global search ten
    thousand times; memoising on the target did not help, because a target that
    moves every step misses every time.

    A target outside the trusted region leaves the command untouched, because
    refusing an impossible pick is the safety layer's job and not the
    controller's.

    Args:
        model: The compiled model.
        data: Its state, with forward kinematics already current.
        arm: The arm indices.
        target_position_world: Desired flange position in world coordinates.
        gain: Fraction of the remaining joint error to command per step.
        yaw_world: Desired tool rotation about the vertical, in radians.
        max_joint_step: How far any one joint's command may move from the
            command before it, in radians, or None to command whatever the
            solve asked for. Near a wrist singularity the Jacobian loses rank
            and the damped solve still asks for a large joint motion to buy a
            small Cartesian one; capping it there trades the pose for a
            command the actuators can follow.

            Measured against the previous command and not against the
            measured position, which is the same distinction guidance makes
            one layer up and matters for the same reason. These are position
            actuators running a proportional-derivative loop, so the command
            has to lead the position to produce any force at all. Capping
            that lead instead of the command rate leaves almost no driving
            error: the arm then crawls, and a flange asked to follow a belt
            at 0.31 m/s falls a metre behind inside two seconds.
        target: Legacy keyword alias for target_position_world.
        yaw: Legacy keyword alias for yaw_world.

    Returns:
        The commanded joint angles after the step.
    """
    target_pos = target_position_world if target_position_world is not None else target
    if target_pos is None:
        raise TypeError("step_toward requires target_position_world or target")
    resolved_yaw = yaw_world if yaw_world is not None else (0.0 if yaw is None else yaw)
    target = target_pos
    yaw = resolved_yaw
    current = joint_positions(model, data, arm)
    if not reachable(arm, target):
        return current

    warm = _TRACKING.get((id(model), id(data)))
    if warm is None:
        try:
            wanted = solve(model, data, arm, target, yaw=yaw)
        except ReachError:
            return current
    else:
        wanted = _descend(model, arm, warm, target, yaw, _TRACKING_ITERATIONS)
    _TRACKING[(id(model), id(data))] = wanted

    commanded = current + gain * (wanted - current)
    if max_joint_step is not None:
        previous = np.array(
            [float(data.ctrl[actuator]) for actuator in arm.actuator_ids]
        )
        commanded = np.clip(
            commanded, previous - max_joint_step, previous + max_joint_step
        )
    clipped: NDArray[np.float64] = np.clip(commanded, arm.lower, arm.upper)
    for slot, actuator_id in enumerate(arm.actuator_ids):
        data.ctrl[actuator_id] = clipped[slot]
    return clipped


def _descend(
    model: Any,
    arm: ArmIndices,
    seed: NDArray[np.float64],
    target: NDArray[np.float64],
    yaw: float,
    iterations: int,
) -> NDArray[np.float64]:
    """Take damped least squares steps from a seed toward a target.

    Args:
        model: The compiled model.
        arm: The arm indices.
        seed: Joint angles to start from.
        target: Desired flange position in world coordinates.
        yaw: Desired tool rotation about the vertical, in radians.
        iterations: Descent steps to take.

    Returns:
        The joint angles reached, clipped to the limits. This is best effort
        rather than a solution: a caller tracking a moving target gets another
        call in two milliseconds.
    """
    import mujoco

    wanted_axis = np.array([math.cos(yaw), math.sin(yaw), 0.0], dtype=np.float64)
    scratch = mujoco.MjData(model)
    for slot, joint in enumerate(arm.joint_ids):
        scratch.qpos[model.jnt_qposadr[joint]] = seed[slot]
    columns = list(arm.dof_indices)

    for _ in range(iterations):
        mujoco.mj_forward(model, scratch)
        frame = scratch.site_xmat[arm.tool_site].reshape(3, 3)
        position_error = target - scratch.site_xpos[arm.tool_site]
        rotation_error = (
            np.cross(frame[:, 2], _DOWN) + np.cross(frame[:, 0], wanted_axis) * 0.5
        )
        if (
            np.linalg.norm(position_error) < 1e-3
            and np.linalg.norm(rotation_error) < 1e-2
        ):
            break
        jacp = np.zeros((3, model.nv))
        jacr = np.zeros((3, model.nv))
        mujoco.mj_jacSite(model, scratch, jacp, jacr, arm.tool_site)
        stacked = np.vstack([jacp[:, columns], jacr[:, columns]])
        error = np.concatenate([position_error, rotation_error])
        wrist_2_angle = float(scratch.qpos[model.jnt_qposadr[arm.joint_ids[4]]])
        sin_w2 = abs(math.sin(wrist_2_angle))
        if sin_w2 < 0.20:
            scale = (1.0 - sin_w2 / 0.20) ** 2
            damping_sq = _DAMPING**2 + (0.35**2) * scale
        else:
            damping_sq = _DAMPING**2
        square = stacked @ stacked.T + damping_sq * np.eye(6)
        delta = stacked.T @ np.linalg.solve(square, error)
        delta = np.clip(delta, -0.20, 0.20)
        here = np.array(
            [float(scratch.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids]
        )
        stepped = np.clip(here + 0.5 * delta, arm.lower, arm.upper)
        for slot, joint in enumerate(arm.joint_ids):
            scratch.qpos[model.jnt_qposadr[joint]] = stepped[slot]

    return np.array([float(scratch.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids])


def project_into_band(base_z: float, z: float) -> float:
    """Pull a height back into the vertical band the arm is trusted over.

    The horizontal projection has a companion for the same reason: a pose
    the arm is not trusted at is refused, and a refusal that nothing can
    correct latches. The arm overshoots the band by a few millimetres under
    its own dynamics, and once it is outside, a reference reseeded from the
    measured flange is outside too, so every pose after it is refused and
    the arm never moves again. Measured on the shipped line, one excursion
    of 7 mm past the ceiling produced 226 refusals in three minutes.

    Args:
        base_z: Height of the arm's mounting face.
        z: The height wanted.

    Returns:
        The height, unchanged when it was already inside the band.
    """
    lowest, highest = TOOL_ABOVE_BASE_METERS
    floor = base_z + lowest + REACH_MARGIN_METERS
    ceiling = base_z + highest - REACH_MARGIN_METERS
    return min(max(z, floor), ceiling)


def project_into_reach(
    base_xy: tuple[float, float], x: float, y: float
) -> tuple[float, float]:
    """Pull a point back into the annulus the arm is trusted over.

    The region the arm is trusted over is an annulus, so it is not convex: a
    straight line between two points inside it can pass through the hole
    around the base. Measured on the shipped line, a traverse from the park
    pose to the far side of the belt passes within 0.10 m of the base, where
    the arm is not trusted and the pose is refused. Neither endpoint is at
    fault and no choice of park pose removes the case, because the base sits
    between the arm's resting place and part of the belt.

    So a point inside the hole is pushed radially out to the inner radius.
    The path that results runs straight until it meets the hole, slides
    around it, and runs straight again, which is what a linear move under a
    workspace constraint does. This is a constraint projection and not
    obstacle avoidance: nothing here knows about anything in the scene.

    The outer radius needs the same treatment for a different reason. A
    chord between two points inside a disc stays inside it, so a path never
    leaves that way, but an interception does: aiming ahead of an object the
    belt is carrying puts the aim downstream of a pose that was reachable,
    and four visits in a sixteen second run were refused at 1.266 m to
    1.287 m against a 1.25 m limit. Pulling the aim back to the edge sends
    the arm to the boundary to wait, which is what it can actually do.

    Args:
        base_xy: Where the arm stands, in the horizontal plane.
        x: The point's first coordinate.
        y: The point's second coordinate.

    Returns:
        The point, unchanged when it was already outside the hole.
    """
    offset_x, offset_y = x - base_xy[0], y - base_xy[1]
    radius = math.hypot(offset_x, offset_y)
    inner = REACH_MIN_METERS + REACH_MARGIN_METERS
    outer = REACH_MAX_METERS - REACH_MARGIN_METERS
    if inner <= radius <= outer:
        return x, y
    if radius == 0.0:
        # Dead centre has no direction to leave by, so any one will do and
        # the choice is recorded rather than left to floating-point noise.
        return base_xy[0] + inner, base_xy[1]
    scale = (inner if radius < inner else outer) / radius
    return base_xy[0] + offset_x * scale, base_xy[1] + offset_y * scale


def pinch_position_world(data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Return where the jaw closes, in world coordinates.

    Args:
        data: Its state, with forward kinematics already current.
        arm: The arm indices.

    Returns:
        The position.
    """
    return np.array(data.site_xpos[arm.pinch_site], dtype=np.float64)


pinch_position = pinch_position_world


def hold(data: Any, arm: ArmIndices, closed: float) -> None:
    """Command the jaw.

    Args:
        data: Its state, modified in place.
        arm: The arm indices.
        closed: How far to close, from 0 for fully open to 1 for fully shut.
            Scaled here onto the 0 to 255 the model takes, which is the scale
            a real 2F-85 accepts over its own bus.
    """
    span = float(np.clip(closed, 0.0, 1.0))
    data.ctrl[arm.gripper_actuator] = span * GRIPPER_FULLY_CLOSED


def tool_yaw_world(data: Any, arm: ArmIndices) -> float:
    """Return the tool's current rotation about the belt normal, in radians.

    Read from the tool frame rather than from the joints, because the frame is
    what a commanded yaw is compared against and the two agree only while the
    tool is vertical.

    Args:
        data: Its state, with forward kinematics already current.
        arm: The arm indices.

    Returns:
        The rotation, in radians.
    """
    frame = data.site_xmat[arm.tool_site].reshape(3, 3)
    return float(math.atan2(frame[1, 0], frame[0, 0]))


tool_yaw = tool_yaw_world


def reachable(
    arm: ArmIndices,
    target_position_world: NDArray[np.float64] | None = None,
    *,
    target: NDArray[np.float64] | None = None,
) -> bool:
    """Report whether a target lies inside the trusted workspace.

    Args:
        arm: The arm indices.
        target_position_world: A position in world coordinates.
        target: Legacy keyword alias for target_position_world.

    Returns:
        Whether the annulus and the height band both admit it. This is the
        region test rather than a solve, so it is cheap and deterministic.
    """
    target_pos = target_position_world if target_position_world is not None else target
    if target_pos is None:
        raise TypeError("reachable requires target_position_world or target")
    if not reaches(
        (float(arm.base_position[0]), float(arm.base_position[1])),
        float(target_pos[0]),
        float(target_pos[1]),
    ):
        return False
    lowest, highest = TOOL_ABOVE_BASE_METERS
    above = float(target_pos[2]) - float(arm.base_position[2])
    return lowest <= above <= highest
