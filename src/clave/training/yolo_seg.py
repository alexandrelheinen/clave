"""Train and score YOLO-seg from corpus instance maps without a live simulator.

Issue #117: AC-DET-12, AC-DET-13, AC-DET-14.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.data.examples import Example
from clave.errors import ClaveError
from clave.taxonomy import CLASS_COUNT, MATERIAL_CLASSES
from clave.training.adapters import CLASS_INDEX

CANDIDATE = "yolo8n-seg"
"""Registry name for the Ultralytics YOLOv8n-seg candidate."""


class YoloSegError(ClaveError):
    """YOLO-seg training or scoring cannot proceed."""


def instance_masks(
    example: Example,
) -> tuple[tuple[int, NDArray[np.bool_]], ...]:
    """Return (class_index, mask) pairs from the corpus instance map.

    Args:
        example: A capture that may carry `instance_ids` on its primary frame
            or first camera capture.

    Returns:
        One entry per visible instance with a non-empty mask. Empty when the
        example has no instance map.
    """
    ids = _instance_map(example)
    if ids is None:
        return ()
    by_serial = {label.object_id: label for label in example.visible_labels}
    found: list[tuple[int, NDArray[np.bool_]]] = []
    for serial in np.unique(ids):
        if int(serial) == 0:
            continue
        label = by_serial.get(int(serial))
        if label is None:
            continue
        mask = ids == serial
        if not bool(mask.any()):
            continue
        found.append((CLASS_INDEX[label.material_class], np.asarray(mask, dtype=bool)))
    return tuple(found)


def export_dataset(examples: Sequence[Example], root: Path) -> Path:
    """Write a YOLO-seg dataset from corpus examples.

    Args:
        examples: Frames with instance maps. Examples without masks are skipped.
        root: Directory that receives `images/`, `labels/`, and `data.yaml`.

    Returns:
        The path to `data.yaml`.

    Raises:
        YoloSegError: If no example carried a usable instance map.
    """
    images = root / "images"
    labels = root / "labels"
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    written = 0
    for index, example in enumerate(examples):
        masks = instance_masks(example)
        if not masks:
            continue
        name = f"{index:06d}"
        _write_image(example.frame, images / f"{name}.jpg")
        _write_label(masks, labels / f"{name}.txt")
        written += 1
    if written == 0:
        raise YoloSegError(
            "no corpus example carried an instance map YOLO-seg can train on"
        )
    data_yaml = root / "data.yaml"
    names = {index: entry.id for index, entry in enumerate(MATERIAL_CLASSES)}
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {root.resolve()}",
                "train: images",
                "val: images",
                f"nc: {CLASS_COUNT}",
                f"names: {json.dumps(names)}",
                "",
            ]
        )
    )
    return data_yaml


def yolo_seg_batches(
    examples: tuple[Example, ...],
    batch_size: int,
    augment: bool = False,
    input_side: int | None = None,
) -> Iterator[
    tuple[list[NDArray[np.uint8]], list[tuple[tuple[int, NDArray[np.bool_]], ...]]]
]:
    """Yield RGB frames paired with instance masks for scoring and smoke tests.

    Args:
        examples: Corpus examples.
        batch_size: Examples per batch.
        augment: Unused; Ultralytics owns augmentation during its train loop.
        input_side: Unused; kept so the call shape matches other batchers.

    Yields:
        Parallel lists of frames and per-frame instance mask tuples.
    """
    del augment, input_side
    usable = [item for item in examples if instance_masks(item)]
    for start in range(0, len(usable), batch_size):
        chunk = usable[start : start + batch_size]
        yield (
            [item.frame for item in chunk],
            [instance_masks(item) for item in chunk],
        )


def train_from_examples(
    examples: Sequence[Example],
    *,
    epochs: int,
    checkpoints: Path,
    seed: int,
    work: Path | None = None,
) -> Path:
    """Train YOLO-seg on corpus examples and write a CLAVE checkpoint.

    Args:
        examples: Training frames with instance maps.
        epochs: Ultralytics training epochs.
        checkpoints: Directory for `{CANDIDATE}.pt` and `{CANDIDATE}.best.pt`.
        seed: Training seed.
        work: Scratch directory for the exported dataset. Defaults under
            `checkpoints`.

    Returns:
        Path to the written `{CANDIDATE}.pt` checkpoint.

    Raises:
        YoloSegError: If ultralytics is missing or export finds no masks.
    """
    from ultralytics import YOLO

    checkpoints.mkdir(parents=True, exist_ok=True)
    scratch = work or (checkpoints / f".{CANDIDATE}-export")
    data_yaml = export_dataset(examples, scratch)
    model = YOLO("yolov8n-seg.yaml")
    model.model.nc = CLASS_COUNT
    model.train(
        data=str(data_yaml),
        epochs=max(1, epochs),
        imgsz=640,
        batch=min(8, max(1, len(tuple(examples)))),
        seed=seed,
        project=str(checkpoints / f".{CANDIDATE}-runs"),
        name="train",
        exist_ok=True,
        verbose=False,
        workers=0,
        device="cpu",
    )
    best = Path(model.trainer.best) if model.trainer is not None else None
    if best is None or not best.is_file():
        # Fall back to the last weights Ultralytics left beside the run.
        run_dir = checkpoints / f".{CANDIDATE}-runs" / "train" / "weights"
        best = run_dir / "best.pt"
        if not best.is_file():
            best = run_dir / "last.pt"
    if not best.is_file():
        raise YoloSegError("ultralytics finished without writing weights")
    return write_clave_checkpoint(best, checkpoints)


def write_clave_checkpoint(weights: Path, checkpoints: Path) -> Path:
    """Publish Ultralytics weights under the CLAVE candidate name.

    The `.pt` file stays an Ultralytics checkpoint so `YOLO(path)` loads it.
    A sibling `.meta.json` records the candidate name for fail-closed checks.

    Args:
        weights: A `.pt` file Ultralytics wrote.
        checkpoints: Destination directory.

    Returns:
        Path to `{CANDIDATE}.pt`.
    """
    import shutil

    destination = checkpoints / f"{CANDIDATE}.pt"
    shutil.copy2(weights, destination)
    shutil.copy2(weights, checkpoints / f"{CANDIDATE}.best.pt")
    meta = {
        "candidate": CANDIDATE,
        "input_side_pixels": 640,
    }
    (checkpoints / f"{CANDIDATE}.meta.json").write_text(json.dumps(meta, indent=2))
    return destination


def load_yolo_from_checkpoint(checkpoint: Path) -> Any:
    """Load a YOLO-seg model from a published checkpoint.

    Args:
        checkpoint: `{CANDIDATE}.pt` written by `write_clave_checkpoint`.

    Returns:
        An Ultralytics YOLO model ready for `predict`.

    Raises:
        YoloSegError: If the file is missing or names another candidate.
    """
    from ultralytics import YOLO

    if not checkpoint.is_file():
        raise YoloSegError(
            f"detection checkpoint {checkpoint} is absent; "
            "train it with `clave train --config configs/training/yolo8n_seg.yml`"
        )
    meta_path = checkpoint.with_name(f"{checkpoint.stem}.meta.json")
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        if meta.get("candidate") != CANDIDATE:
            raise YoloSegError(
                f"{meta_path} holds {meta.get('candidate')!r}, not {CANDIDATE!r}"
            )
    return YOLO(str(checkpoint))


def mean_mask_iou(
    predicted: Sequence[NDArray[np.bool_]],
    truth: Sequence[NDArray[np.bool_]],
) -> float:
    """Mean best mask IoU of each ground-truth instance against predictions.

    Args:
        predicted: Predicted boolean masks for one frame.
        truth: Ground-truth boolean masks for the same frame.

    Returns:
        Mean best overlap, or 0.0 when there is no ground truth.
    """
    if not truth:
        return 0.0
    scores: list[float] = []
    for gold in truth:
        if not predicted:
            scores.append(0.0)
            continue
        scores.append(max(_mask_iou(gold, other) for other in predicted))
    return float(np.mean(scores))


def score_masks(
    model: Any,
    examples: Sequence[Example],
) -> tuple[float, int]:
    """Score YOLO-seg predictions against corpus instance maps.

    Args:
        model: Ultralytics YOLO model.
        examples: Validation examples.

    Returns:
        Mean mask IoU across instances, and the number of ground-truth
        instances scored. AC-DET-14: object ids are never handed to the model.
    """
    overlaps: list[float] = []
    for example in examples:
        truth = [mask for _, mask in instance_masks(example)]
        if not truth:
            continue
        results = model.predict(example.frame, verbose=False)
        predicted: list[NDArray[np.bool_]] = []
        if results and results[0].masks is not None:
            height, width = example.frame.shape[:2]
            for row in results[0].masks.data:
                predicted.append(_as_bool_mask(row, height, width))
        overlaps.append(mean_mask_iou(predicted, truth))
    if not overlaps:
        return 0.0, 0
    return float(np.mean(overlaps)), len(overlaps)


def _instance_map(example: Example) -> NDArray[np.uint16] | None:
    """Prefer the first camera capture's map, else None."""
    if example.captures:
        return example.captures[0].instance_ids
    return None


