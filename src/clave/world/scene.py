"""Assemble the simulated sorting line.

The scene is built programmatically rather than written as a static MJCF file.
Bin count follows the taxonomy, object placement follows a seed, and belt
geometry follows configuration, none of which a fixed XML can express.

The manipulator is attached from a pinned submodule, which is FRET's convention.
CLAVE does not vendor meshes.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from clave.world.config import require, require_range
from clave.world.objects import ObjectSpec, channels, parse

ARM_MODEL = Path(
    "third_party/robotis_mujoco_menagerie/robotis_open_manipulator_x/"
    "open_manipulator_x.xml"
)

PARKED_Z = 0.05
"""Height at which pooled objects wait before they are spawned.

They rest on the floor well to the side of the belt rather than hanging beneath
it. A MuJoCo plane collides from above only, so a body parked below the floor
falls forever and eventually drives the solver to a NaN. v0.6.0 worked around
that by having the conveyor pin every parked slot on each step, which left the
scene stable only while a conveyor happened to be stepping it: building the
world and stepping it directly, as the arm controller does, reproduced the
instability. Parking above the floor makes the scene stable on its own.
"""

PARKED_X = 3.0
"""How far to the side pooled objects wait, clear of the belt and the camera."""

OFFSCREEN_WIDTH = 1920
"""Widest frame any renderer attached to this model can produce."""

OFFSCREEN_HEIGHT = 1080
"""Tallest frame any renderer attached to this model can produce."""


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
        dressed: Whether the warehouse scene dressing was found and used. It
            is reported rather than assumed, because the assets are generated
            from a submodule and a clone that has not run the importer gets a
            plain floor. Nothing the simulation measures depends on it.
    """

    belt: BeltGeometry
    arm_base: tuple[float, float, float]
    reach_radius: float
    channels: tuple[str, ...]
    objects: tuple[ObjectSpec, ...]
    pool_size: int
    timestep: float
    dressed: bool = False


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
        WorldConfigError: If a required key is missing, a range is invalid, or
            an object can be drawn wider than the gripper opens.
    """
    physics = require(raw, "physics")
    belt_cfg = require(raw, "belt")
    arm_cfg = require(raw, "arm")
    spawn_cfg = require(raw, "spawn")
    specs = parse(
        require(raw, "objects"),
        float(require(arm_cfg, "max_grasp_width_meters", "arm")),
    )

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


WAREHOUSE_ASSETS = Path("assets") / "warehouse"
"""Where `scripts/import_warehouse_assets.py` writes what it converts."""


def _dress(mujoco: Any, spec: Any, world: Any, raw: dict[str, Any], root: Path) -> bool:
    """Lay the floor and stand the scene dressing on it.

    The assets are converted from a pinned submodule and are not committed, so
    a clone that has not run the importer gets the plain floor instead. Nothing
    here touches the belt, the arm or the objects: every prop is static geometry
    standing clear of both, and the overhead camera the models see looks
    straight down at the belt rather than at any of it.

    Args:
        mujoco: The imported module.
        spec: The model spec, which owns textures and meshes.
        world: The worldbody being assembled.
        raw: The parsed world configuration.
        root: Repository root.

    Returns:
        Whether the warehouse assets were found and used.
    """
    assets = root / WAREHOUSE_ASSETS
    ground = assets / "textures" / "ground.png"
    if not ground.is_file():
        world.add_geom(
            name="floor",
            type=mujoco.mjtGeom.mjGEOM_PLANE,
            size=[5.0, 5.0, 0.1],
            pos=[0.0, 0.0, 0.0],
        )
        return False

    spec.add_texture(
        name="warehouse_ground",
        type=mujoco.mjtTexture.mjTEXTURE_2D,
        file=str(ground),
    )
    spec.add_material(
        name="warehouse_ground",
        textures=["", "warehouse_ground"],
        texrepeat=[6.0, 6.0],
    )
    world.add_geom(
        name="floor",
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        size=[5.0, 5.0, 0.1],
        pos=[0.0, 0.0, 0.0],
        material="warehouse_ground",
    )

    for index, prop in enumerate(require(raw, "environment").get("props", [])):
        name = str(require(prop, "mesh", "environment.props"))
        path = assets / "meshes" / name
        if not path.is_file():
            continue
        mesh_name = f"prop_{index}"
        spec.add_mesh(name=mesh_name, file=str(path))
        position = [float(v) for v in require(prop, "position_meters", name)]
        yaw = math.radians(float(require(prop, "yaw_degrees", name)))
        world.add_geom(
            name=mesh_name,
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname=mesh_name,
            pos=position,
            quat=[math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)],
            # Visual only. A prop that collided would be one more thing the
            # solver has to resolve every step for no gain, since none of them
            # is inside the workspace.
            contype=0,
            conaffinity=0,
        )
    return True


def _add_supports(
    mujoco: Any, world: Any, plan: SceneLayout, structure: dict[str, Any]
) -> None:
    """Stand the belt and the manipulator on something.

    Everything here is static geometry under equipment that was already resting
    on nothing, so no trajectory changes: the belt surface keeps its height, the
    arm keeps its base, and the legs sit below both. It exists because a scene
    shown to an audience should read as equipment rather than as boxes floating
    over a floor.

    The supports are placed clear of the effector's workspace. The pedestal is
    under the arm base and the legs are under the belt frame, neither of which
    the arm reaches into.

    Args:
        mujoco: The imported module.
        world: The worldbody being assembled.
        plan: The resolved layout, carrying the belt and the arm base.
        structure: The `structure` section of the configuration.
    """
    leg = float(require(structure, "leg_side_meters", "structure"))
    inset = float(require(structure, "leg_inset_meters", "structure"))
    frame_depth = float(require(structure, "frame_depth_meters", "structure"))
    steel = [0.32, 0.33, 0.36, 1.0]

    # The frame the belt rides on, spanning the legs just under the surface.
    frame_top = plan.belt.surface_height - 0.04
    frame_half = frame_depth / 2.0
    world.add_geom(
        name="belt_frame",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[plan.belt.length / 2.0, plan.belt.width / 2.0, frame_half],
        pos=[0.0, 0.0, frame_top - frame_half],
        rgba=steel,
    )

    # Four uprights, inset from the corners as a bench conveyor's are.
    leg_top = frame_top - frame_depth
    for x_sign in (-1.0, 1.0):
        for y_sign in (-1.0, 1.0):
            side = "front" if x_sign < 0 else "back"
            hand = "left" if y_sign < 0 else "right"
            world.add_geom(
                name=f"belt_leg_{side}_{hand}",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                size=[leg, leg, leg_top / 2.0],
                pos=[
                    x_sign * (plan.belt.length / 2.0 - inset),
                    y_sign * (plan.belt.width / 2.0 - inset),
                    leg_top / 2.0,
                ],
                rgba=steel,
            )

    # The pedestal the manipulator is bolted to, from the floor to its base.
    column = float(require(structure, "pedestal_radius_meters", "structure"))
    plate = float(require(structure, "pedestal_plate_radius_meters", "structure"))
    plate_thickness = float(
        require(structure, "pedestal_plate_thickness_meters", "structure")
    )
    mount = plan.arm_base[2]
    world.add_geom(
        name="arm_pedestal",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[column, (mount - plate_thickness) / 2.0, 0.0],
        pos=[plan.arm_base[0], plan.arm_base[1], (mount - plate_thickness) / 2.0],
        rgba=steel,
    )
    world.add_geom(
        name="arm_pedestal_plate",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[plate, plate_thickness / 2.0, 0.0],
        pos=[
            plan.arm_base[0],
            plan.arm_base[1],
            mount - plate_thickness / 2.0,
        ],
        rgba=[0.22, 0.23, 0.26, 1.0],
    )
    # A foot, so the pedestal reads as bolted down rather than balanced.
    world.add_geom(
        name="arm_pedestal_foot",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[plate * 1.2, 0.008, 0.0],
        pos=[plan.arm_base[0], plan.arm_base[1], 0.008],
        rgba=[0.22, 0.23, 0.26, 1.0],
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
    # The offscreen framebuffer bounds what any renderer attached to this model
    # can produce, and MuJoCo defaults it to 640 by 480. That is enough for the
    # 320 by 240 frames the models see and not enough for a demonstration
    # video. This is a ceiling on rendering rather than a property of the world,
    # which is why it sits here rather than in the configuration: changing it
    # changes no trajectory and no measurement.
    spec.visual.global_.offwidth = OFFSCREEN_WIDTH
    spec.visual.global_.offheight = OFFSCREEN_HEIGHT

    world = spec.worldbody
    world.add_light(pos=[0.0, 0.0, 2.0], dir=[0.0, 0.0, -1.0])

    plan = replace(plan, dressed=_dress(mujoco, spec, world, raw, root))

    half = [plan.belt.length / 2.0, plan.belt.width / 2.0, 0.02]
    world.add_geom(
        name="belt",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=half,
        pos=[0.0, 0.0, plan.belt.surface_height - half[2]],
        rgba=[0.25, 0.25, 0.28, 1.0],
    )

    _add_supports(mujoco, world, plan, require(raw, "structure"))

    # Side guides. A real sorting line has them, and without them a cylinder
    # that lands and tips simply rolls off the belt, which showed up as objects
    # recorded at lateral positions outside the belt's own width.
    rail = float(require(require(raw, "belt"), "guide_height_meters", "belt"))
    for sign in (-1.0, 1.0):
        world.add_geom(
            name=f"belt_guide_{'left' if sign < 0 else 'right'}",
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=[half[0], 0.01, rail / 2.0],
            pos=[0.0, sign * (half[1] + 0.01), plan.belt.surface_height + rail / 2.0],
            rgba=[0.30, 0.30, 0.34, 1.0],
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
            pos=[PARKED_X + 0.3 * index, PARKED_X, PARKED_Z],
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
    # A MuJoCo camera already looks along its own negative z, so an identity
    # orientation at this height points straight down at the belt. Rotating it
    # by 180 degrees about x, which looks correct at a glance, aims it at the
    # sky and renders a uniformly black frame.
    world.add_camera(
        name="overhead",
        pos=[0.0, 0.0, plan.belt.surface_height + height.sample(rng)],
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
