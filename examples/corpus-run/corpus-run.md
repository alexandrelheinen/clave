# Run the corpus, training, and validation

Each stage is its own command. A checkpoint is written only at the end of an
epoch. If the machine stops mid-epoch, that epoch's weights are not on disk.

`examples/corpus-run/train.sh` installs the environment and then trains one
configuration. `--clean` deletes that candidate's checkpoint, run record, and
stored picks before training starts. Without `--clean`, a finished epoch is
resumed. `--lite` trains two epochs with one look per crossing and writes
under `runs/debug/corpus-lite/checkpoints`, so a pipeline check does not
touch the full run.

Work from the repository root. The script changes to the root itself:

```bash
cd /home/alexandre/Workspace/clave
```

The example files for this guide live in this folder:
`examples/corpus-run/classification.yml` and `detection.yml`.

This campaign's corpus is already on disk and in the bucket. Do not record it
again unless you want a new campaign.

| Half | Digest |
|---|---|
| train | `074b351dc5d3f4eb5d222bae66dc7abe2f0f44f0c4003284cde43d6d2893138e` |
| validation | `35b66b84e9e04839947219022eb5010e772e2576553d0fd2b527fbd889762f47` |
| campaign | `f5afd3e95a153eff018598a5aaf3be5b519c7449627944e7130cee7f497e5f5b` |

After ResNet, one model is left to train: Faster R-CNN. Validating the two is
not training.

## 1. Confirm the corpus is in place

```bash
test -f datasets/corpus/train/dataset.json && test -f datasets/corpus/validation/dataset.json && echo corpus present
```

There are 72 archives in `datasets/corpus/train` and 18 in
`datasets/corpus/validation`.

```bash
mkdir -p runs/debug/corpus/checkpoints
```

Weights go under `runs/`, which git ignores. The configuration that asks for
them is in the YAML files beside this one.

## 2. Train ResNet-50

Ten epochs. Each frame is resized to 224 pixels on a side before the model
sees it, and the batch holds 1 frame. `samples_per_crossing` keeps three
looks each time an object crosses the camera, which is about 13 minutes an
epoch instead of an hour on every frame. `accumulation_steps` sums eight of
those frames, from different rollouts, before one optimizer step.
`class_balance` gives a rare class a larger positive weight. At the end of
each epoch the run scores a thinned pick of the validation half, keeps the
best epoch in `resnet50-baseline.best.pt`, and stops after three epochs
without a better score. The proof-of-concept budget in
`configs/training/memory.yml` stops the run if the process resident set goes
over 1.25 GiB. A ResNet-50 step on this machine retains about 1.06 GiB, and
the full-resolution frames are released after each batch. One progress bar
per epoch counts that epoch's frames when the terminal is interactive. The
bar shows the running mean loss, the resident set, the rate, the time left,
and the clock time the whole run should finish, and it stays on one line. A
captured log has no bar. Those same facts are written as a count line every
15 seconds instead.

The line `epoch 1/10` is only the start of the epoch. The line
`epoch 1 loss ...` is written when the epoch finishes, and that is when
`runs/debug/corpus/checkpoints/resnet50-baseline.pt` exists.

```bash
examples/corpus-run/train.sh
examples/corpus-run/train.sh --clean
```

The script sources `.venv`, installs `.[dev,world]`, builds the release
safety layer, fetches the object meshes, and then runs:

```bash
MUJOCO_GL=osmesa clave --log-level INFO train --config examples/corpus-run/classification.yml --sync
```

`--sync` uploads the `.pt` and the `.run.json` to the bucket and records the
run in `training_runs`. The `models` row is not written yet. That row is the
validation result.

If the machine stops mid-epoch, that epoch's `.pt` does not exist. Run
`examples/corpus-run/train.sh` again, without `--clean`. If the epoch had
already finished, that continues at the next epoch. `--clean` starts at
epoch 1.

A first pass that has to finish in about an hour uses the lite file. It
keeps the same step, the same class weights, and the same validation score,
with one look per crossing and two epochs. Patience does not end it early.
Stop the full run first. The machine fits one training process.

```bash
examples/corpus-run/train.sh --lite --clean
```

## 3. Train Faster R-CNN

Only after the previous command has exited with code 0. Five epochs, with
the same 224 pixel side and a batch of 1. The bar, or the count line when
the terminal is not interactive, shows frames, the running mean loss, the
resident set, and the time remaining. The
checkpoint is
`runs/debug/corpus/checkpoints/faster-rcnn-mobilenetv3.pt`.

```bash
examples/corpus-run/train.sh --config examples/corpus-run/detection.yml
examples/corpus-run/train.sh --config examples/corpus-run/detection.yml --clean
```

## 4. Validate and publish each model

Each command reads the validation half. The bar, or the count line when the
terminal is not interactive, shows frames done, the running agreement, the
time remaining, and the clock time it should finish.
The detector line also shows mean IoU. When the command
finishes it prints the score and writes the `models` row: name, architecture
(`candidate`), path of the `.pt`, train and validation digests, date, epochs,
loss, and the metrics.

ResNet:

```bash
MUJOCO_GL=osmesa .venv/bin/clave --log-level INFO validate \
  --dataset datasets/corpus/validation \
  --candidate resnet50-baseline \
  --checkpoint runs/debug/corpus/checkpoints/resnet50-baseline.pt \
  --name resnet50-baseline \
  --sync
```

Faster R-CNN:

```bash
MUJOCO_GL=osmesa .venv/bin/clave --log-level INFO validate \
  --dataset datasets/corpus/validation \
  --candidate faster-rcnn-mobilenetv3 \
  --checkpoint runs/debug/corpus/checkpoints/faster-rcnn-mobilenetv3.pt \
  --name faster-rcnn-mobilenetv3 \
  --sync
```

`--name` is the label. Without it, the name is the architecture. For another
label, change only that argument.

## If you want to record another corpus

This replaces `datasets/corpus`. The current campaign is already published.
Do not run this to repeat it.

```bash
rm -rf datasets/corpus
MUJOCO_GL=osmesa .venv/bin/clave --log-level INFO corpus --config configs/data/corpus.yml
```

That is 90 rollouts, about a minute each. At the end the command prints both
digests and the campaign id, and publishes them to the bucket.
