# Roadmap

## Overview

CLAVE sorts waste on a simulated conveyor belt with a learned perception and
pick policy, under a Rust safety layer that can override it. The loop closes
end to end today and every number it produces comes from simulation.

What remains is perception identity. `docs/architecture.md` records, under what
is absent, that object identity is ground truth borrowed from the simulator,
while everything downstream already speaks as though a tracker existed. The
versions below make those sentences true.

Simulation reuses FRET rather than rebuilding it. FRET runs MuJoCo physics SITL
with ROBOTIS manipulators, loads robot and prop meshes from pinned submodules,
and drives pick and place through a robot-agnostic `PickPlaceFSM` that calls
ARCO's `JointSpaceMPC`. That state machine is the scripted expert CLAVE records
demonstrations from, so imitation learning starts with a teacher that works.

## Scope

- **In**: the perception record, the learned association rule, the tracking
  stage the platform lacks, the runtime swap that takes identity away from the
  simulator, and the arm control that moves to a pose the tracker produced.
- **Out**: physical hardware of any kind, real cameras, real belts, real arms,
  and the BOSSA edge deployment that goes with them. Grasping, placement and
  anything that closes an effector. Any claim about real-world accuracy,
  because nothing in the v1.x line measures it.

Arm control was out of scope until the tracker produced poses worth reaching
for. It moved in because the alternative blocks on a sibling roadmap: FRET
carries the state machine and the joint-space controller, but its kinematics
backends are written per robot and it has none for the UR10e, its scenes are
tabletop, and its belt is a version that has not shipped.
[requirements/arm-control.md](requirements/arm-control.md) records the
reasoning and shapes the modules to FRET's own interfaces, so consolidating
later is a port. Grasping and placement stay out.

## Constraints

- **Simulation only through v1.x.** A tag in this line means SITL is complete,
  not that the system works on a line. Hardware is a later era with no plan
  here.
- **FRET owns the simulator.** CLAVE contributes scenes and assets that fit
  FRET's conventions rather than forking its runtime. Tunables live in YAML,
  because FRET treats a hardcoded numeric default as a defect.
- **Assets and datasets are referenced, never vendored.** Meshes come from
  pinned submodules, corpora resolve through a committed manifest with
  checksums, and no binary lands in git. This follows
  [guidelines.md](guidelines.md).
- **Rust owns the runtime, Python owns the learning.** Training code is Python.
  The SITL runtime that runs inference, applies the safety check, and publishes
  a decision is Rust under the lint tiers in
  [languages/rs.md](../.guidelines/languages/rs.md).
- **Licenses are recorded before a dependency is adopted.** Every dataset, mesh
  set, and pretrained checkpoint carries its license in the review that
  proposes it.
- **CLAVE integrates with FRET, not with ARCO directly.** ARCO is a synchronous
  Python library that FRET's planner nodes call. A decision CLAVE publishes
  reaches ARCO through FRET.

## Versioning policy

CLAVE follows semantic versioning, with the meaning of each position fixed for
this project.

| Position | Meaning for CLAVE |
| --- | --- |
| MAJOR | The delivery surface changes. `v1.x` is the simulation era and `v2.x` would open a hardware era, which has no plan in this document. |
| MINOR | One step of the ladder below lands and is tagged. A minor is the unit of planned work. |
| PATCH | A fix, a correction, or a change of mind inside a step already tagged. Unplanned by definition. |

Two rules keep the ladder honest. A minor is tagged only when its release
criteria hold and `./scripts/validate.sh` exits 0, and nothing is tagged on the
strength of an agent reporting success. A change of mind about a shipped step is
a patch on that step rather than a silent edit, so the history says what changed
and when.

## The remaining ladder

| Version | Spec | What lands | State |
| --- | --- | --- | --- |
| v1.1.0 | `perception-record` | The perception contract as code: the belt frame, the clock, evidence and its payloads, the sensor adapters, the barcode decoder, the fusion rules, and `WasteObject` | In the tree, awaiting its tag |
| v1.2.0 | [learned-tracker](requirements/learned-tracker.md) | The association rule as a trained model, the tracking stage the platform lacks, and the runtime swap away from `associate()` | Requirements written, design open |
| v1.3.0 | [arm-control](requirements/arm-control.md) | The arm moving to the pose a grasp marker stands at: target selection, the task state machine, motion between waypoints, and the servo step | Requirements written, design open |
| v1.4.0 | [end-effector](requirements/end-effector.md) | A parallel jaw on the flange, closing on an object and holding it, and pick success rate as a measured figure | Requirements written, design open |
| v1.5.0 | [sorting-outputs](requirements/sorting-outputs.md) | A chute opening per channel, a place recorded when an object crosses one, and misroutes counted | Funnels built, deliveries flown, places and misroutes counted; the grip does not hold through the carry |
| v1.6.0 | [line-throughput](requirements/line-throughput.md) | A feed rate the line is asked for rather than one it happens to have, and belt speed regulated to hold it | Feed by distance and the controller are in the tree, awaiting a tag |

