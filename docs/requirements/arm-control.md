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

`AC-MOVE-20`: The system shall place the park pose inside the region the arm
is trusted over, off the belt, and outside the span the detection camera
images, so the arm at rest is neither unreachable nor in the frames the
tracker reads.

`AC-MOVE-21`: The system shall draw the park pose in the debug view, in a
colour no track is ever given, so the configured pose can be checked by
looking rather than by reading the file.

`AC-MOVE-22`: The system shall film the debug view from a named viewpoint in
configuration, and shall name the viewpoints that exist when asked for one
that does not.

`AC-MOVE-23`: The system shall keep every commanded pose inside the region
the arm is trusted over, including the poses between two admitted ones,
because that region is an annulus and a straight line across it can pass
through the hole around the base.

`AC-MOVE-24`: When the arm starts, the system shall place it at its park
pose, so the first pose the controller commands is not refused for a
configuration the controller did not choose.

`AC-MOVE-25`: When a pose is refused, the system shall command the arm to
hold where it is rather than command nothing, because an uncommanded arm
sags out of the region it is trusted over and refuses everything after.

`AC-MOVE-26`: The system shall compare an anchor against the estimate only
after carrying the anchor along the belt, so an object doing what the belt
makes it do does not count as having moved.

`AC-MOVE-27`: The system shall report which trigger rebuilt the order,
because a rebuild on a track appearing is the mechanism working and a
rebuild on an anchor is the estimate having shifted, and counting them
together hides whether the anchors damp anything.

`AC-MOVE-28`: The system shall carry both the anchor and the live pose on a
candidate, and shall command the arm to the live one, because an arm sent to
a quantised pose jumps by the anchor radius every time the anchor catches
up.

`AC-MOVE-29`: The system shall plan a pick as trajectory segments whose
duration is known before the motion starts, so the instant the flange meets
an object can be computed rather than observed.

`AC-MOVE-30`: The system shall meet position, velocity and acceleration
exactly at both ends of every segment, so two segments chain without a step
in acceleration.

`AC-MOVE-31`: The system shall solve the interception time as the soonest
duration whose segment respects the speed and acceleration ceilings over its
whole length, and shall refuse an object for which no such duration exists
before the object leaves the window.

`AC-MOVE-32`: The system shall approach an object from directly above it, at
a configured clearance, and shall descend vertically onto it.

`AC-MOVE-33`: The system shall arrive at the clearance already descending
and already moving with the belt, so the approach and the descent chain
without the flange stopping between them.

`AC-MOVE-34`: The system shall reach the object moving at the object's own
velocity, so the jaw closes with no relative slip.

`AC-MOVE-35`: The system shall derive the descent duration from the
clearance and the approach speed rather than configuring it separately,
because the three are one relation and a configured third would contradict
the other two.

`AC-MOVE-36`: The system shall command the pose the reference will hold one
configured lead from now, rather than the pose it holds, so the flange does
not trail a moving command by more than the jaw's side clearance.

`AC-MOVE-37`: When leading a pose pushes it outside the region the arm is
trusted over, the system shall project it back rather than refuse, because
the pose the phase asked for and not the correction decides whether a
target is reachable.

`AC-MOVE-38`: The system shall plan a whole visit before the arm moves, as
a sequence of timed arcs, and shall drive the arm from the clock rather
than from proximity, because a jaw has to arrive at a known instant and a
controller that finds out when it arrives by arriving cannot supply one.

`AC-MOVE-39`: The system shall shut the jaw only once the flange is on the
object, and shall hold station with the belt while it shuts, so the jaw
closes around the object rather than sweeping it.

`AC-MOVE-40`: The system shall fix the arrival time at the moment it
commits to a candidate, and shall keep re-aiming the approach arc at a
fresher estimate until the descent begins, because the belt model predicts
travel along the belt exactly and predicts drift across it not at all.

`AC-MOVE-41`: When no interception before the object leaves the window
respects both ceilings, the system shall record the object as missed and
move to the next one rather than chase it.

`AC-MOVE-42`: The system shall take an interception longer than the
soonest feasible one by a configured margin, because the soonest sits
exactly on whichever ceiling binds and an arc on its ceiling cannot be
re-aimed.

`AC-MOVE-43`: The system shall not plan or re-aim a pick whose grasp pose
lies outside the region the arm is trusted over.

