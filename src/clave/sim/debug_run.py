"""Driving the tracker over a rollout and showing what it decided.

This is a diagnostic, not a demonstration. It drives `clave.tracker` directly
rather than through `clave.runtime.loop`, because the tracker is deliberately
not wired into the loop yet.

What a reader sees is the world, with a grasp marker standing where the
tracker believes each object is and turned the way a jaw would have to close
on it. The markers are scene geometry rather than paint on a frame, so MuJoCo
shades and occludes them like any other solid, and nothing touches the image
after the renderer is finished with it.

The sensing cameras and the watching camera never mix. The tracker segments
every camera carrying the detection role, because those are the sensors the
line actually has, and it is handed nothing else. The human watches a view
named in `configs/debug/tracker.yml`, because a grasp pose seen from
straight above has no approach to read. That file carries two views and the
run takes one by name: one camera cannot both read a 60 mm jaw and hold the
park pose in frame.

`--camera-video` writes a second file of the primary detection camera, with a
box on each object a segmentation of that same frame covered. That render
stays off unless it is asked for (`AC-CAM-01`).

**The report separates active motion from grasping.** An arm can reach the pose it
was sent to perfectly and still hold nothing, which is what happens when the
pose is not where the object is, so the run reports the distance to the
commanded pose, the distance from the jaw to the nearest object at the
instant it shuts, and how far each visit actually lifted anything. Only the
last of those is a grasp, and reading the first as one is how a broken pick
looks solved.

A window opens when a display is available and the run writes its artifacts
either way, because a machine with no display is the ordinary case for this
project and refusing to run on one would make the view useless exactly where
it is needed most.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(iterable: Any, *args: Any, **kwargs: Any) -> Any:
        return iterable


import numpy as np
from numpy.typing import NDArray

from clave.control.motion import Command, Reference, toward
from clave.control.pick import JAW_OPEN
from clave.control.selection import Selector, pickable_in_belt
from clave.control.servo import follow
from clave.control.settings import ControlSettings, Phase
from clave.control.story import AnomalyWatch, StoryLog
from clave.control.task import TaskMachine
from clave.control.trajectory import distance, norm, zeros
from clave.errors import ClaveError
from clave.taxonomy import channel_of
from clave.tracker.adapters.detection import detections_from_masks
from clave.tracker.adapters.render import segment_masks
from clave.tracker.association import SimulatorIdentity
from clave.tracker.codes import load_catalog, resolver_for
from clave.tracker.evidence import Evidence, GroundTruth, Role
from clave.tracker.fusion import FusionSettings
from clave.tracker.intake import Deployment, Intake
from clave.tracker.listing import described_fields
from clave.tracker.markers import (
    draw,
    draw_park,
    ground_truth_markers,
    markers_for,
)
from clave.tracker.sensors import load_sensors, of_role, require_role
from clave.tracker.track import Tracker
from clave.world import arm as armmod
from clave.world import belt, config, scene
from clave.world.effector import Effector
from clave.world.feed import FeedSettings, RateController

LOGGER = logging.getLogger(__name__)

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the instants an observation carries."""

_VISITING = frozenset({Phase.TRACK, Phase.DESCEND, Phase.RETREAT})
"""The phases that are about an object rather than about going home."""

GRASPED_METERS = 0.010
"""How far a visit has to raise an object before the jaw was holding it.

Measured against where the object was lying when the plan was made, not
against the belt: a settled object already rests with its center above the
surface, and by a different amount for every mesh in the set. Ten
millimetres is above the millimetre of settling jitter and far below the
50 mm clearance a retreat lifts to, so nothing sits near the boundary.
"""


class DebugRunError(ClaveError):
    """The debug run cannot be set up from this configuration."""


@dataclass(frozen=True)
class DebugRunReport:
    """What one debug run did.

    Attributes:
        captures: Frames the tracker was shown.
        tracks: Tracks open when it finished.
        reorders: How many captures rebuilt the queue, by the trigger that
            did it. A rebuild because a track appeared is the design
            working; a rebuild because an anchor moved is the estimate having
            genuinely shifted. Counting them together hides whether the
            anchors damp anything.
        head_churn: How many captures swapped the head of the queue while the
            previous head was still there to be served. This is the figure
            that decides whether the arm can work through the queue: a
            rebuild that keeps its head costs nothing, and one that does not
            sends the arm somewhere else mid-traverse.
        served: Tracks the arm finished a visit to.
        missed: Tracks no interception existed for, which the arm gave up
            rather than chased. Distinct from a fault: the pose was fine and
            the timing was not.
        arrivals: How far the flange was from the pose each completed visit
            asked for, in meters. Measured at the end of the dwell under a
            stepped profile and at the instant the jaw reaches the object
            under a planned one. Read its median rather than its mean: the
            distribution is a tight cluster with occasional strays, and a
            mean over seventeen visits moved from 3 mm to 43 mm on one of
            them.
        feed_rate: What the line was asked to carry, in objects per second.
        measured_rate: What it achieved over the controller's window, at the
            end of the run.
        belt_speed: What the feed controller ended up commanding, in meters
            per second. Reported beside the two rates so a reader can tell a
            line that held its setpoint from one that saturated trying.
        lifts: How far each completed visit raised the object that ended up
            nearest the jaw, in meters, against where that object was lying
            when the plan was made. This is the figure that says whether the
            jaw held anything: a failed grasp reads near zero however well
            the arm flew.
        placed: How many objects went down a chute, by channel. A place is
            the object's centre crossing below the belt surface inside a
            mouth's footprint, which is where the system's responsibility
            ends and the plant's begins.
        misrouted: How many of those went down a channel their material
            class does not route to. This is the figure `max_misroute_rate`
            has gated with no way to produce.
        jaw_gaps: How far the nearest object was from the pinch site at the
            instant the jaw shut, in meters, one per visit. It separates the
            two ways a pick fails: a large gap is a visit tick that arrived
            somewhere the object was not, and a small gap with no lift is a
            grasp that could not hold.
        profile: Which task profile the run used, because a distance to a
            tracked pose and a distance to a descended pose are not the same
            measurement.
        closest_approach: The nearest the flange ever came to a pose the
            tracking phase asked for, in meters, or None when it never
            tracked.
        closest_live: The nearest it came to where that object actually was
            at the same instant, in meters, or None. The gap between the two
            is the staleness of a pose decided once per capture while the
            belt keeps moving, and is what an interception has to close.
        faults: Refusals the controller recorded, with the track each was
            about.
        phase: The phase the arm ended in.
        drawn: Markers standing in the world on the final frame.
        geoms: Marker geoms the final frame carried, which is more than
            `drawn` because a jaw is a shaft and two pads, and the park pose
            adds two of its own.
        frames_written: Frames written.
        output: Where they went.
        video_path: The playable file, or None when none was asked for or no
            encoder was found.
        camera_video_path: The detection-camera file, with a box on each
            object the segmentation covered, or None when none was asked for
            or no encoder was found.
        telemetry_path: The CSV telemetry file, or None when telemetry was not
            requested.
        metadata_path: Where the revision and the configuration digests were
            recorded, so a number in this report can be traced to the tree and
            the configuration it came from.
        min_jaw_clearance: The smallest distance any of the jaw's collision
            geometry came to the belt surface, in meters. Negative means the
            geometry was inside the belt.
        belt_contacts: How many ticks had a contact between the jaw and the
            belt.
        worst_tool_tilt_degrees: The largest departure of the tool's axis from
            the belt normal, in degrees.
        abandoned: Visits given up before the descent began, with the reason
            each was given up. Distinct from `missed`: an abandoned visit is a
            plan that was active and that the freshest estimate contradicted,
            and this is the only figure that tells that apart from an arm that
            never saw the object.
        worst_aim_drift: The largest distance a active plan was found
            aiming away from where the freshest estimate put the object, in
            meters, or None when no visit was ever re-aimed. This is the figure
            that catches a plan about to descend onto bare belt, and no arrival
            error can show it: the arm meets a stale pose perfectly.
        grasp_yaw_errors: How far the commanded tool yaw stood from the object
            body's own yaw when the jaw shut, in degrees, folded into the 90
            degrees a jaw is symmetric about, one per grab that had an object
            under it. Empty unless the run was driven from ground truth,
            because a tracker estimate has no body to compare against.
        lurches: How fast the flange's vertical acceleration peaked over each
            planned visit, in meters per second squared, one per visit. The
            figure behind "the arm jumps when it lifts": a grasp that slips
            unloads the arm mid-lift and that is an acceleration, not a pose.
        climbs: The fastest the flange rose during each planned visit, in
            meters per second, one per visit.
        report_path: Where this report was written beside the run's other
            artifacts, so the figures survive the terminal that printed them.
        windowed: Whether a live window was opened.
        reason: Why no window was opened, when none was.
    """

    captures: int
    tracks: int
    reorders: dict[str, int]
    head_churn: int
    served: tuple[int, ...]
    missed: tuple[int, ...]
    arrivals: tuple[float, ...]
    lifts: tuple[float, ...]
    jaw_gaps: tuple[float, ...]
    placed: dict[str, int]
    misrouted: int
    feed_rate: float
    measured_rate: float
    belt_speed: float
    profile: str
    closest_approach: float | None
    closest_live: float | None
    faults: tuple[tuple[int | None, str], ...]
    phase: str
    drawn: int
    geoms: int
    frames_written: int
    output: Path
    video_path: Path | None
    telemetry_path: Path | None
    metadata_path: Path
    min_jaw_clearance: float | None
    belt_contacts: int
    worst_tool_tilt_degrees: float | None
    abandoned: tuple[tuple[int, str], ...] = ()
    worst_aim_drift: float | None = None
    grasp_yaw_errors: tuple[float, ...] = ()
    lurches: tuple[float, ...] = ()
    climbs: tuple[float, ...] = ()
    report_path: Path | None = None
    windowed: bool = False
    reason: str | None = None
    ground_truth: bool = False
    camera_video_path: Path | None = None


@dataclass(frozen=True)
class JawState:
    """Where the gripper's own geometry stands relative to the belt.

    Attributes:
        lowest_z: The lowest world height of any collision geometry bolted to
            the flange, in meters. This is the jaw rather than the pose: the
            pose is the flange, and the jaw hangs below it.
        clearance: That height less the belt surface, in meters. Negative means
            the geometry is inside the belt.
        contact: Whether any of that geometry is touching the belt.
        tilt_degrees: How far the tool's own axis stands from the belt normal,
            in degrees.
    """

    lowest_z: float
    clearance: float
    contact: bool
    tilt_degrees: float


