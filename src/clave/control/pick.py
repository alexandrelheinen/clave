"""One visit, planned end to end before the arm moves.

The task machine used to hold a pose and wait for the flange to reach it.
That is enough to follow an object and not enough to pick one up: a jaw has
to arrive at a known instant, moving with the object, having come straight
down onto it, and none of those is available from a controller that finds
out when it arrives by arriving.

So a visit is planned as a sequence of timed arcs, each one's end being the
next one's start, and the arm is driven by the clock rather than by
proximity. [clave.control.trajectory] holds the arc algebra and
`docs/guidance-formulation.md` the mathematics; this holds the sequence.

**The interception time is solved once; the aim is not.** A duration that
keeps changing is a duration nothing can be scheduled against, so `T` is
fixed at commit. Where the arm is aiming is refreshed every capture until
the descent begins, because the belt model carries the x axis exactly and
carries nothing else: an object rolling or settling drifts sideways out
from under a pose predicted three seconds ago. See [refine].

**The hold is a carry, not a stop.** While the jaw closes, the belt keeps
moving and the flange has to move with it. A quintic whose endpoints differ
by exactly the velocity times the duration, with that velocity at both ends
and no acceleration, reduces to a straight line at constant speed, so the
carry is the same object as every other arc rather than a special case.
"""

from __future__ import annotations

from dataclasses import dataclass

from clave.control.settings import Phase, Point
from clave.control.trajectory import (
    Segment,
    State,
    approach,
    descend,
    descent_seconds,
    where,
)

JAW_OPEN = 0.0
"""The jaw command while the arm is travelling and descending."""

JAW_SHUT = 1.0
"""The jaw command from the moment the hold begins."""


@dataclass(frozen=True)
class Flight:
    """What the arm is asked for on one tick of a planned visit.

    Attributes:
        phase: Which phase of the visit this tick belongs to.
        position: Where the flange should be, in belt frame meters.
        velocity: How fast it should be moving there. The servo needs this
            as well as the position, because it leads the plant by a time
            rather than by a distance.
        yaw: What the tool should be turned to about the belt normal, or
            None to hold the rotation it already has.
        grip: What the jaw is commanded to, from zero open to one shut.
    """

    phase: Phase
    position: Point
    velocity: Point
    yaw: float | None
    grip: float


@dataclass(frozen=True)
class Leg:
    """One arc of a visit, with what the jaw does during it.

    Attributes:
        phase: Which phase of the visit this arc is.
        segment: The arc.
        grip: What the jaw is commanded to, from zero open to one shut.
    """

    phase: Phase
    segment: Segment
    grip: float


@dataclass(frozen=True)
class Plan:
    """A whole visit, timed from the instant it was made.

    Attributes:
        track_id: Which track it is about.
        legs: The arcs, in order.
        started_at: Simulated time the first arc begins, in seconds.
        pick_at: When the jaw reaches the object, in seconds. Reported
            because it is the figure the interception exists to produce.
    """

    track_id: int
    legs: tuple[Leg, ...]
    started_at: float
    pick_at: float

    @property
    def duration(self) -> float:
        """How long the whole visit takes, in seconds."""
        return self._boundaries()[-1]

    def at(self, at_seconds: float) -> tuple[Phase, State, float] | None:
        """Return where the visit is, or None once it is over.

        A leg owns the half-open interval from its start to its end, and the
        last leg owns its end as well. That convention is what puts the pick
        instant in the hold rather than in the descent: the two arcs meet at
        one point, they agree about the state there, and they disagree about
        the phase and about whether the jaw is shut.

        Args:
            at_seconds: Simulated time.

        Returns:
            The phase, the state the flange should be in, and the jaw
            command. None when the plan has run out, which is how the
            caller learns the visit finished.
        """
        elapsed = at_seconds - self.started_at
        if elapsed < 0.0:
            first = self.legs[0]
            return first.phase, first.segment.at(0.0), first.grip
        # Against cumulative boundaries rather than by subtracting each leg
        # in turn. Subtracting accumulates rounding, and the instant that
        # rounding lands on is the end of the plan, which is exactly the
        # instant a caller asks about to learn the visit is over.
        edges = self._boundaries()
        for index, (opened, closed) in enumerate(zip(edges, edges[1:], strict=False)):
            last = index == len(self.legs) - 1
            if elapsed < closed or (last and elapsed <= closed):
                leg = self.legs[index]
                return leg.phase, leg.segment.at(elapsed - opened), leg.grip
        return None

    def _boundaries(self) -> tuple[float, ...]:
        """Return the elapsed time each leg starts at, and the total.

        Returns:
            One more number than there are legs, beginning at zero.
        """
        edges, running = [0.0], 0.0
        for leg in self.legs:
            running += leg.segment.duration
            edges.append(running)
        return tuple(edges)