`AC-MOVE-44`: When a commanded pose is refused, the system shall discard
the plan built on it rather than fly the rest of the sequence.

`AC-MOVE-45`: The system shall only admit markers that satisfy configured
modular pickability rules, rejecting any marker whose grasp point lies
outside the conveyor footprint before it enters the pick queue.

`AC-MOVE-46`: The system shall predict an object's travel along the belt and
its drift across the belt, and shall not predict its height, because the belt
drives one axis and gravity settles the object on the other two.

`AC-MOVE-47`: The system shall plan a grasp pose for the height the marker
asks for, whatever vertical component the object's estimated velocity carries,
because an object settling on the belt carries one and a plan that follows it
descends below the belt.

`AC-MOVE-48`: The system shall plan the retreat as the descent reversed: the
same clearance, the same duration derived from the same approach speed, and a
terminal velocity of the object's own motion plus the approach speed along the
belt normal, because a retreat that ends at rest slides backwards through the
whole lift in the frame the object lives in.

`AC-MOVE-49`: When a visit has to clear the belt side barrier, the system
shall reach the barrier in an arc of its own, so the retreat's shape does not
depend on where the delivery goes.

`AC-MOVE-50`: The system shall refuse a grasp pose whose lowest gripper
collision geometry would sit closer to the belt surface than the configured
clearance, and shall record the refusal as it records any other refusal.

`AC-MOVE-51`: The system shall report the largest departure of the tool axis
from the belt normal over a visit, so a tilt that breaks the jaw's orientation
is a number rather than an impression.

`AC-MOVE-52`: The debug run shall record the revision it ran at and the digests
of the configuration it ran under, beside its artifacts.

`AC-MOVE-53`: The run shall report the smallest distance between any gripper
collision geometry and the belt surface over the run, and how many ticks had a
contact between them.

`AC-MOVE-54`: The run shall record, beside the revision and the configuration
digests, what the run was asked for -- the seed, the simulated duration, the
capture interval, the view, the flags -- so a run can be repeated from its own
artifacts rather than from whoever remembers typing it.

`AC-MOVE-55`: The run shall write its report beside its artifacts, in a form a
machine can diff and in the text a reader already scans, so the figures it
measured outlive the terminal they were printed on.

`AC-MOVE-56`: When a plan in flight cannot be re-aimed onto the freshest
estimate of its object and that estimate stands further than the configured
tolerance from the pose the plan is aiming at, the system shall solve the visit
again from the freshest estimate; and when no interception exists for it, the
system shall abandon the visit, record the reason, record the object as missed
and stop flying the plan, rather than fly a pose the object is not going to be
at.

`AC-MOVE-57`: When the object a visit is about is no longer among the
candidates, the system shall abandon the visit and record why, rather than
descend onto the pose last seen.

`AC-MOVE-58`: The system shall report the largest distance a plan in flight was
found aiming away from the freshest estimate of its object, and every visit
given up before its descent with the reason it was given up.

`AC-MOVE-59`: In a run driven from ground truth, the system shall report for
every grab that had an object under the jaw the angle between the commanded
tool yaw and that object's own rotation about the belt normal, folded into the
90 degrees a jaw is symmetric about, because whether the jaw closed along the
object's own axis is a measurement and not an impression.

`AC-MOVE-60`: The system shall report the largest vertical acceleration the
flange reached over each planned visit, because a grasp that slips unloads the
arm mid-lift and every pose the plan asks for is smooth.

`AC-MOVE-61`: The clearance the jaw's lowest geometry keeps above the belt
shall cover the deflection a load adds when the jaw shuts on an object, over
the whole visit including the transition out of the hold, rather than only the
arrival error of the descent onto it.

`AC-MOVE-62`: When an object's rotation about the belt normal is being
measured, the system shall turn the tool to the yaw that object will hold at
the instant the jaws close rather than the yaw it held when the claim was
made, because the claim is made once per capture and the jaws close up to half
a second later.

`AC-MOVE-63`: While a visit is on its descent, the system shall keep moving
the end of that descent onto the freshest estimate of the object, keeping the
arrival time already chosen, and shall keep the plan it already has when the
corrected arc breaks the speed ceiling or leaves the region the arm is trusted
over, rather than abandon the visit or solve a new interception from
mid-descent. The descent's duration is fixed by the clearance and the approach
speed, so the acceleration that duration produces is the one the descent
already in hand carries, and it is not a reason to refuse the correction.

