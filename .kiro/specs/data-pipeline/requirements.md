# Requirements Document

## Project Description (Input)
v0.5.0 built a world where objects ride a belt carrying their material class,
and v0.8.0 built a harness that scores outcomes. Between them there is nothing:
no way to turn a running simulation into a dataset, no splits, and no record of
what any dataset contains.

v0.7.0 trains every shortlisted candidate and cannot start without one. The
comparison v0.8.0 exists to make is worthless if two candidates cannot be shown
to have trained on the same data, and a split that leaks between train and test
turns every number after it into an overstatement nobody can detect by reading
the code.

This feature turns the world into data. It records rollouts as frames paired
with the labels the world already knows, splits them so that nothing leaks,
reports what the result actually contains rather than what it was meant to, and
versions the whole thing through the manifest machinery v0.3.0 built.

It also has to be honest about a gap. The corpora shortlisted at v0.1.2 have not
been fetched, so the path that ingests real imagery is built and exercised
against a fixture rather than against ZeroWaste. Proving it needs a download
this step does not perform.

## Introduction

A dataset is a claim about what a model saw. This feature makes that claim
checkable.

Three properties decide whether the later steps can trust it. Splits are
deterministic given a seed and provably free of leakage, because the cheapest
way to inflate an accuracy number is to test on something seen in training.
Composition is reported rather than assumed, because a class present in the
taxonomy and absent from the data produces a confusion matrix column of zeros
that reads as a model failure. And every dataset resolves by digest, so two
training runs can be shown to have seen the same bytes.

Labels come from the simulator rather than from a labeling pass. The world
already knows each object's material class, so a synthetic frame is labeled by
construction and the usual source of label noise does not arise. The cost is
that these labels describe primitives rather than photographs, which the
delivered document has to state plainly.

## Boundary Context

- **In scope**: recording rollouts from the world as labeled examples, a
  scripted expert that produces demonstrations, deterministic leakage-free
  splits, composition reporting, dataset versioning by digest, and the ingestion
  path for a real corpus together with the taxonomy mapping it applies.
- **Out of scope**: training anything, which is v0.7.0. Metrics and gates, which
  v0.8.0 owns. Fetching a corpus, which is an operator action rather than part
  of a gate. Any accuracy claim. Changes to the world's physics or to the
  taxonomy.
- **Adjacent expectations**: the world supplies labeled objects and is not
  modified. The taxonomy supplies the classes and the corpus mappings. The
  platform supplies seeding, the manifest and digests, and no second mechanism
  is introduced for any of them.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `RECORD`, `EXPERT`, `SPLIT`, `COMPOSE`, `VERSION`, and `INGEST`. Ids are
append-only. These areas are new: none collides with an existing spec.

## Requirements

### Requirement 1: Recording rollouts

**Objective:** As the engineer training at v0.7.0, I want the simulator turned
into labeled examples, so that training has something to read.

#### Acceptance Criteria

1. When a rollout runs, the Pipeline shall record one example per captured frame
   carrying the frame and the objects visible in it. `AC-RECORD-01`
2. The Pipeline shall record each object's material class, its identity, and its
   position, taking all three from the world rather than inferring any of them.
   `AC-RECORD-02`
3. The Pipeline shall record the seed, the world configuration digest, and the
   simulated time of every example. `AC-RECORD-03`
4. When two rollouts run with one seed and one configuration, the Pipeline shall
   record identical examples. `AC-RECORD-04`
5. The Pipeline shall record whether each object was inside the reachable window
   at capture time, since an object outside it cannot be picked.
   `AC-RECORD-05`

### Requirement 2: The scripted expert

**Objective:** As the engineer training by imitation, I want demonstrations from a
scripted policy, so that imitation learning has a teacher.

#### Acceptance Criteria

1. The Pipeline shall provide a scripted policy that selects an object and emits
   a pick decision for it. `AC-EXPERT-01`
2. The Pipeline shall emit a decision only for an object inside the reachable
   window. `AC-EXPERT-02`
3. The Pipeline shall resolve the decision's channel from the object's material
   class using the taxonomy mapping. `AC-EXPERT-03`
4. When the expert runs twice on one seed, the Pipeline shall produce the same
   decisions. `AC-EXPERT-04`
5. If no object is reachable, then the Pipeline shall emit no decision rather
   than a decision naming nothing. `AC-EXPERT-05`

### Requirement 3: Splits

**Objective:** As a reviewer of any accuracy number this project reports, I want
splits proven free of leakage, so that the number means what it says.

#### Acceptance Criteria

1. The Pipeline shall divide a dataset into train, validation and test parts at
   configured proportions. `AC-SPLIT-01`
2. The Pipeline shall split by rollout rather than by frame, so that two frames
   of one object cannot land on both sides of the boundary. `AC-SPLIT-02`
3. When a split runs twice with one seed, the Pipeline shall produce identical
   partitions. `AC-SPLIT-03`
4. The Pipeline shall verify that no example appears in more than one part, and
   fail rather than report a leaking split. `AC-SPLIT-04`
5. If a requested proportion set does not sum to one, then the Pipeline shall
   fail naming the proportions. `AC-SPLIT-05`

### Requirement 4: Composition

**Objective:** As whoever reads a confusion matrix at v0.8.0, I want to know what
the data contained, so that an absent class is distinguishable from a failed one.

#### Acceptance Criteria

1. The Pipeline shall report the example count and the per-class instance count
   of every dataset it produces. `AC-COMPOSE-01`
2. The Pipeline shall report which taxonomy classes have no instances.
   `AC-COMPOSE-02`
3. The Pipeline shall report composition per split part, not only in aggregate,
   since a class present overall may still be absent from the test part.
   `AC-COMPOSE-03`
4. The Pipeline shall report composition as measured counts rather than as the
   proportions the configuration requested. `AC-COMPOSE-04`

### Requirement 5: Versioning

**Objective:** As anyone comparing two training runs, I want each dataset to
resolve by digest, so that "same data" is checkable rather than assumed.

#### Acceptance Criteria

1. When a dataset is written, the Pipeline shall record a digest over its
   contents. `AC-VERSION-01`
2. The Pipeline shall record the digest, the seed, the configuration and the
   composition together as one description of the dataset. `AC-VERSION-02`
3. When a dataset is read, the Pipeline shall verify its digest and refuse a
   mismatch. `AC-VERSION-03`
4. The Pipeline shall not require any dataset to be committed to the repository.
   `AC-VERSION-04`

### Requirement 6: Ingesting a real corpus

**Objective:** As the engineer who will eventually train on photographs, I want
the ingestion path to exist and apply the taxonomy mapping, so that fetching a
corpus is the only remaining step.

#### Acceptance Criteria

1. The Pipeline shall map a corpus label onto taxonomy classes using the mapping
   recorded in the taxonomy document. `AC-INGEST-01`
2. When a corpus label spans several taxonomy classes, the Pipeline shall record
   the ambiguity rather than selecting one class. `AC-INGEST-02`
3. If a corpus label has no taxonomy mapping, then the Pipeline shall record it
   as unmapped rather than discarding the example. `AC-INGEST-03`
4. The Pipeline shall keep ingested real examples separable from synthetic ones,
   so a held-out real set can be excluded from training. `AC-INGEST-04`
5. The Pipeline shall state that no corpus has been fetched and that the
   ingestion path is exercised against a fixture. `AC-INGEST-05`
