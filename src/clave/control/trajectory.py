"""Trajectories with known duration, so an interception time can be solved for.

Guidance until now stepped a reference toward a goal under a speed and an
acceleration bound, which is enough to arrive somewhere and not enough to
pick anything up. Arriving is not the problem: a jaw has to reach an object
at a known instant, moving with it, having come straight down onto it. That
needs a trajectory whose duration is a parameter rather than an outcome.

**Quintic Hermite segments, one per axis.** A quintic has six coefficients
and a segment has six boundary conditions per axis: position, velocity and
acceleration at each end. So the polynomial is determined exactly by what
the phase asks for, in closed form, with no fitting and no solver. That is
also why a quintic and not a B-spline: the requirement is control of
acceleration at the waypoints, and a Hermite form states the acceleration
there as a coefficient rather than approaching it through control points.

**The interception time is a fixed point.** Where the arm must be depends on
how long it takes to get there, because the belt carries the object while
the arm travels. Written out, the approach point is

    p_approach(T) = p_object(t0) + v_object * (T + dt) + (0, 0, z_offset)

and the segment reaching it has to respect the speed and acceleration
ceilings over its whole length. Peak speed and peak acceleration both fall
as `T` grows, so the smallest feasible `T` is found by bisection on a
monotone predicate rather than by an optimiser. It is suboptimal and it is
knowably suboptimal: what the pick needs is a duration it can count on, not
the shortest one that exists.

**The descent duration is not free.** In the frame moving with the belt the
descent is purely vertical, from height `z_offset` at speed `V_approach` to
rest on the object. Writing the quintic in `u = 1 - s` and reading the
leading term, which is cubic because position, velocity and acceleration
all vanish at the end, gives the exact condition for never passing below
the object:

    dt <= 5 * z_offset / (2 * V_approach)

This uses `2 * z_offset / V_approach`, four fifths of that limit, which
leaves margin rather than sitting on a boundary. Acceleration is not the
binding constraint here, so there is nothing to buy by stretching toward it,
and a shorter descent keeps the prediction horizon short, which is the
reason the clearance is small in the first place.

**Both ends move with the belt.** The terminal velocity at the pick is the
object's own, not zero, and the approach velocity is the object's plus the
descent. Two things follow and both are large. A jaw arriving at rest has
the object sliding through it at belt speed, which is the one thing a grasp
cannot tolerate. And the horizontal catch-up a stationary approach forces
dominates the descent: matching the object instead dropped peak acceleration
from 4.58 to 0.94 metres per second squared at the shipped clearance, a
factor of about five, with the slip at the jaw going from 0.314 m/s to zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from clave.control.settings import Point

BISECTION_PASSES = 40
"""How many halvings the interception search takes.

Forty passes take any bracket to about a picosecond, which is far below the
two millisecond tick and costs nothing: each pass is a handful of polynomial
evaluations. A tolerance would be a number to defend; a fixed count that is
obviously enough is not.
"""

SAMPLES = 64
"""How many points a segment is sampled at to bound its speed and acceleration.

