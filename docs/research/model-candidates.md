# Model candidates, measured

> Roadmap step: v0.4.0 · Spec: [.kiro/specs/model-candidates/](../../.kiro/specs/model-candidates/)

[v0.1.2](training-infrastructure-review.md) named which architectures advance
and rejected two on estimated training cost. Every number behind those verdicts
was an estimate. This document replaces them with measurements.

All seven shortlisted architectures were loaded from their upstream libraries
and run. Nothing was trained, no corpus was read, and no accuracy was measured.
A forward pass on a synthetic fixture is a cost measurement and nothing else.

Two measurements contradict a v0.1.2 verdict, and one of them removes the
architecture that review called the strongest policy candidate.

## Measurement conditions

| Condition | Value |
| --- | --- |
| CPU | AMD Ryzen 7 7735U, 8 cores and 16 threads |
| Accelerator | None. Integrated AMD Radeon 680M, no CUDA runtime, no ROCm path |
| Compute threads | 8, as PyTorch reported them |
| Memory | 7 GiB available to WSL |
| PyTorch | 2.14.0+cpu |
| Warm-up | 2 untimed iterations per candidate, discarded |
| Timed runs | 5 per candidate; the median is reported with the full spread |
| Input | One synthetic 3x96x96 frame and a 6-dimensional state, generated from a fixed seed. No binary is committed |

Latency is measured one frame at a time. A conveyor produces frames singly and
batching across objects is not available, so per-frame cost is the number that
binds.

## Measurements

| Candidate | Stage | Parameters | Median latency | Spread | Repetitions | v0.1.2 estimate | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| faster-rcnn-mobilenetv3 | Perception | 18.98 M | 391.7 ms | 28.1 ms | 5 | 10 to 16 hours to train | Confirmed |
| resnet50-baseline | Perception | 23.53 M | 29.0 ms | 6.1 ms | 5 | 2 to 4 hours to train | Confirmed |
| sam2 | Perception | 38.96 M | 1229.2 ms | 41.5 ms | 5 | No training required | Contradicted |
| act | Policy | 51.60 M | 31.6 ms | 5.1 ms | 5 | 2 to 5 days to train | Confirmed |
| diffusion-policy | Policy | 262.95 M | 15479.1 ms | 295.5 ms | 5 | 3 to 7 days to train | Contradicted |
| ppo-mlp | Policy | 0.01 M | 0.2 ms | 0.0 ms | 5 | 6 to 20 hours to train | Confirmed |
| behavior-cloning-baseline | Policy | 0.02 M | 0.4 ms | 0.1 ms | 5 | Under 1 hour to train | Confirmed |

Every candidate loaded. No shortlisted architecture failed to load, and none
loaded but failed to run.

`Outcome` records whether the measurement is consistent with what v0.1.2
assumed, not whether the architecture is good. A `Confirmed` row means the
review's picture of that candidate survives; it does not mean the candidate is
fast enough for a conveyor.

## The same numbers as throughput

| Candidate | Frames or actions per second |
| --- | --- |
| ppo-mlp | about 5,000 |
| behavior-cloning-baseline | about 2,500 |
| resnet50-baseline | about 34 |
| act | about 32 |
| faster-rcnn-mobilenetv3 | about 2.6 |
| sam2 | about 0.8 |
| diffusion-policy | about 0.065, meaning one action every 15 seconds |

## The two contradictions

### Diffusion Policy costs 15.5 seconds per action

v0.1.2 ranked Diffusion Policy first among policy candidates, calling it
"strongest on `C-ARCH-2`" because it learns from demonstrations, which is
exactly what FRET's scripted expert produces. That reasoning still holds. The
cost does not.

At 15.5 seconds per action on this hardware, it is unusable at runtime by three
orders of magnitude, and training is worse: a reinforcement run stepping a
simulated environment one million times would spend roughly 180,000 hours inside
the policy alone. The v0.1.2 estimate of three to seven days was wrong by a
factor in the thousands, because it assumed a per-step cost rather than
accounting for the denoising loop.

