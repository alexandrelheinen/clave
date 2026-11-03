"""Boxes painted on a detection-camera frame."""

import numpy as np
import pytest

from clave.sim.overlay import bounds_of, paint_boxes


def test_bounds_follow_the_runs_ac_cam_03() -> None:
    """AC-CAM-03: a box is the inclusive extent of the object's runs."""
    # Row 2, columns 3 through 5, and row 4, columns 1 through 2.
    assert bounds_of(((2, 3, 3), (4, 1, 2))) == (1, 2, 5, 4)


def test_boxes_paint_the_border_and_leave_the_rest_ac_cam_03() -> None:
    """AC-CAM-03: the border takes the overlay colour; the rest stays."""
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    paint_boxes(frame, ((1, 2, 4, 5),))
    assert tuple(frame[2, 1]) == (0, 255, 0)
    assert tuple(frame[2, 4]) == (0, 255, 0)
    assert tuple(frame[5, 4]) == (0, 255, 0)
    assert tuple(frame[3, 2]) == (0, 0, 0)
    assert tuple(frame[0, 0]) == (0, 0, 0)


def test_a_box_on_a_camera_frame_survives_the_inset_scale() -> None:
    """AC-CAM-07: scaling a camera frame leaves a rectangle, not a dot."""
    cv2 = pytest.importorskip("cv2")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    paint_boxes(frame, ((80, 60, 200, 180),))
    thumb = np.asarray(
        cv2.resize(frame, (480, 360), interpolation=cv2.INTER_AREA),
        dtype=np.uint8,
    )
    scale_x = 480 / 640
    scale_y = 360 / 480
    top = int(round(60 * scale_y))
    mid = int(round(140 * scale_x))
    centre_y = int(round(120 * scale_y))
    centre_x = int(round(140 * scale_x))
    assert int(thumb[top, mid, 1]) > 100
    assert int(thumb[top + 1, mid, 1]) > 80
    assert int(thumb[centre_y, centre_x, 1]) < 20
