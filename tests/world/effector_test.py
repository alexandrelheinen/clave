"""The effector the pick geometry assumes."""

from __future__ import annotations

from pathlib import Path

import pytest

from clave.errors import ClaveError
from clave.world.config import load
from clave.world.effector import Effector

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def test_the_shipped_configuration_describes_an_effector() -> None:
    """The shipped configuration describes an effector."""
    effector = Effector.load(load(CONFIG))
    assert effector.finger_length > 0.0
    assert effector.pad_thickness > 0.0
    assert effector.pad_depth > 0.0
    assert effector.grasp_height > 0.0


def test_the_opening_comes_from_the_arm_rather_than_a_second_number() -> None:
    """The opening comes from the arm rather than a second number.

    `arm.max_grasp_width_meters` already bounds the object set. Repeating it
    here would let the two drift and let a world spawn objects its own marker
    calls unreachable.
    """
    raw = load(CONFIG)
    assert Effector.load(raw).opening == pytest.approx(
        float(raw["arm"]["max_grasp_width_meters"])
    )


def test_an_absent_key_fails_at_load_naming_itself() -> None:
    """An absent key fails at load naming itself."""
    raw = load(CONFIG)
    del raw["effector"]["finger_length_meters"]
    with pytest.raises(ClaveError, match="finger_length_meters"):
        Effector.load(raw)


def test_an_absent_block_fails_at_load_naming_itself() -> None:
    """An absent block fails at load naming itself."""
    raw = load(CONFIG)
    del raw["effector"]
    with pytest.raises(ClaveError, match="effector"):
        Effector.load(raw)


def test_a_pad_no_thicker_than_nothing_is_refused() -> None:
    """A pad no thicker than nothing is refused."""
    raw = load(CONFIG)
    raw["effector"]["pad_thickness_meters"] = 0.0
    with pytest.raises(ClaveError, match="pad_thickness_meters"):
        Effector.load(raw)


def test_the_grasp_height_stays_above_the_belt() -> None:
    """The grasp height stays above the belt.

    A pad plane at or below the surface describes a jaw closing through the
    belt, which is a configuration error rather than a tight grasp.
    """
    raw = load(CONFIG)
    raw["effector"]["grasp_height_meters"] = -0.01
    with pytest.raises(ClaveError, match="grasp_height_meters"):
        Effector.load(raw)
