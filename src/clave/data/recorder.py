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
from clave.data.expert import decide
from clave.world import arm as armmod
from clave.world import belt, config, scene

ARM_GAIN = 0.35
"""How much of each solved inverse kinematics step to apply.

Low enough that the arm tracks the expert smoothly rather than snapping between
targets as objects enter and leave the reachable window.
"""


def _ensure_software_rendering() -> None:
    """Select the CPU rendering backend when none was chosen.

    Setting this after MuJoCo has initialized its GL context has no effect, so
    it happens before the first import inside this module's functions.
    """
    os.environ.setdefault("MUJOCO_GL", "osmesa")


def _boxes_from_segmentation(
    model: Any, segmentation: Any
) -> dict[str, tuple[int, int, int, int]]:
    """Derive exact pixel bounds per object from a segmentation render.

    MuJoCo renders geometry ids per pixel, so the bounds are ground truth rather
    than a projection estimate, and an object absent from the render is simply
    absent from the result.

    Args:
        model: The compiled model, used to map geometry ids to names.
        segmentation: The segmentation buffer, height by width by two.

    Returns:
        Object body name to pixel bounds as (x_min, y_min, x_max, y_max).
    """
    import mujoco
    import numpy as np

    geom_ids = segmentation[:, :, 0]
    boxes: dict[str, tuple[int, int, int, int]] = {}
    for geom_id in np.unique(geom_ids):
        if geom_id < 0 or geom_id >= model.ngeom:
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(geom_id))
        if name is None or not name.startswith("object_"):
            continue
        rows, columns = np.where(geom_ids == geom_id)
        boxes[name.removesuffix("_geom")] = (
            int(columns.min()),
            int(rows.min()),
            int(columns.max()),
            int(rows.max()),
        )
    return boxes


def _labels_for(
    model: Any,
    data: Any,
    conveyor: belt.Conveyor,
    half_window: float,
    boxes: dict[str, tuple[int, int, int, int]],
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
                in_reachable_window=belt.within_reach(
                    (position[0], position[1], position[2]), conveyor.plan
                ),
                bbox=boxes.get(item.name),
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

    indices = armmod.locate(model)
    renderer = mujoco.Renderer(model, height=height, width=width)
    segmenter = mujoco.Renderer(model, height=height, width=width)
    segmenter.enable_segmentation_rendering()
    examples: list[Example] = []
    next_capture = 0.0
    half_window = conveyor.report.window_length / 2.0
    for _ in range(int(seconds / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)

        # Drive the arm toward whatever the scripted expert would pick. Without
        # this the manipulator never moves, its joint angles are constant, and
        # the proprioception recorded below carries no information at all.
        labels_now = _labels_for(model, data, conveyor, half_window, {})
        chosen = decide(labels_now, half_window)
        if chosen is not None:
            armmod.step_toward(
                model, data, indices, np.array(chosen.position), gain=ARM_GAIN
            )

        if data.time < next_capture:
            continue
        renderer.update_scene(data, camera="overhead")
        segmenter.update_scene(data, camera="overhead")
        boxes = _boxes_from_segmentation(model, segmenter.render())
        examples.append(
            Example(
                frame=renderer.render().astype(np.uint8),
                labels=_labels_for(model, data, conveyor, half_window, boxes),
                simulated_time=float(data.time),
                seed=seed,
                config_digest=config_digest,
                origin=Origin.SIMULATED,
                arm_joints=tuple(
                    float(angle)
                    for angle in armmod.joint_positions(model, data, indices)
                ),
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
