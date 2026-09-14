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

CLAVE's intended use, which `S1` is judged against, is **personal research**,
confirmed by the maintainer on 2026-09-14. A license restricted to
non-commercial use therefore passes `S1`. A copyleft license that attaches
obligations to *distribution* still fails, because this repository is public and
MIT licensed, and that is a separate question from whether money changes hands.

The first version of this review judged `S1` against an industrial sorting line
and rejected ZeroWaste on those grounds. That reading is superseded.

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

**State: resolved.** Inventory supplied by the maintainer on 2026-09-14 and
verified by inspecting the machine.

| Component | Value |
| --- | --- |
| CPU | AMD Ryzen 7 7735U, 8 cores and 16 threads, mobile U-series |
| GPU | AMD Radeon 680M integrated, device `0x1681`, 512 MB dedicated |
| Accelerated compute | None usable. No CUDA runtime, no `nvidia-smi`, no NVIDIA device. WSL exposes `libd3d12` and `libdxcore` only, which are graphics rather than compute |
| ROCm | Not installed, and ROCm on WSL supports selected discrete Radeon cards rather than integrated RDNA2 graphics |
| Memory available to WSL | 7 GiB |
| Access | Shared. This is the maintainer's working laptop |

The maintainer expected GPU acceleration to be available. It is not, and that
correction is the single most consequential fact in this revision. The budget is
**CPU-only, on a mobile processor, inside 7 GiB**.

`torch-directml` is the one remaining accelerated path on this hardware, since
DirectX 12 is present. It carries partial operator coverage and lags upstream
PyTorch, so it is recorded as an option to evaluate rather than counted as
available compute.

### How costs below were produced

Every figure in the `Estimated training cost` column is an **estimate, not a
measurement**. Nothing has been trained. Each estimate assumes single-machine
CPU execution at 16 threads and states the throughput assumption it rests on.
They are intended to separate hours from weeks, which is all `S4` needs, and
they should be replaced with measurements at v0.7.0.

## Shortlist

Grouped by the roadmap step that consumes it, ordered within each group by the
criteria tables above.

### Consumed by v0.3.0 `learning-platform`

**Corpora**

1. **ZeroWaste**, now the strongest corpus in the shortlist. Operating recovery
   facility conveyor, localization annotations, and roughly five times
   SpectralWaste's labeled volume. Decided by `C-CORPUS-1`, `C-CORPUS-3` and
   `C-CORPUS-5` together. It ranks below SpectralWaste on `C-CORPUS-2` alone,
   since NonCommercial is a weaker permission than CC BY, and that criterion
   loses to three others.
2. **SpectralWaste**, also captured on an operating sorting line, under the more
   permissive license. Ranked second on `C-CORPUS-5`: 852 labeled images is
   enough to evaluate against and thin to fine-tune on.
3. **TACO**, permissive and localized, carrying the widest category coverage of
   any advancing corpus. Ranked below both on `C-CORPUS-1`, since its imagery is
   outdoor litter rather than a belt.
4. **TrashNet**, advancing as `Baseline` only. It fails `C-CORPUS-3` outright,
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

1. **Faster R-CNN with MobileNetV3-Large FPN**, BSD-3 and the only advancing
   detector the budget admits. Decided by `C-ARCH-3`, since it is the one
   localizing architecture whose training cost is measured in hours.
2. **SAM 2**, Apache-2.0, promptable segmentation with video propagation, which
   is the closest published match to tracking an object across frames. It
   advances because it is used zero-shot and needs no training, so `S4` does not
   bind. Its CPU inference latency is a serious open risk against `C-ARCH-3`.
3. **torchvision ResNet-50**, advancing as `Baseline`. It cannot localize, so it
   exists to show what the localizing options are worth.

Two absences are worth naming. Ultralytics YOLO is the most widely used detector
in this domain and fails `S1` on AGPL-3.0. RT-DETR and Detectron2, which led
this shortlist in the previous revision, now fail `S4`: they are fine
architectures on hardware this project does not have.