## When a precise command still misses

The command can sit on the mass and the short axis can agree, and the jaw can
still miss. Three mechanisms. None of them is a tolerance, and none of the
ceilings moves: aim tolerance 30 mm, drift horizon 0.30 s, speed 1.00 m/s,
acceleration 2.50 m/s², joint speed 2.09 rad/s, jaw clearance 10 mm.

**The roll has no travel left.** A parallel jaw is the same grip at the
commanded yaw and at that yaw plus half a turn. Tracking one of them without
a bound winds the tool roll into its ±2π stop. At the stall this produces,
the Jacobian's smallest singular value is 2.5e-4 and the whole of the
remaining position gradient sits on that stopped joint. Eight further
iterations leave the tool 4.8 mm short. The warm start then stores an answer
that does not close the gap, and each later tick starts from it while the
command keeps moving, so a miss of 5 mm becomes a miss of 108 mm while the
joint command itself is nowhere near its rate cap. The other grip puts the
roll back toward the middle of its travel. A solution nine radians away in
joint space also reaches the pose, and it is not taken during a descent: at
the joint-speed ceiling that slew is longer than the time left before the jaw
closes. The millimetre the other grip has to stay inside is the convergence
the solver already uses.

**The pads meet a flat parcel at its top.** The open jaw hangs 160.3 mm below
the flange and the shut jaw hangs 173.5 mm. A grasp plane clamped to the shut
hang holds the pinch 13 mm above a centre that is itself about 14 mm above
the belt, so the pads, 37.5 mm tall, meet the parcel near its top and the
lift is zero. The descent arrives at the open hang. A millimetre above that
geometry covers the 0.16 mm a rest-to-rest quintic of 0.20 s lags the hang
by, at the sample that lags most. The hold climbs the 13.2 mm in that 0.20 s
and carries for the rest of the dwell. Spreading the same climb over the
whole 0.40 s dwell lags by 4 mm and spends the clearance. Closing at the low
flange, with no rise, puts the pads into the belt. The clearance stays 10 mm.
The shut hang and the open hang grant the same clearance at the two ends.

**A correction the ceiling cannot take whole is taken as far as it allows.**
Once an object has moved further than the time remaining can cover at the
speed ceiling, the plan already in hand is a plan from before the object
moved. That is the ceiling doing what it is for, and it is also a miss of
69 mm on a command the flange was tracking to 3 mm, plus two approaches given
up at 44 mm and 31 mm for the same reason. The largest fraction of the
correction that stays inside the ceiling is the one flown. A fraction of zero
is not a correction. On a descent it leaves the plan already in hand, which
is what `AC-MOVE-63` requires. On an approach it is the refusal `AC-MOVE-56`
names, and the visit is solved again or abandoned. The descent is gated on
speed alone, for the reason `AC-MOVE-63` gives. The approach is gated on
speed and acceleration.

`AC-MOVE-64`: When the tool roll sits more than half a turn from the middle
of its travel, the system shall track the same jaw the other way round,
whenever that grip keeps the tool within a millimetre of the grip that kept
the commanded yaw and puts the roll closer to the middle of its travel. A
descent step that increases the tool's distance from the command shall be
discarded, so the next tick does not start further away.

`AC-MOVE-65`: When a descent already in flight is moved onto a fresher
estimate and the whole correction breaks the speed ceiling, the system shall
fly the largest fraction of that correction that stays under the ceiling. A
fraction of zero is not a correction, and the system shall keep the plan
already in hand. The acceleration ceiling does not refuse the fraction.

`AC-MOVE-66`: When an approach already in flight is moved onto a fresher
estimate and the whole correction breaks the speed ceiling or the
acceleration ceiling, the system shall fly the largest fraction of that
correction that stays inside both. A fraction of zero is the refusal
`AC-MOVE-56` names.

`AC-MOVE-67`: While the jaw is closing, the system shall raise the flange by
the extra hang of the shut jaw, over the first 0.20 s of the hold, and the
descent shall arrive at the clearance the open jaw keeps. The retreat shall
still lift its own clearance above where that hold finished.

## Test plan

Each criterion names the test that guards it. The grasp-plane floor and the
open reach live with the effector and the marker, and they are in this plan
because the rise is one correction.

