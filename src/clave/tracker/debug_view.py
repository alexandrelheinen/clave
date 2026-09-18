"""Drawing what the tracker believes, where it believes it.

This is the one place in CLAVE where something is drawn onto a rendered frame,
and it is quarantined on purpose.

`agents/claude.md` forbids post-processed overlays on captured output, and a
published figure may carry geometry and never an overlay. Both hold. A
published figure argues something to a reader who cannot run the code, so
anything drawn on it is a claim they cannot check. A debug view argues
nothing: it is read by somebody with the records open beside it, and its whole
job is to show which number belongs to which place. The separation is
mechanical rather than a convention: nothing
here imports the published encoder, a test asserts that, and the flat-gray tests
guarding `demo` and `still` are untouched.

Two rules keep it honest. Every value drawn is read from a `WasteObject` and
never computed for display, so the view cannot show something the system does
not know. And every field of the record is drawn, because choosing which
properties are interesting is choosing which defect to miss: the integration bug
that motivated this view was two tracks over one object, visible only in the
`evidence` set.
"""

from __future__ import annotations

import colorsys
import math
from typing import Any

from clave.errors import ClaveError
from clave.tracker.belt_frame import NadirOptics
from clave.tracker.track import WasteObject

CAPTION = "DEBUG RENDER, tracker only, not the runtime loop and not a figure"
"""What every frame says about itself.

A frame that does not say what it is will eventually be pasted into something
that does not either.
"""


class DebugViewError(ClaveError):
    """A frame and the optics describing it disagree."""


def to_pixels(
    x: float,
    y: float,
    camera: tuple[float, float, float],
    optics: NadirOptics,
    surface_height: float,
    render: tuple[int, int],
) -> tuple[float, float]:
    """Return where a belt point falls in the frame, in pixels.

    The inverse of `clave.tracker.adapters.detection.to_belt`, through the same
    optics. Using a different scale factor here would put every box slightly off
    its object, consistently, which is the kind of wrong that looks right.

    Args:
        x: Along belt travel, in belt frame meters.
        y: Across the belt, in belt frame meters.
        camera: Where the camera stands, in belt frame meters.
        optics: What its pixels are worth.
        surface_height: Height of the surface being imaged.
        render: The frame size as `(width, height)` in pixels.

    Returns:
        The point as `(column, row)`.

    Raises:
        DebugViewError: If the camera does not stand above the surface.
    """
    from clave.tracker.belt_frame import FrameError

    width, height = render
    try:
        metres = optics.meters_per_pixel(surface_height, height)
    except FrameError as error:
        raise DebugViewError(str(error)) from error
    return (
        width / 2.0 + (x - camera[0]) / metres,
        height / 2.0 - (y - camera[1]) / metres,
    )


def colour_for(track_id: int) -> tuple[int, int, int]:
    """Return a stable colour for one track, as blue, green, red.

    Derived from the identity rather than assigned in order, so a track keeps
    its colour when another retires, and the footprint and the listing row
    correspond without a reader counting.

    Args:
        track_id: The track's identity.

    Returns:
        The colour, in the channel order OpenCV writes.
    """
    # The golden ratio spreads successive integers around the hue circle, so
    # neighbouring track ids never come out as neighbouring colours.
    hue = (track_id * 0.618033988749895) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return (int(blue * 255), int(green * 255), int(red * 255))


