# CLAVE

<img src="docs/images/clave.svg" alt="CLAVE Logo" width="120" align="left">

**CLAVE** = **C**oleta de **L**ixo **A**través de **V**isão **E**mbarcada

CLAVE sorts recyclable waste traveling on a conveyor belt through a learned
perception-action policy. A neural architecture fuses visual perception,
object tracking, and pick timing into an end-to-end system trained via
imitation and reinforcement learning. The policy runs against the clock with
hard safety guarantees: a Rust core handles interlocks and workspace limits,
while neural inference provides perception and decision-making. Models train
in Python against MuJoCo simulation supplied by FRET. Everything through the
v1.x line runs in simulation.

<br clear="left">

*Clave* is Portuguese for the musical clef, which places the project in the
same family as **arco**, **fret**, **luthier**, and **bossa**.

## What this project is about

The hard problem is learning a policy that maps visual streams to physical
actions. Classifying an object on a belt is a solved exercise; predicting
what to pick, when to pick it, and where to route it under conveyor motion,
variable material properties, and hardware constraints is where the
engineering lives.

CLAVE addresses this by replacing handcoded scheduling rules with a learned
policy trained end to end:

- **Neural perception**: continuous spatial-temporal representations of the
  conveyor state, replacing frame-by-frame snapshots.
- **Learned tracking**: tracking networks that hold an identity through
  occlusion, illumination change, and overlapping objects without geometric
  heuristics.
- **Policy learning**: a perception-action loop trained by imitation from a
  scripted expert, then fine-tuned with reinforcement learning in MuJoCo,
  so pick timing survives physical variation.
- **Hybrid safety**: inference proposes, and a Rust layer disposes. Every
  action passes a deterministic check on workspace bounds and actuator
  limits before it reaches the arm.

The split between learned policy and deterministic safety is where Rust
earns its place, and the perception stage becomes a replaceable component
behind a contract.

## Running it

Two commands do something visible. Both need the world extra and a built
runtime: `uv pip install -e ".[dev,world]"` and `cargo build --release -p
clave-sitl`. For the scene assets, also run
`uv pip install -e ".[assets]" && python scripts/import_scene_assets.py` once.
Without it the belt falls back to a plain box on legs and the floor to a gray
plane; everything still runs and the world reports which it used.

```bash
python -m clave.cli demo sorting-line
```

Runs one scenario end to end and records a video of the simulation it ran.
Objects ride the belt, inference proposes a pick, the Rust safety layer accepts
or overrides it, and the decision is published. Every tunable, including the
angle the video is filmed from, lives in `configs/demos/`. Nothing is drawn on a
frame: the video is what MuJoCo rendered.

```bash
python -m clave.cli benchmark
```

Runs every configuration in `configs/benchmark/default.yml` over the same seeds
and prints one comparison, with an evidence pack beside it. Read
[docs/measurements.md](docs/measurements.md) before reading the table, because
two of the five headline metrics cannot be measured yet and that document says
why.

```bash
python -m clave.cli still thumbnail
```

Captures three 1920 by 1080 frames of a real rollout, lit for a page rather
than for a dataset. The lighting and the cameras live in `configs/stills/` and
reach the world as an argument, so `configs/world/sorting_line.yml`, which data
generation, training, validation and the benchmark all read, is untouched by
them.

Smaller commands: `clave run-sitl` for one loop with latency, `clave record-dataset`
to record rollouts, `clave train --candidate <name>` to train one, and
`clave validate-run --outcomes <file>` to score records against the gates.

## The simulated line, and its dimensions

Every number below is configuration in
[configs/world/sorting_line.yml](configs/world/sorting_line.yml), and every one
of them is sized to the manipulator rather than to a photograph of a recovery
facility. [docs/measurements.md](docs/measurements.md) carries the
measurements that set them.

