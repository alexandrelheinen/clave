# Requirements Document

## Project Description (Input)
Every step before this one produced either a document or a component. None of
them can say whether a trained candidate is good enough to keep, because nothing
in the project computes a metric and nothing states a threshold.

v0.7.0 will produce trained candidates and v1.0.0 will compare them. Both need a
scorer that was written before the numbers existed, because a threshold chosen
after seeing a result is a description of that result rather than a gate on it.

Three earlier documents already fix what this step has to measure.
[docs/waste-taxonomy.md](../../../docs/waste-taxonomy.md) names eleven material
classes and three confusions a color camera cannot resolve, and asks v0.8.0 to
report those three specifically instead of folding them into general error. It
also separates a missed pick, which is a throughput loss, from a misroute, which
contaminates a bale, and asks for the two to be counted separately.
[docs/research/sorting-world.md](../../../docs/research/sorting-world.md) fixes
the per-object time budget at 1.13 seconds at the fastest configured belt speed.
[docs/research/model-candidates.md](../../../docs/research/model-candidates.md)
measured perception latency on the development machine, so a latency gate has a
measured cost to sit beside.

This feature computes the metrics, states the gates as numbers in configuration,
and emits a report that separates what was run from what was concluded. It
trains nothing, loads no model, and steps no simulator.

## Introduction

The harness is a scorer over recorded outcomes. Its input is a list of records,
one per object presented to the system, and its output is a set of metrics plus
a pass or fail verdict against thresholds that were written down first.

Two properties shape the design. Every metric is a pure function of the records,
so a number can be reproduced from a file without a GPU, a simulator, or a
trained checkpoint. And every threshold lives in configuration, so no tunable
number is buried in Python where randomization and review cannot reach it.

The record type this harness defines is deliberately small and deliberately
temporary. v0.6.0 owns the rollout format, and when it lands, its format
supersedes this one. What survives the handover is the metric functions, which
depend on the fields rather than on the file.

Nothing here evaluates a model. No accuracy number in this repository is a
measurement until a trained candidate runs through the harness, and the report
has to make that visible rather than leave it to be assumed.

## Boundary Context

- **In scope**: the recorded outcome type, per-class accuracy and the confusion
  matrix over the eleven taxonomy classes, pick success rate, cycle time,
  decision latency percentiles including p99, missed picks counted apart from
  misroutes, the three named confusions reported individually, the gate
  thresholds as configuration, the pass or fail verdict, and one command that
  runs all of it.
- **Out of scope**: producing the outcomes, which belongs to v0.6.0 and v0.7.0.
  Training, checkpoint loading, and inference. Stepping the simulated world.
  Choosing which candidate CLAVE ships, which is v1.0.0's benchmark. The
  numbers themselves, since no model has been trained.
- **Adjacent expectations**: the taxonomy supplies the class identifiers and the
  three named confusions, and is not reopened here. The sorting world supplies
  the time budget a cycle time gate is set against. The data pipeline will
  supersede the record type defined here, so the metric functions must not
  depend on how the records were stored.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `OUTCOME`, `ACCURACY`, `PICK`, `TIMING`, `CONFUSION`, `GATE`, and
`VERDICT`. None of those areas is in use by an earlier spec. Ids are
append-only.

## Requirements

### Requirement 1: The recorded outcome

**Objective:** As the engineer writing the data pipeline at v0.6.0, I want the
harness to depend on a small set of named fields rather than on a file format,
so that replacing the format later does not rewrite the metrics.

#### Acceptance Criteria

1. The Harness shall define one record type describing what happened to a single
   object presented to the system, carrying its true class, the predicted class,
   whether it was picked, the channel it was routed to, its decision latency,
   and its cycle time. `AC-OUTCOME-01`
2. The Harness shall compute every metric as a pure function of a sequence of
   those records, without loading a model, stepping a simulator, or reading a
   corpus. `AC-OUTCOME-02`
3. If a record names a material class outside the taxonomy, then the Harness
   shall reject the record naming the offending class rather than counting it
   toward any metric. `AC-OUTCOME-03`
4. The Harness shall record whether each object instance was seen during
   training, so generalization is separable from memorization. `AC-OUTCOME-04`
5. The Harness shall read records from a file, so validation runs from one
   command. `AC-OUTCOME-05`
6. The Harness shall carry a provenance string alongside the records naming where
   they came from, so a fixture is never read as a measurement. `AC-OUTCOME-06`

### Requirement 2: Classification metrics

**Objective:** As whoever decides whether a candidate advances, I want per-class
accuracy and a full confusion matrix, so that a model good at the common classes
and blind to the rare ones is visible rather than hidden behind one average.

#### Acceptance Criteria

1. The Harness shall compute a confusion matrix over the eleven taxonomy
   classes, with rows indexed by the true class and columns by the predicted
   class. `AC-ACCURACY-01`
2. The Harness shall report accuracy for every taxonomy class individually, not
   only in aggregate. `AC-ACCURACY-02`
3. The Harness shall count objects for which no class was predicted separately
   from objects predicted as the wrong class. `AC-ACCURACY-03`
