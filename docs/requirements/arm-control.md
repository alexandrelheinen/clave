# Arm control to the grasp markers

## Intent

Move the arm to the pose the tracker points at. The markers stand in the world
showing where a jaw would close on each object, and the arm ignores them: it
runs a one-line controller that leans toward whichever reachable object comes
first and never arrives at anything.

This spec gives the arm a task layer and a guidance layer, so it goes to a
marker, holds there while the belt carries the object under it, lifts away and
takes the next one. Nothing grasps. What is delivered is the motion, and the
evidence that the motion reached the pose the tracker asked for.

The audience is whoever is judging whether the perception stack produces poses
an arm can actually be commanded to, which is the question no amount of
rendering answers.

## Scope

**In.** Ordering the markers into a queue and holding that order steady. A
task state machine over the phases of one visit, with a profile that runs the
motion alone. Guidance that turns a pair of poses into
a timed task-space path. A servo step that solves inverse kinematics and writes
the actuators. Interception, because the target moves with the belt. The
measurement of how close the flange got to the pose it was given.

**Out.** Grasping, gripper geometry in the model, and anything that closes on
an object. Placement and the bins. Obstacle avoidance and collision-free
planning, because the belt is a plane under a single layer of objects and
nothing stands between the arm and the object. Learning any part of this: the
task layer and the guidance layer are written, not trained. The Rust safety
layer, which already exists and gates what it is given.

## The question this spec answers first

**Where inverse kinematics comes from.** Three sources were examined before
writing anything.

| Source | What it offers | Why it is or is not taken |
| --- | --- | --- |
| ROS 2 and MoveIt 2 | Mature solvers behind a plugin interface: KDL, TRAC-IK, pick_ik, BioIK, with a planning scene and a node graph around them | Not taken. CLAVE has no ROS runtime dependency today beyond an optional publisher that imports `rclpy` inside a function. MoveIt brings a URDF, an SRDF, a planning scene and a process tree to solve a problem this repository has already solved, and it would put a second description of the arm beside the compiled MuJoCo model, which is the one every measured bound in `docs/measurements.md` was swept against |
| FRET | `PickPlaceFSM` with ten states, `joint_mpc`, a controller node, and a `_KinematicsBackend` protocol carrying `forward_kinematics` and `inverse_kinematics` | Not taken as a dependency, taken as a shape. Its kinematics backends are written per robot and it has three: Dubins, OpenMANIPULATOR-X and OpenMANIPULATOR-Y. There is no UR10e backend and no generic solver anywhere in it, so reuse here means writing the missing backend in a sibling repository whose scenes are tabletop and whose belt is an unshipped version |
| `clave.world.arm` | `solve` and `step_toward`, already in this repository | Taken. Damped least squares on the stacked position and orientation Jacobian, with random restarts to escape local minima, warm-started tracking for a target that moves under a millimetre per step, joint limits enforced, and a refusal for anything outside the trusted annulus. A test re-sweeps the region and fails if a point it admits stops solving |

So nothing is reimplemented and no solver is adopted. What is missing above
the solver is the task layer and the guidance layer, and that is what this
spec builds.

**What this costs, stated plainly.** `docs/roadmap.md` puts motion planning
and effector execution out of scope, in ARCO and FRET, and the v0.10.0
narrowing said CLAVE gains no planner and no controller. This spec reverses
that for the arm's own motion. The reason is that the reverse is now more
expensive: FRET has no UR10e, its scenes are tabletop, and its belt is a
version that has not shipped, so the alternative is blocking this delivery on a
sibling roadmap. The modules below are shaped to FRET's own interfaces, so
consolidating later is a port rather than a rewrite. This paragraph is the
record; the roadmap's scope line is amended to match.

## On gimbal lock

Orientation here is a pose with the tool axis vertical and a rotation about it,
and the worry that this sits in gimbal lock is worth answering because it
changes what the code should do.

Gimbal lock is a property of an Euler parameterisation, not of an arm. When
pitch reaches ninety degrees the first and third Euler angles turn about the
same physical axis and one degree of freedom disappears from the
representation while the mechanism keeps it. The usual remedies, pinning one
angle and folding it into another, are remedies for that representation.

`clave.world.arm.solve` never forms Euler angles. It reads the tool frame's
own basis vectors out of the compiled model and builds the orientation error
from two cross products: one drives the tool's z axis onto the world's
downward vertical, the other spins the tool's x axis onto the commanded yaw.
Cross products of basis vectors have no singular parameterisation, so there is
no angle to block and no third angle to fold anything into. The pose is
already fully determined: two constraints hold the axis down, one sets the
rotation about it, three set the position, and the arm has six joints to meet
them with.

