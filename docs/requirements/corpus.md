# Perception corpus

Status: draft

## Intent

Give every perception model one training corpus and one validation corpus,
recorded from the same factor grid and disjoint seeds, with the simulator's
ground truth on every frame. `clave corpus` records both, publishes the bytes
and the file index, and `clave train` / `clave validate` name each half by
its digest.

## Scope

**In scope:**

- A factor grid of belt speed and release spacing, configured, not hardcoded.
- Both detection cameras, spawn serial as identity, pose, velocity, boxes and
  an instance map.
- A campaign id pairing the two digests, and a D1 row per archive.
- `clave train` accepting a digest and refusing the validation half.
- `clave validate` scoring a perception checkpoint against the validation half.
- A short preview video of a dense stream. The arm stays parked.

**Out of scope:**

- Four cells in series, and any change to the live line's feed setpoint.
- Policy learning, reinforcement, and arm speed.
- Code cameras.
- A new object catalog.

## Acceptance criteria

`AC-CORPUS-01`: When a corpus configuration is loaded, the system shall expand
belt speed and spacing into one cell per pair, and shall assign train and
validation disjoint seeds that both visit every cell.

`AC-CORPUS-02`: When a corpus rollout is written, the system shall store every
detection camera, the spawn serial, the pose, the velocities, the pixel box
and an instance map, and shall record the belt speed and spacing of that
rollout on the archive.

`AC-CORPUS-03`: When `clave corpus` finishes, the system shall have written two
datasets whose digests differ, sharing one campaign id, and shall have pushed
both to object storage and recorded the campaign, the datasets and the files.

`AC-CORPUS-04`: When `clave train` is given a validation digest, the system
shall refuse it. When it is given a training digest recorded against a
different world configuration than the tree, the system shall refuse it.

`AC-CORPUS-05`: When a dataset is pushed, the system shall record one D1 row
per archive, naming its digest, size, frame count, seed, belt speed, spacing
and cameras.

`AC-CORPUS-06`: When `clave validate` scores a perception checkpoint, the
system shall compare it to the validation labels and shall not pass object
identity into the model. A policy candidate shall be refused.

`AC-CORPUS-07`: The arm shall stay parked while a corpus is recorded.

`AC-CORPUS-08`: When `clave validate --sync` finishes, the system shall upload
the score and insert it into `corpus_evaluations`.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-CORPUS-01` | `test_train_and_validation_cover_the_grid_with_disjoint_seeds` |
| `AC-CORPUS-02` | `test_a_corpus_archive_round_trips_cameras_and_pose` |
| `AC-CORPUS-04` | `test_train_refuses_a_validation_corpus`, `test_a_corpus_from_another_world_is_refused` |
| `AC-CORPUS-06` | `test_box_overlap_matches_a_perfect_prediction`, `test_a_policy_candidate_is_refused` |

`AC-CORPUS-03`, `AC-CORPUS-05` and `AC-CORPUS-08` are the remote publication.
The local file records they depend on are covered by the archive round trip.
A live D1 call is not part of the gate.

## Constraints

- Numeric levels live in `configs/data/corpus.yml` and
  `configs/validation/corpus.yml`.
- The feed controller stays out of this recording, so a requested belt speed
  is the speed that is stored.
- Format 1 datasets written by `record-dataset` keep loading.

## Design notes

R2 layout is unchanged: `datasets/<digest>/`. D1 gains `campaigns`,
`dataset_files` and `corpus_evaluations`, and `datasets.role` plus
`datasets.campaign_id`. Training reads the first detection camera through the
existing split loader. `load_split(..., camera=)` selects another stored
camera without a new archive format.
