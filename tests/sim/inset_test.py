"""The free-camera frame carries the detection views."""

from __future__ import annotations

import numpy as np

from clave.sim.overlay import (
    _INSET_GAP,
    inset_frame_size,
    paste_camera_insets,
    thumb_size,
)


def test_detection_views_sit_on_the_free_camera_frame() -> None:
    """AC-CAM-04: each detection view is painted along the bottom, boxes and all."""
    frame = np.zeros((90, 240, 3), dtype=np.uint8)
    gate = np.full((30, 40, 3), (0, 255, 0), dtype=np.uint8)
    pick = np.full((30, 40, 3), (255, 0, 0), dtype=np.uint8)
    paste_camera_insets(frame, (("gate_wide", gate), ("pick_wide", pick)))
    bottom = frame[-40:]
    assert bottom[:, :, 1].max() == 255
    assert bottom[:, :, 0].max() == 255
    assert frame[:40].max() == 0


def test_an_inset_keeps_the_width_it_was_given() -> None:
    """AC-CAM-05, AC-CAM-06: the views keep their width, stacked on the right.

    The free-camera pixels stay where they were, including the bottom edge
    where the placing bins sit. The gate camera is above the pick camera.
    """
    frame = np.zeros((90, 240, 3), dtype=np.uint8)
    frame[0, 0] = (7, 8, 9)
    frame[89, 230] = (1, 2, 3)
    gate = np.full((48, 64, 3), (0, 180, 0), dtype=np.uint8)
    pick = np.full((48, 64, 3), (180, 0, 0), dtype=np.uint8)
    out = paste_camera_insets(
        frame, (("gate_wide", gate), ("pick_wide", pick)), min_width=80
    )
    width, height = inset_frame_size(240, 90, 64, 48, 2, 80)
    assert out.shape == (height, width, 3)
    assert width >= 240 + 80
    assert out.shape[1] >= 240 + 80
    np.testing.assert_array_equal(out[:90, :240], frame)
    assert frame[0, 0, 0] == 7
    # The label is drawn on the view, so the check is the middle of each one.
    thumb_w, thumb_h = thumb_size(64, 48, 80)
    assert thumb_w >= 80
    gate_mid = out[thumb_h // 2, 240 + _INSET_GAP + thumb_w // 2]
    pick_mid = out[thumb_h + _INSET_GAP + thumb_h // 2, 240 + _INSET_GAP + thumb_w // 2]
    assert tuple(int(v) for v in gate_mid) == (0, 180, 0)
    assert tuple(int(v) for v in pick_mid) == (180, 0, 0)