What is real, and what this spec tests instead, is the wrist singularity every
six-revolute arm has. When the fifth joint approaches zero the fourth and
sixth axes become collinear, the Jacobian loses rank, and an undamped solver
commands enormous joint velocities for a small Cartesian motion. The damping
term in the solver is what keeps that bounded, trading a little tracking
accuracy near the singularity for a command the actuators can follow.
`AC-MOVE-11` requires a test that drives the arm through such a configuration
and bounds the commanded joint velocity rather than asserting the pose is met.

## The pipeline

One tick of the control loop, from what the tracker settled to what the
actuators are told.

```
WasteObject (tracker)
     │
     ├── markers.marker_for ──► GraspMarker: flange pose, closing axis, reachable
     │
     ▼
selection ──► the queue, head first, or empty
     │            (ordered by distance + exit_weight * distance before
     │             leaving, scored at anchors, recomputed on change)
     ▼
task ──────► Phase, and the pose that phase wants
     │            (STANDBY, TRACK, DESCEND, HOLD, RETREAT, PARK, FAULT)
     ▼
guidance ──► the pose to command this tick, on a bounded-speed path from
     │       where the flange is to where the phase wants it, with the
     │       interception offset applied for belt travel
     ▼
servo ─────► arm.solve warm started, joint limits clipped, data.ctrl written
```

The safety envelope in `crates/clave-safety` already refuses a pose outside
the workspace, and the selection stage asks the same geometry through
`clave.world.arm.reaches`, so a pose that reaches the servo has been admitted
twice by the same numbers.

## The modules

Four, split where the decisions differ rather than where the code is long.

| Module | Decides | Does not decide |
| --- | --- | --- |
| `clave.control.selection` | The order the tracks are served in, and when that order is recomputed | Where the flange goes, or how it gets there |
| `clave.control.task` | Which phase of a visit the arm is in, and the pose that phase wants | The path to that pose, or the joint angles |
| `clave.control.guidance` | The pose to command this tick, bounded in speed and acceleration, with interception applied | Which object, which phase, or how joints realise a pose |
| `clave.control.servo` | Joint angles for one commanded pose, and the actuator write | Anything about time, phase or target |

**`selection`.** Orders the reachable markers into a queue and hands the arm
its head. This is a travelling-salesman problem with a deadline, and the
deadline is what makes the ordinary metric wrong: an object about to leave the
window is worth more than a nearer one that will still be there. So each
candidate is scored

```
cost = distance_to_flange + exit_weight * distance_before_leaving
```

both terms in meters, `exit_weight` dimensionless and configured. Minimising
it puts the objects running out of belt first and breaks ties by travel. The
queue is built greedily, scoring each next candidate from where the flange
will stand after the previous one, which is nearest-neighbour tour
construction rather than an optimal tour. Naming that is the point: the
ordering is a starting algorithm chosen to be replaced, and calling it
optimal would hide that it is not.

**What keeps the queue still.** A queue recomputed every tick reorders faster
than the arm can traverse, and the symptom is an arm oscillating near the
centroid of the population. Two things damp it, and neither of them freezes
the decision.

Each track carries an **anchor**: the position selection scores it at. The
anchor follows the tracker's estimate only when that estimate moves more than
a configured radius, so the millimetre-scale jitter of a segmentation
footprint never reaches the ordering while a real displacement does.

The queue is then recomputed **on change rather than on a clock**: when a
track opens, when a track retires, and when an anchor moves. Between those
events the order is the order. Belt travel alone does not reorder anything,
because every candidate loses belt at the same rate and the ordering is
unchanged by a common term.

**`task`.** A state machine over one visit. Without a gripper the phases are
STANDBY when the queue is empty, TRACK while the flange follows the marker at
approach height, DESCEND while it drops to the grasp plane, HOLD for a dwell
proving it arrived and stayed, RETREAT while it lifts clear, PARK on the way
home, and FAULT when the solver or the envelope refused. The phase names and
the shape of the transition are FRET's `PickPlaceState` with the grasp,
placement and release states removed, so adding them later is filling in gaps
rather than rewriting.

The profile is configuration. `motion_only` runs STANDBY, TRACK, PARK and
FAULT and nothing else, so the arm goes to each marker in turn and moves on,
which is what tuning arm speed against belt speed needs. `full_visit` adds
DESCEND, HOLD and RETREAT. Neither profile grasps, because no gripper exists;
the phases a gripper would need are absent from both rather than present and
skipped.

**`guidance`.** Turns where the flange is and where the phase wants it into
the single pose to command this tick. A straight line in task space, which is
what an industrial linear move is, under a configured speed and acceleration
bound. It also applies interception: the belt carries the object while the arm
travels, so the pose commanded is where the marker will be on arrival rather
than where it is now, computed from the belt speed the world already reports.

**`servo`.** One commanded pose to joint angles and one actuator write. This
is `clave.world.arm.step_toward` widened to take a full pose rather than a
point, and it keeps the warm start that makes a moving target affordable.

