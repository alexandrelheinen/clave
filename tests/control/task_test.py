"""The phases of one visit, under the motion-only profile.

Etapa A runs standby, tracking, parking and fault. Descent, dwell at the
grasp plane and retreat belong to the full-visit profile and arrive later, so
nothing here exercises them.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from clave.control.selection import Candidate, Queue
from clave.control.settings import (
    CalibrationSettings,
    ControlSettings,
    Phase,
    Profile,
    TaskSettings,
)
from clave.control.task import TaskMachine

ROOT = Path(__file__).resolve().parents[2]
BELT_SURFACE = 0.90
PARK = (0.45, -1.00, 1.20)


def task_settings(**overrides: object) -> TaskSettings:
    """Task settings for the motion-only profile."""
    fields: dict[str, object] = {
        "profile": Profile.MOTION_ONLY,
        "approach_height": 0.220,
        "arrival_tolerance": 0.010,
        "dwell_seconds": 0.30,
        "park_position": PARK,
        "park_marker_color": (0.85, 0.10, 0.10),
    }
    fields.update(overrides)
    return TaskSettings(**fields)  # type: ignore[arg-type]


def machine(**overrides: object) -> TaskMachine:
    """A machine with no calibration offset unless a test adds one."""
    return TaskMachine(
        task_settings(**overrides),
        CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
        belt_surface=BELT_SURFACE,
    )


def queue_of(*candidates: Candidate) -> Queue:
    """A queue holding these candidates in this order."""
    return Queue(order=candidates, recomputed=True)


def candidate(track_id: int = 1, x: float = 0.30, y: float = 0.0) -> Candidate:
    """One candidate the arm could serve."""
    return Candidate(
        track_id=track_id,
        flange=(x, y, 1.035),
        closing_axis=math.pi / 2.0,
        distance_before_leaving=1.5,
    )


def test_an_empty_queue_sends_the_arm_to_park() -> None:
    """AC-MOVE-03: an empty queue sends the arm to park."""
    goal = machine().step(queue_of(), flange=(0.0, 0.0, 1.30), at_seconds=0.0)
    assert goal.phase is Phase.PARK
    assert goal.position == PARK
    assert goal.track_id is None


def test_arriving_at_park_settles_into_standby() -> None:
    """An empty queue, once the arm is there, settles into standby."""
    arm = machine()
    arm.step(queue_of(), flange=(0.0, 0.0, 1.30), at_seconds=0.0)
    goal = arm.step(queue_of(), flange=PARK, at_seconds=0.1)
    assert goal.phase is Phase.STANDBY
    assert goal.position == PARK


def test_a_queue_with_a_head_puts_the_arm_in_tracking() -> None:
    """AC-MOVE-04: a queue with a head puts the arm in tracking."""
    goal = machine().step(queue_of(candidate(7)), flange=PARK, at_seconds=0.0)
    assert goal.phase is Phase.TRACK
    assert goal.track_id == 7


def test_the_goal_rides_at_the_configured_approach_height() -> None:
    """The goal rides at the configured approach height above the belt.

    Motion only, so the flange never descends: the height it tracks at is the
    height it holds.
    """
    goal = machine().step(queue_of(candidate()), flange=PARK, at_seconds=0.0)
    assert goal.position[2] == pytest.approx(BELT_SURFACE + 0.220)


def test_the_goal_carries_the_calibration_offset() -> None:
    """AC-MOVE-06: the goal carries the calibration offset."""
    offset = TaskMachine(
        task_settings(),
        CalibrationSettings(flange_offset=(0.01, -0.02, 0.03)),
        belt_surface=BELT_SURFACE,
    )
    goal = offset.step(queue_of(candidate(x=0.30, y=0.10)), PARK, 0.0)
    assert goal.position[0] == pytest.approx(0.31)
    assert goal.position[1] == pytest.approx(0.08)
    assert goal.position[2] == pytest.approx(BELT_SURFACE + 0.220 + 0.03)


def test_the_goal_turns_the_tool_to_the_closing_axis() -> None:
    """AC-MOVE-07: the goal turns the tool to the closing axis."""
    goal = machine().step(queue_of(candidate()), PARK, 0.0)
    assert goal.yaw == pytest.approx(math.pi / 2.0)


def test_an_unoriented_candidate_asks_for_no_rotation() -> None:
    """AC-MOVE-08: an unoriented candidate asks for no rotation."""
    round_one = Candidate(
        track_id=1,
        flange=(0.3, 0.0, 1.035),
        closing_axis=None,
        distance_before_leaving=1.0,
    )
    assert machine().step(queue_of(round_one), PARK, 0.0).yaw is None


def test_a_visit_is_served_after_the_dwell_and_the_arm_moves_on() -> None:
    """AC-MOVE-04: a visit is served after the dwell, and the arm moves on."""
    arm = machine()
    first, second = candidate(1, x=0.30), candidate(2, x=0.60)
    here = (0.30, 0.0, BELT_SURFACE + 0.220)

    assert arm.step(queue_of(first, second), PARK, 0.0).track_id == 1
    # Arrived, but the dwell has not elapsed.
    assert arm.step(queue_of(first, second), here, 0.1).track_id == 1
    assert arm.step(queue_of(first, second), here, 0.3).track_id == 1
    # The dwell elapsed, so this track is served and the next one is taken.
    assert arm.step(queue_of(first, second), here, 0.45).track_id == 2
    assert arm.served == (1,)


def test_a_track_still_out_of_reach_does_not_start_its_dwell() -> None:
    """A track still out of tolerance does not start its dwell.

    Otherwise a visit completes because time passed rather than because the
    arm arrived, which is the failure that makes a distance report meaningless.
    """
    arm = machine()
    only = candidate(1, x=0.30)
    far = (0.0, 0.0, 1.30)
    for at_seconds in (0.0, 0.5, 1.0, 5.0):
        assert arm.step(queue_of(only), far, at_seconds).track_id == 1
    assert arm.served == ()


def test_a_refusal_faults_the_track_and_the_arm_holds_still() -> None:
    """AC-MOVE-05: a refusal faults the track and the arm holds still."""
    arm = machine()
    here = (0.1, 0.2, 1.10)
    goal = arm.step(queue_of(candidate(3)), here, 0.0, refusal="outside the annulus")
    assert goal.phase is Phase.FAULT
    assert goal.position == here
    assert arm.faults == ((3, "outside the annulus"),)


def test_a_refused_track_is_not_offered_again() -> None:
    """AC-MOVE-05: a refused track is not offered again.

    A pose the solver or the envelope refused will be refused next tick too,
    so retrying it forever is an arm that stops working on the first bad pose.
    """
    arm = machine()
    bad, good = candidate(3, x=0.30), candidate(4, x=0.60)
    arm.step(queue_of(bad, good), PARK, 0.0, refusal="outside the annulus")
    goal = arm.step(queue_of(bad, good), PARK, 0.1)
    assert goal.phase is Phase.TRACK
    assert goal.track_id == 4


def test_a_track_that_leaves_the_queue_is_abandoned() -> None:
    """A track that leaves the queue is abandoned.

    The object fell off the end of the belt or its track retired. Either way
    the arm has nothing to arrive at, and holding the old goal would park the
    flange over empty belt.
    """
    arm = machine()
    arm.step(queue_of(candidate(1)), PARK, 0.0)
    goal = arm.step(queue_of(candidate(2, x=0.80)), PARK, 0.1)
    assert goal.track_id == 2
    assert arm.served == ()


def test_the_full_visit_profile_is_refused_for_now() -> None:
    """The full visit profile is refused for now.

    Descent, dwell at the grasp plane and retreat are not implemented. A
    machine that silently ran the motion-only phases under a full-visit
    configuration would report figures for a visit that never descended.
    """
    from clave.errors import ClaveError

    with pytest.raises(ClaveError, match="full_visit"):
        machine(profile=Profile.FULL_VISIT)


def test_the_shipped_configuration_builds_a_machine() -> None:
    """The shipped configuration builds a machine."""
    from clave.world.config import load

    settings = ControlSettings.load(load(ROOT / "configs" / "runtime" / "control.yml"))
    arm = TaskMachine(settings.task, settings.calibration, belt_surface=BELT_SURFACE)
    assert arm.step(queue_of(), PARK, 0.0).phase in {Phase.PARK, Phase.STANDBY}


def test_a_refusal_with_nothing_queued_is_still_recorded() -> None:
    """AC-MOVE-05: a refusal with nothing queued is still recorded.

    A refusal nobody counted is the one way the arm can stop working and
    leave no trace of why, so it goes down against no track rather than
    being dropped.
    """
    arm = machine()
    goal = arm.step(queue_of(), PARK, 0.0, refusal="the envelope said no")
    assert goal.phase is Phase.FAULT
    assert arm.faults == ((None, "the envelope said no"),)
