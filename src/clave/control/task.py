"""The phases of one visit, and the pose each phase asks for.

A visit is what the arm does about one object: go to it, stay with it long
enough to prove it arrived, and move on. The machine says which phase it is
in and where it wants the flange; it decides nothing about the path there,
which is guidance, and nothing about joint angles, which is the servo.

Under the motion-only profile the phases are standby, tracking, parking and
fault. That is what tuning arm speed against belt speed needs: the flange
rides at approach height the whole time, so nothing about a descent muddies
what a distance figure means. The full-visit profile adds descent to the
grasp plane, a dwell there, and a retreat back to approach height.

Neither profile grasps. No gripper exists in the model, so the phases one
would need are absent from both rather than present and skipped, and a
full visit therefore descends onto an object, waits over it, and leaves.

**A descent follows the object it descends onto.** The belt does not stop
while the flange comes down, so the descent goal keeps riding the belt and
only its height changes. A descent to a fixed point would put the flange
where the object was when the descent started.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from clave.control.selection import Candidate, Queue
from clave.control.settings import (
    CalibrationSettings,
    Phase,
    Point,
    Profile,
    TaskSettings,
)
from clave.errors import ClaveError

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the instant a goal records."""


class TaskError(ClaveError):
    """The task machine cannot run this configuration."""


@dataclass(frozen=True)
class Goal:
    """Where a phase wants the flange, and which phase asked.

    Attributes:
        phase: Which phase the arm is in.
        position: Where the flange should be, in belt frame meters.
        yaw: What the tool should be turned to about the belt normal, or None
            to hold the rotation the arm already has.
        track_id: Which track this is about, or None when no track is.
        observed_at_nanos: When this pose was seen. A goal is decided once
            per capture and held for half a second while the belt keeps
            moving, so a consumer aiming at it has to know how old it is.
        rides_belt: Whether the belt is carrying this pose while the arm
            travels to it. True for an object and false for the park pose,
            which is what tells guidance whether to aim ahead of it.
    """

    phase: Phase
    position: Point
    yaw: float | None
    track_id: int | None
    observed_at_nanos: int
    rides_belt: bool = False


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
        belt_surface: float,
    ) -> None:
        """Hold the settings and the belt the approach height is measured from.

        Args:
            settings: The phases, the tolerances and the park pose.
            calibration: The offset between a marker's pose and the flange.
            belt_surface: Height of the belt surface, in meters.

        Raises:
            TaskError: If the profile is one this machine does not run.
        """
        self._settings = settings
        self._calibration = calibration
        self._belt_surface = belt_surface
        self._serving: int | None = None
        self._arrived_at: float | None = None
        self._phase = Phase.STANDBY
        self._served: list[int] = []
        self._faults: list[tuple[int | None, str]] = []
        self._arrivals: list[float] = []

    @property
    def served(self) -> tuple[int, ...]:
        """Every track this machine finished a visit to, in order."""
        return tuple(self._served)

    @property
    def arrivals(self) -> tuple[float, ...]:
        """How far the flange was from its goal at the end of each dwell.

        One figure per completed visit, in meters. This is what the run
        reports: the arm is judged against the pose it was asked for, not
        against the object, because whether that pose was the right pose is
        the tracker's question and is measured separately.
        """
        return tuple(self._arrivals)

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
        flange: Point,
        at_seconds: float,
        refusal: str | None = None,
    ) -> Goal:
        """Advance one tick and say where the flange should go.

        Args:
            queue: The order selection produced.
            flange: Where the flange stands.
            at_seconds: Simulated time, which the dwell is measured against.
            refusal: Why the last commanded pose was refused, or None.

        Returns:
            The goal for this tick.
        """
        at_nanos = int(at_seconds * NANOS_PER_SECOND)
        if refusal is not None:
            return self._fault(queue, flange, refusal, at_nanos)

        head = self._next(queue)
        if head is None:
            self._serving, self._arrived_at = None, None
            return self._rest(flange, at_nanos)

        if head.track_id != self._serving:
            self._serving, self._arrived_at = head.track_id, None
            self._phase = Phase.TRACK

        goal = self._track(head, at_nanos, self._phase)
        gap = math.dist(flange, goal.position)
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

        following = self._after(self._phase)
        if following is None:
            self._arrivals.append(gap)
            self._served.append(head.track_id)
            self._serving, self._arrived_at = None, None
            self._phase = Phase.STANDBY
            return self.step(queue, flange, at_seconds)
        self._phase, self._arrived_at = following, None
        return self._track(head, at_nanos, self._phase)

    def _after(self, phase: Phase) -> Phase | None:
        """Return the phase that follows this one, or None to end the visit.

        Args:
            phase: The phase just completed.

        Returns:
            The next phase. Under the motion-only profile a visit is one
            phase long, so tracking ends it. A full visit descends onto the
            object, dwells there, and retreats before the visit closes.
        """
        if self._settings.profile is Profile.MOTION_ONLY:
            return None
        return {Phase.TRACK: Phase.DESCEND, Phase.DESCEND: Phase.RETREAT}.get(phase)

    def _next(self, queue: Queue) -> Candidate | None:
        """Return the first candidate worth serving, or None.

        Args:
            queue: The order selection produced.

        Returns:
            The head, skipping anything already served or faulted. A pose the
            solver refused will be refused again, so retrying it forever is an
            arm that stops working on the first bad pose.
        """
        refused = {track_id for track_id, _ in self._faults if track_id is not None}
        done = set(self._served) | refused
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
            head.flange[2] - self._belt_surface
            if phase is Phase.DESCEND
            else self._settings.approach_height
        )
        return Goal(
            phase=phase,
            rides_belt=True,
            position=(
                head.flange[0] + offset[0],
                head.flange[1] + offset[1],
                self._belt_surface + above + offset[2],
            ),
            yaw=head.closing_axis,
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
        park = self._settings.park_position
        arrived = math.dist(flange, park) <= self._settings.arrival_tolerance
        return Goal(
            phase=Phase.STANDBY if arrived else Phase.PARK,
            position=park,
            yaw=None,
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
        faulted = self._serving
        if faulted is None:
            head = self._next(queue)
            faulted = None if head is None else head.track_id
        already = {track_id for track_id, _ in self._faults}
        if faulted is None or faulted not in already:
            self._faults.append((faulted, refusal))
        self._serving, self._arrived_at = None, None
        self._phase = Phase.STANDBY
        return Goal(
            phase=Phase.FAULT,
            position=flange,
            yaw=None,
            track_id=faulted,
            observed_at_nanos=at_nanos,
        )
