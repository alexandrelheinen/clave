"""Actuating the manipulator.

The arm is a SCARA in the geometry of an ABB IRB 910SC-3/0.65, built as
`assets/scara/irb910sc.xml` and mounted inverted above the belt.

Its inverse kinematics are closed form, which is the point. A SCARA's first two
axes are a planar two-link chain, so the joint angles that put the tool at a
Cartesian point follow from the law of cosines rather than from an iterative
solve. The previous arm used damped least squares and stalled short of poses a
workspace sweep had already proven reachable; that failure mode does not exist
here, because there is no iteration to converge.

The fourth axis is what earns the arm its place. It rotates the tool about the
vertical, independently of where the tool sits, so a jaw or a suction cup can be
aligned to an object's minor axis. A serial arm whose only yaw joint is at the
shoulder spends it pointing at the object and has none left for orientation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.errors import ClaveError

ARM_JOINTS = ("arm_Joint1", "arm_Joint2", "arm_Joint3", "arm_Joint4")
"""Shoulder rotation, elbow rotation, spline travel, spline rotation."""

TOOL_SITE = "arm_tool_point"
"""Site at the tool flange, which is the point every target is expressed for."""

ARM1_METERS = 0.400
"""Shoulder to elbow, from the ABB specification for the 0.65 m variant."""

ARM2_METERS = 0.250
"""Elbow to spline, identical on all three variants."""

REACH_MAX_METERS = ARM1_METERS + ARM2_METERS
"""Fully extended reach, 0.650 m."""

REACH_MIN_METERS = 0.222
"""Radius of the dead zone under the spline.

Axis 2 stops at plus or minus 150 degrees, so the tool cannot fold closer to
the shoulder than this. On a conveyor the dead zone costs pick time rather than
coverage, because the belt carries an object through it and out the far side.
"""


class ReachError(ClaveError):
    """A target lies outside the arm's workspace."""


@dataclass(frozen=True)
class ArmIndices:
    """Where the arm lives inside the model's arrays.

    Attributes:
        joint_ids: Model joint ids of the four axes, in order.
        dof_indices: Velocity-space indices of those joints.
        actuator_ids: Position actuators driving those joints, in order.
        tool_site: Site id of the tool point.
        base_position: World position of the shoulder axis.
        tool_offset: Signed tool height below the shoulder at zero spline
            travel. Negative, because the arm hangs.
        lower: Lower joint limits.
        upper: Upper joint limits.
    """

    joint_ids: tuple[int, ...]
    dof_indices: tuple[int, ...]
    actuator_ids: tuple[int, ...]
    tool_site: int
    base_position: NDArray[np.float64]
    tool_offset: float
    lower: NDArray[np.float64]
    upper: NDArray[np.float64]


SHOULDER_LIMIT_RADIANS = 2.443461
"""Axis 1 stops at plus or minus 140 degrees.

This cuts a wedge out of the annulus behind the shoulder, so being inside the
annulus is necessary and not sufficient. Ignoring it overstates the pick window
on the belt centerline by a factor of two, which a sweep caught and an analytic
chord formula did not.
"""

ELBOW_LIMIT_RADIANS = 2.617994
"""Axis 2 stops at plus or minus 150 degrees, which is what sets the dead zone."""


def reaches(shoulder_xy: tuple[float, float], x: float, y: float) -> bool:
    """Whether the planar chain can put the tool at a point, limits included.

    Pure geometry, so the reachability test the world applies and the one the
    solver applies cannot drift apart. They did once before, on the previous
    arm: the scripted expert and the safety layer read the same geometry
    through two different tests and only one of them was right, which showed up
    as a 47 percent override rate.

    Args:
        shoulder_xy: Where axis 1 sits, in world meters.
        x: Target x, in world meters.
        y: Target y, in world meters.

    Returns:
        Whether some elbow configuration reaches the point within the limits.
    """
    dx, dy = x - shoulder_xy[0], y - shoulder_xy[1]
    radius = math.hypot(dx, dy)
    if not REACH_MIN_METERS <= radius <= REACH_MAX_METERS:
        return False
    cosine = (radius**2 - ARM1_METERS**2 - ARM2_METERS**2) / (
        2.0 * ARM1_METERS * ARM2_METERS
    )
    magnitude = math.acos(max(-1.0, min(1.0, cosine)))
    bearing = math.atan2(dy, dx)
    for elbow in (magnitude, -magnitude):
        if abs(elbow) > ELBOW_LIMIT_RADIANS:
            continue
        shoulder = _wrap(
            bearing
            - math.atan2(
                ARM2_METERS * math.sin(elbow),
                ARM1_METERS + ARM2_METERS * math.cos(elbow),
            )
        )
        if abs(shoulder) <= SHOULDER_LIMIT_RADIANS:
            return True
    return False


