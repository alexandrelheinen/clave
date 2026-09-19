"""Trajectories with a known duration, and the interception they let us solve."""

from __future__ import annotations

import math

import pytest

from clave.control.trajectory import (
    Segment,
    State,
    approach,
    descend,
    descent_seconds,
)

BELT = (0.314, 0.0, 0.0)
MAX_SPEED = 1.00
MAX_ACCELERATION = 2.50
Z_OFFSET = 0.05
APPROACH_SPEED = 0.25
PARK = (0.45, -1.00, 1.20)


def moving(position: tuple[float, float, float]) -> State:
    """A state standing still somewhere."""
    return State.at_rest(position)


def test_a_segment_meets_every_boundary_condition_it_was_given() -> None:
    """A segment meets every boundary condition it was given.

    Six conditions per axis and six coefficients, so the polynomial is
    determined rather than fitted. This is the property the whole
    formulation rests on: if the acceleration at a waypoint were only
    approached, chaining two arcs would jerk.
    """
    start = State(
        position=(0.1, 0.2, 1.0),
        velocity=(0.3, -0.1, 0.0),
        acceleration=(0.5, 0.0, -0.2),
    )
    end = State(
        position=(0.6, 0.0, 0.9),
        velocity=(0.0, 0.2, -0.25),
        acceleration=(0.0, 0.0, 0.0),
    )
    arc = Segment(start=start, end=end, duration=0.8)

    begins, finishes = arc.at(0.0), arc.at(0.8)
    for axis in range(3):
        assert begins.position[axis] == pytest.approx(start.position[axis])
        assert begins.velocity[axis] == pytest.approx(start.velocity[axis])
        assert begins.acceleration[axis] == pytest.approx(start.acceleration[axis])
        assert finishes.position[axis] == pytest.approx(end.position[axis])
        assert finishes.velocity[axis] == pytest.approx(end.velocity[axis])
        assert finishes.acceleration[axis] == pytest.approx(end.acceleration[axis])


def test_asking_past_the_end_returns_the_end() -> None:
    """Asking past the end returns the end.

    A quintic extrapolated diverges fast, and a controller that reads one
    tick late should hold rather than be thrown across the cell.
    """
    arc = Segment(
        start=State.at_rest((0.0, 0.0, 1.0)),
        end=State.at_rest((0.5, 0.0, 1.0)),
        duration=0.5,
    )
    assert arc.at(9.0).position == pytest.approx(arc.at(0.5).position)


def test_the_descent_duration_is_where_the_dip_stops() -> None:
    """The descent duration is where the dip stops.

    Twice the clearance over the approach speed. Longer and the quintic
    passes below the object it is descending onto, which for a jaw closing
    around something is the difference between a grasp and a collision.
    """
    assert descent_seconds(0.05, 0.25) == pytest.approx(0.40)

    clearance, speed = 0.05, 0.25
    exact = descent_seconds(clearance, speed)
    top = (0.0, 0.0, 1.00)
    for stretch, dips in ((1.0, False), (1.5, True)):
        span = exact * stretch
        arc = Segment(
            start=State(
                position=top,
                velocity=(BELT[0], 0.0, -speed),
                acceleration=(0.0, 0.0, 0.0),
            ),
            end=State(
                position=(BELT[0] * span, 0.0, top[2] - clearance),
                velocity=BELT,
                acceleration=(0.0, 0.0, 0.0),
            ),
            duration=span,
        )
        lowest = min(arc.at(span * i / 200).position[2] for i in range(201))
        under = (top[2] - clearance) - lowest
        assert (under > 1e-5) is dips, f"stretch {stretch} dipped {under * 1000:.2f} mm"


def test_a_descent_that_matches_the_object_costs_far_less_acceleration() -> None:
    """A descent that matches the object costs far less acceleration.

    Ending at rest means the flange stops while the object keeps moving, so
    the arc has to cover the belt travel horizontally inside the descent.
    That horizontal catch-up, and not the vertical braking, is what
    dominates the acceleration.
    """
    span = descent_seconds(Z_OFFSET, APPROACH_SPEED)
    top = State(
        position=(0.0, 0.0, 1.00),
        velocity=(BELT[0], 0.0, -APPROACH_SPEED),
        acceleration=(0.0, 0.0, 0.0),
    )
    landing = (BELT[0] * span, 0.0, 0.95)

    stopping = Segment(top, State.at_rest(landing), span).peak_acceleration()
    matching = Segment(
        top,
        State(position=landing, velocity=BELT, acceleration=(0.0, 0.0, 0.0)),
        span,
    ).peak_acceleration()
    assert matching < 0.35 * stopping