def plan_pick(
    flange: State,
    track_id: int,
    object_position: Point,
    belt_velocity: Point,
    z_offset: float,
    approach_speed: float,
    dwell_seconds: float,
    max_speed: float,
    max_acceleration: float,
    latest: float,
    at_seconds: float,
    margin: float = 1.0,
) -> Plan | None:
    """Plan a whole visit, or report that there is no time for one.

    Args:
        flange: Where the flange is and how it is moving.
        track_id: Which track this visit is about.
        object_position: Where the object is now, in belt frame meters.
        belt_velocity: How the belt is carrying it.
        z_offset: Clearance above the object to approach and retreat at.
        approach_speed: How fast to be descending on arrival.
        dwell_seconds: How long the jaw is given to close.
        max_speed: Speed ceiling, in meters per second.
        max_acceleration: Acceleration ceiling, in meters per second squared.
        latest: The longest interception worth considering, in seconds,
            normally what the object has left before it leaves the window.
        at_seconds: Simulated time the plan starts.
        margin: How much longer than the soonest feasible interception to
            take, as a multiple, leaving room for [refine] to correct the
            arc later. One leaves none.

    Returns:
        The plan, or None when no interception inside `latest` respects both
        ceilings. None is the honest answer for an object the arm cannot
        reach in the belt it has left.
    """
    reaching = approach(
        flange,
        object_position,
        belt_velocity,
        z_offset,
        approach_speed,
        max_speed,
        max_acceleration,
        latest,
        margin,
    )
    if reaching is None:
        return None
    return _assemble(
        reaching,
        track_id,
        object_position,
        belt_velocity,
        z_offset,
        approach_speed,
        dwell_seconds,
        at_seconds,
    )