def _jaw_collision_geoms(model: Any, arm: Any) -> tuple[int, ...]:
    """Return every collision geom bolted to the flange.

    Found by walking down the body tree from the body the pinch site stands on
    rather than by matching names, so a vendored gripper that renames its parts
    still reports the geometry that would hit the belt.

    Args:
        model: The compiled model.
        arm: The arm indices.

    Returns:
        The geom ids, in model order.
    """
    base = int(model.site_bodyid[arm.pinch_site])
    children: dict[int, list[int]] = {}
    for body in range(model.nbody):
        children.setdefault(int(model.body_parentid[body]), []).append(body)
    subtree: set[int] = set()
    stack = [base]
    while stack:
        body = stack.pop()
        subtree.add(body)
        stack.extend(children.get(body, ()))
    return tuple(
        geom
        for geom in range(model.ngeom)
        if int(model.geom_bodyid[geom]) in subtree and model.geom_contype[geom] != 0
    )


_MESH_VERTS: dict[tuple[int, int], NDArray[np.float64]] = {}
"""Mesh vertices copied once per compiled model, keyed by model id and mesh id.

Used when a marker or resting height needs the mesh itself. Jaw clearance no
longer walks these vertices (`AC-PERF-03`).
"""


def _mesh_vertices(model: Any, mesh: int) -> NDArray[np.float64]:
    """Return one mesh's vertices, copied out of the model the first time.

    Args:
        model: The compiled model.
        mesh: The mesh id.

    Returns:
        The vertices, shape `(count, 3)`, in the mesh frame.
    """
    key = (id(model), mesh)
    cached = _MESH_VERTS.get(key)
    if cached is None:
        start = int(model.mesh_vertadr[mesh])
        count = int(model.mesh_vertnum[mesh])
        cached = np.array(model.mesh_vert[start : start + count], dtype=np.float64)
        _MESH_VERTS[key] = cached
    return cached


def _aabb_support_down(rotation: Any, centre: float, size: Any) -> float:
    """Return the lowest world height of a local AABB under a rotation.

    The support of an axis-aligned box along world-down is each half-extent
    times how much of that local axis points down. Written out rather than as
    a matrix product because this runs once per geom per physics tick.

    Args:
        rotation: The geom's 3x3 world rotation.
        centre: The geom origin's world height, in meters.
        size: Local half-extents along x, y, and z.

    Returns:
        The lowest world height of that box, in meters.
    """
    return centre - (
        abs(float(rotation[2, 0])) * float(size[0])
        + abs(float(rotation[2, 1])) * float(size[1])
        + abs(float(rotation[2, 2])) * float(size[2])
    )


def _lowest_world_z(model: Any, data: Any, geom: int) -> float:
    """Return the lowest height of one collision geom's own volume.

    Exact for the primitive shapes a gripper pad is made of. Mesh geoms use
    MuJoCo's local AABB (`geom_size` half-extents) under the same support
    formula as a box (`AC-PERF-03`): that bound never sits above the true
    mesh, so a clearance report never overstates how close the jaw came, and
    it stays O(1) where walking tens of thousands of vertices per tick was
    most of the debug-run wall.

    Args:
        model: The compiled model.
        data: Its state, with forward kinematics current.
        geom: The geom to measure.

    Returns:
        The lowest world height of that geom, in meters.
    """
    import mujoco

    rotation = data.geom_xmat[geom].reshape(3, 3)
    centre = float(data.geom_xpos[geom][2])
    size = model.geom_size[geom]
    kind = int(model.geom_type[geom])
    if kind in (int(mujoco.mjtGeom.mjGEOM_BOX), int(mujoco.mjtGeom.mjGEOM_MESH)):
        return _aabb_support_down(rotation, centre, size)
    if kind == int(mujoco.mjtGeom.mjGEOM_SPHERE):
        return centre - float(size[0])
    if kind in (
        int(mujoco.mjtGeom.mjGEOM_CYLINDER),
        int(mujoco.mjtGeom.mjGEOM_CAPSULE),
    ):
        return centre - abs(float(rotation[2, 2])) * float(size[1]) - float(size[0])
    return centre - float(max(size))


def _jaw_state(
    mujoco: Any,
    model: Any,
    data: Any,
    arm: Any,
    jaw_geoms: tuple[int, ...],
    belt_geom: int,
    surface: float,
) -> JawState:
    """Read the jaw's clearance, its contact with the belt and its tilt.

    Args:
        mujoco: The imported MuJoCo module.
        model: The compiled model.
        data: Its state, with forward kinematics current.
        arm: The arm indices.
        jaw_geoms: The collision geoms bolted to the flange.
        belt_geom: The belt's geom id, or -1 when the world names none.
        surface: Belt surface height, in world frame meters.

    Returns:
        The state.
    """

    lowest = min(
        (_lowest_world_z(model, data, geom) for geom in jaw_geoms),
        default=float("inf"),
    )
    jaw = set(jaw_geoms)
    touching = False
    for index in range(data.ncon):
        pair = {int(data.contact[index].geom1), int(data.contact[index].geom2)}
        # Either order: MuJoCo reports the pair in whichever order its broad
        # phase produced, and a test that assumed the jaw came first missed
        # every contact the run was making.
        if belt_geom in pair and pair & jaw:
            touching = True
            break
    axis = data.site_xmat[arm.tool_site].reshape(3, 3)[:, 2]
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, -float(axis[2])))))
    return JawState(
        lowest_z=lowest,
        clearance=lowest - surface,
        contact=touching,
        tilt_degrees=tilt,
    )


class _TelemetryWriter:
    """Write fixed-width MuJoCo telemetry columns for PlotJuggler."""

    def __init__(self, path: Path, model: Any, pool_size: int, rate: float) -> None:
        self._file = path.open("w", newline="")
        self._writer = csv.writer(self._file)
        self._period = 1.0 / rate
        self.next_sample = 0.0
        self._pool_size = pool_size
        self._headers = [
            "time",
            "belt_speed",
            "gripper_command",
            "flange_x",
            "flange_y",
            "flange_z",
            "pinch_x",
            "pinch_y",
            "pinch_z",
            "phase_code",
            "task_active",
            "commanded_x",
            "commanded_y",
            "commanded_z",
            "commanded_yaw",
            "jaw_lowest_z",
            "jaw_clearance",
            "belt_contact",
            "tool_tilt_degrees",
        ]
        self._headers.extend(f"qpos_{index}" for index in range(model.nq))
        self._headers.extend(f"qvel_{index}" for index in range(model.nv))
        self._headers.extend(f"ctrl_{index}" for index in range(model.nu))
        for index in range(pool_size):
            self._headers.extend(
                (f"object_{index}_x", f"object_{index}_y", f"object_{index}_z")
            )
        self._writer.writerow(self._headers)

    def write(
        self,
        model: Any,
        data: Any,
        indices: Any,
        conveyor: Any,
        belt_speed: float,
        phase: Phase,
        active: bool,
        jaw: JawState,
        command: Any = None,
    ) -> None:
        """Write the current state when the requested sample period is due.

        Written after the tick's command has been decided rather than before it,
        so the phase and the commanded pose in a row are the ones that tick
        commanded. Written before, the row carried the previous tick's phase,
        which is a millisecond of nothing on a 500 Hz tick and a whole leg on a
        coarse one: a run whose `DESCEND` column spanned 0.79 s against a
        0.40 s leg is what that looks like from outside.
        """
        if float(data.time) + 1e-12 < self.next_sample:
            return
        flange = _flange(indices, data)
        pinch = _pinch(indices, data)
        if command is None:
            commanded: list[object] = ["", "", "", ""]
        else:
            commanded = [*command.position, "" if command.yaw is None else command.yaw]
        row: list[object] = [
            float(data.time),
            belt_speed,
            float(data.ctrl[indices.gripper_actuator]),
            *flange,
            *pinch,
            list(Phase).index(phase),
            int(active),
            *commanded,
            jaw.lowest_z,
            jaw.clearance,
            int(jaw.contact),
            jaw.tilt_degrees,
            *[float(value) for value in data.qpos],
            *[float(value) for value in data.qvel],
            *[float(value) for value in data.ctrl],
        ]
        positions = {item.index: item.name for item in conveyor.active}
        for index in range(self._pool_size):
            name = positions.get(index)
            if name is None:
                row.extend(("", "", ""))
                continue
            body = mujoco_body_id(model, name)
            address = model.jnt_qposadr[model.body_jntadr[body]]
            row.extend(float(value) for value in data.qpos[address : address + 3])
        self._writer.writerow(row)
        self._file.flush()
        self.next_sample += self._period

    def close(self) -> None:
        """Flush and close the telemetry file."""
        self._file.close()


def _progress(steps: int, enabled: bool) -> Any:
    """Return the physics-step iterator, with a bar only when one was asked for.

    The bar and a debug log share one stream. ``--no-progress`` is how an
    operator reads the narrative without the bar redrawing over it.

    Args:
        steps: How many physics steps the run takes.
        enabled: Whether to draw the bar.

    Returns:
        A tqdm bar, or a plain range when the bar is off. A machine with no
        tqdm installed gets the plain range either way.
    """
    if not enabled:
        return range(steps)
    return tqdm(range(steps), desc="Simulating", unit="step")


def mujoco_body_id(model: Any, name: str) -> int:
    """Return a body id without importing MuJoCo at module import time."""
    import mujoco

    return int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name))


