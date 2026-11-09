"""Perception latency gate (issue #117 AC-DET-18)."""

from __future__ import annotations

import pytest

from clave.validation.gates import GateConfig
from clave.validation.perception_latency import (
    PerceptionLatencyError,
    clears_perception_latency,
    require_perception_latency,
)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def test_ac_det_18_yolo_median_clears_the_perception_gate() -> None:
    """AC-DET-18: measured yolo8n-seg median (0.1342 s) clears the 0.30 s gate."""
    gates = GateConfig.load(ROOT / "configs" / "validation" / "gates.yml")
    assert clears_perception_latency(
        0.1342, gates.thresholds.max_perception_latency_p99_seconds
    )
    require_perception_latency("yolo8n-seg", 0.1342, gates.thresholds)


def test_ac_det_18_over_budget_candidate_is_refused() -> None:
    """AC-DET-18: a forward pass over the ceiling fails even if mIoU would pass."""
    gates = GateConfig.load(ROOT / "configs" / "validation" / "gates.yml")
    assert not clears_perception_latency(
        0.35, gates.thresholds.max_perception_latency_p99_seconds
    )
    with pytest.raises(PerceptionLatencyError, match="AC-DET-18"):
        require_perception_latency("too-slow-seg", 0.35, gates.thresholds)
