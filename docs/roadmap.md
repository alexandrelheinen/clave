# Roadmap

## Overview

CLAVE sorts waste on a simulated conveyor belt with a learned perception and
pick policy, under a Rust safety layer that can override it. The loop closes
end to end in simulation, and every number it produces comes from simulation.

The tagged line runs through v1.6.0. What remains is identity taken from
observation, a grip that holds through the carry, and a cycle time measured
to a chute. `docs/architecture.md` records, under what is absent, that the
proposal loop still borrows object identity from the simulator.

Simulation reuses FRET. FRET runs MuJoCo physics SITL, loads robot and prop
meshes from pinned submodules, and drives pick and place through a
robot-agnostic `PickPlaceFSM` that calls ARCO's `JointSpaceMPC`. That state
machine is the scripted expert CLAVE records demonstrations from.

## Scope

- **In**: a learned association rule and the runtime swap that takes identity
  away from the simulator; a jaw that holds an object through the carry, with
  pick success rate as a measured figure; cycle time from a published decision
  to an object crossing a chute.
- **Out**: physical hardware of any kind, real cameras, real belts, real arms,
  and the BOSSA edge deployment that goes with them. Any claim about
  real-world accuracy. The v1.x line measures simulation.

Arm motion, the mounted jaw, the chute openings and the feed-rate loop are
already in the tagged line.
[requirements/arm-control.md](requirements/arm-control.md) shapes the motion
modules to FRET's interfaces, so consolidating later is a port.

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

## The ladder

Versions already tagged stay where they are. v1.2.0, v1.4.0 and v1.5.0 were
named while the work was open and were never tagged. The latest tag is
v1.6.0, so the work that was still open under those names continues as
v1.7.0, v1.8.0 and v1.9.0. A later minor is greater than v1.6.0.

| Version | Spec | What landed | State |
| --- | --- | --- | --- |
| v1.1.0 | `perception-record` | The perception contract as code: belt frame, clock, evidence, adapters, barcode decoder, fusion, and `WasteObject` | Tagged |
| v1.3.0 | [arm-control](requirements/arm-control.md) | The arm moving to the pose a grasp marker stands at | Tagged |
| v1.6.0 | [line-throughput](requirements/line-throughput.md) | A feed rate the line is asked for, held by regulating belt speed | Tagged |

**v1.1.0.** Tagged. `clave.tracker` produces a `WasteObject` from evidence.
The release records the criteria that closed.

**v1.3.0.** Tagged. The arm reaches the pose a marker stands at, and every
visit reports the distance from the flange to that pose. Pick success and
cycle time were left for later steps.

**v1.6.0.** Tagged. Objects are released by metres of belt travel, and a
proportional-integral loop holds a configured feed rate inside the drive's
range.

| Version | Spec | What lands | State |
| --- | --- | --- | --- |
| v1.7.0 | [learned-tracker](requirements/learned-tracker.md) | The association rule as a trained model, and the runtime swap away from `associate()` | Open. Blocks v1.8.0 |
| v1.8.0 | [end-effector](requirements/end-effector.md) | A hold through the carry, and pick success rate as a measured figure | Open. The jaw is already mounted. Waits on v1.7.0 |
| v1.9.0 | [sorting-outputs](requirements/sorting-outputs.md) | Cycle time from a published decision to an object crossing a chute | Open. Chutes, places and misroutes are already counted. Waits on a carry that holds |

**v1.7.0 release criteria.** A tracking candidate is registered, trained from
one command, and holds one identity across the frames of one rollout with that
identity derived from observation. A test proves `object_id` is a training
label and never an inference input. The behavior when two objects cross, or
touch and segment as one, is stated and tested. The runtime consumes
`WasteObject` and no longer calls `associate()`. The model's identity recovery
is reported against the ground-truth associator, including when the comparison
is unflattering.

**v1.8.0 release criteria.** The Robotiq 2F-85 is already vendored and mounted,
and the object set is already swept against the 85 mm opening. What remains is
the hold: the jaw closes on an object and keeps it against belt motion and
gravity, proved by the object moving with the flange. A failed grasp is counted
and named. Pick success rate is reported as a measured figure, beside the
effector it was measured with.
[requirements/end-effector.md](requirements/end-effector.md) records why a jaw
is the simulator's effector.

The arm reaches the pose it is sent to within 1.8 mm. On the three picks last
measured, that pose sat 35 to 415 mm from the nearest object. v1.7.0 therefore
lands before v1.8.0 can be claimed.

**v1.9.0 release criteria.** One chute opening per resolved channel already
stands at belt height inside the region the arm is trusted over. An object
crossing an opening already records a place, a place into the wrong channel
already counts as a misroute, and an object that reaches the end of the belt
unplaced is already reported apart from both. What remains is cycle time from
a published decision to an object crossing an opening. That figure needs a
carry that holds, so it waits on v1.8.0.

## Perception weights

The ladder above records identity, motion, and the line. The weights that
name a material follow [training-pipeline.md](training-pipeline.md). A tag
on this ladder means those release criteria hold. The checkpoint a runtime
loads is chosen by that procedure, on a validation digest held out of the
training half.

The living documents and the operator harness were brought in line with the
tagged line under [requirements/housekeeping.md](requirements/housekeeping.md).
That work does not move the version number.

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

What is still open. Closed items stay in the commits and in
[measurements.md](measurements.md).

- **The estimate and the identity behind it.** Three picks in 24 seconds closed
  35, 123 and 415 mm from the nearest object, each inside a detection camera's
  footprint, while the flange met the commanded pose to 1.8 mm median.
  `gate_wide` and `pick_wide` together cover the reachable window. A detection
  carries no identity and joins the nearest track inside a gate scaled to that
  track's footprint, so a track tens of millimetres out can miss a fresh
  observation. The repair is
  [learned-tracker](requirements/learned-tracker.md) at v1.7.0. See
  [measurements.md](measurements.md#what-the-arm-aims-at-with-the-tracker-in-the-loop).

- **`association_radius_meters: 0.12` is still the proposal loop's gate.** The
  comment in `configs/runtime/sitl.yml` sizes it for a 0.16 m belt. The belt is
  0.50 m. Widening the constant would admit the behavior-cloning proposals,
  which land 0.445 m from the expert's choice. The sim tracker already gates
  on the track's own footprint. The proposal loop takes that gate at v1.7.0,
  when it stops calling `associate()`.

- **The jaw holds about one object in seven when the aim is already inside
  30 mm.** The pads are 37.5 mm tall and their lowest geometry stays 10 mm
  above the belt, so a parcel 18 mm thick gets about 9 mm of pad overlap and
  closing drives it out. This is the hold v1.8.0 has to prove. The repairs
  left are a jaw whose pads reach lower, or a grasp plane allowed lower for
  flat parcels while the pads still clear the belt.

- **A pad still meets the belt by 0.9 mm.** `AC-EFF-01` sized the closing
  torque to the jaw's own stroke and took a 27 mm crush down to that contact.
  Removing the last of it needs an arm whose position loop stays put under a
  few newtons, or a gripper that stops when it feels the object. Neither is
  scheduled.

- **The belt model spins parcels faster than a grasp can follow.** The turn
  about the belt normal has an autocorrelation of −0.03 after 0.04 s, and the
  p90 turn rate is 17.0 rad/s. The belt imposes a centre velocity while the
  contact patch is free to spin, and the friction between the two winds the
  parcel up. Pinning the spin and damping it were both measured and both made
  the grasp worse. The repair is a belt modelled as a surface moving under the
  object. That change moves every measurement in this document, so it stays a
  recorded decision and has no version.

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
