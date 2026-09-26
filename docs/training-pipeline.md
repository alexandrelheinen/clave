# Training and validation pipeline

A perception checkpoint is only as trustworthy as the experiment that produced
it. The experiment CLAVE already runs is a sound proof of concept: the labels
come from the simulator, the validation rollouts are a different digest from
the training rollouts, and a checkpoint is named by the candidate, the
configuration digest, and the dataset digest. A number from that experiment
can be traced. It can also be a weak model. The optimizer step that fits
inside the development machine is the part a training host would refuse to
copy. The step was sized to a resident-memory ceiling. The gradient the
loss wants is a batch of scenes that are not the same object a moment apart.

This page is the sequence that closes that gap. The version ladder in
[roadmap.md](roadmap.md) ships identity, motion, and the line. Checkpoint
selection is the procedure here. Each step below gets a requirements document before
code, the same way the rest of the tree does. Numbers that a designer chooses
live in YAML.

## What the proof of concept already settles

The corpus is one factor grid of belt speed and spacing, recorded by
`clave corpus` from [configs/data/corpus.yml](../configs/data/corpus.yml).
Train and validation visit every cell and do not share a seed.
[requirements/corpus.md](requirements/corpus.md) makes `clave train` refuse
the validation digest, so a high score cannot be bought by training on the
frames that will later be called a test.

Archives stay at the camera resolution. The training step resizes to the side
in [configs/training/memory.yml](../configs/training/memory.yml) and drops the
full frame after the batch. The published bytes do not change when the side
or the batch changes. Object storage holds the blobs under
`datasets/<digest>/`. D1 holds the catalog: campaigns, datasets, files, and
later the training run and the score. Pixels do not go in the database.

The classifier uses binary cross-entropy with logits, because a frame holds
several materials and a single label would be the wrong target. The detector
uses the classification, box, and region-proposal losses of the torchvision
model it loads. The learning rate follows cosine annealing from the configured
value down to one percent of it. Flips and a brightness scale match a nadir
view, where a reflection is still the same object. `seed_everything` seeds
Python, NumPy, and PyTorch from the training file before the loop starts.

Two scores stay separate, and both are specified before a result exists.
`clave validate` compares a checkpoint to the validation labels and does not
hand the model an object id. The cuts in
[configs/validation/corpus.yml](../configs/validation/corpus.yml) decide when
a class counts as present and when a box counts as a match. They are not a
pass line. `clave validate-run` scores line outcomes against
[configs/validation/gates.yml](../configs/validation/gates.yml): accuracy,
named confusions, pick, misroute, latency. [validation-protocol.md](validation-protocol.md)
states that an unmet gate fails the command, and that a class with too few
records is unmeasured. An empty denominator is not a pass.

The arm stays parked while the corpus is recorded, so this campaign has no
expert action in it. Policy training is a later corpus. A parked arm is why
a perception model and a pick policy are not the same training run.

## What the ceiling bends

[requirements/training-memory.md](requirements/training-memory.md) caps the
resident set at 1.25 GiB because the development virtual machine is capped at
7806 MB and a full-resolution batch took the machine down. The proof of
concept accepts four consequences of that cap.

The batch size in the training files is 1. One frame is a legal gradient and
a noisy one. Consecutive frames in a rollout are the same objects a fifth of
a second apart (`capture_interval_seconds` is 0.2), so the next step sees
almost the same scene. The loop walks archives in archive order and reads
each file once. The kept frames of the loaded rollout are shuffled on every
epoch. A shuffle in [src/clave/data/splits.py](../src/clave/data/splits.py)
runs when a split is built, which is a different permutation from the one
inside an epoch.

The builders in [src/clave/candidates/perception.py](../src/clave/candidates/perception.py)
pass `weights=None`. ResNet-50 and the MobileNetV3 backbone therefore start
from a random draw. Ten epochs on this corpus do not grow the filters a
published checkpoint already contains. The parameter count is the same
either way, so loading published weights does not raise the resident set.

Every step collects garbage and asks glibc to return free pages, so the
process stays under the ceiling. That keeps the machine up. It also spends
the time a training host would spend on the next batch. A checkpoint is
written at the end of an epoch and resumed at the next epoch. When
`validation_dataset` is set, that same moment scores the thinned validation
pick, and `{candidate}.best.pt` keeps the epoch with the highest held-out
score. `{candidate}.pt` stays the last epoch, so a resume still has an
optimizer state. The published score is still `clave validate` on every
validation frame.

The input side of 224 is the side this budget uses, and it is the side
ResNet-50 was built for. The 96 pixel fixture in
[src/clave/candidates/fixture.py](../src/clave/candidates/fixture.py) is a
latency smoke test. A gate measured on that fixture does not describe a
checkpoint trained at 224.

The digest, the split, and the score still name the run that produced them.
A loss curve from the development machine shows that the loop finishes. It
is weak evidence about the best model this corpus can support.

## The published half covers four classes

The training half
`074b351dc5d3f4eb5d222bae66dc7abe2f0f44f0c4003284cde43d6d2893138e`
holds 10800 frames and these label occurrences:

| Class | Occurrences |
| --- | ---: |
| M-02 | 20784 |
| M-09 | 12072 |
| M-06 | 6962 |
| M-04 | 3561 |