| Part | Dimension |
| --- | --- |
| Belt | 3.00 m long, 1.00 m wide, surface at 0.90 m |
| Belt speed | 0.25 to 0.35 m/s, randomized per run |
| Conveyor modules | **10 modules of 0.300 m**, spanning the 3.00 m belt |
| Arm | Universal Robots UR10e, on a pedestal 0.70 m off the belt centerline |
| Effector workspace | an annulus 0.25 m to 1.25 m about the base, over a 0.50 m vertical band, measured by sweeping the model with the tool held vertical |
| Reachable window | 2.071 m of belt on the centerline, 6.6 s per object at 0.31 m/s |
| Sensing | one detection camera and three barcode cameras, all nadir, at a gate 1.00 m upstream |
| Objects | 18 scanned packages |

### The conveyor modules

The belt is drawn as a row of identical modules from the CC BY 4.0 Open-RMF
model. The module is **published at 0.500 by 0.504 by 0.502 m** with its belt
surface on top, and CLAVE scales each axis independently to the belt it
configures:

| Axis | Published | Scaled to | Factor |
| --- | --- | --- | --- |
| Length | 0.500 m | **0.300 m**, so four span 1.20 m | 0.600 |
| Width | 0.504 m | **0.320 m**, the belt width | 0.635 |
| Height | 0.502 m | **0.350 m**, so the module surface lands on the belt surface | 0.697 |

Change `belt.modules` and `belt.length_meters` together: four modules of 0.30 m
make a 1.20 m belt, eight of 0.15 m make the same belt out of shorter sections,
and six modules on a 1.80 m belt lengthen the line. The module count changes
nothing the simulation measures, because the modules carry no collision
geometry: an object still rests on the box the belt has always been.

### The objects

**Every object is a scanned package.** There are no parametric shapes on the
belt: a colored cylinder teaches a classifier shape rather than material, which
is the whole problem CLAVE exists to solve.

| Class | Objects | Source |
| --- | --- | --- |
| `M-02` HDPE | 6 supplement tubs, toiletry bottles and a mustard bottle | Scanned Objects and YCB |
| `M-04` Other plastic | 2, a sprinkles jar and snack bags | Scanned Objects |
| `M-06` Ferrous metal | 4 food cans | YCB |
| `M-09` Paperboard | 6 cartons | YCB and Scanned Objects |

The set was selected against the previous arm's **0.180 m spline stroke** rather
than a gripper opening, which took the candidate pool from 153 models to 836 and
admitted four YCB packages the old 55.7 mm jaw refused, including a 102.5 mm
master chef can. The UR10e's vertical band is 0.50 m, so that bound no longer
binds; the end effector is specified separately and is what will set the next
one.

**Seven classes still have no object, and the gripper was never the reason.**
Probing both pinned collections for them finds nothing: no PET bottle, no
individual aluminum can, no glass container, no corrugated box, no beverage
carton. Google Scanned Objects is a retail-shelf scan of toys, shoes,
supplements and electronics, and the pinned YCB subset is ten manipulation
benchmark items. Exactly one bottle exists among the 836 models that fit. Those
classes need a new asset source rather than a wider effector.

### Submodule sizes

`git submodule update --init --recursive` fetches about **2 GB**, almost all of
it the scanned objects.

| Submodule | Checked out | What it supplies |
| --- | --- | --- |
| `third_party/scanned_objects` | 2.0 GB | 1,030 scanned household objects, 11 used |
| `third_party/robotis_mujoco_menagerie` | 185 MB | Sibling ROBOTIS arms, kept for comparison |
| `third_party/ycb_sim` | 24 MB | 10 YCB packages, 4 used |
| `third_party/aws-robomaker-small-warehouse-world` | 17 MB | Warehouse props and textures |
| `.guidelines` | Under 10 MB | The shared guidelines |

## What runs today

Everything through v1.0.0 runs in simulation and nothing has touched hardware.

| Part | State |
| --- | --- |
| Material taxonomy, corpus mappings | 11 classes, four corpora mapped |
| Corpora | TrashNet and ZeroWaste fetched, digested and measured |
| Simulated world | MuJoCo conveyor from Open-RMF modules, ROBOTIS arm, bins, warehouse dressing, randomized per seed |
| Data pipeline | Labeled rollouts, ground-truth boxes, proprioception, digested splits |
| Candidates | Seven benchmarked, four trained |
| Runtime | Frame to published decision, with a Rust safety layer that can override the model |
| Integration | The decision on a ROS 2 topic, specified for a consumer to implement against |
| Benchmark | Every runnable configuration compared under one protocol |

