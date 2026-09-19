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

**In.** Choosing which marker to serve and committing to it. A task state
machine over the phases of one visit. Guidance that turns a pair of poses into
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
selection ──► the track this arm has committed to, or none
     │            (least time remaining among reachable, and it does not
     │             switch once committed)
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
| `clave.control.selection` | Which track the arm serves, and when it lets go | Where the flange goes, or how it gets there |
| `clave.control.task` | Which phase of a visit the arm is in, and the pose that phase wants | The path to that pose, or the joint angles |
| `clave.control.guidance` | The pose to command this tick, bounded in speed and acceleration, with interception applied | Which object, which phase, or how joints realise a pose |
| `clave.control.servo` | Joint angles for one commanded pose, and the actuator write | Anything about time, phase or target |

**`selection`.** Reads the markers and returns the one the arm is serving. The
rule is least time remaining among reachable markers, which is the scripted
expert's rule and is already known to work. What it adds is commitment: once a
track is chosen it stays chosen until it is served, leaves reach, or its track
retires. A controller that re-reads the best target every tick chases the
population and arrives at nothing, which is what the current one-line
controller does.

**`task`.** A state machine over one visit. Without a gripper the phases are
STANDBY when nothing is committed, TRACK while the flange follows the marker at
approach height, DESCEND while it drops to the grasp plane, HOLD for a dwell
proving it arrived and stayed, RETREAT while it lifts clear, PARK on the way
home, and FAULT when the solver or the envelope refused. The phase names and
the shape of the transition are FRET's `PickPlaceState` with the grasp,
placement and release states removed, so adding them later is filling in gaps
rather than rewriting.

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

`AC-MOVE-01`: The system shall select the reachable marker with the least time
remaining before it leaves the reachable window, and shall report which track
it selected.

`AC-MOVE-02`: When a track is selected, the system shall keep serving it until
it is released, it leaves the reachable window, or its track retires, rather
than reselecting while a visit is in progress.

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

## Design notes

**Why commitment is a requirement and not a detail.** A mean of 2.67 objects
sit inside the workspace at once, peaking at six. A controller that picks the
best target every tick will swap targets faster than it can traverse between
them, and the recorded symptom is an arm that oscillates near the centroid of
the population. Commitment is what turns a population into a queue.

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
