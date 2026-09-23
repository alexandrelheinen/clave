"""The story of one run, told as the arm decides it.

A report says what a visit came to. This says why the arm did it, at the
moment it chose, and only when the operator asked for debug. The sentence
shape and the watches are specified in
`docs/requirements/simulation-narrative.md`.

Nothing here decides. A line that reports a collision does not stop the arm,
and a missing material does not change a plan.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable

from clave.taxonomy import BY_ID

LOGGER = logging.getLogger(__name__)

OUTCOMES = frozenset({"success", "fail", "pending"})
"""The only verdicts a line may end with."""

PINCH_MISS_METERS = 0.040
"""How far from the pinch an object is treated as not in the jaw.

The jaw opens 0.085 m, so half of that is 0.0425 m. Forty millimetres is
inside the opening and well past the 8.7 mm of side clearance the narrowest
object leaves, so an object there is not between the pads.
"""

ACCELERATION_WATCH = 25.0
"""Vertical acceleration, in m/s², above which a sample is a spike.

The commanded ceiling is 2.50 m/s². The smallest slip lurch on record is
52.9 m/s². Twenty-five sits an order above the command and about half the
slip, so a planned move does not trip it and a slip does. The sample is a
second difference of flange height, not the planner's analytic acceleration.
"""

ACCELERATION_CLEAR = ACCELERATION_WATCH / 2.0
"""Below this the acceleration watch may report again.

Half the watch, so a sample that chatters on the threshold is one line.
"""

TRACKING_WATCH = 0.050
"""How far the flange may lag its command, in meters, before that is a loss.

