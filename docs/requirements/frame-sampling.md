# Frame sampling

Status: draft

## Intent

A training epoch on every corpus frame takes about an hour because consecutive
captures show the same objects. The run keeps a few frames per camera
crossing, stores that pick, and reloads it when a checkpoint already exists.

## Scope

**In scope:**

- `training.samples_per_crossing`, the number of looks kept while an object
  crosses the detection camera's along-belt footprint.
- A stride `floor(K / N)` from that footprint, the rollout belt speed, and
  the capture interval, with every frame kept when the crossing is shorter
  than `N`.
- A seeded phase per rollout, written to a manifest and into the checkpoint
  before the first epoch finishes.
- A resumed checkpoint training on the stored indexes.

**Out of scope:**

- Copying pixels into a second corpus.
- A D1 column for the sample. The manifest and the run record carry the digest.
- Thinning the published validation score. That pass still reads every
  validation frame.
- A global shuffle that would keep every kept frame resident at once.

## Acceptance criteria

`AC-SAMPLE-01`: When `samples_per_crossing` is `N` and a crossing contains
`K` frames, the system shall keep one frame every `floor(K / N)` frames.
When `floor(K / N)` is less than 1, the system shall keep every frame.

`AC-SAMPLE-02`: When a rollout has no belt speed, the system shall keep
every frame of that rollout.

`AC-SAMPLE-03`: When two samples are drawn for the same dataset, the same
`N`, and the same seed, the system shall produce the same indexes. The phase
of a rollout shall be an integer in `0 .. M-1`.

`AC-SAMPLE-04`: When a training configuration is loaded, the system shall
read `training.samples_per_crossing` and shall fail naming the key when it
is absent. The configuration digest shall change when `N` changes.

`AC-SAMPLE-05`: When a checkpoint contains a frame sample, the system shall
train on those indexes. When `samples_per_crossing` differs from the stored
value, the system shall refuse the checkpoint. When the checkpoint has no
sample, the system shall refuse it.

`AC-SAMPLE-06`: The along-travel extent used for `K` shall be derived from
the first detection camera's sensor, lens, and standoff. For the shipped
line that extent is 0.920 m.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-SAMPLE-01` | `test_ac_sample_01_stride_keeps_n_looks_per_crossing` |
| `AC-SAMPLE-02` | `test_ac_sample_02_a_rollout_without_belt_speed_keeps_every_frame` |
| `AC-SAMPLE-03` | `test_ac_sample_03_the_same_seed_draws_the_same_indexes` |
| `AC-SAMPLE-04` | `test_ac_sample_04_the_configuration_names_samples_per_crossing` |
| `AC-SAMPLE-05` | `test_ac_sample_05_a_checkpoint_reloads_its_stored_pick` |
| `AC-SAMPLE-06` | `test_ac_sample_06_the_shipped_gate_covers_0_920_m_along_travel` |

## Constraints

- The YAML key is `training.samples_per_crossing`.
- Belt speed comes from the dataset file record. The capture interval is the
  median gap of `times` in the first rollout that has a belt speed.
- Rollouts stay in archive order so each archive is read once. An epoch may
  shuffle the kept frames of the rollout it has loaded.
- The manifest is `{candidate}.sample.json` beside the checkpoint.

## Design notes

`K = L / (V * dt)`. `L` is the along-travel footprint, not `fovy`. The stored
pick is the list of indexes. Recomputing it on resume would let a later edit
of the sampler change the data under weights that already exist.