Every tunable of all four lives in `configs/runtime/`, because a gain buried in
Python is a gain nobody reviews.

## Constraints

- **Nothing grasps.** No gripper enters the model and no phase closes one. Any
  metric that needs a grasp stays unmeasured and says so.
- **The solver is the one already here.** No second description of the arm, in
  URDF or anywhere else, and no second set of reach bounds.
- **The safety layer is not bypassed.** A pose the envelope refuses does not
  reach the actuators, and the refusal is counted rather than swallowed.
- **Configuration, not constants.** Speeds, accelerations, approach height,
  dwell, and the calibration offset are YAML keys that fail at load when
  absent.
- **The arm is judged against the pose it was given**, not against the object.
  Whether the tracker's pose is the right pose is the tracker's question and is
  measured separately.

## Acceptance criteria

Ids begin at `AC-MOVE-01`. They are append-only and never reused.

`AC-MOVE-01`: The system shall order the reachable markers by the distance
from the flange to the marker plus the configured exit weight times the
distance the marker has left before leaving the reachable window, and shall
report the order and the head.

`AC-MOVE-02`: The system shall build that order greedily, scoring each next
candidate from the position the flange is predicted to hold after the previous
one, rather than scoring every candidate from where the flange stands now.

`AC-MOVE-03`: When no marker is reachable, the system shall hold the arm at its
park pose rather than tracking a pose no object occupies.

`AC-MOVE-04`: The system shall pass through the phases of one visit in order,
and shall expose the phase it is in at every tick.

`AC-MOVE-05`: When the solver or the safety envelope refuses the pose a phase
asks for, the system shall enter its fault phase naming the refusal, and shall
not write an actuator command derived from the refused pose.

`AC-MOVE-06`: The system shall command a flange position equal to the marker's
flange position plus a configured calibration offset, and shall fail at load
when that offset is absent.

`AC-MOVE-07`: The system shall command a tool orientation with the tool axis
vertical and downward, and a rotation about that axis equal to the marker's
closing axis.

`AC-MOVE-08`: When a marker is not oriented, the system shall command the
rotation the arm already holds rather than turning the tool to an angle the
tracker did not claim.

`AC-MOVE-09`: The system shall bound the commanded task-space speed and
acceleration to the configured limits over every tick of a visit.

`AC-MOVE-10`: When the arm travels toward a marker, the system shall command
the pose the marker is predicted to hold on arrival, computed from the belt
speed, rather than the pose it holds at the instant of commanding.

`AC-MOVE-11`: When the arm passes through a wrist configuration where the
Jacobian loses rank, the system shall keep the commanded joint velocity inside
the configured bound rather than meeting the pose.

`AC-MOVE-12`: The system shall report, for every completed visit, the distance
between the flange and the pose the phase asked for at the end of its dwell.

`AC-MOVE-13`: The system shall report every visit that ended in the fault
phase, with the refusal that caused it, rather than counting only the visits
that completed.

`AC-MOVE-14`: The system shall read every gain, bound, height, dwell and offset
from configuration, and shall fail at load naming any that is absent.

`AC-MOVE-15`: The system shall leave the model unchanged, so a run that drives
the arm renders the same scene as one that does not, apart from the arm's own
pose.

`AC-MOVE-16`: The system shall score a track at an anchor that follows the
tracker's estimate only when that estimate has moved more than the configured
anchor radius, so a footprint jittering below that radius never reorders the
queue.

`AC-MOVE-17`: The system shall recompute the order when a track opens, when a
track retires, and when an anchor moves, and at no other time, so belt travel
alone leaves the order untouched.

`AC-MOVE-18`: When the configured task profile is the motion-only one, the
system shall run the standby, tracking, parking and fault phases and shall
enter no descent, dwell or retreat phase, so arm speed can be tuned against
belt speed without a descent in the way.

`AC-MOVE-19`: The system shall report which profile a run used alongside every
figure that run produced, because a distance to a tracked pose and a distance
to a descended pose are not the same measurement.

## Design notes

**Why the queue is damped at its inputs rather than frozen at its output.**
A mean of 2.67 objects sit inside the workspace at once, peaking at six, so a
controller that reorders every tick swaps targets faster than it can traverse
between them and oscillates near the centroid of the population. The obvious
fix is to freeze the choice until it is served, and it is the wrong one: a
frozen choice cannot react to the object that appears between it and the
flange, or to the one about to fall off the end.

Anchoring fixes the cause instead. The ordering is unstable because its input
is, so the input is quantised: an anchor moves only when the estimate moves
more than a radius, and the order is recomputed only when the set of anchors
changes. The arm still reacts to everything that actually happened, and to
nothing that did not.

