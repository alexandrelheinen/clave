"""Assemble the simulated sorting line.

The scene is built programmatically rather than written as a static MJCF file.
Bin count follows the taxonomy, object placement follows a seed, and belt
geometry follows configuration, none of which a fixed XML can express.

The manipulator is attached from a pinned submodule, which is FRET's convention.
CLAVE does not vendor meshes.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from clave.world.config import require, require_range
from clave.world.objects import ObjectSpec, channels, parse

ARM_MODEL = Path(
    "third_party/robotis_mujoco_menagerie/robotis_open_manipulator_x/"
    "open_manipulator_x.xml"
)

PARKED_Z = -5.0
"""Where pooled objects wait before they are spawned, well below the floor."""


@dataclass(frozen=True)
class BeltGeometry:
    """The belt's extent and how fast it runs.

    Attributes:
        length: Belt length along the travel axis, in meters.
        width: Belt width, in meters.
        surface_height: Height of the belt surface above the floor, in meters.
        speed: Belt speed in meters per second, resolved from its range.
    """

    length: float
    width: float
    surface_height: float
    speed: float


@dataclass(frozen=True)
class SceneLayout:
    """Everything the belt drive and the reachability report need.

    Attributes:
        belt: Belt geometry and speed.
        arm_base: Where the manipulator stands, in meters.
        reach_radius: The manipulator's reachable radius, in meters.
        channels: Channel identifiers, one bin each.
        objects: The object set the pool draws from.
        pool_size: How many object bodies exist.
        timestep: Simulation timestep in seconds.
    """

    belt: BeltGeometry
    arm_base: tuple[float, float, float]
    reach_radius: float
    channels: tuple[str, ...]
    objects: tuple[ObjectSpec, ...]
    pool_size: int
    timestep: float


def _arm_spec(root: Path) -> Any:
    """Load the manipulator from the pinned submodule.

    Args:
        root: Repository root.

    Returns:
        The manipulator spec.

    Raises:
        FileNotFoundError: If the submodule is not checked out, naming the
            command that fixes it.
    """
    import mujoco

    path = root / ARM_MODEL
    if not path.is_file():
        raise FileNotFoundError(
            f"{ARM_MODEL} is missing. The ROBOTIS menagerie submodule is not "
            f"checked out. Run: git submodule update --init --recursive"
        )
    return mujoco.MjSpec.from_file(str(path))


def layout(raw: dict[str, Any], rng: np.random.Generator) -> SceneLayout:
    """Resolve configuration and randomization ranges into one layout.

    Args:
        raw: The parsed world configuration.
        rng: Generator used to resolve ranges.

    Returns:
        The resolved layout.

    Raises:
        WorldConfigError: If a required key is missing or a range is invalid.
    """
    physics = require(raw, "physics")
    belt_cfg = require(raw, "belt")
    arm_cfg = require(raw, "arm")
    spawn_cfg = require(raw, "spawn")
    specs = parse(require(raw, "objects"))

    belt = BeltGeometry(
        length=float(require(belt_cfg, "length_meters", "belt")),
        width=float(require(belt_cfg, "width_meters", "belt")),
        surface_height=float(require(belt_cfg, "surface_height_meters", "belt")),
        speed=require_range(belt_cfg, "speed_meters_per_second", "belt").sample(rng),
    )
    base = require(arm_cfg, "base_position_meters", "arm")
    return SceneLayout(
        belt=belt,
        arm_base=(float(base[0]), float(base[1]), float(base[2])),
        reach_radius=float(require(arm_cfg, "reach_radius_meters", "arm")),
        channels=channels(specs),
        objects=specs,
        pool_size=int(require(spawn_cfg, "pool_size", "spawn")),
        timestep=float(require(physics, "timestep_seconds", "physics")),
    )


def build(
    raw: dict[str, Any], rng: np.random.Generator, root: Path
) -> tuple[Any, Any, SceneLayout]:
    """Assemble the model.

    Args:
        raw: The parsed world configuration.
        rng: Generator used to resolve ranges and size pooled objects.
        root: Repository root, used to find the submodule.

    Returns:
        The compiled model, its data, and the resolved layout.

    Raises:
        FileNotFoundError: If the manipulator submodule is not checked out.
        WorldConfigError: If configuration is incomplete.
    """
    import mujoco

    plan = layout(raw, rng)
    bins_cfg = require(raw, "bins")
    spawn_cfg = require(raw, "spawn")
    camera_cfg = require(raw, "camera")

    spec = mujoco.MjSpec()
    spec.option.timestep = plan.timestep
    # Adopt the manipulator's contact settings rather than the defaults, since
    # its grasp behavior was tuned with them.
    spec.option.impratio = 10.0
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC

    world = spec.worldbody
    world.add_light(pos=[0.0, 0.0, 2.0], dir=[0.0, 0.0, -1.0])

    world.add_geom(
        name="floor",
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        size=[5.0, 5.0, 0.1],
        pos=[0.0, 0.0, 0.0],
    )

    half = [plan.belt.length / 2.0, plan.belt.width / 2.0, 0.02]
    world.add_geom(
        name="belt",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=half,
        pos=[0.0, 0.0, plan.belt.surface_height - half[2]],
        rgba=[0.25, 0.25, 0.28, 1.0],
    )

    bin_size = [float(v) for v in require(bins_cfg, "size_meters", "bins")]
    spacing = float(require(bins_cfg, "spacing_meters", "bins"))
    offset = float(require(bins_cfg, "offset_from_belt_meters", "bins"))
    first = -spacing * (len(plan.channels) - 1) / 2.0
    for index, channel in enumerate(plan.channels):
        world.add_geom(
            name=f"bin_{channel}",
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=bin_size,
            pos=[first + index * spacing, offset, bin_size[2]],
            rgba=[0.15, 0.45, 0.65, 1.0],
        )

    drop = require_range(spawn_cfg, "drop_height_meters", "spawn")
    for index in range(plan.pool_size):
        template = plan.objects[index % len(plan.objects)]
        body = world.add_body(
            name=f"object_{index}",
            pos=[0.0, 0.0, PARKED_Z - index],
        )
        body.add_freejoint()
        size_a = template.size[0].sample(rng)
        size_b = template.size[1].sample(rng)
        density = template.density.sample(rng)
        if template.shape == "cylinder":
            body.add_geom(
                name=f"object_{index}_geom",
                type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                size=[size_a, size_b, 0.0],
                density=density,
                rgba=[0.8, 0.6, 0.2, 1.0],
            )
        else:
            body.add_geom(
                name=f"object_{index}_geom",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                size=[size_a, size_a, size_b],
                density=density,
                rgba=[0.7, 0.5, 0.3, 1.0],
            )

    height = require_range(camera_cfg, "height_above_belt_meters", "camera")
    world.add_camera(
        name="overhead",
        pos=[0.0, 0.0, plan.belt.surface_height + height.sample(rng)],
        quat=[0.0, 1.0, 0.0, 0.0],
        fovy=require_range(camera_cfg, "fovy_degrees", "camera").sample(rng),
    )

    frame = world.add_frame()
    frame.pos = list(plan.arm_base)
    with warnings.catch_warnings():
        # The manipulator declares its own impratio and cone; this scene already
        # adopted both above, so the conflict notice carries no information.
        warnings.simplefilter("ignore")
        spec.attach(_arm_spec(root), prefix="arm_", frame=frame)

    model = spec.compile()
    data = mujoco.MjData(model)
    _ = drop
    return model, data, plan