def described_fields(record: WasteObject) -> dict[str, str]:
    """Return every property of one record, rendered for reading.

    Every field the record stores and every one it computes. The record's own
    shape is the contract, so a field added to `WasteObject` and not here fails
    a test rather than quietly going unseen.

    Args:
        record: The settled record.

    Returns:
        Field name to the string drawn for it.
    """
    simulated = record.simulated

    def mark(name: str, text: str) -> str:
        """Flag a value the simulator supplied rather than a sensor measured."""
        return f"{text}   [SIMULATED]" if name in simulated else text

    box = record.footprint
    orientation = (
        f"yaw {box.yaw:+.3f} rad" if box.oriented else "unoriented, no yaw claimed"
    )
    return {
        "track_id": str(record.track_id),
        "observed_at_nanos": f"{record.observed_at_nanos} ns",
        "valid_until_nanos": (
            f"{record.valid_until_nanos} ns "
            f"(+{(record.valid_until_nanos - record.observed_at_nanos) / 1e9:.2f} s)"
        ),
        "footprint": (
            f"centre ({box.center[0]:.3f}, {box.center[1]:.3f}, "
            f"{box.center[2]:.3f}) m  "
            f"major {box.major_extent:.3f} m  minor {box.minor_extent:.3f} m  "
            f"{orientation}"
        ),
        "height": (
            f"{record.height:.3f} m" if record.height is not None else "unmeasured"
        ),
        "material": mark(
            "material", f"{record.material} at {record.material_confidence:.3f}"
        ),
        "material_confidence": f"{record.material_confidence:.3f}",
        "density": (
            mark(
                "density",
                f"{record.density.low:.3f} to {record.density.high:.3f} kg/m3",
            )
            if record.density is not None
            else "no class density, nothing in the world carries this class"
        ),
        "mass": (
            mark("mass", f"{record.mass.low:.3f} to {record.mass.high:.3f} kg")
            if record.mass is not None
            else "unknown, no density or no height"
        ),
        "codes": ", ".join(record.codes) if record.codes else "none read",
        "evidence": (
            ", ".join(sorted(role.value for role in record.evidence))
            if record.evidence
            else "none"
        ),
        "simulated": (
            ", ".join(sorted(record.simulated)) if record.simulated else "nothing"
        ),
        "grasp_point": (
            f"({record.grasp_point[0]:.3f}, {record.grasp_point[1]:.3f}, "
            f"{record.grasp_point[2]:.3f}) m"
        ),
        "grasp_axis": f"{record.grasp_axis:+.3f} rad",
        "grasp_width": f"{record.grasp_width:.3f} m",
        "surface_normal": (
            f"({record.surface_normal[0]:.1f}, {record.surface_normal[1]:.1f}, "
            f"{record.surface_normal[2]:.1f})"
        ),
    }


def annotate(
    frame: Any,
    records: tuple[WasteObject, ...],
    camera: tuple[float, float, float],
    optics: NadirOptics,
    surface_height: float,
    render: tuple[int, int],
    at_nanos: int,
    beside: bool = False,
    only_drawn: bool = False,
) -> tuple[Any, str]:
    """Return a copy of the frame with every record drawn beside it.

    The frame is copied rather than drawn into, because the array handed in is
    what the simulator rendered and the published encoders must never receive
    one already marked.

    Args:
        frame: The rendered frame, height by width by three.
        records: What the tracker settled at this instant.
        camera: Where the camera stands, in belt frame meters.
        optics: What its pixels are worth.
        surface_height: Height of the surface the records sit on.
        render: The frame size as `(width, height)` in pixels.
        at_nanos: The instant the records describe.
        beside: Put the listing to the right of the image rather than under it.
            Stacked is the readable layout for one frame; beside is the one that
            fits a video, where a listing taller than the screen is no listing
            at all.
        only_drawn: List only the records whose footprint landed on the frame.
            A track propagated off the belt has nothing to point at, so in a
            video its entry is noise; auditing one frame, it is not, which is
            why this is a choice rather than a rule.

    Returns:
        The annotated frame, and a one-line summary naming how many tracks were
        open and how many were drawn.

    Raises:
        DebugViewError: If the frame does not match the render size given.
    """
    import cv2
    import numpy as np

    width, height = render
    if frame.shape[0] != height or frame.shape[1] != width:
        raise DebugViewError(
            f"the frame is {frame.shape[1]} by {frame.shape[0]} and the render "
            f"size given is {width} by {height}"
        )

    on_frame = tuple(
        r for r in records if _lands_on_frame(r, camera, optics, surface_height, render)
    )
    listed = on_frame if only_drawn else records
    fields = len(described_fields(records[0])) if records else 0
    needed = 96 + (17 * fields + 26) * max(len(listed), 1)

    if beside:
        canvas = np.full((max(height, needed), width + 780, 3), 24, dtype=np.uint8)
    else:
        canvas = np.full((height + needed, max(width, 780), 3), 24, dtype=np.uint8)
    canvas[:height, :width] = frame

    drawn = 0
    for record in records:
        if _draw_footprint(cv2, canvas, record, camera, optics, surface_height, render):
            drawn += 1

    left = width + 12 if beside else 8
    top = 20 if beside else height + 20
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(
        canvas, CAPTION, (left, top), font, 0.42, (200, 200, 200), 1, cv2.LINE_AA
    )

    off = len(records) - drawn
    summary = f"t={at_nanos / 1e9:.2f}s  {len(records)} tracks open, {drawn} drawn" + (
        f", {off} off frame" if off else ""
    )
    cv2.putText(
        canvas, summary, (left, top + 26), font, 0.42, (170, 220, 170), 1, cv2.LINE_AA
    )

    # Below both header lines, so the listing never lands on top of them.
    line = top + 60
    for record in listed:
        colour = colour_for(record.track_id)
        cv2.putText(
            canvas,
            f"track {record.track_id}",
            (left, line),
            font,
            0.5,
            colour,
            1,
            cv2.LINE_AA,
        )
        line += 20
        for name, shown in described_fields(record).items():
            cv2.putText(
                canvas,
                f"  {name:<20} {shown}",
                (left, line),
                font,
                0.38,
                (205, 205, 205),
                1,
                cv2.LINE_AA,
            )
            line += 17
        line += 6

    return canvas, f"{CAPTION} | {summary}"


