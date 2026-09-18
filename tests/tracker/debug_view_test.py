"""Annotating a frame with everything the tracker believes.



The rule this file exists to keep honest is that nothing is drawn which the
record does not carry. A view that invents a value is a view that argues for
something the system does not know, which is the failure the
no-fabricated-evidence rule guards against everywhere else in this repository.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from clave.tracker.belt_frame import Footprint, NadirOptics
from clave.tracker.debug_view import (
    DebugViewError,
    annotate,
    colour_for,
    described_fields,
    to_pixels,
)
from clave.tracker.evidence import Role
from clave.tracker.track import WasteObject
from clave.world.config import Range

ROOT = Path(__file__).resolve().parents[2]
WIDE = NadirOptics(camera_height=1.942, fovy_degrees=55.65)
CAMERA = (-1.0, 0.0, 1.942)
SURFACE = 0.90
RENDER = (640, 480)


def a_record(track_id: int = 1, **overrides: object) -> WasteObject:
    """One settled record."""
    fields: dict[str, object] = {
        "track_id": track_id,
        "observed_at_nanos": 1_000_000_000,
        "valid_until_nanos": 4_000_000_000,
        "footprint": Footprint(
            center=(-1.0, 0.0, 0.93), major_extent=0.10, minor_extent=0.06, yaw=0.3
        ),
        "height": 0.06,
        "material": "M-06",
        "material_confidence": 0.94,
        "density": Range(180.0, 320.0),
        "mass": Range(0.065, 0.115),
        "codes": ("037600138727",),
        "evidence": frozenset({Role.DETECTION, Role.GROUND_TRUTH}),
        "simulated": frozenset({"material"}),
    }
    fields.update(overrides)
    return WasteObject(**fields)  # type: ignore[arg-type]


def blank() -> Any:
    """A frame with nothing on it."""
    import numpy as np

    return np.full((RENDER[1], RENDER[0], 3), 40, dtype=np.uint8)


def test_a_belt_point_projects_back_to_the_pixel_it_came_from() -> None:
    """A belt point projects back to the pixel it came from.

    The inverse of the adapter's own conversion. Using a different scale factor
    would put every box slightly off its object, consistently, which is the
    kind of wrong that looks right.
    """
    from clave.tracker.adapters.detection import to_belt

    column, row = 400.0, 180.0
    x, y = to_belt(column, row, CAMERA, WIDE, SURFACE, RENDER)
    back = to_pixels(x, y, CAMERA, WIDE, SURFACE, RENDER)
    assert back[0] == pytest.approx(column, abs=1e-6)
    assert back[1] == pytest.approx(row, abs=1e-6)


def test_every_field_of_the_record_is_described() -> None:
    """Every field of the record is described.

    The contract is the record's own shape. Adding a field to `WasteObject` and
    not to the view fails here, which is what stops the view quietly showing
    less than the tracker knows.
    """
    stored = {field.name for field in dataclasses.fields(WasteObject)}
    computed = {"grasp_point", "grasp_axis", "grasp_width", "surface_normal"}
    assert described_fields(a_record()).keys() >= stored | computed


def test_nothing_is_drawn_that_the_record_does_not_carry() -> None:
    """Nothing is drawn that the record does not carry.

    Every value in the listing has to be traceable to a field. A view that
    computes a number for display is drawing something the system does not
    know.
    """
    record = a_record()
    described = described_fields(record)
    for name, shown in described.items():
        assert shown, f"{name} rendered as nothing"
        if name in {field.name for field in dataclasses.fields(record)}:
            held = getattr(record, name)
            assert str(held) in shown or _looks_like(held, shown), (
                f"{name} shows {shown!r}, which does not follow from {held!r}"
            )


def _looks_like(held: object, shown: str) -> bool:
    """Whether a rendered string plausibly comes from the value it claims.

    Checks each component rather than the repr, because a field is traceable
    when every number in it appears, not when its `str()` appears verbatim.
    """
    if dataclasses.is_dataclass(held) and not isinstance(held, type):
        return all(
            _looks_like(getattr(held, field.name), shown)
            for field in dataclasses.fields(held)
            if field.name != "oriented"
        )
    if isinstance(held, bool):
        return True
    if isinstance(held, Range):
        return f"{held.low:.3f}" in shown and f"{held.high:.3f}" in shown
    if isinstance(held, frozenset):
        return all(str(getattr(item, "value", item)) in shown for item in held)
    if isinstance(held, tuple):
        return all(str(round(v, 3)) in shown for v in held if isinstance(v, float)) or (
            all(str(v) in shown for v in held)
        )
    if isinstance(held, float):
        return f"{held:.3f}" in shown or f"{held:.2f}" in shown
    return str(held) in shown


def test_a_track_keeps_one_colour_and_two_tracks_differ() -> None:
    """A track keeps one colour and two tracks differ."""
    assert colour_for(7) == colour_for(7)
    assert colour_for(7) != colour_for(8)
    for channel in colour_for(7):
        assert 0 <= channel <= 255


def test_a_simulated_field_is_marked_as_one() -> None:
    """A simulated field is marked as one.

    A reader auditing perception has to see which values the simulator supplied,
    because a material folded from `GroundTruth` is the simulator's label.
    """
    described = described_fields(a_record(simulated=frozenset({"material"})))
    assert "simulated" in described["material"].lower()
    clean = described_fields(a_record(simulated=frozenset()))
    assert "simulated" not in clean["material"].lower()


def test_an_unoriented_footprint_is_not_drawn_as_a_square_one() -> None:
    """An unoriented footprint is not drawn as a square one.

    A can is circular in plan. Drawing it with a confident yaw of zero is a
    claim the record declined to make.
    """
    round_box = Footprint(
        center=(-1.0, 0.0, 0.93),
        major_extent=0.07,
        minor_extent=0.07,
        yaw=0.0,
        oriented=False,
    )
    described = described_fields(a_record(footprint=round_box))
    assert "unoriented" in described["footprint"].lower()


def test_the_frame_says_it_is_a_debug_render_of_the_tracker() -> None:
    """The frame says it is a debug render of the tracker.

    Nothing produced here may be read as the loop's output or as a figure.
    """
    pytest.importorskip("cv2")
    frame, caption = annotate(
        blank(), (a_record(),), CAMERA, WIDE, SURFACE, RENDER, at_nanos=1_000_000_000
    )
    assert "debug" in caption.lower()
    assert "tracker" in caption.lower()
    assert frame.shape[0] >= RENDER[1]


def test_annotating_changes_the_frame_it_was_given_only_by_copy() -> None:
    """Annotating changes the frame it was given only by copy.

    The source frame is what the simulator rendered. Drawing into it in place
    would mean the same array reaching a published encoder already marked.
    """
    pytest.importorskip("cv2")
    import numpy as np

    source = blank()
    before = np.array(source, copy=True)
    annotate(
        source, (a_record(),), CAMERA, WIDE, SURFACE, RENDER, at_nanos=1_000_000_000
    )
    assert np.array_equal(source, before), "the source frame was drawn into"


def test_a_record_off_the_frame_is_reported_rather_than_drawn_at_an_edge() -> None:
    """A record off the frame is reported rather than drawn at an edge.

    A track propagated past the belt has no pixel, and clamping it to the border
    would put a box where no object is.
    """
    pytest.importorskip("cv2")
    far = a_record(
        footprint=Footprint(
            center=(40.0, 0.0, 0.93), major_extent=0.10, minor_extent=0.06, yaw=0.0
        )
    )
    _, caption = annotate(
        blank(), (far,), CAMERA, WIDE, SURFACE, RENDER, at_nanos=1_000_000_000
    )
    assert "off frame" in caption.lower() or "0 drawn" in caption.lower()


def test_a_frame_of_the_wrong_shape_is_refused() -> None:
    """The optics describe one render size."""
    pytest.importorskip("cv2")
    import numpy as np

    with pytest.raises(DebugViewError, match="render"):
        annotate(
            np.zeros((10, 10, 3), dtype=np.uint8),
            (a_record(),),
            CAMERA,
            WIDE,
            SURFACE,
            RENDER,
            at_nanos=0,
        )


def test_the_published_encoder_is_not_reachable_from_here() -> None:
    """The published encoder is not reachable from here.

    The demo and still paths keep their flat-gray guarantee because nothing
    here can write through them.
    """
    source = (ROOT / "src" / "clave" / "tracker" / "debug_view.py").read_text()
    assert "clave.demo" not in source
    assert "open_recorder" not in source
