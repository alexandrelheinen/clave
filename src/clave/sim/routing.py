"""Apply a routing policy to the markers the arm is about to serve.

The shipped simulation leaves each object on the channel its class maps
to. A debug file can select expected cost. The arm then flies the chute
that decision names, when the line has a mouth for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from clave.belief.decide import floored_class, minimizing_channel
from clave.control.story import StoryLog
from clave.runtime.loop import RoutingPolicy, RuntimeConfigError
from clave.taxonomy import REJECT_CHANNEL, channel_of
from clave.tracker.fusion import OUTCOMES
from clave.tracker.markers import GraspMarker

# Printed in the comparison so a reader can see which rule each column used.
_FLOOR_RULE = "confidence_floor"


@dataclass(frozen=True)
class Arrival:
    """One track, routed by both rules.

    Attributes:
        track_id: The identity the task layer serves.
        material: The class the posterior was built from, or the leading
            class when the weights came from the tracker.
        floor_chute: Where the confidence floor would send it.
        chosen_chute: Where expected cost would send it.
        flown_chute: The chute placed on the marker. This is `chosen_chute`
            when that mouth exists, and the marker's previous chute when
            the line has no mouth there.
        expected_cost: The expected cost of the chosen channel.
        leading_class: The class the decision still reports.
    """

    track_id: int
    material: str
    floor_chute: str
    chosen_chute: str
    flown_chute: str
    expected_cost: float
    leading_class: str


class RoutingSession:
    """Remembers each track's decision so a later tick does not invent one.

    Attributes:
        policy: The loaded routing block.
        posterior_floor: The fusion floor a ground-truth spike is built with.
        mouths: Chute names the world actually built.
    """

    def __init__(
        self,
        policy: RoutingPolicy,
        posterior_floor: float,
        mouths: Sequence[str],
    ) -> None:
        """Hold the policy and the mouths the arm can release over.

        Args:
            policy: The routing block for this run.
            posterior_floor: Smallest weight in a ground-truth posterior.
            mouths: Chute names present in the scene.
        """
        self.policy = policy
        self.posterior_floor = posterior_floor
        self.mouths = frozenset(mouths)
        self._chutes = _chutes(policy)
        self._arrivals: dict[int, Arrival] = {}

    @property
    def arrivals(self) -> tuple[Arrival, ...]:
        """The decisions so far, in track order."""
        return tuple(self._arrivals[key] for key in sorted(self._arrivals))

    def chute_for(self, track_id: int, fallback: str) -> str:
        """Return the chute a track is flying, or `fallback` before a decision.

        Args:
            track_id: The identity the task layer serves.
            fallback: The chute the world assigned from the class.

        Returns:
            The flown chute once a decision exists, otherwise `fallback`.
        """
        arrival = self._arrivals.get(track_id)
        if arrival is None:
            return fallback
        return arrival.flown_chute

    def decided(self, track_id: int) -> bool:
        """Whether this track already has a decision.

        Args:
            track_id: The identity the task layer serves.

        Returns:
            True once `apply` has routed the track.
        """
        return track_id in self._arrivals

    def apply(
        self,
        markers: tuple[GraspMarker, ...],
        beliefs: Mapping[int, tuple[str, tuple[float, ...]]],
        story: StoryLog,
        at_seconds: float,
    ) -> tuple[GraspMarker, ...]:
        """Replace each marker's chute when expected cost is the rule.

        Args:
            markers: The markers about to enter the queue.
            beliefs: Track id to `(material, posterior)`.
            story: The narrative. A repeated decision does not emit a line.
            at_seconds: Simulated time.

        Returns:
            The markers, with the flown chute written on each one that had
            a belief.
        """
        if self.policy.rule != "expected_cost" or self.policy.cost is None:
            return markers
        routed: list[GraspMarker] = []
        for marker in markers:
            belief = beliefs.get(marker.track_id)
            if belief is None:
                routed.append(marker)
                continue
            material, posterior = belief
            decision = minimizing_channel(posterior, self.policy.cost)
            chosen = self._chutes[decision.channel]
            floor = _floor_chute(
                material, decision.leading_weight, self.policy.confidence_floor
            )
            flown = chosen if chosen in self.mouths else marker.channel
            self._arrivals[marker.track_id] = Arrival(
                track_id=marker.track_id,
                material=material,
                floor_chute=floor,
                chosen_chute=chosen,
                flown_chute=flown,
                expected_cost=decision.expected_cost,
                leading_class=decision.leading_class,
            )
            story.route(
                at_seconds,
                marker.track_id,
                decision.leading_class,
                chosen,
                decision.expected_cost,
            )
            routed.append(replace(marker, channel=flown))
        return tuple(routed)

    def notes(self, seed: int) -> str:
        """Return the paired-rule comparison for this run.

        Args:
            seed: The seed the arrivals were drawn from.

        Returns:
            The note written beside the run.
        """
        rows = self.arrivals
        differed = [row for row in rows if row.floor_chute != row.chosen_chute]
        rejected = [
            row
            for row in rows
            if row.chosen_chute == REJECT_CHANNEL and row.material != "M-11"
        ]
        lines = [
            f"Seed {seed}. Rule expected_cost, compared with {_FLOOR_RULE}.",
            f"Arrivals: {len(rows)}. Channels that differ: {len(differed)}.",
            "",
        ]
        if not rows:
            lines.append(
                "No arrival was routed on this seed. The cost table was not edited."
            )
        elif differed:
            lines.append(
                "An arrival the confidence floor would sort took another chute "
                "under expected cost."
            )
        else:
            lines.append(
                "No arrival changed channel. A class posterior that keeps its "
                "spare mass on the true class still minimizes on the mapped "
                "channel. The reasoned default prices that placement at 0 and "
                "reject at 2, so the cost of a likely mistake does not outweigh "
                "the nop on this posterior. The cost table was not edited."
            )
        lines.append("")
        if rejected:
            lines.append(
                f"Expected cost rejected {len(rejected)} arrivals and kept the "
                "leading class on the decision line."
            )
        else:
            lines.append(
                "Expected cost rejected no arrival on this seed. A reject that "
                "keeps the leading class is covered by AC-SORT-08 in the "
                "routing tests."
            )
        missing = [row for row in rows if row.flown_chute != row.chosen_chute]
        if missing:
            lines.append("")
            lines.append(
                "A chosen chute had no mouth on this line, so the visit kept "
                "the chute it already had."
            )
        lines.append("")
        lines.append("track material leading floor_chute chosen_chute flown_chute cost")
        for row in rows:
            lines.append(
                f"{row.track_id} {row.material} {row.leading_class} "
                f"{row.floor_chute} {row.chosen_chute} {row.flown_chute} "
                f"{row.expected_cost:.3f}"
            )
        return "\n".join(lines)


def record_beliefs(
    records: Sequence[tuple[int, str, tuple[float, ...]]],
    floor: float,
) -> dict[int, tuple[str, tuple[float, ...]]]:
    """Pair each track with the posterior it holds, or a class spike.

    Args:
        records: `(track id, material, posterior)`. An empty posterior is
            replaced by a floored spike on the material when that material
            is an outcome.
        floor: The posterior floor used for that spike.

    Returns:
        Track id to `(material, posterior)`. A material outside the
        outcomes is omitted.
    """
    beliefs: dict[int, tuple[str, tuple[float, ...]]] = {}
    for track_id, material, posterior in records:
        weights = posterior
        if not weights:
            if material not in OUTCOMES:
                continue
            weights = floored_class(material, floor)
        beliefs[track_id] = (material, weights)
    return beliefs


def ground_truth_beliefs(
    items: Sequence[tuple[int, str]], floor: float
) -> dict[int, tuple[str, tuple[float, ...]]]:
    """Build a floored class posterior for each ground-truth object.

    Args:
        items: `(track id, material class)` pairs.
        floor: The posterior floor.

    Returns:
        Track id to the class and its posterior.
    """
    return {
        track_id: (material, floored_class(material, floor))
        for track_id, material in items
    }


def _floor_chute(material: str, confidence: float, floor: float) -> str:
    """Return the chute the confidence floor would assign."""
    if material not in OUTCOMES or material == "reject" or confidence < floor:
        return REJECT_CHANNEL
    return channel_of(material)


def _chutes(policy: RoutingPolicy) -> dict[int, str]:
    """Map a channel id to the taxonomy chute the arm can fly to."""
    names = {policy.reject_channel: REJECT_CHANNEL}
    for class_id, channel in policy.channels.items():
        chute = channel_of(class_id)
        previous = names.get(channel)
        if previous is not None and previous != chute:
            raise RuntimeConfigError(
                f"channel {channel} is both {previous} and {chute}, so the arm "
                "has two mouths for one id"
            )
        names[channel] = chute
    return names
