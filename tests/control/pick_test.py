"""One visit, planned end to end before the arm moves.

The claims worth pinning are about the seams between the arcs rather than
about any one arc, because the arcs themselves are tested in
`trajectory_test.py`. A sequence whose legs do not chain produces a step in
velocity at every waypoint, and a step in velocity is a lurch.
"""

from __future__ import annotations

import math

import pytest

from clave.control.pick import JAW_OPEN, JAW_SHUT, Plan, plan_pick, refine
from clave.control.settings import Phase
from clave.control.trajectory import State, descent_seconds

BELT = (0.314, 0.0, 0.0)
CLEARANCE = 0.050
APPROACH_SPEED = 0.25
DWELL = 0.30
PARK = (0.45, -1.00, 1.20)
OBJECT = (0.30, 0.0, 1.035)


def a_plan(**overrides: object) -> Plan | None:
    """A plan from the park pose onto an object the belt is carrying."""
    fields: dict[str, object] = {
        "flange": State.at_rest(PARK),
        "track_id": 1,
        "object_position": OBJECT,
        "belt_velocity": BELT,
        "z_offset": CLEARANCE,
        "approach_speed": APPROACH_SPEED,
        "dwell_seconds": DWELL,
        "max_speed": 1.00,
        "max_acceleration": 2.50,
        "latest": 4.00,
        "at_seconds": 0.0,
        "margin": 1.0,
    }
    fields.update(overrides)
    return plan_pick(**fields)  # type: ignore[arg-type]


def test_a_plan_runs_track_descend_hold_retreat() -> None:
    """AC-MOVE-38: a plan runs track, descend, hold and retreat."""
    plan = a_plan()
    assert plan is not None
    assert [leg.phase for leg in plan.legs] == [
        Phase.TRACK,
        Phase.DESCEND,
        Phase.HOLD,
        Phase.RETREAT,
    ]


def test_every_leg_begins_where_the_last_one_ended() -> None:
    """AC-MOVE-39: every leg begins where the last one ended.

    Position, velocity and acceleration all three, because a sequence that
    only matches position produces a step in velocity at every waypoint.
    """
    plan = a_plan()
    assert plan is not None
    for before, after in zip(plan.legs, plan.legs[1:], strict=False):
        assert after.segment.start.position == pytest.approx(
            before.segment.end.position
        )
        assert after.segment.start.velocity == pytest.approx(
            before.segment.end.velocity
        )
        assert after.segment.start.acceleration == pytest.approx(
            before.segment.end.acceleration
        )


def test_the_hold_is_a_carry_at_exactly_belt_speed() -> None:
    """AC-MOVE-39: the hold is a carry at exactly belt speed.

    A quintic whose endpoints differ by the velocity times the duration, with
    that velocity at both ends and no acceleration, collapses to a straight
    line at constant speed. The jaw therefore closes with no relative motion
    at all, which is the precondition a grasp needs.
    """
    plan = a_plan()
    assert plan is not None
    hold = plan.legs[2].segment
    for step in range(11):
        state = hold.at(hold.duration * step / 10.0)
        assert state.velocity == pytest.approx(BELT, abs=1e-12)
        assert state.acceleration == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


def test_the_jaw_stays_open_until_the_hold() -> None:
    """AC-MOVE-38: the jaw stays open until the hold.

    A jaw closing on the way down sweeps the object off the belt, which is
    the failure this whole sequence exists to remove.
    """
    plan = a_plan()
    assert plan is not None
    grips = {leg.phase: leg.grip for leg in plan.legs}
    assert grips[Phase.TRACK] == JAW_OPEN
    assert grips[Phase.DESCEND] == JAW_OPEN
    assert grips[Phase.HOLD] == JAW_SHUT
    assert grips[Phase.RETREAT] == JAW_SHUT


def test_the_pick_instant_is_when_the_hold_begins() -> None:
    """AC-MOVE-40: the pick instant is when the hold begins."""
    plan = a_plan()
    assert plan is not None
    assert plan.at(plan.pick_at) is not None
    phase, _, grip = plan.at(plan.pick_at)  # type: ignore[misc]
    assert phase is Phase.HOLD
    assert grip == JAW_SHUT


def test_the_retreat_lifts_the_clearance_and_ends_at_rest() -> None:
    """AC-MOVE-40: the retreat lifts the clearance and ends at rest.

    At rest because the delivery that follows is unconstrained by any
    interception, so it may as well start from a standstill rather than
    inherit a velocity it has no reason to carry.
    """
    plan = a_plan()
    assert plan is not None
    hold, retreat = plan.legs[2].segment, plan.legs[3].segment
    assert retreat.end.position[2] - hold.end.position[2] == pytest.approx(CLEARANCE)
    assert retreat.end.velocity == pytest.approx((0.0, 0.0, 0.0))
    assert retreat.duration == pytest.approx(descent_seconds(CLEARANCE, APPROACH_SPEED))