def locate(model: Any) -> ArmIndices:
    """Find the arm's joints, actuators and tool site in a compiled model.

    Args:
        model: The compiled model.

    Returns:
        The indices and the fixed geometry the solver needs.

    Raises:
        KeyError: If a joint, actuator or site is absent, naming it.
    """
    import mujoco

    def joint(name: str) -> int:
        found = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if found < 0:
            raise KeyError(f"joint {name!r} is not in the model")
        return int(found)

    def actuator(name: str) -> int:
        found = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        if found < 0:
            raise KeyError(f"actuator {name!r} is not in the model")
        return int(found)

    joint_ids = tuple(joint(name) for name in ARM_JOINTS)
    site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, TOOL_SITE)
    if site < 0:
        raise KeyError(f"site {TOOL_SITE!r} is not in the model")

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    shoulder = np.array(data.xanchor[joint_ids[0]], dtype=np.float64)
    tool = np.array(data.site_xpos[site], dtype=np.float64)

    return ArmIndices(
        joint_ids=joint_ids,
        dof_indices=tuple(int(model.jnt_dofadr[j]) for j in joint_ids),
        actuator_ids=tuple(actuator(name) for name in ARM_JOINTS),
        tool_site=int(site),
        base_position=shoulder,
        tool_offset=float(tool[2] - shoulder[2]),
        lower=np.array([model.jnt_range[j][0] for j in joint_ids]),
        upper=np.array([model.jnt_range[j][1] for j in joint_ids]),
    )