**v1.1.0 release criteria.** `clave.tracker` produces a `WasteObject` from
evidence. An observation taken at one instant propagates to a later one by belt
speed, proved by a test that moves the clock rather than the object. A `Code`
associates to an object rather than to a position, and resolves to a bill of
materials rather than to a material. The material posterior combines visual
evidence with a code-derived prior, and the code never overrides a confident
visual reading. Adding a camera edits `configs/world/sorting_line.yml` and
nothing else, proved by a test rather than asserted. A runtime configured for
hardware refuses `GroundTruth` at the adapter boundary. The belt frame the
documents describe is the belt frame the code uses. The barcode decode yield is
measured on rendered frames and published whatever it is.

**v1.2.0 release criteria.** A tracking candidate is registered, trained from
one command, and holds one identity across the frames of one rollout with that
identity derived from observation rather than read from the simulator. A test
proves `object_id` is a training label and never an inference input. The
behavior when two objects cross, or touch and segment as one, is stated and
tested rather than left undefined. The runtime consumes `WasteObject` and no
longer calls `associate()`. The model's identity recovery is reported against
the ground-truth associator, including when the comparison is unflattering.

**v1.3.0 release criteria.** The arm reaches the pose a marker stands at and
holds it while the belt carries the object under the flange, from one command,
with the distance between the flange and the commanded pose reported for every
visit. A visit that the solver or the safety envelope refused is counted and
named rather than dropped. The commanded task-space speed and acceleration
stay inside their configured bounds, proved by a test rather than asserted, and
a wrist configuration where the Jacobian loses rank bounds the commanded joint
velocity rather than meeting the pose. Nothing grasps, so pick success rate and
cycle time to placement stay unmeasured and the report says why.

**v1.4.0 release criteria.** A Robotiq 2F-85 from MuJoCo Menagerie is
vendored with its provenance and licence, mounted on the flange, and the tool
site every commanded pose is expressed against moves with it. The object set
is re-swept against the 85 mm jaw rather than carried forward from a
different effector. The jaw closes on an object and holds it against belt
motion and gravity, proved by the object moving with the flange and not by
the jaw being commanded shut. A failed grasp is counted and named. Pick
success rate is reported as a measured figure, beside the effector it was
measured with and beside the statement that the suction systems this stream
normally runs are faster.
[requirements/end-effector.md](requirements/end-effector.md) records why a
jaw is adopted against what a municipal packaging line would install, and it
is a simulator argument rather than a process one.

This is the criterion the first open defect below blocks, and it blocks it
from the perception side rather than the arm side. The arm reaches the pose
it is sent to within 1.8 mm; the pose is 35 to 415 mm from the nearest object
on the three picks last measured.
v1.2.0 therefore has to land before v1.4.0 can be claimed, whatever order the
work happens to be done in.

**v1.5.0 release criteria.** One chute opening per resolved channel is built
into the conveyor structure at belt height, every one inside the region the
arm is trusted over, with a load-time refusal for any that is not. An object
crossing an opening records a place naming the object, the channel and the
instant. A place into the wrong channel counts as a misroute, which is the
figure `max_misroute_rate` has gated with no way to produce. Objects that
reach the end of the belt unplaced are reported apart from both, because a
throughput loss is not a contaminated bale. Cycle time from a published
decision to an object crossing an opening is measured, which closes the last
figure the benchmark reports as unmeasurable.

**v1.6.0 release criteria.** The line releases objects by metres of belt
travel rather than by elapsed seconds, so belt speed is the throughput knob
and not only a spacing knob. A configured setpoint in objects per second is
held by a proportional-integral controller inside the drive's own range,
proved by a test that starts the line off setpoint and reads the error once
it settles, and by a second that proves the loop corrects a spacing it was
not tuned for. A setpoint the drive cannot deliver saturates and reports the
shortfall rather than failing. A slot returns to the object pool when its
object leaves the belt, so a rate the line holds is not a rate it holds
until the pool is spent. No part of the loop reads perception, proved by a
test rather than by a comment.

## Seams to watch

