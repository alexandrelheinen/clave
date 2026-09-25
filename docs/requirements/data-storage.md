# Remote dataset storage and experiment metadata

## Intent

Provide remote persistence, content-addressed distribution, and centralized
experiment tracking for CLAVE's datasets, trained checkpoints, and validation
evidence using Cloudflare R2 (S3-compatible object storage) and Cloudflare D1
(serverless SQLite).

Currently, all synthetic rollouts, external corpora, and model checkpoints live
strictly as gitignored local files. A developer or CI runner starting from a
fresh clone must synthesize rollouts from scratch, and experiment history is
lost across clean checkouts. This specification establishes a reproducible
storage and versioning layer that integrates with CLAVE's digest-first
guarantees without adding cloud dependencies to the offline simulation loop.

## Scope

**In.**
- Pushing and pulling synthetic rollouts and dataset descriptions to and from
  Cloudflare R2, addressed by SHA-256 digest.
- Pushing and pulling trained policy and perception checkpoints (`.pt`) and run
  records (`.run.json`) to and from R2.
- Synchronizing external raw corpora archives matching `corpora/manifest.toml`.
- Publishing experiment run summaries and validation gate outcomes to Cloudflare
  D1 via its HTTP API.
- Querying historical runs and benchmarks from the CLI (`clave runs list`).
- Reading configuration from `.env` or the process environment.

**Out.**
- Streaming live camera frames, telemetry, or proposals during SITL simulation.
  The SITL loop remains purely local and zero-network to preserve latency budgets.
- Requiring an internet connection for training, simulation, or validation.
  Local offline operations remain fully functional when cloud services are
  unreachable.
- Bypassing local SHA-256 verification. Bytes fetched from R2 must still verify
  locally before any component is permitted to train or evaluate on them.

## Content addressing and layout

Data in R2 is immutable and keyed by cryptographic digest, mirroring the
local verification model in `clave.data.dataset` and `clave.corpus.manifest`:

```
s3://<R2_BUCKET_NAME>/
  datasets/
    <dataset_digest>/
      dataset.json
      rollout_000.npz
      ...
  corpora/
    <artifact_name>/
      <sha256>
  checkpoints/
    <candidate>/
      <config_digest>_<dataset_digest>/
        <candidate>.pt
        <candidate>.run.json
  benchmarks/
    <world_digest>/
      <timestamp>_benchmark.json
```

Because every archive path contains its expected SHA-256 digest, objects in
R2 are never overwritten. A push checks for existence before uploading, so
resuming an interrupted push transfers only the missing rollouts.

## Database schema (Cloudflare D1)

Cloudflare D1 serves as the queryable index over immutable R2 objects,
tracking datasets, training trajectories, and benchmark evidence packs.

### `datasets`
Records every synthesized dataset pushed to the cloud:
- `digest` (TEXT, PRIMARY KEY): The composite SHA-256 digest over rollouts.
- `seed` (INTEGER): The base seed used during generation.
- `config_digest` (TEXT): Digest of the world configuration used.
- `example_count` (INTEGER): Total frames captured.
- `train_examples` (INTEGER): Frames allocated to training.
- `validation_examples` (INTEGER): Frames allocated to validation.
- `test_examples` (INTEGER): Frames allocated to testing.
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP).

### `training_runs`
Records candidate training convergence and links to weights in R2:
- `run_id` (TEXT, PRIMARY KEY): Unique run identifier.
- `candidate` (TEXT): Architecture name from the candidate registry.
- `dataset_digest` (TEXT, REFERENCES datasets(digest)).
- `config_digest` (TEXT): Hyperparameter digest.
- `epochs` (INTEGER): Total epochs completed.
- `final_loss` (REAL): Final training loss achieved.
- `machine` (TEXT): Hardware identifier and CPU thread count.
- `checkpoint_r2_key` (TEXT): Object key of the `.pt` weights in R2.
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP).

### `benchmarks`
Records validation gate evaluations:
- `benchmark_id` (TEXT, PRIMARY KEY).
- `world_digest` (TEXT): Digest of the simulation scene configuration.
- `configuration_name` (TEXT): Candidate pairing (e.g. `resnet50 + act`).
- `overall_accuracy` (REAL): Measured overall classification accuracy.
- `misroute_rate` (REAL): Measured misroute share.
- `decision_latency_p99_seconds` (REAL): Measured p99 decision latency.
- `passed` (INTEGER): 1 if all gates were satisfied, 0 otherwise.
- `pack_r2_key` (TEXT): Object key of the full `benchmark.json` in R2.
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP).

## Constraints

- **Credentials never land in git.** Authentication parameters are loaded from
  the environment or `.env`, which is permanently gitignored.
- **Offline independence.** When network credentials are absent or remote
  services return HTTP errors, the system warns and proceeds with local storage.
  An offline training run must never fail solely because D1 could not be reached.
- **Zero silent corruption.** A downloaded rollout archive whose bytes do not
  match the expected digest recorded in `dataset.json` is deleted immediately
  and raises a `DatasetError`.
- **Egress cost discipline.** All downloads target Cloudflare R2's S3 endpoint
  where egress is free, preserving zero-cost artifact sharing.

## Acceptance criteria

Ids begin at `AC-DATA-01`. They are append-only and never reused.

`AC-DATA-01`: The system shall read Cloudflare R2 and D1 credentials from the
process environment or a local `.env` file, and shall fail with a clear error
naming the missing keys when a remote operation is requested without credentials.

`AC-DATA-02`: When `clave dataset push` is executed for a local dataset, the
system shall verify the local digest and upload all rollout archives and
`dataset.json` to R2 under `datasets/<digest>/`, skipping files that already
exist remotely.

`AC-DATA-03`: When `clave dataset pull <digest>` is executed, the system shall
download the requested dataset from R2, verify the composite SHA-256 digest
locally, and raise `DatasetError` if the observed digest does not match.

`AC-DATA-04`: When a dataset is pushed, the system shall record its metadata,
example count, and split composition into the Cloudflare D1 `datasets` table.

`AC-DATA-05`: When `clave train` completes with remote sync enabled, the
system shall upload the resulting `.pt` checkpoint and `.run.json` to R2,
and insert a record into the D1 `training_runs` table.

`AC-DATA-06`: When `clave benchmark` completes with remote sync enabled, the
system shall upload the evidence pack to R2 and insert the configuration results,
accuracies, latencies, and gate verdicts into the D1 `benchmarks` table.

`AC-DATA-07`: When `clave runs list` is executed, the system shall query D1 and
render a formatted table of historical training runs and benchmark scores.

`AC-DATA-08`: When network connectivity is lost during training or simulation,
the system shall log a warning, retain all records and checkpoints locally, and
exit with zero if the local operation succeeded.

A perception corpus adds `campaigns`, `dataset_files` and `corpus_evaluations`,
and two columns on `datasets`. That index is specified in
[corpus.md](corpus.md), which is the command that fills it. This document's
push and pull still address bytes by digest.
