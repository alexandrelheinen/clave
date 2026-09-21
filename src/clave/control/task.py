"""The phases of one visit, and the pose each phase asks for.

A visit is what the arm does about one object: go to it, stay with it long
enough to prove it arrived, and move on. The machine says which phase it is
in and where it wants the flange; it decides nothing about the path there,
which is guidance, and nothing about joint angles, which is the servo.

Under the motion-only profile the phases are standby, tracking, parking and
fault. That is what tuning arm speed against belt speed needs: the flange
rides at approach height the whole time, so nothing about a descent muddies
what a distance figure means.

**A full visit is planned, not stepped.** The motion-only path asks for a
pose and finds out when it arrives by arriving, which is enough to follow an
object and not enough to pick one up: a jaw has to reach an object at a
known instant, moving with it, having come straight down onto it. So the
full-visit path hands the whole visit to [clave.control.pick] the moment it
commits to a candidate, gets back a sequence of timed arcs, and thereafter
drives the arm from the clock rather than from proximity.

That makes the two profiles differ in how they are driven and not only in
how many phases they run, which is why a caller asks [TaskMachine.flying]
which regime it is in rather than reading the phase.

**A plan owns which object and when; not where.** Re-deciding the target
mid-flight would turn an interception into a chase, and re-deciding the
arrival time would leave nothing able to schedule against it, so both are
fixed the moment the machine commits. The aim is refreshed every capture
until the descent begins, because the belt model predicts the x axis
exactly and predicts nothing else, and an object that rolls drifts out from
under a pose solved three seconds ago.

A refusal is the one thing that tears a plan up, because a pose the solver
will not take is a pose the rest of the sequence was built on.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass

from clave.control.pick import Flight, Plan, plan_pick, refine
from clave.control.selection import Candidate, Queue
from clave.control.settings import (
    CalibrationSettings,
    GuidanceSettings,
    Phase,
    Point,
    Profile,
    TaskSettings,
)
from clave.control.trajectory import State
from clave.errors import ClaveError

LOGGER = logging.getLogger(__name__)

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the instant a goal records."""


class TaskError(ClaveError):
    """The task machine cannot run this configuration."""


@dataclass(frozen=True)
class Goal:
    """Where a phase wants the flange, and which phase asked.

    Attributes:
        phase: Which phase the arm is in.
        target_position_world: Where the flange should be, in world frame meters.
        target_yaw_world: What the tool should be turned to about the belt
            normal, or None to hold the rotation the arm already has.
        track_id: Which track this is about, or None when no track is.
        observed_at_nanos: When this pose was seen. A goal is decided once
            per capture and held for half a second while the belt keeps
            moving, so a consumer aiming at it has to know how old it is.
        rides_belt: Whether the belt is carrying this pose while the arm
            travels to it. True for an object and false for the park pose,
            which is what tells guidance whether to aim ahead of it.
    """

    phase: Phase
    target_position_world: Point
    target_yaw_world: float | None = None
    track_id: int | None = None
    observed_at_nanos: int = 0
    rides_belt: bool = False

    def __init__(
        self,
        phase: Phase,
        target_position_world: Point | None = None,
        target_yaw_world: float | None = None,
        track_id: int | None = None,
        observed_at_nanos: int = 0,
        rides_belt: bool = False,
        *,
        position: Point | None = None,
        yaw: float | None = None,
    ) -> None:
        pos = target_position_world if target_position_world is not None else position
        if pos is None:
            raise TypeError("Goal requires target_position_world or position")
        y = target_yaw_world if target_yaw_world is not None else yaw
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "target_position_world", pos)
        object.__setattr__(self, "target_yaw_world", y)
        object.__setattr__(self, "track_id", track_id)
        object.__setattr__(self, "observed_at_nanos", observed_at_nanos)
        object.__setattr__(self, "rides_belt", rides_belt)

    @property
    def position(self) -> Point:
        """Backwards compatibility alias for target_position_world."""
        return self.target_position_world

    @property
    def yaw(self) -> float | None:
        """Backwards compatibility alias for target_yaw_world."""
        return self.target_yaw_world


