"""The grasp pose, as geometry in the world.

A marker is what the tracker believes, standing in the scene where it believes
it. One per open track, coloured by the track's identity, showing where a jaw
would close, how wide it would open, and which way it would be turned.

This is geometry and not an overlay, and the difference is the whole reason
the module exists. An overlay is painted onto a frame after the renderer is
done with it, so it argues for something the simulator never drew. A marker is
pushed into the scene before the render, so MuJoCo shades it, occludes it
behind the arm, and moves it with the camera exactly as it does every other
solid. `agents/claude.md` forbids the first and permits the second.

Two parts of the pose are derived and one is assumed. The horizontal position,
the closing axis and the opening all come from the record's footprint, which
came from pixels. The height does not: the gate looks straight down, no sensor
on this line estimates depth, and a `WasteObject` here carries no height at
all. So the pad plane is a configured standoff read from
[clave.world.effector.Effector], and this docstring is where that is admitted
rather than in a comment nobody reaches.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from typing import Any

from clave.taxonomy import REJECT_CHANNEL, channel_of
from clave.tracker.track import WasteObject
from clave.world.effector import Effector

Point = tuple[float, float, float]
"""A position in belt frame meters, which is MuJoCo world."""

SHAFT_RADIUS = 0.004
"""How thick the approach shaft is drawn, in meters.

A marker is drawn to scale wherever a dimension means something. This one does
not: no shaft exists on any effector, and it is here to show the approach
direction and to tie the pads to the flange. It is deliberately thin enough to
read as an annotation rather than as a part.
"""

UNORIENTED_PADS = 4
"""How many pads ring a footprint with no axis.

A circular footprint has no minor axis, so there is no one direction to turn a
jaw to. Ringing the object says the jaw could close along any diameter, which
is the claim the record actually supports. A single pair at the yaw that fell
out of the arithmetic would show a decision the tracker did not make, and a
filled disc of the same radius would hide the object a reader is checking the
marker against.
"""

UNREACHABLE_ALPHA = 0.35
"""How far a marker fades when the jaw cannot open that wide.

