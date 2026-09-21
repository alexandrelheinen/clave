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

import math
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
"""The jaw command from the moment the hold begins until the object is over
its chute."""

PEAK_OVER_MEAN = 15.0 / 8.0
"""What a rest-to-rest quintic's peak speed is, as a multiple of its mean.

Exact rather than a safety factor: with every boundary condition but the
endpoints at zero, only one basis term survives and its derivative is
`30 s^2 (1-s)^2`, which peaks at `15/8` in the middle.
`docs/guidance-formulation.md` derives it.
"""

MINIMUM_DELIVERY_SECONDS = 0.05
"""A floor on the delivery, so a chute already underneath is not a zero arc.

A segment of no duration divides by its own span. The floor is far below
any delivery the shipped geometry produces and exists so the arithmetic
cannot be handed a zero.
"""


def _fit_segment(
    start: State,
    end: State,
    max_speed: float,
    max_acceleration: float,
    min_duration: float = 0.50,
) -> Segment:
    """Return a quintic segment respecting speed and acceleration ceilings.

    Args:
        start: State at the beginning.
        end: State at the end.
        max_speed: Speed ceiling, in meters per second.
        max_acceleration: Acceleration ceiling, in meters per second squared.
        min_duration: Minimum duration to consider, in seconds.

    Returns:
        The fitted segment respecting both ceilings.
    """
    distance = math.dist(start.position, end.position)
    ceiling = max(max_speed, 1e-6)
    duration = max(PEAK_OVER_MEAN * distance / ceiling, min_duration)
    while duration < 30.0:
        candidate = Segment(start=start, end=end, duration=duration)
        if candidate.fits(max_speed, max_acceleration):
            return candidate
        duration += 0.05
    return candidate


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
        target_yaw: Orientation about the belt normal at the pick, or None.
        initial_yaw: Orientation about the belt normal at the approach start, or None.
    """

    track_id: int
    legs: tuple[Leg, ...]
    started_at: float
    pick_at: float
    target_yaw: float | None = None
    initial_yaw: float | None = None

    @property
    def duration(self) -> float:
        """How long the whole visit takes, in seconds."""
        return self._boundaries()[-1]

    def with_yaw(
        self,
        target_yaw: float | None = None,
        initial_yaw: float | None = None,
    ) -> Plan:
        """Return a copy of the plan with updated target and initial yaw."""
        return Plan(
            track_id=self.track_id,
            legs=self.legs,
            started_at=self.started_at,
            pick_at=self.pick_at,
            target_yaw=target_yaw if target_yaw is not None else self.target_yaw,
            initial_yaw=initial_yaw if initial_yaw is not None else self.initial_yaw,
        )

    def yaw_at(self, at_seconds: float) -> float | None:
        """Return the commanded tool yaw at a simulated instant, or None."""
        if self.target_yaw is None:
            return None
        if self.initial_yaw is None:
            return self.target_yaw
        track_duration = max(1e-6, self.pick_at - self.started_at)
        elapsed = at_seconds - self.started_at
        if elapsed >= track_duration:
            return self.target_yaw
        tau = min(1.0, max(0.0, elapsed / track_duration))
        s = tau * tau * tau * (10.0 + tau * (-15.0 + 6.0 * tau))
        diff = (
            self.target_yaw - self.initial_yaw + math.pi / 2.0
        ) % math.pi - math.pi / 2.0
        two_pi = 2.0 * math.pi
        return (self.initial_yaw + s * diff + math.pi) % two_pi - math.pi

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
    object_position_belt: Point | None = None,
    belt_velocity_world: Point | None = None,
    approach_clearance_z: float | None = None,
    approach_speed: float = 0.0,
    dwell_seconds: float = 0.0,
    max_speed: float = 0.0,
    max_acceleration: float = 0.0,
    latest: float = 0.0,
    at_seconds: float = 0.0,
    margin: float = 1.0,
    target_position_world: Point | None = None,
    retreat_lift: float | None = None,
    *,
    object_position: Point | None = None,
    belt_velocity: Point | None = None,
    z_offset: float | None = None,
    over: Point | None = None,
    belt_width: float = 0.50,
    belt_center_y: float = 0.0,
    belt_border_y: float | None = None,
    safe_height_world: float | None = None,
    cross_speed: float | None = None,
) -> Plan | None:
    """Plan a whole visit, or report that there is no time for one.

    Args:
        flange: Where the flange is and how it is moving.
        track_id: Which track this visit is about.
        object_position_belt: Where the object is now, in belt frame meters.
        belt_velocity_world: How the belt is carrying it.
        approach_clearance_z: Clearance above the object to approach and retreat at.
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
        target_position_world: The chute mouth to release the object over,
            or None to end the visit at the retreat. None drops the object back
            on the belt, which is a line with nowhere to put anything.
        retreat_lift: How far to lift during retreat, in meters. If None,
            defaults to `approach_clearance_z`.
        object_position: Deprecated alias for object_position_belt.
        belt_velocity: Deprecated alias for belt_velocity_world.
        z_offset: Deprecated alias for approach_clearance_z.
        over: Deprecated alias for target_position_world.
        belt_width: Width of the belt in meters, used to compute border position.
        belt_center_y: Lateral center of the belt in meters.
        belt_border_y: Lateral coordinate of the belt border on the chute side,
            or None to compute from belt_center_y - belt_width / 2.0.
        safe_height_world: Flange height giving safe clearance above the belt side
            barrier, in meters, or None to derive from flange or target height.
        cross_speed: Speed across the belt border, in meters per second, or None
            to match approach_speed.

    Returns:
        The plan, or None when no interception inside `latest` respects both
        ceilings. None is the honest answer for an object the arm cannot
        reach in the belt it has left.
    """
    obj_pos = object_position if object_position is not None else object_position_belt
    if obj_pos is None:
        raise TypeError("plan_pick requires object_position_belt or object_position")
    belt_vel = belt_velocity if belt_velocity is not None else belt_velocity_world
    if belt_vel is None:
        raise TypeError("plan_pick requires belt_velocity_world or belt_velocity")
    clearance = z_offset if z_offset is not None else approach_clearance_z
    if clearance is None:
        raise TypeError("plan_pick requires approach_clearance_z or z_offset")
    target_pos = over if over is not None else target_position_world
    max_accel = max_acceleration if max_acceleration > 0.0 else 2.50
    border_y = (
        belt_border_y
        if belt_border_y is not None
        else (belt_center_y - belt_width / 2.0)
    )
    cross_v = cross_speed if cross_speed is not None else approach_speed

    entry_arc: Segment | None = None
    reaching: Segment | None = None
    obj_pos_at_border = obj_pos

    if target_pos is not None and flange.position[1] <= border_y:
        if safe_height_world is not None:
            safe_height = max(target_pos[2], safe_height_world)
        else:
            safe_height = max(target_pos[2], flange.position[2])
        border_approach = State(
            position=(target_pos[0], border_y, safe_height),
            velocity=(0.0, cross_v, 0.0),
            acceleration=(0.0, 0.0, 0.0),
        )
        entry_arc = _fit_segment(
            flange, border_approach, max_speed, max_accel, min_duration=0.50
        )
        if entry_arc.duration >= latest:
            return None
        remaining_latest = latest - entry_arc.duration
        obj_pos_at_border = (
            obj_pos[0] + belt_vel[0] * entry_arc.duration,
            obj_pos[1],
            obj_pos[2],
        )
        reaching = approach(
            border_approach,
            obj_pos_at_border,
            belt_vel,
            clearance,
            approach_speed,
            max_speed,
            max_accel,
            remaining_latest,
            margin,
        )
    else:
        reaching = approach(
            flange,
            obj_pos,
            belt_vel,
            clearance,
            approach_speed,
            max_speed,
            max_accel,
            latest,
            margin,
        )

    if reaching is None:
        return None

    return _assemble(
        reaching,
        track_id,
        obj_pos_at_border,
        belt_vel,
        clearance,
        approach_speed,
        dwell_seconds,
        at_seconds,
        target_pos,
        max_speed,
        retreat_lift,
        entry_segment=entry_arc,
        belt_border_y=border_y,
        safe_height_world=safe_height_world,
        cross_speed=cross_v,
        max_acceleration=max_accel,
    )


def refine(
    plan: Plan,
    object_position_belt: Point | None = None,
    belt_velocity_world: Point | None = None,
    approach_clearance_z: float | None = None,
    approach_speed: float = 0.0,
    dwell_seconds: float = 0.0,
    max_speed: float = 0.0,
    max_acceleration: float = 0.0,
    at_seconds: float = 0.0,
    target_position_world: Point | None = None,
    retreat_lift: float | None = None,
    *,
    object_position: Point | None = None,
    belt_velocity: Point | None = None,
    z_offset: float | None = None,
    over: Point | None = None,
    belt_width: float = 0.50,
    belt_center_y: float = 0.0,
    belt_border_y: float | None = None,
    safe_height_world: float | None = None,
    cross_speed: float | None = None,
) -> Plan | None:
    """Correct a plan in flight against a fresher estimate of the object.

    Refinement keeps the arrival time already chosen and solves only for a
    new approach arc that lands on the refreshed position at that instant.
    The descent, the carry and the retreat are then hung off the new end
    exactly as they were off the old one.

    Args:
        plan: The plan in flight.
        object_position_belt: Where the object is now believed to be.
        belt_velocity_world: How the belt is moving.
        approach_clearance_z: Clearance above the object, in meters.
        approach_speed: How fast the flange is coming down on arrival.
        dwell_seconds: How long the jaw is given to close.
        max_speed: Speed ceiling, in meters per second.
        max_acceleration: Acceleration ceiling, in meters per second squared.
        at_seconds: Current simulated time.
        target_position_world: The chute mouth to release over, carried
            through unchanged.
        retreat_lift: How far to lift during retreat, in meters. If None,
            defaults to `approach_clearance_z`.
        object_position: Deprecated alias for object_position_belt.
        belt_velocity: Deprecated alias for belt_velocity_world.
        z_offset: Deprecated alias for approach_clearance_z.
        over: Deprecated alias for target_position_world.
        belt_width: Width of the belt in meters.
        belt_center_y: Lateral center of the belt in meters.
        belt_border_y: Lateral position of the belt border on the chute side.
        safe_height_world: Safe clearance height above the belt side barrier.
        cross_speed: Speed across the belt border, in meters per second.

    Returns:
        The re-aimed plan, or None when there is nothing left to re-aim or
        the re-aimed arc breaks a ceiling. None means keep flying the plan
        already in hand rather than abandon the visit.
    """
    obj_pos = object_position if object_position is not None else object_position_belt
    if obj_pos is None:
        raise TypeError("refine requires object_position_belt or object_position")
    belt_vel = belt_velocity if belt_velocity is not None else belt_velocity_world
    if belt_vel is None:
        raise TypeError("refine requires belt_velocity_world or belt_velocity")
    clearance = z_offset if z_offset is not None else approach_clearance_z
    if clearance is None:
        raise TypeError("refine requires approach_clearance_z or z_offset")
    target_pos = over if over is not None else target_position_world
    max_accel = max_acceleration if max_acceleration > 0.0 else 2.50
    border_y = (
        belt_border_y
        if belt_border_y is not None
        else (belt_center_y - belt_width / 2.0)
    )
    cross_v = cross_speed if cross_speed is not None else approach_speed

    track_legs = [leg for leg in plan.legs if leg.phase is Phase.TRACK]
    dt = descent_seconds(clearance, approach_speed)
    elapsed = at_seconds - plan.started_at

    if len(track_legs) > 1:
        entry_leg = track_legs[0].segment
        track_leg = track_legs[1].segment
        if elapsed < entry_leg.duration:
            rem_entry = entry_leg.duration - elapsed
            new_entry_arc = Segment(
                start=entry_leg.at(elapsed),
                end=entry_leg.end,
                duration=rem_entry,
            )
            if not new_entry_arc.fits(max_speed, max_accel):
                return None
            obj_pos_at_border = (
                obj_pos[0] + belt_vel[0] * rem_entry,
                obj_pos[1],
                obj_pos[2],
            )
            new_track_arc = Segment(
                start=entry_leg.end,
                end=State(
                    position=where(
                        obj_pos_at_border,
                        belt_vel,
                        track_leg.duration + dt,
                        clearance,
                    ),
                    velocity=(
                        belt_vel[0],
                        belt_vel[1],
                        belt_vel[2] - approach_speed,
                    ),
                    acceleration=(0.0, 0.0, 0.0),
                ),
                duration=track_leg.duration,
            )
            if not new_track_arc.fits(max_speed, max_accel):
                return None
            return _assemble(
                new_track_arc,
                plan.track_id,
                obj_pos_at_border,
                belt_vel,
                clearance,
                approach_speed,
                dwell_seconds,
                at_seconds,
                target_pos,
                max_speed,
                retreat_lift,
                entry_segment=new_entry_arc,
                belt_border_y=border_y,
                safe_height_world=safe_height_world,
                cross_speed=cross_v,
                max_acceleration=max_accel,
            )
        if elapsed < entry_leg.duration + track_leg.duration:
            rem_track = (entry_leg.duration + track_leg.duration) - elapsed
            track_elapsed = elapsed - entry_leg.duration
            current_state = track_leg.at(track_elapsed)
            new_track_arc = Segment(
                start=current_state,
                end=State(
                    position=where(
                        obj_pos,
                        belt_vel,
                        rem_track + dt,
                        clearance,
                    ),
                    velocity=(
                        belt_vel[0],
                        belt_vel[1],
                        belt_vel[2] - approach_speed,
                    ),
                    acceleration=(0.0, 0.0, 0.0),
                ),
                duration=rem_track,
            )
            if not new_track_arc.fits(max_speed, max_accel):
                return None
            return _assemble(
                new_track_arc,
                plan.track_id,
                obj_pos,
                belt_vel,
                clearance,
                approach_speed,
                dwell_seconds,
                at_seconds,
                target_pos,
                max_speed,
                retreat_lift,
                belt_border_y=border_y,
                safe_height_world=safe_height_world,
                cross_speed=cross_v,
                max_acceleration=max_accel,
            )
        return None

    reaching = track_legs[0].segment
    remaining = reaching.duration - elapsed
    if remaining <= 0.0:
        return None
    arc = Segment(
        start=reaching.at(elapsed),
        end=State(
            position=where(
                obj_pos,
                belt_vel,
                remaining + dt,
                clearance,
            ),
            velocity=(
                belt_vel[0],
                belt_vel[1],
                belt_vel[2] - approach_speed,
            ),
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=remaining,
    )
    if not arc.fits(max_speed, max_accel):
        return None
    return _assemble(
        arc,
        plan.track_id,
        obj_pos,
        belt_vel,
        clearance,
        approach_speed,
        dwell_seconds,
        at_seconds,
        target_pos,
        max_speed,
        retreat_lift,
        belt_border_y=border_y,
        safe_height_world=safe_height_world,
        cross_speed=cross_v,
        max_acceleration=max_accel,
    )


def _deliver(start: State, target_position_world: Point, max_speed: float) -> Segment:
    """Return the arc that carries the object to its chute and lets go.

    Args:
        start: Where the retreat ended, at rest above the belt.
        target_position_world: The chute mouth to release over.
        max_speed: Speed ceiling, in meters per second.

    Returns:
        The arc, ending at rest over the mouth.
    """
    distance = math.dist(start.position, target_position_world)
    seconds = max(PEAK_OVER_MEAN * distance / max_speed, MINIMUM_DELIVERY_SECONDS)
    return Segment(
        start=start,
        end=State(
            position=target_position_world,
            velocity=(0.0, 0.0, 0.0),
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=seconds,
    )


def _assemble(
    reaching: Segment,
    track_id: int,
    object_position_belt: Point,
    belt_velocity_world: Point,
    approach_clearance_z: float,
    approach_speed: float,
    dwell_seconds: float,
    at_seconds: float,
    target_position_world: Point | None = None,
    max_speed: float = 1.0,
    retreat_lift: float | None = None,
    *,
    entry_segment: Segment | None = None,
    belt_border_y: float = -0.25,
    safe_height_world: float | None = None,
    cross_speed: float | None = None,
    max_acceleration: float = 2.50,
) -> Plan:
    """Hang the descent, the carry, the retreat and delivery off an approach arc.

    Args:
        reaching: The approach tracking arc.
        track_id: Which track the visit is about.
        object_position_belt: Where the object is at `at_seconds`.
        belt_velocity_world: How the belt is carrying it.
        approach_clearance_z: Clearance above the object, in meters.
        approach_speed: How fast the flange is coming down on arrival.
        dwell_seconds: How long the jaw is given to close.
        at_seconds: Simulated time the approach begins.
        target_position_world: Where to release the object over.
        max_speed: Speed ceiling in meters per second.
        retreat_lift: How far to lift during retreat, in meters.
        entry_segment: Preceding arc to the intermediary border waypoint.
        belt_border_y: Lateral coordinate of the belt border on the chute side.
        safe_height_world: Safe clearance height above the belt side barrier.
        cross_speed: Speed across the belt border, in meters per second.
        max_acceleration: Acceleration ceiling in meters per second squared.

    Returns:
        The whole visit.
    """
    cross_v = cross_speed if cross_speed is not None else approach_speed
    dropping = descend(
        reaching,
        object_position_belt,
        belt_velocity_world,
        approach_clearance_z,
        approach_speed,
    )
    holding = _carry(dropping.end, dwell_seconds, belt_velocity_world)
    if target_position_world is not None:
        if safe_height_world is not None:
            safe_height = max(target_position_world[2], safe_height_world)
        else:
            safe_height = max(target_position_world[2], reaching.start.position[2])
        lift = max(
            approach_clearance_z if retreat_lift is None else retreat_lift,
            safe_height - holding.end.position[2],
        )
    else:
        lift = approach_clearance_z if retreat_lift is None else retreat_lift
    rising = _rise(holding.end, lift, approach_speed, belt_velocity_world)
    legs = []
    if entry_segment is not None:
        legs.append(Leg(Phase.TRACK, entry_segment, JAW_OPEN))
    legs.extend(
        [
            Leg(Phase.TRACK, reaching, JAW_OPEN),
            Leg(Phase.DESCEND, dropping, JAW_OPEN),
            Leg(Phase.HOLD, holding, JAW_SHUT),
            Leg(Phase.RETREAT, rising, JAW_SHUT),
        ]
    )
    if target_position_world is not None:
        if safe_height_world is not None:
            safe_height = max(target_position_world[2], safe_height_world)
        else:
            safe_height = max(target_position_world[2], reaching.start.position[2])
        border_retreat = State(
            position=(target_position_world[0], belt_border_y, safe_height),
            velocity=(0.0, -cross_v, 0.0),
            acceleration=(0.0, 0.0, 0.0),
        )
        chute_target = State(
            position=target_position_world,
            velocity=(0.0, 0.0, 0.0),
            acceleration=(0.0, 0.0, 0.0),
        )
        seg_to_border = _fit_segment(
            rising.end, border_retreat, max_speed, max_acceleration, min_duration=0.50
        )
        seg_to_chute = _fit_segment(
            border_retreat,
            chute_target,
            max_speed,
            max_acceleration,
            min_duration=MINIMUM_DELIVERY_SECONDS,
        )
        legs.append(Leg(Phase.DELIVER, seg_to_border, JAW_SHUT))
        legs.append(Leg(Phase.DELIVER, seg_to_chute, JAW_SHUT))
    entry_duration = entry_segment.duration if entry_segment is not None else 0.0
    return Plan(
        track_id=track_id,
        legs=tuple(legs),
        started_at=at_seconds,
        pick_at=at_seconds + entry_duration + reaching.duration + dropping.duration,
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
    """Return the arc that lifts the object vertically clear of the belt.

    Args:
        start: Where the hold ended, moving with the belt.
        z_offset: How far to lift, in meters.
        approach_speed: The speed the descent came down at, used again so
            the retreat takes the same time.
        belt_velocity: How the belt is moving.

    Returns:
        The arc, lifting vertically in z without lateral motion and ending at
        rest above the belt so the delivery that follows starts from a
        standstill.
    """
    seconds = descent_seconds(z_offset, approach_speed)
    return Segment(
        start=start,
        end=State(
            position=(
                start.position[0] + belt_velocity[0] * seconds,
                start.position[1],
                start.position[2] + z_offset,
            ),
            velocity=(0.0, 0.0, 0.0),
            acceleration=(0.0, 0.0, 0.0),
        ),
        duration=seconds,
    )