def joint_positions(model: Any, data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Read the arm's joint values.

    This is the proprioception a vision-only policy lacks. Axes 1, 2 and 4 are
    radians; axis 3 is meters of spline travel.

    Args:
        model: The compiled model.
        data: Its state.
        arm: The arm indices.

    Returns:
        Joint values in joint order.
    """
    return np.array([float(data.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids])


def end_effector_position(data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Read where the tool point currently is, in world coordinates."""
    return np.array(data.site_xpos[arm.tool_site], dtype=np.float64)


def solve(
    arm: ArmIndices,
    target: NDArray[np.float64],
    yaw: float = 0.0,
    elbow_left: bool = True,
) -> NDArray[np.float64]:
    """Solve the joint values that put the tool at a Cartesian target.

    The first two axes form a planar two-link chain, so the elbow angle comes
    from the law of cosines and the shoulder angle from the difference between
    the bearing to the target and the elbow's own contribution. The third axis
    is prismatic and resolves by subtraction. The fourth absorbs whatever the
    first two left, which is what makes the tool's yaw independent of where the
    tool sits.

    Args:
        arm: The arm indices, carrying the base position and tool offset.
        target: Desired tool position in world coordinates.
        yaw: Desired tool rotation about the vertical, in radians.
        elbow_left: Which of the two mirror solutions to take.

    Returns:
        Joint values in joint order, every one inside its limit.

    Raises:
        ReachError: If the target lies outside the annulus, outside the
            spline's travel, or needs a shoulder angle past the stop in either
            elbow configuration, naming which of the three failed.
    """
    offset = np.asarray(target, dtype=np.float64) - arm.base_position
    radius = math.hypot(float(offset[0]), float(offset[1]))

    if radius > REACH_MAX_METERS or radius < REACH_MIN_METERS:
        raise ReachError(
            f"target is {radius:.3f} m from the shoulder, outside the "
            f"{REACH_MIN_METERS:.3f} m to {REACH_MAX_METERS:.3f} m annulus"
        )

    # The spline hangs from the arm, so travel is the shortfall between where
    # the tool sits at zero travel and where it is wanted.
    travel = float(offset[2]) - arm.tool_offset
    if not arm.lower[2] - 1e-9 <= travel <= arm.upper[2] + 1e-9:
        raise ReachError(
            f"target needs {travel:.3f} m of spline travel, outside the "
            f"{arm.lower[2]:.3f} m to {arm.upper[2]:.3f} m stroke"
        )

    # Law of cosines on the two-link chain. The clip absorbs the rounding that
    # puts a target exactly at the reach limit a hair outside the domain.
    cosine = (radius**2 - ARM1_METERS**2 - ARM2_METERS**2) / (
        2.0 * ARM1_METERS * ARM2_METERS
    )
    magnitude = math.acos(max(-1.0, min(1.0, cosine)))
    bearing = math.atan2(float(offset[1]), float(offset[0]))

    # Try the requested elbow first, then its mirror. Being inside the annulus
    # is necessary but not sufficient: axis 1 stops at plus or minus 140
    # degrees, which cuts a wedge out of the annulus behind the shoulder, and
    # one elbow configuration often clears the limit where the other does not.
    # Clipping a solution to the limit instead would return joint values whose
    # tool is somewhere other than the target, which is a silent wrong answer.
    order = (magnitude, -magnitude) if elbow_left else (-magnitude, magnitude)
    for elbow in order:
        shoulder = _wrap(
            bearing
            - math.atan2(
                ARM2_METERS * math.sin(elbow),
                ARM1_METERS + ARM2_METERS * math.cos(elbow),
            )
        )
        if not arm.lower[0] <= shoulder <= arm.upper[0]:
            continue
        if not arm.lower[1] <= elbow <= arm.upper[1]:
            continue
        # Axis 4 carries the tool's absolute yaw minus what axes 1 and 2 already
        # contributed, which is the whole reason this arm can orient a tool.
        spin = _wrap(yaw - shoulder - elbow)
        if not arm.lower[3] <= spin <= arm.upper[3]:
            continue
        return np.array([shoulder, elbow, travel, spin], dtype=np.float64)

    raise ReachError(
        f"target at {radius:.3f} m and bearing {math.degrees(bearing):.1f} deg "
        f"needs a shoulder angle outside the "
        f"{math.degrees(arm.lower[0]):.0f} to {math.degrees(arm.upper[0]):.0f} "
        f"degree range, in either elbow configuration"
    )


def _wrap(angle: float) -> float:
    """Fold an angle into minus pi to pi, so a limit test means what it says."""
    return math.atan2(math.sin(angle), math.cos(angle))


def step_toward(
    model: Any,
    data: Any,
    arm: ArmIndices,
    target: NDArray[np.float64],
    gain: float,
    yaw: float = 0.0,
) -> NDArray[np.float64]:
    """Move the commanded joint values one step toward a Cartesian target.

    Solves the target exactly, then commands a fraction of the way there so the
    actuators are not asked for a step they cannot track. A target outside the
    workspace leaves the command where it was rather than driving the arm at a
    limit, because the safety layer, not the controller, is what refuses an
    impossible pick.

    Args:
        model: The compiled model.
        data: Its state, with forward kinematics already current.
        arm: The arm indices.
        target: Desired tool position in world coordinates.
        gain: Fraction of the remaining joint error to apply per step.
        yaw: Desired tool rotation about the vertical, in radians.

    Returns:
        The commanded joint values after the step.
    """
    current = joint_positions(model, data, arm)
    try:
        wanted = solve(arm, target, yaw=yaw)
    except ReachError:
        return current

    commanded = current + gain * (wanted - current)
    clipped: NDArray[np.float64] = np.clip(commanded, arm.lower, arm.upper)
    for slot, actuator_id in enumerate(arm.actuator_ids):
        data.ctrl[actuator_id] = clipped[slot]
    return clipped


def reachable(arm: ArmIndices, target: NDArray[np.float64]) -> bool:
    """Report whether a target lies inside the workspace.

    Args:
        arm: The arm indices.
        target: A position in world coordinates.

    Returns:
        Whether [solve] would succeed for it, ignoring tool yaw, which axis 4
        can always satisfy.
    """
    try:
        solve(arm, target)
    except ReachError:
        return False
    return True
