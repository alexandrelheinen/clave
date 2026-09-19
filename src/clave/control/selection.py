"""Ordering the markers into a queue the arm works through.

This is a travelling-salesman problem with a deadline, and the deadline is
what makes the ordinary metric wrong: an object about to run out of belt is
worth more than a nearer one that will still be there. Each candidate is
therefore scored

    cost = distance_to_flange + exit_weight * distance_before_leaving

with both terms in meters, so the weight is dimensionless. The order is built
greedily, scoring each next candidate from where the flange will stand after
the previous one, which is nearest-neighbour tour construction and not an
optimal tour. Naming that is the point: the ordering is a starting algorithm
chosen to be replaced, and calling it optimal would hide that it is not.

What is absent here is deliberate and scheduled. The anchors that quantise the
ordering's input, and recomputing the order on change rather than every tick,
belong to the step after this one. Until they land, the order is rebuilt on
every call and will jitter with the tracker's own estimate.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from clave.control.settings import Point, SelectionSettings
from clave.tracker.markers import GraspMarker

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the instants a marker carries."""


@dataclass(frozen=True)
class Candidate:
    """One marker, scored and ready for the task layer.

    Attributes:
        track_id: The identity this came from.
        flange: Where the marker wants the flange.
        closing_axis: Rotation of the jaw about the belt normal, or None when
            the footprint had no axis to turn one to.
        distance_before_leaving: How much belt the object has left, in meters.
    """

    track_id: int
    flange: Point
    closing_axis: float | None
    distance_before_leaving: float


@dataclass(frozen=True)
class Queue:
    """The order the arm works through.

    Attributes:
        order: Every candidate, best first.
        recomputed: Whether this call rebuilt the order. Always true until the
            anchors land, and carried now so the runtime can report it
            without changing shape later.
    """

    order: tuple[Candidate, ...]
    recomputed: bool

    @property
    def head(self) -> Candidate | None:
        """The candidate the arm should serve, or None when there is none."""
        return self.order[0] if self.order else None


class Selector:
    """Turns markers into an ordered queue.

    The one object in the control path that will hold state. It holds none
    yet: the anchors it will carry arrive with the step that damps the
    ordering, and constructing it now is what keeps that arrival from
    changing every caller.
    """

    def __init__(
        self, settings: SelectionSettings, admits: Callable[[Point], bool]
    ) -> None:
        """Hold the settings the ordering reads and the region it aims inside.

        Args:
            settings: The weight and the anchor radius.
            admits: Whether the arm is trusted over a pose. Supplied rather
                than computed here, so the region selection aims inside is
                the same object `clave.world.arm` enforces and cannot drift
                from it.
        """
        self._settings = settings
        self._admits = admits

    def update(
        self,
        markers: tuple[GraspMarker, ...],
        flange: Point,
        belt_speed: float,
        at_nanos: int,
    ) -> Queue:
        """Return the order to serve these markers in.

        Args:
            markers: Every marker the tracker settled at this instant.
            flange: Where the flange stands.
            belt_speed: How fast the belt runs, in meters per second.
            at_nanos: The instant the markers were settled at.

        Returns:
            The queue, best first.
        """
        remaining = [
            _candidate(marker, belt_speed, at_nanos)
            for marker in markers
            if self._admissible(marker, at_nanos)
        ]
        order: list[Candidate] = []
        # Nearest neighbour: each pick moves the flange, and the next one is
        # scored from where it landed rather than from where the arm started.
        standing = flange
        while remaining:
            best = min(remaining, key=lambda item: self._cost(item, standing))
            remaining.remove(best)
            order.append(best)
            standing = best.flange
        return Queue(order=tuple(order), recomputed=True)

    def _admissible(self, marker: GraspMarker, at_nanos: int) -> bool:
        """Return whether a marker is worth ordering at all.

        Three different refusals, and keeping them apart matters. The jaw may
        not open wide enough, which is what `GraspMarker.reachable` reports.
        The arm may not be trusted over the pose, which is a different
        question about a different machine and is what `admits` answers. And
        the window may already have closed. Ordering a marker that fails any
        of them spends a visit on something the arm was always going to
        refuse.

        Args:
            marker: The marker.
            at_nanos: The instant it was settled at.

        Returns:
            Whether to order it.
        """
        return (
            marker.reachable
            and marker.valid_until_nanos > at_nanos
            and self._admits(marker.flange)
        )

    def _cost(self, candidate: Candidate, flange: Point) -> float:
        """Return what serving this candidate from here costs.

        Args:
            candidate: The candidate scored.
            flange: Where the flange stands, or will stand.

        Returns:
            The cost, in meters. Lower is served sooner, so an object with
            little belt left scores low and outranks a nearer one.
        """
        travel = math.dist(flange, candidate.flange)
        return travel + self._settings.exit_weight * candidate.distance_before_leaving


def _candidate(marker: GraspMarker, belt_speed: float, at_nanos: int) -> Candidate:
    """Turn one marker into a scored candidate.

    Args:
        marker: The marker.
        belt_speed: How fast the belt runs, in meters per second.
        at_nanos: The instant the marker was settled at.

    Returns:
        The candidate. The belt it has left is derived here rather than stored
        on the marker, because it depends on a speed and an instant that the
        marker knows nothing about.
    """
    seconds = (marker.valid_until_nanos - at_nanos) / NANOS_PER_SECOND
    return Candidate(
        track_id=marker.track_id,
        flange=marker.flange,
        closing_axis=marker.closing_axis,
        distance_before_leaving=max(0.0, seconds * belt_speed),
    )
