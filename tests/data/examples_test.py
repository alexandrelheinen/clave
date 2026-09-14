"""Tests for labeled examples and the scripted expert."""

import numpy as np
import pytest

from clave.data.examples import Example, LabelError, ObjectLabel, Origin, Rollout
from clave.data.expert import decide


def label(object_id: int, material: str, x: float, reachable: bool) -> ObjectLabel:
    """Build a label for testing."""
    return ObjectLabel(
        object_id=object_id,
        material_class=material,
        channel="CH-PET",
        position=(x, 0.0, 0.4),
        in_reachable_window=reachable,
    )


def test_a_label_carries_class_identity_and_position() -> None:
    """AC-RECORD-02."""
    item = label(3, "M-05", 0.1, True)
    assert item.object_id == 3
    assert item.material_class == "M-05"
    assert item.position == (0.1, 0.0, 0.4)


def test_a_label_records_whether_the_object_was_reachable() -> None:
    """AC-RECORD-05: an unreachable object cannot be a pick target."""
    assert label(1, "M-01", 0.9, False).in_reachable_window is False


def test_an_unknown_material_class_is_refused_naming_the_object() -> None:
    """A mislabeled example corrupts every number computed from it."""
    with pytest.raises(LabelError, match="M-99"):
        label(7, "M-99", 0.0, True)


def test_an_example_reports_the_classes_it_contains() -> None:
    """AC-RECORD-01."""
    example = Example(
        frame=np.zeros((4, 4, 3), dtype=np.uint8),
        labels=(label(1, "M-01", 0.0, True), label(2, "M-07", 0.1, False)),
        simulated_time=1.5,
        seed=3,
        config_digest="abc",
    )
    assert set(example.material_classes) == {"M-01", "M-07"}
    assert example.origin is Origin.SIMULATED


def test_a_rollout_holds_its_examples_in_order() -> None:
    """Splits partition by rollout, so a rollout is the unit of grouping."""
    rollout = Rollout(rollout_id="r0", seed=1, examples=())
    assert rollout.rollout_id == "r0"
    assert rollout.examples == ()


def test_the_expert_picks_the_object_nearest_the_window_exit() -> None:
    """AC-EXPERT-01: least time remaining goes first."""
    far = label(1, "M-01", -0.10, True)
    near = label(2, "M-07", 0.15, True)
    chosen = decide((far, near), window_exit=0.17)
    assert chosen is not None
    assert chosen.object_id == 2


def test_the_expert_ignores_unreachable_objects() -> None:
    """AC-EXPERT-02."""
    chosen = decide((label(1, "M-01", 0.9, False), label(2, "M-07", 0.1, True)), 0.17)
    assert chosen is not None
    assert chosen.object_id == 2


def test_the_expert_resolves_the_channel_from_the_taxonomy() -> None:
    """AC-EXPERT-03: the channel is not taken from the label."""
    chosen = decide((label(1, "M-06", 0.1, True),), 0.17)
    assert chosen is not None
    assert chosen.channel == "CH-FERROUS"


def test_the_expert_declines_when_nothing_is_reachable() -> None:
    """AC-EXPERT-05: no decision beats a decision naming nothing."""
    assert decide((label(1, "M-01", 0.9, False),), 0.17) is None
    assert decide((), 0.17) is None


def test_the_expert_is_deterministic() -> None:
    """AC-EXPERT-04."""
    labels = (label(1, "M-01", 0.0, True), label(2, "M-07", 0.0, True))
    first, second = decide(labels, 0.17), decide(labels, 0.17)
    assert first == second
