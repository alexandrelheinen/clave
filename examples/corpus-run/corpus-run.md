# Run the corpus, training, and validation

One command at a time, in your own terminal. Do not chain them with `&&` or a
script. A checkpoint is written only at the end of an epoch. If the machine
stops mid-epoch, that epoch's weights are not on disk.

Work from the repository root, with the environment already installed:

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
sees it, and the batch holds 1 frame. The proof-of-concept budget in
`configs/training/memory.yml` stops the run if the process resident set goes
over 1.25 GiB. A ResNet-50 step on this machine retains about 1.06 GiB, and
the full-resolution frames are released after each batch. A progress bar
counts frames in the current epoch and shows the running mean loss and the
resident set. The log line
`epoch 1 loss ...` is written when the epoch finishes, and that is when
`runs/debug/corpus/checkpoints/resnet50-baseline.pt` exists.

```bash
MUJOCO_GL=osmesa .venv/bin/clave --log-level INFO train --config examples/corpus-run/classification.yml --sync
```

`--sync` uploads the `.pt` and the `.run.json` to the bucket and records the
run in `training_runs`. The `models` row is not written yet. That row is the
validation result.

If the machine stops mid-epoch, that epoch's `.pt` does not exist. Run the
same command again. If the epoch had already finished, the same command
continues at the next epoch.

## 3. Train Faster R-CNN

Only after the previous command has exited with code 0. Five epochs, with
the same 224 pixel side and a batch of 1. The bar again shows frames, the
running mean loss, and the resident set. The checkpoint is
`runs/debug/corpus/checkpoints/faster-rcnn-mobilenetv3.pt`.

```bash
MUJOCO_GL=osmesa .venv/bin/clave --log-level INFO train --config examples/corpus-run/detection.yml --sync
```

## 4. Validate and publish each model

Each command reads the validation half. A progress bar counts frames and shows
the running agreement. The detector bar also shows mean IoU. When the command
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
