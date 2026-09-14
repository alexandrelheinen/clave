"""Tests for scene assembly and the belt.

These need MuJoCo and the pinned menagerie submodule, and skip when either is
absent, matching how the candidate tests treat their optional libraries.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from clave.world import belt, config, scene
from clave.world.scene import SceneLayout

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def built(
    seed: int,
) -> tuple[dict[str, Any], np.random.Generator, Any, Any, SceneLayout]:
    """Build the shipped world at one seed."""
    raw = config.load(CONFIG)
    rng = np.random.default_rng(seed)
    model, data, plan = scene.build(raw, rng, ROOT)
    return raw, rng, model, data, plan


def conveyor_for(
    raw: dict[str, Any], rng: np.random.Generator, plan: SceneLayout
) -> belt.Conveyor:
    """Build a conveyor from configuration."""
    spawn = raw["spawn"]
    assert isinstance(spawn, dict)
    return belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(spawn["entry_margin_meters"]),
    )


def test_the_scene_builds_with_one_bin_per_channel() -> None:
    """AC-SCENE-01 and AC-SCENE-02."""
    pytest.importorskip("mujoco")
    import mujoco

    _, _, model, _, plan = built(0)
    for channel in plan.channels:
        assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"bin_{channel}") >= 0
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "belt") >= 0
    # The manipulator arrived from the submodule under its attachment prefix.
    assert any("arm_" in (model.joint(i).name or "") for i in range(model.njnt))


def test_the_scene_exposes_its_timestep() -> None:
    """AC-SCENE-04."""
    pytest.importorskip("mujoco")
    _, _, model, _, plan = built(0)
    assert plan.timestep > 0
    assert model.opt.timestep == pytest.approx(plan.timestep)


def test_the_scene_steps_without_instability() -> None:
    """AC-SCENE-03: parked pool bodies used to fall forever into a NaN."""
    pytest.importorskip("mujoco")
    import mujoco

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    for _ in range(4000):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert np.all(np.isfinite(data.qpos))
    assert np.all(np.isfinite(data.qvel))


def test_one_seed_twice_places_objects_identically() -> None:
    """AC-CONFIG-04."""
    pytest.importorskip("mujoco")
    _, _, _, _, first = built(5)
    _, _, _, _, second = built(5)
    assert first.belt.speed == second.belt.speed


def test_two_seeds_place_objects_differently() -> None:
    """AC-CONFIG-05: the guard above would pass for a constant."""
    pytest.importorskip("mujoco")
    _, _, _, _, first = built(5)
    _, _, _, _, second = built(6)
    assert first.belt.speed != second.belt.speed
