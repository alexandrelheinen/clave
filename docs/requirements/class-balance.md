# Class balance

Status: draft

## Intent

M-02 is about half of the labels on the training half. An unweighted
classifier can look healthy while a rare class is ignored. The positive
class of a rare label gets a larger weight, computed from the stored
training pick and reloaded with the checkpoint.

## Scope

**In scope:**

- Required `training.class_balance`, either `none` or `inverse`.
- `inverse` on `resnet50-baseline`: `pos_weight` for binary cross-entropy
  with logits, from the frames in the stored training pick.
- A class with no positive frame keeps weight 1.
- The weight vector is written into the checkpoint and the run record. A
  resume uses the stored vector.

**Out of scope:**

- Reweighting the detector. Its loss is the sum torchvision returns.
- Reweighting a policy loss.
- Drawing rare classes more often. The stored pick stays the pick.
- Inventing labels for classes the corpus does not contain.

## Acceptance criteria

`AC-BALANCE-01`: When a training configuration is loaded, the system shall
read `training.class_balance` and shall fail naming the key when it is
absent. `inverse` on a candidate other than `resnet50-baseline` shall fail.
`none` and `inverse` shall produce different configuration digests.

`AC-BALANCE-02`: When `inverse` is set, the positive weight of a class shall
be `(frames - positives) / positives` for the frames in the stored pick. A
class with zero positives shall have weight 1.

`AC-BALANCE-03`: When a checkpoint is resumed under `inverse` and it stores
a weight vector, the system shall use that vector. When the checkpoint has
no vector, the system shall refuse it.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-BALANCE-01` | `test_ac_balance_01_inverse_is_only_for_the_classifier` |
| `AC-BALANCE-02` | `test_ac_balance_02_a_rare_class_outweighs_a_common_one` |
| `AC-BALANCE-03` | `test_ac_balance_03_a_resume_reloads_the_stored_weights` |

## Constraints

- Corpus classification and `configs/training/classification_full.yml` set
  `inverse`. Every other training file sets `none`.
- Positives are frames in which the class is visible, not object counts.
- The vector length is the taxonomy length. A stored vector of another
  length is refused.

## Design notes

The weight is a property of the pick, not of an epoch. Counting again after
a resume would change the loss under the same weights. The first run counts
once, while it still has to read each training archive for the first epoch,
and stores the result before that epoch's steps.
