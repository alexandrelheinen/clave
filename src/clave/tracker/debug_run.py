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

**The report separates flying from grasping.** An arm can reach the pose it
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

import logging
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

from clave.control.guidance import Command, Motion, toward
from clave.control.pick import JAW_OPEN
from clave.control.selection import Selector
from clave.control.servo import follow
from clave.control.settings import ControlSettings, Phase, Point
from clave.control.task import TaskMachine
from clave.errors import ClaveError
from clave.tracker.adapters.detection import detections_from_masks
from clave.tracker.adapters.render import segment_masks
from clave.tracker.association import SimulatorIdentity
from clave.tracker.codes import load_catalog, resolver_for
from clave.tracker.evidence import Evidence, GroundTruth, Role
from clave.tracker.fusion import FusionSettings
from clave.tracker.intake import Deployment, Intake
from clave.tracker.listing import described_fields
from clave.tracker.markers import draw, draw_park, markers_for
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
            two ways a pick fails: a large gap is a flight that arrived
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
    fps: int | None = None,
    view_name: str | None = None,
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
        fps: Playback rate of that file, or None for the rate the debug
            configuration names.
        view_name: Which view in the debug configuration to film from, or
            None for the one that file names as its default.

    Returns:
        The report.

    Raises:
        DebugRunError: If the world declares no detection camera.
    """
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    LOGGER.debug(
        "initializing tracker debug run: root=%s out=%s seconds=%.3f seed=%d "
        "capture_interval=%.3f",
        root,
        out,
        seconds,
        seed,
        capture_interval,
    )
    import cv2
    import mujoco
    import numpy as np

    from clave.tracker.sensors import SensorError

    raw = config.load(root / "configs" / "world" / "sorting_line.yml")
    sensors = load_sensors(raw)
    try:
        # Every detection camera, not the first one. A line with a single
        # camera over the sensing gate can only ever hand the arm an estimate
        # that has been dead reckoned since the object left that gate, and
        # what the belt model does not predict is exactly what a jaw closing
        # on 8.7 mm of side clearance cannot absorb.
        require_role(sensors, Role.DETECTION)
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
    control = ControlSettings.load(
        config.load(root / "configs" / "runtime" / "control.yml")
    )
    debug = config.load(root / "configs" / "debug" / "tracker.yml")
    view = _view(debug, view_name)

    model, data, plan = scene.build(raw, np.random.default_rng(seed), root)
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
        lowest=drive.low,
        highest=drive.high,
        speed=plan.belt.speed,
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
        # Seeded from the layout and updated every capture below, because the
        # feed controller moves the belt and a prediction made with the speed
        # the run drew is wrong by however far the controller has trimmed it.
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
    tracker_cam = mujoco.Renderer(model, height=180, width=240) if opened else None
    start_wall = time.perf_counter()

    indices = armmod.locate(model)
    # Start the arm parked. The model's own initial configuration leaves the
    # flange below the trusted vertical band, so the first pose the controller
    # commands is refused for a reason that has nothing to do with the pose: a
    # line starts with its arm at rest, and so does this.
    _park_the_arm(mujoco, model, data, indices, control.task.park_position)

    base_xy = (float(indices.base_position[0]), float(indices.base_position[1]))

    def keep_inside(pose: tuple[float, float, float]) -> tuple[float, float, float]:
        """Push a pose back into the region the arm is trusted over.

        All three axes. Correcting only the horizontal ones leaves a
        reference reseeded from a flange that has overshot the vertical band
        still outside it, and every pose after that is refused.

        Args:
            pose: The pose.

        Returns:
            The pose, unchanged where it was already inside.
        """
        x, y = armmod.project_into_reach(base_xy, pose[0], pose[1])
        return x, y, armmod.project_into_band(float(indices.base_position[2]), pose[2])

    def admits(pose: tuple[float, float, float]) -> bool:
        """Whether the arm is trusted at a pose.

        Args:
            pose: The pose.

        Returns:
            Whether it lies inside the region the safety layer enforces.
            Selection and planning ask the same question of the same
            function, so the queue cannot offer what a plan would refuse.
        """
        return bool(armmod.reachable(indices, np.array(pose, dtype=float)))

    selector = Selector(control.selection, admits)
    task = TaskMachine(
        control.task,
        control.calibration,
        belt_surface=surface,
        belt_speed=plan.belt.speed,
        guidance=control.guidance,
        admits=admits,
        chutes=plan.chutes,
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
    # How far each visit raised the object it went for, against where that
    # object was resting when the plan was made. A flight can be perfect and
    # this still read zero, which is the whole point of measuring it apart.
    lifts: list[float] = []
    counted = 0
    # And how near the jaw came to any object at all when it shut, which is
    # the figure that separates a flight that missed from a grasp that let go.
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
    # Guidance integrates its own output, so the reference is seeded once and
    # fed back afterwards. Seeding it from the flange every tick would make it
    # chase the arm instead of leading it.
    motion = Motion(position=_flange(indices, data), speed=0.0)
    # And which way it is going, which a plan needs so its first arc begins
    # where the motion already is instead of asking for a step in velocity.
    moving: Point = (0.0, 0.0, 0.0)
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
    recorder = (
        _recorder(
            view,
            out,
            fps or int(config.require(movie, "frames_per_second")),
            movie_interval,
        )
        if video
        else None
    )
    next_capture = 0.0
    next_frame = 0.0

    def _interruptible(iterable):
        try:
            yield from iterable
        except KeyboardInterrupt:
            LOGGER.warning("simulation interrupted by user; finalizing")

    try:
        steps = int(seconds / plan.timestep)
        progress = tqdm(range(steps), desc="Simulating", unit="step")
        for _ in _interruptible(progress):
            mujoco.mj_step(model, data)
            conveyor.step(model, data)
            # Checked every tick, not every capture. An object released
            # over a mouth falls the belt's height in 0.43 s and the pool
            # recycles it below 0.30 m, so at the half second capture
            # cadence it goes from above the surface to gone without ever
            # being seen crossing.
            routes.update({i.index: i.channel for i in conveyor.active})
            for name, channel in _placed(
                mujoco, model, data, conveyor, plan.chutes, mouth, surface
            ).items():
                if name in seen_down:
                    continue
                seen_down[name] = channel
                placed[channel] = placed.get(channel, 0) + 1
                belongs = routes.get(int(name.rsplit("_", 1)[1]))
                if belongs is not None and belongs != channel:
                    misrouted += 1
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
            was_flying = task.flying
            flown = task.flight(data.time, place)
            command = None
            if flown is not None:
                command = Command(
                    position=flown.position,
                    yaw=flown.yaw,
                    speed=math.dist((0.0, 0.0, 0.0), flown.velocity),
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
                # Guidance resumes from where the plan left the reference, so
                # the park move after a visit does not start by jumping back
                # to wherever the reference had been before the plan.
                motion = Motion(position=command.position, speed=command.speed)
            elif was_flying:
                # The plan ran out on this tick and the visit is recorded.
                # Open the jaw, stand still, and let the next capture decide.
                armmod.hold(data, indices, JAW_OPEN)
                nearest = _in_the_jaw(
                    mujoco, model, data, conveyor, _pinch(indices, data)
                )
                lifts.append(
                    0.0
                    if nearest is None or nearest[0] not in resting
                    else _object_place(mujoco, model, data, nearest[0])[2]
                    - resting[nearest[0]]
                )
                resting = {}
                goal = None
                moving = (0.0, 0.0, 0.0)
                motion = Motion(position=keep_inside(place), speed=0.0)
            elif goal is not None:
                command = toward(
                    motion,
                    goal,
                    plan.timestep,
                    control.guidance,
                    feeding.speed,
                    int(data.time * NANOS_PER_SECOND),
                    keep_inside,
                )
                motion = Motion(position=command.position, speed=command.speed)

            if command is not None:
                moving = command.velocity
                stepped = follow(
                    model,
                    data,
                    indices,
                    command,
                    control.servo.gain,
                    max_joint_step=joint_step,
                    lead_seconds=control.servo.lead_seconds,
                    keep_inside=keep_inside,
                )
                if stepped.refusal is not None:
                    refusal = stepped.refusal
                elif flown is not None or (
                    goal is not None and goal.phase in _VISITING
                ):
                    closest = min(closest, math.dist(place, command.position))

            # The video and live window render on their own cadence. The
            # capture cadence is what the tracker decides at, and watching
            # a decision rate is watching an arm teleport.
            if (recorder is not None or opened) and data.time >= next_frame:
                next_frame = data.time + movie_interval
                frame = _painted(watching, data, eye, standing, control, surface)
                if recorder is not None:
                    recorder.write(frame)
                if opened and tracker_cam is not None:
                    tracker_cam.update_scene(data, camera="gate_wide")
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
                            position=(position[0], position[1], position[2]),
                        ),
                    ),
                    at_nanos=now,
                )

            records = tracker.settle(at_nanos=now)
            standing = markers_for(records, effector, surface)

            flange = _flange(indices, data)
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
                if name in seen_down:
                    continue
                seen_down[name] = channel
                placed[channel] = placed.get(channel, 0) + 1
                slot = int(name.rsplit("_", 1)[1])
                belongs = routes.get(slot)
                if belongs is not None and belongs != channel:
                    misrouted += 1

            for trigger in queue.reasons:
                reorders[trigger] += 1
            head_id = None if queue.head is None else queue.head.track_id
            if (
                previous_head is not None
                and head_id != previous_head
                and any(item.track_id == previous_head for item in queue.order)
            ):
                head_churn += 1
            previous_head = head_id
            goal = task.step(queue, flange, data.time, refusal, moving)
            refusal = None
            if goal.phase in _VISITING:
                head = next(
                    (item for item in standing if item.track_id == goal.track_id),
                    None,
                )
                if head is not None:
                    closest_live = min(closest_live, math.dist(flange, head.flange))
            if goal.phase is Phase.FAULT:
                # The arm was told to hold, so the reference comes back to the
                # pose it is holding rather than resuming from wherever it had
                # run ahead to. It is projected on the way: the flange itself
                # can cut the corner of the hole while tracking, and reseeding
                # the reference inside it is what turned one refusal into
                # every refusal after it.
                motion = Motion(position=keep_inside(flange), speed=0.0)
                moving = (0.0, 0.0, 0.0)
            if task.flying and not resting:
                # Snapshot how high everything is lying before the arm
                # touches anything, so a lift is measured against where the
                # object actually was.
                resting = _resting(mujoco, model, data, conveyor)

            # The markers go in before the render and live only until the next
            # update_scene, so they reach this view and no other. The gate the
            # tracker reads was rendered above and carries none of them.
            geoms = _markers_on(watching, data, eye, standing, control, surface)
            drawn = len(standing)
            canvas = watching.render()

            cv2.imwrite(
                str(out / f"frame_{captures:04d}.png"),
                cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR),
            )
            written += 1
            _write_beliefs(believed, captures, now, records)
    finally:
        watching.close()
        masks.close()
        if tracker_cam is not None:
            tracker_cam.close()
        if recorder is not None:
            recorder.close()
        if opened:
            cv2.destroyAllWindows()

    return DebugRunReport(
        captures=captures,
        tracks=len(tracker.settle(at_nanos=int(data.time * NANOS_PER_SECOND))),
        reorders=reorders,
        head_churn=head_churn,
        served=task.served,
        missed=task.missed,
        arrivals=task.arrivals,
        lifts=tuple(lifts),
        jaw_gaps=tuple(gaps),
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


def _park_the_arm(
    mujoco: Any, model: Any, data: Any, indices: Any, park: tuple[float, ...]
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
    import numpy as np

    try:
        angles = armmod.solve(model, data, indices, np.array(park, dtype=float))
    except armmod.ReachError as error:
        raise DebugRunError(f"the park pose does not solve: {error}") from error
    for slot, joint in enumerate(indices.joint_ids):
        data.qpos[model.jnt_qposadr[joint]] = angles[slot]
    for slot, actuator in enumerate(indices.actuator_ids):
        data.ctrl[actuator] = angles[slot]
    mujoco.mj_forward(model, data)


def _pinch(indices: Any, data: Any) -> tuple[float, float, float]:
    """Return where the jaw closes, as three meters.

    Args:
        indices: The arm indices.
        data: Its state, with forward kinematics already current.

    Returns:
        The pinch site's position. Every commanded pose is against the
        flange, because that is what the trusted reach was swept against,
        and this is where the object actually ends up.
    """
    place = data.site_xpos[indices.pinch_site]
    return float(place[0]), float(place[1]), float(place[2])


def _flange(indices: Any, data: Any) -> tuple[float, float, float]:
    """Return where the flange stands, as three meters.

    Args:
        indices: The arm indices.
        data: Its state, with forward kinematics already current.

    Returns:
        The position.
    """
    place = armmod.end_effector_position(data, indices)
    return float(place[0]), float(place[1]), float(place[2])


def _object_place(
    mujoco: Any, model: Any, data: Any, name: str
) -> tuple[float, float, float]:
    """Return where one conveyor object stands, as three meters.

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
    return float(place[0]), float(place[1]), float(place[2])


def _placed(
    mujoco: Any,
    model: Any,
    data: Any,
    conveyor: Any,
    chutes: dict[str, tuple[float, float, float]],
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
    mujoco: Any, model: Any, data: Any, conveyor: Any, pinch: tuple[float, float, float]
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
    nearest, best = None, float("inf")
    for item in conveyor.active:
        gap = math.dist(pinch, _object_place(mujoco, model, data, item.name))
        if gap < best:
            nearest, best = (item.name, gap), gap
    return nearest


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


def _painted(
    renderer: Any,
    data: Any,
    camera: Any,
    standing: tuple[Any, ...],
    control: Any,
    surface: float,
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

    This is the diagnostic view, not a published figure. `clave sim --still`
    renders those and keeps its shadows, because there a frame is rendered
    once and the lighting is the point.

    Args:
        renderer: The renderer, whose scene flags are set in place.
    """
    import mujoco

    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
