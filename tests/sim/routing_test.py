"""Expected cost in the simulator, beside the confidence floor.

The shipped runtime file stays on the floor. A debug file names the
reasoned default. These tests do not edit that table.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from clave.belief.decide import floored_class
from clave.cli import _build_parser
from clave.control.story import StoryLog
from clave.runtime.loop import RoutingPolicy, RuntimeConfigError, load_routing_policy
from clave.sim.routing import RoutingSession, record_beliefs
from clave.taxonomy import MATERIAL_CLASSES, channel_of
from clave.tracker.fusion import OUTCOMES
from clave.tracker.markers import GraspMarker

ROOT = Path(__file__).resolve().parents[2]
DEBUG = ROOT / "configs" / "debug" / "expected-cost.yml"
SHIPPED = ROOT / "configs" / "runtime" / "sitl.yml"
MOUTHS = ("CH-HDPE", "CH-FIBER", "CH-FERROUS", "CH-PLASTIC-OTHER")


def _floor() -> float:
    """The fusion floor a class spike is built with."""
    raw = yaml.safe_load(
        (ROOT / "configs" / "perception" / "fusion.yml").read_text(encoding="utf-8")
    )
    return float(raw["posterior"]["floor"])


def _marker(track_id: int, channel: str) -> GraspMarker:
    """A marker whose only interesting field is the chute."""
    zeros = np.zeros(3, dtype=np.float64)
    return GraspMarker(
        track_id,
        0,
        pinch_position_belt=zeros,
        flange_position_world=zeros,
        channel=channel,
    )


def _posterior(weights: dict[str, float]) -> tuple[float, ...]:
    """A posterior with the named outcomes set and the rest at zero."""
    values = [0.0] * len(OUTCOMES)
    for name, weight in weights.items():
        values[OUTCOMES.index(name)] = weight
    return tuple(values)


def _session(mouths: tuple[str, ...] = MOUTHS) -> RoutingSession:
    """A session on the debug file."""
    return RoutingSession(load_routing_policy(DEBUG), _floor(), mouths)


def test_the_shipped_runtime_stays_on_the_confidence_floor() -> None:
    """The debug file opts in. The shipped file does not, and the maps match."""
    shipped = load_routing_policy(SHIPPED)
    debug = load_routing_policy(DEBUG)
    assert shipped.rule == "confidence_floor"
    assert shipped.cost is None
    assert debug.rule == "expected_cost"
    assert debug.cost is not None
    assert debug.channels == shipped.channels
    assert debug.reject_channel == shipped.reject_channel
    assert debug.confidence_floor == shipped.confidence_floor


def test_sim_routing_defaults_to_absent() -> None:
    """Without --routing the simulation does not load a cost table."""
    parser = _build_parser()
    assert parser.parse_args(["sim"]).routing is None
    chosen = parser.parse_args(["sim", "--routing", "configs/debug/expected-cost.yml"])
    assert chosen.routing == Path("configs/debug/expected-cost.yml")


def test_a_class_spike_keeps_the_mapped_chute_and_says_so() -> None:
    """The reasoned default does not divert a posterior that is nearly one class."""
    session = _session(mouths=tuple(channel_of(entry.id) for entry in MATERIAL_CLASSES))
    story, kept = _lines()
    floor = _floor()
    markers = []
    beliefs = {}
    for index, entry in enumerate(MATERIAL_CLASSES, start=1):
        markers.append(_marker(index, entry.channel))
        beliefs[index] = (entry.id, floored_class(entry.id, floor))
    routed = session.apply(tuple(markers), beliefs, story, 1.25)
    for marker, entry in zip(routed, MATERIAL_CLASSES, strict=True):
        assert marker.channel == entry.channel
    notes = session.notes(0)
    assert "Channels that differ: 0" in notes
    assert "was not edited" in notes
    assert "AC-SORT-08" in notes
    assert len(kept) == len(MATERIAL_CLASSES)
    session.apply(tuple(routed), beliefs, story, 1.75)
    assert len(kept) == len(MATERIAL_CLASSES)


def test_a_mixed_fiber_belief_differs_from_the_floor() -> None:
    """The floor would sort cardboard. Expected cost sends it to ferrous."""
    session = _session()
    story, kept = _lines()
    posterior = _posterior({"M-08": 0.6, "M-06": 0.4})
    routed = session.apply(
        (_marker(7, "CH-FIBER"),),
        {7: ("M-08", posterior)},
        story,
        1.25,
    )
    assert routed[0].channel == "CH-FERROUS"
    arrival = session.arrivals[0]
    assert arrival.floor_chute == "CH-FIBER"
    assert arrival.chosen_chute == "CH-FERROUS"
    assert arrival.flown_chute == "CH-FERROUS"
    assert arrival.expected_cost == pytest.approx(1.8)
    assert "minimizes expected cost" in kept[0]
    assert "CH-FERROUS" in kept[0]
    notes = session.notes(3)
    assert "Channels that differ: 1" in notes
    assert "took another chute" in notes
    assert session.chute_for(7, "CH-FIBER") == "CH-FERROUS"
    assert session.decided(7)
    assert session.chute_for(8, "CH-FIBER") == "CH-FIBER"


def test_a_missing_mouth_keeps_the_chute_the_marker_already_had() -> None:
    """The arm does not fly a chute the line did not build."""
    session = _session()
    story, _kept = _lines()
    posterior = _posterior({"M-05": 0.9, "M-06": 0.1})
    routed = session.apply(
        (_marker(4, "CH-HDPE"),),
        {4: ("M-02", posterior)},
        story,
        0.5,
    )
    assert routed[0].channel == "CH-HDPE"
    arrival = session.arrivals[0]
    assert arrival.chosen_chute == "CH-ALU"
    assert arrival.flown_chute == "CH-HDPE"
    assert "no mouth" in session.notes(1)


def test_the_confidence_floor_does_not_reroute() -> None:
    """A floor policy leaves the marker and emits no decision line."""
    policy = load_routing_policy(SHIPPED)
    session = RoutingSession(policy, _floor(), MOUTHS)
    story, kept = _lines()
    marker = _marker(1, "CH-HDPE")
    routed = session.apply(
        (marker,),
        {1: ("M-02", floored_class("M-02", _floor()))},
        story,
        0.0,
    )
    assert routed == (marker,)
    assert kept == []
    assert session.arrivals == ()
    assert "was not edited" in session.notes(0)


def test_two_taxonomy_chutes_cannot_share_one_channel_id() -> None:
    """One channel id is one mouth."""
    width = len(OUTCOMES)
    policy = RoutingPolicy(
        channels={"M-01": 1, "M-02": 1, "M-11": 0},
        reject_channel=0,
        confidence_floor=0.6,
        rule="expected_cost",
        cost=((0, (0.0,) * width), (1, (0.0,) * width)),
    )
    with pytest.raises(RuntimeConfigError, match="channel 1"):
        RoutingSession(policy, _floor(), MOUTHS)


def test_an_empty_posterior_becomes_a_class_spike() -> None:
    """A record without weights still has a belief when the class is known."""
    floor = _floor()
    beliefs = record_beliefs([(3, "M-02", ()), (4, "not-a-class", ())], floor)
    assert beliefs[3][0] == "M-02"
    assert beliefs[3][1] == floored_class("M-02", floor)
    assert 4 not in beliefs
    kept = record_beliefs([(3, "M-02", floored_class("M-06", floor))], floor)
    assert kept[3][1] == floored_class("M-06", floor)


def test_a_debug_run_writes_the_comparison(tmp_path: Path) -> None:
    """A short ground-truth run under the debug file records both rules."""
    from clave.sim.debug_run import run

    report = run(
        root=ROOT,
        out=tmp_path,
        seconds=0.6,
        seed=0,
        window=False,
        video=False,
        frames=False,
        ground_truth_tracker=True,
        progress=False,
        routing_path=DEBUG,
    )
    assert report.output == tmp_path
    text = (tmp_path / "routing-comparison.txt").read_text(encoding="utf-8")
    assert "was not edited" in text
    metadata = yaml.safe_load((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["parameters"]["routing"] == str(DEBUG)


def _lines() -> tuple[StoryLog, list[str]]:
    """A log that keeps every sentence."""
    kept: list[str] = []
    return StoryLog(sink=kept.append), kept