def test_the_approach_ends_above_where_the_object_will_be() -> None:
    """AC-MOVE-10: the approach ends above where the object will be.

    Checked against the definition rather than a constant: the arc's end
    sits one clearance above the object's position at the instant the
    descent that follows will finish.
    """
    now = (-0.40, 0.10, 0.95)
    arc = approach(
        moving(PARK),
        now,
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert arc is not None
    arrival = arc.duration + descent_seconds(Z_OFFSET, APPROACH_SPEED)
    assert arc.end.position[0] == pytest.approx(now[0] + BELT[0] * arrival)
    assert arc.end.position[2] == pytest.approx(now[2] + Z_OFFSET)


def test_the_approach_arrives_already_descending_and_moving_with_the_belt() -> None:
    """The approach arrives already descending and moving with the belt.

    So the two arcs chain rather than the flange stopping between them,
    which is the whole reason the terminal velocity is a boundary condition
    and not an outcome.
    """
    arc = approach(
        moving(PARK),
        (-0.40, 0.10, 0.95),
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert arc is not None
    assert arc.end.velocity[0] == pytest.approx(BELT[0])
    assert arc.end.velocity[2] == pytest.approx(-APPROACH_SPEED)


def test_the_approach_respects_both_ceilings_over_its_whole_length() -> None:
    """AC-MOVE-09: the approach respects both ceilings over its whole length."""
    arc = approach(
        moving(PARK),
        (-0.40, 0.10, 0.95),
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert arc is not None
    assert arc.peak_speed() <= MAX_SPEED + 1e-9
    assert arc.peak_acceleration() <= MAX_ACCELERATION + 1e-9


def test_the_interception_found_is_the_soonest_feasible_one() -> None:
    """The interception found is the soonest feasible one.

    A duration the pick can count on rather than the shortest that exists,
    and the bisection is only correct because the predicate is monotone.
    This pins that: a shade sooner does not fit.
    """
    arc = approach(
        moving(PARK),
        (-0.40, 0.10, 0.95),
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert arc is not None
    hurried = Segment(arc.start, arc.end, arc.duration * 0.85)
    assert not hurried.fits(MAX_SPEED, MAX_ACCELERATION)


def test_an_object_that_cannot_be_reached_in_time_is_refused() -> None:
    """An object that cannot be reached in time is refused.

    None rather than a plan the arm cannot execute, so the caller drops the
    object instead of chasing it off the end of the belt.
    """
    assert (
        approach(
            moving(PARK),
            (-0.40, 0.10, 0.95),
            BELT,
            Z_OFFSET,
            APPROACH_SPEED,
            MAX_SPEED,
            MAX_ACCELERATION,
            latest=0.2,
        )
        is None
    )


def test_the_descent_starts_exactly_where_the_approach_ended() -> None:
    """The descent starts exactly where the approach ended.

    Position, velocity and acceleration all carried across, which is what
    makes the pair one motion rather than two with a stop between them.
    """
    now = (-0.40, 0.10, 0.95)
    first = approach(
        moving(PARK),
        now,
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert first is not None
    second = descend(first, now, BELT, Z_OFFSET, APPROACH_SPEED)
    assert second.start == first.end


def test_the_descent_lands_on_the_object_moving_with_it() -> None:
    """AC-MOVE-10: the descent lands on the object, moving with it."""
    now = (-0.40, 0.10, 0.95)
    first = approach(
        moving(PARK),
        now,
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert first is not None
    second = descend(first, now, BELT, Z_OFFSET, APPROACH_SPEED)
    arrival = first.duration + second.duration
    assert second.end.position[0] == pytest.approx(now[0] + BELT[0] * arrival)
    assert second.end.position[2] == pytest.approx(now[2])
    assert second.end.velocity == pytest.approx(BELT)


def test_the_pair_never_stops_between_the_two_arcs() -> None:
    """The pair never stops between the two arcs.

    Swept across the join rather than checked at it, because a profile that
    happens to be moving at the waypoint and stalls either side of it is
    still an arm that goes, stops and goes.
    """
    now = (-0.40, 0.10, 0.95)
    first = approach(
        moving(PARK),
        now,
        BELT,
        Z_OFFSET,
        APPROACH_SPEED,
        MAX_SPEED,
        MAX_ACCELERATION,
        latest=6.0,
    )
    assert first is not None
    second = descend(first, now, BELT, Z_OFFSET, APPROACH_SPEED)
    for arc, fraction in ((first, 0.9), (first, 1.0), (second, 0.0), (second, 0.1)):
        speed = math.dist((0, 0, 0), arc.at(arc.duration * fraction).velocity)
        assert speed > 0.1, f"the flange all but stopped at the join: {speed:.3f} m/s"


def test_a_belt_the_arm_cannot_outrun_refuses_every_interception() -> None:
    """A belt the arm cannot outrun refuses every interception.

    Feasibility is not that the arm beats the belt. A quintic from rest
    peaks at about 1.875 times its average, so the ceiling has to clear
    that multiple of the belt speed before any interception exists. This
    fails if that margin is ever quietly assumed away.
    """
    quick = (0.9, 0.0, 0.0)
    assert (
        approach(
            moving(PARK),
            (-0.40, 0.10, 0.95),
            quick,
            Z_OFFSET,
            APPROACH_SPEED,
            MAX_SPEED,
            MAX_ACCELERATION,
            latest=8.0,
        )
        is None
    )


def test_a_descent_of_no_height_has_no_duration() -> None:
    """A descent of no height has no duration."""
    for clearance, speed in ((0.0, 0.25), (0.05, 0.0)):
        with pytest.raises(ValueError, match="no duration"):
            descent_seconds(clearance, speed)
