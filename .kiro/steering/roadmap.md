# Roadmap

## Overview

CLAVE reaches v1.0.0 when a learned perception and pick policy sorts waste on
a simulated conveyor belt, end to end, with training, validation, and a
benchmark that anyone can reproduce from a seed and a manifest. Everything up
to that tag runs in simulation. No camera, no belt, no arm, and no claim that
any of it was tested on hardware.

The work splits into three blocks the version ladder below turns into nine
minor releases. The first block reads the field before committing to anything:
which datasets exist, which architectures are worth trying, and what training
them costs. The second block settles the algorithmic foundation, meaning the
deep learning framework, where the corpus lives, and the candidate networks
behind one interface. The third block builds the training application itself,
which is the simulated world, the data preparation, the training runs, and the
validation that says whether a policy is good enough to care about.

Simulation reuses FRET rather than rebuilding it. FRET already runs MuJoCo
physics SITL with two ROBOTIS manipulators, loads its robot and prop meshes
from pinned submodules, and drives pick-and-place through a robot-agnostic
`PickPlaceFSM` that calls ARCO's `JointSpaceMPC`. That FSM is the scripted
expert CLAVE records demonstrations from, so imitation learning starts with a
teacher that already works.

## Approach Decision

- **Chosen**: reuse FRET's MuJoCo SITL stack and ROBOTIS arms, add a conveyor
  sorting world and a waste asset set on top of it, and learn perception and
  pick policy from a mix of public waste imagery and simulated rollouts.
- **Why**: FRET has solved arm kinematics, joint-space planning, contact
  physics, gate cameras, and the asset submodule policy. Rebuilding any of it
  inside CLAVE would duplicate a working stack and split the family's
  simulation effort across two repositories.
- **Rejected alternatives**:
  - *A CLAVE-owned simulator.* Full control over the scene, at the cost of
    reimplementing physics SITL, camera rendering, and arm control that FRET
    already ships and tests.
  - *Isaac Sim or Gazebo.* Better photorealism and a larger asset catalog, but
    neither is what the family runs, and the sibling arms exist as MuJoCo MJCF
    today.
  - *Real imagery only, no simulated rollouts.* Public waste datasets label
    images, not actions. A pick policy needs state transitions and reward, and
    no public dataset supplies those for this task.
  - *Hardware in the v1.x line.* FRET keeps hardware in its own v2.x era for
    the same reason: a learned policy that has never closed a loop in
    simulation is not ready to move a physical arm.

## Scope

- **In**: the bibliographic review, the waste taxonomy and its sorting
  doctrine, the learning platform and corpus storage, at least three
  open-source candidate architectures per learned stage, the MuJoCo sorting
  world with waste assets, data preparation, training, validation, the SITL
  runtime that closes the loop, and the benchmark that compares candidates.
- **Out**: physical hardware of any kind, real cameras, real belts, real arms,
  and the BOSSA edge deployment that goes with them. Motion planning and
  effector execution, which stay in ARCO and FRET. Any claim about real-world
  accuracy, because nothing in the v1.x line measures it.

## Constraints

- **Simulation only through v1.x.** The v1.0.0 tag means SITL is complete, not
  that the system works on a line. Hardware is a later era with no plan here.
- **FRET owns the simulator.** CLAVE contributes scenes and assets that fit
  FRET's conventions rather than forking its runtime. Tunables live in YAML,
  because FRET treats a hardcoded numeric default as a defect.
- **Assets and datasets are referenced, never vendored.** Meshes come from
  pinned submodules, corpora resolve through a committed manifest with
  checksums, and no binary lands in git. This follows
  [docs/guidelines.md](../../docs/guidelines.md).
- **Rust owns the runtime, Python owns the learning.** Training code is Python.
  The SITL runtime that runs inference, applies the safety check, and publishes
  a decision is Rust under the lint tiers in
  [languages/rs.md](../../standards/guidelines/languages/rs.md).
- **Licenses are recorded before a dependency is adopted.** Every dataset,
  mesh set, and pretrained checkpoint carries its license in the review that
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
strength of an agent reporting success. A change of mind about a shipped step
is a patch on that step rather than a silent edit, so the history says what
changed and when.

