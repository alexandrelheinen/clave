# Checkpoint selection

Status: draft

## Intent

The last epoch is not the one the held-out frames prefer. Training keeps
that epoch, stops after a configured run of epochs with no improvement, and
leaves the published score on every validation frame.

## Scope

**In scope:**

- Optional `training.validation_dataset`. When it is absent, training does
  not score a held-out set and does not stop early.
- Required `training.patience` when `validation_dataset` is present. After
  that many epochs with no improvement, the run stops.
- A validation pick drawn with the same `samples_per_crossing` and seed as
  the training pick, stored as `{candidate}.validation-sample.json`.
- A score of the live model on those indexes. The classifier metric is
  agreement. The detector metric is mean intersection over union.
- `{candidate}.pt` remains the last epoch, including optimizer state.
  `{candidate}.best.pt` is the epoch with the best held-out score.
- The best score, the best epoch, and the count of epochs without
  improvement travel in the checkpoint and the run record, so a resume does
  not restart patience.

**Out of scope:**

- Scoring every validation frame at the end of each epoch. That pass is
  `clave validate`, once, after training.
- A second copy of the model. The live weights are scored in place.
- A selection metric other than agreement or mean intersection over union.
- Policy candidates. They have no validation corpus in these files.

## Acceptance criteria

`AC-SELECT-01`: When a training configuration has no `validation_dataset`,
the system shall train without a held-out score. When `validation_dataset`
is present and `patience` is absent, the system shall fail naming
`training.patience`. When `patience` is present and `validation_dataset` is
absent, the system shall fail naming `training.validation_dataset`.

`AC-SELECT-02`: When a held-out score is strictly greater than the best
score so far, the system shall replace the best score, reset the count of
epochs without improvement, and keep those weights. When the score is not
greater, the system shall increment that count. When the count reaches
`patience`, the system shall stop.

`AC-SELECT-03`: When the candidate is `resnet50-baseline`, the selection
metric shall be agreement. When the candidate is `faster-rcnn-mobilenetv3`,
the selection metric shall be mean intersection over union.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-SELECT-01` | `test_ac_select_01_patience_belongs_with_a_validation_dataset` |
| `AC-SELECT-02` | `test_ac_select_02_a_worse_score_counts_toward_patience` |
| `AC-SELECT-03` | `test_ac_select_03_the_metric_follows_the_candidate` |

## Constraints

- The validation pick uses the same footprint, capture interval rule, `N`,
  and seed as the training pick. The part is the validation half.
- One validation archive is resident at a time.
- `patience` equal to `epochs` lets the schedule finish.
- Corpus classification starts at `patience: 3`.

## Design notes

Higher is better for both metrics. An equal score is not an improvement.
A resume that already has `patience` stale epochs returns without another
epoch. Raising `patience` in the file lets that resume continue.
