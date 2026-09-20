# Data versioning, model storage, and experiment reproducibility

This document specifies the storage layout, versioning semantics, and reproduction
workflows for CLAVE's datasets, model checkpoints, and benchmark evidence,
backed by Cloudflare R2 and Cloudflare D1.

## 1. Storage architecture & layout

CLAVE pairs content-addressed object storage (Cloudflare R2) with a serverless
relational index (Cloudflare D1).

### Cloudflare R2 (Object storage)

Objects in R2 are immutable and addressed by SHA-256 cryptographic digests.
Files are uploaded once and never overwritten:

```
s3://clave-data/
  datasets/
    <dataset_digest>/
      dataset.json               # Split composition, seeds, frame counts, composite digest
      rollout_000.npz            # Compressed tensors (frames, timestamps, joints, labels)
      rollout_001.npz
      ...
  checkpoints/
    <candidate>/
      <config_digest>_<dataset_digest>/
        <candidate>.pt           # PyTorch model weights and optimizer state
        <candidate>.run.json     # Machine metadata, epoch losses, seed, and timestamps
  benchmarks/
    <world_digest>/
      <timestamp>_benchmark.json # Scored configurations, latency percentiles, gate verdicts
```

### Cloudflare D1 (Experiment ledger)

Cloudflare D1 provides a queryable SQLite ledger over all stored runs:
- `datasets`: Records dataset composite digests, frame counts, seeds, and train/val/test splits.
- `training_runs`: Records candidate convergence, epochs, final loss, host specs, and R2 keys.
- `benchmarks`: Records configuration accuracies, misroute rates, p99 decision latencies, and gate pass/fail verdicts.

## 2. Versioning logic

Every trained model checkpoint is uniquely identified by a **cryptographic triplet**:

$$\text{Artifact Identity} = (\text{candidate}, \text{config\_digest}, \text{dataset\_digest})$$

1. **`candidate`**: The architecture identity (e.g. `act`, `resnet50`).
2. **`config_digest`**: SHA-256 digest over the hyperparameter configuration file (`configs/training/*.yml`).
3. **`dataset_digest`**: Composite SHA-256 digest over the ordered binary rollout archives (`rollout_*.npz`).

Because any change to model hyperparameters alters `config_digest`, and any change to the training examples alters `dataset_digest`, checkpoint weights are deterministic and collision-free.

## 3. Reproduction workflows

### Prerequisites: Authentication

Ensure `.env` exists at the repository root with credentials (permanently gitignored):

```ini
CLOUDFLARE_ACCOUNT_ID="<account_id>"
CLOUDFLARE_API_TOKEN="<cloudflare_api_token>"
R2_BUCKET_NAME="clave-data"
R2_ACCESS_KEY_ID="<access_key_id>"
R2_SECRET_ACCESS_KEY="<secret_access_key>"
R2_ENDPOINT_URL="https://<account_id>.r2.cloudflarestorage.com"
D1_DATABASE_NAME="clave-db"
D1_DATABASE_ID="<database_id>"
```

### Initializing the experiment ledger

Run once to create the D1 database tables:

```bash
clave storage init-db
```

### Storing and distributing datasets

1. **Synthesize and describe rollouts locally**:
   ```bash
   clave record-dataset --out datasets/synthetic --seed 42
   ```

2. **Push to R2 and register in D1**:
   ```bash
   clave dataset push datasets/synthetic
   ```
   *Behavior*: Checks R2 before uploading. Resuming an interrupted push only uploads missing rollouts.

3. **Pull onto a fresh clone or CI runner**:
   ```bash
   clave dataset pull <dataset_digest> --out datasets/
   ```
   *Behavior*: Downloads all rollouts and verifies the composite SHA-256 digest locally. Any corrupted bytes cause immediate cleanup and raise `DatasetError`.

### Training models and automated cloud backup

Train a model with cloud backup enabled:

```bash
clave train --config configs/training/default.yml --candidate act --sync
```

When `--sync` is passed:
1. Local training proceeds normally and saves `checkpoints/<candidate>.pt` and `.run.json`.
2. On completion, the checkpoint and run record are uploaded to R2 under:
   `checkpoints/<candidate>/<config_digest>_<dataset_digest>/`
3. A record is inserted into D1 `training_runs` with the loss, epoch count, and R2 key.

### Restoring pre-trained checkpoints

To reproduce or benchmark an existing model without retraining:

- **Restore the latest checkpoint for an architecture**:
  ```bash
  clave checkpoint pull act --latest
  ```
- **Restore a specific version by digest**:
  ```bash
  clave checkpoint pull act --config-digest <cfg_digest> --dataset-digest <data_digest>
  ```

### Evaluating benchmarks and gate evidence

Run benchmark validation with cloud synchronization:

```bash
clave benchmark --config configs/benchmark/default.yml --sync
```

This publishes the evidence pack to `s3://clave-data/benchmarks/<world_digest>/` and indexes the measured metrics in the D1 `benchmarks` table.

### Inspecting experiment history

View the centralized history of training runs and benchmark evaluations:

```bash
clave runs list --limit 20
```

### Offline resilience

All core operations remain functional when disconnected:
- Training and simulation proceed purely locally without remote calls.
- If `--sync` is enabled while offline or when Cloudflare returns an error, the system prints a warning to `stderr`, preserves all local files, and exits cleanly.
