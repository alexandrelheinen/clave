"""Capturing a still of the sorting world.

A still is a frame of a real rollout, chosen by when it happens rather than by
arranging anything: the world runs from a seed with the scripted expert driving
the arm, and the renderer is asked for a frame at a stated instant. Nothing is
drawn on it, composited into it or corrected afterwards. The encoder writes the
pixels the renderer produced.

The lighting and the camera come from the still's own file and are handed to
the world as an argument, so `configs/world/sorting_line.yml` is the file every
dataset, training run and benchmark reads and this changes none of it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from clave.errors import ClaveError

ENCODER = "ffmpeg"
"""Writes the PNG. No imaging library enters the wheel for one frame."""


ARM_GAIN = 1.0
"""How much of each solved step to command.

One, meaning the solved angles are commanded outright. The arm's own position
actuators already implement a proportional-derivative loop, so interpolating the
setpoint on top of them adds a second lag, and a target riding a belt at 0.31 m/s
exposes it: at 0.35 the tool settled 1.13 m behind the object it was following,
against 35 mm when the setpoint is commanded directly.

The previous arm hid this. It was light and its targets were nearly static at the
scale its workspace covered, so a fractional setpoint looked like smoothing
rather than lag.
"""


class StillError(ClaveError):
    """A still scenario is missing a key or cannot be rendered."""


@dataclass(frozen=True)
class StillCamera:
    """One point of view on the scene.

    Attributes:
        name: Used in the output file name.
        azimuth: Degrees around the scene, measured as MuJoCo measures it.
        elevation: Degrees above the horizon, negative looking down.
        distance: Meters from the point it looks at.
        lookat: What it points at, in world meters.
        fovy: Vertical field of view in degrees.
    """

    name: str
    azimuth: float
    elevation: float
    distance: float
    lookat: tuple[float, float, float]
    fovy: float


@dataclass(frozen=True)
class StillScenario:
    """What one still captures, and how it is lit.

    Attributes:
        name: The scenario's name.
        description: What the frame is meant to show.
        seed: Seed the rollout runs from.
        capture_at_seconds: Simulated instant the frame is taken at.
        width: Frame width in pixels.
        height: Frame height in pixels.
        lighting: Extra lights, headlight and background, passed to the world
            rather than written into it.
        annotations: Explanatory geometry the scene stands up for a figure,
            passed the same way and empty by default.
        cameras: The points of view to render.
    """

    name: str
    description: str
    seed: int
    capture_at_seconds: float
    width: int
    height: int
    lighting: dict[str, Any]
    annotations: dict[str, Any]
    cameras: tuple[StillCamera, ...]

    @classmethod
    def load(cls, path: Path) -> StillScenario:
        """Read a still scenario from YAML.

        Args:
            path: The scenario file.

        Returns:
            The scenario.

        Raises:
            StillError: If a key is absent or no camera is declared.
        """
        raw = yaml.safe_load(path.read_text())
        still = _require(raw, "still")
        cameras = _require(raw, "cameras")
        if not isinstance(cameras, list) or not cameras:
            raise StillError("the scenario declares no camera")
        return cls(
            name=str(_require(still, "name", "still")),
            description=str(_require(still, "description", "still")).strip(),
            seed=int(_require(still, "seed", "still")),
            capture_at_seconds=float(_require(still, "capture_at_seconds", "still")),
            width=int(_require(still, "width", "still")),
            height=int(_require(still, "height", "still")),
            lighting=dict(raw.get("lighting") or {}),
            annotations=dict(raw.get("annotations") or {}),
            cameras=tuple(_camera(entry) for entry in cameras),
        )


def _camera(entry: Any) -> StillCamera:
    """Read one camera."""
    name = str(_require(entry, "name", "cameras"))
    lookat = [float(v) for v in _require(entry, "lookat_meters", name)]
    if len(lookat) != 3:
        raise StillError(f"camera {name!r}: lookat_meters needs three numbers")
    return StillCamera(
        name=name,
        azimuth=float(_require(entry, "azimuth_degrees", name)),
        elevation=float(_require(entry, "elevation_degrees", name)),
        distance=float(_require(entry, "distance_meters", name)),
        lookat=(lookat[0], lookat[1], lookat[2]),
        fovy=float(_require(entry, "fovy_degrees", name)),
    )


def _require(mapping: Any, key: str, path: str = "") -> Any:
    """Read a key, failing with its location when it is absent.

    Args:
        mapping: The mapping to read from.
        key: The key required.
        path: Name of the parent, used in the error message.

    Returns:
        The value.

    Raises:
        StillError: If the key is absent.
    """
    if not isinstance(mapping, dict) or key not in mapping:
        where = f"{path}.{key}" if path else key
        raise StillError(f"required still key {where!r} is missing")
    return mapping[key]


def write_png(frame: Any, path: Path, width: int, height: int) -> None:
    """Write one rendered frame as a PNG.

    The frame goes to the encoder as raw `rgb24` and comes back as sRGB with no
    alpha, which is what the card plate expects. Nothing is drawn on it.

    Args:
        frame: The rendered frame, height by width by three bytes.
        path: Where the PNG goes.
        width: Frame width in pixels.
        height: Frame height in pixels.

    Raises:
        StillError: If the encoder is absent or refuses the frame.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                ENCODER,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{width}x{height}",
                "-i",
                "-",
                "-frames:v",
                "1",
                "-pix_fmt",
                "rgb24",
                str(path),
            ],
            input=np.ascontiguousarray(frame, dtype=np.uint8).tobytes(),
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as error:
        raise StillError(
            f"{ENCODER} is not installed, so no still can be written"
        ) from error
    except subprocess.CalledProcessError as error:
        raise StillError(f"{ENCODER} refused the frame: {error.stderr!r}") from error


