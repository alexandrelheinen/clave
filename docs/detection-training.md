# Training perception models to full precision

The sorting pipeline operates end to end, the safety layer enforces physical
envelopes, and perception accuracy governs sorting yield. This guide covers
sensor limits, the losses, and the commands. The sequence a host follows,
from initialization through the batch to the checkpoint that is kept, is
[training-pipeline.md](training-pipeline.md).

## Sensor limits and expected confusions

Before tuning training parameters, observe which error modes a nadir color
camera can resolve and which require complementary sensors. Three specific
confusions are documented in [waste-taxonomy.md](waste-taxonomy.md):

1. **PET vs. PP vs. PS** (classes M-01, M-03, and portions of M-04) when
   unlabeled and transparent. A recovery facility separates these through
   near-infrared spectroscopy based on polymer absorption; an RGB sensor lacks
   that spectral signal.
2. **Aluminum vs. ferrous metal** (classes M-05 and M-06). A sorting facility
   uses an eddy current separator for aluminum and an overhead magnet for
   ferrous cans. Can geometry offers a partial signal for intact packages, but
   crushed or deformed items present identical visual features.
3. **Corrugated cardboard vs. paperboard** (classes M-08 and M-09). The fluted
   inner layer distinguishes corrugated board when viewed edge-on, but remains
   concealed when viewed face-on under a nadir camera.

The project's [validation gates](../configs/validation/gates.yml) account for
these physical bounds: `max_named_confusion_rate: 0.35` sets a dedicated
threshold for these three groups, recognizing the boundary of what color
imagery alone can decide.

## Dataset generation and domain randomization

Training data in CLAVE is generated from physics simulation using MuJoCo,
configured in [sorting_line.yml](../configs/world/sorting_line.yml).

### Recording multi-seed rollouts

Generate training examples across multiple random seeds to expose the models to
broad variations in belt travel, object orientation, and lighting:

```bash
for seed in $(seq 0 49); do
  clave record-dataset \
    --out datasets/synthetic \
    --seed "$seed" \
    --config configs/world/sorting_line.yml
done
```

Each seed draws from bounded intervals defined in configuration:
- Belt speed: 0.25 to 0.35 m/s (`belt.speed_meters_per_second`)
- Lateral placement: -0.17 to +0.17 m (`spawn.lateral_offset_meters`)
- Drop height: 0.01 to 0.03 m (`spawn.drop_height_meters`)
- Longitudinal spacing: 1.00 to 1.40 m (`spawn.spacing_meters`)
- Diffuse illumination: 0.45 to 0.80 (`lighting.diffuse`)

### Verifying and storing datasets

Push the dataset to Cloudflare R2 object storage:

```bash
clave dataset push datasets/synthetic
```

The CLI records a composite SHA-256 digest over all rollout archives and indexes
metadata in the Cloudflare D1 ledger. Checkpoint files and run records tie
deterministically to this dataset digest.

## Detector training: Faster R-CNN MobileNetV3

The detector candidate `faster-rcnn-mobilenetv3` uses a MobileNetV3-Large FPN
backbone with a box prediction head sized for 12 classes (11 material classes
plus background).

Configuration lives in `configs/training/detection_full.yml`:

```yaml
training:
  candidate: faster-rcnn-mobilenetv3
  dataset: datasets/synthetic
  checkpoints: runs
  epochs: 5
  batch_size: 1
  learning_rate: 0.0001
  seed: 0
  window_exit_meters: 1.034
  act_chunk_size: 10
```

Run training with remote synchronization:

```bash
clave train \
  --config configs/training/detection_full.yml \
  --candidate faster-rcnn-mobilenetv3 \
  --sync
```

Batches filter out objects situated outside the camera field of view via
`visible_labels`, preventing the detector from regressing boxes on unobserved
coordinates. The composite loss sums classification cross-entropy, smooth L1
box regression, and region proposal network losses.

## Classifier training: ResNet-50 baseline

The classification candidate `resnet50-baseline` predicts multi-label presence
across all 11 taxonomy classes for frames containing multiple items.

Configuration lives in `configs/training/classification_full.yml`:

```yaml
training:
  candidate: resnet50-baseline
  dataset: datasets/synthetic
  checkpoints: runs
  epochs: 10
  batch_size: 1
  learning_rate: 0.0001
  seed: 0
  window_exit_meters: 1.034
  act_chunk_size: 10
```

Execute the training run:

```bash
clave train \
  --config configs/training/classification_full.yml \
  --candidate resnet50-baseline \
  --sync
```

The objective uses binary cross-entropy with logits across all taxonomy classes.
Learning rates follow a cosine annealing schedule down to one percent of the
initial step size.

## Training-time data augmentation

To prevent models from memorizing specific pixel backgrounds or fixed object
orientations, the data loader in `src/clave/training/adapters.py` applies
augmentations to training batches:

1. **Horizontal and vertical flips**: Top-down belt views are invariant to
   reflections across either image axis. Bounding boxes update coordinate
   limits accordingly.
2. **Photometric brightness scaling**: Scaled illumination factors simulate
   lamp output variations without breaking label semantics.

## Validation gates and benchmark verification

Models are scored against unambiguous thresholds defined in
`configs/validation/gates.yml`:

| Metric | Required gate | Description |
|---|---|---|
| Overall accuracy | >= 80% | Share of all records classified correctly |
| Per-class accuracy | >= 60% | Share of records correctly classified per class |
| Named confusion rate | <= 35% | Upper bound on confusions within color-blind groups |
| Decision latency p99 | <= 450 ms | 99th percentile inference time on target host |
| Unseen accuracy drop | <= 10% | Maximum degradation when evaluating unseen instances |

Run the benchmark harness across test rollouts:

```bash
clave benchmark --config configs/benchmark/default.yml --sync
```

The harness scores every gate, publishes the report to R2, and registers the
verdict in the experiment ledger.

