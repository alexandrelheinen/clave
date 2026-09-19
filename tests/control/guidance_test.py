"""The pose to command this tick, on a bounded path.

Etapa A bounds speed and nothing else. The acceleration bound and the
interception offset for belt travel arrive with etapa C, so nothing here
asserts either.
"""

from __future__ import annotations

import math

import pytest

from clave.control.guidance import toward
from clave.control.settings import GuidanceSettings, Phase
from clave.control.task import Goal

TIMESTEP = 0.002
LIMITS = GuidanceSettings(max_speed=1.00, max_acceleration=2.50)


def goal_at(x: float, y: float = 0.0, z: float = 1.12, yaw: float | None = 0.5) -> Goal:
    """A tracking goal at one place."""
    return Goal(phase=Phase.TRACK, position=(x, y, z), yaw=yaw, track_id=1)


def test_a_step_never_exceeds_the_speed_ceiling() -> None:
    """AC-MOVE-09: a step never exceeds the speed ceiling."""
    flange = (0.0, 0.0, 1.12)
    command = toward(flange, goal_at(2.0), TIMESTEP, LIMITS)
    assert math.dist(flange, command.position) == pytest.approx(
        LIMITS.max_speed * TIMESTEP
    )


def test_the_ceiling_is_respected_over_a_whole_traverse() -> None:
    """AC-MOVE-09: the ceiling is respected over a whole traverse.

    Swept rather than checked once, because a limiter that holds for the
    first step and not the last is a limiter that does not hold.
    """
    flange = (0.0, 0.0, 1.12)
    goal = goal_at(1.30, y=0.40)
    for _ in range(2000):
        command = toward(flange, goal, TIMESTEP, LIMITS)
        assert math.dist(flange, command.position) <= LIMITS.max_speed * TIMESTEP + 1e-9
        flange = command.position
    assert math.dist(flange, goal.position) < 1e-6


def test_a_goal_within_one_step_is_reached_rather_than_overshot() -> None:
    """A goal within one step is reached rather than overshot.

    Stepping a fixed distance past a near goal is what makes a flange buzz
    around a target it has already met.
    """
    flange = (0.0, 0.0, 1.12)
    near = goal_at(0.0005)
    command = toward(flange, near, TIMESTEP, LIMITS)
    assert command.position == pytest.approx(near.position)


def test_the_step_runs_straight_at_the_goal() -> None:
    """The step runs straight at the goal.

    A straight line in task space is what an industrial linear move is, and
    it is what makes a descent a descent rather than an arc.
    """
    flange = (0.0, 0.0, 1.12)
    goal = goal_at(0.60, y=0.80, z=1.12)
    command = toward(flange, goal, TIMESTEP, LIMITS)
    travelled = [command.position[axis] - flange[axis] for axis in range(3)]
    remaining = [goal.position[axis] - flange[axis] for axis in range(3)]
    scale = math.dist((0, 0, 0), travelled) / math.dist((0, 0, 0), remaining)
    for moved, wanted in zip(travelled, remaining, strict=True):
        assert moved == pytest.approx(wanted * scale)


def test_the_yaw_the_goal_asked_for_is_carried_through() -> None:
    """AC-MOVE-07: the yaw the goal asked for is carried through."""
    command = toward((0.0, 0.0, 1.12), goal_at(0.3, yaw=1.25), TIMESTEP, LIMITS)
    assert command.yaw == pytest.approx(1.25)


def test_a_goal_asking_for_no_rotation_commands_none() -> None:
    """AC-MOVE-08: a goal asking for no rotation commands none."""
    command = toward((0.0, 0.0, 1.12), goal_at(0.3, yaw=None), TIMESTEP, LIMITS)
    assert command.yaw is None


def test_a_fault_goal_commands_no_motion() -> None:
    """AC-MOVE-05: a fault goal commands no motion.

    The task machine holds the flange where it is by asking for the pose it
    already has, and guidance has to honour that rather than step toward it.
    """
    flange = (0.11, -0.22, 1.09)
    held = Goal(phase=Phase.FAULT, position=flange, yaw=None, track_id=3)
    assert toward(flange, held, TIMESTEP, LIMITS).position == pytest.approx(flange)


def test_a_longer_tick_travels_further() -> None:
    """A longer tick travels further.

    The bound is a speed and not a step length, so the distance covered has
    to scale with the tick it was given.
    """
    flange = (0.0, 0.0, 1.12)
    goal = goal_at(2.0)
    short = toward(flange, goal, 0.002, LIMITS)
    long = toward(flange, goal, 0.010, LIMITS)
    assert math.dist(flange, long.position) == pytest.approx(
        5.0 * math.dist(flange, short.position)
    )


BASE_XY = (0.0, -0.70)
INNER = 0.25


def keep_inside(pose: tuple[float, float, float]) -> tuple[float, float, float]:
    """The shipped projection, over the shipped arm base."""
    from clave.world.arm import project_into_reach

    x, y = project_into_reach(BASE_XY, pose[0], pose[1])
    return x, y, pose[2]


def test_a_path_between_two_admitted_poses_stays_out_of_the_hole() -> None:
    """AC-MOVE-23: a path between two admitted poses stays out of the hole.

    The arm is trusted over an annulus, so its workspace is not convex and a
    straight line between two poses inside it can cross the hole around the
    base. Measured on the shipped line, a traverse from the park pose to the
    far side of the belt passed within 0.10 m of a base the arm is not
    trusted inside 0.25 m of, and every pose along that stretch was refused.
    """
    park = (0.45, -1.00, 1.20)
    across = (-0.50, 0.42, 1.12)
    goal = Goal(phase=Phase.TRACK, position=across, yaw=0.0, track_id=1)

    naive, guarded = park, park
    breached = False
    for _ in range(3000):
        naive = toward(naive, goal, TIMESTEP, LIMITS).position
        guarded = toward(guarded, goal, TIMESTEP, LIMITS, keep_inside).position
        if math.dist(naive[:2], BASE_XY) < INNER:
            breached = True
        assert math.dist(guarded[:2], BASE_XY) >= INNER - 1e-9

    assert breached, "the straight line no longer crosses the hole to begin with"
    assert math.dist(guarded, across) < 1e-6, "the guarded path still arrives"


def test_the_projection_leaves_a_pose_outside_the_hole_alone() -> None:
    """The projection leaves a pose outside the hole alone.

    It is a constraint and not a filter: everywhere the arm is trusted, the
    path is the straight line and nothing rounds it off.
    """
    outside = (0.60, -0.20, 1.12)
    assert keep_inside(outside) == pytest.approx(outside)


def test_the_projection_keeps_the_height_it_was_given() -> None:
    """The projection keeps the height it was given.

    The hole is a cylinder about the base, so leaving it is a horizontal
    move. Changing the height here would quietly undo a descent.
    """
    assert keep_inside((0.0, -0.68, 1.07))[2] == pytest.approx(1.07)