Fading rather than hiding: an object the effector cannot take is exactly the
one a reader wants to see, and a marker that vanishes looks like a tracker
that lost the object.
"""

OPAQUE = 1.0
"""Alpha for a pose the effector could take."""

PARK_POST_RADIUS = 0.010
"""How thick the post under the park pose is drawn, in meters."""

PARK_BALL_RADIUS = 0.030
"""How large the ball at the park pose is drawn, in meters."""


@dataclass(frozen=True)
class GraspMarker:
    """Where the effector would go for one track.

    Attributes:
        track_id: The identity this marker belongs to.
        valid_until_nanos: When belt travel invalidates this pose, copied from
            the record. A pose and the window it holds for travel together
            here for the same reason they travel together in the published
            decision: a pose with no expiry is a pose somebody will use late.
        pinch_position_belt: Where the pads would close, in belt frame meters.
        flange_position_world: Where the face the tool bolts to would sit.
        pad_positions_belt: The pad centers in belt frame, or an empty tuple when
            the footprint has no axis to turn a jaw to.
        pad_size: One pad's half-extents, in its own frame: along the closing
            direction, across it, and vertical.
        closing_yaw_belt: Rotation of the closing direction about the belt normal,
            in radians, or None when the footprint is not oriented.
        opening: How far the jaw would have to open, in meters.
        oriented: Whether `closing_yaw_belt` means anything.
        reachable: Whether the effector opens that wide at all.
        extent: The footprint's larger horizontal side, which sizes the disc
            drawn when there is no axis.
        color: The track's color, as red, green and blue in the unit range.
        channel: Where the object routes to, resolved from its material
            class. Carried here because the arm has to know which chute to
            release over, and the alternative is the task layer resolving a
            taxonomy identifier it has no other reason to hold.
    """

    track_id: int
    valid_until_nanos: int
    pinch_position_belt: Point
    flange_position_world: Point
    pad_positions_belt: tuple[Point, ...]
    pad_size: Point
    closing_yaw_belt: float | None
    opening: float
    oriented: bool
    reachable: bool
    extent: float
    color: tuple[float, float, float]
    channel: str = REJECT_CHANNEL
    velocity_world: Point | None = None

    def __init__(
        self,
        track_id: int,
        valid_until_nanos: int,
        pinch_position_belt: Point | None = None,
        flange_position_world: Point | None = None,
        pad_positions_belt: tuple[Point, ...] | None = None,
        pad_size: Point = (0.0, 0.0, 0.0),
        closing_yaw_belt: float | None = None,
        opening: float = 0.0,
        oriented: bool = False,
        reachable: bool = False,
        extent: float = 0.0,
        color: tuple[float, float, float] = (0.0, 0.0, 0.0),
        channel: str = REJECT_CHANNEL,
        velocity_world: Point | None = None,
        *,
        grasp: Point | None = None,
        flange: Point | None = None,
        pads: tuple[Point, ...] | None = None,
        closing_axis: float | None = None,
    ) -> None:
        p_grasp = grasp if grasp is not None else pinch_position_belt
        if p_grasp is None:
            raise TypeError("GraspMarker requires pinch_position_belt or grasp")
        p_flange = flange if flange is not None else flange_position_world
        if p_flange is None:
            raise TypeError("GraspMarker requires flange_position_world or flange")
        p_pads = (
            pads
            if pads is not None
            else (() if pad_positions_belt is None else pad_positions_belt)
        )
        axis = closing_axis if closing_axis is not None else closing_yaw_belt

        object.__setattr__(self, "track_id", track_id)
        object.__setattr__(self, "valid_until_nanos", valid_until_nanos)
        object.__setattr__(self, "pinch_position_belt", p_grasp)
        object.__setattr__(self, "flange_position_world", p_flange)
        object.__setattr__(self, "pad_positions_belt", p_pads)
        object.__setattr__(self, "pad_size", pad_size)
        object.__setattr__(self, "closing_yaw_belt", axis)
        object.__setattr__(self, "opening", opening)
        object.__setattr__(self, "oriented", oriented)
        object.__setattr__(self, "reachable", reachable)
        object.__setattr__(self, "extent", extent)
        object.__setattr__(self, "color", color)
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "velocity_world", velocity_world)

    @property
    def grasp(self) -> Point:
        """Backwards compatibility alias for pinch_position_belt."""
        return self.pinch_position_belt

    @property
    def flange(self) -> Point:
        """Backwards compatibility alias for flange_position_world."""
        return self.flange_position_world

    @property
    def closing_axis(self) -> float | None:
        """Backwards compatibility alias for closing_yaw_belt."""
        return self.closing_yaw_belt

    @property
    def pads(self) -> tuple[Point, ...]:
        """Backwards compatibility alias for pad_positions_belt."""
        return self.pad_positions_belt


RESERVED_HUE = 0.05
"""The wedge at each end of the hue circle no track is given.

