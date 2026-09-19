"""The phases of one visit, and the pose each phase asks for.

A visit is what the arm does about one object: go to it, stay with it long
enough to prove it arrived, and move on. The machine says which phase it is
in and where it wants the flange; it decides nothing about the path there,
which is guidance, and nothing about joint angles, which is the servo.

Under the motion-only profile the phases are standby, tracking, parking and
fault. That is what tuning arm speed against belt speed needs: the flange
rides at approach height the whole time, so nothing about a descent muddies
what a distance figure means. The full-visit profile adds descent, dwell at
the grasp plane and retreat, and it is not implemented yet: a machine that
quietly ran the motion-only phases under a full-visit configuration would
report figures for a visit that never descended, so it refuses instead.

Neither profile grasps. No gripper exists in the model, so the phases one
would need are absent from both rather than present and skipped.
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
    """

    phase: Phase
    position: Point
    yaw: float | None
    track_id: int | None


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
        if settings.profile is not Profile.MOTION_ONLY:
            raise TaskError(
                f"task.profile is {settings.profile.value!r}, and only "
                f"{Profile.MOTION_ONLY.value!r} is implemented. Descent, dwell "
                f"and retreat have not been written, and running the "
                f"motion-only phases under a full_visit configuration would "
                f"report figures for a visit that never descended"
            )
        self._settings = settings
        self._calibration = calibration
        self._belt_surface = belt_surface
        self._serving: int | None = None
        self._arrived_at: float | None = None
        self._served: list[int] = []
        self._faults: list[tuple[int | None, str]] = []

    @property
    def served(self) -> tuple[int, ...]:
        """Every track this machine finished a visit to, in order."""
        return tuple(self._served)

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
        if refusal is not None:
            return self._fault(queue, flange, refusal)

        head = self._next(queue)
        if head is None:
            self._serving, self._arrived_at = None, None
            return self._rest(flange)

        if head.track_id != self._serving:
            self._serving, self._arrived_at = head.track_id, None

        goal = self._track(head)
        if math.dist(flange, goal.position) > self._settings.arrival_tolerance:
            # Not there yet, so the dwell has not started. A visit that
            # completes because time passed rather than because the arm
            # arrived makes every distance figure meaningless.
            self._arrived_at = None
            return goal

        if self._arrived_at is None:
            self._arrived_at = at_seconds
        elif at_seconds - self._arrived_at >= self._settings.dwell_seconds:
            self._served.append(head.track_id)
            self._serving, self._arrived_at = None, None
            return self.step(queue, flange, at_seconds)
        return goal

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

    def _track(self, head: Candidate) -> Goal:
        """Return the goal for following one candidate.

        Args:
            head: The candidate being served.

        Returns:
            The goal, at approach height and carrying the calibration offset.
        """
        offset = self._calibration.flange_offset
        return Goal(
            phase=Phase.TRACK,
            position=(
                head.flange[0] + offset[0],
                head.flange[1] + offset[1],
                self._belt_surface + self._settings.approach_height + offset[2],
            ),
            yaw=head.closing_axis,
            track_id=head.track_id,
        )

    def _rest(self, flange: Point) -> Goal:
        """Return the goal for an arm with nothing to serve.

        Args:
            flange: Where the flange stands.

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
        )

    def _fault(self, queue: Queue, flange: Point, refusal: str) -> Goal:
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
        return Goal(phase=Phase.FAULT, position=flange, yaw=None, track_id=faulted)
