"""Tests for the conveyor drive and reachability."""

from pathlib import Path
from typing import Any

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
        arm_base=(0.0, offset, 0.90),
        reach_min=armmod.REACH_MIN_METERS,
        reach_max=armmod.REACH_MAX_METERS,
        tool_above_base=(-0.05, 0.45),
        pedestal=(0.30, 0.30),
        channels=("CH-PET",),
        objects=(),
        pool_size=0,
        timestep=0.002,
    )


def test_the_report_states_the_annulus_window_and_budget() -> None:
    """The report states the annulus window and budget."""
    report = belt.reach_report(layout(speed=0.2, offset=-0.34))
    assert report.reach_min == armmod.REACH_MIN_METERS
    assert report.reach_max == armmod.REACH_MAX_METERS
    assert report.belt_offset == pytest.approx(0.34)
    assert report.window_length > 0
    assert report.time_budget == pytest.approx(report.window_length / 0.2)
    assert report.reachable


def test_a_belt_outside_reach_yields_no_window() -> None:
    """A world where the arm cannot touch the belt must say so.

    The offset has to clear the outer radius now. A UR10e reaches 1.25 m, so
    the 0.9 m that stranded the previous arm leaves this one comfortably on
    the belt.
    """
    report = belt.reach_report(
        layout(speed=0.2, offset=-(armmod.REACH_MAX_METERS + 0.5))
    )
    assert report.window_length == 0.0
    assert not report.reachable


def test_a_faster_belt_shortens_the_budget() -> None:
    """The budget is what every perception latency fits inside."""
    slow = belt.reach_report(layout(speed=0.1, offset=-0.34))
    fast = belt.reach_report(layout(speed=0.4, offset=-0.34))
    assert fast.time_budget < slow.time_budget


def built(
    seed: int,
) -> tuple[dict[str, Any], np.random.Generator, Any, Any, SceneLayout]:
    """Build the shipped world at one seed, with a conveyor ready to drive.

    Args:
        seed: The seed.

    Returns:
        The configuration, the generator, the model, its state and the plan.
    """
    raw = config.load(CONFIG)
    rng = np.random.default_rng(seed)
    model, data, plan = scene.build(raw, rng, ROOT)
    return raw, rng, model, data, plan


def conveyor_for(
    raw: dict[str, Any], rng: np.random.Generator, plan: SceneLayout
) -> belt.Conveyor:
    """A conveyor built from the shipped spawn configuration.

    Args:
        raw: The configuration.
        rng: The generator.
        plan: The resolved layout.

    Returns:
        The conveyor.
    """
    spawn = raw["spawn"]
    return belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "spacing_meters", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(spawn["entry_margin_meters"]),
    )


def test_objects_reach_belt_speed_and_enter_the_window() -> None:
    """Objects reach belt speed and enter the window."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    rng = np.random.default_rng(7)
    model, data, plan = scene.build(raw, rng, ROOT)
    spawn = raw["spawn"]
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "spacing_meters", "spawn"),
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


def test_a_lifted_object_is_not_driven_by_the_belt() -> None:
    """A grasped object keeps its motion after it leaves the belt."""
    plan = layout(speed=0.3, offset=-0.34)
    assert belt._on_belt((0.0, 0.0, 0.90), plan)
    assert not belt._on_belt((0.0, 0.0, 0.951), plan)


def test_an_unpicked_object_is_not_removed() -> None:
    """A real line does not stop for a missed pick."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    rng = np.random.default_rng(2)
    model, data, plan = scene.build(raw, rng, ROOT)
    spawn = raw["spawn"]
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "spacing_meters", "spawn"),
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


def test_the_window_covers_both_halves_of_the_belt() -> None:
    """The belt is centered on the origin, so the sweep must be.

    A sweep that starts at the origin sees only the downstream half, which the
    expert then halves again to obtain the edge an object leaves reach at. The
    two ends are found here by asking the same test the safety layer asks,
    rather than by a radius this test computes for itself.
    """
    plan = layout(speed=0.2, offset=-0.70)
    step = 0.002
    reachable = [
        x * step
        for x in range(
            int(-plan.belt.length / 2.0 / step), int(plan.belt.length / 2.0 / step) + 1
        )
        if armmod.reaches((plan.arm_base[0], plan.arm_base[1]), x * step, 0.0)
    ]
    assert min(reachable) < 0.0, "nothing upstream of the arm is reachable"
    span = max(reachable) - min(reachable)
    report = belt.reach_report(plan)
    assert report.window_length == pytest.approx(span, abs=2 * step)
    # The edges a figure draws are the ones the sweep found.
    assert report.window_edges[0] == pytest.approx(min(reachable), abs=2 * step)
    assert report.window_edges[1] == pytest.approx(max(reachable), abs=2 * step)


def test_the_feed_is_by_distance_rather_than_by_elapsed_time() -> None:
    """AC-RATE-01: the feed is by distance rather than by elapsed time.

    The property the whole loop rests on. Halving the belt speed has to
    halve the number of objects released in a given span of time; a feed by
    time would release the same number and only spread them further apart.
    """
    pytest.importorskip("mujoco")
    import mujoco

    released = {}
    for speed in (0.30, 0.15):
        raw, rng, model, data, plan = built(0)
        conveyor = conveyor_for(raw, rng, plan)
        conveyor.speed = speed
        for _ in range(int(40.0 / plan.timestep)):
            mujoco.mj_step(model, data)
            conveyor.step(model, data)
        released[speed] = len(conveyor.arrivals)
    assert released[0.30] >= 6, "too few objects for the ratio to mean anything"
    assert released[0.15] == pytest.approx(released[0.30] / 2, abs=1)


def test_a_slot_returns_to_the_pool_once_its_object_leaves() -> None:
    """AC-RATE-01: a slot returns to the pool once its object leaves.

    A compiled model cannot gain bodies at run time, so a line that never
    gives a slot back stops feeding after `pool_size` objects. A rate held
    for ninety seconds is a different claim from a rate held.
    """
    pytest.importorskip("mujoco")
    import mujoco

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    conveyor.speed = 0.35
    for _ in range(int(240.0 / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert conveyor.retired > 0, "nothing ever left the belt"
    assert len(conveyor.arrivals) > plan.pool_size, (
        "the line stopped feeding once the pool was spent"
    )
