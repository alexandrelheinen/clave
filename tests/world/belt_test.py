"""Tests for the conveyor drive and reachability."""

from pathlib import Path

import numpy as np
import pytest

from clave.world import arm as armmod
from clave.world import belt, config, scene
from clave.world.scene import BeltGeometry, SceneLayout

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def layout(speed: float, offset: float) -> SceneLayout:
    """A minimal layout for reachability arithmetic, needing no physics.

    The reach bounds are the arm's own and are not parameters here: they come
    from the model rather than from a number a test picks, which is what keeps
    this arithmetic describing the manipulator the world actually has.
    """
    return SceneLayout(
        belt=BeltGeometry(length=3.0, width=1.0, surface_height=0.90, speed=speed),
        arm_shoulder=(0.0, offset, 1.408),
        shoulder_drop=0.251,
        reach_min=armmod.REACH_MIN_METERS,
        reach_max=armmod.REACH_MAX_METERS,
        tool_above_belt=(0.030, 0.210),
        channels=("CH-PET",),
        objects=(),
        pool_size=0,
        timestep=0.002,
    )


def test_the_report_states_the_annulus_window_and_budget() -> None:
    """AC-REACH-01 and AC-REACH-03."""
    report = belt.reach_report(layout(speed=0.2, offset=-0.34))
    assert report.reach_min == armmod.REACH_MIN_METERS
    assert report.reach_max == armmod.REACH_MAX_METERS
    assert report.belt_offset == pytest.approx(0.34)
    assert report.window_length > 0
    assert report.time_budget == pytest.approx(report.window_length / 0.2)
    assert report.reachable


def test_a_belt_outside_reach_yields_no_window() -> None:
    """A world where the arm cannot touch the belt must say so."""
    report = belt.reach_report(layout(speed=0.2, offset=-0.9))
    assert report.window_length == 0.0
    assert not report.reachable


def test_a_faster_belt_shortens_the_budget() -> None:
    """AC-BELT-02: the budget is what every perception latency fits inside."""
    slow = belt.reach_report(layout(speed=0.1, offset=-0.34))
    fast = belt.reach_report(layout(speed=0.4, offset=-0.34))
    assert fast.time_budget < slow.time_budget


def test_objects_reach_belt_speed_and_enter_the_window() -> None:
    """AC-BELT-01 and AC-REACH-02."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    rng = np.random.default_rng(7)
    model, data, plan = scene.build(raw, rng, ROOT)
    spawn = raw["spawn"]
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(spawn["entry_margin_meters"]),
    )
    for _ in range(12000):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert conveyor.active, "nothing spawned"
    assert conveyor.entered_window(), "no object reached the arm"
    for item in conveyor.active:
        assert item.material_class.startswith("M-")
        assert item.channel.startswith("CH-")


def test_an_unpicked_object_is_not_removed() -> None:
    """AC-BELT-03: a real line does not stop for a missed pick."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    rng = np.random.default_rng(2)
    model, data, plan = scene.build(raw, rng, ROOT)
    spawn = raw["spawn"]
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(spawn["entry_margin_meters"]),
    )
    for _ in range(10000):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    before = len(conveyor.active)
    for _ in range(3000):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert len(conveyor.active) >= before
