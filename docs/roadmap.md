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
  [languages/rs.md](../standards/guidelines/languages/rs.md).
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
| v1.3.0 | [arm-control](requirements/arm-control.md) | The arm moving to the pose a grasp marker stands at: target selection, the task state machine, guidance between waypoints, and the servo step | Requirements written, design open |

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

Two defects found while reading the code ahead of the tracker work. Neither is
repaired, and both are recorded here rather than fixed quietly, because each
carries a blast radius wider than the line it sits on.

- **The sensing gate does not cover the belt it stands over.** Measured by
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

- **`association_radius_meters: 0.12` in `configs/runtime/sitl.yml` was sized
  for a 0.16 m wide belt**, as its own comment says, and the belt is 1.00 m
  wide. Widening it would be a false fix: the behavior-cloning policy regresses
  a pick point 0.445 m from the expert's choice, so a gate wide enough to admit
  those proposals would admit wrong associations rather than recover right
  ones. The real repair is that the radius stops being a global constant and
  becomes the track's own propagated footprint plus a gate, which belongs to
  the tracker rather than to a configuration edit.

## What CLAVE reuses from the family

| Source | What CLAVE takes | Where it lives |
| --- | --- | --- |
| FRET | MuJoCo physics SITL, gate cameras, the robot-agnostic `PickPlaceFSM`, the YAML configuration policy, and the asset submodule convention | `src/fret/` in the FRET repository |
| FRET submodule | OpenMANIPULATOR-X, 4 revolute joints plus a parallel gripper, and OpenMANIPULATOR-Y, 6 revolute joints | `third_party/robotis_mujoco_menagerie` |
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
