# Training infrastructure review

> Roadmap step: v0.1.0 · Spec: [.kiro/specs/training-infrastructure-review/](../../.kiro/specs/training-infrastructure-review/)

CLAVE has to choose a corpus, a set of candidate architectures, and a training
platform before v0.3.0 and v0.4.0 can start. This review screens the options
that exist today and records which advance, which do not, and why.

It is a screening instrument rather than a literature summary. Nothing advances
because it is well known. Every option is judged against the four constraints
below, a rejection names the constraint it failed, and a reader who later
changes a constraint can find the rows worth revisiting by searching for its id.

Every fact about a third-party project carries a citation. Facts that will
expire, meaning release dates and license terms, carry the date they were
checked. Where a required field could not be verified, the cell says so rather
than carrying a plausible guess.

## Screening constraints

Applied uniformly to every option below, before any verdict.

| Id | Constraint |
| --- | --- |
| `S1` | The license permits CLAVE's intended use |
| `S2` | The option works with FRET's MuJoCo simulation and the ROBOTIS manipulators, without a different simulator or robot |
| `S3` | The training signal the option needs can be produced by FRET's scripted `PickPlaceFSM` expert |
| `S4` | Training fits the stated compute budget |

`S3` applies only to pick-policy architectures. Corpus and infrastructure rows
record it as not applicable rather than leaving it blank, so a blank always
means omission.