| Criterion | Test |
| --- | --- |
| `AC-MOVE-64` | `test_a_wrist_wound_to_its_stop_takes_the_other_grip`, `test_a_descent_that_walks_off_the_command_is_discarded` |
| `AC-MOVE-65` | `test_a_descent_correction_past_the_ceiling_is_taken_part_way` |
| `AC-MOVE-66` | `test_an_approach_correction_past_the_ceiling_is_taken_part_way` |
| `AC-MOVE-67` | `test_the_hold_rises_while_the_jaw_closes`, `test_the_rise_leads_the_hang_the_jaw_adds_as_it_shuts` |
| `AC-GRIP-14` | `test_the_open_jaw_is_the_configured_open_reach` |
| `AC-MARK-17` | `test_the_grasp_plane_stands_on_the_open_jaw` |

## The guidance formulation

The mathematics has its own document,
[guidance-formulation.md](../guidance-formulation.md): the quintic Hermite
basis and why it rather than a B-spline, the interception time as a fixed
point and why bisection solves it, the exact condition on the descent
duration, the two terminal velocities that have to match the object, and
the feasibility floor at 1.875 times belt speed. It carries the algebra so
this document does not have to carry a summary of it that can drift.

Three things from it belong here, because they are requirements rather than
derivations. A pick is planned as segments whose duration is known before
the motion starts. Every segment meets position, velocity and acceleration
exactly at both ends, so two chain without a step in acceleration. And an
object for which no feasible interception exists before it leaves the
window is refused rather than chased.

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

**Why the other grip, and not a second solution.** The damped step that
tracks a moving command is local. Once the roll is on its stop, that step
has no joint left for the last few millimetres, and storing the step anyway
walks the tool off the command on the ticks that follow. Half a turn is the
same jaw. The other minimum of the same pose is several radians of shoulder
and elbow away, which at the joint-speed ceiling does not finish before the
jaw closes, so a descent does not switch to it.

**Why a refused correction is taken part way.** A ceiling that refuses the
whole arc also refuses a correction of a few millimetres, and the jaw then
closes on the pose from before the object moved. The largest fraction that
fits is still the same quintic, with the same duration, and a fraction of
zero is the refusal the caller already has. The ceilings themselves do not
move.

**Why the hold rises while the jaw shuts.** The linkage hangs 13.2 mm further
shut than open. Arriving at the shut hang holds a flat parcel below the pads.
Arriving at the open hang and staying there puts the pads into the belt as
the jaw shuts. The climb is 0.20 s because that is the duration whose
rest-to-rest quintic leads the hang the linkage adds. The clearance the open
arrival granted is the clearance the shut jaw keeps.

**Why red is reserved rather than merely chosen.** The park pose is the one
marker in the scene that is not a track, so a reader has to tell it apart at a
glance. Picking red for it was not enough: the track palette walks the hue
circle by the golden ratio and track 0 landed on pure red, and because the
sequence is dense, some identity eventually lands arbitrarily close to any
hue. `clave.tracker.markers` therefore squeezes the track hues off both ends
of the circle and leaves the wedge around red to the park pose, which makes
the guarantee hold for every identity rather than for the first few.

**Why the debug view carries two viewpoints.** One camera cannot do both
jobs. Framing tight enough to read a 60 mm jaw puts the park pose outside the
frame, because the park pose is off the belt and downstream, which is where
that framing is not looking. Framing wide enough to hold the park pose renders
a jaw a few pixels across. Splitting the difference does neither well, so the
views are named and the run takes one.

**What the anchors measured.** Over fourteen simulated seconds and 231
observations, the residual between a live grasp point and its anchor carried
along the belt has a median of 0.0 mm, which says the belt compensation
carries no bias, and exceeds the 20 mm radius on 39 of them. So an anchor
holds still for about five observations in six.

The queue still rebuilds on 26 of 32 captures, and that is aggregation
rather than failure: about seven tracks are live at once, so one of them
leaving its radius is enough. What matters is whether a rebuild moves the
head, and over the same run the head was swapped zero times while the track
it replaced was still there to be served. A rebuild that keeps its head
costs nothing.

**What interception and the bounds found.** Four more defects, and two of
them are the same mistake at different layers, which is the part worth
remembering.

