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


def test_an_object_wider_than_the_gripper_is_refused() -> None:
    """A world that spawns what it cannot grasp measures an impossible task.

    Guards the defect v1.0.1 fixed: every object in the shipped set was wider
    than the gripper's 55.7 mm opening, and nothing said so.
    """
    from clave.world.config import WorldConfigError
    from clave.world.objects import parse

    entry = {
        "name": "boulder",
        "material_class": "M-01",
        "shape": "cylinder",
        "size_a_meters": [0.030, 0.038],
        "size_b_meters": [0.090, 0.120],
        "density_kg_per_m3": [55, 110],
    }
    with pytest.raises(WorldConfigError, match="boulder"):
        parse([entry], 0.045)
    # The same object is accepted when the gripper is wide enough for it.
    assert parse([entry], 0.080)[0].max_grasp_width == pytest.approx(0.076)


def test_every_shipped_object_fits_the_shipped_gripper() -> None:
    """The committed world builds, which means every object clears the bound."""
    from clave.world.objects import parse

    raw = load(CONFIG)
    limit = float(require(require(raw, "arm"), "max_grasp_width_meters"))
    specs = parse(require(raw, "objects"), limit)
    assert specs
    assert all(spec.max_grasp_width <= limit for spec in specs)