The bound is on the Euclidean norm across three axes, and the norm of a
vector of polynomials is not a polynomial, so its extremum has no closed
form worth writing. Sampling a quintic at 64 points catches the peak to
better than a percent, which is far inside the margin any of these bounds
carry.
"""


@dataclass(frozen=True)
class State:
    """Where the flange is, how fast, and how hard it is changing.

    Attributes:
        position: In belt frame meters.
        velocity: In meters per second.
        acceleration: In meters per second squared.
    """

    position: Point
    velocity: Point
    acceleration: Point

    @classmethod
    def at_rest(cls, position: Point) -> State:
        """Return a state standing still at a position.

        Args:
            position: Where it stands.

        Returns:
            The state, with no velocity and no acceleration.
        """
        return cls(
            position=position, velocity=(0.0, 0.0, 0.0), acceleration=(0.0, 0.0, 0.0)
        )


@dataclass(frozen=True)
class Segment:
    """One quintic Hermite arc, with the duration it takes.

    Attributes:
        start: The boundary condition at the beginning.
        end: The boundary condition at the end.
        duration: How long it lasts, in seconds.
    """

    start: State
    end: State
    duration: float

    def at(self, elapsed: float) -> State:
        """Return the state this many seconds in.

        Args:
            elapsed: Seconds since the segment began. Clamped to the
                segment, so asking past the end returns the end rather than
                extrapolating a quintic, which diverges fast.

        Returns:
            The state.
        """
        span = max(self.duration, 1e-12)
        s = min(max(elapsed / span, 0.0), 1.0)
        position, velocity, acceleration = [], [], []
        for axis in range(3):
            terms = (
                self.start.position[axis],
                self.start.velocity[axis] * span,
                self.start.acceleration[axis] * span * span,
                self.end.acceleration[axis] * span * span,
                self.end.velocity[axis] * span,
                self.end.position[axis],
            )
            position.append(sum(w * h for w, h in zip(terms, _basis(s), strict=True)))
            velocity.append(
                sum(w * h for w, h in zip(terms, _first(s), strict=True)) / span
            )
            acceleration.append(
                sum(w * h for w, h in zip(terms, _second(s), strict=True))
                / (span * span)
            )
        return State(
            position=(position[0], position[1], position[2]),
            velocity=(velocity[0], velocity[1], velocity[2]),
            acceleration=(acceleration[0], acceleration[1], acceleration[2]),
        )

    def peak_speed(self) -> float:
        """Return the largest speed anywhere on the segment, in meters per second."""
        return max(
            _norm(self.at(self.duration * i / SAMPLES).velocity)
            for i in range(SAMPLES + 1)
        )

    def peak_acceleration(self) -> float:
        """Return the largest acceleration anywhere, in meters per second squared."""
        return max(
            _norm(self.at(self.duration * i / SAMPLES).acceleration)
            for i in range(SAMPLES + 1)
        )

    def fits(self, max_speed: float, max_acceleration: float) -> bool:
        """Report whether the segment stays inside both ceilings.

        Args:
            max_speed: Speed ceiling, in meters per second.
            max_acceleration: Acceleration ceiling, in meters per second
                squared.

        Returns:
            Whether both hold everywhere on the segment.
        """
        return (
            self.peak_speed() <= max_speed
            and self.peak_acceleration() <= max_acceleration
        )


def descent_seconds(z_offset: float, approach_speed: float) -> float:
    """Return how long the descent onto an object takes.

    Args:
        z_offset: How far above the object the approach stands, in meters.
        approach_speed: How fast the flange is coming down when it gets
            there, in meters per second.

    Returns:
        The duration, `2 * z_offset / approach_speed`. The exact condition
        for never passing below the object is
        `dt <= 5 * z_offset / (2 * approach_speed)`, read off the leading
        cubic term of the quintic written about its end, and this sits at
        four fifths of it rather than on it.

    Raises:
        ValueError: If either argument is not positive, because neither a
            descent of no height nor one at no speed has a duration.
    """
    if z_offset <= 0.0 or approach_speed <= 0.0:
        raise ValueError(
            f"a descent of {z_offset} m at {approach_speed} m/s has no duration"
        )
    return 2.0 * z_offset / approach_speed


def descent_limit_seconds(z_offset: float, approach_speed: float) -> float:
    """Return the longest descent that never passes below the object.

    Args:
        z_offset: How far above the object the approach stands, in meters.
        approach_speed: How fast the flange is coming down, in meters per
            second.

    Returns:
        `5 * z_offset / (2 * approach_speed)`, which is where the leading
        cubic term of the quintic written about its end changes sign.
    """
    return 2.5 * z_offset / approach_speed


def approach(
    flange: State,
    object_position_belt: Point | None = None,
    object_velocity_world: Point | None = None,
    approach_clearance_z: float | None = None,
    approach_speed: float = 0.0,
    max_speed: float = 0.0,
    max_acceleration: float = 0.0,
    latest: float = 0.0,
    margin: float = 1.0,
    *,
    object_position: Point | None = None,
    object_velocity: Point | None = None,
    z_offset: float | None = None,
) -> Segment | None:
    """Return the soonest feasible arc onto the point above a moving object.

    The arc ends above where the object will be when the descent that
    follows finishes, moving with the object and already coming down at the
    approach speed, so the two arcs chain without the flange stopping
    between them.

    Args:
        flange: Where the flange is now and how it is moving.
        object_position_belt: Where the object is now, in belt frame meters.
        object_velocity_world: How the belt is carrying it, in meters per second.
        approach_clearance_z: Clearance above the object to approach at, in meters.
        approach_speed: How fast to be descending on arrival, in meters per
            second.
        max_speed: Speed ceiling, in meters per second.
        max_acceleration: Acceleration ceiling, in meters per second squared.
        latest: The longest interception worth considering, in seconds,
            which is normally what the object has left before it leaves the
            window.
        margin: How much longer than the soonest feasible interception to
            take, as a multiple. One takes the soonest, which sits exactly
            on whichever ceiling binds and therefore leaves no room to
            re-aim the arc later: every correction breaks the bound it was
            already touching. Anything above one buys that room at the cost
            of a later pick.
        object_position: Deprecated alias for object_position_belt.
        object_velocity: Deprecated alias for object_velocity_world.
        z_offset: Deprecated alias for approach_clearance_z.

    Returns:
        The arc, or None when no interception inside `latest` respects both
        ceilings. None is the honest answer for an object the arm cannot
        reach in the belt it has left, and the caller drops it rather than
        chasing it.
    """
    obj_pos = object_position if object_position is not None else object_position_belt
    if obj_pos is None:
        raise TypeError("approach requires object_position_belt or object_position")
    obj_vel = object_velocity if object_velocity is not None else object_velocity_world
    if obj_vel is None:
        raise TypeError("approach requires object_velocity_world or object_velocity")
    clearance = z_offset if z_offset is not None else approach_clearance_z
    if clearance is None:
        raise TypeError("approach requires approach_clearance_z or z_offset")

    dt = descent_seconds(clearance, approach_speed)

    def arc(seconds: float) -> Segment:
        return Segment(
            start=flange,
            end=State(
                position=where(
                    obj_pos,
                    obj_vel,
                    seconds + dt,
                    clearance,
                ),
                velocity=(
                    obj_vel[0],
                    obj_vel[1],
                    obj_vel[2] - approach_speed,
                ),
                acceleration=(0.0, 0.0, 0.0),
            ),
            duration=seconds,
        )

    # Peak speed and peak acceleration both fall as the duration grows, so
    # the predicate is monotone and the soonest feasible interception is a
    # bisection rather than a search.
    if not arc(latest).fits(max_speed, max_acceleration):
        return None
    low, high = 0.0, latest
    for _ in range(BISECTION_PASSES):
        middle = 0.5 * (low + high)
        if middle <= 0.0:
            break
        if arc(middle).fits(max_speed, max_acceleration):
            high = middle
        else:
            low = middle
    return arc(min(high * margin, latest))


def descend(
    approach_arc: Segment,
    object_position_belt: Point | None = None,
    object_velocity_world: Point | None = None,
    approach_clearance_z: float | None = None,
    approach_speed: float = 0.0,
    *,
    object_position: Point | None = None,
    object_velocity: Point | None = None,
    z_offset: float | None = None,
) -> Segment:
    """Return the arc from the approach point down onto the object.

    Args:
        approach_arc: The arc that ended above the object, whose end is this
            one's start, so the flange never stops between them.
        object_position_belt: Where the object was when the approach was planned.
        object_velocity_world: How the belt is carrying it.
        approach_clearance_z: The clearance the approach stood at, in meters.
        approach_speed: How fast the flange is coming down, in meters per
            second.
        object_position: Deprecated alias for object_position_belt.
        object_velocity: Deprecated alias for object_velocity_world.
        z_offset: Deprecated alias for approach_clearance_z.

    Returns:
        The arc. It ends moving with the object rather than at rest, because
        a jaw arriving stopped has the object sliding through it at belt
        speed.
    """
    obj_pos = object_position if object_position is not None else object_position_belt
    if obj_pos is None:
        raise TypeError("descend requires object_position_belt or object_position")
    obj_vel = object_velocity if object_velocity is not None else object_velocity_world
    if obj_vel is None:
        raise TypeError("descend requires object_velocity_world or object_velocity")
    clearance = z_offset if z_offset is not None else approach_clearance_z
    if clearance is None:
        raise TypeError("descend requires approach_clearance_z or z_offset")

    dt = descent_seconds(clearance, approach_speed)
    arrival = approach_arc.duration + dt
    return Segment(
        start=approach_arc.end,
        end=State(
            position=where(obj_pos, obj_vel, arrival, 0.0),
            velocity=obj_vel,
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=dt,
    )


def where(position: Point, velocity: Point, seconds: float, lift: float) -> Point:
    """Return where a point carried at a constant velocity will be.

    Public because the sequence in [clave.control.pick] predicts against the
    same model the arcs here are solved against, and two copies of a
    prediction is how the arc and the pose it aims at come to disagree.

    Args:
        position: Where it is now.
        velocity: How it is moving.
        seconds: How far ahead.
        lift: How far above the result to sit, in meters.

    Returns:
        The predicted position.
    """
    return (
        position[0] + velocity[0] * seconds,
        position[1] + velocity[1] * seconds,
        position[2] + velocity[2] * seconds + lift,
    )


def _norm(vector: Point) -> float:
    """Return a vector's length.

    Args:
        vector: The vector.

    Returns:
        Its Euclidean norm.
    """
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)


def _basis(s: float) -> tuple[float, ...]:
    """Return the quintic Hermite basis at a normalized time.

    Args:
        s: Normalized time, from zero to one.

    Returns:
        The six weights, ordered to match the coefficient vector: start
        position, start velocity, start acceleration, end acceleration, end
        velocity, end position.
    """
    s2, s3, s4, s5 = s * s, s**3, s**4, s**5
    return (
        1 - 10 * s3 + 15 * s4 - 6 * s5,
        s - 6 * s3 + 8 * s4 - 3 * s5,
        0.5 * s2 - 1.5 * s3 + 1.5 * s4 - 0.5 * s5,
        0.5 * s3 - s4 + 0.5 * s5,
        -4 * s3 + 7 * s4 - 3 * s5,
        10 * s3 - 15 * s4 + 6 * s5,
    )


def _first(s: float) -> tuple[float, ...]:
    """Return the basis differentiated once with respect to normalized time.

    Args:
        s: Normalized time.

    Returns:
        The six weights.
    """
    s2, s3, s4 = s * s, s**3, s**4
    return (
        -30 * s2 + 60 * s3 - 30 * s4,
        1 - 18 * s2 + 32 * s3 - 15 * s4,
        s - 4.5 * s2 + 6 * s3 - 2.5 * s4,
        1.5 * s2 - 4 * s3 + 2.5 * s4,
        -12 * s2 + 28 * s3 - 15 * s4,
        30 * s2 - 60 * s3 + 30 * s4,
    )


def _second(s: float) -> tuple[float, ...]:
    """Return the basis differentiated twice with respect to normalized time.

    Args:
        s: Normalized time.

    Returns:
        The six weights.
    """
    s2, s3 = s * s, s**3
    return (
        -60 * s + 180 * s2 - 120 * s3,
        -36 * s + 96 * s2 - 60 * s3,
        1 - 9 * s + 18 * s2 - 10 * s3,
        3 * s - 12 * s2 + 10 * s3,
        -24 * s + 84 * s2 - 60 * s3,
        60 * s - 180 * s2 + 120 * s3,
    )