## The ladder to v1.0.0

Versions land in this order. The dependency graph further down allows several
specs to be written in parallel, but releases are sequential.

### Block A: study

| Version | Spec | What lands |
| --- | --- | --- |
| v0.1.0 | `training-infrastructure-review` | The bibliographic review: datasets, architectures, training infrastructure, and what each costs |
| v0.2.0 | `waste-taxonomy` | Material classes grounded in recovery-facility practice, the object to material mapping, and the channel policy |

**v0.1.0 release criteria.** A document under `docs/research/` surveys waste
perception datasets, candidate perception and policy architectures, and
training infrastructure, and it names which options advance and why. Every
candidate carries its license, a maintenance signal, and a stated reason it is
viable or not under FRET reuse. The compute budget states what hardware is
available and what a training run on it is expected to cost. No option advances
on reputation alone.

**v0.2.0 release criteria.** Every material class has a definition, at least one
canonical everyday object, and a channel. The reject rule for low-confidence
objects is stated. The label sets of the datasets shortlisted at v0.1.0 are
mapped onto the taxonomy, and the labels that do not map are listed rather than
quietly dropped. Sources for the sorting doctrine are cited.

### Block B: algorithmic foundation

| Version | Spec | What lands |
| --- | --- | --- |
| v0.3.0 | `learning-platform` | The deep learning framework, corpus storage and versioning, experiment tracking, and the reproducibility rules |
| v0.4.0 | `model-candidates` | At least three open-source architectures per learned stage, behind one interface |

**v0.3.0 release criteria.** A fresh clone fetches the corpus from a committed
manifest and reproduces a recorded smoke run. Every artifact resolves by
checksum. No binary is committed. A run records its seed, its configuration,
and its environment, and a second run of the same seed produces the same
metrics within a stated tolerance.

**v0.4.0 release criteria.** Each candidate loads behind the shared interface,
runs a forward pass on a committed fixture, and reports its parameter count and
single-frame latency on the development machine. Licenses are recorded. At
least three candidates exist for perception and at least three for the pick
policy, all from open sources.

### Block C: training application

| Version | Spec | What lands |
| --- | --- | --- |
| v0.5.0 | `sorting-world` | The MuJoCo conveyor scene: belt, arm, cameras, channel bins, waste assets, and the randomization knobs |
| v0.6.0 | `data-pipeline` | Ingestion of public corpora, synthetic generation from the world, demonstration recording, and reproducible splits |
| v0.7.0 | `training-application` | Training runs for every candidate: imitation learning from the scripted expert, then reinforcement fine-tuning |
| v0.8.0 | `validation-harness` | Metrics, the validation protocol, and the gates that decide whether a candidate passes |
| v0.9.0 | `sitl-runtime` | The Rust runtime closing the loop inside CLAVE: inference bridge, safety check, and the published decision |
| v0.10.0 | `fret-integration` | Handing the decision to FRET over ROS 2 so it drives the manipulator |

**v0.5.0 release criteria.** The scene steps in MuJoCo, objects ride the belt
into the arm's workspace, and the arm reaches them. Every asset carries a
material class from v0.2.0. Every randomization knob is a YAML key, with no
numeric default in Python or MJCF. A seed reproduces a run. Meshes load from
pinned submodules.

**v0.6.0 release criteria.** One command builds a versioned dataset from a
manifest. Splits are deterministic by seed and free of leakage between them.
Class balance is reported rather than assumed. Demonstrations recorded from
FRET's `PickPlaceFSM` replay to the same outcome. A held-out set of real
imagery exists and is never trained on, so the gap between simulation and
photographs can be measured later.

**v0.7.0 release criteria.** One command trains any candidate from a
configuration file. Runs resume after interruption and log metrics to the
tracker. At least three perception candidates and at least three policy
candidates have completed runs with recorded numbers. The reward and the
randomization schedule are configuration, not code.