Bounding a command against a *measurement* rather than against the previous
command. Guidance did it with the reference and the traverse ran at the
tracking error; the joint rate limiter then did it again one layer down.
These are position actuators running a proportional-derivative loop, so the
command has to lead the position to produce force, and capping that lead
left almost no driving error. A flange asked to follow the belt at 0.31 m/s
fell a metre behind inside two seconds. Measured against the previous
command instead, the same cap costs a slower transient and nothing else.

Compensating the traverse and not the staleness. An intercept that only
accounts for how long the arm takes to arrive fixes nothing once the arm has
caught up, because the traverse is then zero and the aim collapses onto a
pose that is still half a second old. The goal carries the instant it was
seen, and the intercept is carried from there.

The outer radius needs the same projection the inner hole does. A chord
between two points inside a disc stays inside it, so a path never leaves
that way; an interception does, because aiming ahead puts the aim downstream
of a pose that was reachable. Four visits in a sixteen second run were
refused at 1.266 m to 1.287 m against a 1.25 m limit.

The arrival tolerance was set from the wrong quantity. Ten millimetres came
from how precisely the solver converges, which is about a millimetre. What
decides how close the flange gets to a pose the belt is moving is the
actuators running one time constant behind a moving command: swept across
the belt, that settles at 24.3 mm over most of the width and 60.9 mm at the
far edge. At 10 mm no visit could ever complete, and the symptom was a run
that faulted nothing and served nothing.

**What the arm does now.** Over twenty-two simulated seconds under the
motion-only profile: 8 visits served, zero refusals, the flange holding the
commanded pose to 1 mm and each completed visit arriving 24.9 mm from the
pose it was asked for. That last figure is the actuator lag rather than an
error anybody chose, and a controller given belt velocity as a feedforward
term would cancel most of it. The full-visit profile completes one visit in
the same time, because each one now tracks, descends, dwells and retreats.

**What the walking skeleton found.** Four defects, all of them in the
integration rather than in any one module, and none of them visible from the
unit tests that pass on either side of them.

Guidance integrating from the measured flange rather than from its own
previous output. The reference then never leads the plant, so the effective
speed becomes the tracking error divided by the tick. Measured: 0.11 m of
travel in three seconds where the ceiling allows 0.71 m in less than one.

A marker the jaw can open to is not the same as a pose the arm can reach,
and selection checked only the first. It offered the controller poses a
metre outside the annulus, which faulted every visit.

The workspace is an annulus and therefore not convex, so a straight line
between two poses the arm is trusted over can pass through the hole around
the base. No choice of park pose removes this, because the base sits between
the arm's resting place and part of the belt.

A refused pose that wrote no actuator command left the arm to sag under
gravity, out of its own trusted vertical band, after which every pose was
refused for a reason the controller had caused.

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
  profile: full_visit         # or motion_only
  approach_height_meters: ...
  arrival_tolerance_meters: ...
  dwell_seconds: ...
  grasp_clearance_meters: ...              # AC-MOVE-32
  approach_speed_meters_per_second: ...    # AC-MOVE-33, and AC-MOVE-35 with it
  interception_limit_seconds: ...          # AC-MOVE-41
  interception_margin: ...                 # AC-MOVE-42
  park_position_meters: [...]
  park_marker_color: [...]     # AC-MOVE-21
guidance:
  max_speed_meters_per_second: ...
  max_acceleration_meters_per_second_squared: ...
servo:
  gain: ...
  max_joint_speed_radians_per_second: ...
  lead_seconds: ...            # AC-MOVE-36
calibration:
  flange_offset_meters: [...]  # AC-MOVE-06
```

### The seams under test

| Seam | Tested with |
|---|---|
| `Selector.update` | Values. No model, no renderer: markers in, a queue out |
| `TaskMachine.step` | Values, driving the clock rather than the world |
| `TaskMachine.flight` | Values, advancing the clock through a whole planned visit |
| `pick.plan_pick` and `pick.refine` | Values, checked at the seams between arcs |
| `guidance.toward` | Values, with the bounds checked over a swept path |
| `servo.follow` | The compiled model, which is the only place joint angles mean anything |
| The four together | One rollout, reporting per-visit distance to the commanded pose |

The first three need no simulator, which is what keeps the loop's decisions
testable without a render. Only `servo` compiles a model, and it is the one
module with no decisions in it.