**Why belt travel does not reorder the queue.** Every candidate loses belt at
the same rate, so belt travel subtracts a common term from every
`distance_before_leaving` and leaves the ordering unchanged. That is what
makes recomputing on change rather than on a clock correct rather than merely
cheap, and `AC-MOVE-17` is what will catch it if a future metric breaks the
property.

**Why interception is in guidance and not in selection.** Whether an object is
worth serving depends on where it is now; where to point the flange depends on
where it will be when the arm arrives. Those are different questions with
different time bases, and folding them together is how a controller starts
aiming at where an object was.

**Why the arm is judged against the commanded pose.** The pose comes from a
footprint whose vertical placement is a configured standoff rather than a
measurement, so judging the arm against the object would measure the tracker
and the effector assumption together with the controller. Separating them is
what lets one of the three be wrong without hiding the other two.

**What stays unmeasurable.** Pick success rate and cycle time to placement,
because nothing grasps and there is nowhere to place. Both are reported as
unmeasured for the same reason the benchmark already reports them so.

## Design

The shapes below are the contract between the four modules. Three of them are
pure functions over values; only the selector holds state, and it holds one
thing, which is the anchors.

### What flows

```python
# clave.control.selection

@dataclass(frozen=True)
class Candidate:
    """One marker, scored where its anchor stands."""
    track_id: int
    anchor: Point                  # where selection scores it
    flange: Point                  # where the marker wants the flange
    closing_axis: float | None     # None when the footprint has no axis
    distance_before_leaving: float # belt speed times the time left

@dataclass(frozen=True)
class Queue:
    """The order, and whether this tick rebuilt it."""
    order: tuple[Candidate, ...]
    recomputed: bool

    @property
    def head(self) -> Candidate | None: ...

class Selector:
    """Holds the anchors. The one mutable object in the control path."""
    def update(
        self, markers: tuple[GraspMarker, ...], flange: Point, belt_speed: float
    ) -> Queue: ...
```

```python
# clave.control.task

class Phase(enum.Enum):
    STANDBY = "standby"
    TRACK = "track"
    DESCEND = "descend"
    HOLD = "hold"
    RETREAT = "retreat"
    PARK = "park"
    FAULT = "fault"

class Profile(enum.Enum):
    MOTION_ONLY = "motion_only"   # standby, track, park, fault
    FULL_VISIT = "full_visit"     # adds descend, hold, retreat

@dataclass(frozen=True)
class Goal:
    """Where the phase wants the flange, and which phase asked."""
    phase: Phase
    position: Point
    yaw: float | None             # None holds the rotation the arm has
    track_id: int | None

class TaskMachine:
    def step(
        self, queue: Queue, flange: Point, at_seconds: float,
        refusal: str | None = None,
    ) -> Goal: ...
```

```python
# clave.control.guidance

@dataclass(frozen=True)
class Command:
    """The pose to command this tick."""
    position: Point
    yaw: float | None

def toward(
    flange: Point, goal: Goal, belt_speed: float,
    timestep: float, limits: MotionLimits,
) -> Command: ...
```

```python
# clave.control.servo

def follow(model, data, arm, command: Command, gain: float) -> NDArray: ...
```

### Where the numbers come from

`distance_before_leaving` is not a field of `GraspMarker` and is not added to
one. A `WasteObject` already carries `valid_until_nanos`, the instant it
reaches the measured window exit, so the distance is the belt speed times the
time remaining. Deriving it here keeps the marker a description of a pose and
nothing else.

`Goal.yaw` of None is how an unoriented footprint reaches the servo without
anybody inventing an angle for it, which is `AC-MOVE-08`.

### Configuration

One new file, `configs/runtime/control.yml`, every key required:

```yaml
selection:
  exit_weight: ...            # dimensionless, weights urgency against travel
  anchor_radius_meters: ...   # how far an estimate moves before the anchor does
task:
  profile: motion_only        # or full_visit
  approach_height_meters: ...
  dwell_seconds: ...
  park_position_meters: [...]
guidance:
  max_speed_meters_per_second: ...
  max_acceleration_meters_per_second_squared: ...
servo:
  gain: ...
  max_joint_speed_radians_per_second: ...
calibration:
  flange_offset_meters: [...]  # AC-MOVE-06
```

### The seams under test

| Seam | Tested with |
|---|---|
| `Selector.update` | Values. No model, no renderer: markers in, a queue out |
| `TaskMachine.step` | Values, driving the clock rather than the world |
| `guidance.toward` | Values, with the bounds checked over a swept path |
| `servo.follow` | The compiled model, which is the only place joint angles mean anything |
| The four together | One rollout, reporting per-visit distance to the commanded pose |

The first three need no simulator, which is what keeps the loop's decisions
testable without a render. Only `servo` compiles a model, and it is the one
module with no decisions in it.