def _lands_on_frame(
    record: WasteObject,
    camera: tuple[float, float, float],
    optics: NadirOptics,
    surface_height: float,
    render: tuple[int, int],
) -> bool:
    """Whether a record's footprint centre falls inside the frame."""
    width, height = render
    column, row = to_pixels(
        record.footprint.center[0],
        record.footprint.center[1],
        camera,
        optics,
        surface_height,
        render,
    )
    return 0 <= column <= width and 0 <= row <= height


def _draw_footprint(
    cv2: Any,
    canvas: Any,
    record: WasteObject,
    camera: tuple[float, float, float],
    optics: NadirOptics,
    surface_height: float,
    render: tuple[int, int],
) -> bool:
    """Draw one record's footprint, or report that it falls outside the frame.

    A track propagated past the belt has no pixel, and clamping it to the border
    would put a box where no object is.

    Returns:
        Whether it was drawn.
    """
    import numpy as np

    width, height = render
    box = record.footprint
    yaw = box.yaw if box.oriented else 0.0
    half_major, half_minor = box.major_extent / 2.0, box.minor_extent / 2.0
    corners = []
    for along, across in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        dx = along * half_major * math.cos(yaw) - across * half_minor * math.sin(yaw)
        dy = along * half_major * math.sin(yaw) + across * half_minor * math.cos(yaw)
        corners.append(
            to_pixels(
                box.center[0] + dx,
                box.center[1] + dy,
                camera,
                optics,
                surface_height,
                render,
            )
        )
    if not any(0 <= c <= width and 0 <= r <= height for c, r in corners):
        return False

    colour = colour_for(record.track_id)
    points = np.array([[int(c), int(r)] for c, r in corners], dtype=np.int32)
    # Dashed for an unoriented box, so a shape the record declined to orient is
    # not drawn as one it did.
    thickness = 2 if box.oriented else 1
    cv2.polylines(canvas, [points], True, colour, thickness, cv2.LINE_AA)
    label_c, label_r = to_pixels(
        box.center[0], box.center[1], camera, optics, surface_height, render
    )
    cv2.putText(
        canvas,
        f"{record.track_id}:{record.material}",
        (int(label_c) + 6, int(label_r) - 6),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        colour,
        1,
        cv2.LINE_AA,
    )
    return True
