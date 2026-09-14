"""Tests for the process boundary.

These start the real runtime, so they build it when it is not built and skip
when cargo is absent. Covers `AC-BRIDGE-04`, `AC-SAFETY-01` and `AC-SAFETY-07`.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clave.runtime.bridge import Bridge, BridgeError, BridgePaths, locate_binary
from clave.runtime.proposal import Proposal

ROOT = Path(__file__).resolve().parents[2]

CONFIG: dict[str, Any] = {
    "arm_base_meters": [0.0, -0.34, 0.35],
    "reach_radius_meters": 0.38,
    "belt_surface_z_meters": 0.35,
    "belt_x_meters": [-1.0, 1.0],
    "belt_y_meters": [-0.25, 0.25],
    "channels": {"M-01": 1},
    "reject_channel": 0,
    "confidence_floor": 0.6,
}


def binary_or_skip() -> Path:
    """Return the built runtime, building it once if it is absent."""
    try:
        return locate_binary(ROOT)
    except BridgeError:
        pass
    if shutil.which("cargo") is None:
        pytest.skip("cargo is absent, so the runtime cannot be built here")
    subprocess.run(
        ["cargo", "build", "-p", "clave-sitl"], cwd=ROOT, check=True, timeout=900
    )
    return locate_binary(ROOT)


def proposal(x: float, y: float, z: float, confidence: float) -> Proposal:
    """Build a proposal naming a point at a confidence."""
    return Proposal(
        object_id=7,
        material_class="M-01",
        confidence=confidence,
        point=(x, y, z),
        yaw_radians=0.0,
        reference_time_nanos=1_000,
        window_start_nanos=1_000,
        window_end_nanos=2**62,
    )


def test_the_bridge_reports_a_runtime_that_was_never_built(tmp_path: Path) -> None:
    """The error says how to build it rather than what file is missing."""
    with pytest.raises(BridgeError, match="cargo build"):
        locate_binary(tmp_path)


def test_every_verdict_crosses_the_boundary_and_is_counted(tmp_path: Path) -> None:
    """One round trip per proposal, and the runtime's own counts at the end."""
    binary = binary_or_skip()
    paths = BridgePaths.under(tmp_path)
    with Bridge(binary, paths, CONFIG) as bridge:
        sorted_outcome = bridge.submit(proposal(0.0, 0.0, 0.36, 0.9))
        assert sorted_outcome.accepted
        assert sorted_outcome.channel == 1

        overridden = bridge.submit(proposal(0.9, 0.0, 0.36, 0.9))
        assert overridden.overridden
        assert overridden.check == "reach"

        rejected = bridge.submit(proposal(0.0, 0.0, 0.36, 0.1))
        assert rejected.accepted
        assert rejected.channel == 0
        assert rejected.reject_reason == "below_threshold"

        assert bridge.decisions_received == 2
        counters = bridge.counters()

    assert counters["proposals"] == 3
    assert counters["accepted"] == 1
    assert counters["overridden_reach"] == 1
    assert counters["rejected_low_confidence"] == 1
    assert counters["published"] == 2


def test_a_proposal_submitted_before_the_runtime_starts_is_refused(
    tmp_path: Path,
) -> None:
    """A bridge that is not running says so rather than dropping the message."""
    bridge = Bridge(Path("unused"), BridgePaths.under(tmp_path), CONFIG)
    with pytest.raises(BridgeError, match="not running"):
        bridge.submit(proposal(0.0, 0.0, 0.36, 0.9))
