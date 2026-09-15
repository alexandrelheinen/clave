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
clave-sitl`. For the warehouse scene dressing, also run
`python scripts/import_warehouse_assets.py` once, which converts the meshes the
pinned MIT-0 submodule holds. Without it the scene keeps a plain floor.

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
[docs/research/benchmark.md](docs/research/benchmark.md) before reading the
table, because two of the five headline metrics cannot be measured yet and the
document says why.

Smaller commands: `clave run-sitl` for one loop with latency, `clave record-dataset`
to record rollouts, `clave train --candidate <name>` to train one, and
`clave validate-run --outcomes <file>` to score records against the gates.

## What runs today

Everything through v1.0.0 runs in simulation and nothing has touched hardware.

| Part | State |
| --- | --- |
| Material taxonomy, corpus mappings | 11 classes, four corpora mapped |
| Corpora | TrashNet and ZeroWaste fetched, digested and measured |
| Simulated world | MuJoCo conveyor, ROBOTIS arm, bins, randomized per seed |
| Data pipeline | Labeled rollouts, ground-truth boxes, proprioception, digested splits |
| Candidates | Seven benchmarked, four trained |
| Runtime | Frame to published decision, with a Rust safety layer that can override the model |
| Integration | The decision on a ROS 2 topic, specified for a consumer to implement against |
| Benchmark | Every runnable configuration compared under one protocol |

What is missing is as important: nothing tracks an object across frames, nothing
executes a pick, and no model has been trained on real imagery. The
[roadmap](.kiro/steering/roadmap.md) carries the ladder and each step's release
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
trains against, including the OpenMANIPULATOR arms and the pinned mesh
submodules. BOSSA carries telemetry once a hardware era opens, which is
outside the v1.x line. What CLAVE takes from each sibling is itemized in the
[roadmap](.kiro/steering/roadmap.md#what-clave-reuses-from-the-family).

## Repository layout

| Path | Contents |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | The constitution: quality gates, merge policy, agent rules |
| [docs/guidelines.md](docs/guidelines.md) | Coding notes specific to CLAVE, on top of the shared baseline |
| [standards/](standards/README.md) | Shared guidelines, the SDD method, and the agent toolchain |
| [.kiro/steering/roadmap.md](.kiro/steering/roadmap.md) | The ladder to v1.0.0, its release criteria, and the spec dependency order |
| [docs/research/](docs/research/) | One report per roadmap step, each stating what it measured and what it did not |
| [docs/decisions.md](docs/decisions.md) | Why a gate or a constraint was scoped the way it is |
| `crates/` | The decision contract, the routing policy, the publisher, the safety layer, the runtime |
| `src/clave/` | The world, the data pipeline, training, validation, the runtime, the benchmark, the demos |
| `configs/` | Every tunable. Nothing in Python or MJCF carries a numeric default |
| `.kiro/` | Committed specifications and the steering documents agents read as project memory |
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
