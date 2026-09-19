"""Driving the tracker over a rollout and showing what it decided.

This is a diagnostic, not a demonstration. It drives `clave.tracker` directly
rather than through `clave.runtime.loop`, because the tracker is deliberately
not wired into the loop yet.

What a reader sees is the world, with a grasp marker standing where the
tracker believes each object is and turned the way a jaw would have to close
on it. The markers are scene geometry rather than paint on a frame, so MuJoCo
shades and occludes them like any other solid, and nothing touches the image
after the renderer is finished with it.

Two cameras run and they never mix. The tracker segments the nadir gate,
because that is the sensor the line actually carries. The human watches an
oblique view configured in `configs/debug/tracker.yml`, because a grasp
pose seen from straight above has no approach to read.

A window opens when a display is available and the run writes its artifacts
either way, because a machine with no display is the ordinary case for this
project and refusing to run on one would make the view useless exactly where
it is needed most.
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
from clave.tracker.evidence import Evidence, GroundTruth, Role
from clave.tracker.fusion import FusionSettings
from clave.tracker.intake import Deployment, Intake
from clave.tracker.listing import described_fields
from clave.tracker.markers import draw, markers_for
from clave.tracker.sensors import load_sensors, require_role
from clave.tracker.track import Tracker
from clave.world import belt, config, scene
from clave.world.effector import Effector

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
        drawn: Markers standing in the world on the final frame.
        geoms: Marker geoms the final frame carried, which is more than
            `drawn` because a jaw is a shaft and two pads.
        frames_written: Frames written.
        output: Where they went.
        video_path: The playable file, or None when none was asked for or no
            encoder was found.
        windowed: Whether a live window was opened.
        reason: Why no window was opened, when none was.
    """

    captures: int
    tracks: int
    drawn: int
    geoms: int
    frames_written: int
    output: Path
    video_path: Path | None
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
    video: bool = False,
    fps: int = 4,
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
        video: Encode the rendered frames into a playable file beside them.
            A machine with no `ffmpeg` runs anyway and says none was written.
        fps: Playback rate of that file.

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
    effector = Effector.load(raw)
    view = config.require(
        config.load(root / "configs" / "debug" / "tracker.yml"), "view"
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
    masks = mujoco.Renderer(model, height=height, width=width)
    masks.enable_segmentation_rendering()

    watching = mujoco.Renderer(
        model,
        height=int(config.require(view, "height", "view")),
        width=int(config.require(view, "width", "view")),
    )
    eye = mujoco.MjvCamera()
    eye.azimuth = float(config.require(view, "azimuth_degrees", "view"))
    eye.elevation = float(config.require(view, "elevation_degrees", "view"))
    eye.distance = float(config.require(view, "distance_meters", "view"))
    eye.lookat[:] = _lookat(view)

    out.mkdir(parents=True, exist_ok=True)
    opened, reason = _open_window(cv2, window)

    captures = written = drawn = geoms = 0
    believed = out / "records.txt"
    believed.write_text("")
    recorder = _recorder(view, out, fps, capture_interval) if video else None
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

            records = tracker.settle(at_nanos=now)
            standing = markers_for(records, effector, surface)

            # The markers go in before the render and live only until the next
            # update_scene, so they reach this view and no other. The gate the
            # tracker reads was rendered above and carries none of them.
            watching.update_scene(data, camera=eye)
            geoms = draw(watching.scene, standing)
            drawn = len(standing)
            canvas = watching.render()

            cv2.imwrite(
                str(out / f"frame_{captures:04d}.png"),
                cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR),
            )
            written += 1
            if recorder is not None:
                recorder.write(canvas)
            _write_beliefs(believed, captures, now, records)
            if opened:
                cv2.imshow(
                    "clave tracker debug", cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
                )
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    finally:
        watching.close()
        masks.close()
        if recorder is not None:
            recorder.close()
        if opened:
            cv2.destroyAllWindows()

    return DebugRunReport(
        captures=captures,
        tracks=len(tracker.settle(at_nanos=int(data.time * NANOS_PER_SECOND))),
        drawn=drawn,
        geoms=geoms,
        frames_written=written,
        output=out,
        video_path=None if recorder is None else recorder.settings.path,
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


def _recorder(view: dict[str, Any], out: Path, fps: int, interval: float) -> Any:
    """Start recording the view, or report that no encoder is installed.

    The recorder reads the same camera block the still frames render from, so
    the two cannot show the world from two different angles.

    Args:
        view: The `view` block of the debug configuration.
        out: Where the run writes.
        fps: Playback rate.
        interval: Simulated seconds between captures.

    Returns:
        The recorder, or None when `ffmpeg` is absent.
    """
    from clave.demo.video import VideoSettings, open_recorder

    return open_recorder(
        VideoSettings(
            path=out / "tracker-debug.mp4",
            width=int(config.require(view, "width", "view")),
            height=int(config.require(view, "height", "view")),
            frames_per_second=fps,
            interval_seconds=interval,
            azimuth=float(config.require(view, "azimuth_degrees", "view")),
            elevation=float(config.require(view, "elevation_degrees", "view")),
            distance=float(config.require(view, "distance_meters", "view")),
            lookat=_lookat(view),
        )
    )


def _lookat(view: dict[str, Any]) -> tuple[float, float, float]:
    """Return what the camera points at, as three meters.

    Args:
        view: The `view` block of the debug configuration.

    Returns:
        The target.

    Raises:
        DebugRunError: If the key does not hold three numbers.
    """
    values = [float(value) for value in config.require(view, "lookat_meters", "view")]
    if len(values) != 3:
        raise DebugRunError(
            f"view.lookat_meters holds {len(values)} numbers, and a camera "
            f"target is three"
        )
    return values[0], values[1], values[2]


def _write_beliefs(path: Path, capture: int, at_nanos: int, records: Any) -> None:
    """Append what the tracker believed at one instant.

    The markers show where; this says what. Keeping the two apart is what lets
    the frame stay a render of the world with nothing written on it.

    Args:
        path: The listing file.
        capture: Which capture this is.
        at_nanos: The instant the records were settled at.
        records: The settled records.
    """
    lines = [f"# capture {capture:04d} at {at_nanos} ns, {len(records)} open"]
    for record in records:
        lines.append(f"track {record.track_id}")
        lines.extend(
            f"    {name}: {value}" for name, value in described_fields(record).items()
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n\n")
