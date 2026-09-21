"""The phases of one visit, under both profiles.

The two are driven differently and are tested differently because of it. A
motion-only visit is stepped toward a goal and ends when the flange gets
there, so its tests move the flange onto the goal by hand. A full visit is
planned as timed arcs and ends when the clock says so, so its tests advance
the clock and read what the plan asks for.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from clave.control.selection import Candidate, Queue
from clave.control.settings import (
    CalibrationSettings,
    ControlSettings,
    GuidanceSettings,
    Phase,
    Profile,
    TaskSettings,
)
from clave.control.task import TaskError, TaskMachine

ROOT = Path(__file__).resolve().parents[2]
BELT_SURFACE = 0.90
PARK = (0.45, -1.00, 1.20)
BELT_SPEED = 0.314
LIMITS = GuidanceSettings(max_speed=1.00, max_acceleration=2.50)


def task_settings(**overrides: object) -> TaskSettings:
    """Task settings for the motion-only profile."""
    fields: dict[str, object] = {
        "profile": Profile.MOTION_ONLY,
        "approach_height": 0.220,
        "arrival_tolerance": 0.010,
        "dwell_seconds": 0.30,
        "grasp_clearance": 0.050,
        "approach_speed": 0.25,
        "interception_limit": 4.00,
        "interception_margin": 1.15,
        "park_position": PARK,
        "park_marker_color": (0.85, 0.10, 0.10),
    }
    fields.update(overrides)
    return TaskSettings(**fields)  # type: ignore[arg-type]


def machine(**overrides: object) -> TaskMachine:
    """A machine with no calibration offset unless a test adds one.

    The belt and the ceilings go in whatever the profile, because a
    motion-only machine ignores them and a test that switches profile should
    not also have to remember to switch its fixture.
    """
    return TaskMachine(
        task_settings(**overrides),
        CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
        belt_surface=BELT_SURFACE,
        belt_speed=BELT_SPEED,
        guidance=LIMITS,
    )


def queue_of(*candidates: Candidate) -> Queue:
    """A queue holding these candidates in this order."""
    return Queue(order=candidates, recomputed=True)


def candidate(track_id: int = 1, x: float = 0.30, y: float = 0.0) -> Candidate:
    """One candidate the arm could serve."""
    return Candidate(
        track_id=track_id,
        anchor=(x, y, 0.945),
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
        anchor=(0.3, 0.0, 0.945),
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


def _fly(arm: TaskMachine, only: Candidate, span: float = 8.0) -> list[Phase]:
    """Run a planned visit to its end and return the phases it passed through.

    Args:
        arm: The machine, already committed or about to be.
        only: The candidate to serve.
        span: How many seconds to run for at worst.

    Returns:
        The phases seen, in order and without repeats.
    """
    arm.step(queue_of(only), PARK, 0.0)
    seen: list[Phase] = []
    at_seconds = 0.0
    while at_seconds < span:
        at_seconds += 0.01
        flown = arm.flight(at_seconds, PARK)
        if flown is None:
            break
        seen.append(flown.phase)
    return list(dict.fromkeys(seen))


def test_a_full_visit_tracks_descends_grasps_and_retreats() -> None:
    """AC-MOVE-18: a full visit tracks, descends, grasps and retreats."""
    arm = machine(profile=Profile.FULL_VISIT)
    assert _fly(arm, candidate(1, x=0.30)) == [
        Phase.TRACK,
        Phase.DESCEND,
        Phase.HOLD,
        Phase.RETREAT,
    ]
    assert arm.served == (1,)
    assert arm.flying is False


def test_a_planned_visit_shuts_the_jaw_only_once_it_is_on_the_object() -> None:
    """AC-MOVE-38: a planned visit shuts the jaw only once it is on the object.

    A jaw that closes on the way down sweeps the object off the belt, which
    is exactly the failure the whole formulation exists to remove.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    only = candidate(1, x=0.30)
    arm.step(queue_of(only), PARK, 0.0)
    at_seconds, shut_from = 0.0, None
    while at_seconds < 8.0:
        at_seconds += 0.01
        flown = arm.flight(at_seconds, PARK)
        if flown is None:
            break
        if flown.grip > 0.0 and shut_from is None:
            shut_from = flown.phase
    assert shut_from is Phase.HOLD


