# Training, measured

> Roadmap step: v0.7.0 · Spec: [.kiro/specs/training-application/](../../.kiro/specs/training-application/)

> **The geometry in this document was superseded at v1.0.1.** The belt, the arm
> offset, the reach radius, the belt speed and the object sizes were all
> rescaled after a solved workspace sweep found the manipulator could not reach
> the middle of its own belt and its gripper could not close on any object in
> the set. [world-scale.md](world-scale.md) carries the measurements and the new
> values. What this document records is what was measured at the time, and it is
> left standing rather than rewritten.


Four candidates were trained on the hardware this project actually has. This
document reports what that cost.

It reports nothing about whether any of them works. The dataset is 240 frames,
which is far too small to support a claim about accuracy, and every loss curve
below describes optimization on a toy. What the runs do establish is per-epoch
wall-clock, which [v0.1.2](training-infrastructure-review.md) estimated and had
no way to check.

## What was trained

Measured on an AMD Ryzen 7 7735U at 8 threads, no accelerator, PyTorch
2.14.0+cpu, three epochs each over a 160-frame training split.

| Candidate | Stage | Loss, first to last | Per-epoch cost |
| --- | --- | --- | --- |
| `behavior-cloning-baseline` | Policy | 0.0332 to 0.0094 | 0.7 s |
| `act` | Policy | 30.07 to 4.65 | 16.3 s |
| `resnet50-baseline` | Perception | 0.519 to 0.401 | 37.4 s |
| `faster-rcnn-mobilenetv3` | Perception | 0.878 to 0.589 | 136.9 s |

Every loss fell. That says the optimizer works and the data is learnable, and it
says nothing else. Three epochs on 160 frames is not convergence, and none of
these runs was stopped because it had converged.

## Measured cost against the v0.1.2 estimates

v0.1.2 estimated whole training runs rather than epochs, so the comparison needs
an assumption about epoch count. At 30 epochs, which is a plausible schedule for
a real dataset:

| Candidate | v0.1.2 estimate | Measured per epoch | Implied 30 epochs | Verdict |
| --- | --- | --- | --- | --- |
| `behavior-cloning-baseline` | Under 1 hour | 0.7 s | 21 seconds | Confirmed |
| `act` | 2 to 5 days | 16.3 s | 8 minutes | Estimate was pessimistic |
| `resnet50-baseline` | 2 to 4 hours | 37.4 s | 19 minutes | Estimate was pessimistic |
| `faster-rcnn-mobilenetv3` | 10 to 16 hours | 136.9 s | 68 minutes | Estimate was pessimistic |

**Read that table carefully, because it flatters the architectures.** The
estimates assumed a dataset of realistic size. These runs use 160 frames,
so the per-epoch figures are small because the epoch is small, not because the
architectures are cheap. Scaling to a corpus the size of ZeroWaste, roughly
4,500 labeled images, multiplies every figure by about 28. Faster R-CNN would
then reach roughly 32 hours at 30 epochs, which is above the original 10 to 16
hour estimate rather than below it, and ResNet-50 roughly 9 hours against an
estimate of 2 to 4.

So the estimates were not merely pessimistic; they were measuring a different
thing. Per example they were optimistic. `AC-COST-04` asks whether any v0.1.2
verdict is contradicted, and none is: the two architectures rejected there on
`S4`, RT-DETR and Detectron2, are both heavier than Faster R-CNN, and a 32 hour
projection for the lighter one supports their rejection rather than undermining
it.

What changed is that the estimates now rest on a measured per-example cost
rather than on a guess, and that cost is what scales.

## What was not trained, and why

Three shortlisted candidates were not trained. In each case the reason is a
missing signal or a measured cost, not a judgment about the architecture.

**`ppo-mlp` could not be trained at all.** Reinforcement learning needs an
environment the policy can act in and earn reward from. Nothing in CLAVE writes
`data.ctrl`: the manipulator is present in the scene and inert. There is no
action to take and therefore no reward to earn.

This is the single largest gap between the project as it stands and a working
system, and it belongs to v0.9.0, which closes the loop.

**`diffusion-policy` was excluded on measured cost.** v0.4.0 measured 15.5
seconds per action on this hardware, dominated by a hundred-step denoising
chain. A training run that samples actions is therefore slower than the belt it
is meant to control, and v0.5.0 established the object is reachable for 1.13
seconds.

**`sam2` requires no training.** It advanced at v0.1.2 as a zero-shot model. v0.5.0
then measured its encoder at 1.23 seconds a frame, above the whole per-object
budget, so it is disqualified on latency rather than on trainability.

### The roadmap target

The roadmap asks for at least three perception and three policy candidates with
completed runs.

**Perception is unmet: two of three.** `resnet50-baseline` and
`faster-rcnn-mobilenetv3` trained; `sam2` needs no training and is in any case
disqualified on latency. Meeting the target needs a third trainable detector,
and v0.4.0 already named the candidates never screened under a CPU-only
constraint: YOLOX and RF-DETR, both Apache-2.0.

**Policy is unmet: two of four.** `behavior-cloning-baseline` and `act` trained.
`ppo-mlp` needs actuation that does not exist, and `diffusion-policy` is too slow
to train or run. Meeting the target needs v0.9.0's control loop, after which
`ppo-mlp` becomes trainable.

Both targets are recorded as unmet rather than reported as met by counting
candidates that were screened but never trained.

## Two limits inherited from the data

**The policies are vision-only.** The dataset carries object state but never the
manipulator's joint positions, because nothing actuates it, so the state input to
every policy is zeroed. A policy that cannot see where its own arm is cannot
learn to account for it.

**ACT trains at a shorter horizon than v0.4.0 benchmarked.** Its upstream default
predicts a chunk of 100 actions. Captures here are half a second apart, so a
chunk of 100 would reach 50 seconds ahead, far past the 1.13 second window an
object is reachable for, and would be almost entirely padding. Training uses a
chunk of 10 and the run's configuration digest records it, so the trained model
and the benchmarked one are never mistaken for one another.

## What none of this shows

No accuracy, precision or recall figure appears in this document, and none should
be inferred from a loss. The training split is 160 frames drawn from six
rollouts of one simulated world, covering 8 of 11 material classes, with the
classes present imbalanced by a factor of three.

No model was evaluated against real imagery. The corpora fetched since, reported
in [corpus-ingestion.md](corpus-ingestion.md), are not in this dataset, and
nothing here was trained or scored on one. The synthetic frames show parametric
primitives, so a classifier trained on them learns shape rather than material,
which makes the perception results here weak by construction rather than by
accident. The policy side is what this data
genuinely supports.

Every measurement is CPU-only and becomes void the moment an accelerator appears.