class TaskMachine:
    """Runs one visit at a time.

    Holds three things across ticks: which track it is serving, when the
    flange first came inside tolerance of it, and which tracks it has already
    served or faulted. Everything else it reads from the queue it is handed.
    """

    def __init__(
        self,
        settings: TaskSettings,
        calibration: CalibrationSettings,
        belt_surface_height_world: float | None = None,
        belt_speed: float = 0.0,
        guidance: GuidanceSettings | None = None,
        admits: Callable[[Point], bool] | None = None,
        chutes: dict[str, Point] | None = None,
        belt_width: float = 0.50,
        belt_center_y: float = 0.0,
        belt_border_y: float | None = None,
        *,
        belt_surface: float | None = None,
    ) -> None:
        """Hold the settings and the belt the approach height is measured from.

        Args:
            settings: The phases, the tolerances and the park pose.
            calibration: The offset between a marker's pose and the flange.
            belt_surface_height_world: Height of the belt surface, in meters.
            belt_speed: How fast the belt runs, in meters per second, which a
                planned visit needs to know where the object will be.
            guidance: The speed and acceleration ceilings a planned arc has to
                respect. Required under the full-visit profile and unused
                under motion-only, which is stepped rather than planned.
            admits: Whether the arm is trusted at a pose, or None to plan
                without that check. Supplied rather than computed here, so
                the region a pick aims inside is the one the safety layer
                enforces and cannot drift from it.
            chutes: Where each channel's chute mouth stands. A visit ends
                over the one its object routes to; without them it ends at
                the retreat and the object goes back on the belt, which is
                a line with nowhere to put anything.
            belt_width: Width of the belt in meters.
            belt_center_y: Lateral center coordinate of the belt in meters.
            belt_border_y: Lateral position of the belt border on the chute side,
                or None to compute from belt_center_y - belt_width / 2.0.
            belt_surface: Legacy keyword alias for belt_surface_height_world.

        Raises:
            TaskError: If the profile plans arcs and was given neither the
                ceilings to plan them under nor a belt to plan them against.
        """
        surface = (
            belt_surface_height_world
            if belt_surface_height_world is not None
            else (0.0 if belt_surface is None else belt_surface)
        )
        if settings.profile is Profile.FULL_VISIT:
            if guidance is None:
                raise TaskError(
                    "the full-visit profile plans arcs and needs the speed and "
                    "acceleration ceilings to plan them under"
                )
            if not belt_speed > 0.0:
                raise TaskError(
                    f"the full-visit profile intercepts a moving object, and a "
                    f"belt at {belt_speed} m/s carries nothing to intercept"
                )
        self._settings = settings
        self._calibration = calibration
        self._belt_surface_height_world = surface
        self._belt_speed = belt_speed
        self._guidance = guidance
        self._admits = admits if admits is not None else _anywhere
        self._chutes = chutes or {}
        self._belt_border_y = (
            belt_border_y
            if belt_border_y is not None
            else (belt_center_y - belt_width / 2.0)
        )
        safe_clearance: float = (
            settings.safe_clearance
            if settings.safe_clearance is not None
            else settings.approach_height
        )
        self._safe_height_world = self._belt_surface_height_world + safe_clearance
        self._serving: int | None = None
        self._arrived_at: float | None = None
        self._phase = Phase.STANDBY
        self._served: list[int] = []
        self._faults: list[tuple[int | None, str]] = []
        self._arrivals: list[float] = []
        self._plan: Plan | None = None
        self._plan_yaw: float | None = None
        self._last_yaw: float | None = None
        self._pick_error: float | None = None
        self._missed: list[int] = []

    @property
    def belt_surface(self) -> float:
        """Backwards compatibility alias for belt_surface_height_world."""
        return self._belt_surface_height_world

    @property
    def served(self) -> tuple[int, ...]:
        """Every track this machine finished a visit to, in order."""
        return tuple(self._served)

    @property
    def arrivals(self) -> tuple[float, ...]:
        """How far the flange was from its goal at the moment that decides it.

        One figure per completed visit, in meters, and the moment differs by
        profile because what the profile is for differs. A motion-only visit
        is measured at the end of its dwell, which is when it claims to have
        arrived. A planned visit is measured at the instant the jaw reaches
        the object, which is the only instant a pick is decided at.

        Either way the arm is judged against the pose it was asked for, not
        against the object: whether that pose was the right pose is the
        tracker's question and is measured separately.
        """
        return tuple(self._arrivals)

    @property
    def missed(self) -> tuple[int, ...]:
        """Every track no interception existed for, in order.

        Distinct from a fault. A fault is the solver or the envelope refusing
        a pose, which is a problem with the pose. This is the arm being too
        far away or the object too near the end of the belt, which is a
        problem with the timing and is the normal way a line drops work.
        """
        return tuple(self._missed)

    @property
    def belt_speed(self) -> float:
        """How fast the machine believes the belt is running.

        Settable, because a line whose feed rate is regulated moves its belt
        and an interception solved against the speed the run drew is wrong by
        however far the controller has trimmed it since.
        """
        return self._belt_speed

    @belt_speed.setter
    def belt_speed(self, metres_per_second: float) -> None:
        self._belt_speed = metres_per_second

    @property
    def flying(self) -> bool:
        """Whether a planned visit is currently driving the arm.

        A caller reads this to know which regime it is in: while it is true
        the arm is driven from [TaskMachine.flight] and guidance is out of
        the path, because the arcs already respect the ceilings guidance
        would otherwise enforce.
        """
        return self._plan is not None

    @property
    def plan(self) -> Plan | None:
        """Return the active visit plan, if one is currently flying."""
        return self._plan

    @property
    def faults(self) -> tuple[tuple[int | None, str], ...]:
        """Every refusal, with the track it was about.

        The track is None when a refusal arrived with nothing being served
        and nothing queued. That is recorded rather than dropped, because a
        refusal nobody counted is the one way the arm can stop working and
        leave no trace of why.
        """
        return tuple(self._faults)

    def step(
        self,
        queue: Queue,
        flange_position_world: Point | None = None,
        at_seconds: float = 0.0,
        refusal: str | None = None,
        reference_velocity: Point = (0.0, 0.0, 0.0),
        *,
        flange: Point | None = None,
    ) -> Goal:
        """Decide what the arm is doing, and say where it wants the flange.

        Called at the cadence decisions are made at, which is slower than the
        cadence the arm is driven at. Under a planned visit the driving is
        [TaskMachine.flight]; this only commits to a candidate and then keeps
        out of the way until the plan runs out.

        Args:
            queue: The order selection produced.
            flange_position_world: Where the flange stands in world frame.
            at_seconds: Simulated time, which the dwell is measured against.
            refusal: Why the last commanded pose was refused, or None.
            reference_velocity: How fast the reference is moving, so a plan
                begins where the motion already is rather than asking for a
                step in velocity. Zero is right whenever the arm is at rest,
                which is where a visit normally starts.
            flange: Legacy keyword alias for flange_position_world.

        Returns:
            The goal for this tick.
        """
        flange_pos = (
            flange_position_world if flange_position_world is not None else flange
        )
        if flange_pos is None:
            raise TypeError("step requires flange_position_world or flange")
        at_nanos = int(at_seconds * NANOS_PER_SECOND)
        if refusal is not None:
            return self._fault(queue, flange_pos, refusal, at_nanos)

        if self._plan is not None:
            self._reaim(queue, at_seconds)
            return self._held(at_nanos)

        head = self._next(queue)
        if head is None:
            self._serving, self._arrived_at = None, None
            return self._rest(flange_pos, at_nanos)

        if self._settings.profile is Profile.FULL_VISIT:
            return self._commit(
                head, flange_pos, reference_velocity, at_seconds, at_nanos
            )

        if head.track_id != self._serving:
            self._serving, self._arrived_at = head.track_id, None
            self._phase = Phase.TRACK

        goal = self._track(head, at_nanos, self._phase)
        gap = math.dist(flange_pos, goal.position)
        if gap > self._settings.arrival_tolerance:
            # Not there yet, so the dwell has not started. A visit that
            # completes because time passed rather than because the arm
            # arrived makes every distance figure meaningless.
            self._arrived_at = None
            return goal

        if self._arrived_at is None:
            self._arrived_at = at_seconds
            return goal
        if at_seconds - self._arrived_at < self._settings.dwell_seconds:
            return goal

        # A stepped visit is one phase long: the arm goes to the marker and
        # moves on. Everything past tracking belongs to a plan, and a plan
        # never reaches here.
        self._arrivals.append(gap)
        self._served.append(head.track_id)
        self._serving, self._arrived_at = None, None
        self._phase = Phase.STANDBY
        return self.step(queue, flange_pos, at_seconds)

    def flight(
        self,
        at_seconds: float,
        flange_position_world: Point | None = None,
        *,
        flange: Point | None = None,
    ) -> Flight | None:
        """Drive one tick of a planned visit, or report that none is flying.

        Called at the rate the arm is actually commanded at, which is the
        physics rate: a goal half a second old is still the right goal, and a
        joint command half a second old is a lurch.

        Args:
            at_seconds: Simulated time.
            flange_position_world: Where the flange stands, read only to
                measure how near it came to the object when the jaw closed.
            flange: Legacy keyword alias for flange_position_world.

        Returns:
            What to command, or None when no plan is flying. None on the tick
            a plan runs out, which is also when the visit is recorded, so a
            caller that stops asking on None never misses the end.
        """
        flange_pos = (
            flange_position_world if flange_position_world is not None else flange
        )
        if flange_pos is None:
            raise TypeError("flight requires flange_position_world or flange")
        if self._plan is None:
            return None
        sampled = self._plan.at(at_seconds)
        if sampled is None:
            self._finish(flange_pos)
            return None
        phase, state, grip = sampled
        if phase is Phase.HOLD and self._pick_error is None:
            # The hold begins at the instant the jaw reaches the object, so
            # the first tick of it is the one a pick is decided on. Later
            # ticks are the carry, and measuring there would report how well
            # the arm rides the belt rather than how well it arrived.
            self._pick_error = math.dist(flange_pos, state.position)
        self._phase = phase
        yaw = self._plan.yaw_at(at_seconds)
        if yaw is None:
            yaw = self._plan_yaw
        self._last_yaw = yaw
        return Flight(
            phase=phase,
            position=state.position,
            velocity=state.velocity,
            yaw=yaw,
            grip=grip,
        )

    def _grasp_pose(self, head: Candidate) -> Point:
        """Return where the flange has to sit to grasp a candidate.

        Args:
            head: The candidate.

        Returns:
            The marker's flange pose with the calibration offset applied,
            which is the pose a plan aims at and the pose a stepped visit
            descends to. One place, so the two cannot disagree.
        """
        offset = self._calibration.flange_offset
        return (
            head.flange_position_world[0] + offset[0],
            head.flange_position_world[1] + offset[1],
            head.flange_position_world[2] + offset[2],
        )

    def _reaim(self, queue: Queue, at_seconds: float) -> None:
        """Point the plan in flight at a fresher estimate of its object.

        The arrival time does not move, so everything downstream of this is
        still scheduled against the same instant. What moves is where the
        approach ends, which is what stops a three second old prediction
        from deciding where a jaw closes.

        Args:
            queue: The order selection produced, for the track being served.
            at_seconds: Simulated time.
        """
        assert self._plan is not None
        assert self._guidance is not None
        head = next(
            (item for item in queue.order if item.track_id == self._plan.track_id),
            None,
        )
        if head is None:
            return
        target = self._grasp_pose(head)
        transit_height_world = self._safe_height_world
        retreat_lift = max(
            self._settings.grasp_clearance, transit_height_world - target[2]
        )
        chute = self._chutes.get(head.channel)
        over = (chute[0], chute[1], transit_height_world) if chute is not None else None
        obj_vel = (
            head.velocity_world
            if head.velocity_world is not None
            else (self._belt_speed, 0.0, 0.0)
        )
        clamped_vel = (max(0.0, obj_vel[0]), obj_vel[1], obj_vel[2])
        refreshed = refine(
            plan=self._plan,
            object_position=target,
            belt_velocity=clamped_vel,
            z_offset=self._settings.grasp_clearance,
            approach_speed=self._settings.approach_speed,
            dwell_seconds=self._settings.dwell_seconds,
            max_speed=self._guidance.max_speed,
            max_acceleration=self._guidance.max_acceleration,
            at_seconds=at_seconds,
            over=over,
            retreat_lift=retreat_lift,
            belt_border_y=self._belt_border_y,
            safe_height_world=transit_height_world,
            cross_speed=self._settings.approach_speed,
        )
        initial_yaw: float | None = (
            self._last_yaw if self._last_yaw is not None else head.closing_yaw_belt
        )
        if head.closing_yaw_belt is not None:
            self._plan_yaw = head.closing_yaw_belt
            self._plan = self._plan.with_yaw(
                target_yaw=head.closing_yaw_belt,
                initial_yaw=initial_yaw,
            )
        if refreshed is not None:
            descent_leg = next(
                leg for leg in refreshed.legs if leg.phase is Phase.DESCEND
            )
            if self._admits(descent_leg.segment.end.position):
                self._plan = refreshed.with_yaw(
                    target_yaw=head.closing_yaw_belt,
                    initial_yaw=initial_yaw,
                )

    def _commit(
        self,
        head: Candidate,
        flange: Point,
        velocity: Point,
        at_seconds: float,
        at_nanos: int,
    ) -> Goal:
        """Plan a whole visit to a candidate, or give it up.

        Args:
            head: The candidate to serve.
            flange: Where the flange stands.
            velocity: How fast the reference is moving, so the first arc
                begins where the motion already is.
            at_seconds: Simulated time the plan starts.
            at_nanos: The same instant, for the goal it returns.

        Returns:
            A goal naming the approach point, or the park pose when no
            interception exists. An object the arm cannot reach in the belt
            it has left is recorded as missed and skipped, because chasing it
            costs the objects behind it.
        """
        # The constructor refused this profile without ceilings to plan under.
        assert self._guidance is not None
        if not self._admits(flange):
            # A plan begins where the arm is, so an arm outside the region it
            # is trusted over produces a plan whose very first pose the servo
            # refuses, and the refusal tears up the plan that caused it, and
            # the next capture builds the same one again. Measured on the
            # shipped line that latched: one excursion became 46 faults and
            # the arm never moved again.
            #
            # Going home is the recovery, because the park pose is inside the
            # region by construction and the servo will take it. The
            # candidate is not recorded as missed: nothing is wrong with it.
            self._serving = None
            return self._rest(flange, at_nanos)
        target = self._grasp_pose(head)
        transit_height_world = self._safe_height_world
        retreat_lift = max(
            self._settings.grasp_clearance, transit_height_world - target[2]
        )
        chute = self._chutes.get(head.channel)
        over = (chute[0], chute[1], transit_height_world) if chute is not None else None
        # An interception is worth planning only inside what the object has
        # left on the belt, whichever of the two limits binds first.
        obj_vel = (
            head.velocity_world
            if head.velocity_world is not None
            else (self._belt_speed, 0.0, 0.0)
        )
        speed_x = max(0.01, obj_vel[0])
        clamped_vel = (max(0.0, obj_vel[0]), obj_vel[1], obj_vel[2])
        leaving = head.distance_before_leaving / speed_x
        # The margin buys room to re-aim and it buys it by intercepting
        # further downstream, which can put the pick past the edge of the
        # annulus. Where it does, the soonest interception is taken instead:
        # an arc that cannot be corrected still beats one the arm cannot fly.
        plan = None
        for margin in (self._settings.interception_margin, 1.0):
            attempt = plan_pick(
                flange=State(
                    position=flange, velocity=velocity, acceleration=(0.0, 0.0, 0.0)
                ),
                track_id=head.track_id,
                object_position=target,
                belt_velocity=clamped_vel,
                z_offset=self._settings.grasp_clearance,
                approach_speed=self._settings.approach_speed,
                dwell_seconds=self._settings.dwell_seconds,
                max_speed=self._guidance.max_speed,
                max_acceleration=self._guidance.max_acceleration,
                latest=min(self._settings.interception_limit, leaving),
                at_seconds=at_seconds,
                margin=margin,
                over=over,
                retreat_lift=retreat_lift,
                belt_border_y=self._belt_border_y,
                safe_height_world=transit_height_world,
                cross_speed=self._settings.approach_speed,
            )
            if attempt is not None:
                descent_leg = next(
                    leg for leg in attempt.legs if leg.phase is Phase.DESCEND
                )
                if self._admits(descent_leg.segment.end.position):
                    plan = attempt
                    break
        if plan is None:
            self._missed.append(head.track_id)
            self._serving = None
            LOGGER.debug(
                "pick planning failed for candidate %d (leaving=%.3f s); marked missed",
                head.track_id,
                leaving,
            )
            return self._rest(flange, at_nanos)
        target_yaw = head.closing_yaw_belt
        initial_yaw = self._last_yaw if self._last_yaw is not None else target_yaw
        self._plan = plan.with_yaw(target_yaw=target_yaw, initial_yaw=initial_yaw)
        self._plan_yaw = target_yaw
        self._serving = head.track_id
        self._pick_error = None
        self._phase = Phase.TRACK
        LOGGER.debug(
            "committed pick plan for candidate %d: duration=%.3f s, legs=%d, chute=%s",
            head.track_id,
            plan.duration,
            len(plan.legs),
            head.channel,
        )
        return Goal(
            phase=Phase.TRACK,
            rides_belt=True,
            target_position_world=plan.legs[0].segment.end.position,
            target_yaw_world=head.closing_yaw_belt,
            track_id=head.track_id,
            observed_at_nanos=at_nanos,
        )

    def _held(self, at_nanos: int) -> Goal:
        """Report the visit already in flight, without re-deciding it.

        Args:
            at_nanos: Now.

        Returns:
            A goal naming the phase and the pose the plan is currently
            asking for. It exists so a caller can report what the arm is
            doing; nothing consumes it to steer, because the plan does that.
        """
        assert self._plan is not None
        elapsed = max(0.0, at_nanos / NANOS_PER_SECOND - self._plan.started_at)
        sampled = self._plan.at(self._plan.started_at + elapsed)
        position = (
            self._plan.legs[-1].segment.end.position
            if sampled is None
            else sampled[1].position
        )
        return Goal(
            phase=self._phase,
            rides_belt=True,
            target_position_world=position,
            target_yaw_world=self._plan_yaw,
            track_id=self._plan.track_id,
            observed_at_nanos=at_nanos,
        )

    def _finish(self, flange: Point) -> None:
        """Close a planned visit that has run out of arcs.

        Args:
            flange: Where the flange stands, used only if the hold was
                shorter than a tick and so was never sampled. That cannot
                happen at the shipped dwell and tick, and falling back beats
                recording a figure nobody measured.
        """
        assert self._plan is not None
        last = self._plan.legs[-1].segment.end.position
        error = (
            self._pick_error
            if self._pick_error is not None
            else math.dist(flange, last)
        )
        self._arrivals.append(error)
        self._served.append(self._plan.track_id)
        LOGGER.debug(
            "completed pick visit for candidate %d: pick_error=%.4f m",
            self._plan.track_id,
            error,
        )
        self._plan = None
        self._plan_yaw = None
        self._pick_error = None
        self._serving = None
        self._arrived_at = None
        self._phase = Phase.STANDBY

    def _next(self, queue: Queue) -> Candidate | None:
        """Return the first candidate worth serving, or None.

        Args:
            queue: The order selection produced.

        Returns:
            The head, skipping anything already served, faulted or missed. A
            pose the solver refused will be refused again, so retrying it
            forever is an arm that stops working on the first bad pose, and
            an object no interception existed for only gets further away.
        """
        refused = {track_id for track_id, _ in self._faults if track_id is not None}
        done = set(self._served) | refused | set(self._missed)
        return next((item for item in queue.order if item.track_id not in done), None)

    def _track(self, head: Candidate, at_nanos: int, phase: Phase) -> Goal:
        """Return the goal one phase of a visit asks for.

        Args:
            head: The candidate being served.
            at_nanos: When the candidate's pose was seen.
            phase: Which phase of the visit this is.

        Returns:
            The goal, carrying the calibration offset. Only the height
            changes between phases: the descent follows the object along the
            belt exactly as the approach did, because the belt does not stop
            while the flange comes down.
        """
        offset = self._calibration.flange_offset
        above = (
            head.flange_position_world[2] - self._belt_surface_height_world
            if phase is Phase.DESCEND
            else self._settings.approach_height
        )
        return Goal(
            phase=phase,
            rides_belt=True,
            target_position_world=(
                head.flange_position_world[0] + offset[0],
                head.flange_position_world[1] + offset[1],
                self._belt_surface_height_world + above + offset[2],
            ),
            target_yaw_world=head.closing_yaw_belt,
            track_id=head.track_id,
            observed_at_nanos=at_nanos,
        )

    def _rest(self, flange: Point, at_nanos: int) -> Goal:
        """Return the goal for an arm with nothing to serve.

        Args:
            flange: Where the flange stands.
            at_nanos: Now.

        Returns:
            The park pose, under the phase that says whether the arm is still
            travelling to it.
        """
        park = self._settings.park_position_world
        arrived = math.dist(flange, park) <= self._settings.arrival_tolerance
        return Goal(
            phase=Phase.STANDBY if arrived else Phase.PARK,
            target_position_world=park,
            target_yaw_world=None,
            track_id=None,
            observed_at_nanos=at_nanos,
        )

    def _fault(self, queue: Queue, flange: Point, refusal: str, at_nanos: int) -> Goal:
        """Record a refusal and hold the arm where it is.

        A refusal is about the pose commanded on the previous tick, so the
        track it belongs to is normally the one being served. On the first
        tick of a run there is no such track, and the refusal is attributed
        to the head the machine would have served instead. Only when nothing
        is queued either does it go down against no track, which is still
        recorded: a refusal nobody counted is the one way the arm can stop
        working and leave no trace of why.

        Args:
            queue: The order selection produced, read only for its head.
            flange: Where the flange stands.
            refusal: Why the pose was refused.
            at_nanos: Now.

        Returns:
            A goal asking for no motion, so a refused pose moves nothing.
        """
        self._plan, self._plan_yaw, self._pick_error = None, None, None
        faulted = self._serving
        if faulted is None:
            head = self._next(queue)
            faulted = None if head is None else head.track_id
        LOGGER.warning(
            "task machine faulted: refusal=%s (candidate=%s)",
            refusal,
            faulted,
        )
        already = {track_id for track_id, _ in self._faults}
        if faulted is None or faulted not in already:
            self._faults.append((faulted, refusal))
        self._serving, self._arrived_at = None, None
        self._phase = Phase.STANDBY
        return Goal(
            phase=Phase.FAULT,
            target_position_world=flange,
            target_yaw_world=None,
            track_id=faulted,
            observed_at_nanos=at_nanos,
        )


def _anywhere(pose: Point) -> bool:
    """Admit any pose, for a caller that supplied no region.

    Args:
        pose: The pose.

    Returns:
        True.
    """
    del pose
    return True
