"""Runtime wiring for learned detection (issue #117 AC-DET-03, 04, 16)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from clave.sim.debug_run import DebugRunError, run
from clave.tracker.adapters.learned_detection import StubSegmenter

ROOT = Path(__file__).resolve().parents[2]


def test_ac_det_03_debug_config_names_detection_checkpoint() -> None:
    """AC-DET-03: debug configuration names the detection checkpoint key."""
    text = (ROOT / "configs" / "debug" / "tracker.yml").read_text()
    assert "detection:" in text
    assert "checkpoint:" in text
    assert "yolo8n-seg" in text


def test_ac_det_04_missing_checkpoint_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-DET-04: absent weights fail naming the train command; no MuJoCo fallback."""
    from clave.tracker.adapters.learned_detection import load_segmenter as real_load

    monkeypatch.setattr("clave.sim.debug_run.load_segmenter", real_load)
    with pytest.raises(DebugRunError, match="yolo8n_seg"):
        run(
            root=ROOT,
            out=tmp_path,
            seconds=0.2,
            seed=0,
            window=False,
            video=False,
            frames=False,
            progress=False,
            segmenter=None,
            detection_checkpoint=tmp_path / "missing-yolo8n-seg.pt",
        )


def test_ac_det_16_debug_run_does_not_call_segment_masks() -> None:
    """AC-DET-16: detection path does not import or call MuJoCo segment_masks."""
    source = (ROOT / "src" / "clave" / "sim" / "debug_run.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "clave.tracker.adapters.render"
            if node.names:
                assert all(alias.name != "segment_masks" for alias in node.names)
                assert all(
                    alias.name != "detections_from_masks" for alias in node.names
                )
    assert "segment_masks" not in source
    assert "detections_from_masks" not in source


def test_ac_det_16_capture_runs_with_injected_segmenter(tmp_path: Path) -> None:
    """AC-DET-16: a capture loop observes through the injected segmenter."""
    report = run(
        root=ROOT,
        out=tmp_path,
        seconds=0.6,
        seed=0,
        window=False,
        video=False,
        frames=False,
        progress=False,
        ground_truth_tracker=True,
        segmenter=StubSegmenter(()),
    )
    assert report.captures > 0