M-01, M-03, M-05, M-07, M-08, M-10, and M-11 occur zero times. The head is
still sized to eleven classes, which is what the runtime expects. A score on
this half can speak for the four classes that appear. The other seven are
unmeasured, which is the rule
[validation-protocol.md](validation-protocol.md) already states, and the
minimum support there is 30 records. The three named confusions each need
more than one member of the group. This half has M-04 without M-01 and M-03,
M-06 without M-05, and M-09 without M-08, so those gates have no pair to
score.

M-02 is about half of the labels that do exist. An unweighted average over
frames will look healthy while the rare class is ignored.
[requirements/class-balance.md](requirements/class-balance.md) gives a rare
class a larger positive weight on the classifier. A later campaign
that places the missing classes is a new digest. The training code does not
invent those labels, and this page does not ask for the current corpus to be
recorded again in order to shrink it.

`dataset.json` lists `camera_ids` as empty on every archive. The archive
itself stores both names, `gate_wide` and `pick_wide`, and `frames` has shape
`(150, 2, 480, 640, 3)`. Training reads the first camera. The index should
carry the names the array already stores, so a later choice of camera is a
fact in the catalog.

## The sequence

### 1. Say what the corpus supports

Before a run is compared with another, the score prints the class counts and
marks every class under the minimum support as unmeasured. Overall agreement
is reported beside that list, so a four-class corpus cannot read as an
eleven-class result. The decision to record a campaign that contains the
missing classes is a data decision, taken when a full taxonomy score is
required. It produces a new digest. This half stays as published.

### 2. Start from published weights

The candidate spec names the weight set, and the review records its license
before the builder loads it. Torchvision ships ImageNet-1k weights for
ResNet-50 and COCO weights for the MobileNetV3 Faster R-CNN backbone under
the BSD-3-Clause license the candidate entries already cite. The final layer
is replaced so the head matches the taxonomy: eleven outputs for the
classifier, twelve for the detector once background is counted. The trunk
loads. The new head starts at random. `weights=None` remains available as an
ablation, selected in the training file, so a comparison can show what the
published initialization was worth on the same validation digest.

### 3. Build a batch of different scenes

[requirements/gradient-accumulation.md](requirements/gradient-accumulation.md)
is this step. An epoch draws a permutation of frames across rollouts, seeded,
and the training file sets the period. The frames that enter the permutation
are a stored sample of the corpus, a few looks per camera footprint, as
[frame-sampling.md](frame-sampling.md) sets out. The published archives stay
intact. Consecutive frames of one object stop being consecutive steps.

On the development machine the resident budget still holds one image. The
available improvement there is gradient accumulation: a configured number of
shuffled frames each contribute a gradient, and the optimizer steps once.
Accumulation of sixteen neighbors from the same rollout would not be that
improvement. The permutation is what makes the sum a batch.

A host that can raise `resident_limit_bytes` also raises `batch_size` and
drops the per-step page return. Loader processes stay at zero until that
raise, because each worker would keep its own copy of the batch. The device
name and, on CUDA, mixed precision are keys in the training file. Flip
probability and the brightness range move out of the literals in
[src/clave/training/adapters.py](../src/clave/training/adapters.py) into that
same file. The follow-up in
[requirements/training-memory.md](requirements/training-memory.md) is this
step's memory half: the published corpus stays, and the ceiling, the side,
and the batch size move together.

### 4. Keep the checkpoint the validation half prefers

[requirements/checkpoint-selection.md](requirements/checkpoint-selection.md)
is this step. At the end of each epoch the run scores the validation digest
with the same function `clave validate` uses, and writes that score into the
run record. The frames in that pass are the thinned validation pick. The
published score still reads every validation frame, once, after training.
The file that is kept for deployment is the epoch with the best of those
scores, and the last epoch is kept beside it so a resume still has an
optimizer state. Patience is a key in the training file: after that many
epochs without an improvement the run stops. The metric is agreement for the
classifier and mean intersection over union for the detector, restricted to
classes the corpus supports. A second metric invented only for selection
would make the published score and the chosen weights disagree.

### 5. Train the task the line asks for

A multi-label frame tag answers whether a class appears somewhere in the
picture. A pick needs a class on an object, and a box. The corpus already
stores boxes and an instance map. The detector is the model that can feed
the proposal. The classifier stays as the baseline: it is cheaper, it is
the wrong task for a pick, and a baseline that fails on the same digest
says the frames are the limit. A crop or a masked region from the instance
map, classified on its own, is the middle model if the detector is too slow
for the latency budget. It is still one object in, one class out.

Policy training waits for a corpus in which the scripted expert moves. The
perception campaign parks the arm on purpose.

### 6. Publish two reports

The perception report is the validation score: agreement or mean overlap,
per-class figures, unmeasured classes named, and the checkpoint identity.
The line report is the gate file: pick, misroute, the named confusions, and
latency at p99, measured at the input side stored in the checkpoint and on
the machine that will serve it. A strong perception score can sit next to a
failed pick gate, because identity and the grasp are still the open defects
in [roadmap.md](roadmap.md). The two documents are how that stays visible.

Seen-versus-unseen accuracy is the generalization gate already written. The
corpus split blocks a shared rollout. It does not by itself prove that a
mesh in the validation half was absent from training. The report states
which object instances occur in both halves, and the drop is computed on
the instances that occur in only one.

## What this page does not change

The development-machine run stays inside the 1.25 GiB budget until a host
exists. The published corpus is not re-recorded to make that run faster.
Hardware stays out of the v1 line, so none of these scores are a claim about
a factory camera. Reinforcement learning stays out until a reward exists,
which means an arm that can succeed or fail a pick.