4. The Harness shall report accuracy over unseen object instances separately
   from accuracy over seen ones. `AC-ACCURACY-04`
5. If a taxonomy class has no record in the run, then the Harness shall report
   that class as unmeasured rather than as accurate. `AC-ACCURACY-05`

### Requirement 3: Picking and routing

**Objective:** As whoever has to fix a failing run, I want a missed pick counted
apart from a misroute, because one is a timing and grasping problem and the
other is a classification problem, and averaging them hides which to work on.

#### Acceptance Criteria

1. The Harness shall report the pick success rate over the objects presented to
   the system. `AC-PICK-01`
2. The Harness shall count missed picks separately from misroutes, and report
   both. `AC-PICK-02`
3. The Harness shall decide what counts as a misroute against a configured
   class-to-channel mapping rather than a mapping fixed in code. `AC-PICK-03`
4. The Harness shall count an object routed to the reject channel separately
   from an object routed into the wrong material channel, since a reject costs
   recovery and a misroute contaminates a bale. `AC-PICK-04`
5. If an object was not picked, then the Harness shall count it as a missed pick
   and shall not count it as a routing error. `AC-PICK-05`
6. The Harness shall report the rate of objects both picked and routed to the
   channel their true class belongs in, which is the end to end sorting rate.
   `AC-PICK-06`

### Requirement 4: Timing

**Objective:** As the engineer who has to fit a decision inside a 1.13 second
per-object budget, I want the tail rather than the average, because a system
that averages well and misses one object in a hundred drops that object.

#### Acceptance Criteria

1. The Harness shall report decision latency percentiles including the 99th.
   `AC-TIMING-01`
2. The Harness shall report cycle time, meaning the time an object occupied the
   system from decision to placement. `AC-TIMING-02`
3. The Harness shall compute a percentile by a stated method, and two runs over
   the same records shall produce the same percentile. `AC-TIMING-03`
4. The Harness shall report the sample count behind each percentile, so a tail
   figure drawn from too few samples is visible. `AC-TIMING-04`
5. If no record carries a value for a timing series, then the Harness shall
   report that series as unmeasured rather than as zero. `AC-TIMING-05`

### Requirement 5: The named confusions

**Objective:** As the reader of a validation report, I want the three
separations a color camera cannot make reported by name, so that an expected
sensor limit is distinguishable from a model that has learned nothing.

#### Acceptance Criteria

1. The Harness shall report each of the three confusions named in the taxonomy
   individually: transparent resins, can metals, and fiber flute. `AC-CONFUSION-01`
2. The Harness shall carry, for each named confusion, the class identifiers it
   spans and the reason the separation is unavailable from a color image.
   `AC-CONFUSION-02`
3. The Harness shall report, for each named confusion, the share of that group's
   records that were predicted as another member of the same group.
   `AC-CONFUSION-03`
4. The Harness shall report, for each named confusion, the errors on that group
   that fall outside the group, so a confusion rate is not read as the group's
   whole error. `AC-CONFUSION-04`
5. The Harness shall keep every named confusion inside the general confusion
   matrix as well, so naming a confusion removes nothing from the aggregate.
   `AC-CONFUSION-05`

### Requirement 6: The gates

**Objective:** As a reviewer, I want the threshold written down before the run,
so that a passing verdict is a claim somebody committed to in advance rather
than a number reported after the fact.

#### Acceptance Criteria

1. The Harness shall read every threshold from a configuration file, and shall
   carry no numeric threshold default in code. `AC-GATE-01`
2. If a threshold key is absent from the configuration, then the Harness shall
   fail at load naming the missing key rather than substituting a value.
   `AC-GATE-02`
3. When any gate is unmet, the Harness shall report the run as failed rather
   than reporting the observed number alone. `AC-GATE-03`
4. The Harness shall state, for every gate, its threshold beside the observed
   value, whether the gate passed or failed. `AC-GATE-04`
5. If a taxonomy class has fewer records than the configured minimum support,
   then the Harness shall fail that class's gate as unmeasured rather than
   passing it. `AC-GATE-05`
6. The Harness shall gate decision latency at the 99th percentile rather than at
   the mean. `AC-GATE-06`
7. The Harness shall gate the accuracy drop from seen to unseen object instances,
   so a candidate that only memorized fails. `AC-GATE-07`

### Requirement 7: The report and the command

**Objective:** As the reader of a validation run, I want the timeline and the
conclusion kept apart, because conflating them is how an optimistic reading
quietly replaces the evidence.

#### Acceptance Criteria

1. The Report shall separate what was run, meaning the record counts and their
   provenance, from what was concluded, meaning the gate verdicts.
   `AC-VERDICT-01`
2. The Report shall name the provenance of the records it scored, so a synthetic
   fixture is labeled as one. `AC-VERDICT-02`
3. The Report shall list every gate, including the ones that passed, so a
   threshold stays visible after the run as well as before it. `AC-VERDICT-03`
4. When any gate fails, the command shall exit non-zero. `AC-VERDICT-04`
5. The Harness shall run from one command taking a records file and a gate
   configuration. `AC-VERDICT-05`