def test_a_planned_visit_meets_the_object_moving_with_the_belt() -> None:
    """AC-MOVE-39: a planned visit meets the object moving with the belt.

    A jaw arriving at rest has the object sliding through it at belt speed,
    which is the one thing a grasp cannot tolerate.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    only = candidate(1, x=0.30)
    arm.step(queue_of(only), PARK, 0.0)
    at_seconds = 0.0
    while at_seconds < 8.0:
        at_seconds += 0.01
        flown = arm.flight(at_seconds, PARK)
        assert flown is not None
        if flown.phase is Phase.HOLD:
            assert flown.velocity == pytest.approx((BELT_SPEED, 0.0, 0.0), abs=1e-9)
            return
    pytest.fail("the visit never reached the object")


def test_a_planned_visit_descends_onto_where_the_object_will_be() -> None:
    """AC-MOVE-40: a planned visit descends onto where the object will be.

    Not onto where it was. The belt carries the object the whole time the
    arm is travelling, so the pick pose is the marker's pose carried forward
    by the interception and the descent together.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    only = candidate(1, x=0.30)
    arm.step(queue_of(only), PARK, 0.0)
    at_seconds, pick = 0.0, None
    while at_seconds < 8.0:
        at_seconds += 0.01
        flown = arm.flight(at_seconds, PARK)
        assert flown is not None
        if flown.phase is Phase.HOLD:
            pick, elapsed = flown.position, at_seconds
            break
    assert pick is not None
    assert pick[2] == pytest.approx(only.flange[2], abs=1e-3)
    assert pick[0] == pytest.approx(only.flange[0] + BELT_SPEED * elapsed, abs=5e-3)


def test_an_object_with_no_interception_is_missed_rather_than_chased() -> None:
    """AC-MOVE-41: an object with no interception is missed rather than chased.

    A candidate about to leave the belt cannot be reached in the time it has
    left, and the arm gives it up: chasing it costs the objects behind it.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    leaving = Candidate(
        track_id=7,
        anchor=(0.30, 0.0, 0.945),
        flange=(0.30, 0.0, 1.035),
        closing_axis=0.0,
        distance_before_leaving=0.01,
    )
    goal = arm.step(queue_of(leaving), PARK, 0.0)
    assert arm.missed == (7,)
    assert arm.flying is False
    assert goal.position == PARK
    # And it is not offered again on the next capture.
    assert arm.step(queue_of(leaving), PARK, 0.5).track_id is None


def test_a_plan_owns_the_arm_until_it_runs_out() -> None:
    """AC-MOVE-42: a plan owns the arm until it runs out.

    Re-deciding mid-flight turns an interception into a chase: each fresh arc
    is solved against a fresh estimate and the arm never arrives.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    first = candidate(1, x=0.30)
    arm.step(queue_of(first), PARK, 0.0)
    arm.flight(0.01, PARK)
    nearer = candidate(2, x=0.40)
    goal = arm.step(queue_of(nearer, first), PARK, 0.5)
    assert goal.track_id == 1
    assert arm.flying is True


