# Gradient accumulation

Status: draft

## Intent

One frame is a legal gradient and a noisy one. An optimizer step sums a
configured number of frames, and those frames come from different rollouts
whenever more than one rollout still has frames left.

## Scope

**In scope:**

- Required `training.accumulation_steps` in every training file. `1` steps
  on every microbatch, which is the previous loop.
- A window of that many microbatches, then one optimizer update. Each loss
  is scaled by `1 / accumulation_steps`.
- A seeded schedule of the stored pick, built before an epoch reads pixels.
  A window draws its microbatches from distinct rollouts when at least as
  many rollouts still have unused frames as the window asks for. A rollout
  may repeat inside a window only when fewer rollouts remain.

**Out of scope:**

- Holding more than one archive resident.
- A cache of decoded frames.
- Loader workers.
- Raising `batch_size`.

## Acceptance criteria

`AC-ACCUM-01`: When a training configuration is loaded, the system shall
read `training.accumulation_steps` and shall fail naming the key when it is
absent. The value shall be an integer of at least one. When the value is
`1`, each window shall hold one microbatch, and the rollouts shall stay in
archive order.

`AC-ACCUM-02`: When at least `accumulation_steps` rollouts still have unused
frames, a window shall contain that many microbatches and their rollout ids
shall be distinct.

`AC-ACCUM-03`: When fewer than `accumulation_steps` rollouts still have
unused frames, and at least two remain, a window may repeat a rollout. The
same seed and epoch shall rebuild the same windows.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-ACCUM-01` | `test_ac_accum_01_one_step_keeps_archive_order` |
| `AC-ACCUM-02` | `test_ac_accum_02_a_window_uses_distinct_rollouts` |
| `AC-ACCUM-03` | `test_ac_accum_03_the_tail_may_repeat_a_rollout` |

## Constraints

- Corpus classification and detection set `accumulation_steps` to 8. The
  other training files set it to 1.
- The schedule is a function of the stored indexes, the batch size, the
  accumulation count, the seed, and the epoch. It does not read pixels.
- One archive is loaded for one microbatch and released before the next.

## Design notes

`K = L / (V * dt)` is unchanged. Accumulation changes when the optimizer
steps, not which frames the sample keeps. A short tail window still steps.
The recorded epoch loss is the mean of the unscaled objective.
