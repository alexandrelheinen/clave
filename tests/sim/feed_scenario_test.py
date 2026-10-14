"""One run asking for a feed the shipped drive cannot hold.

AC-RATE-12. The file names the rate. This proves the simulation reports
that rate and that objects actually arrive faster than the shipped line.
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
    assert report.belt_speed > 1.0
    assert report.measured_rate > 1.0