def test_a_plan_runs_out_rather_than_extrapolating() -> None:
    """AC-MOVE-42: a plan runs out rather than extrapolating.

    A quintic asked for a time past its end diverges fast, so the plan
    reports that it is over instead of answering.
    """
    plan = a_plan()
    assert plan is not None
    assert plan.at(plan.started_at + plan.duration + 1e-9) is None
    before = plan.at(plan.started_at - 1.0)
    assert before is not None
    assert before[1].position == pytest.approx(PARK)


def test_no_interception_inside_the_window_is_no_plan() -> None:
    """AC-MOVE-41: no interception inside the window is no plan.

    Refusing is the honest answer for an object the arm cannot reach in the
    belt it has left, and it is what lets the caller move on to the next one.
    """
    assert a_plan(latest=0.20) is None


def test_the_duration_is_the_sum_of_its_legs() -> None:
    """AC-MOVE-42: the duration is the sum of its legs."""
    plan = a_plan()
    assert plan is not None
    assert plan.duration == pytest.approx(
        sum(leg.segment.duration for leg in plan.legs)
    )
    assert plan.at(plan.started_at + plan.duration) is not None


def test_re_aiming_keeps_the_arrival_time_and_moves_the_target() -> None:
    """AC-MOVE-40: re-aiming keeps the arrival time and moves the target.

    The whole point of separating the two: a duration that keeps changing is
    a duration nothing can be scheduled against, and an aim that never
    changes is an aim three seconds out of date.
    """
    plan = a_plan(margin=1.15)
    assert plan is not None
    drifted = (OBJECT[0] + BELT[0] * 0.5, OBJECT[1] + 0.040, OBJECT[2])
    again = refine(
        plan=plan,
        object_position=drifted,
        belt_velocity=BELT,
        z_offset=CLEARANCE,
        approach_speed=APPROACH_SPEED,
        dwell_seconds=DWELL,
        max_speed=1.00,
        max_acceleration=2.50,
        at_seconds=0.5,
    )
    assert again is not None
    assert again.pick_at == pytest.approx(plan.pick_at, abs=1e-9)
    moved = math.dist(
        plan.legs[1].segment.end.position, again.legs[1].segment.end.position
    )
    assert moved == pytest.approx(0.040, abs=1e-6)


def test_re_aiming_begins_where_the_arm_has_got_to() -> None:
    """AC-MOVE-40: re-aiming begins where the arm has got to.

    Position, velocity and acceleration, because a correction that only
    matched position would put a step in velocity into the middle of an
    approach.
    """
    plan = a_plan(margin=1.15)
    assert plan is not None
    here = plan.legs[0].segment.at(0.5)
    again = refine(
        plan=plan,
        object_position=OBJECT,
        belt_velocity=BELT,
        z_offset=CLEARANCE,
        approach_speed=APPROACH_SPEED,
        dwell_seconds=DWELL,
        max_speed=1.00,
        max_acceleration=2.50,
        at_seconds=0.5,
    )
    assert again is not None
    start = again.legs[0].segment.start
    assert start.position == pytest.approx(here.position)
    assert start.velocity == pytest.approx(here.velocity)
    assert start.acceleration == pytest.approx(here.acceleration)


def test_nothing_is_re_aimed_once_the_descent_has_begun() -> None:
    """AC-MOVE-40: nothing is re-aimed once the descent has begun.

    Swapping the target under a jaw already coming down turns an approach
    into a swipe.
    """
    plan = a_plan(margin=1.15)
    assert plan is not None
    descending = plan.started_at + plan.legs[0].segment.duration + 0.01
    assert (
        refine(
            plan=plan,
            object_position=OBJECT,
            belt_velocity=BELT,
            z_offset=CLEARANCE,
            approach_speed=APPROACH_SPEED,
            dwell_seconds=DWELL,
            max_speed=1.00,
            max_acceleration=2.50,
            at_seconds=descending,
        )
        is None
    )


def test_a_margin_widens_the_correction_an_arc_will_accept() -> None:
    """AC-MOVE-42: a margin widens the correction an arc will accept.

    Which is why it exists. The bisection returns the soonest arc that fits,
    so it sits on whichever ceiling binds, and a correction large enough to
    matter breaks the bound it was already touching. Asserting that some one
    correction is refused would be asserting more than that: whether a given
    nudge fits depends on where it points, and the property worth pinning is
    that the room grows.
    """

    def accepted(margin: float, sideways: float) -> bool:
        plan = a_plan(margin=margin)
        assert plan is not None
        return (
            refine(
                plan=plan,
                object_position=(OBJECT[0], OBJECT[1] + sideways, OBJECT[2]),
                belt_velocity=BELT,
                z_offset=CLEARANCE,
                approach_speed=APPROACH_SPEED,
                dwell_seconds=DWELL,
                max_speed=1.00,
                max_acceleration=2.50,
                at_seconds=0.5,
            )
            is not None
        )

    def widest(margin: float) -> float:
        low, high = 0.0, 2.0
        for _ in range(30):
            middle = 0.5 * (low + high)
            if accepted(margin, middle):
                low = middle
            else:
                high = middle
        return low

    assert widest(1.15) > widest(1.00)