Red belongs to the park pose, which is the one marker in the scene that is not
a track, and a reader has to be able to tell it apart at a glance. The golden
ratio sequence is dense, so no amount of spreading keeps a track away from red
on its own: track 0 landed on pure red, and with enough tracks something lands
arbitrarily close to any hue. Reserving the wedge is what makes the guarantee
hold for every identity rather than for the first few.
"""


def color_for(track_id: int) -> tuple[float, float, float]:
    """Return a stable color for one track, as red, green and blue.

    Derived from the identity rather than assigned in order, so a track keeps
    its color when another retires, and a marker and a record correspond
    without a reader counting.

    Args:
        track_id: The track's identity.

    Returns:
        The color, each channel in the unit range, and never red.
    """
    # The golden ratio spreads successive integers around the hue circle, so
    # neighbouring track ids never come out as neighbouring colors. The span
    # is then squeezed off both ends, leaving red to the park pose.
    spread = (track_id * 0.618033988749895) % 1.0
    hue = RESERVED_HUE + spread * (1.0 - 2.0 * RESERVED_HUE)
    return colorsys.hsv_to_rgb(hue, 0.85, 1.0)


def marker_for(
    record: WasteObject,
    effector: Effector,
    belt_surface_height_world: float | None = None,
    *,
    belt_surface: float | None = None,
) -> GraspMarker:
    """Return where the effector would go for one record.

    Args:
        record: What the tracker settled.
        effector: The effector the pick geometry assumes.
        belt_surface_height_world: Height of the belt surface, in meters.
        belt_surface: Legacy keyword alias for belt_surface_height_world.

    Returns:
        The marker. Its horizontal position, closing axis and opening come
        from the record; its height comes from `effector`, because nothing on
        this line measures one.
    """
    surface = (
        belt_surface_height_world
        if belt_surface_height_world is not None
        else (0.0 if belt_surface is None else belt_surface)
    )
    x, y, _ = record.grasp_point
    pad_z = surface + effector.grasp_height
    opening = record.grasp_width
    oriented = record.footprint.oriented

    pads: tuple[Point, ...] = ()
    axis: float | None = None
    if oriented:
        axis = record.grasp_axis
        # The pads face each other across the object, so their centers stand
        # half a pad beyond the opening on either side.
        reach = opening / 2.0 + effector.pad_thickness / 2.0
        step_x, step_y = math.cos(axis) * reach, math.sin(axis) * reach
        pads = (
            (x - step_x, y - step_y, pad_z),
            (x + step_x, y + step_y, pad_z),
        )

    return GraspMarker(
        track_id=record.track_id,
        valid_until_nanos=record.valid_until_nanos,
        pinch_position_belt=(x, y, pad_z),
        flange_position_world=(x, y, pad_z + effector.finger_length),
        pad_positions_belt=pads,
        pad_size=(
            effector.pad_thickness / 2.0,
            effector.pad_depth / 2.0,
            effector.pad_height / 2.0,
        ),
        closing_yaw_belt=axis,
        opening=opening,
        oriented=oriented,
        reachable=opening <= effector.opening,
        channel=_channel_of(record.material),
        extent=record.footprint.major_extent,
        color=color_for(record.track_id),
    )


def markers_for(
    records: tuple[WasteObject, ...],
    effector: Effector,
    belt_surface_height_world: float | None = None,
    *,
    belt_surface: float | None = None,
) -> tuple[GraspMarker, ...]:
    """Return one marker per record, in the order given.

    Args:
        records: What the tracker settled at one instant.
        effector: The effector the pick geometry assumes.
        belt_surface_height_world: Height of the belt surface, in meters.
        belt_surface: Legacy keyword alias for belt_surface_height_world.

    Returns:
        The markers. A track that retired is absent from `records` and
        therefore absent here, which is how a marker stops being drawn.
    """
    surface = (
        belt_surface_height_world
        if belt_surface_height_world is not None
        else (0.0 if belt_surface is None else belt_surface)
    )
    return tuple(marker_for(record, effector, surface) for record in records)


def ground_truth_markers(
    model: Any,
    data: Any,
    active_objects: list[Any],
    plan: Any,
    effector: Effector,
    belt_surface_height_world: float,
    at_nanos: int,
    window_exit: float,
    belt_speed: float,
) -> tuple[GraspMarker, ...]:
    """Compute grasp markers directly from MuJoCo ground-truth physics.

    One marker per active object on the belt, derived directly from the
    simulator body position, orientation quaternion, and geom extents rather
    than from camera segmentation and tracker estimation.

    Args:
        model: Compiled MuJoCo model.
        data: Current MuJoCo simulation state.
        active_objects: Objects currently managed by the conveyor.
        plan: Resolved scene layout carrying belt geometry.
        effector: Effector parameters sizing pads, fingers, and grasp height.
        belt_surface_height_world: Surface height of the belt in world frame.
        at_nanos: Current simulated timestamp in nanoseconds.
        window_exit: X-coordinate in belt frame where reachability closes.
        belt_speed: Conveyor belt speed in meters per second.

    Returns:
        One marker per active object resting on the belt within the reachable
        window, in pool slot order.
    """
    import mujoco

    surface = belt_surface_height_world

    markers: list[GraspMarker] = []
    for item in active_objects:
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
        if body < 0:
            continue

        pos = data.xpos[body]
        x, y, z = float(pos[0]), float(pos[1]), float(pos[2])

        # Exclude objects not resting on the driven belt region.
        # Height tolerance of 0.15 m accommodates packaging resting on the belt
        # while excluding dropped objects or items lifted by the gripper.
        on_belt = (
            abs(x) <= plan.belt.length / 2.0
            and abs(y) <= plan.belt.width / 2.0
            and surface - 0.05 < z <= surface + 0.15
        )
        if not on_belt or x > window_exit:
            continue

        # Body orientation quaternion: data.xquat[body] is [w, x, y, z]
        quat = data.xquat[body]
        w, qx, qy, qz = float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
        yaw = math.atan2(2.0 * (w * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))

        geom_id = model.body_geomadr[body]
        geom_type = model.geom_type[geom_id] if geom_id >= 0 else None

        oriented = True
        closing_axis: float | None = yaw

        pad_z = surface + effector.grasp_height
        if geom_type == mujoco.mjtGeom.mjGEOM_CYLINDER:
            r = float(model.geom_size[geom_id][0])
            opening = 2.0 * r
            extent = 2.0 * r
            oriented = False
            closing_axis = None
            center_z = float(data.geom_xpos[geom_id][2])
            pad_z = min(max(center_z, surface + 0.012), surface + 0.150)
        elif geom_type == mujoco.mjtGeom.mjGEOM_BOX:
            sx = float(model.geom_size[geom_id][0])
            sy = float(model.geom_size[geom_id][1])
            dim_x, dim_y = 2.0 * sx, 2.0 * sy
            if dim_x <= dim_y:
                opening = dim_x
                extent = dim_y
                closing_axis = yaw
            else:
                opening = dim_y
                extent = dim_x
                closing_axis = yaw + math.pi / 2.0
            center_z = float(data.geom_xpos[geom_id][2])
            pad_z = min(max(center_z, surface + 0.012), surface + 0.150)
        elif geom_type == mujoco.mjtGeom.mjGEOM_MESH:
            mesh_id = model.geom_dataid[geom_id]
            if mesh_id >= 0:
                start = model.mesh_vertadr[mesh_id]
                count = model.mesh_vertnum[mesh_id]
                verts = model.mesh_vert[start : start + count]
                dim_x = float(verts[:, 0].max() - verts[:, 0].min())
                dim_y = float(verts[:, 1].max() - verts[:, 1].min())
                if dim_x <= dim_y:
                    opening = dim_x
                    extent = dim_y
                    closing_axis = yaw
                else:
                    opening = dim_y
                    extent = dim_x
                    closing_axis = yaw + math.pi / 2.0
                R = data.geom_xmat[geom_id].reshape(3, 3)
                world_z = (R[2, :] @ verts.T) + float(data.geom_xpos[geom_id][2])
                center_z = float((world_z.min() + world_z.max()) / 2.0)
                pad_z = min(max(center_z, surface + 0.012), surface + 0.150)
            else:
                opening = effector.opening * 0.5
                extent = opening
        else:
            opening = effector.opening * 0.5
            extent = opening

        flange_z = pad_z + effector.finger_length

        if closing_axis is not None:
            closing_axis = (closing_axis + math.pi) % (2.0 * math.pi) - math.pi

        pads: tuple[Point, ...] = ()
        if oriented and closing_axis is not None:
            reach = opening / 2.0 + effector.pad_thickness / 2.0
            step_x = math.cos(closing_axis) * reach
            step_y = math.sin(closing_axis) * reach
            pads = (
                (x - step_x, y - step_y, pad_z),
                (x + step_x, y + step_y, pad_z),
            )

        obj_velocity: Point | None = None
        jnt_id = model.body_jntadr[body] if body < len(model.body_jntadr) else -1
        if jnt_id >= 0 and model.jnt_type[jnt_id] == mujoco.mjtJoint.mjJNT_FREE:
            dof_adr = model.jnt_dofadr[jnt_id]
            obj_velocity = (
                float(data.qvel[dof_adr]),
                float(data.qvel[dof_adr + 1]),
                float(data.qvel[dof_adr + 2]),
            )
        elif hasattr(data, "cvel") and data.cvel is not None and len(data.cvel) > body:
            obj_velocity = (
                float(data.cvel[body][3]),
                float(data.cvel[body][4]),
                float(data.cvel[body][5]),
            )

        remaining = max(0.0, window_exit - x)
        effective_speed = (
            obj_velocity[0]
            if obj_velocity is not None and obj_velocity[0] > 0.01
            else belt_speed
        )
        expires = (
            at_nanos + int(remaining / effective_speed * 1_000_000_000)
            if effective_speed > 0.0
            else at_nanos
        )

        markers.append(
            GraspMarker(
                track_id=item.index,
                valid_until_nanos=expires,
                pinch_position_belt=(x, y, pad_z),
                flange_position_world=(x, y, flange_z),
                pad_positions_belt=pads,
                pad_size=(
                    effector.pad_thickness / 2.0,
                    effector.pad_depth / 2.0,
                    effector.pad_height / 2.0,
                ),
                closing_yaw_belt=closing_axis,
                opening=opening,
                oriented=oriented,
                reachable=opening <= effector.opening,
                channel=item.channel,
                extent=extent,
                color=color_for(item.index),
                velocity_world=obj_velocity,
            )
        )

    return tuple(markers)


def draw(scene: Any, markers: tuple[GraspMarker, ...]) -> int:
    """Add every marker to a scene, and report how many geoms that took.

    The scene is the renderer's own, already populated by `update_scene`. What
    this adds lives until the next `update_scene` overwrites it, so a marker
    is visible to whoever renders next and to nobody else: not to physics, not
    to a camera the tracker reads, and not to a run that never calls this.

    Args:
        scene: The `mjvScene` to add to.
        markers: What to draw.

    Returns:
        How many geoms were added, which is fewer than asked for when the
        scene runs out of room.
    """
    import mujoco
    import numpy as np

    added = 0
    for marker in markers:
        alpha = OPAQUE if marker.reachable else UNREACHABLE_ALPHA
        rgba = np.array([*marker.color, alpha], dtype=np.float32)
        for geom_type, size, position, yaw in _solids(marker):
            if scene.ngeom >= scene.maxgeom:
                return added
            mujoco.mjv_initGeom(
                scene.geoms[scene.ngeom],
                geom_type,
                np.asarray(size, dtype=np.float64),
                np.asarray(position, dtype=np.float64),
                _spin(yaw),
                rgba,
            )
            scene.ngeom += 1
            added += 1
    return added


def draw_park(
    scene: Any,
    position_world: Point | None = None,
    color: tuple[float, float, float] = (1.0, 0.0, 0.0),
    belt_surface_height_world: float | None = None,
    *,
    position: Point | None = None,
    belt_surface: float | None = None,
) -> int:
    """Add the park pose to a scene, and report how many geoms that took.

    A ball where the flange rests and a post down to belt height, so the pose
    reads as a place in the world rather than as a dot floating in it. Neither
    shape is a jaw: the arm grasps nothing at park, and drawing pads there
    would say it was about to.

    Args:
        scene: The `mjvScene` to add to.
        position_world: Where the flange rests in world coordinates.
        color: What to draw it in, as red, green and blue in the unit range.
        belt_surface_height_world: Height of the belt surface, in meters, which is where
            the post stops.
        position: Legacy keyword alias for position_world.
        belt_surface: Legacy keyword alias for belt_surface_height_world.

    Returns:
        How many geoms were added, which is fewer than asked for when the
        scene runs out of room.
    """
    import mujoco
    import numpy as np

    pos = position_world if position_world is not None else position
    if pos is None:
        raise TypeError("draw_park requires position_world or position")
    surface = (
        belt_surface_height_world
        if belt_surface_height_world is not None
        else (0.0 if belt_surface is None else belt_surface)
    )

    rgba = np.array([*color, OPAQUE], dtype=np.float32)
    x, y, z = pos
    half_post = max((z - surface) / 2.0, PARK_BALL_RADIUS)
    solids: tuple[tuple[int, Point, Point], ...] = (
        (int(mujoco.mjtGeom.mjGEOM_SPHERE), (PARK_BALL_RADIUS, 0.0, 0.0), pos),
        (
            int(mujoco.mjtGeom.mjGEOM_CYLINDER),
            (PARK_POST_RADIUS, half_post, 0.0),
            (x, y, z - half_post),
        ),
    )
    added = 0
    for geom_type, size, place in solids:
        if scene.ngeom >= scene.maxgeom:
            return added
        mujoco.mjv_initGeom(
            scene.geoms[scene.ngeom],
            geom_type,
            np.asarray(size, dtype=np.float64),
            np.asarray(place, dtype=np.float64),
            _spin(0.0),
            rgba,
        )
        scene.ngeom += 1
        added += 1
    return added


def _solids(marker: GraspMarker) -> tuple[tuple[int, Point, Point, float], ...]:
    """Return every solid one marker is made of.

    A jaw is two pads and the shaft that carries them. A pose with no axis
    gets the same shaft and a ring of pads instead of a pair, so the position
    the tracker is sure of is drawn without inventing the angle it is not.

    Args:
        marker: The pose to draw.

    Returns:
        Tuples of MuJoCo geom type, half-size, position, and rotation about
        the belt normal.
    """
    import mujoco

    x, y, grasp_z = marker.grasp
    half_shaft = (marker.flange[2] - grasp_z) / 2.0
    solids: list[tuple[int, Point, Point, float]] = [
        (
            int(mujoco.mjtGeom.mjGEOM_CYLINDER),
            (SHAFT_RADIUS, half_shaft, 0.0),
            (x, y, grasp_z + half_shaft),
            0.0,
        )
    ]
    for angle, pad in _pad_places(marker):
        solids.append((int(mujoco.mjtGeom.mjGEOM_BOX), marker.pad_size, pad, angle))
    return tuple(solids)


def _pad_places(marker: GraspMarker) -> tuple[tuple[float, Point], ...]:
    """Return where each pad stands and which way it faces.

    Args:
        marker: The pose to draw.

    Returns:
        Pairs of rotation about the belt normal and pad center.
    """
    if marker.oriented and marker.closing_axis is not None:
        return tuple((marker.closing_axis, pad) for pad in marker.pads)

    x, y, grasp_z = marker.grasp
    reach = marker.opening / 2.0 + marker.pad_size[0]
    places = []
    for index in range(UNORIENTED_PADS):
        angle = index * 2.0 * math.pi / UNORIENTED_PADS
        places.append(
            (angle, (x + math.cos(angle) * reach, y + math.sin(angle) * reach, grasp_z))
        )
    return tuple(places)


def _spin(yaw: float) -> Any:
    """Return the rotation matrix for a turn about the belt normal.

    Args:
        yaw: The rotation, in radians.

    Returns:
        The matrix, flattened row major, as MuJoCo expects it.
    """
    import numpy as np

    cos, sin = math.cos(yaw), math.sin(yaw)
    return np.array([cos, -sin, 0.0, sin, cos, 0.0, 0.0, 0.0, 1.0], dtype=np.float64)


def _channel_of(material: str) -> str:
    """Return the channel a material class routes to.

    Args:
        material: A taxonomy identifier, or `reject` when the tracker could
            not settle on one.

    Returns:
        The channel. Anything outside the taxonomy goes to the reject
        channel rather than raising: a track the tracker cannot classify is
        an ordinary outcome and the line has somewhere to put it.
    """
    try:
        return channel_of(material)
    except KeyError:
        return REJECT_CHANNEL
