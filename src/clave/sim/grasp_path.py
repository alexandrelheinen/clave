"""What the gripper does to a package before the jaw shuts.

A close a few millimetres from the package can follow a descent that arrived
downstream of it and swept back through it. The close hides that. These
figures are the approach: how far the package slid and turned relative to the
belt between the first touch and the jaw shutting, and how far above the
package the jaw stayed while it was not yet over it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MISALIGN_METERS = 0.005
"""Horizontal miss, in meters, past which the jaw is not yet over the package.

`AC-BEHAVE-07`. A measurement, in the same sense as `GRASPED_METERS`: the
report bins samples with it. The planner is not given it as a tolerance.
"""


def turn_radians(
    before: tuple[float, float, float, float],
    after: tuple[float, float, float, float],
) -> float:
    """Return the rotation from one unit quaternion to another, in radians.

    Args:
        before: `(w, x, y, z)` at the first sample.
        after: `(w, x, y, z)` at the later sample.

    Returns:
        The angle of the relative rotation, from 0 to π. The sign of a
        quaternion is the same rotation, so the dot product is taken in
        absolute value.
    """
    dot = abs(sum(left * right for left, right in zip(before, after, strict=True)))
    return 2.0 * math.acos(min(1.0, max(0.0, dot)))


@dataclass
class _Episode:
    """One visit, up to the tick the jaw is commanded shut."""

    track: int
    min_above: float | None = None
    touched: bool = False
    contact_belt: float = 0.0
    contact_x: float = 0.0
    contact_y: float = 0.0
    contact_quat: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    max_slide: float = 0.0
    max_turn: float = 0.0


class GraspPathWatch:
    """Accumulate the approach figures for each visit of a run.

    Attributes:
        slides: Horizontal displacement of the target relative to the belt,
            in meters, from the first gripper contact until the jaw is
            commanded shut. One value per close that touched its target.
        turns: The rotation of that target over the same interval, in radians.
        above: The lowest the gripper's geometry sat above the target's top
            while the pinch was more than `MISALIGN_METERS` off the target,
            in meters, one value per visit that had such a sample. Negative
            means the jaw was already inside the package's height while it
            was not yet over it.
    """

    def __init__(self) -> None:
        self.slides: list[float] = []
        self.turns: list[float] = []
        self.above: list[float] = []
        self._open: _Episode | None = None
        self._closed: set[int] = set()
        self._belt = 0.0
        self._last: float | None = None

    def observe(
        self,
        *,
        track: int | None,
        time: float,
        pinch_xy: tuple[float, float],
        lowest_z: float,
        object_xy: tuple[float, float],
        object_top_z: float,
        object_quat: tuple[float, float, float, float],
        belt_speed: float,
        contacting: bool,
        jaw_shut: bool,
    ) -> None:
        """Record one physics tick of the visit now underway.

        Args:
            track: The target, or None when the arm is not on a visit.
            time: Simulated time, in seconds.
            pinch_xy: Where the jaw closes, in the belt's horizontal plane.
            lowest_z: The lowest world height of the jaw's collision geometry.
            object_xy: The target's centre, in the same plane.
            object_top_z: The highest world height of the target's geometry.
            object_quat: The target's orientation, `(w, x, y, z)`.
            belt_speed: The speed the belt drove at on this tick, in meters
                per second. Integrated here, so a speed that changes does
                not look like the package sliding.
            contacting: Whether the jaw's geometry touches the target.
            jaw_shut: Whether the jaw is commanded shut on this tick.
        """
        if self._last is not None:
            self._belt += belt_speed * (time - self._last)
        self._last = time
        # A tick with no plan is not a new visit. Sealing here split one
        # descent into a sample per tick, and the worst height was a list
        # instead of a figure.
        if track is None:
            return
        if track in self._closed:
            self._seal(closed=False)
            return
        if self._open is None or self._open.track != track:
            self._seal(closed=False)
            self._open = _Episode(track=track)
        episode = self._open
        miss = math.hypot(pinch_xy[0] - object_xy[0], pinch_xy[1] - object_xy[1])
        if miss > MISALIGN_METERS:
            margin = lowest_z - object_top_z
            episode.min_above = (
                margin if episode.min_above is None else min(episode.min_above, margin)
            )
        if contacting and not episode.touched:
            episode.touched = True
            episode.contact_belt = self._belt
            episode.contact_x = object_xy[0]
            episode.contact_y = object_xy[1]
            episode.contact_quat = object_quat
        if episode.touched:
            slide = math.hypot(
                (object_xy[0] - self._belt)
                - (episode.contact_x - episode.contact_belt),
                object_xy[1] - episode.contact_y,
            )
            episode.max_slide = max(episode.max_slide, slide)
            episode.max_turn = max(
                episode.max_turn, turn_radians(episode.contact_quat, object_quat)
            )
        if jaw_shut:
            self._seal(closed=True)

    def finish(self) -> None:
        """Close a visit the run ended in the middle of.

        A slide is recorded only when the jaw was commanded shut. The height
        above the package is recorded either way: an approach that dipped is
        still an approach.
        """
        self._seal(closed=False)

    def _seal(self, *, closed: bool) -> None:
        episode = self._open
        self._open = None
        if episode is None:
            return
        if episode.min_above is not None:
            self.above.append(episode.min_above)
        if closed and episode.touched:
            self.slides.append(episode.max_slide)
            self.turns.append(episode.max_turn)
            self._closed.add(episode.track)