def test_a_margin_buys_its_room_by_intercepting_later() -> None:
    """AC-MOVE-42: a margin buys its room by intercepting later."""
    soonest, roomy = a_plan(margin=1.0), a_plan(margin=1.15)
    assert soonest is not None and roomy is not None
    assert roomy.pick_at > soonest.pick_at
    assert roomy.pick_at == pytest.approx(
        (soonest.pick_at - 0.40) * 1.15 + 0.40, rel=1e-6
    )


def test_a_visit_ends_over_its_chute_rather_than_over_the_belt() -> None:
    """AC-DROP-05: a visit ends over its chute rather than over the belt.

    Without a delivery leg the plan runs out at the retreat and the jaw
    opens fifty millimetres above the belt, which drops the object back
    where it came from. That is what the line did before this existed.
    """
    mouth = (0.58, -0.42, 0.90)
    plan = a_plan(over=mouth)
    assert plan is not None
    assert [leg.phase for leg in plan.legs][-1] is Phase.DELIVER
    last = plan.legs[-1].segment
    assert last.end.position == pytest.approx(mouth)
    assert last.end.velocity == pytest.approx((0.0, 0.0, 0.0))


def test_the_jaw_holds_all_the_way_to_the_chute() -> None:
    """AC-DROP-05: the jaw holds all the way to the chute.

    Opening at the end of the retreat is the failure this leg removes, so
    the grip has to survive every leg after the hold.
    """
    plan = a_plan(over=(0.58, -0.42, 0.90))
    assert plan is not None
    after_hold = False
    for leg in plan.legs:
        if leg.phase is Phase.HOLD:
            after_hold = True
        if after_hold:
            assert leg.grip == JAW_SHUT, f"{leg.phase} let go early"


def test_the_delivery_stays_inside_the_speed_ceiling() -> None:
    """AC-DROP-05: the delivery stays inside the speed ceiling.

    Nothing constrains this arc's duration from outside, so it is set from
    the distance and the ceiling: a rest-to-rest quintic peaks at 15/8 of
    its mean speed, and taking that as the duration touches the ceiling
    once rather than crossing it.
    """
    plan = a_plan(over=(1.14, -0.42, 0.90), max_speed=1.00)
    assert plan is not None
    assert plan.legs[-1].segment.peak_speed() <= 1.00 + 1e-6


def test_no_chute_means_no_delivery_rather_than_a_broken_one() -> None:
    """AC-DROP-05: no chute means no delivery rather than a broken one.

    A channel with no opening is a configuration error the world refuses at
    load. Here it means the caller asked for a visit that ends at the
    retreat, which is what the motion-only profiles want.
    """
    plan = a_plan()
    assert plan is not None
    assert [leg.phase for leg in plan.legs][-1] is Phase.RETREAT


def test_approach_enters_via_border_with_horizontal_perpendicular_speed() -> None:
    """AC-DROP-06: approach routes through border with transverse horizontal speed."""
    mouth = (0.58, -0.42, 0.90)
    plan = a_plan(over=mouth)
    assert plan is not None
    entry_leg = plan.legs[0]
    assert entry_leg.phase is Phase.TRACK
    assert entry_leg.segment.end.position[0] == pytest.approx(0.58)
    assert entry_leg.segment.end.position[1] == pytest.approx(-0.25)
    assert entry_leg.segment.end.position[2] >= 1.20
    assert entry_leg.segment.end.velocity[0] == pytest.approx(0.0)
    assert entry_leg.segment.end.velocity[1] > 0.0
    assert entry_leg.segment.end.velocity[2] == pytest.approx(0.0)


def test_retreat_lifts_vertically_without_lateral_motion_to_safe_height() -> None:
    """AC-DROP-06: retreat lifts vertically without lateral velocity to clear rail."""
    mouth = (0.58, -0.42, 0.90)
    plan = a_plan(over=mouth)
    assert plan is not None
    retreat_leg = next(leg for leg in plan.legs if leg.phase is Phase.RETREAT)
    retreat = retreat_leg.segment
    assert retreat.end.position[2] >= 1.20
    for step in range(11):
        state = retreat.at(retreat.duration * step / 10.0)
        assert state.position[1] == pytest.approx(retreat.start.position[1])
        assert state.velocity[1] == pytest.approx(0.0)


def test_delivery_exits_via_border_with_horizontal_perpendicular_speed() -> None:
    """AC-DROP-06: delivery passes through border with transverse horizontal speed."""
    mouth = (0.58, -0.42, 0.90)
    plan = a_plan(over=mouth)
    assert plan is not None
    deliver_legs = [leg for leg in plan.legs if leg.phase is Phase.DELIVER]
    assert len(deliver_legs) == 2
    border_leg = deliver_legs[0]
    assert border_leg.segment.end.position[0] == pytest.approx(0.58)
    assert border_leg.segment.end.position[1] == pytest.approx(-0.25)
    assert border_leg.segment.end.position[2] >= 1.20
    assert border_leg.segment.end.velocity[0] == pytest.approx(0.0)
    assert border_leg.segment.end.velocity[1] < 0.0
    assert border_leg.segment.end.velocity[2] == pytest.approx(0.0)