def capture(root: Path, scenario: StillScenario, out: Path) -> list[Path]:
    """Run the rollout to its instant and render every camera.

    Args:
        root: Repository root.
        scenario: What to capture.
        out: Directory the PNGs go in.

    Returns:
        The files written, in camera order.
    """
    import os

    os.environ.setdefault("MUJOCO_GL", "osmesa")
    import mujoco

    from clave.data.examples import ObjectLabel
    from clave.data.expert import decide
    from clave.world import arm as armmod
    from clave.world import belt, config, scene

    raw = config.load(root / "configs" / "world" / "sorting_line.yml")
    rng = np.random.default_rng(scenario.seed)
    model, data, plan = scene.build(
        raw,
        rng,
        root,
        presentation=scenario.lighting,
        annotations=scenario.annotations,
    )
    spawn = config.require(raw, "spawn")
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(config.require(spawn, "entry_margin_meters", "spawn")),
    )
    indices = armmod.locate(model)
    half_window = conveyor.report.window_length / 2.0

    for _ in range(int(scenario.capture_at_seconds / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        labels = []
        for item in conveyor.active:
            body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
            address = model.jnt_qposadr[model.body_jntadr[body]]
            raw_position = data.qpos[address : address + 3]
            position = (
                float(raw_position[0]),
                float(raw_position[1]),
                float(raw_position[2]),
            )
            labels.append(
                ObjectLabel(
                    object_id=item.index,
                    material_class=item.material_class,
                    channel=item.channel,
                    position=position,
                    in_reachable_window=belt.within_reach(position, plan),
                )
            )
        chosen = decide(tuple(labels), half_window)
        if chosen is not None:
            armmod.step_toward(
                model, data, indices, np.array(chosen.position), gain=ARM_GAIN
            )

    renderer = mujoco.Renderer(model, height=scenario.height, width=scenario.width)
    written: list[Path] = []
    for camera in scenario.cameras:
        view = mujoco.MjvCamera()
        view.azimuth = camera.azimuth
        view.elevation = camera.elevation
        view.distance = camera.distance
        view.lookat[:] = camera.lookat
        model.vis.global_.fovy = camera.fovy
        renderer.update_scene(data, camera=view)
        path = out / f"{scenario.name}-{camera.name}.png"
        write_png(renderer.render(), path, scenario.width, scenario.height)
        written.append(path)
    return written