**Policy architectures**, four advancing, meeting the roadmap target of three. Unchanged by this revision: all four are CPU-trainable at reduced scale, and MuJoCo rollouts are the workload a CPU handles best.

1. **Diffusion Policy**, MIT, strongest on `C-ARCH-2`: it learns from
   demonstrations, which is exactly what FRET's scripted expert produces.
2. **ACT**, MIT, same training signal, with action chunking that suits a timed
   pick.
3. **PPO through stable-baselines3**, MIT, the reinforcement path, learning from
   reward rather than demonstrations.
4. **Behavior cloning**, advancing as `Baseline`, implemented in-project.

OpenVLA is the notable absence among policies, rejected on `S3`.

### Criteria that did not decide anything

Three criteria separated no candidate in this revision: `C-CORPUS-4`,
`C-ARCH-4`, and `C-ARCH-5`. That is down from six, because resolving the compute
budget put `C-ARCH-3` and `C-CORPUS-5` to work deciding real calls.

`C-ARCH-4` stays inert for a poor reason: the maintenance signals it reads are
among the cells this review left unverified. It cannot decide anything until
somebody fills them in.

The three are retained because v0.4.0 scores the shortlist against the same
tables once the candidates are running, and a criterion that separates nothing
on paper can separate a great deal once there are measurements.

### Roadmap target

Met for both stages, but narrowly on the perception side. Three perception and
four policy architectures advance against a target of three each, and each stage
carries the required simple comparator.

Perception has no margin. Of its three, one is a baseline that cannot localize
and one is used zero-shot with unmeasured CPU latency. If the Faster R-CNN cost
estimate proves optimistic, or if SAM 2 turns out too slow for a conveyor, the
target is unmet and v0.4.0 has to say so rather than proceed quietly.

## Candidate registers

### Corpus register

