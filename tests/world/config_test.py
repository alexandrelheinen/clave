"""Tests for world configuration loading."""

from pathlib import Path

import pytest

from clave.world.config import WorldConfigError, load, require, require_range

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def test_the_shipped_configuration_loads() -> None:
    """AC-CONFIG-01: the world reads its tunables from a file."""
    raw = load(CONFIG)
    assert "belt" in raw
    assert "objects" in raw


def test_a_missing_key_fails_naming_its_location() -> None:
    """AC-CONFIG-02: nothing is substituted for an absent key."""
    with pytest.raises(WorldConfigError, match="belt.speed_meters_per_second"):
        require({}, "speed_meters_per_second", "belt")


def test_an_inverted_range_fails_naming_the_key() -> None:
    """AC-CONFIG-03: a range whose bounds are the wrong way round is a defect."""
    with pytest.raises(WorldConfigError, match="inverted"):
        require_range({"speed": [0.4, 0.1]}, "speed", "belt")


def test_a_scalar_where_a_range_belongs_is_rejected() -> None:
    """AC-CONFIG-03: a randomizable quantity must be a range."""
    with pytest.raises(WorldConfigError, match="two-element range"):
        require_range({"speed": 0.2}, "speed", "belt")


def test_every_randomizable_belt_and_spawn_value_is_a_range() -> None:
    """AC-CONFIG-03 against the shipped configuration, not a fixture."""
    raw = load(CONFIG)
    require_range(raw["belt"], "speed_meters_per_second", "belt")
    require_range(raw["spawn"], "interval_seconds", "spawn")
    require_range(raw["spawn"], "lateral_offset_meters", "spawn")
    require_range(raw["camera"], "fovy_degrees", "camera")