**v0.8.0 release criteria.** Validation runs from one command against any
trained candidate and emits a report that separates what was run from what was
concluded. Generalization to unseen object instances is measured separately
from seen ones. Every gate states its threshold before the run rather than
after it.

**v0.9.0 release criteria.** The loop closes inside CLAVE: frames leave the
simulator, inference produces a decision, the Rust safety layer accepts or
overrides it, and the decision is published to a consumer. Decision latency is
measured at p99 against a stated budget with a Criterion benchmark. A test
proves the safety layer overrides an action that leaves the workspace. The
report states plainly that nothing was validated on hardware.

This step was narrowed on 2026-09-14. It previously also required FRET to drive
the arm, which bundled four things under one label and two of them had never
been designed: the boundary by which Rust consumes a model trained in Python,
deferred at v0.3.0 and still open, and a ROS 2 integration crossing into a
sibling repository with its own roadmap. Both now sit at v0.10.0, so v0.9.0
proves the loop CLAVE owns end to end and v0.10.0 hands it to FRET.

**v0.10.0 release criteria.** CLAVE's published decision reaches FRET and drives
the manipulator in FRET's MuJoCo SITL. This is the first step that depends on a
sibling repository at runtime rather than for assets, and it needs ROS 2, which
CLAVE does not depend on today. Nothing here runs on hardware.

### v1.0.0

| Version | Spec | What lands |
| --- | --- | --- |
| v1.0.0 | `benchmark-suite` | The benchmark comparing every candidate, the chosen configuration, and the evidence pack |

**v1.0.0 release criteria.** The benchmark runs from one command and reports
throughput, per-class sorting accuracy, pick success rate, cycle time, and
latency percentiles for every candidate in one table. The chosen configuration
is named along with the reason it beat the others. Every number is reproducible
from a seed and a manifest. The release states what was verified in simulation
and what a human has to check before any of it touches hardware.

Beyond v1.0.0, the v1.x line continues in simulation for work that needs no
hardware. A hardware era would open at v2.0.0 and has no plan in this document,
matching how FRET separates its own eras.

## Boundary Strategy

- **Why this split**: the study blocks produce documents, the foundation blocks
  produce interfaces and storage, and the training blocks produce runnable
  pipelines. A spec that mixes those three kinds of output cannot state a
  release criterion anybody can check. Splitting at the kind of artifact keeps
  each spec testable on its own terms.
- **Shared seams to watch**:
  - The material taxonomy from v0.2.0 is consumed by the asset tagging in
    v0.5.0, the label mapping in v0.6.0, and the confusion metrics in v0.8.0. A
    class renamed in one place and not the others silently corrupts every
    downstream number.
  - The model interface from v0.4.0 is what v0.7.0 trains against and what
    v0.9.0 loads at runtime. If it leaks a specific architecture's assumptions,
    swapping candidates stops being cheap.
  - The scene configuration from v0.5.0 is shared by data generation, training,
    and validation. Validation must run on scene variants training never saw,
    which is a property of how the configuration is partitioned rather than an
    afterthought.
  - The decision CLAVE publishes is consumed by FRET. It is specified by
    `pick-decision-contract`, which predates this roadmap and needs the
    realignment noted below.

## Existing Spec Updates

- [ ] pick-decision-contract -- realign the decision payload and the consumer
  boundary with the learned-policy architecture, and correct the claim that
  ARCO consumes CLAVE output directly when ARCO is a library FRET calls.
  Dependencies: none

Both questions are settled. The maintainer confirmed on 2026-09-14 that the
output is a pick location plus a material class, so the payload stays a discrete
pick decision and the "continuous action" framing is withdrawn. FRET is the
consumer, and its planner nodes reach ARCO as a library.

The spec's original requirements already described exactly that payload, so they
stand. Its design needed one correction: its `MaterialClass` carried TrashNet's
six labels, which v0.2.0 superseded with the eleven-class taxonomy. That is the
drift the taxonomy's stability section named in advance, and it is now aligned.

The spec carries the first Rust crate and the workspace gates, so it depends on
no learning work and can land at any point on the ladder.

## Direct Implementation Candidates