What is missing is as important: nothing tracks an object across frames, nothing
executes a pick, and no model has been trained on real imagery. The
[roadmap](docs/roadmap.md) carries the ladder and each step's release
criteria.

## Versioning

CLAVE follows semantic versioning, with each position given a fixed meaning
for this project.

| Position | Meaning |
| --- | --- |
| MAJOR | The delivery surface changes. `v1.x` is the simulation era; a hardware era would open at `v2.0.0` and has no plan yet. |
| MINOR | One roadmap step lands and is tagged. A minor is the unit of planned work. |
| PATCH | A fix, a correction, or a change of mind inside a step already tagged. Unplanned by definition. |

`v1.0.0` means the full pipeline runs in simulation, with training,
validation, and a benchmark that reproduces from a seed and a manifest. It
does not mean anything was tested on hardware. A minor is tagged only once
its release criteria hold and `./scripts/validate.sh` exits 0.

## Ecosystem

CLAVE is one project in a family that shares a method and a set of
guidelines. Contracts point at siblings; source trees are never vendored
between them.

| Project | Role |
| --- | --- |
| **CLAVE** (this repo) | Learned perception and pick policy, plus the safety layer that checks it |
| **[ARCO](https://github.com/alexandrelheinen/arco)** | Python planning and control algorithms, including joint-space MPC |
| **[FRET](https://github.com/alexandrelheinen/fret)** | ROS 2 and MuJoCo SITL, the ROBOTIS manipulators, and the simulation CLAVE trains in |
| **[Luthier](https://github.com/alexandrelheinen/luthier)** | Photogrammetry and point clouds |
| **[BOSSA](https://github.com/alexandrelheinen/bossa)** | C++20 edge runtime on ARM Linux, publishing telemetry to SQLite |

FRET is the integration edge. CLAVE publishes a decision, FRET's planner
nodes consume it, and those nodes call ARCO as a synchronous library rather
than reaching CLAVE directly. FRET also supplies the MuJoCo world CLAVE
trains against, including the sibling ROBOTIS arms and the pinned mesh
submodules. BOSSA carries telemetry once a hardware era opens, which is
outside the v1.x line. What CLAVE takes from each sibling is itemized in the
[roadmap](docs/roadmap.md#what-clave-reuses-from-the-family).

## Repository layout

| Path | Contents |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | The constitution: quality gates, merge policy, agent rules |
| [docs/guidelines.md](docs/guidelines.md) | Coding notes specific to CLAVE, on top of the shared baseline |
| [.guidelines/](.guidelines/README.md) | Shared guidelines and the SDD method |
| [docs/roadmap.md](docs/roadmap.md) | The ladder to v1.0.0, its release criteria, and the spec dependency order |
| [docs/architecture.md](docs/architecture.md) | What each block does, its inputs and outputs, and what is deliberately absent |
| [docs/measurements.md](docs/measurements.md) | Every measured number a gate or a configuration value rests on |
| [docs/guidance-formulation.md](docs/guidance-formulation.md) | The mathematics the arm's motion is planned with, and the one place it was wrong |
| `crates/` | The decision contract, the routing policy, the publisher, the safety layer, the runtime |
| `src/clave/` | The world, the data pipeline, training, validation, the runtime, the benchmark, the demos |
| `configs/` | Every tunable. Nothing in Python or MJCF carries a numeric default |
| `third_party/` | Pinned submodules: the ROBOTIS arm, the AWS warehouse props, the YCB objects |
| [docs/requirements/](docs/requirements/) | One document per feature: intent, scope, acceptance criteria, and the ids its tests reference |
| `scripts/` | Toolchain setup and the local quality gate |

## Getting started

```bash
git clone --recurse-submodules https://github.com/alexandrelheinen/clave.git
cd clave
./scripts/setup.sh
./scripts/validate.sh
```

If the clone already exists without submodules, run
`git submodule update --init --recursive` first.

## License

MIT. See [LICENSE](LICENSE).
