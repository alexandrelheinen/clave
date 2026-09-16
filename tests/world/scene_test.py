"""Tests for scene assembly and the belt.

These need MuJoCo and the pinned menagerie submodule, and skip when either is
absent, matching how the candidate tests treat their optional libraries.
"""

import subprocess
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


def test_the_belt_is_drawn_as_the_modules_the_configuration_names() -> None:
    """The module count and the belt length have to describe one belt."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    model, _, plan = scene.build(raw, np.random.default_rng(0), ROOT)
    names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g)
        for g in range(model.ngeom)
    ]
    drawn = [n for n in names if n and n.startswith("conveyor_module_")]
    expected = int(config.require(config.require(raw, "belt"), "modules", "belt"))
    if not (ROOT / scene.CONVEYOR_MODULE).is_file():
        assert not drawn
        return
    assert len(drawn) == expected
    # The modules are what a viewer sees; the box underneath keeps the physics.
    belt = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "belt")
    assert model.geom_rgba[belt][3] == 0.0
    assert model.geom_contype[belt] != 0
    for name in drawn:
        g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        assert model.geom_contype[g] == 0, "a module must not collide"


def test_a_module_count_of_zero_is_refused() -> None:
    """Zero modules describes no belt."""
    pytest.importorskip("mujoco")
    import copy

    raw = copy.deepcopy(config.load(CONFIG))
    raw["belt"]["modules"] = 0
    with pytest.raises(config.WorldConfigError, match="positive"):
        scene.build(raw, np.random.default_rng(0), ROOT)


def test_the_arm_keeps_its_gantry_whatever_draws_the_belt() -> None:
    """The modules replace the belt's legs, not the arm's support."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    model, _, _ = scene.build(raw, np.random.default_rng(0), ROOT)
    for part in (
        "arm_gantry_upright_left",
        "arm_gantry_upright_right",
        "arm_gantry_beam",
    ):
        assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, part) >= 0


def test_the_gantry_stands_clear_of_the_arm_sweep() -> None:
    """A portal that blocks the manipulator it carries is worse than none.

    The uprights were first placed at the belt edge, which put them inside the
    0.650 m annulus; the arm drove into them and stalled short of every target
    beyond, which reads exactly like a reach failure and is not one.
    """
    pytest.importorskip("mujoco")
    import mujoco

    from clave.world import arm as armmod

    raw = config.load(CONFIG)
    model, _, plan = scene.build(raw, np.random.default_rng(0), ROOT)
    for side in ("left", "right"):
        geom = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_GEOM, f"arm_gantry_upright_{side}"
        )
        position = model.geom_pos[geom]
        distance = float(
            np.hypot(
                position[0] - plan.arm_shoulder[0], position[1] - plan.arm_shoulder[1]
            )
        )
        assert distance > armmod.REACH_MAX_METERS


def test_the_arm_model_is_committed_rather_than_ignored() -> None:
    """A clone has to carry the arm, and CI proved that is not automatic.

    The model first landed under `assets/`, which `.gitignore` excludes because
    everything else there is generated by `scripts/import_scene_assets.py`. It
    ran locally and every test touching the world failed on a fresh checkout.
    This asserts the file git actually tracks, not the file on this disk.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(scene.ARM_MODEL)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, (
        f"{scene.ARM_MODEL} is not tracked by git, so a clone cannot build the "
        f"world: {tracked.stderr.strip()}"
    )
