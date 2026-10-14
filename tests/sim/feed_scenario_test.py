"""One run asking for a closer feed on the shipped belt.

AC-RATE-12 and AC-RATE-13. The file keeps the shipped setpoint and names
a spacing. The run reports that setpoint, keeps the belt inside the
drive, and lets objects arrive faster than the shipped spacing does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clave.sim.debug_run import run
from clave.world.feed import FeedScenario

ROOT = Path(__file__).resolve().parents[2]


def test_a_feed_file_raises_the_setpoint_for_one_run(tmp_path: Path) -> None:
    """AC-RATE-12: a feed file raises the setpoint for one run."""
    pytest.importorskip("mujoco")
    scenario = FeedScenario.load(ROOT / "configs" / "debug" / "high-flow.yml")
    report = run(
        ROOT,
        out=tmp_path,
        seconds=3.0,
        seed=0,
        window=False,
        video=False,
        frames=False,
        progress=False,
        feed_path=Path("configs/debug/high-flow.yml"),
    )
    assert report.feed_rate == scenario.rate
    assert 0.25 <= report.belt_speed <= 0.35
    assert report.measured_rate > 0.6


def test_high_flow_spacing_is_the_ten_times_flow() -> None:
    """AC-RATE-15: high-flow centers are 0.125 m, so the floor carries 2.0/s.

    The two largest bounding radii still sum to more than that gap.
    Packages may touch. The earlier clearance floor is withdrawn.
    """
    mujoco = pytest.importorskip("mujoco")
    import numpy as np

    from clave.world import scene
    from clave.world.config import load

    scenario = FeedScenario.load(ROOT / "configs" / "debug" / "high-flow.yml")
    world = load(ROOT / "configs" / "world" / "sorting_line.yml")
    model, _data, plan = scene.build(
        world,
        np.random.default_rng(0),
        ROOT,
    )
    radii: list[float] = []
    for spec in plan.objects:
        mesh = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_MESH, f"asset_{spec.name}")
        start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
        vertices = model.mesh_vert[start : start + count]
        radii.append(float(np.linalg.norm(vertices, axis=1).max()))
    radii.sort(reverse=True)
    clearance = radii[0] + radii[1]
    assert scenario.spacing.low == pytest.approx(0.125)
    assert scenario.spacing.high == pytest.approx(0.125)
    assert scenario.spacing.low < clearance
    assert scenario.belt_speed / scenario.spacing.low == pytest.approx(2.0)
    assert scenario.pool_size is not None
    assert scenario.pool_size > int(world["spawn"]["pool_size"])