def test_a_refusal_tears_up_the_plan_it_was_built_on() -> None:
    """AC-MOVE-43: a refusal tears up the plan it was built on.

    Every arc after the refused pose was built on it, so continuing to fly
    them would command the rest of a sequence whose premise the solver has
    already rejected.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    only = candidate(1, x=0.30)
    arm.step(queue_of(only), PARK, 0.0)
    assert arm.flying is True
    arm.step(queue_of(only), PARK, 0.5, refusal="outside the annulus")
    assert arm.flying is False
    assert arm.flight(0.6, PARK) is None
    assert arm.faults == ((1, "outside the annulus"),)


def test_the_full_visit_profile_refuses_to_run_without_ceilings() -> None:
    """AC-MOVE-44: the full-visit profile refuses to run without ceilings."""
    with pytest.raises(TaskError, match="ceilings"):
        TaskMachine(
            task_settings(profile=Profile.FULL_VISIT),
            CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
            belt_surface=BELT_SURFACE,
            belt_speed=BELT_SPEED,
        )


def test_the_full_visit_profile_refuses_to_run_on_a_stopped_belt() -> None:
    """AC-MOVE-44: the full-visit profile refuses to run on a stopped belt."""
    with pytest.raises(TaskError, match="carries nothing to intercept"):
        TaskMachine(
            task_settings(profile=Profile.FULL_VISIT),
            CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
            belt_surface=BELT_SURFACE,
            guidance=LIMITS,
        )


def test_the_motion_only_profile_never_descends() -> None:
    """AC-MOVE-18: the motion-only profile never descends."""
    arm = machine()
    only = candidate(1, x=0.30)
    goal = arm.step(queue_of(only), PARK, 0.0)
    for tick in range(20):
        goal = arm.step(queue_of(only), goal.position, 0.2 * (tick + 1))
        assert goal.phase in {Phase.TRACK, Phase.PARK, Phase.STANDBY}


def test_a_completed_visit_records_how_near_the_arm_got() -> None:
    """AC-MOVE-12: a completed visit records how near the arm got."""
    arm = machine()
    only = candidate(1, x=0.30)
    here = (0.30, 0.0, BELT_SURFACE + 0.220)
    arm.step(queue_of(only), PARK, 0.0)
    arm.step(queue_of(only), here, 0.1)
    arm.step(queue_of(only), here, 0.5)
    assert arm.served == (1,)
    assert len(arm.arrivals) == 1
    assert arm.arrivals[0] == pytest.approx(0.0, abs=1e-9)


def test_the_shipped_configuration_builds_a_machine() -> None:
    """The shipped configuration builds a machine."""
    from clave.world.config import load

    settings = ControlSettings.load(load(ROOT / "configs" / "runtime" / "control.yml"))
    arm = TaskMachine(
        settings.task,
        settings.calibration,
        belt_surface=BELT_SURFACE,
        belt_speed=BELT_SPEED,
        guidance=settings.guidance,
    )
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


def test_a_plan_is_re_aimed_while_the_arm_is_still_approaching() -> None:
    """AC-MOVE-40: a plan is re-aimed while the arm is still approaching.

    The arrival time does not move with it, so everything downstream stays
    scheduled against the same instant.
    """
    arm = machine(profile=Profile.FULL_VISIT)
    first = candidate(1, x=0.30)
    arm.step(queue_of(first), PARK, 0.0)
    before = arm.step(queue_of(first), PARK, 0.01)
    drifted = Candidate(
        track_id=1,
        anchor=(0.34, 0.05, 0.945),
        flange=(0.34, 0.05, 1.035),
        closing_axis=math.pi / 2.0,
        distance_before_leaving=1.5,
    )
    arm.step(queue_of(drifted), PARK, 0.50)
    arm.flight(0.50, PARK)
    assert arm.flying is True
    after = arm.step(queue_of(drifted), PARK, 0.51)
    assert math.dist(before.position, after.position) > 0.010


def test_a_pick_outside_the_trusted_region_is_never_planned() -> None:
    """AC-MOVE-43: a pick outside the trusted region is never planned.

    The arm is where it should be and the grasp pose is not, which is the
    candidate's problem and is recorded against it. Contrast with the test
    below, where the arm itself is out of place and the candidate is fine.
    """
    arm = TaskMachine(
        task_settings(profile=Profile.FULL_VISIT),
        CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
        belt_surface=BELT_SURFACE,
        belt_speed=BELT_SPEED,
        guidance=LIMITS,
        admits=lambda pose: pose == PARK,
    )
    only = candidate(1, x=0.30)
    assert arm.step(queue_of(only), PARK, 0.0).position == PARK
    assert arm.flying is False
    assert arm.missed == (1,)


def test_no_plan_is_built_from_a_pose_the_arm_should_not_be_in() -> None:
    """AC-MOVE-43: no plan is built from a pose the arm should not be in.

    A plan begins where the arm is, so planning from outside the trusted
    region produces a first pose the servo refuses, and the refusal tears up
    the plan that caused it. The next capture builds the same one again.
    Measured on the shipped line that latched: one excursion became 46
    faults and the arm never moved again.
    """
    outside = (0.45, -1.00, 1.48)
    arm = TaskMachine(
        task_settings(profile=Profile.FULL_VISIT),
        CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
        belt_surface=BELT_SURFACE,
        belt_speed=BELT_SPEED,
        guidance=LIMITS,
        admits=lambda pose: pose != outside,
    )
    goal = arm.step(queue_of(candidate(1, x=0.30)), outside, 0.0)
    assert arm.flying is False
    assert goal.position == PARK, "the arm was not sent home to recover"
    # And the candidate is not blamed: nothing is wrong with it.
    assert arm.missed == ()


def test_task_machine_accepts_custom_belt_parameters() -> None:
    """AC-MOVE-43: TaskMachine respects custom belt dimensions and border position."""
    arm = TaskMachine(
        task_settings(profile=Profile.FULL_VISIT),
        CalibrationSettings(flange_offset=(0.0, 0.0, 0.0)),
        belt_surface=BELT_SURFACE,
        belt_speed=BELT_SPEED,
        guidance=LIMITS,
        belt_width=0.70,
        belt_center_y=0.05,
    )
    # Expected border: 0.05 - 0.70 / 2.0 = -0.30
    assert arm._belt_border_y == pytest.approx(-0.30)
