"""The free-camera frame carries the detection views."""

from __future__ import annotations

import numpy as np

from clave.sim.overlay import paste_camera_insets


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