| Corpus | License | Size | Annotation type | Capture conditions | Difference from CLAVE scene | Constraint failed | Verdict | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SpectralWaste | CC BY 4.0 | 852 labeled images, 2,059 instances, 6,803 unlabeled RGB and hyperspectral frames | Semantic segmentation, six classes | Operating waste sorting plant for plastics, cartons and cans, conveyor belt, fixed camera | Carries a hyperspectral channel CLAVE has no sensor for; its six classes are object kinds such as film and trash bags rather than material classes | - | Advance | [arXiv 2403.18033](https://arxiv.org/abs/2403.18033) |
| ZeroWaste | CC BY-NC 4.0 | About 4,500 labeled images, about 27,000 instances, about 6,000 unlabeled frames | Detection and segmentation | Operating material recovery facility, conveyor belt | None material: this is the closest published match to CLAVE's scene | - | Advance | [ai.bu.edu/zerowaste](https://ai.bu.edu/zerowaste) |
| TACO | CC BY 4.0 | About 1,500 images, 60 categories | Segmentation masks in COCO format | Outdoor, in the wild, litter in streets and nature | Background is ground and vegetation rather than a belt; no conveyor motion; objects appear singly rather than as a stream | - | Advance | [tacodataset.org](http://tacodataset.org/) |
| TrashNet | MIT | 2,527 images, six classes | Whole-image classification only | Controlled indoor capture, one object on a plain background | No clutter, no occlusion, no belt, and no localization to learn from | - | Baseline | [github.com/garythung/trashnet](https://github.com/garythung/trashnet) |
| WaDaBa | Images downloadable; annotations released only after signing a license whose terms are not publicly inspectable | About 2,000 images | Classification by plastic resin code | Controlled indoor capture, objects well separated from background | Objects are isolated rather than cluttered, which is the opposite of a belt | S1 | Reject | [waste-datasets-review](https://github.com/AgaMiko/waste-datasets-review) |

Licenses above were checked on 2026-09-14.

ZeroWaste advances in this revision. It was rejected in the first version on
`CC BY-NC 4.0` against an industrial sorting line; the maintainer confirmed on
2026-09-14 that CLAVE is personal research, under which a NonCommercial term is
satisfied. It is now the strongest corpus in the shortlist: the only one whose
imagery is a material recovery facility conveyor at scale, with localization
annotations and roughly five times the labeled volume of SpectralWaste.

Its license still constrains what can be done later. A NonCommercial corpus
cannot train a model that is subsequently used commercially, so if CLAVE's
intent ever changes, every model trained on ZeroWaste has to be retrained.

### Architecture register

| Architecture | Stage | License | Weights license | Last release | Training signal | Estimated training cost | Published result | Measured on | Constraint failed | Verdict | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Faster R-CNN MobileNetV3-Large FPN | Perception | BSD-3-Clause | BSD-3-Clause | Tracks PyTorch releases | n/a | Estimated 10 to 16 hours, assuming about 0.3 s per image for a forward and backward pass at 16 CPU threads, over 5,000 images and 30 epochs | Not extracted (2026-09-14) | Not extracted (2026-09-14) | - | Advance | [torchvision detection models](https://github.com/pytorch/vision) |
| SAM 2 | Perception | Apache-2.0 | Apache-2.0 | SAM 2.1 checkpoint, date not verified (2026-09-14) | n/a | No training required; used zero-shot for mask proposals, so `S4` does not bind | Not extracted (2026-09-14) | Not extracted (2026-09-14) | - | Advance | [arXiv 2408.00714](https://arxiv.org/abs/2408.00714) |
| torchvision ResNet-50 | Perception | BSD-3-Clause | BSD-3-Clause | Tracks PyTorch releases | n/a | Estimated 2 to 4 hours, assuming about 0.15 s per image at 16 CPU threads over 2,500 images and 30 epochs | n/a, used as a comparator | n/a | - | Baseline | [pytorch.org](https://github.com/pytorch/pytorch/blob/main/NOTICE) |
| RT-DETR | Perception | Apache-2.0 | Apache-2.0 | Not verified (2026-09-14) | n/a | Estimated 3 to 6 weeks, assuming about 1.5 s per image for a forward and backward pass at 16 CPU threads over 5,000 images and 40 epochs | Not extracted (2026-09-14) | Not extracted (2026-09-14) | S4 | Reject | [arXiv 2304.08069](https://arxiv.org/abs/2304.08069) |
| Detectron2 Mask R-CNN | Perception | Apache-2.0 | Apache-2.0 | Not verified (2026-09-14) | n/a | Estimated 4 to 8 weeks, on the same basis as RT-DETR with a heavier backbone and an added mask head | Not extracted (2026-09-14) | Not extracted (2026-09-14) | S4 | Reject | [github.com/facebookresearch/detectron2](https://github.com/facebookresearch/detectron2) |
| Ultralytics YOLO | Perception | AGPL-3.0 | AGPL-3.0 | YOLO26, January 2026 | n/a | Not estimated; rejected on license before cost was considered | Not extracted (2026-09-14) | Not extracted (2026-09-14) | S1 | Reject | [docs.ultralytics.com](https://docs.ultralytics.com/models/yolo26) |
| Diffusion Policy | Policy | MIT | Trained in project | Not verified (2026-09-14) | Demonstrations | Estimated 3 to 7 days, assuming a reduced-width network on simulated rollouts at 16 CPU threads | 46.9 percent average improvement over the prior state of the art | 15 tasks across 4 manipulation benchmarks | - | Advance | [arXiv 2303.04137](https://arxiv.org/abs/2303.04137) |
| ACT | Policy | MIT | Trained in project | Not verified (2026-09-14) | Demonstrations | Estimated 2 to 5 days, assuming a reduced-depth transformer on simulated rollouts at 16 CPU threads | Not extracted (2026-09-14) | Bimanual fine manipulation tasks | - | Advance | [github.com/tonyzhaozh/act](https://github.com/tonyzhaozh/act) |
| PPO through stable-baselines3 | Policy | MIT | Trained in project | 2.9.0, 15 June 2026 | Reward | Estimated 6 to 20 hours for one million MuJoCo steps, assuming a small MLP policy and CPU rollouts, which is the workload MuJoCo is most efficient at | n/a, an algorithm implementation rather than a published result | n/a | - | Advance | [github.com/DLR-RM/stable-baselines3](https://github.com/DLR-RM/stable-baselines3) |
| Behavior cloning | Policy | n/a, implemented in project | Trained in project | n/a | Demonstrations | Estimated under 1 hour on recorded scripted-expert demonstrations | n/a, used as a comparator | n/a | - | Baseline | n/a, no upstream |
| OpenVLA | Policy | MIT for code | Llama Community License, inherited from Llama-2 | Not verified (2026-09-14) | Demonstrations at Open X-Embodiment scale, about 970,000 trajectories | Not estimated; rejected on training signal before cost was considered | Not extracted (2026-09-14) | Open X-Embodiment evaluation suite | S3 | Reject | [arXiv 2406.09246](https://arxiv.org/abs/2406.09246) |

Licenses above were checked on 2026-09-14.

Four rejections carry this register, and two of them are new in this revision.

Ultralytics YOLO fails `S1` and the change of intent does not save it. AGPL-3.0
attaches obligations to *distribution*, not to commerce, and this repository is
public and MIT licensed, so the conflict is unchanged by CLAVE being personal
research.

OpenVLA fails `S3`. FRET's scripted expert generates demonstrations
indefinitely, but for one task on one arm, and a model pretrained on roughly
970,000 trajectories across 70 robot datasets is not reachable from that signal.

RT-DETR and Detectron2 Mask R-CNN are the new rejections, both on `S4`. Neither
is a weak architecture; both are simply untrainable on a mobile CPU inside
7 GiB in any timeframe this project can absorb. They return the moment an
accelerator does, which is exactly what recording the failed constraint id is
for.

Their removal dropped the advancing perception count to two, below the roadmap
target of three. Rather than lower the bar, the review added a candidate the
resolved budget admits: torchvision's Faster R-CNN with a MobileNetV3-Large FPN
backbone, which is BSD-3, localizes, and fine-tunes in hours rather than weeks.
That is a re-screen driven by a changed constraint, which is the mechanism
working rather than a concession.

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

**The compute budget is resolved and the answer constrains the project.** The
maintainer expected GPU acceleration; the machine has an integrated AMD Radeon
680M with no CUDA and no ROCm path, 7 GiB of memory available to WSL, and a
mobile CPU. Two architectures were rejected on that basis. Nothing further is
needed to proceed, but two options would reopen them: an NVIDIA machine, or
`torch-directml`, which is the one accelerated path DirectX 12 leaves open on
this hardware and which carries partial operator coverage. Evaluating
`torch-directml` is a task for v0.3.0's successor rather than a blocker here.

**Every training cost in this document is an estimate, not a measurement.** They
separate hours from weeks, which is what `S4` needs, and no more. Closed by
v0.7.0 replacing them with measured wall-clock times. If the Faster R-CNN
estimate is wrong by a factor of five, the perception shortlist has one entry
and the roadmap target is unmet.

**ZeroWaste's NonCommercial term still binds later.** It passes `S1` under
personal research. A model trained on it cannot later be used commercially
without retraining. Closed only by CLAVE's intent staying research, and worth
re-reading if that ever changes.

**Release dates and published results are incompletely verified.** Unchanged
from the first revision. Cells marked `Not verified (2026-09-14)` and
`Not extracted (2026-09-14)` need a human with the upstream repositories open.
`AC-ARCH-02` and `AC-ARCH-04` stay partially unmet. No verdict depends on one of
those cells.

**Mesh sources were not surveyed.** Unchanged. The roadmap lists them here and
the design placed them at v0.5.0 `sorting-world`, next to the scene that
consumes them.

**SAM 2 inference latency on CPU is unmeasured and may be disqualifying.** It
advances because it needs no training, but a conveyor has a latency budget and a
promptable segmentation model on a mobile CPU is the least likely candidate here
to meet one. Closed by measuring it at v0.4.0, which is the step that reports
single-frame latency.

## Retrieval notes

No corpus was fetched. Every entry above was screened from its published
description, and the source column cites the reference documenting it rather
than a download link. WaDaBa's annotations were not retrieved, because they are
gated behind a license agreement whose terms are not publicly inspectable, which
is the reason for its `S1` rejection rather than a retrieval failure.