- [x] Correct the sibling-project descriptions across `README.md`,
  `CONTRIBUTING.md`, `docs/guidelines.md`, and the steering documents. BOSSA is
  a C++20 telemetry runtime writing SQLite and Cloudflare D1, not a neural
  inference runtime, and ARCO is reached through FRET.
- [x] Repair the typography the writing guidelines forbid in the documents
  rewritten before this roadmap: em dashes outside prose and one negative
  parallelism in `README.md`.

Both landed with the commit that introduced this file, so nothing here is
outstanding. The section stays because the entries record what was corrected
and why, which a later reader needs in order to trust the sibling boundaries
the ladder rests on.

## Specs (dependency order)

- [x] training-infrastructure-review -- Survey waste datasets, candidate architectures, and training infrastructure, and name what advances. Dependencies: none
- [x] waste-taxonomy -- Define material classes from recovery-facility practice, map everyday objects onto them, and set the channel and reject policy. Dependencies: training-infrastructure-review
- [x] learning-platform -- Choose the deep learning framework, corpus storage and versioning, experiment tracking, and the reproducibility rules. Dependencies: training-infrastructure-review
- [x] model-candidates -- Put at least three open-source perception architectures and three policy architectures behind one interface. Dependencies: training-infrastructure-review, learning-platform
- [x] sorting-world -- Build the MuJoCo conveyor scene with a ROBOTIS arm, channel bins, tagged waste assets, and YAML randomization knobs. Dependencies: waste-taxonomy
- [x] data-pipeline -- Ingest public corpora, generate labeled rollouts from the world, record expert demonstrations, and produce reproducible splits. Dependencies: waste-taxonomy, learning-platform, sorting-world
- [x] validation-harness -- Define sorting and picking metrics, the validation protocol on unseen scenes, and the pass gates. Dependencies: waste-taxonomy, sorting-world
- [x] training-application -- Train every candidate by imitation from the scripted expert, then fine-tune with reinforcement learning under domain randomization. Dependencies: model-candidates, data-pipeline
- [ ] sitl-runtime -- Close the loop in Rust: inference, safety override, decision publication, and the p99 latency benchmark. Dependencies: training-application, sorting-world
- [ ] fret-integration -- Hand the published decision to FRET over ROS 2 so it drives the manipulator in SITL. Dependencies: sitl-runtime
- [ ] benchmark-suite -- Compare every candidate in one reproducible benchmark and record the chosen configuration. Dependencies: sitl-runtime, validation-harness

Checkboxes above track the roadmap step, which closes when its deliverable
lands, not when its spec is written.

| Spec | Requirements | Design | Tasks | Step |
| --- | --- | --- | --- | --- |
| training-infrastructure-review | Approved | Approved | Approved | Delivered, tagged v0.1.0 |
| waste-taxonomy | Approved | Approved | Approved | Delivered, tagged v0.2.0 |
| learning-platform | Approved | Approved | Approved | Delivered, tagged v0.3.0 |
| model-candidates | Approved | Approved | Approved | Delivered, tagged v0.4.0 |
| sorting-world | Approved | Approved | Approved | Delivered, tagged v0.5.0 |
| data-pipeline | Approved | Approved | Approved | Delivered, tagged v0.6.0 |
| training-application | Approved | Approved | Approved | Delivered, tagged v0.7.0 |
| validation-harness | Approved | Approved | Approved | Delivered, tagged v0.8.0 |
| every other spec | Not started | Not started | Not started | Not started |

v0.1.0 delivered [docs/research/training-infrastructure-review.md](../../docs/research/training-infrastructure-review.md).
Two of its acceptance criteria are partially unmet and recorded in that
document's open questions rather than closed silently: the compute budget waits
on a maintainer input, and release-date verification is incomplete.

Authoring waves, given those dependencies:

| Wave | Specs |
| --- | --- |
| 1 | training-infrastructure-review |
| 2 | waste-taxonomy, learning-platform |
| 3 | model-candidates, sorting-world |
| 4 | data-pipeline, validation-harness |
| 5 | training-application |
| 6 | sitl-runtime |
| 7 | benchmark-suite |

## What CLAVE reuses from the family

