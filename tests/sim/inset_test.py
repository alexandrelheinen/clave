"""The free-camera frame carries the detection views."""

from __future__ import annotations

import numpy as np

from clave.sim.overlay import inset_frame_size, paste_camera_insets


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
    """AC-CAM-05: a detection view is at least the configured width.

    The free-camera pixels stay where they were. The views are added
    under them, so a box is not shrunk to fit a band.
    """
    frame = np.zeros((90, 240, 3), dtype=np.uint8)
    frame[0, 0] = (7, 8, 9)
    gate = np.full((48, 64, 3), (0, 180, 0), dtype=np.uint8)
    pick = np.full((48, 64, 3), (180, 0, 0), dtype=np.uint8)
    out = paste_camera_insets(
        frame, (("gate_wide", gate), ("pick_wide", pick)), min_width=80
    )
    width, height = inset_frame_size(240, 90, 64, 48, 2, 80)
    assert out.shape == (height, width, 3)
    assert out.shape[1] >= 80 * 2
    assert int(out[0, (out.shape[1] - 240) // 2, 0]) == 7
    assert frame[0, 0, 0] == 7
    band = out[90:]
    assert (band[:, :, 1] == 180).any()
    assert (band[:, :, 0] == 180).any()