- The material taxonomy is consumed by the asset tagging, the label mapping,
  and the confusion metrics. A class renamed in one place and not the others
  silently corrupts every downstream number.
- The model interface is what training runs against and what the runtime loads.
  If it leaks a specific architecture's assumptions, swapping candidates stops
  being cheap.
- The scene configuration is shared by data generation, training, and
  validation. Validation has to run on scene variants training never saw, which
  is a property of how the configuration is partitioned rather than an
  afterthought.
- The decision CLAVE publishes is consumed by FRET, so its payload and its
  units are a contract rather than an implementation detail.

## Open defects

Six defects, each recorded rather than fixed quietly because each carries a
blast radius wider than the line it sits on. The first blocks the grasp at
v1.4.0 and was found by measuring a pick that flew correctly and held nothing;
the next two were found by replaying a run's own state through the compiled
model, which is what turned "the retreat looks wrong" into a measurement; the
last three were found while reading the code ahead of the tracker work, and the
sixth was found by the branch that closed the first four.

- **The jaw closes on where an object was estimated to be, and the estimate is
  the limit.** Measured then: against the nearest object a record could
  describe, the tracker's grasp point had a median error of 11.7 mm inside the
  sensing gate, 182 mm through the near half of the arm's reach and 644 mm
  beyond it, and the gate camera stood at x = −1.00 m imaging 0.92 m of travel
  while the annulus runs to about +1.1 m, so every pick downstream was made on
  two to five seconds of dead reckoning. An object rolling or settling drifts
  sideways by a mean of 41 mm over 2.5 seconds, against a jaw whose narrowest
  side clearance is 8.7 mm.

  **The sensor half of this is done and the document above still read as though
  it were not.** `pick_wide` now stands at x = +0.38 m, images −0.345 m to
  +1.105 m, and together with `gate_wide` covers the whole reachable window of
  −1.036 m to +1.036 m; the world's own camera comment records the sweep that
  sized it. Measured on the tree that carries the belt-clearance work, three
  picks in 24 seconds closed 35, 123 and 415 mm from the nearest object, every
  one of them inside a detection camera's footprint, with the flange reaching
  the pose the plan asked for to 1.8 mm median. So the control side is not the
  limit and neither is coverage: what is left is the **estimate and the identity
  behind it**.

  A detection carries no identity and joins the nearest track inside a gate
  scaled to that track's footprint, so a track tens of millimetres out can fail
  to be corrected by a fresh observation and no run reports that failure as a
  failure. The repair is the association and retirement rule specified as
  [learned-tracker](requirements/learned-tracker.md) at v1.2.0, and the figure
  to aim at is the 35 to 415 mm measured now rather than the 94 to 644 mm this
  bullet was written with. See
  [measurements.md](measurements.md#what-the-arm-aims-at-with-the-tracker-in-the-loop).

- **The plan asked the jaws to descend below the belt.** The velocity the plan
  predicts the object with was the object's own measured three-axis velocity,
  and gravity settles an object on the belt, so the vertical component was
  extrapolated forward over a two second interception. The median vertical
  velocity on the belt is 0.027 m/s and the p90 pair with lateral drift is
  0.11 m/s, which asks for a grasp plane **31 mm to 116 mm below** the object and
  below every floor the marker and the world enforce; the marker's own clearance
  was quoted at the pinch point, which in the compiled gripper is **not the
  lowest part of the jaw** -- the pads hang 4.5 to 17.7 mm below it, so the
  marker's floor put them 5.5 mm inside the belt. Replaying a recorded run's
  state through the compiled model found the jaws at 0.8993 m against a belt
  surface at 0.900 m, 343 of 6001 samples with a pad-to-belt contact, and the
  tool axis **48° off the belt normal while holding**. The control side was
  measuring its own success against the pose it asked for, which the plan had
  already placed under the belt. Closed by `AC-MOVE-46`, `AC-MOVE-47`,
  `AC-MOVE-50`, `AC-MARK-15`, `AC-MARK-16`, `AC-GRIP-12` and `AC-GRIP-13`.

  **The residual is not closed and is now measured to its cause.** After those
  fixes a pad-to-belt contact lasts one tick of one retreat at −1.4 mm, and the
  run of 2026-09-22 showed where the geometry goes: the jaw closes on a parcel
  that weighs ten to twenty grams with the ±5 N·m the vendored gripper ships,
  which is about a hundred newtons at the pads, and the parcel is driven **27 mm
  below the belt surface** with the tool following it. The closing torque is now
  a world parameter sized by the jaw's own stroke (`AC-EFF-01`), which takes the
  crush to 0.9 mm, and the contact that is left is a boundary the belt sets
  rather than a penetration the pads press through. What would remove it
  entirely is either an arm whose position loop is stiff enough that a few
  newtons do not move the tool ten millimetres, or a gripper that stops closing
  when it feels the object. Both change the machine rather than the branch, and
  neither is measured here.


- **A run's numbers cannot be traced to the tree that produced them.** The debug
  run writes frames, a video and telemetry and no revision and no configuration
  digest, and the artifacts from 2026-09-21 do not reproduce: the plan's
  `DESCEND` leg is 0.40 s from the configuration and from a plan rebuilt at the
  run's own recorded state, while the telemetry's `DESCEND` column spans 0.79 s
  in every visit. Every number in the measurement above that is a property of the
  state the run reached survives that, and the figures that are properties of the
  control path do not. Closed by `AC-MOVE-51`, `AC-MOVE-52` and `AC-MOVE-53`.

- **RESOLVED by narrowing the belt to 0.50 m.** The sensing gate does not
  cover the belt it stands over. Measured by
  sweeping objects laterally and reading the segmentation render, `gate_wide`
  images y from -0.400 m to +0.380 m, meaning 0.800 m of a 1.00 m belt, while
  `spawn.lateral_offset_meters` places objects out to 0.42 m. The detection
  camera therefore does not see every object it is supposed to detect. The
  three code cameras image 73 percent of the width with two dead bands near
  0.12 m to 0.22 m on each side, so they do not tile it and a third of the belt
  can never present a barcode.

  Covering the full width at the configured standoff needs `gate_wide` at about
  62 degrees rather than 45, which changes every rendered frame, the world
  digest, and the input distribution every trained checkpoint saw. That is a
  world change with a real blast radius rather than a stale comment, so it is
  measured and recorded here for a decision rather than made quietly.

  The decision taken was the other one: the belt narrowed to 0.50 m instead,
  for reach-margin reasons of its own, and 0.50 m of belt is inside both the
  calculated extent and the measured one. The lens is unchanged and the
  disagreement between the two figures is unresolved, which costs nothing
  while the belt sits well inside the smaller of them.

- **`association_radius_meters: 0.12` in `configs/runtime/sitl.yml` was sized
  for a 0.16 m wide belt**, as its own comment says, and the belt is 1.00 m
  wide. Widening it would be a false fix: the behavior-cloning policy regresses
  a pick point 0.445 m from the expert's choice, so a gate wide enough to admit
  those proposals would admit wrong associations rather than recover right
  ones. The real repair is that the radius stops being a global constant and
  becomes the track's own propagated footprint plus a gate, which belongs to
  the tracker rather than to a configuration edit.

- **A grasp yaw is claimed half a second before it is used, and the objects on
  this belt turn faster than that.** Measured at the instant the jaws shut, over
  nine grabs: up to **5.4 rad/s**, which is 155 degrees over the capture
  interval, and 22 to 40 degrees of error between the commanded yaw and the
  object's own axis, with the object walked tens of millimetres sideways from a
  pose the arm met to two. `AC-MOVE-62` carries the yaw forward while the turn
  being predicted is inside the 45 degrees a jaw's symmetry leaves useful, and
  commands the claim beyond it. Three world-side repairs are measured and
  rejected: pinning the spin tips the parcels over, damping them leaves them
  flat under the jaw, and predicting the yaw over a four second plan is twenty
  radians of guess. What is left is the objects turning past the threshold, and
  they cannot be aligned with by any control-side change: the repairs are a
  settling zone on the line, or a gripper that does not need an axis. Measured
  in [measurements.md](measurements.md#what-the-reported-run-turned-out-to-be).

- **RESOLVED for both directions of travel by this branch.** The conveyor freed
  a pool slot for an object that left the belt downstream or fell below it, and
  not for one that left it *upstream*: measured, an object 1.5 m upstream of the
  entrance stayed on the active list for **668 ticks** while its slot went back
  to the pool and was spawned into, which put two objects in one pool slot and
  handed the arm a marker for a body 1.5 m behind the belt. Closed by the
  upstream test in `_recycle`, with the invariant asserted from the test that
  reads it.

- **The prediction across the belt was carried over the whole visit, and that
  was the largest aiming error in the line.** RESOLVED by `AC-MOVE-46` as
  amended: an object on a belt is driven *along* it and nothing drives it
  *across* it, the drift across is a transient whose autocorrelation is +0.04
  after 0.2 s, and the p90 lateral speed of 0.261 m/s carried over the four
  seconds a visit commits ahead is **900 mm of aim error**. Measured, two visits
  in nine aimed at a pose 208 and 346 mm from any object, outside the region the
  arm is trusted over, with the arm falling 50 to 80 mm behind its own command
  while the jaws closed on nothing. Bounded to the 0.30 s it lasts for, the aim
  lands 9 to 33 mm from the object on every visit and the jaw is 20 to 36 mm
  from the nearest object when it shuts, against 185 and 167 mm. The plan's
  whole path is now checked against the trusted region as well, sampled along
  every leg. See
  [measurements.md](measurements.md#what-the-prediction-was-actually-doing-measured-three-ways).

- **A parcel on this belt turns faster than any grasp can follow, and the belt
  model is why.** Measured: the turn about the belt normal has an autocorrelation
  of −0.03 after **0.04 s** -- it is not predictable at the 2 Hz capture rate at
  all -- and the p90 turn rate is **17.0 rad/s** with a worst of 299 rad/s. A
  parcel whose centre velocity the belt *imposes as a constraint* while its
  contact patch is free to spin is not a parcel riding a belt, and the friction
  between the two winds it up. The control side can only bound what it commands
  (`AC-MOVE-62`), because predicting a turn that lasts 40 ms from a claim that is
  500 ms old is arithmetic on noise. Every world-side repair was measured and
  rejected: pinning the spin tips the parcels over (pad-to-belt contact −0.6 mm
  over 4 ticks became −2.8 mm over 54, the lurch 99 to 934 m/s², grasps one of
  seven to none) and damping it leaves them flat under the jaw (−18.6 mm over 17
  ticks). What it needs is the belt modelled as a *surface moving under the
  object*, with friction between the two, rather than a velocity imposed on the
  body's centre. That is a world change that moves every measurement in this
  document, so it is recorded here for a decision rather than made quietly.

- **The jaw closes near the top of a parcel and shoves it.** With the aim inside
  30 mm the jaw still holds **one object in seven**. The pads are 37.5 mm tall,
  their lowest geometry is kept 10 mm above the belt, and the marker places its
  plane at the object's own mid-height clamped up to that floor: 27.7 mm above
  the surface at its lowest. A parcel lying 18 mm thick therefore gets about
  **9 mm of pad overlap**, so closing drives it down and out instead of clamping
  it and the lift is zero. Raising the plane for every object was tried and made
  the belt contact worse (the clearance entry above); the repairs that remain are
  a jaw whose pads reach lower, or a grasp plane allowed lower for flat parcels
  while the pads still clear the belt.

## What CLAVE reuses from the family

| Source | What CLAVE takes | Where it lives |
| --- | --- | --- |
| FRET | MuJoCo physics SITL, gate cameras, the robot-agnostic `PickPlaceFSM`, the YAML configuration policy, and the asset submodule convention | `src/fret/` in the FRET repository |
| FRET | OpenMANIPULATOR-X and OpenMANIPULATOR-Y, kept in FRET. CLAVE does not vendor them | FRET repository |
| FRET submodule | Warehouse props and textures, including bucket and clutter meshes | `third_party/aws-robomaker-small-warehouse-world`, MIT-0 |
| ARCO | Joint-space planning and `JointSpaceMPC`, reached through FRET's planner nodes | ARCO repository, Python library |
| BOSSA | The telemetry contract for a later hardware era, out of scope for v1.x | BOSSA repository, C++20 |

## References

- [ZeroWaste dataset](https://openreview.net/pdf?id=DAkP1TT_Ubm), conveyor imagery from a full-scale recovery facility.
- [waste-datasets-review](https://github.com/AgaMiko/waste-datasets-review), an index of litter and waste image datasets.
- [mujoco_scanned_objects](https://github.com/kevinzakka/mujoco_scanned_objects), MJCF models of Google Scanned Objects.
- [Google Scanned Objects](https://arxiv.org/abs/2204.11918), the source dataset of 1,030 scanned household items.
- [Diffusion Policy](https://arxiv.org/abs/2303.04137), visuomotor policy learning through action diffusion.
- [The Plastic Recycling Process](https://plasticsrecycling.org/how-recycling-works/the-plastic-recycling-process/), Association of Plastic Recyclers, on resin separation.
- [Materials Recovery Center](https://www3.epa.gov/recyclecity/recovery.htm), US EPA, on what a facility separates.
- [FRET roadmap](https://github.com/alexandrelheinen/fret/blob/main/docs/roadmap.md), the era convention this ladder follows.