def _write_image(frame: NDArray[np.uint8], path: Path) -> None:
    """Write an RGB frame as JPEG without requiring OpenCV at import time."""
    from PIL import Image

    Image.fromarray(frame).save(path, format="JPEG", quality=95)


def _write_label(
    masks: Sequence[tuple[int, NDArray[np.bool_]]], path: Path
) -> None:
    """Write YOLO-seg polygon lines for one image."""
    lines: list[str] = []
    for class_index, mask in masks:
        polygon = _mask_to_polygon(mask)
        if polygon is None:
            continue
        coords = " ".join(f"{value:.6f}" for value in polygon)
        lines.append(f"{class_index} {coords}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def _mask_to_polygon(mask: NDArray[np.bool_]) -> tuple[float, ...] | None:
    """Approximate a boolean mask as a normalized xy polygon for YOLO labels."""
    import cv2

    height, width = mask.shape
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 4.0:
        return None
    epsilon = 0.002 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 3:
        return None
    points: list[float] = []
    for point in approx.reshape(-1, 2):
        points.append(float(point[0]) / float(width))
        points.append(float(point[1]) / float(height))
    return tuple(points)


def _mask_iou(left: NDArray[np.bool_], right: NDArray[np.bool_]) -> float:
    """Intersection over union of two boolean masks."""
    intersection = np.logical_and(left, right).sum()
    union = np.logical_or(left, right).sum()
    if union == 0:
        return 0.0
    return float(intersection) / float(union)


def _as_bool_mask(mask: Any, height: int, width: int) -> NDArray[np.bool_]:
    """Resize a model mask tensor to the frame grid."""
    import torch.nn.functional as functional

    tensor = mask.detach().float().unsqueeze(0).unsqueeze(0)
    if tensor.shape[-2:] != (height, width):
        tensor = functional.interpolate(
            tensor, size=(height, width), mode="bilinear", align_corners=False
        )
    return tensor.squeeze().cpu().numpy() > 0.5