def run(
    root: Path,
    out: Path,
    seconds: float = 14.0,
    seed: int = 0,
    capture_interval: float = 0.5,
    render: tuple[int, int] = (640, 480),
    window: bool = True,
    video: bool = False,
    camera_video: bool = False,
    frames: bool | None = None,
    fps: int | None = None,
    view_name: str | None = None,
    telemetry_path: Path | None = None,
    telemetry_rate: float = 100.0,
    trajectory_seconds: float = 2.0,
    ground_truth_tracker: bool | None = None,
    belt_speed: float | None = None,
    progress: bool = True,
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
        camera_video: Encode the primary detection camera, with a box on each
            object a segmentation of that same frame covered (`AC-CAM-01`).
            Off unless asked, because the render is the expensive part. A
            machine with no `ffmpeg` runs anyway and says none was written.
        frames: Write annotated PNG captures. When None, defaults to on if a
            window or video was asked for, and off for a headless run with
            neither (`AC-PERF-02`).
        fps: Playback rate of that file, or None for the rate the debug
            configuration names.
        view_name: Which view in the debug configuration to film from, or
            None for the one that file names as its default.
        telemetry_path: CSV output path, or None to disable telemetry.
        telemetry_rate: Telemetry samples per simulated second.
        trajectory_seconds: Future portion of the active plan to draw.
        ground_truth_tracker: Feed downstream selection and planning from
            MuJoCo ground-truth physics instead of tracker estimates, or None
            to read the debug configuration.
        belt_speed: Override belt speed in meters per second, or None to use
            the speed sampled by the scene layout.
        progress: Draw the tqdm bar. Off when the operator wants the debug
            narrative, which shares the terminal with the bar.

    Returns:
        The report.

    Raises:
        DebugRunError: If the world declares no detection camera.
    """
    write_frames = bool(window or video) if frames is None else frames
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    LOGGER.debug(
        "initializing tracker debug run: root=%s out=%s seconds=%.3f seed=%d "
        "capture_interval=%.3f ground_truth_tracker=%s frames=%s",
        root,
        out,
        seconds,
        seed,
        capture_interval,
        ground_truth_tracker,
        write_frames,
    )
    import cv2
    import mujoco

    from clave.tracker.sensors import SensorError

    world_path = root / "configs" / "world" / "sorting_line.yml"
    control_path = root / "configs" / "runtime" / "control.yml"
    debug_path = root / "configs" / "debug" / "tracker.yml"
    fusion_path = root / "configs" / "perception" / "fusion.yml"
    packaging_path = root / "configs" / "perception" / "packaging.yml"
    LOGGER.debug(
        "loading simulation configs: world=%s control=%s debug=%s fusion=%s "
        "packaging=%s",
        world_path,
        control_path,
        debug_path,
        fusion_path,
        packaging_path,
    )
    raw = config.load(world_path)
    sensors = load_sensors(raw)
    try:
        # Every detection camera, not the first one. A line with a single
        # camera over the sensing gate can only ever hand the arm an estimate
        # that has been dead reckoned since the object left that gate, and
        # what the belt model does not predict is exactly what a jaw closing
        # on 8.7 mm of side clearance cannot absorb.
        detection_spec = require_role(sensors, Role.DETECTION)
        detection_camera = detection_spec.source_id
        detecting = of_role(sensors, Role.DETECTION)
    except SensorError as error:
        raise DebugRunError(str(error)) from error

    surface = float(
        config.require(config.require(raw, "belt"), "surface_height_meters", "belt")
    )
    grasp = float(
        config.require(config.require(raw, "arm"), "max_grasp_width_meters", "arm")
    )
    effector = Effector.load(raw)
    control = ControlSettings.load(config.load(control_path))
    debug = config.load(debug_path)
    view = _view(debug, view_name)
    use_ground_truth = (
        ground_truth_tracker
        if ground_truth_tracker is not None
        else bool(debug.get("ground_truth_tracker", False))
    )

    model, data, plan = scene.build(raw, np.random.default_rng(seed), root)
    if belt_speed is not None:
        plan = replace(plan, belt=replace(plan.belt, speed=belt_speed))
    spawn = config.require(raw, "spawn")
    conveyor = belt.Conveyor(
        plan,
        np.random.default_rng(seed),
        config.require_range(spawn, "spacing_meters", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(config.require(spawn, "entry_margin_meters", "spawn")),
    )
    # The belt speed the layout drew is where the loop starts, not where it
    # stays. Its range becomes the drive's limits rather than a distribution.
    drive = config.require_range(
        config.require(raw, "belt"), "speed_meters_per_second", "belt"
    )
    feeding = RateController(
        settings=FeedSettings.load(raw),
        lowest=min(drive.low, plan.belt.speed),
        highest=max(drive.high, plan.belt.speed),
        speed=plan.belt.speed,
    )

    tracker = Tracker(
        intake=Intake(Deployment.SIMULATED, sensors),
        associator=SimulatorIdentity(),
        settings=FusionSettings.load(fusion_path, world_path),
        belt_speed=plan.belt.speed,
        window_exit=belt.window_exit(plan) or 1.034,
        # Seeded from the layout and updated every capture below, because the
        # feed controller moves the belt and a prediction made with the speed
        # the run drew is wrong by however far the controller has trimmed it.
        unmeasured_extent=grasp,
        resolve=resolver_for(load_catalog(packaging_path)),
    )

    LOGGER.debug(
        "resolved simulation parameters: belt_speed=%.3f m/s surface=%.3f m "
        "jaw_opening=%.3f m render=%dx%d view=%s ground_truth_tracker=%s",
        plan.belt.speed,
        surface,
        grasp,
        render[0],
        render[1],
        view_name or "default",
        use_ground_truth,
    )

    width, height = render
    masks = mujoco.Renderer(model, height=height, width=width)
    masks.enable_segmentation_rendering()

    opened, reason = _open_window(cv2, window)
    # Watching RGB is only for PNG dumps, live window, or video (`AC-PERF-01`).
    needs_rgb = write_frames or opened or video
    watching = (
        mujoco.Renderer(
            model,
            height=int(config.require(view, "height", "view")),
            width=int(config.require(view, "width", "view")),
        )
        if needs_rgb
        else None
    )
    eye = mujoco.MjvCamera()
    eye.azimuth = float(config.require(view, "azimuth_degrees", "view"))
    eye.elevation = float(config.require(view, "elevation_degrees", "view"))
    eye.distance = float(config.require(view, "distance_meters", "view"))
    eye.lookat[:] = _lookat(view)

    out.mkdir(parents=True, exist_ok=True)
    tracker_cam = mujoco.Renderer(model, height=180, width=240) if opened else None
    start_wall = time.perf_counter()

    indices = armmod.locate(
        model,
        armmod.ReachBounds(plan.reach_min, plan.reach_max, plan.tool_above_base),
    )
    jaw_geoms = _jaw_collision_geoms(model, indices)
    belt_geom = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "belt"))
    telemetry = None
    if telemetry_path is not None:
        if telemetry_rate <= 0.0:
            raise DebugRunError(f"telemetry rate {telemetry_rate} must be above zero")
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        telemetry = _TelemetryWriter(
            telemetry_path,
            model,
            plan.pool_size,
            telemetry_rate,
        )
        LOGGER.info(
            "telemetry enabled: path=%s rate=%.3f Hz",
            telemetry_path,
            telemetry_rate,
        )
    else:
        LOGGER.info("telemetry disabled")

    metadata_path = out / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            _run_metadata(
                root,
                {
                    "world": world_path,
                    "control": control_path,
                    "debug": debug_path,
                    "fusion": fusion_path,
                    "packaging": packaging_path,
                },
                {
                    "seconds": seconds,
                    "seed": seed,
                    "capture_interval_seconds": capture_interval,
                    "render": list(render),
                    "view": view_name or str(debug.get("default_view", "")),
                    "video": video,
                    "fps": fps,
                    "frames": write_frames,
                    "telemetry_rate": telemetry_rate,
                    "trajectory_seconds": trajectory_seconds,
                    "ground_truth_tracker": use_ground_truth,
                    "belt_speed_override": belt_speed,
                    "window": window,
                    "progress": progress,
                },
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    LOGGER.info("run metadata written: %s", metadata_path)

    if trajectory_seconds < 0.0:
        raise DebugRunError(
            f"trajectory horizon {trajectory_seconds} cannot be negative"
        )
    # Start the arm parked. The model's own initial configuration leaves the
    # flange below the trusted vertical band, so the first pose the controller
    # commands is refused for a reason that has nothing to do with the pose: a
    # line starts with its arm at rest, and so does this.
    _park_the_arm(mujoco, model, data, indices, control.task.park_position)

    base_xy = (float(indices.base_position[0]), float(indices.base_position[1]))

    def keep_inside(pose: NDArray[np.float64]) -> NDArray[np.float64]:
        """Push a pose back into the region the arm is trusted over.

        All three axes. Correcting only the horizontal ones leaves a
        reference reseeded from a flange that has overshot the vertical band
        still outside it, and every pose after that is refused.

        Args:
            pose: The pose.

        Returns:
            The pose, unchanged where it was already inside.
        """
        x, y = armmod.project_into_reach(
            base_xy, float(pose[0]), float(pose[1]), indices.reach
        )
        return np.asarray(
            (
                x,
                y,
                armmod.project_into_band(
                    float(indices.base_position[2]), float(pose[2]), indices.reach
                ),
            ),
            dtype=np.float64,
        )

    def admits(pose: NDArray[np.float64]) -> bool:
        """Whether the arm is trusted at a pose.

        Args:
            pose: The pose.

        Returns:
            Whether it lies inside the region the safety layer enforces.
            Selection and planning ask the same question of the same
            function, so the queue cannot offer what a plan would refuse.
        """
        return bool(armmod.reachable(indices, np.asarray(pose, dtype=float)))

    selector = Selector(
        control.selection,
        admits,
        pickable_in_belt(plan.belt.length, plan.belt.width),
    )
    story = StoryLog()
    watch = AnomalyWatch(story)
    task = TaskMachine(
        control.task,
        control.calibration,
        belt_surface=surface,
        belt_speed=plan.belt.speed,
        motion=control.motion,
        admits=admits,
        chutes=plan.chutes,
        belt_width=plan.belt.width,
        effector=effector,
        story=story,
    )
    goal = None
    refusal: str | None = None
    # How near the flange ever got to what a phase asked for. Without
    # interception the arm trails a marker the belt is carrying, and this is
    # the figure that sizes the interception rather than a guess at it.
    reorders: dict[str, int] = {"appeared": 0, "retired": 0, "anchor": 0}
    head_churn = 0
    previous_head: int | None = None
    closest = float("inf")
    clearance = float("inf")
    contacts = 0
    tilt = 0.0
    # The jaw's own figures, over every tick rather than every capture: a
    # contact with the belt lasts milliseconds and the capture cadence is 0.5 s.
    # How far each visit raised the object it went for, against where that
    # object was resting when the plan was made. A visit can be perfect and
    # this still read zero, which is the whole point of measuring it apart.
    lifts: list[float] = []
    # The arm's own vertical motion, integrated at the physics rate rather than
    # sampled at the capture rate: a grasp that slips unloads the arm mid-lift
    # and that is an acceleration lasting ticks, where every pose the plan asks
    # for is smooth. Peaks are per visit, so a run reports a figure per visit.
    lurches: list[float] = []
    climbs: list[float] = []
    lurch, climb = 0.0, 0.0
    last_flange_z = _flange(indices, data)[2]
    last_rise = 0.0
    # And how the tool was turned against the object it closed on, which only a
    # ground-truth run can measure.
    yaw_errors: list[float] = []
    counted = 0
    # And how near the jaw came to any object at all when it shut, which is
    # the figure that separates a visit tick that missed from a grasp that let go.
    gaps: list[float] = []
    resting: dict[str, float] = {}
    # A place is counted once per object, the first capture its centre is
    # seen below a mouth. Counting every capture after that would report a
    # figure that grows while the object sits there.
    placed: dict[str, int] = {}
    seen_down: dict[str, str] = {}
    misrouted = 0
    opening = [
        float(v)
        for v in config.require(config.require(raw, "chutes"), "mouth_meters", "chutes")
    ]
    mouth = (opening[0], opening[1])
    # Which channel each pool slot's object belongs in, learned as objects
    # spawn rather than read once from an empty belt. Ground truth, and used
    # only to count a misroute: nothing the controller reads comes from here.
    routes: dict[int, str] = {}
    # And how near it got to where the head actually was at that instant.
    # Without interception the commanded pose is as old as the decision
    # interval, so the gap between these two figures is the staleness the
    # belt imposes and is what an interception has to close.
    closest_live = float("inf")
    # Motion integrates its own output, so the reference is seeded once and
    # fed back afterwards. Seeding it from the flange every tick would make it
    # chase the arm instead of leading it.
    motion = Reference(position=_flange(indices, data), speed=0.0)
    # And which way it is going, which a plan needs so its first arc begins
    # where the motion already is instead of asking for a step in velocity.
    moving: NDArray[np.float64] = zeros()
    # The furthest any joint may be commanded to move in one tick. Near a
    # wrist singularity the damped solve still asks for a large joint motion
    # to buy a small Cartesian one, and this is what keeps the command
    # inside what the actuators turn at.
    joint_step = control.servo.max_joint_speed * plan.timestep

    standing: tuple[Any, ...] = ()
    captures = written = drawn = geoms = 0
    believed = out / "records.txt"
    believed.write_text("")
    movie = config.require(debug, "video")
    movie_interval = float(config.require(movie, "interval_seconds", "video"))
    playback = fps or int(config.require(movie, "frames_per_second"))
    recorder = _recorder(view, out, playback, movie_interval) if video else None
    # The detection-camera file is a second render. It stays unbuilt unless
    # asked for, which is what keeps a headless run from paying for it
    # (`AC-CAM-01`).
    camera_recorder = None
    camera_rgb = None
    camera_seg = None
    if camera_video:
        camera_recorder = _camera_recorder(out, width, height, playback)
        if camera_recorder is not None:
            camera_rgb = mujoco.Renderer(model, height=height, width=width)
            camera_seg = mujoco.Renderer(model, height=height, width=width)
            camera_seg.enable_segmentation_rendering()
    next_capture = 0.0
    # Ground truth is the object's own pose, so the arm can read it far faster
    # than the cameras settle. A descent lasts 0.4 s and the capture is 0.5 s,
    # which means a visit steered only at the capture closes on a prediction
    # made before the descent began. Fifty milliseconds keeps that prediction
    # inside a few millimetres at the lateral speeds measured on this belt.
    next_ground_truth = 0.0
    ground_truth_steer = 0.05
    next_frame = 0.0
    telemetry_phase = Phase.STANDBY
    # The acceleration watch is a second difference. The first sample has no
    # previous rise, and comparing it with a seed of zero is not a spike.
    accel_ready = False

    def _record_place(name: str, channel: str) -> None:
        """Count one object crossing a mouth, and say so in the narrative.

        Both the physics tick and the capture look for the crossing. The first
        one to see a body records it; the second finds it already seen. The
        story is emitted here, on that first sighting, because a body can fall
        through a mouth between captures.

        Args:
            name: The body name.
            channel: The chute it crossed.
        """
        nonlocal misrouted
        if name in seen_down:
            return
        seen_down[name] = channel
        placed[channel] = placed.get(channel, 0) + 1
        slot_text = name.rsplit("_", 1)[-1]
        slot = int(slot_text) if slot_text.isdecimal() else None
        belongs = None if slot is None else routes.get(slot)
        item = next(
            (active for active in conveyor.active if active.index == slot),
            None,
        )
        material = "" if item is None else item.material_class
        serial = item.serial if item is not None and use_ground_truth else None
        if belongs is not None and belongs != channel:
            misrouted += 1
            LOGGER.warning(
                "misroute detected: object %s (channel %s) placed in chute %s",
                name,
                belongs,
                channel,
            )
        story.placed(
            data.time,
            name,
            material,
            channel,
            belongs,
            serial=serial,
        )

    def _interruptible(iterable: Any) -> Any:
        try:
            yield from iterable
        except KeyboardInterrupt:
            LOGGER.warning("simulation interrupted by user; finalizing")

    try:
        steps = int(seconds / plan.timestep)
        for _ in _interruptible(_progress(steps, progress)):
            mujoco.mj_step(model, data)
            conveyor.step(model, data)
            # Checked every tick, not every capture. An object released
            # over a mouth falls the belt's height in 0.43 s and the pool
            # recycles it below 0.30 m, so at the half second capture
            # cadence it goes from above the surface to gone without ever
            # being seen crossing.
            routes.update({i.index: i.channel for i in conveyor.active})
            if use_ground_truth:
                for item in conveyor.active:
                    story.note(item.serial, item.material_class, item.channel)
            for name, channel in _placed(
                mujoco, model, data, conveyor, plan.chutes, mouth, surface
            ).items():
                _record_place(name, channel)
            # The feed loop runs at the physics rate and reads the simulator's
            # own arrivals, which is ground truth and is why it is named as
            # such: the tracker's estimate is not usable this far down the
            # belt, so a loop built on it would regulate an opinion.
            while len(conveyor.arrivals) > counted:
                feeding.arrived(conveyor.arrivals[counted])
                counted += 1
            conveyor.speed = feeding.update(data.time, plan.timestep)

            # The deciders run at the capture cadence and the servo runs at
            # the physics rate, because a goal half a second old is still the
            # right goal while a joint command half a second old is a lurch.
            # A planned visit is the exception in one direction only: the
            # plan was decided once, and it is sampled here every tick.
            place = _flange(indices, data)
            was_active = task.active
            active_track = None if task.plan is None else task.plan.track_id
            flown = task.tick(data.time, place)
            rise = (place[2] - last_flange_z) / plan.timestep
            accel_sample = abs(rise - last_rise) / plan.timestep
            if flown is not None or was_active:
                lurch = max(lurch, accel_sample)
                climb = max(climb, rise)
            vertical_acceleration = 0.0 if not accel_ready else accel_sample
            accel_ready = True
            last_flange_z, last_rise = place[2], rise
            command = None
            if flown is not None:
                telemetry_phase = flown.phase
                command = Command(
                    position=flown.position,
                    yaw=flown.yaw,
                    speed=norm(flown.velocity),
                    velocity=flown.velocity,
                    aim=flown.position,
                )
                armmod.hold(data, indices, flown.grip)
                if flown.phase is Phase.HOLD and len(gaps) < len(lifts) + 1:
                    # The first tick of the hold is the instant the jaw
                    # reaches the object, which is the one a pick is decided
                    # on. Later ticks are the carry.
                    nearest = _in_the_jaw(
                        mujoco, model, data, conveyor, _pinch(indices, data)
                    )
                    gaps.append(float("inf") if nearest is None else nearest[1])
                    story.grasp_reading(
                        data.time,
                        None if task.plan is None else task.plan.track_id,
                        gaps[-1],
                    )
                    # And how the jaw is turned against the object it closed
                    # on, which is ground truth and only available from it: a
                    # tracker estimate has no body to measure against. Folded
                    # into the 90 degrees a jaw is symmetric about, because
                    # closing along an object's other axis is the same grasp.
                    if nearest is not None:
                        _log_closure(
                            mujoco,
                            model,
                            data,
                            indices,
                            nearest[0],
                            command,
                            place,
                        )
                    if use_ground_truth and command.yaw is not None and nearest:
                        body = _body_yaw(mujoco, model, data, nearest[0])
                        if body is not None:
                            turned = math.degrees(command.yaw) - body
                            yaw_errors.append(abs((turned + 45.0) % 90.0 - 45.0))
                # Motion resumes from where the plan left the reference, so
                # the park move after a visit does not start by jumping back
                # to wherever the reference had been before the plan.
                motion = Reference(position=command.position, speed=command.speed)
            elif was_active:
                telemetry_phase = Phase.STANDBY
                # The plan ran out on this tick and the visit is recorded.
                # Open the jaw, stand still, and let the next capture decide.
                armmod.hold(data, indices, JAW_OPEN)
                nearest = _in_the_jaw(
                    mujoco, model, data, conveyor, _pinch(indices, data)
                )
                lift = (
                    0.0
                    if nearest is None or nearest[0] not in resting
                    else _object_place(mujoco, model, data, nearest[0])[2]
                    - resting[nearest[0]]
                )
                lifts.append(lift)
                story.visit_ended(
                    data.time,
                    active_track,
                    lift,
                    held=lift >= GRASPED_METERS,
                )
                lurches.append(lurch)
                climbs.append(climb)
                lurch, climb = 0.0, 0.0
                resting = {}
                goal = None
                moving = zeros()
                motion = Reference(position=keep_inside(place), speed=0.0)
            elif goal is not None:
                command = toward(
                    motion,
                    goal,
                    plan.timestep,
                    control.motion,
                    feeding.speed,
                    int(data.time * NANOS_PER_SECOND),
                    keep_inside,
                )
                motion = Reference(position=command.position, speed=command.speed)

            tick_refusal: str | None = None
            if command is not None:
                moving = command.velocity
                # Lead cancels lag on a moving approach. Through DESCEND/HOLD the
                # command should already match the object; extrapolating a large
                # lateral quintic residual (seed-0 peak |vy| ≈ 0.94 m/s) only
                # throws the jaw past the grasp.
                lead = (
                    0.0
                    if flown is not None and flown.phase in (Phase.DESCEND, Phase.HOLD)
                    else control.servo.lead_seconds
                )
                stepped = follow(
                    model,
                    data,
                    indices,
                    command,
                    control.servo.gain,
                    max_joint_step=joint_step,
                    lead_seconds=lead,
                    keep_inside=keep_inside,
                )
                if stepped.refusal is not None:
                    refusal = stepped.refusal
                    tick_refusal = stepped.refusal
                elif flown is not None or (
                    goal is not None and goal.phase in _VISITING
                ):
                    closest = min(closest, distance(place, command.position))

            # Written here rather than before the decisions, so a row's phase and
            # commanded pose are the ones that tick flew on, and the jaw's own
            # clearance with them: the figure that says whether the pads were
            # anywhere near the belt, which no pose in this file can answer
            # because a pose is the flange and the jaw hangs below it.
            jaw = _jaw_state(
                mujoco, model, data, indices, jaw_geoms, belt_geom, surface
            )
            clearance = min(clearance, jaw.clearance)
            contacts += int(jaw.contact)
            tilt = max(tilt, jaw.tilt_degrees)
            if task.plan is not None:
                subject = task.plan.track_id
            elif active_track is not None:
                subject = active_track
            elif goal is None:
                subject = None
            else:
                subject = goal.track_id
            tracking_error = (
                None if command is None else distance(place, command.position)
            )
            watch.observe(
                data.time,
                contact=jaw.contact,
                clearance=jaw.clearance,
                vertical_acceleration=vertical_acceleration,
                tracking_error=tracking_error,
                refusal=tick_refusal,
                track_id=subject,
            )
            if telemetry is not None:
                telemetry.write(
                    model,
                    data,
                    indices,
                    conveyor,
                    feeding.speed,
                    telemetry_phase,
                    task.active,
                    jaw,
                    command,
                )

            # The video and live window render on their own cadence. The
            # capture cadence is what the tracker decides at, and watching
            # a decision rate is watching an arm teleport. The detection
            # camera shares that cadence (`AC-CAM-01`).
            due = data.time >= next_frame
            line_view = (recorder is not None or opened) and watching is not None
            if due and (line_view or camera_recorder is not None):
                next_frame = data.time + movie_interval
            if due and camera_recorder is not None:
                _write_camera_frame(
                    camera_rgb,
                    camera_seg,
                    model,
                    data,
                    detection_camera,
                    camera_recorder,
                )
            if due and line_view:
                frame = _painted(
                    watching,
                    data,
                    eye,
                    standing,
                    control,
                    surface,
                    task,
                    trajectory_seconds,
                    indices,
                )
                if recorder is not None:
                    recorder.write(frame)
                if opened and tracker_cam is not None:
                    tracker_cam.update_scene(data, camera=detection_camera)
                    _without_shadows(tracker_cam)
                    gate_img = tracker_cam.render()

                    display = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    gate_bgr = cv2.cvtColor(gate_img, cv2.COLOR_RGB2BGR)

                    gh, gw = gate_bgr.shape[:2]
                    y1 = 15
                    y2 = y1 + gh
                    x2 = display.shape[1] - 15
                    x1 = x2 - gw

                    display[y1:y2, x1:x2] = gate_bgr
                    cv2.rectangle(
                        display,
                        (x1 - 1, y1 - 1),
                        (x2 + 1, y2 + 1),
                        (0, 255, 255),
                        2,
                    )
                    cv2.putText(
                        display,
                        "TRACKER (GATE CAM)",
                        (x1 + 6, y1 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (0, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )

                    phase_name = "standby" if goal is None else goal.phase.value
                    hud = (
                        f"SIM: {data.time:5.2f}s | BELT: {feeding.speed:4.2f} m/s | "
                        f"PHASE: {phase_name.upper()}"
                    )
                    cv2.putText(
                        display,
                        hud,
                        (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        display,
                        f"TRACKS: {len(standing)} | GRASPS: {len(lifts)}",
                        (20, 55),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.50,
                        (200, 200, 200),
                        1,
                        cv2.LINE_AA,
                    )

                    target_wall = start_wall + data.time
                    now_wall = time.perf_counter()
                    sleep_sec = target_wall - now_wall
                    if sleep_sec > 0.001:
                        time.sleep(sleep_sec)

                    cv2.imshow("clave tracker debug", display)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        break

            if use_ground_truth and task.active and data.time >= next_ground_truth:
                next_ground_truth = data.time + ground_truth_steer
                now_gt = int(data.time * NANOS_PER_SECOND)
                standing = ground_truth_markers(
                    model,
                    data,
                    conveyor.active,
                    plan,
                    effector,
                    surface,
                    now_gt,
                    tracker.window_exit,
                    feeding.speed,
                )
                flange = _flange(indices, data)
                queue = selector.update(standing, flange, feeding.speed, now_gt)
                goal = task.step(queue, flange, data.time, refusal, moving)
                refusal = None

            if data.time < next_capture:
                continue
            next_capture = data.time + capture_interval
            captures += 1
            now = int(data.time * NANOS_PER_SECOND)
            # Everything that predicts along the belt reads the speed the belt
            # is running at, not the one the layout drew. The feed controller
            # moves it, and over a two second interception a one percent error
            # is millimetres against a jaw with eight of clearance.
            tracker.belt_speed = feeding.speed
            task.belt_speed = feeding.speed

            for eye_on in detecting:
                masks.update_scene(data, camera=eye_on.source_id)
                found = segment_masks(model, masks.render())
                if not found:
                    continue
                for reading in detections_from_masks(
                    found,
                    source_id=eye_on.source_id,
                    observed_at_nanos=now,
                    camera=eye_on.position,
                    optics=eye_on.optics,
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
                            position=np.asarray(
                                (position[0], position[1], position[2]),
                                dtype=np.float64,
                            ),
                        ),
                    ),
                    at_nanos=now,
                )

            records = tracker.settle(at_nanos=now)
            if use_ground_truth:
                standing = ground_truth_markers(
                    model,
                    data,
                    conveyor.active,
                    plan,
                    effector,
                    surface,
                    now,
                    tracker.window_exit,
                    feeding.speed,
                )
            else:
                standing = markers_for(records, effector, surface)

            flange = _flange(indices, data)
            if not use_ground_truth:
                for record in records:
                    try:
                        chute = channel_of(record.material)
                    except KeyError:
                        chute = ""
                    story.note(record.track_id, record.material, chute)
            queue = selector.update(standing, flange, feeding.speed, now)

            routes.update({item.index: item.channel for item in conveyor.active})
            for name, channel in _placed(
                mujoco,
                model,
                data,
                conveyor,
                plan.chutes,
                (mouth[0], mouth[1]),
                surface,
            ).items():
                _record_place(name, channel)

            for trigger in queue.reasons:
                reorders[trigger] += 1
            head_id = None if queue.head is None else queue.head.track_id
            still_waiting = previous_head is not None and any(
                item.track_id == previous_head for item in queue.order
            )
            if previous_head is not None and head_id != previous_head and still_waiting:
                head_churn += 1
            if queue.recomputed or head_id != previous_head:
                story.queue(
                    data.time,
                    queue.reasons,
                    head_id,
                    previous_head,
                    still_waiting,
                )
            previous_head = head_id
            goal = task.step(queue, flange, data.time, refusal, moving)
            refusal = None
            if goal.phase in _VISITING:
                head = next(
                    (item for item in standing if item.track_id == goal.track_id),
                    None,
                )
                if head is not None:
                    closest_live = min(closest_live, distance(flange, head.flange))
            if goal.phase is Phase.FAULT:
                # The arm was told to hold, so the reference comes back to the
                # pose it is holding rather than resuming from wherever it had
                # run ahead to. It is projected on the way: the flange itself
                # can cut the corner of the hole while tracking, and reseeding
                # the reference inside it is what turned one refusal into
                # every refusal after it.
                motion = Reference(position=keep_inside(flange), speed=0.0)
                moving = zeros()
            if task.active and not resting:
                # Snapshot how high everything is lying before the arm
                # touches anything, so a lift is measured against where the
                # object actually was.
                resting = _resting(mujoco, model, data, conveyor)

            # The markers go in before the render and live only until the next
            # update_scene, so they reach this view and no other. The gate the
            # tracker reads was rendered above and carries none of them.
            if watching is None or not write_frames:
                drawn = len(standing)
                geoms = 0
            else:
                geoms = _markers_on(watching, data, eye, standing, control, surface)
                geoms += _trajectory_on(
                    watching.scene,
                    task,
                    data.time,
                    trajectory_seconds,
                    _flange(indices, data),
                )
                drawn = len(standing)
                canvas = watching.render()

                cv2.imwrite(
                    str(out / f"frame_{captures:04d}.png"),
                    cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR),
                )
                written += 1
            _write_beliefs(believed, captures, now, records)
    finally:
        if watching is not None:
            watching.close()
        masks.close()
        if tracker_cam is not None:
            tracker_cam.close()
        if recorder is not None:
            recorder.close()
        if camera_rgb is not None:
            camera_rgb.close()
        if camera_seg is not None:
            camera_seg.close()
        if camera_recorder is not None:
            camera_recorder.close()
        if telemetry is not None:
            telemetry.close()
        if opened:
            cv2.destroyAllWindows()

    report = DebugRunReport(
        captures=captures,
        tracks=len(tracker.settle(at_nanos=int(data.time * NANOS_PER_SECOND))),
        reorders=reorders,
        head_churn=head_churn,
        served=task.served,
        missed=task.missed,
        arrivals=task.arrivals,
        lifts=tuple(lifts),
        jaw_gaps=tuple(gaps),
        abandoned=task.abandoned,
        worst_aim_drift=task.worst_aim_drift,
        grasp_yaw_errors=tuple(yaw_errors),
        lurches=tuple(lurches),
        climbs=tuple(climbs),
        placed=dict(placed),
        misrouted=misrouted,
        feed_rate=feeding.settings.rate,
        measured_rate=feeding.measured,
        belt_speed=feeding.speed,
        profile=control.task.profile.value,
        closest_approach=None if closest == float("inf") else closest,
        closest_live=None if closest_live == float("inf") else closest_live,
        faults=task.faults,
        phase="none" if goal is None else goal.phase.value,
        drawn=drawn,
        geoms=geoms,
        frames_written=written,
        output=out,
        video_path=None if recorder is None else recorder.settings.path,
        camera_video_path=(
            None if camera_recorder is None else camera_recorder.settings.path
        ),
        telemetry_path=telemetry_path,
        windowed=opened,
        reason=reason,
        ground_truth=use_ground_truth,
        min_jaw_clearance=None if clearance == float("inf") else clearance,
        belt_contacts=contacts,
        worst_tool_tilt_degrees=tilt,
        metadata_path=metadata_path,
    )
    written_report = out / "report.json"
    written_report.write_text(
        json.dumps(_report_document(report), indent=2, sort_keys=True) + "\n"
    )
    (out / "report.txt").write_text("\n".join(report_lines(report)) + "\n")
    LOGGER.info("run report written: %s and %s", written_report, out / "report.txt")
    return replace(report, report_path=written_report)


def _report_document(report: DebugRunReport) -> dict[str, Any]:
    """Return a report as JSON a reader can diff against another run's.

    AC-MOVE-55. The report used to be printed and nothing else, so a run's
    figures died with the terminal they were printed on: the run this branch
    was opened for lost its own grasp distances that way, and reconstructing
    them from telemetry meant inferring which of thirteen objects each visit
    had been about. Written beside the artifacts instead, in both a machine
    form and the text a reader already knows how to scan.

    Args:
        report: The report.

    Returns:
        Its fields as JSON-compatible values: paths as strings, tuples as
        lists at any depth, and everything else as it is.
    """
    return {name: _plain(getattr(report, name)) for name in report.__dataclass_fields__}


def _plain(value: Any) -> Any:
    """Return one of a report's values as data JSON can carry.

    Args:
        value: The value.

    Returns:
        The same value with paths read as strings and every tuple -- at any
        depth, because a visit given up is a pair inside a tuple -- read as a
        list.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return value


def report_lines(report: DebugRunReport) -> tuple[str, ...]:
    """Return the run's report as the lines it is printed and filed as.

    One formatter for both, because a report that reads one way on a terminal
    and another way in the file beside it is two reports, and a reader
    comparing them has no way to tell which one the numbers came from.

    Args:
        report: The report.

    Returns:
        The lines, in the order a reader scans them: what the run was, what the
        line did, and what the arm did about it.
    """
    lines: list[str] = []
    if report.ground_truth:
        lines.append("  targets         ground truth (MuJoCo physics)")
    lines.append(f"  captures        {report.captures}")
    lines.append(f"  tracks open     {report.tracks}")
    lines.append(f"  markers on last {report.drawn}, as {report.geoms} geoms")
    rebuilt = ", ".join(f"{why} {count}" for why, count in report.reorders.items())
    lines.append(f"  queue rebuilt   {rebuilt}, of {report.captures} captures")
    lines.append(
        f"  head swapped    {report.head_churn} times with the old head still there"
    )
    lines.append(f"  profile         {report.profile}")
    lines.append(
        f"  feed rate       {report.measured_rate:.3f} of "
        f"{report.feed_rate:.3f} objects/s, belt at {report.belt_speed:.3f} m/s"
    )
    lines.append(f"  visits served   {len(report.served)} {list(report.served)}")
    if report.missed:
        lines.append(f"  no interception {len(report.missed)} {list(report.missed)}")
    if report.abandoned:
        each = "; ".join(f"{track}: {why}" for track, why in report.abandoned)
        lines.append(f"  visits given up {len(report.abandoned)} ({each})")
    if report.worst_aim_drift is not None:
        lines.append(
            f"  aim checked     worst {report.worst_aim_drift * 1000:.0f} mm between "
            f"the plan and the freshest estimate"
        )
    if report.arrivals:
        # Median rather than mean, and the count of outliers beside it. The
        # mean lied: sixteen visits at 2 to 4 mm and one at 688 mm reads as
        # "43 mm", which describes no visit that happened.
        ranked = sorted(report.arrivals)
        middle = ranked[len(ranked) // 2] * 1000
        stray = sum(1 for gap in ranked if gap > 0.050)
        lines.append(
            f"  arrival error   median {middle:.1f} mm, worst "
            f"{ranked[-1] * 1000:.1f} mm, {stray} over 50 mm"
        )
    if report.jaw_gaps:
        each = ", ".join(f"{gap * 1000:.0f}" for gap in report.jaw_gaps)
        lines.append(f"  jaw to object   {each} mm when the jaw shut")
    if report.grasp_yaw_errors:
        each = ", ".join(f"{error:.1f}" for error in report.grasp_yaw_errors)
        lines.append(f"  tool turned off {each} deg from the object's own axis")
    if report.placed or report.misrouted:
        total = sum(report.placed.values())
        each = ", ".join(f"{c}: {n}" for c, n in sorted(report.placed.items()))
        lines.append(f"  placed          {total} down a chute ({each})")
        lines.append(f"  misrouted       {report.misrouted} of {total}")
    if report.lifts:
        held = sum(1 for lift in report.lifts if lift >= GRASPED_METERS)
        each = ", ".join(f"{lift * 1000:.0f}" for lift in report.lifts)
        lines.append(
            f"  grasps held     {held} of {len(report.lifts)}, lifts {each} mm"
        )
    if report.lurches:
        each = ", ".join(f"{value:.1f}" for value in report.lurches)
        lines.append(f"  vertical lurch  {each} m/s2 at worst per visit")
    lines.append(f"  faults          {len(report.faults)}")
    for track_id, why in report.faults:
        lines.append(f"    track {track_id}: {why}")
    lines.append(f"  ended in        {report.phase}")
    if report.closest_approach is not None:
        lines.append(f"  to commanded    {report.closest_approach * 1000:.0f} mm")
    if report.closest_live is not None:
        lines.append(f"  to the object   {report.closest_live * 1000:.0f} mm")
    if report.min_jaw_clearance is not None:
        lines.append(
            f"  jaw clearance   {report.min_jaw_clearance * 1000:.1f} mm above the "
            f"belt, {report.belt_contacts} ticks in contact"
        )
    if report.worst_tool_tilt_degrees is not None:
        lines.append(
            f"  tool tilt       {report.worst_tool_tilt_degrees:.1f} deg off the "
            f"belt normal at worst"
        )
    lines.append(f"  frames written  {report.frames_written} to {report.output}")
    if report.video_path is not None:
        lines.append(f"  video           {report.video_path}")
    if report.camera_video_path is not None:
        lines.append(f"  camera video    {report.camera_video_path}")
    if report.telemetry_path is not None:
        lines.append(f"  telemetry       {report.telemetry_path}")
    lines.append(f"  metadata        {report.metadata_path}")
    if report.report_path is not None:
        lines.append(f"  report          {report.report_path}")
    return tuple(lines)


def _git(root: Path, *args: str) -> str | None:
    """Return what git says about the tree, or None when it cannot be asked.

    A debug run has to work in a checkout without git and in a copy of the
    source with no repository at all, so an unanswerable question is recorded
    as unanswerable rather than raised.

    Args:
        root: The repository root.
        args: The arguments after `git`.

    Returns:
        The stripped standard output, or None.
    """
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _run_metadata(
    root: Path,
    paths: dict[str, Path],
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return what a reader needs to trace this run's numbers to their inputs.

    AC-MOVE-52, extended by AC-MOVE-54. A revision alone is not enough: a dirty
    tree has no revision that describes it, so that is recorded beside it, and
    a digest per configuration is what lets a number be compared against a tree
    that has since moved on. This exists because a run's artifacts could not be
    attributed to a tree, and the phase durations in its telemetry did not
    reproduce from the configuration the tree carried.

    That much still did not make a run reproducible. The seed, the duration and
    the view are not configuration: they are the command somebody typed, and a
    run whose seed is not recorded cannot be run again even by whoever wrote
    it. A reader trying to reproduce a published run hit exactly that: the
    re-run at seed 0 produced a different world, and there was nothing in the
    artifacts to say whether the seed or the world was the difference.

    Args:
        root: The repository root.
        paths: Where each configuration lives, by name.
        parameters: What the run was asked for -- the seed, the duration, the
            view, the flags -- or None for a caller that has none to record.

    Returns:
        The record, in the shape the rest of the repository records a run's
        inputs: a digest per configuration, where it came from, and what the
        run was asked to do.
    """
    from clave.experiment.run import config_digest

    status = _git(root, "status", "--porcelain")
    return {
        "revision": _git(root, "rev-parse", "HEAD"),
        "dirty": None if status is None else bool(status),
        "config_digests": {
            name: config_digest(config.load(path)) for name, path in paths.items()
        },
        "config_paths": {name: str(path) for name, path in paths.items()},
        "parameters": dict(parameters or {}),
    }


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


def _park_the_arm(
    mujoco: Any, model: Any, data: Any, indices: Any, park: NDArray[np.float64]
) -> None:
    """Put the arm at its park pose before the run starts.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state, modified in place.
        indices: The arm indices.
        park: Where the arm rests.

    Raises:
        DebugRunError: If the park pose does not solve. That is a
            configuration error rather than a run-time one, and finding it
            here beats a run that faults on every tick.
    """

    try:
        angles = armmod.solve(model, data, indices, np.array(park, dtype=float))
    except armmod.ReachError as error:
        raise DebugRunError(f"the park pose does not solve: {error}") from error
    for slot, joint in enumerate(indices.joint_ids):
        data.qpos[model.jnt_qposadr[joint]] = angles[slot]
    for slot, actuator in enumerate(indices.actuator_ids):
        data.ctrl[actuator] = angles[slot]
    mujoco.mj_forward(model, data)


def _pinch_position_world(indices: Any, data: Any) -> NDArray[np.float64]:
    """Return where the jaw closes, as three meters in world frame.

    Args:
        indices: The arm indices.
        data: Its state, with forward kinematics already current.

    Returns:
        The pinch site's position. Every commanded pose is against the
        flange, because that is what the trusted reach was swept against,
        and this is where the object actually ends up.
    """
    place = data.site_xpos[indices.pinch_site]
    return np.asarray(
        (float(place[0]), float(place[1]), float(place[2])), dtype=np.float64
    )


_pinch = _pinch_position_world


def _flange_position_world(indices: Any, data: Any) -> NDArray[np.float64]:
    """Return where the flange stands, as three meters in world frame.

    Args:
        indices: The arm indices.
        data: Its state, with forward kinematics already current.

    Returns:
        The position.
    """
    place = armmod.end_effector_position(data, indices)
    return np.asarray(
        (float(place[0]), float(place[1]), float(place[2])), dtype=np.float64
    )


_flange = _flange_position_world


def _object_position_world(
    mujoco: Any, model: Any, data: Any, name: str
) -> NDArray[np.float64]:
    """Return where one conveyor object stands, as three meters in world frame.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        name: The body's name.

    Returns:
        The center of mass, not the body origin. These meshes carry their
        origin wherever the scanner left it, which for most of the set is
        the base, so an origin height answers a different question from the
        one a lift is asking.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    place = data.xipos[body]
    return np.asarray(
        (float(place[0]), float(place[1]), float(place[2])), dtype=np.float64
    )


_object_place = _object_position_world


def _placed(
    mujoco: Any,
    model: Any,
    data: Any,
    conveyor: Any,
    chutes: dict[str, NDArray[np.float64]],
    mouth: tuple[float, float],
    surface: float,
) -> dict[str, str]:
    """Return which objects have gone down a chute, and which one.

    A place is a plane crossing, which is what
    `docs/requirements/sorting-outputs.md` settled on: an object whose
    centre is below the belt surface and inside a mouth's footprint has
    left the line through that opening. Nothing models the chute's
    interior, because nothing below the opening is in scope.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        conveyor: The belt, for the objects still on it.
        chutes: Where each channel's mouth stands.
        mouth: Mouth size, along travel and across it.
        surface: Height of the belt surface.

    Returns:
        Body name to the channel it went down, for those that have.
    """
    gone: dict[str, str] = {}
    for item in conveyor.active:
        x, y, z = _object_place(mujoco, model, data, item.name)
        if z >= surface:
            continue
        for channel, (cx, cy, _) in chutes.items():
            if abs(x - cx) <= mouth[0] / 2.0 and abs(y - cy) <= mouth[1] / 2.0:
                gone[item.name] = channel
                break
    return gone


def _resting(mujoco: Any, model: Any, data: Any, conveyor: Any) -> dict[str, float]:
    """Return how high every object on the belt is lying right now.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        conveyor: The belt.

    Returns:
        Each body's name against the height of its center of mass. Taken
        before a plan begins, so a lift is measured against where the object
        actually was rather than against the belt: these meshes rest with
        their centers anywhere from twenty to seventy millimetres up.
    """
    return {
        item.name: _object_place(mujoco, model, data, item.name)[2]
        for item in conveyor.active
    }


def _in_the_jaw(
    mujoco: Any, model: Any, data: Any, conveyor: Any, pinch: NDArray[np.float64]
) -> tuple[str, float] | None:
    """Return the object the jaw is closed on, and how far off center it sits.

    Found by proximity to the pinch site rather than by identity. Which
    object the arm believed it was going for is the tracker's claim, and a
    measurement that trusted it would report the claim rather than the
    grasp; what is in the jaw is in the jaw.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        conveyor: The belt.
        pinch: Where the jaw closes.

    Returns:
        The body's name and its distance from the pinch site, or None when
        the belt is empty.
    """
    places = [_object_place(mujoco, model, data, item.name) for item in conveyor.active]
    if not places:
        return None
    gaps = np.linalg.norm(
        np.asarray(places, dtype=np.float64) - np.asarray(pinch), axis=1
    )
    at = int(np.argmin(gaps))
    return (conveyor.active[at].name, float(gaps[at]))


def _fold_jaw_degrees(delta_degrees: float) -> float:
    """Return how far two headings are apart, folded into a jaw's symmetry.

    A jaw is symmetric about 90 degrees, so 40 degrees and 50 degrees the
    other way are the same miss. The fold is `(delta + 45) mod 90 - 45`.

    Args:
        delta_degrees: One heading minus the other, in degrees.

    Returns:
        The absolute miss, in degrees, from 0 to 45.
    """
    return abs((delta_degrees + 45.0) % 90.0 - 45.0)


def _short_axis_degrees(mujoco: Any, model: Any, data: Any, name: str) -> float | None:
    """Return the yaw of an object's short axis in the belt plane, in degrees.

    The jaw closes horizontally. The direction it has to match is the short
    direction of the object after it has been rotated into the world, projected
    onto the belt, not the body's Euler yaw. Those two agree while the object
    lies flat on the axes it was scanned in, and they come apart as soon as it
    tips.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        name: The body's name.

    Returns:
        The yaw in degrees, or None when the shape has no preferred axis.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    if body < 0:
        return None
    geom = int(model.body_geomadr[body])
    if geom < 0:
        return None
    rotation = data.geom_xmat[geom].reshape(3, 3)
    origin = np.asarray(data.geom_xpos[geom], dtype=np.float64)
    kind = model.geom_type[geom]
    if kind == mujoco.mjtGeom.mjGEOM_BOX:
        size = np.asarray(model.geom_size[geom], dtype=np.float64)
        signs = np.array(
            [[x, y, z] for x in (-1.0, 1.0) for y in (-1.0, 1.0) for z in (-1.0, 1.0)]
        )
        local = signs * size
    elif kind == mujoco.mjtGeom.mjGEOM_MESH:
        mesh = int(model.geom_dataid[geom])
        if mesh < 0:
            return None
        local = _mesh_vertices(model, mesh)
    else:
        return None
    flat = (local @ rotation.T + origin)[:, :2]
    centered = flat - flat.mean(axis=0)
    _values, vectors = np.linalg.eigh(centered.T @ centered)
    minor = vectors[:, 0]
    return math.degrees(math.atan2(float(minor[1]), float(minor[0])))


def _free_velocity(
    mujoco: Any, model: Any, data: Any, name: str
) -> tuple[NDArray[np.float64], float] | None:
    """Return a free body's linear velocity and its spin about the belt normal.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        name: The body's name.

    Returns:
        The linear velocity in meters per second and the spin in radians per
        second, or None when the body has no free joint.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    if body < 0:
        return None
    joint = int(model.body_jntadr[body])
    if joint < 0 or model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_FREE:
        return None
    address = int(model.jnt_dofadr[joint])
    linear = np.asarray(
        (
            float(data.qvel[address]),
            float(data.qvel[address + 1]),
            float(data.qvel[address + 2]),
        ),
        dtype=np.float64,
    )
    geom = int(model.body_geomadr[body])
    rotation = data.geom_xmat[geom].reshape(3, 3)
    spin = data.qvel[address + 3 : address + 6]
    about_up = float(rotation[2] @ np.asarray(spin, dtype=np.float64))
    return linear, about_up


def _log_closure(
    mujoco: Any,
    model: Any,
    data: Any,
    indices: Any,
    name: str,
    command: Command,
    flange: NDArray[np.float64],
) -> None:
    """Log where a closing jaw sat relative to the object and to its command.

    Three distances, because a grasp fails for different reasons that one
    number confuses. The flange against the command is the inverse kinematics.
    The command against the object, in the belt plane, is the plan. The pinch
    against the object is what the jaw actually did, which is both of those
    plus the tool not being vertical. The yaw is split the same way: the tool
    against the command, and the command against the object's own short axis.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        indices: The arm indices.
        name: The nearest object's body name.
        command: The pose the plan asked for on this tick.
        flange: Where the flange actually is.
    """
    pinch = _pinch(indices, data)
    center = _object_place(mujoco, model, data, name)
    origin = _body_origin(mujoco, model, data, name)
    centroid = _geometric_center(mujoco, model, data, name)

    def _offset(
        left: NDArray[np.float64], right: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        return np.asarray(
            (
                (float(left[0]) - float(right[0])) * 1000.0,
                (float(left[1]) - float(right[1])) * 1000.0,
                (float(left[2]) - float(right[2])) * 1000.0,
            ),
            dtype=np.float64,
        )

    gap = _offset(pinch, center)
    origin_gap = None if origin is None else _offset(origin, center)
    shape_gap = None if centroid is None else _offset(centroid, center)
    pinch_shape = None if centroid is None else _offset(pinch, centroid)
    aim = tuple((command.position[axis] - center[axis]) * 1000.0 for axis in range(2))
    aim_origin = (
        None
        if origin is None
        else tuple(
            (command.position[axis] - origin[axis]) * 1000.0 for axis in range(2)
        )
    )
    tracked = distance(flange, command.position) * 1000.0
    tool = math.degrees(armmod.tool_yaw(data, indices))
    ordered = None if command.yaw is None else math.degrees(command.yaw)
    body = _body_yaw(mujoco, model, data, name)
    short = _short_axis_degrees(mujoco, model, data, name)
    motion = _free_velocity(mujoco, model, data, name)

    def _yaw(left: float | None, right: float | None) -> str:
        if left is None or right is None:
            return "n/a"
        return f"{_fold_jaw_degrees(left - right):.1f}"

    if motion is None:
        velocity, spin = "n/a", "n/a"
    else:
        linear, rate = motion
        velocity = f"({linear[0]:+.3f}, {linear[1]:+.3f}, {linear[2]:+.3f})"
        spin = f"{rate:+.2f}"

    def _millimetres(offset: NDArray[np.float64] | None) -> str:
        if offset is None:
            return "n/a"
        return f"({offset[0]:+.0f}, {offset[1]:+.0f}, {offset[2]:+.0f})"

    LOGGER.info(
        "closure at %.3f s on %s: pinch-com dx=%+.0f dy=%+.0f dz=%+.0f mm; "
        "pinch-shape %s mm; origin-com %s mm; shape-com %s mm; "
        "command-com dx=%+.0f dy=%+.0f mm; command-origin %s mm; "
        "flange-command %.1f mm; "
        "tool-command yaw %s deg; command-body yaw %s deg; "
        "command-short-axis yaw %s deg; object v=%s m/s spin=%s rad/s",
        data.time,
        name,
        gap[0],
        gap[1],
        gap[2],
        _millimetres(pinch_shape),
        _millimetres(origin_gap),
        _millimetres(shape_gap),
        aim[0],
        aim[1],
        (
            "n/a"
            if aim_origin is None
            else f"({aim_origin[0]:+.0f}, {aim_origin[1]:+.0f})"
        ),
        tracked,
        _yaw(tool, ordered),
        _yaw(ordered, body),
        _yaw(ordered, short),
        velocity,
        spin,
    )


def _body_origin(
    mujoco: Any, model: Any, data: Any, name: str
) -> NDArray[np.float64] | None:
    """Return a body's frame origin, which is where a marker is drawn from.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        name: The body's name.

    Returns:
        The origin in world frame meters, or None when the body is absent.
        This is `xpos`, not the centre of mass: scanned meshes keep their
        origin wherever the scan left it.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    if body < 0:
        return None
    place = data.xpos[body]
    return np.asarray(
        (float(place[0]), float(place[1]), float(place[2])), dtype=np.float64
    )


def _geometric_center(
    mujoco: Any, model: Any, data: Any, name: str
) -> NDArray[np.float64] | None:
    """Return the centre of an object's geometry in the world, not its origin.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        name: The body's name.

    Returns:
        The mean of the geometry in world frame meters, or None when the body
        has no box or mesh to read one from.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    if body < 0:
        return None
    geom = int(model.body_geomadr[body])
    if geom < 0:
        return None
    rotation = data.geom_xmat[geom].reshape(3, 3)
    origin = np.asarray(data.geom_xpos[geom], dtype=np.float64)
    kind = model.geom_type[geom]
    if kind == mujoco.mjtGeom.mjGEOM_BOX:
        local = np.zeros(3)
    elif kind == mujoco.mjtGeom.mjGEOM_MESH:
        mesh = int(model.geom_dataid[geom])
        if mesh < 0:
            return None
        local = _mesh_vertices(model, mesh).mean(axis=0)
    else:
        local = np.zeros(3)
    world = rotation @ local + origin
    return np.asarray(
        (float(world[0]), float(world[1]), float(world[2])), dtype=np.float64
    )


def _body_yaw(mujoco: Any, model: Any, data: Any, name: str) -> float | None:
    """Return an object's own rotation about the belt normal, in degrees.

    Read from the body's quaternion rather than from anything the tracker
    published, because the question this answers is whether the jaw closed
    along the object's own short axis -- and a figure computed from the
    estimate that asked for the pose would agree with itself however the
    object was lying.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state.
        name: The body's name in the model.

    Returns:
        The yaw in degrees, or None when the body carries no free joint to
        read a rotation from.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    if body < 0:
        return None
    quat = data.xquat[body]
    w, x, y, z = (float(quat[i]) for i in range(4))
    return math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


# Green reads on the belt without sitting on a material the line already paints.
_BOX_RGB = (0, 255, 0)


def bounds_of(runs: Sequence[tuple[int, int, int]]) -> tuple[int, int, int, int]:
    """Return inclusive pixel bounds of run-length coverage.

    Args:
        runs: `(row, start_column, length)` triples from one object's mask.

    Returns:
        `(x_min, y_min, x_max, y_max)`.
    """
    x_min = min(start for _, start, _ in runs)
    y_min = min(row for row, _, _ in runs)
    x_max = max(start + length - 1 for _, start, length in runs)
    y_max = max(row for row, _, _ in runs)
    return x_min, y_min, x_max, y_max


def paint_boxes(
    frame: NDArray[np.uint8],
    boxes: Sequence[tuple[int, int, int, int]],
) -> NDArray[np.uint8]:
    """Draw inclusive box borders on an RGB frame.

    The boxes are the pixels each object covered in a segmentation of this
    same frame (`AC-CAM-03`). Pixels outside a box stay as the camera
    rendered them.

    Args:
        frame: Height by width by three, RGB.
        boxes: Inclusive `(x_min, y_min, x_max, y_max)` bounds.

    Returns:
        The same frame, with borders written in.
    """
    height, width = frame.shape[:2]
    color = np.asarray(_BOX_RGB, dtype=np.uint8)
    for x0, y0, x1, y1 in boxes:
        left = min(max(int(x0), 0), width - 1)
        right = min(max(int(x1), 0), width - 1)
        top = min(max(int(y0), 0), height - 1)
        bottom = min(max(int(y1), 0), height - 1)
        if right < left:
            left, right = right, left
        if bottom < top:
            top, bottom = bottom, top
        frame[top, left : right + 1] = color
        frame[bottom, left : right + 1] = color
        frame[top : bottom + 1, left] = color
        frame[top : bottom + 1, right] = color
    return frame


def _camera_recorder(out: Path, width: int, height: int, fps: int) -> Any:
    """Start recording the detection camera, or report that no encoder is installed.

    Args:
        out: Where the run writes.
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps: Playback rate.

    Returns:
        The recorder, or None when `ffmpeg` is absent.
    """
    from clave.demo.video import StreamSettings, open_stream

    return open_stream(
        StreamSettings(
            path=out / "camera-debug.mp4",
            width=width,
            height=height,
            frames_per_second=fps,
        )
    )


def _write_camera_frame(
    rgb: Any,
    segmentation: Any,
    model: Any,
    data: Any,
    camera: str,
    recorder: Any,
) -> None:
    """Paint one detection-camera frame and hand it to the encoder.

    The colour frame and the segmentation are the same camera at the same
    size, so a box sits on the pixels the object actually covered.

    Args:
        rgb: Renderer for the colour frame.
        segmentation: Renderer for geometry ids, segmentation already enabled.
        model: The compiled model, used to name geometries.
        data: The simulated state.
        camera: The detection camera's name.
        recorder: The open encoder.
    """
    rgb.update_scene(data, camera=camera)
    frame = np.array(rgb.render(), copy=True)
    segmentation.update_scene(data, camera=camera)
    boxes = tuple(
        bounds_of(mask.runs)
        for mask in segment_masks(model, segmentation.render()).values()
    )
    paint_boxes(frame, boxes)
    recorder.write(frame)


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


def _view(raw: dict[str, Any], wanted: str | None) -> dict[str, Any]:
    """Return the view to film from, naming the alternatives when it is wrong.

    Args:
        raw: The parsed debug configuration.
        wanted: The view asked for, or None for the configured default.

    Returns:
        The view block.

    Raises:
        DebugRunError: If the view does not exist. A typo here is a run filmed
            from somewhere nobody chose, so the message lists what it could
            have been.
    """
    views = config.require(raw, "views")
    name = wanted if wanted is not None else str(config.require(raw, "default_view"))
    if name not in views:
        known = ", ".join(sorted(views))
        raise DebugRunError(f"no view named {name!r}. Known: {known}")
    return dict(views[name])


def _lookat(view: dict[str, Any]) -> NDArray[np.float64]:
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
    return np.asarray((values[0], values[1], values[2]), dtype=np.float64)


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


def _markers_on(
    renderer: Any,
    data: Any,
    camera: Any,
    standing: tuple[Any, ...],
    control: Any,
    surface: float,
) -> int:
    """Rebuild the scene from this camera and stand the markers in it.

    The markers go in after `update_scene` and live only until the next one,
    so they reach whoever renders next and nobody else: not physics, not the
    gate the tracker reads, and not a run that never calls this.

    Args:
        renderer: The renderer to build into.
        data: The simulation state.
        camera: The camera to build from.
        standing: The grasp markers to draw.
        control: The control settings, for the park pose and its colour.
        surface: Height of the belt surface, in meters.

    Returns:
        How many geoms were added.
    """
    renderer.update_scene(data, camera=camera)
    added = draw(renderer.scene, standing)
    return added + draw_park(
        renderer.scene,
        control.task.park_position,
        control.task.park_marker_color,
        belt_surface=surface,
    )


def _trajectory_on(
    scene: Any,
    task: TaskMachine,
    at_seconds: float,
    horizon_seconds: float,
    flange: NDArray[np.float64],
) -> int:
    """Draw the active plan's future path and discrete pose indicators."""
    import mujoco

    added = _trajectory_sphere(scene, flange, 0.018, (0.95, 0.95, 0.95, 1.0))
    plan = task.plan
    if plan is None or horizon_seconds == 0.0:
        return added

    start = max(at_seconds, plan.started_at)
    end = min(start + horizon_seconds, plan.started_at + plan.duration)
    if end <= start:
        return added
    count = max(2, int(math.ceil((end - start) * 12.0)) + 1)
    samples: list[tuple[NDArray[np.float64], tuple[float, float, float, float]]] = []
    for index in range(count):
        instant = start + (end - start) * index / (count - 1)
        sampled = plan.at(instant)
        if sampled is None:
            continue
        phase, state, _ = sampled
        samples.append((state.position, _trajectory_color(phase)))
    for before, after in zip(samples, samples[1:], strict=False):
        added += _trajectory_segment(scene, before[0], after[0], after[1])

    pick = plan.legs[1].segment.end.position if len(plan.legs) > 1 else None
    if pick is not None:
        added += _trajectory_sphere(scene, pick, 0.022, (1.0, 0.72, 0.10, 1.0))
    if plan.legs[-1].phase is Phase.DELIVER:
        added += _trajectory_sphere(
            scene,
            plan.legs[-1].segment.end.position,
            0.024,
            (0.20, 0.90, 0.35, 1.0),
        )
    del mujoco
    return added


def _trajectory_color(phase: Phase) -> tuple[float, float, float, float]:
    """Return a subtle color for one future trajectory phase."""
    return {
        Phase.TRACK: (0.20, 0.55, 0.95, 0.75),
        Phase.DESCEND: (0.95, 0.72, 0.18, 0.85),
        Phase.HOLD: (0.25, 0.85, 0.45, 0.85),
        Phase.RETREAT: (0.95, 0.48, 0.18, 0.80),
        Phase.DELIVER: (0.85, 0.35, 0.85, 0.80),
    }.get(phase, (0.70, 0.70, 0.70, 0.65))


def _trajectory_sphere(
    scene: Any,
    position: NDArray[np.float64],
    radius: float,
    color: tuple[float, float, float, float],
) -> int:
    """Add one small trajectory indicator sphere to a render scene."""
    import mujoco

    if scene.ngeom >= scene.maxgeom:
        return 0
    mujoco.mjv_initGeom(
        scene.geoms[scene.ngeom],
        mujoco.mjtGeom.mjGEOM_SPHERE,
        np.array([radius, 0.0, 0.0], dtype=np.float64),
        np.asarray(position, dtype=np.float64),
        np.eye(3, dtype=np.float64).ravel(),
        np.asarray(color, dtype=np.float32),
    )
    scene.ngeom += 1
    return 1


def _trajectory_segment(
    scene: Any,
    start: NDArray[np.float64],
    end: NDArray[np.float64],
    color: tuple[float, float, float, float],
) -> int:
    """Add a thin capsule between two future trajectory samples."""
    import mujoco

    vector = np.asarray(end, dtype=np.float64) - np.asarray(start, dtype=np.float64)
    length = float(np.linalg.norm(vector))
    if length <= 1e-9 or scene.ngeom >= scene.maxgeom:
        return 0
    axis = vector / length
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(axis[2])) > 0.9:
        reference = np.array([1.0, 0.0, 0.0])
    first = np.cross(reference, axis)
    first /= np.linalg.norm(first)
    second = np.cross(axis, first)
    rotation = np.column_stack((first, second, axis)).ravel()
    midpoint = (np.asarray(start) + np.asarray(end)) / 2.0
    mujoco.mjv_initGeom(
        scene.geoms[scene.ngeom],
        mujoco.mjtGeom.mjGEOM_CAPSULE,
        np.array([0.004, length / 2.0, 0.0], dtype=np.float64),
        midpoint,
        rotation,
        np.asarray(color, dtype=np.float32),
    )
    scene.ngeom += 1
    return 1


def _painted(
    renderer: Any,
    data: Any,
    camera: Any,
    standing: tuple[Any, ...],
    control: Any,
    surface: float,
    task: TaskMachine,
    trajectory_seconds: float,
    indices: Any,
) -> Any:
    """Render one video frame with the markers standing in it.

    Args:
        renderer: The renderer to use.
        data: The simulation state.
        camera: The camera to film from.
        standing: The grasp markers settled at the last capture.
        control: The control settings, for the park pose and its colour.
        surface: Height of the belt surface, in meters.

    Returns:
        The rendered frame.
    """
    _markers_on(renderer, data, camera, standing, control, surface)
    _trajectory_on(
        renderer.scene,
        task,
        float(data.time),
        trajectory_seconds,
        _flange(indices, data),
    )
    _without_shadows(renderer)
    return renderer.render()


def _without_shadows(renderer: Any) -> None:
    """Turn the shadow map off for one frame.

    MEASURED, and it is the whole cost of this view. A frame of this scene
    takes 90.9 ms to render and 28.5 ms with shadows off, and halving the
    output resolution changes nothing at all: 89.7 ms at 480 by 270 against
    90.9 at 960 by 540. That rules out rasterisation and names the shadow
    map, which is an offscreen buffer of fixed size rendered once per
    casting light, and this scene has two of them.

    At the shipped frame interval a sixty second run asks for six thousand
    frames, so the difference is twenty six minutes against eight.

    This is the diagnostic view, not a published figure. `clave still`
    renders those and keeps its shadows, because there a frame is rendered
    once and the lighting is the point.

    Args:
        renderer: The renderer, whose scene flags are set in place.
    """
    import mujoco

    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
