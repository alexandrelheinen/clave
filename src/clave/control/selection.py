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

**The queue is damped at its inputs rather than frozen at its output.** A
mean of 2.67 objects sit inside the workspace at once, peaking at six, so an
order rebuilt every tick swaps targets faster than the arm can traverse
between them and leaves it oscillating near the centroid. Freezing the choice
until it is served is the obvious fix and the wrong one: it cannot react to
the object that appears between the flange and the target, or to the one
about to fall off the end.

So the input is quantised instead. Each track carries an anchor, and the
anchor follows the tracker's estimate only when the estimate moves more than
a configured radius. The order is then rebuilt when a track opens, when a
track retires, and when an anchor moves, and at no other time.

**An anchor is compared after being carried along the belt.** An object doing
what the belt makes it do has not moved in the frame that matters, and
comparing raw positions would re-anchor every object every few tens of
milliseconds, which is the whole mechanism defeated. Belt travel also
subtracts a common term from every deadline, so it cannot change an ordering
even when one is rebuilt.

The anchor is what the ordering scores. It is not what the arm is commanded
to: a candidate carries the live pose as well, because an arm sent to a
quantised pose jumps by the radius every time the anchor catches up.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from clave.control.settings import Point, SelectionSettings
from clave.tracker.belt_frame import carry
from clave.tracker.markers import GraspMarker

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the instants a marker carries."""


@dataclass(frozen=True)
class Candidate:
    """One marker, scored and ready for the task layer.

    Attributes:
        track_id: The identity this came from.
        anchor: Where the ordering scored it, which lags the live pose by up
            to the anchor radius and is what holds the order still.
        flange: Where the marker wants the flange, live rather than
            quantised, because that is what the arm is commanded to.
        closing_axis: Rotation of the jaw about the belt normal, or None when
            the footprint had no axis to turn one to.
        distance_before_leaving: How much belt the object has left, in meters.
    """

    track_id: int
    anchor: Point
    flange: Point
    closing_axis: float | None
    distance_before_leaving: float


@dataclass(frozen=True)
class Queue:
    """The order the arm works through.

    Attributes:
        order: Every candidate, best first.
        recomputed: Whether this call rebuilt the order, rather than applying
            the order it already had to fresh poses.
        reasons: Which triggers fired, among `appeared`, `retired` and
            `anchor`. Reported apart because they mean different things: a
            rebuild on a track appearing is the design working, and a rebuild
            on an anchor is the estimate having genuinely moved. Counting
            them together hides whether the anchors damp anything.
    """

    order: tuple[Candidate, ...]
    recomputed: bool
    reasons: frozenset[str] = frozenset()

    @property
    def head(self) -> Candidate | None:
        """The candidate the arm should serve, or None when there is none."""
        return self.order[0] if self.order else None


@dataclass(frozen=True)
class _Anchor:
    """Where a track was scored, and when.

    Attributes:
        position: The position, in belt frame meters.
        at_nanos: When it was taken, so belt travel since then can be carried
            before the anchor is compared to anything.
    """

    position: Point
    at_nanos: int


class Selector:
    """Turns markers into an ordered queue, and holds that order still.

    The one stateful object in the control path. It remembers two things: an
    anchor per open track, and the order those tracks were last sorted into.
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
        self._anchors: dict[int, _Anchor] = {}
        self._order: tuple[int, ...] = ()

    @property
    def anchor_count(self) -> int:
        """How many tracks are anchored, so a leak is visible from a test."""
        return len(self._anchors)

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
            The queue, best first, holding the order it already had unless
            something happened that could change it.
        """
        live = {
            marker.track_id: marker
            for marker in markers
            if self._admissible(marker, at_nanos)
        }
        for track_id in tuple(self._anchors):
            if track_id not in live:
                del self._anchors[track_id]

        reasons = set()
        if self._reanchor(live, belt_speed, at_nanos):
            reasons.add("anchor")
        if any(track_id not in live for track_id in self._order):
            reasons.add("retired")
        if any(track_id not in self._order for track_id in live):
            reasons.add("appeared")
        if reasons:
            self._order = self._sorted(live, flange, belt_speed, at_nanos)

        return Queue(
            order=tuple(
                _candidate(
                    live[track_id],
                    self._carried(track_id, belt_speed, at_nanos),
                    belt_speed,
                    at_nanos,
                )
                for track_id in self._order
            ),
            recomputed=bool(reasons),
            reasons=frozenset(reasons),
        )

    def _reanchor(
        self, live: dict[int, GraspMarker], belt_speed: float, at_nanos: int
    ) -> bool:
        """Move any anchor whose track has left its radius, and say whether one did.

        Args:
            live: Every admissible marker, by track.
            belt_speed: How fast the belt runs, in meters per second.
            at_nanos: The instant the markers were settled at.

        Returns:
            Whether an existing anchor moved. A track being anchored for the
            first time is not counted here: that is a track appearing, and it
            is reported as one.
        """
        moved = False
        for track_id, marker in live.items():
            held = self._anchors.get(track_id)
            if held is None:
                self._anchors[track_id] = _Anchor(marker.grasp, at_nanos)
                continue
            carried = carry(held.position, belt_speed, held.at_nanos, at_nanos)
            if math.dist(marker.grasp, carried) > self._settings.anchor_radius:
                self._anchors[track_id] = _Anchor(marker.grasp, at_nanos)
                moved = True
        return moved

    def _carried(self, track_id: int, belt_speed: float, at_nanos: int) -> Point:
        """Return a track's anchor, carried to now.

        Args:
            track_id: Whose anchor.
            belt_speed: How fast the belt runs, in meters per second.
            at_nanos: The instant to carry it to.

        Returns:
            The anchor, where the belt has taken it since it was set.
        """
        held = self._anchors[track_id]
        return carry(held.position, belt_speed, held.at_nanos, at_nanos)

    def _sorted(
        self,
        live: dict[int, GraspMarker],
        flange: Point,
        belt_speed: float,
        at_nanos: int,
    ) -> tuple[int, ...]:
        """Return the order to serve these tracks in.

        Args:
            live: Every admissible marker, by track.
            flange: Where the flange stands.
            belt_speed: How fast the belt runs, in meters per second.
            at_nanos: The instant the markers were settled at.

        Returns:
            The track ids, best first.
        """
        remaining = [
            _candidate(
                marker,
                self._carried(track_id, belt_speed, at_nanos),
                belt_speed,
                at_nanos,
            )
            for track_id, marker in live.items()
        ]
        order: list[int] = []
        # Nearest neighbour: each pick moves the flange, and the next one is
        # scored from where it landed rather than from where the arm started.
        standing = flange
        while remaining:
            best = min(remaining, key=lambda item: self._cost(item, standing))
            remaining.remove(best)
            order.append(best.track_id)
            standing = best.anchor
        return tuple(order)

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
        travel = math.dist(flange, candidate.anchor)
        return travel + self._settings.exit_weight * candidate.distance_before_leaving


def _candidate(
    marker: GraspMarker, anchor: Point, belt_speed: float, at_nanos: int
) -> Candidate:
    """Turn one marker into a scored candidate.

    Args:
        marker: The marker.
        anchor: Where the ordering scores it, carried to now.
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
        anchor=anchor,
        flange=marker.flange,
        closing_axis=marker.closing_axis,
        distance_before_leaving=max(0.0, seconds * belt_speed),
    )