CLAVE's intended use, which `S1` is judged against, is the one stated in
[README.md](../../README.md): an industrial recycling sorting line. A license
restricted to non-commercial use fails `S1` under that reading. The maintainer
may narrow the stated intent to research, which would change two verdicts here;
that decision is recorded in [Open questions](#open-questions) rather than
assumed.

### Verdict vocabulary

Closed. A verdict cell contains exactly one of these.

| Verdict | Meaning |
| --- | --- |
| `Advance` | Passes every applicable constraint and appears in the shortlist |
| `Advance (provisional)` | Passes every applicable constraint except `S4`, which is unresolved |
| `Reject` | Fails at least one constraint; the failed constraint id is recorded |
| `Unavailable` | Cannot be retrieved from a working public source |
| `Baseline` | Advances as a deliberate simple comparator rather than on merit |

## Criteria tables

A constraint is pass or fail and produces a verdict. A criterion is comparative
and orders the survivors. The shortlist presents advancing entries in criteria
order and names the criterion that decided any close call.

### Corpora

| Id | Criterion | Weight |
| --- | --- | --- |
| `C-CORPUS-1` | Imagery was captured on a moving conveyor viewed from a fixed camera | High |
| `C-CORPUS-2` | License permits the intended use without further negotiation | High |
| `C-CORPUS-3` | Annotations support localization, not only whole-image classification | High |
| `C-CORPUS-4` | Label set can be mapped onto a material taxonomy | Medium |
| `C-CORPUS-5` | Size is sufficient to fine-tune on, not only to evaluate against | Medium |

### Architectures

| Id | Criterion | Weight |
| --- | --- | --- |
| `C-ARCH-1` | License permits redistribution alongside MIT code without a copyleft obligation | High |
| `C-ARCH-2` | Training signal is obtainable from a scripted expert rather than human teleoperation | High |
| `C-ARCH-3` | Inference cost is compatible with a conveyor latency budget | High |
| `C-ARCH-4` | Upstream shows activity within the last twelve months | Medium |
| `C-ARCH-5` | Reference implementation runs without a bespoke data format | Medium |

### Infrastructure

| Id | Criterion | Weight |
| --- | --- | --- |
| `C-INFRA-1` | Runs against FRET's MuJoCo stack without forking it | High |
| `C-INFRA-2` | License is permissive | High |
| `C-INFRA-3` | Seed control and environment pinning are documented | High |
| `C-INFRA-4` | Serves both the imitation and the reinforcement path | Medium |
| `C-INFRA-5` | Does not duplicate a capability FRET already owns | Medium |

## Compute budget

**State: unresolved.**

The hardware inventory was requested from the maintainer on 2026-09-14 and has
not been supplied. `AC-COMPUTE-01` needs the accelerator model, its memory, and
whether access is continuous or shared. No agent can observe what machines this
project may use, and assuming one would be the fabrication `AC-DOC-04` forbids.

Two consequences follow, and both are visible in the registers below.

Every architecture row carries `pending budget` in its estimated training cost
cell rather than a number. No option is rejected under `S4` while the budget is
unresolved, so an architecture that would otherwise advance carries the verdict
`Advance (provisional)` instead of `Advance`.

Resolving the inventory converts every `pending budget` cell into wall-clock
time with its governing assumption named, and turns every provisional verdict
final or rejected.

## Shortlist

Grouped by the roadmap step that consumes it, ordered within each group by the
criteria tables above.

### Consumed by v0.3.0 `learning-platform`

**Corpora**

1. **SpectralWaste**, the only advancing corpus captured on an operating
   sorting line under a permissive license. Decided by `C-CORPUS-1` and
   `C-CORPUS-2` together: ZeroWaste matches the scene as well but fails `S1`.
2. **TACO**, permissive and localized, carrying the widest category coverage of
   any advancing corpus. Ranked below SpectralWaste on `C-CORPUS-1`, since its
   imagery is outdoor litter rather than a belt.
3. **TrashNet**, advancing as `Baseline` only. It fails `C-CORPUS-3` outright,
   carrying whole-image labels with no localization, which makes it a sanity
   check rather than a training corpus.

**Infrastructure**

1. **MuJoCo**, which is not a choice so much as the thing FRET already runs.
   Perfect on `C-INFRA-1` and `C-INFRA-5`.
2. **PyTorch**, advancing over JAX on `C-INFRA-4`: every candidate policy
   architecture below ships a PyTorch reference implementation, and none ships
   a JAX one. This is the close call of the infrastructure group, and
   `C-INFRA-4` decided it. JAX wins on parallel rollout throughput through MJX,
   which is why it advances too rather than being rejected.
3. **Gymnasium**, the environment interface both `stable-baselines3` and the
   MuJoCo ecosystem expect.
4. **stable-baselines3**, for the reinforcement path.
5. **LeRobot**, for the imitation path, carrying reference implementations of
   two of the three advancing policy architectures.
6. **JAX with MJX**, advancing for parallel rollouts specifically, not as the
   primary framework.

### Consumed by v0.4.0 `model-candidates`

**Perception architectures**, four advancing, meeting the roadmap target of three.

1. **RT-DETR**, Apache-2.0 and transformer-based, strongest on `C-ARCH-1` and
   `C-ARCH-3` together.
2. **Detectron2 Mask R-CNN**, Apache-2.0, instance segmentation rather than
   boxes, which suits overlapping objects on a belt.
3. **SAM 2**, Apache-2.0, promptable segmentation with video propagation, which
   is the closest published match to tracking an object across frames.
4. **torchvision ResNet-50**, advancing as `Baseline`. It cannot localize, so it
   exists to show what the sophisticated options are worth.

Ultralytics YOLO is the notable absence. It is the most widely used detector in
this domain and it fails `S1`.

**Policy architectures**, four advancing, meeting the roadmap target of three.

1. **Diffusion Policy**, MIT, strongest on `C-ARCH-2`: it learns from
   demonstrations, which is exactly what FRET's scripted expert produces.
2. **ACT**, MIT, same training signal, with action chunking that suits a timed
   pick.
3. **PPO through stable-baselines3**, MIT, the reinforcement path, learning from
   reward rather than demonstrations.
4. **Behavior cloning**, advancing as `Baseline`, implemented in-project.

OpenVLA is the notable absence among policies, rejected on `S3`.

### Criteria that did not decide anything

Six criteria separated no candidate in this round: `C-CORPUS-4`, `C-CORPUS-5`,
`C-ARCH-4`, `C-ARCH-5`, `C-INFRA-2`, and `C-INFRA-3`. They are retained rather
than deleted because v0.4.0 scores the shortlisted architectures against the
same tables once they are running, and a criterion that separates nothing on
paper can separate a great deal once there are measurements. `C-ARCH-4` in
particular is inert here only because the maintenance signals it reads are
among the cells this review left unverified.

Naming them is the point. A criteria table nobody cites is decoration, and the
honest way to keep one is to say which parts of it are not yet doing work.

### Roadmap target

Met for both stages. Four perception and four policy architectures advance,
against a target of three each, and each stage carries the required simple
comparator.

## Candidate registers

### Corpus register

| Corpus | License | Size | Annotation type | Capture conditions | Difference from CLAVE scene | Constraint failed | Verdict | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SpectralWaste | CC BY 4.0 | 852 labeled images, 2,059 instances, 6,803 unlabeled RGB and hyperspectral frames | Semantic segmentation, six classes | Operating waste sorting plant for plastics, cartons and cans, conveyor belt, fixed camera | Carries a hyperspectral channel CLAVE has no sensor for; its six classes are object kinds such as film and trash bags rather than material classes | - | Advance | [arXiv 2403.18033](https://arxiv.org/abs/2403.18033) |
| ZeroWaste | CC BY-NC 4.0 | About 4,500 labeled images, about 27,000 instances, about 6,000 unlabeled frames | Detection and segmentation | Operating material recovery facility, conveyor belt | None material: this is the closest published match to CLAVE's scene | S1 | Reject | [ai.bu.edu/zerowaste](https://ai.bu.edu/zerowaste) |
| TACO | CC BY 4.0 | About 1,500 images, 60 categories | Segmentation masks in COCO format | Outdoor, in the wild, litter in streets and nature | Background is ground and vegetation rather than a belt; no conveyor motion; objects appear singly rather than as a stream | - | Advance | [tacodataset.org](http://tacodataset.org/) |
| TrashNet | MIT | 2,527 images, six classes | Whole-image classification only | Controlled indoor capture, one object on a plain background | No clutter, no occlusion, no belt, and no localization to learn from | - | Baseline | [github.com/garythung/trashnet](https://github.com/garythung/trashnet) |
| WaDaBa | Images downloadable; annotations released only after signing a license whose terms are not publicly inspectable | About 2,000 images | Classification by plastic resin code | Controlled indoor capture, objects well separated from background | Objects are isolated rather than cluttered, which is the opposite of a belt | S1 | Reject | [waste-datasets-review](https://github.com/AgaMiko/waste-datasets-review) |

Licenses above were checked on 2026-09-14.

ZeroWaste is the most painful rejection in this review. It is the only corpus
whose imagery is a material recovery facility conveyor at scale, and its
`CC BY-NC 4.0` term forbids commercial use, which conflicts with the industrial
sorting line CLAVE's README describes. See [Open questions](#open-questions).

### Architecture register

| Architecture | Stage | License | Weights license | Last release | Training signal | Estimated training cost | Published result | Measured on | Constraint failed | Verdict | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RT-DETR | Perception | Apache-2.0 | Apache-2.0 | Not verified (2026-09-14) | n/a | pending budget | Not extracted (2026-09-14) | Not extracted (2026-09-14) | - | Advance (provisional) | [arXiv 2304.08069](https://arxiv.org/abs/2304.08069) |
| Detectron2 Mask R-CNN | Perception | Apache-2.0 | Apache-2.0 | Not verified (2026-09-14) | n/a | pending budget | Not extracted (2026-09-14) | Not extracted (2026-09-14) | - | Advance (provisional) | [github.com/facebookresearch/detectron2](https://github.com/facebookresearch/detectron2) |
| SAM 2 | Perception | Apache-2.0 | Apache-2.0 | SAM 2.1 checkpoint, date not verified (2026-09-14) | n/a | pending budget | Not extracted (2026-09-14) | Not extracted (2026-09-14) | - | Advance (provisional) | [arXiv 2408.00714](https://arxiv.org/abs/2408.00714) |
| torchvision ResNet-50 | Perception | BSD-3-Clause | BSD-3-Clause | Tracks PyTorch releases | n/a | pending budget | n/a, used as a comparator | n/a | - | Baseline | [pytorch.org](https://github.com/pytorch/pytorch/blob/main/NOTICE) |
| Ultralytics YOLO | Perception | AGPL-3.0 | AGPL-3.0 | YOLO26, January 2026 | n/a | pending budget | Not extracted (2026-09-14) | Not extracted (2026-09-14) | S1 | Reject | [docs.ultralytics.com](https://docs.ultralytics.com/models/yolo26) |
| Diffusion Policy | Policy | MIT | Trained in project | Not verified (2026-09-14) | Demonstrations | pending budget | 46.9 percent average improvement over the prior state of the art | 15 tasks across 4 manipulation benchmarks | - | Advance (provisional) | [arXiv 2303.04137](https://arxiv.org/abs/2303.04137) |
| ACT | Policy | MIT | Trained in project | Not verified (2026-09-14) | Demonstrations | pending budget | Not extracted (2026-09-14) | Bimanual fine manipulation tasks | - | Advance (provisional) | [github.com/tonyzhaozh/act](https://github.com/tonyzhaozh/act) |
| PPO through stable-baselines3 | Policy | MIT | Trained in project | 2.9.0, 15 June 2026 | Reward | pending budget | n/a, an algorithm implementation rather than a published result | n/a | - | Advance (provisional) | [github.com/DLR-RM/stable-baselines3](https://github.com/DLR-RM/stable-baselines3) |
| Behavior cloning | Policy | n/a, implemented in project | Trained in project | n/a | Demonstrations | pending budget | n/a, used as a comparator | n/a | - | Baseline | n/a, no upstream |
| OpenVLA | Policy | MIT for code | Llama Community License, inherited from Llama-2 | Not verified (2026-09-14) | Demonstrations at Open X-Embodiment scale, about 970,000 trajectories | pending budget | Not extracted (2026-09-14) | Open X-Embodiment evaluation suite | S3 | Reject | [arXiv 2406.09246](https://arxiv.org/abs/2406.09246) |

Licenses above were checked on 2026-09-14.

Two rejections carry the weight of this register. Ultralytics YOLO is the
default detector in most published waste sorting work, and its AGPL-3.0 term
obliges anyone distributing a derived work to publish their own source under
the same terms, which CLAVE's MIT license cannot absorb. OpenVLA fails `S3`
rather than `S1`: FRET's scripted expert can generate demonstrations
indefinitely, but it generates them for one task on one arm, and a model
pretrained on roughly 970,000 trajectories across 70 robot datasets is not
reachable from that signal.

### Infrastructure register

| Option | Purpose | License | Runs on FRET MuJoCo unforked | Reproducibility requirements | Tradeoff against | Constraint failed | Verdict | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MuJoCo | Physics simulation, contacts, rendering | Apache-2.0 | Yes, this is what FRET already runs | Deterministic given a seed and a fixed model; pin the version | - | - | Advance | [github.com/google-deepmind/mujoco](https://github.com/google-deepmind/mujoco/blob/main/LICENSE) |
| PyTorch | Deep learning framework | BSD-3-Clause | Yes, independent of the simulator | Manual seed control; pin through a lockfile | JAX: PyTorch carries every candidate reference implementation, JAX carries none | - | Advance | [pytorch NOTICE](https://github.com/pytorch/pytorch/blob/main/NOTICE) |
| JAX with MJX | GPU and TPU parallel rollouts | Apache-2.0 | Partially: requires an MJX-compatible model, which is a porting cost rather than a fork | Explicit PRNG key threading; pin through a lockfile | PyTorch: JAX scales rollouts far better, PyTorch has the implementations | - | Advance | [github.com/jax-ml/jax](https://github.com/jax-ml/jax/blob/main/LICENSE) |
| Gymnasium | Environment API | MIT | Yes, wraps MuJoCo without replacing it | Seeded `reset`; pin through a lockfile | - | - | Advance | [github.com/Farama-Foundation/Gymnasium](https://github.com/Farama-Foundation/Gymnasium) |
| stable-baselines3 | Reinforcement learning algorithm implementations | MIT | Yes, through Gymnasium | Seed argument per algorithm; pin through a lockfile | LeRobot: this serves the reward path, LeRobot serves the demonstration path | - | Advance | [github.com/DLR-RM/stable-baselines3](https://github.com/DLR-RM/stable-baselines3/blob/master/LICENSE) |
| LeRobot | Imitation learning training stack | Apache-2.0 | Yes, simulator agnostic | Dataset and config versioning through the Hub; pin through a lockfile | stable-baselines3: LeRobot carries ACT and Diffusion Policy references, stable-baselines3 carries PPO | - | Advance | [huggingface.co/docs/lerobot](https://huggingface.co/docs/lerobot/act) |
| robosuite | Manipulation task scaffolding on MuJoCo | MIT, with an Apache-2.0 MuJoCo component | No: ships its own robot models, controllers and task suite, which duplicates FRET's arms and `PickPlaceFSM` | Seeded environments; pin through a lockfile | Raw MuJoCo with FRET, which already provides the scaffolding robosuite would add | S2 | Reject | [github.com/ARISE-Initiative/robosuite](https://github.com/ARISE-Initiative/robosuite) |

Licenses above were checked on 2026-09-14. robosuite v1.5 was released on
2024-10-28; stable-baselines3 2.9.0 was released on 2026-06-15; MuJoCo 3.2.7
was released on 2025-01-15, and whether a later version exists was not verified.

robosuite is the infrastructure rejection worth understanding. It is a good
project and it fails `S2` for the same reason it would be attractive elsewhere:
it supplies robot models, controllers, and a pick-and-place task suite, all of
which FRET already owns. Adopting it would mean running two manipulation stacks
and choosing between them at every boundary.

## Open questions

Each entry names who can close it and what closing it requires.

**The compute budget is unresolved.** Closed by the maintainer supplying the
accelerator model, its memory, and whether access is continuous or shared. Until
then, seven architectures carry `Advance (provisional)` rather than `Advance`,
and no option can be rejected on cost.

**ZeroWaste hinges on how CLAVE's intended use is stated.** Closed by the
maintainer. `CC BY-NC 4.0` forbids commercial use, and the README describes an
industrial sorting line, so `S1` fails on the current reading. If the stated
intent is narrowed to non-commercial research, ZeroWaste advances and becomes
the best-matched corpus in this review by a wide margin, ahead of SpectralWaste
on `C-CORPUS-5`. This single decision changes the corpus shortlist more than
anything else in this document.

**Release dates and published results are incompletely verified.** Closed by a
human filling the cells marked `Not verified (2026-09-14)` and
`Not extracted (2026-09-14)`. This review checked every license, which is what
the rejections turn on, and did not finish checking every maintenance signal.
`AC-ARCH-02` and `AC-ARCH-04` are therefore partially unmet, and this is
recorded rather than papered over. No verdict in this document depends on a
cell that carries one of those markers.

**Mesh sources were not surveyed.** The roadmap lists simulated object meshes
among this step's candidate inputs, and the design placed them at v0.5.0
`sorting-world` instead, because no approved requirement covers them and they
carry neither an annotation type nor capture conditions. Closed by the
maintainer either amending the roadmap entry or accepting the divergence.

**The corpus label sets have not been mapped onto a material taxonomy.** That
mapping is v0.2.0 `waste-taxonomy` work. This review records what each corpus
labels; it does not decide what CLAVE's classes are. SpectralWaste labels object
kinds such as film and trash bags rather than materials, so the mapping is not
trivial and should be treated as real work rather than a rename.

## Retrieval notes

No corpus was fetched. Every entry above was screened from its published
description, and the source column cites the reference documenting it rather
than a download link. WaDaBa's annotations were not retrieved, because they are
gated behind a license agreement whose terms are not publicly inspectable, which
is the reason for its `S1` rejection rather than a retrieval failure.
