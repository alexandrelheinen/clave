# Requirements Document

## Project Description (Input)
Everything is in place except the thing that learns. v0.4.0 put seven
architectures behind one interface and measured them. v0.6.1 produces datasets
with ground-truth boxes and known visibility. v0.8.0 scores outcomes and waits.
Nothing trains.

The step also has to be honest about two limits it did not choose.

The compute budget resolved at v0.1.2 is a mobile CPU inside 7 GiB with no
accelerator. Estimates there put ResNet-50 at two to four hours and ACT at two
to five days. Those are estimates; this step replaces them with wall-clock
measurements and reports which candidates could not be trained to convergence
rather than presenting a short run as a finished one.

And the world has an arm that nothing actuates. A policy learned from reward
needs an environment it can act in, and `data.ctrl` is never written, so the
only training signal available for the pick policy is demonstrations from the
scripted expert. That is a gap in the simulation rather than in the
architectures, and it decides which candidates this step can train at all.

## Introduction

This feature delivers the application that trains a shortlisted candidate from a
configuration file, records what the run consumed, and survives interruption.

The machinery matters more than any individual number produced here. A dataset
of 240 frames cannot support a claim about accuracy, and this document does not
make one. What it can support is a claim about cost: how long each architecture
takes per epoch on the hardware this project actually has, which is the number
v0.1.2 guessed at and v0.7.0 is the first step able to measure.

Reproducibility carries over unchanged. A run records its seed, its
configuration digest and the dataset digest it read, so two runs can be shown to
have seen the same bytes, and the same seed reproduces the same loss.

## Boundary Context

- **In scope**: the training application and its configuration, run records and
  resumption, training loops for the candidates the available signal supports,
  measured wall-clock cost per candidate, and the report comparing those
  measurements against the v0.1.2 estimates.
- **Out of scope**: accuracy claims, which need a dataset orders of magnitude
  larger. Metrics and gates, which v0.8.0 owns. Arm actuation and the reward
  loop, which belong to v0.9.0 and whose absence this step reports rather than
  fills. Fetching a corpus.
- **Adjacent expectations**: the candidate registry supplies the architectures
  and is not reopened. The data pipeline supplies datasets and their digests.
  The platform supplies seeding and run records, and no second mechanism is
  added for either.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `TRAIN`, `RESUME`, `COST`, `SIGNAL`, and `TRUTH`. Ids are append-only and
none of these areas collides with an existing spec.

## Requirements

### Requirement 1: Training a candidate

**Objective:** As the engineer comparing architectures, I want one command that
trains any candidate from a configuration file, so that comparing two of them
does not mean writing two programs.

#### Acceptance Criteria

1. When a candidate name and a configuration are supplied, the Trainer shall
   train that candidate without requiring code changes. `AC-TRAIN-01`
2. The Trainer shall read every hyperparameter from configuration rather than
   from a default embedded in code. `AC-TRAIN-02`
3. The Trainer shall read its training data from a dataset produced by the data
   pipeline, verifying that dataset's digest before reading it.
   `AC-TRAIN-03`
4. The Trainer shall train only on the training split, never on validation or
   test. `AC-TRAIN-04`
5. When training a detection candidate, the Trainer shall use only labels whose
   objects are visible in the frame. `AC-TRAIN-05`
6. If a candidate's library is not installed, then the Trainer shall report it
   as unavailable rather than failing with an import error. `AC-TRAIN-06`

### Requirement 2: Run records and resumption

**Objective:** As anyone who has had a multi-hour run die at hour three, I want
runs to resume, and to carry what produced them.

#### Acceptance Criteria

1. When a run completes an epoch, the Trainer shall write a checkpoint from
   which training can continue. `AC-RESUME-01`
2. When a run is restarted against an existing checkpoint, the Trainer shall
   continue from the recorded epoch rather than starting over.
   `AC-RESUME-02`
3. The Trainer shall record the seed, the configuration digest, the dataset
   digest and the environment of every run. `AC-RESUME-03`
4. The Trainer shall record per-epoch loss in a form a later tool can read
   without importing project code. `AC-RESUME-04`
5. When two runs use one seed, one configuration and one dataset, the Trainer
   shall produce the same first-epoch loss within a stated tolerance.
   `AC-RESUME-05`

### Requirement 3: Measured cost

**Objective:** As whoever plans the remaining steps, I want measured wall-clock
per architecture, so that the schedule rests on this hardware rather than on an
estimate about it.

#### Acceptance Criteria

1. When an epoch completes, the Trainer shall record its wall-clock duration.
   `AC-COST-01`
2. The Trainer shall record the hardware and the thread count a run executed on.
   `AC-COST-02`
3. The Report shall state measured per-epoch cost beside the v0.1.2 estimate it
   replaces. `AC-COST-03`
4. If a measured cost contradicts a v0.1.2 verdict, then the Report shall say so
   and name the verdict affected. `AC-COST-04`

### Requirement 4: Available training signal

**Objective:** As a reader deciding whether the shortlist survived, I want the
candidates that could not be trained named with the reason, so that an untrained
candidate is distinguishable from a failed one.

#### Acceptance Criteria

1. The Report shall name every shortlisted candidate that was not trained, with
   the reason. `AC-SIGNAL-01`
2. Where a candidate requires a training signal the simulation does not produce,
   the Report shall name the missing signal rather than the architecture.
   `AC-SIGNAL-02`
3. If fewer candidates are trained than the roadmap target for a stage, then the
   Report shall state that the target is unmet and name what would change it.
   `AC-SIGNAL-03`

### Requirement 5: Truthfulness of results

**Objective:** As a reader of any number this step produces, I want it impossible
to mistake a cost measurement for an accuracy claim.

#### Acceptance Criteria

1. The Report shall state the size of the dataset every result was produced
   from. `AC-TRUTH-01`
2. The Report shall not present any accuracy, precision or recall figure as
   evidence that a candidate works. `AC-TRUTH-02`
3. The Report shall state, for every candidate trained, whether the run reached
   convergence or was stopped early, and why. `AC-TRUTH-03`
4. The Report shall state that no model was evaluated against real imagery.
   `AC-TRUTH-04`
