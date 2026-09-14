"""Recording rollouts from the simulated world.

Stepping the world and capturing frames is mechanical. What matters is that
every captured frame carries the labels the world already holds, so the dataset
is labeled by construction rather than by a later pass.

Rendering runs offscreen on CPU through OSMesa, because this machine has no
usable accelerator. That costs roughly 52 milliseconds a frame at 320 by 240.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from clave.data.examples import Example, ObjectLabel, Origin, Rollout
from clave.world import belt, config, scene


def _ensure_software_rendering() -> None:
    """Select the CPU rendering backend when none was chosen.

    Setting this after MuJoCo has initialized its GL context has no effect, so
    it happens before the first import inside this module's functions.
    """
    os.environ.setdefault("MUJOCO_GL", "osmesa")


def _labels_for(
    model: Any, data: Any, conveyor: belt.Conveyor, half_window: float
) -> tuple[ObjectLabel, ...]:
    """Read every active object's label straight from the world."""
    import mujoco

    labels: list[ObjectLabel] = []
    for item in conveyor.active:
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
        address = model.jnt_qposadr[model.body_jntadr[body]]
        position = tuple(float(value) for value in data.qpos[address : address + 3])
        labels.append(
            ObjectLabel(
                object_id=item.index,
                material_class=item.material_class,
                channel=item.channel,
                position=(position[0], position[1], position[2]),
                in_reachable_window=abs(position[0]) <= half_window,
            )
        )
    return tuple(labels)


def record(
    root: Path,
    seed: int,
    seconds: float,
    capture_interval_seconds: float,
    height: int,
    width: int,
    rollout_id: str,
) -> Rollout:
    """Run the world once and capture labeled frames.

    Args:
        root: Repository root, used to find the configuration and the submodule.
        seed: Seed controlling belt speed, placement and spawn timing.
        seconds: Simulated seconds to run.
        capture_interval_seconds: Simulated seconds between captures.
        height: Frame height in pixels.
        width: Frame width in pixels.
        rollout_id: Identity for this rollout within a dataset.

    Returns:
        The rollout, with one example per captured frame.
    """
    _ensure_software_rendering()
    import mujoco

    raw = config.load(root / "configs" / "world" / "sorting_line.yml")
    config_digest = _config_digest(root)
    rng = np.random.default_rng(seed)
    model, data, plan = scene.build(raw, rng, root)
    spawn = config.require(raw, "spawn")
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(config.require(spawn, "entry_margin_meters", "spawn")),
    )
    half_window = conveyor.report.window_length / 2.0

    renderer = mujoco.Renderer(model, height=height, width=width)
    examples: list[Example] = []
    next_capture = 0.0
    for _ in range(int(seconds / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        if data.time < next_capture:
            continue
        renderer.update_scene(data, camera="overhead")
        examples.append(
            Example(
                frame=renderer.render().astype(np.uint8),
                labels=_labels_for(model, data, conveyor, half_window),
                simulated_time=float(data.time),
                seed=seed,
                config_digest=config_digest,
                origin=Origin.SIMULATED,
            )
        )
        next_capture = data.time + capture_interval_seconds
    return Rollout(rollout_id=rollout_id, seed=seed, examples=tuple(examples))


def _config_digest(root: Path) -> str:
    """Digest the world configuration that produced a rollout.

    Two datasets recorded under different world configurations are different
    datasets even at the same seed, so the digest travels with every example.
    """
    from clave.corpus.artifacts import digest_of

    return digest_of(root / "configs" / "world" / "sorting_line.yml")
