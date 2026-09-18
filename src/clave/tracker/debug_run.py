"""Driving the tracker over a rollout and showing what it decided.

This is a diagnostic, not a demonstration. It drives `clave.tracker` directly
rather than through `clave.runtime.loop`, because the tracker is deliberately
not wired into the loop yet, and every frame it writes says so.

A window opens when a display is available and the run writes its artifact
either way, because a machine with no display is the ordinary case for this
project and refusing to run on one would make the view useless exactly where it
is needed most.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clave.errors import ClaveError
from clave.tracker.adapters.detection import detections_from_masks
from clave.tracker.adapters.render import segment_masks
from clave.tracker.association import SimulatorIdentity
from clave.tracker.codes import load_catalog, resolver_for
from clave.tracker.debug_view import annotate
from clave.tracker.evidence import Evidence, GroundTruth, Role
from clave.tracker.fusion import FusionSettings
from clave.tracker.intake import Deployment, Intake
from clave.tracker.sensors import load_sensors, require_role
from clave.tracker.track import Tracker
from clave.world import belt, config, scene

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the instants an observation carries."""


class DebugRunError(ClaveError):
    """The debug run cannot be set up from this configuration."""


@dataclass(frozen=True)
class DebugRunReport:
    """What one debug run did.

    Attributes:
        captures: Frames the tracker was shown.
        tracks: Tracks open when it finished.
        drawn: Records drawn on the final frame.
        frames_written: Annotated frames written.
        output: Where they went.
        windowed: Whether a live window was opened.
        reason: Why no window was opened, when none was.
    """

    captures: int
    tracks: int
    drawn: int
    frames_written: int
    output: Path
    windowed: bool
    reason: str | None = None


def run(
    root: Path,
    out: Path,
    seconds: float = 14.0,
    seed: int = 0,
    capture_interval: float = 0.5,
    render: tuple[int, int] = (640, 480),
    window: bool = True,
) -> DebugRunReport:
    """Drive the tracker over one rollout, annotating every capture.

    Args:
        root: Repository root.
        out: Directory the annotated frames go to. Its own, never the one the
            published figures use.
        seconds: Simulated seconds to run.
        seed: Seed controlling belt speed, placement and spawn timing.
        capture_interval: Simulated seconds between captures.
        render: Frame size as `(width, height)` in pixels.
        window: Open a live window when a display is available.

    Returns:
        The report.

    Raises:
        DebugRunError: If the world declares no detection camera.
    """
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    import cv2
    import mujoco
    import numpy as np

    from clave.tracker.sensors import SensorError

    raw = config.load(root / "configs" / "world" / "sorting_line.yml")
    sensors = load_sensors(raw)
    try:
        wide = require_role(sensors, Role.DETECTION)
    except SensorError as error:
        raise DebugRunError(str(error)) from error

    surface = float(
        config.require(config.require(raw, "belt"), "surface_height_meters", "belt")
    )
    grasp = float(
        config.require(config.require(raw, "arm"), "max_grasp_width_meters", "arm")
    )

    model, data, plan = scene.build(raw, np.random.default_rng(seed), root)
    spawn = config.require(raw, "spawn")
    conveyor = belt.Conveyor(
        plan,
        np.random.default_rng(seed),
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(config.require(spawn, "entry_margin_meters", "spawn")),
    )

    tracker = Tracker(
        intake=Intake(Deployment.SIMULATED, sensors),
        associator=SimulatorIdentity(),
        settings=FusionSettings.load(
            root / "configs" / "perception" / "fusion.yml",
            root / "configs" / "world" / "sorting_line.yml",
        ),
        belt_speed=plan.belt.speed,
        window_exit=belt.window_exit(plan) or 1.034,
        unmeasured_extent=grasp,
        resolve=resolver_for(
            load_catalog(root / "configs" / "perception" / "packaging.yml")
        ),
    )

    width, height = render
    colour = mujoco.Renderer(model, height=height, width=width)
    masks = mujoco.Renderer(model, height=height, width=width)
    masks.enable_segmentation_rendering()

    out.mkdir(parents=True, exist_ok=True)
    opened, reason = _open_window(cv2, window)

    captures = written = drawn = 0
    next_capture = 0.0
    try:
        for _ in range(int(seconds / plan.timestep)):
            mujoco.mj_step(model, data)
            conveyor.step(model, data)
            if data.time < next_capture:
                continue
            next_capture = data.time + capture_interval
            captures += 1
            now = int(data.time * NANOS_PER_SECOND)

            masks.update_scene(data, camera=wide.source_id)
            found = segment_masks(model, masks.render())
            if found:
                for reading in detections_from_masks(
                    found,
                    source_id=wide.source_id,
                    observed_at_nanos=now,
                    camera=wide.position,
                    optics=wide.optics,
                    surface_height=surface + 0.05,
                    render=render,
                    belt_surface=surface,
                ):
                    tracker.observe(reading, at_nanos=now)
            for item in conveyor.active:
                body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
                address = model.jnt_qposadr[model.body_jntadr[body]]
                position = tuple(float(v) for v in data.qpos[address : address + 3])
                tracker.observe(
                    Evidence(
                        source_id="simulator",
                        role=Role.GROUND_TRUTH,
                        observed_at_nanos=now,
                        confidence=1.0,
                        payload=GroundTruth(
                            object_id=item.index,
                            material_class=item.material_class,
                            position=(position[0], position[1], position[2]),
                        ),
                    ),
                    at_nanos=now,
                )

            colour.update_scene(data, camera=wide.source_id)
            records = tracker.settle(at_nanos=now)
            canvas, summary = annotate(
                colour.render(),
                records,
                wide.position,
                wide.optics,
                surface + 0.05,
                render,
                at_nanos=now,
            )
            drawn = summary.count("drawn") and int(
                summary.split(" tracks open, ")[1].split(" ")[0]
            )
            cv2.imwrite(
                str(out / f"frame_{captures:04d}.png"),
                cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR),
            )
            written += 1
            if opened:
                cv2.imshow(
                    "clave tracker debug", cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
                )
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    finally:
        colour.close()
        masks.close()
        if opened:
            cv2.destroyAllWindows()

    return DebugRunReport(
        captures=captures,
        tracks=len(tracker.settle(at_nanos=int(data.time * NANOS_PER_SECOND))),
        drawn=drawn,
        frames_written=written,
        output=out,
        windowed=opened,
        reason=reason,
    )


def _open_window(cv2: Any, wanted: bool) -> tuple[bool, str | None]:
    """Open a live window, or say why there is none.

    A machine with no display is the ordinary case here, so this reports rather
    than raises: the artifact is the point and the window is a convenience.
    """
    if not wanted:
        return False, "not asked for"
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False, "no display is attached"
    try:
        cv2.namedWindow("clave tracker debug", cv2.WINDOW_NORMAL)
    except Exception as error:  # noqa: BLE001 - any GUI failure is the same answer
        return False, f"this OpenCV build cannot open a window ({error})"
    return True, None