The cause is structural rather than incidental. Diffusion Policy generates an
action by running a denoising chain, and lerobot's default configuration runs
100 steps. The 262.95 M parameter count is not the problem; running the network
a hundred times per action is.

There is a real mitigation and it is not free. The step count is configurable,
and a shorter chain trades action quality for speed. Ten steps would bring this
to roughly 1.5 seconds, which is still far outside a conveyor budget. Reaching
`act`'s 31.6 ms would need roughly two steps, at which point the architecture's
reason for existing is gone.

**Recommendation**: Diffusion Policy does not advance on this hardware. It
should be recorded against `S4` in the review, alongside RT-DETR and Detectron2,
and revisited if an accelerator appears. This document does not edit v0.1.2; the
verdict there still reads `Advance`, and the two disagree visibly until somebody
resolves it.

### SAM 2 costs 1.23 seconds per frame

v0.1.2 advanced SAM 2 because it is used zero-shot and needs no training, so
`S4` did not bind, and it named the risk explicitly: "SAM 2 inference latency on
CPU is unmeasured and may be disqualifying." It is disqualifying.

At 1.23 seconds per frame the encoder alone yields 0.8 frames per second. This
is the smallest published SAM 2 configuration, `hiera_t`, so there is no smaller
variant to fall back to.

Only the image encoder was timed. The mask decoder runs once per prompt and adds
to this rather than replacing it, so 1.23 seconds is a floor, not an estimate of
the whole pipeline.

**Recommendation**: SAM 2 does not advance on this hardware.

## What this does to the shortlist

v0.1.2 recorded that perception met its target of three "with no margin", and
warned that if SAM 2 proved too slow the target would be unmet. That is what
happened.

**Perception**, after these measurements:

| Candidate | Localizes? | Latency | Standing |
| --- | --- | --- | --- |
| faster-rcnn-mobilenetv3 | Yes | 391.7 ms | The only viable localizing candidate, and it is marginal |
| resnet50-baseline | No | 29.0 ms | Baseline. Classifies a whole frame, cannot say where anything is |
| sam2 | Yes | 1229.2 ms | Disqualified on latency |

One localizing candidate remains, at 2.6 frames per second. The roadmap target
of three advancing perception architectures is **unmet** in substance, and
`AC-SHORTLIST-03` requires saying so rather than counting three rows and moving
on.

**Policy**, after these measurements:

| Candidate | Latency | Standing |
| --- | --- | --- |
| act | 31.6 ms | The clear candidate. Learns from demonstrations, runs in real time |
| ppo-mlp | 0.2 ms | Viable. Learns from reward, which needs a reward function v0.5.0 has not written |
| behavior-cloning-baseline | 0.4 ms | Baseline |
| diffusion-policy | 15479.1 ms | Disqualified on latency |

Policy still meets its target of three, and `act` is now the one to beat rather
than one of several.

## What would have to change

Naming this now rather than discovering it at v0.7.0:

**An accelerator restores four candidates.** RT-DETR and Detectron2 were
rejected at v0.1.2 on training cost, and Diffusion Policy and SAM 2 are rejected
here on inference cost. All four are ordinary choices on a machine with a CUDA
GPU. This is the single change that would most improve CLAVE's options.

**A lighter localizing detector would restore the perception margin.** The
search at v0.1.0 was not conducted under a CPU-only constraint, so it did not
look for one. YOLOX and RF-DETR are Apache-2.0 and were noted but never
screened.

**A belt speed would turn latency into a pass or fail.** No belt speed, field of
view, or effector reach has been fixed; v0.5.0 sets them. Until then 391.7 ms is
a number without a threshold, and calling it marginal is a judgment rather than
a measurement.

## What was not measured

No training, no accuracy, no memory footprint, and no throughput under
concurrent load. Latency was measured with a single process on an otherwise idle
machine, which flatters every candidate relative to a running pipeline.

All measurements are CPU-only and become void the moment an accelerator appears.

Parameter counts are of freshly constructed architectures. Pretrained weights
were not loaded for the detector or SAM 2, because this step measures
architecture cost rather than model quality.
