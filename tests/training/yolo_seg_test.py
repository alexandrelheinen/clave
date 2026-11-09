"""YOLO-seg corpus helpers (issue #117 AC-DET-12, AC-DET-13, AC-DET-14)."""

from __future__ import annotations

import numpy as np

from clave.data.examples import CameraCapture, Example, ObjectLabel, Origin
from clave.training.yolo_seg import (
    export_dataset,
    instance_masks,
    mean_mask_iou,
    yolo_seg_batches,
)


def _example_with_map() -> Example:
    frame = np.zeros((32, 40, 3), dtype=np.uint8)
    ids = np.zeros((32, 40), dtype=np.uint16)
    ids[8:20, 10:26] = 7
    label = ObjectLabel(
        object_id=7,
        material_class="M-01",
        channel="CH-PET",
        position=np.asarray((0.0, 0.0, 0.9), dtype=np.float64),
        in_reachable_window=True,
        bbox=(10, 8, 25, 19),
    )
    capture = CameraCapture(
        camera_id="gate_wide", frame=frame, labels=(label,), instance_ids=ids
    )
    return Example(
        frame=frame,
        labels=(label,),
        simulated_time=1.0,
        seed=0,
        config_digest="deadbeef",
        origin=Origin.SIMULATED,
        captures=(capture,),
    )


def test_ac_det_12_instance_masks_come_from_corpus_without_simulator() -> None:
    """AC-DET-12: masks are derived from stored instance maps only."""
    pairs = instance_masks(_example_with_map())
    assert len(pairs) == 1
    class_index, mask = pairs[0]
    assert class_index == 0
    assert int(mask.sum()) == 12 * 16


def test_ac_det_12_export_writes_yolo_dataset(tmp_path) -> None:
    """AC-DET-12: export builds images/labels/data.yaml from corpus examples."""
    data_yaml = export_dataset((_example_with_map(),), tmp_path / "yolo")
    assert data_yaml.is_file()
    assert (tmp_path / "yolo" / "images" / "000000.jpg").is_file()
    assert (tmp_path / "yolo" / "labels" / "000000.txt").is_file()
    text = (tmp_path / "yolo" / "labels" / "000000.txt").read_text().strip()
    assert text.startswith("0 ")


def test_ac_det_13_mean_mask_iou_scores_overlap() -> None:
    """AC-DET-13: identical masks score 1.0; disjoint score 0.0."""
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 2:5] = True
    assert mean_mask_iou([mask], [mask]) == 1.0
    other = np.zeros((10, 10), dtype=bool)
    other[7:9, 7:9] = True
    assert mean_mask_iou([other], [mask]) == 0.0


def test_ac_det_14_batches_expose_pixels_not_object_ids() -> None:
    """AC-DET-14: batch contents are frames and masks, never object ids."""
    batches = list(yolo_seg_batches((_example_with_map(),), batch_size=1))
    assert len(batches) == 1
    frames, targets = batches[0]
    assert frames[0].shape == (32, 40, 3)
    class_index, mask = targets[0][0]
    assert isinstance(class_index, int)
    assert mask.dtype == bool