After the lead term the settled error is 1.0 to 1.25 mm. The visits that
lost the command fell 50 to 80 mm behind it. Fifty millimetres is that
failure, not the arrival tolerance.
"""

TRACKING_CLEAR = TRACKING_WATCH / 2.0
"""Below this the lag watch may report again."""


def material_phrase(class_id: str) -> str:
    """Return a material the way a person reads it.

    Args:
        class_id: A taxonomy identifier, or empty when nothing was noted.

    Returns:
        The taxonomy name and its id, the raw identifier when the class is
        unknown, or `unknown material` when there is none.
    """
    if not class_id:
        return "unknown material"
    entry = BY_ID.get(class_id)
    if entry is None:
        return class_id
    return f"{entry.name}, {entry.id}"


class StoryLog:
    """Emits the narrative, and remembers which object is which.

    The task machine knows a track and a channel. The material is noted by
    the caller, because a track id minted by the tracker and a spawn serial
    are both small integers and must not share one map.
    """

    def __init__(self, sink: Callable[[str], None] | None = None) -> None:
        """Hold an optional sink.

        Args:
            sink: Receives each line directly. Tests pass one. A production
                log leaves it empty and emits through the debug logger, which
                drops the line unless DEBUG is enabled.
        """
        self._sink = sink
        self._materials: dict[int, str] = {}
        self._channels: dict[int, str] = {}
        self._grasp_misses: set[int] = set()

    def note(self, track_id: int, material: str, channel: str) -> None:
        """Remember what a track is, without letting an empty note erase one.

        Args:
            track_id: The identity the task layer serves.
            material: Taxonomy identifier, or empty to leave the previous one.
            channel: The chute, or empty to leave the previous one.
        """
        if material:
            self._materials[track_id] = material
        if channel:
            self._channels[track_id] = channel

    def material_of(self, track_id: int | None) -> str:
        """Return the noted material class, or empty when none was noted."""
        if track_id is None:
            return ""
        return self._materials.get(track_id, "")

    def channel_of(self, track_id: int | None) -> str:
        """Return the noted chute, or empty when none was noted."""
        if track_id is None:
            return ""
        return self._channels.get(track_id, "")

    def refer(self, track_id: int | None) -> str:
        """Return the object the way the sentence names it."""
        if track_id is None:
            return "no object"
        phrase = material_phrase(self.material_of(track_id))
        return f"object {track_id} ({phrase})"

    def missed_the_grasp(self, track_id: int | None) -> bool:
        """Whether the close on this track was already counted as a miss."""
        return track_id is not None and track_id in self._grasp_misses

    def tell(
        self,
        at_seconds: float,
        because: str,
        action: str,
        outcome: str,
        channel: str = "",
    ) -> None:
        """Emit one sentence, or nothing when debug is off.

        Args:
            at_seconds: Simulated time.
            because: The cause, without a leading "because".
            action: What the arm will do, without a leading "I will".
            outcome: `success`, `fail`, or `pending`.
            channel: The chute, omitted from the line when empty.

        Raises:
            ValueError: If the outcome is not one of the three tokens.
        """
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome {outcome!r} is not success, fail, or pending")
        chute = f", chute {channel}" if channel else ""
        text = (
            f"t={at_seconds:8.3f}s because {because}, I will {action}{chute}: {outcome}"
        )
        self._emit(text)

    def queue(
        self,
        at_seconds: float,
        reasons: frozenset[str],
        head_id: int | None,
        previous_head: int | None,
        previous_still_waiting: bool,
    ) -> None:
        """Narrate a rebuild of the queue.

        Args:
            at_seconds: Simulated time.
            reasons: Which triggers fired, among `appeared`, `retired`, `anchor`.
            head_id: The head after the rebuild, or None.
            previous_head: The head before it, or None.
            previous_still_waiting: Whether the previous head is still a candidate.
        """
        why = ", ".join(sorted(reasons)) if reasons else "the order was rebuilt"
        if head_id is None:
            self.tell(
                at_seconds,
                f"the queue was rebuilt ({why}) and it has no head",
                "not start a visit",
                "pending",
            )
            return
        head = self.refer(head_id)
        channel = self.channel_of(head_id)
        if (
            previous_head is not None
            and head_id != previous_head
            and previous_still_waiting
        ):
            self.tell(
                at_seconds,
                f"the queue was rebuilt ({why}) while {self.refer(previous_head)} "
                "was still waiting",
                f"leave it and serve {head} instead",
                "pending",
                channel=channel,
            )
            return
        if head_id != previous_head:
            self.tell(
                at_seconds,
                f"the queue was rebuilt ({why})",
                f"serve {head} next",
                "pending",
                channel=channel,
            )
            return
        self.tell(
            at_seconds,
            f"the queue was rebuilt ({why}) and the head did not change",
            f"keep serving {head}",
            "pending",
            channel=channel,
        )

    def grasp_reading(
        self, at_seconds: float, track_id: int | None, gap: float
    ) -> None:
        """Narrate the instant the jaw reached the object.

        Args:
            at_seconds: Simulated time.
            track_id: The visit this close belongs to.
            gap: Distance from the pinch to the nearest object, in meters, or
                infinity when nothing was in reach.
        """
        who = self.refer(track_id)
        channel = self.channel_of(track_id)
        missed = math.isinf(gap) or gap > PINCH_MISS_METERS
        if missed and track_id is not None:
            self._grasp_misses.add(track_id)
        if missed:
            if math.isinf(gap):
                because = "nothing is in reach of the pinch"
            else:
                because = (
                    f"the nearest object is {gap * 1000:.0f} mm from the pinch, "
                    f"past the {PINCH_MISS_METERS * 1000:.0f} mm watch"
                )
            self.tell(
                at_seconds,
                because,
                f"count the close on {who} as a miss",
                "fail",
                channel=channel,
            )
            return
        self.tell(
            at_seconds,
            f"the nearest object is {gap * 1000:.0f} mm from the pinch",
            f"close the jaw on {who}",
            "pending",
            channel=channel,
        )

    def visit_ended(
        self, at_seconds: float, track_id: int | None, lift: float, *, held: bool
    ) -> None:
        """Narrate the lift that decides whether the jaw kept the object.

        Args:
            at_seconds: Simulated time.
            track_id: The visit that ended.
            lift: How far the nearest object rose, in meters.
            held: Whether that lift reaches the report's grasp threshold.
        """
        self.tell(
            at_seconds,
            f"the visit ended and the nearest object rose {lift * 1000:.0f} mm",
            f"count the grasp of {self.refer(track_id)}",
            "success" if held else "fail",
            channel=self.channel_of(track_id),
        )

    def placed(
        self,
        at_seconds: float,
        body: str,
        material: str,
        channel: str,
        belongs: str | None,
        serial: int | None = None,
    ) -> None:
        """Narrate an object crossing a chute mouth.

        Args:
            at_seconds: Simulated time.
            body: The body name in the model.
            material: The taxonomy identifier recorded at spawn.
            channel: The chute the body crossed.
            belongs: The chute the material routes to, or None when unknown.
            serial: The spawn serial, when the feed keys tracks on it.
        """
        label = material_phrase(material)
        if serial is None:
            subject = f"body {body} ({label})"
        else:
            subject = f"body {body}, object {serial} ({label})"
        if belongs is not None and belongs != channel:
            self.tell(
                at_seconds,
                f"{subject} crossed chute {channel}, which is not {belongs}",
                "count a misroute",
                "fail",
                channel=channel,
            )
            return
        self.tell(
            at_seconds,
            f"{subject} crossed the mouth",
            f"count a place in chute {channel}",
            "success",
            channel=channel,
        )

    def _emit(self, text: str) -> None:
        """Send one line to the sink, or to the debug logger."""
        if self._sink is not None:
            self._sink(text)
            return
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug("%s", text)


class AnomalyWatch:
    """Reports collisions, acceleration spikes, and a loss of control.

    Each condition is edge-triggered. A contact that lasts a hundred ticks
    is one line, and it is reported again only after it has let go. The
    watch does not command the arm.
    """

    def __init__(self, story: StoryLog) -> None:
        """Watch through one story, so the anomaly sits in the same narrative.

        Args:
            story: The log the lines are emitted on.
        """
        self._story = story
        self._contact = False
        self._accelerating = False
        self._lagging = False
        self._refusal: str | None = None

    def observe(
        self,
        at_seconds: float,
        *,
        contact: bool,
        clearance: float,
        vertical_acceleration: float,
        tracking_error: float | None,
        refusal: str | None,
        track_id: int | None,
    ) -> None:
        """Update the watches from one physics tick.

        Args:
            at_seconds: Simulated time.
            contact: Whether a jaw collision geom is touching the belt.
            clearance: Jaw clearance above the belt, in meters. Negative means
                the geometry is inside the belt.
            vertical_acceleration: Sampled vertical acceleration of the flange,
                in m/s². Zero on the first tick, before a previous rise exists.
            tracking_error: How far the flange is from the pose it was
                commanded, in meters, or None when this tick commanded nothing.
            refusal: Why the servo refused the pose, or None when it accepted.
            track_id: The visit under way, or None when the arm is idle.
        """
        who = self._story.refer(track_id)
        channel = self._story.channel_of(track_id)
        if contact and not self._contact:
            self._story.tell(
                at_seconds,
                "the jaw's collision geometry touched the belt "
                f"(clearance {clearance * 1000:.1f} mm)",
                f"report a collision while fetching {who}",
                "fail",
                channel=channel,
            )
        self._contact = contact

        spiked = vertical_acceleration > ACCELERATION_WATCH
        if spiked and not self._accelerating:
            self._story.tell(
                at_seconds,
                "the flange's vertical acceleration reached "
                f"{vertical_acceleration:.1f} m/s^2, above the "
                f"{ACCELERATION_WATCH:.1f} m/s^2 watch",
                f"report an acceleration spike while fetching {who}",
                "fail",
                channel=channel,
            )
            self._accelerating = True
        elif (not spiked) and vertical_acceleration < ACCELERATION_CLEAR:
            self._accelerating = False

        lagging = tracking_error is not None and tracking_error > TRACKING_WATCH
        if lagging and not self._lagging:
            assert tracking_error is not None
            self._story.tell(
                at_seconds,
                f"the flange is {tracking_error * 1000:.0f} mm from the pose "
                f"it was commanded, above the {TRACKING_WATCH * 1000:.0f} mm watch",
                f"report a loss of control while fetching {who}",
                "fail",
                channel=channel,
            )
            self._lagging = True
        elif tracking_error is None or tracking_error < TRACKING_CLEAR:
            self._lagging = False

        if refusal != self._refusal:
            self._refusal = refusal
            if refusal is not None:
                self._story.tell(
                    at_seconds,
                    f"the servo refused the pose ({refusal})",
                    f"report a loss of control while fetching {who}",
                    "fail",
                    channel=channel,
                )