| Source | What CLAVE takes | Where it lives |
| --- | --- | --- |
| FRET | MuJoCo physics SITL, gate cameras, the robot-agnostic `PickPlaceFSM`, the YAML configuration policy, and the asset submodule convention | `src/fret/` in the FRET repository |
| FRET submodule | OpenMANIPULATOR-X, 4 revolute joints plus a parallel gripper, and OpenMANIPULATOR-Y, 6 revolute joints | `third_party/robotis_mujoco_menagerie` |
| FRET submodule | Warehouse props and textures, including bucket and clutter meshes | `third_party/aws-robomaker-small-warehouse-world`, MIT-0 |
| ARCO | Joint-space planning and `JointSpaceMPC`, reached through FRET's planner nodes | ARCO repository, Python library |
| BOSSA | The telemetry contract for a later hardware era, out of scope for v1.x | BOSSA repository, C++20 |

## Candidate inputs for the v0.1.0 review

These are starting points for the review to evaluate, not decisions. The review
is the step that accepts or rejects each one, with its license and its fit
recorded.

**Waste imagery corpora**

| Corpus | Shape | Why it is a candidate |
| --- | --- | --- |
| ZeroWaste | About 4,600 annotated images and 6,000 unlabeled frames from a real recovery facility conveyor | The only shortlisted corpus whose imagery matches CLAVE's actual scene |
| TACO | About 1,500 outdoor images across 60 categories | Wide category coverage and real clutter, at the cost of an unrelated background |
| TrashNet | 2,527 images across six classes, controlled indoor capture | A cheap sanity baseline, weak on generalization |
| waste-datasets-review | An index of litter and waste image datasets | A survey entry point rather than a corpus |

**Simulated object meshes**

Recorded at v0.1.0 as a candidate input and resolved on 2026-09-14. The v0.1.0
design placed mesh sources at v0.5.0, next to the world that consumes them, and
v0.5.0 then shipped parametric primitives instead: they give correct mass,
footprint and grasp width for belt dynamics, which is what the pick policy
needs, and give nothing for appearance.

That tradeoff stands, and its cost is already recorded where it bites. Frames
from this world show shape rather than material, so perception trained on them
alone is weak by construction. Adopting `mujoco_scanned_objects`, 1,030 MJCF
models from Google Scanned Objects under CC-BY 4.0 meshes with MIT XML, is the
refinement that would close it, and it is a v0.5.x patch rather than an open
question.

**Architectures**

The review has to cover perception, meaning detection and segmentation on
conveyor imagery, and the pick policy, meaning a mapping from observation to
action. Published starting points include Diffusion Policy for multimodal
action distributions, action-chunking transformers for smooth trajectories,
behavior cloning as the honest baseline, and an on-policy reinforcement method
for fine-tuning in simulation.

**Training infrastructure**

MuJoCo with MJX for parallel rollouts on a GPU, Gymnasium for the environment
API, and the question of PyTorch against JAX, which the review settles with a
reason rather than a preference.

## References

- [ZeroWaste dataset](https://openreview.net/pdf?id=DAkP1TT_Ubm), conveyor imagery from a full-scale recovery facility.
- [waste-datasets-review](https://github.com/AgaMiko/waste-datasets-review), an index of litter and waste image datasets.
- [mujoco_scanned_objects](https://github.com/kevinzakka/mujoco_scanned_objects), MJCF models of Google Scanned Objects.
- [Google Scanned Objects](https://arxiv.org/abs/2204.11918), the source dataset of 1,030 scanned household items.
- [Diffusion Policy](https://arxiv.org/abs/2303.04137), visuomotor policy learning through action diffusion.
- [The Plastic Recycling Process](https://plasticsrecycling.org/how-recycling-works/the-plastic-recycling-process/), Association of Plastic Recyclers, on resin separation.
- [Materials Recovery Center](https://www3.epa.gov/recyclecity/recovery.htm), US EPA, on what a facility separates.
- [FRET roadmap](https://github.com/alexandrelheinen/fret/blob/main/docs/roadmap.md), the era convention this ladder follows.