def refine(
    plan: Plan,
    object_position: Point,
    belt_velocity: Point,
    z_offset: float,
    approach_speed: float,
    dwell_seconds: float,
    max_speed: float,
    max_acceleration: float,
    at_seconds: float,
) -> Plan | None:
    """Re-aim a plan at a fresher estimate without moving its arrival time.

    The interception is solved once and then held, because a duration that
    keeps changing is a duration nothing can be scheduled against. What can
    change is where the arm is aiming, and it has to: the belt carries the
    x axis exactly and carries nothing else, so an object rolling or
    settling drifts sideways out from under a pose predicted three seconds
    ago. Measured on the shipped line, that lateral drift averages 41 mm
    over a 2.5 second horizon and 10 mm over half a second.

    So the approach arc is re-solved every capture from wherever the arm has
    got to, onto the refreshed prediction, over whatever time is left. The
    horizon collapses from the whole interception to the descent alone, and
    the old arc's terminal state is the new arc's start, so nothing jumps.

    Once the descent has begun there is nothing left to re-aim: the arm is
    committed, and swapping the target under a jaw already coming down is
    how an approach turns into a swipe.

    Args:
        plan: The plan in flight.
        object_position: Where the object is believed to be now.
        belt_velocity: How the belt is carrying it.
        z_offset: Clearance above the object, in meters.
        approach_speed: How fast to be descending on arrival.
        dwell_seconds: How long the jaw is given to close.
        max_speed: Speed ceiling, in meters per second.
        max_acceleration: Acceleration ceiling, in meters per second squared.
        at_seconds: Simulated time.

    Returns:
        The re-aimed plan, or None when there is nothing left to re-aim or
        the re-aimed arc breaks a ceiling. None means keep flying the plan
        already in hand rather than abandon the visit.
    """
    reaching = plan.legs[0].segment
    elapsed = at_seconds - plan.started_at
    remaining = reaching.duration - elapsed
    if remaining <= 0.0:
        return None
    dt = descent_seconds(z_offset, approach_speed)
    arc = Segment(
        start=reaching.at(elapsed),
        end=State(
            position=where(object_position, belt_velocity, remaining + dt, z_offset),
            velocity=(
                belt_velocity[0],
                belt_velocity[1],
                belt_velocity[2] - approach_speed,
            ),
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=remaining,
    )
    if not arc.fits(max_speed, max_acceleration):
        return None
    return _assemble(
        arc,
        plan.track_id,
        object_position,
        belt_velocity,
        z_offset,
        approach_speed,
        dwell_seconds,
        at_seconds,
    )


def _assemble(
    reaching: Segment,
    track_id: int,
    object_position: Point,
    belt_velocity: Point,
    z_offset: float,
    approach_speed: float,
    dwell_seconds: float,
    at_seconds: float,
) -> Plan:
    """Hang the descent, the carry and the retreat off an approach arc.

    Args:
        reaching: The approach arc, however it was solved.
        track_id: Which track the visit is about.
        object_position: Where the object is at `at_seconds`.
        belt_velocity: How the belt is carrying it.
        z_offset: Clearance above the object, in meters.
        approach_speed: How fast the flange is coming down on arrival.
        dwell_seconds: How long the jaw is given to close.
        at_seconds: Simulated time the approach begins.

    Returns:
        The whole visit.
    """
    dropping = descend(
        reaching, object_position, belt_velocity, z_offset, approach_speed
    )
    holding = _carry(dropping.end, dwell_seconds, belt_velocity)
    rising = _rise(holding.end, z_offset, approach_speed, belt_velocity)
    return Plan(
        track_id=track_id,
        legs=(
            Leg(Phase.TRACK, reaching, JAW_OPEN),
            Leg(Phase.DESCEND, dropping, JAW_OPEN),
            Leg(Phase.HOLD, holding, JAW_SHUT),
            Leg(Phase.RETREAT, rising, JAW_SHUT),
        ),
        started_at=at_seconds,
        pick_at=at_seconds + reaching.duration + dropping.duration,
    )


def _carry(start: State, seconds: float, belt_velocity: Point) -> Segment:
    """Return the arc that rides along with the belt while the jaw closes.

    Args:
        start: Where the descent ended, already moving with the belt.
        seconds: How long to carry for.
        belt_velocity: How the belt is moving.

    Returns:
        The arc. Its endpoints differ by exactly the velocity times the
        duration, with that velocity at both ends and no acceleration, so
        the quintic reduces to a straight line at constant speed.
    """
    return Segment(
        start=start,
        end=State(
            position=(
                start.position[0] + belt_velocity[0] * seconds,
                start.position[1] + belt_velocity[1] * seconds,
                start.position[2] + belt_velocity[2] * seconds,
            ),
            velocity=belt_velocity,
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=seconds,
    )


def _rise(
    start: State, z_offset: float, approach_speed: float, belt_velocity: Point
) -> Segment:
    """Return the arc that lifts the object clear of the belt.

    Args:
        start: Where the hold ended, moving with the belt.
        z_offset: How far to lift, in meters.
        approach_speed: The speed the descent came down at, used again so
            the retreat takes the same time.
        belt_velocity: How the belt is moving.

    Returns:
        The arc, ending at rest above the belt so the delivery that follows
        starts from a standstill and is unconstrained by interception.
    """
    seconds = descent_seconds(z_offset, approach_speed)
    return Segment(
        start=start,
        end=State(
            position=(
                start.position[0] + belt_velocity[0] * seconds,
                start.position[1] + belt_velocity[1] * seconds,
                start.position[2] + z_offset,
            ),
            velocity=(0.0, 0.0, 0.0),
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=seconds,
    )
