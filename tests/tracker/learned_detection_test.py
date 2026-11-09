"""Learned detection: image + telemetry only (issue #117).

Guards AC-DET-01, AC-DET-04, AC-DET-05, AC-DET-06, AC-DET-07, AC-DET-08,
AC-DET-09, AC-DET-10, AC-DET-11, AC-DET-17.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest

from clave.tracker.adapters.detection import detections_from_masks, oriented_extent
from clave.tracker.adapters.learned_detection import (
    DetectionTelemetry,
    InstancePrediction,
    LearnedDetectionError,
    StubSegmenter,
    detect,
    evidence_carries_simulator_identity,
    load_segmenter,
)
from clave.tracker.adapters.masks import pixel_mask_from_array
from clave.tracker.belt_frame import NadirOptics
from clave.tracker.evidence import Detection, Material, Role

WIDE = NadirOptics(camera_height=1.942, fovy=math.radians(55.65))
CAMERA = np.asarray((-1.0, 0.0, 1.942), dtype=np.float64)
SURFACE = 0.90
RENDER = (64, 48)


def _telemetry() -> DetectionTelemetry:
    return DetectionTelemetry(
        source_id="gate_wide",
        observed_at_nanos=1_000_000_000,
        camera=CAMERA,
        optics=WIDE,
        render=RENDER,
        surface_height=SURFACE + 0.05,
        belt_surface=SURFACE,
    )


def _frame() -> np.ndarray:
    return np.zeros((RENDER[1], RENDER[0], 3), dtype=np.uint8)


def _block_mask(
    row: int, column: int, height: int, width: int
) -> np.ndarray:
    mask = np.zeros((RENDER[1], RENDER[0]), dtype=bool)
    mask[row : row + height, column : column + width] = True
    return mask


def test_ac_det_01_detect_accepts_frame_and_telemetry_only() -> None:
    """AC-DET-01: detect inputs are colour frame + telemetry + segmenter."""
    mask = _block_mask(10, 20, 12, 16)
    model = StubSegmenter(
        [InstancePrediction(mask=mask, class_index=0, confidence=0.9)]
    )
    readings = detect(_frame(), _telemetry(), model)
    assert readings
    assert all(isinstance(reading, type(readings[0])) for reading in readings)


def test_ac_det_05_learned_detection_modules_import_no_mujoco() -> None:
    """AC-DET-05: learned detection must not import mujoco or render adapter."""
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "clave"
        / "tracker"
        / "adapters"
    )
    forbidden = {"mujoco", "clave.tracker.adapters.render"}
    for name in ("learned_detection.py", "masks.py"):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden
                    assert alias.name not in forbidden
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] != "mujoco"
                assert node.module != "clave.tracker.adapters.render"
                assert not node.module.startswith("clave.tracker.adapters.render")


def test_ac_det_06_detect_emits_detection_via_detections_from_masks() -> None:
    """AC-DET-06: Detection evidence carries PixelMask and oriented footprint."""
    mask = _block_mask(8, 16, 20, 24)
    model = StubSegmenter(
        [InstancePrediction(mask=mask, class_index=None, confidence=0.8)]
    )
    readings = detect(_frame(), _telemetry(), model, emit_material=False)
    assert len(readings) == 1
    reading = readings[0]
    assert reading.role is Role.DETECTION
    assert isinstance(reading.payload, Detection)
    assert reading.payload.mask.pixel_count == 20 * 24
    assert reading.payload.footprint.major_extent > 0.0


def test_ac_det_07_material_evidence_is_optional() -> None:
    """AC-DET-07: Material may accompany Detection; detection works without it."""
    mask = _block_mask(8, 16, 20, 24)
    model = StubSegmenter(
        [InstancePrediction(mask=mask, class_index=2, confidence=0.85)]
    )
    with_material = detect(_frame(), _telemetry(), model, emit_material=True)
    assert any(isinstance(item.payload, Material) for item in with_material)
    assert any(isinstance(item.payload, Detection) for item in with_material)

    without = detect(_frame(), _telemetry(), model, emit_material=False)
    assert all(isinstance(item.payload, Detection) for item in without)
    assert without


def test_ac_det_08_evidence_carries_no_simulator_identity() -> None:
    """AC-DET-08: no object id, pool slot, or geometry name in Evidence."""
    mask = _block_mask(8, 16, 20, 24)
    model = StubSegmenter(
        [InstancePrediction(mask=mask, class_index=1, confidence=0.7)]
    )
    readings = detect(_frame(), _telemetry(), model)
    assert not evidence_carries_simulator_identity(readings)
    for reading in readings:
        assert not hasattr(reading.payload, "object_id")


def test_ac_det_09_degenerate_masks_are_dropped() -> None:
    """AC-DET-09: empty / too-small instances produce no zero-size footprint."""
    empty = np.zeros((RENDER[1], RENDER[0]), dtype=bool)
    model = StubSegmenter(
        [InstancePrediction(mask=empty, class_index=0, confidence=1.0)]
    )
    assert detect(_frame(), _telemetry(), model, emit_material=False) == ()


def test_ac_det_10_footprint_matches_detections_from_masks() -> None:
    """AC-DET-10: principal-axis rules match the shared geometry path."""
    mask_array = _block_mask(10, 12, 8, 28)
    packed = pixel_mask_from_array(mask_array)
    assert packed is not None
    major, minor, yaw, oriented = oriented_extent(packed)
    model = StubSegmenter(
        [InstancePrediction(mask=mask_array, class_index=None, confidence=1.0)]
    )
    telem = _telemetry()
    learned = detect(_frame(), telem, model, emit_material=False)
    direct = detections_from_masks(
        {"only": packed},
        source_id=telem.source_id,
        observed_at_nanos=telem.observed_at_nanos,
        camera=telem.camera,
        optics=telem.optics,
        surface_height=telem.surface_height,
        render=telem.render,
        belt_surface=telem.belt_surface,
    )
    assert len(learned) == 1 and len(direct) == 1
    left = learned[0].payload
    right = direct[0].payload
    assert isinstance(left, Detection) and isinstance(right, Detection)
    assert left.footprint.major_extent == pytest.approx(right.footprint.major_extent)
    assert left.footprint.minor_extent == pytest.approx(right.footprint.minor_extent)
    assert left.footprint.oriented == oriented
    assert left.footprint.oriented == right.footprint.oriented
    if oriented:
        assert left.footprint.yaw == pytest.approx(right.footprint.yaw)
    assert major >= minor


def test_ac_det_11_projection_uses_telemetry_optics_only() -> None:
    """AC-DET-11: moving telemetry camera pose moves the footprint centre."""
    mask = _block_mask(RENDER[1] // 2 - 5, RENDER[0] // 2 - 5, 10, 10)
    model = StubSegmenter(
        [InstancePrediction(mask=mask, class_index=None, confidence=1.0)]
    )
    base = _telemetry()
    shifted = DetectionTelemetry(
        source_id=base.source_id,
        observed_at_nanos=base.observed_at_nanos,
        camera=np.asarray((-0.5, 0.0, 1.942), dtype=np.float64),
        optics=base.optics,
        render=base.render,
        surface_height=base.surface_height,
        belt_surface=base.belt_surface,
    )
    a = detect(_frame(), base, model, emit_material=False)[0].payload
    b = detect(_frame(), shifted, model, emit_material=False)[0].payload
    assert isinstance(a, Detection) and isinstance(b, Detection)
    assert b.footprint.center[0] == pytest.approx(a.footprint.center[0] + 0.5)


def test_ac_det_04_missing_checkpoint_fails_closed() -> None:
    """AC-DET-04: absent checkpoint fails naming path and train command."""
    missing = Path("/tmp/clave-missing-yolo8n-seg.pt")
    if missing.exists():
        missing.unlink()
    with pytest.raises(LearnedDetectionError, match="yolo8n_seg"):
        load_segmenter(missing)


def test_ac_det_17_offline_frame_needs_no_simulator() -> None:
    """AC-DET-17: RGB array + telemetry produces Evidence without mujoco."""
    import sys

    loaded_before = "mujoco" in sys.modules
    mask = _block_mask(8, 16, 20, 24)
    readings = detect(
        _frame(),
        _telemetry(),
        StubSegmenter(
            [InstancePrediction(mask=mask, class_index=None, confidence=0.9)]
        ),
        emit_material=False,
    )
    assert readings
    assert isinstance(readings[0].payload, Detection)
    if not loaded_before:
        assert "mujoco" not in sys.modules
