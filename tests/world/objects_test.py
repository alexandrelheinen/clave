"""Tests for the object set and its material classes."""

from pathlib import Path

import pytest

from clave.taxonomy import BY_ID
from clave.world.config import WorldConfigError, load
from clave.world.objects import ObjectSpec, channels, material_classes, parse

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def shipped() -> tuple[ObjectSpec, ...]:
    """Parse the object set the world actually ships with."""
    return parse(load(CONFIG)["objects"])


def test_every_object_carries_a_taxonomy_material_class() -> None:
    """AC-ASSET-01: a rollout is labeled by construction."""
    assert all(spec.material_class in BY_ID for spec in shipped())


def test_the_object_set_covers_at_least_six_material_classes() -> None:
    """AC-ASSET-02."""
    assert len(material_classes(shipped())) >= 6


def test_an_unknown_material_class_is_rejected_naming_the_object() -> None:
    """AC-ASSET-04: a mislabeled object would corrupt every rollout."""
    entry = [
        {
            "name": "mystery",
            "material_class": "M-99",
            "shape": "box",
            "size_a_meters": [0.1, 0.2],
            "size_b_meters": [0.1, 0.2],
            "density_kg_per_m3": [10, 20],
        }
    ]
    with pytest.raises(WorldConfigError, match="mystery"):
        parse(entry)


def test_an_unknown_shape_is_rejected_naming_the_object() -> None:
    """Only the two primitives the scene can build are accepted."""
    entry = [
        {
            "name": "blob",
            "material_class": "M-01",
            "shape": "torus",
            "size_a_meters": [0.1, 0.2],
            "size_b_meters": [0.1, 0.2],
            "density_kg_per_m3": [10, 20],
        }
    ]
    with pytest.raises(WorldConfigError, match="blob"):
        parse(entry)


def test_channels_are_deduplicated_and_ordered() -> None:
    """Bin layout must not depend on object declaration order."""
    resolved = channels(shipped())
    assert resolved == tuple(sorted(set(resolved)))
    assert "CH-FIBER" in resolved
