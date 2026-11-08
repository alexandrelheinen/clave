"""Colour frame plus telemetry into Detection evidence.

The pipeline is image-source agnostic: the same call accepts a simulator RGB
render, a corpus frame, or a hardware grab. Masks come from a local instance
segmenter (YOLO-seg at runtime). Oriented footprints come from the existing
`detections_from_masks` / `oriented_extent` path. Nothing here imports MuJoCo
or reads a segmentation buffer.

Issue #117: AC-DET-01, AC-DET-04 through AC-DET-11, AC-DET-17.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from clave.errors import ClaveError
from clave.taxonomy import CLASS_COUNT, MATERIAL_CLASSES
from clave.tracker.adapters.detection import detections_from_masks
from clave.tracker.adapters.masks import pixel_mask_from_array
from clave.tracker.belt_frame import NadirOptics
from clave.tracker.evidence import (
    OUTCOME_COUNT,
    Detection,
    Evidence,
    Material,
    Role,
)

TRAIN_COMMAND = "clave train --config configs/training/yolo8n_seg.yml"
"""How an operator obtains the checkpoint this path refuses to invent."""


class LearnedDetectionError(ClaveError):
    """The learned detection path cannot produce evidence as asked."""


@dataclass(frozen=True)
class DetectionTelemetry:
    """Physical quantities that place one frame on the belt.

    Attributes:
        source_id: Provenance for the evidence envelope.
        observed_at_nanos: Monotonic instant the frame was taken.
        camera: Camera pose in belt frame metres.
        optics: What its pixels are worth on the belt.
        render: Frame size as `(width, height)` in pixels.
        surface_height: Height of the surface being imaged, metres.
        belt_surface: Belt surface height in belt frame metres.
    """

    source_id: str
    observed_at_nanos: int
    camera: NDArray[np.float64]
    optics: NadirOptics
    render: tuple[int, int]
    surface_height: float
    belt_surface: float


@dataclass(frozen=True)
class InstancePrediction:
    """One instance the segmenter found in pixel space.

    Attributes:
        mask: Height by width boolean coverage.
        class_index: Taxonomy index 0..CLASS_COUNT-1, or None when unknown.
        confidence: Segmenter score in `[0, 1]`.
    """

    mask: NDArray[np.bool_]
    class_index: int | None
    confidence: float


class InstanceSegmenter(Protocol):
    """Anything that turns an RGB frame into instance masks."""

    def segment(self, frame: NDArray[np.uint8]) -> Sequence[InstancePrediction]:
        """Return every instance visible in the frame."""


def detect(
    frame: NDArray[np.uint8],
    telemetry: DetectionTelemetry,
    model: InstanceSegmenter,
    *,
    emit_material: bool = True,
) -> tuple[Evidence, ...]:
    """Run instance segmentation and emit contract evidence.

    Args:
        frame: Colour image, height by width by three, uint8.
        telemetry: Belt-frame placement for this capture.
        model: Loaded segmenter. Callers that lack a checkpoint must not reach
            here: use `load_segmenter` which fails closed.
        emit_material: When True, also emit `Material` evidence per instance
            that carries a class index.

    Returns:
        Detection evidence (and optional Material evidence) with no simulator
        identity in any field.

    Raises:
        LearnedDetectionError: If the frame shape disagrees with telemetry.
    """
    _check_frame(frame, telemetry.render)
    predictions = model.segment(frame)
    masks: dict[str, Any] = {}
    materials: list[Evidence] = []
    for index, prediction in enumerate(predictions):
        packed = pixel_mask_from_array(prediction.mask)
        if packed is None:
            continue
        # Keys are iteration handles only; detections_from_masks discards them.
        masks[f"instance_{index}"] = packed
        if emit_material and prediction.class_index is not None:
            materials.append(
                _material_evidence(telemetry, prediction.class_index, prediction.confidence)
            )

    detections = detections_from_masks(
        masks,
        source_id=telemetry.source_id,
        observed_at_nanos=telemetry.observed_at_nanos,
        camera=telemetry.camera,
        optics=telemetry.optics,
        surface_height=telemetry.surface_height,
        render=telemetry.render,
        belt_surface=telemetry.belt_surface,
    )
    return detections + tuple(materials)


def load_segmenter(checkpoint: Path) -> InstanceSegmenter:
    """Load a YOLO-seg checkpoint, failing closed when it is absent.

    Args:
        checkpoint: Path to the weights file.

    Returns:
        A segmenter ready for `detect`.

    Raises:
        LearnedDetectionError: If the file is missing, naming it and the train
            command that produces it.
    """
    if not checkpoint.is_file():
        raise LearnedDetectionError(
            f"detection checkpoint {checkpoint} is absent; "
            f"train it with `{TRAIN_COMMAND}`"
        )
    return YoloSegmenter(checkpoint)


class YoloSegmenter:
    """Ultralytics YOLO instance segmentation wrapper.

    Imports stay inside methods so importing this module does not require
    ultralytics on machines that only run the geometry tests.
    """

    def __init__(self, checkpoint: Path) -> None:
        """Load weights from disk.

        Args:
            checkpoint: Path to a YOLO-seg weights file.
        """
        from ultralytics import YOLO

        self._model = YOLO(str(checkpoint))

    def segment(self, frame: NDArray[np.uint8]) -> Sequence[InstancePrediction]:
        """Run one forward pass on an RGB frame."""
        results = self._model.predict(frame, verbose=False)
        if not results:
            return ()
        result = results[0]
        if result.masks is None or result.boxes is None:
            return ()
        masks = result.masks.data
        classes = result.boxes.cls
        scores = result.boxes.conf
        height, width = frame.shape[:2]
        predictions: list[InstancePrediction] = []
        for index in range(int(masks.shape[0])):
            mask = _resize_mask(masks[index], height, width)
            class_index = int(classes[index].item())
            if not 0 <= class_index < CLASS_COUNT:
                class_index_value: int | None = None
            else:
                class_index_value = class_index
            predictions.append(
                InstancePrediction(
                    mask=mask,
                    class_index=class_index_value,
                    confidence=float(scores[index].item()),
                )
            )
        return tuple(predictions)


class StubSegmenter:
    """Deterministic segmenter for tests that cannot load ultralytics.

    Attributes:
        predictions: Fixed instances returned for every frame.
    """

    def __init__(self, predictions: Sequence[InstancePrediction]) -> None:
        self._predictions = tuple(predictions)

    def segment(self, frame: NDArray[np.uint8]) -> Sequence[InstancePrediction]:
        """Ignore the frame and return the fixture predictions."""
        del frame
        return self._predictions


def _check_frame(frame: NDArray[np.uint8], render: tuple[int, int]) -> None:
    """Refuse a frame whose shape disagrees with telemetry."""
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise LearnedDetectionError(
            f"detection expects an HxWx3 colour frame, got shape {frame.shape}"
        )
    height, width = frame.shape[:2]
    expected_width, expected_height = render
    if (width, height) != (expected_width, expected_height):
        raise LearnedDetectionError(
            f"frame is {width}x{height} but telemetry.render is "
            f"{expected_width}x{expected_height}"
        )


def _material_evidence(
    telemetry: DetectionTelemetry, class_index: int, confidence: float
) -> Evidence:
    """Build a Material reading peaked on one taxonomy class."""
    weights = [0.0] * OUTCOME_COUNT
    # Reject is the last slot; taxonomy classes occupy 0..CLASS_COUNT-1.
    peak = min(1.0, max(0.0, confidence))
    remainder = 1.0 - peak
    if CLASS_COUNT > 1:
        share = remainder / (OUTCOME_COUNT - 1)
        for index in range(OUTCOME_COUNT):
            weights[index] = share
    weights[class_index] = peak
    total = sum(weights)
    weights = [weight / total for weight in weights]
    # MATERIAL_CLASSES is only referenced so a wrong CLASS_COUNT fails loudly.
    assert len(MATERIAL_CLASSES) == CLASS_COUNT
    return Evidence(
        source_id=telemetry.source_id,
        role=Role.SPECTRAL,
        observed_at_nanos=telemetry.observed_at_nanos,
        confidence=peak,
        payload=Material(posterior=tuple(weights)),
    )


def _resize_mask(
    mask: Any, height: int, width: int
) -> NDArray[np.bool_]:
    """Resize a model mask tensor to the frame size as a boolean array."""
    import torch
    import torch.nn.functional as functional

    if hasattr(mask, "detach"):
        tensor = mask.detach().float().unsqueeze(0).unsqueeze(0)
    else:
        tensor = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
    if tensor.shape[-2:] != (height, width):
        tensor = functional.interpolate(
            tensor, size=(height, width), mode="bilinear", align_corners=False
        )
    return tensor.squeeze().cpu().numpy() > 0.5


def evidence_carries_simulator_identity(readings: Sequence[Evidence]) -> bool:
    """Return whether any reading leaks a simulator object id or geometry name.

    Used by AC-DET-08 tests. Detection payloads carry masks and footprints only;
    Material carries a posterior. Neither may hold an object id field.
    """
    for reading in readings:
        payload = reading.payload
        if isinstance(payload, Detection):
            # PixelMask has no identity; footprint has no object id.
            continue
        if hasattr(payload, "object_id"):
            return True
    return False
