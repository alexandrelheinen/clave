# Requirements Document

## Project Description (Input)

Every step from v0.1.0 to v0.10.0 produced a number, and they are scattered
across ten documents measured under different conditions. v1.0.0 is where they
become one comparison: every configuration CLAVE can actually run, scored by the
same protocol, from one command, reproducible from a seed and a manifest.

It also has to be honest about what it cannot measure. Nothing in CLAVE executes
a pick, so pick success and cycle time have no value to report, and a benchmark
that quietly omitted them would read as though they were fine.

A second deliverable rides with it: a demonstration a person can run in one
line, ending in a video of the simulation it actually ran. Everything in this
repository so far is provable and nothing is watchable.

## Introduction

Three properties decide whether this release is worth the tag.

The comparison has to be fair, meaning every configuration sees the same seeds,
the same world and the same protocol, so a difference between rows is a
difference between configurations. Every number has to be reproducible, meaning
a seed, a dataset digest and a configuration digest travel with it. And the
unmeasurable has to be named rather than omitted, because the reader deciding
whether to trust this is the same reader who will eventually put it near a
machine.

## Boundary Context

- **In scope**: the benchmark, its configuration, its evidence pack and its
  report; the one-line demonstration and the video it records.
- **Out of scope**: training new architectures, fetching new corpora, executing
  a pick, anything on hardware, and any claim that a configuration is ready for
  a line.
- **Adjacent expectations**: the validation harness from v0.8.0 owns metrics and
  gates and is reused rather than reimplemented. The runtime from v0.9.0 owns
  the loop. The taxonomy owns the classes.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `BENCH` and `DEMO`. Ids are append-only and neither area collides with an
existing spec.

## Requirements

### Requirement 1: One comparison

**Objective:** As the engineer choosing what CLAVE should run, I want every
configuration scored by one protocol in one table, so that the choice rests on a
comparison rather than on ten documents.

#### Acceptance Criteria

1. The Benchmark shall run every configuration its file names, over the same
   seeds and the same world. `AC-BENCH-01`
2. The Benchmark shall report, per configuration, throughput, per-class sorting
   accuracy, decision latency percentiles, and the gates each configuration
   passed and failed. `AC-BENCH-02`
3. When a metric cannot be measured because nothing executes a pick, the
   Benchmark shall report it as unmeasured and name the reason rather than
   omitting it or substituting a value. `AC-BENCH-03`
4. The Benchmark shall name the configuration it recommends and the measured
   reason it beat the others. `AC-BENCH-04`
5. The Benchmark shall run from one command. `AC-BENCH-05`

### Requirement 2: Reproducibility

**Objective:** As anyone who will rerun this in six months, I want every number
to carry what produced it, so that a difference is a change rather than a
mystery.

#### Acceptance Criteria

1. The Benchmark shall record the seeds, the world configuration digest, the
   benchmark configuration digest, and the machine every measurement was taken
   on. `AC-BENCH-06`
2. The Benchmark shall write an evidence pack a later reader can parse without
   this package. `AC-BENCH-07`
3. When a configuration cannot run because a checkpoint or a library is absent,
   the Benchmark shall record that configuration as unavailable with the reason
   and continue with the others. `AC-BENCH-08`
4. Two runs at the same seeds and the same configuration shall produce the same
   per-class accuracy. `AC-BENCH-09`

### Requirement 3: A demonstration

**Objective:** As someone seeing this project for the first time, I want to run
one command and watch what it does, so that the claim is visible rather than
only provable.

#### Acceptance Criteria

1. The Demo shall run a named scenario from one command, with no argument beyond
   the scenario name required. `AC-DEMO-01`
2. The Demo shall take every tunable from a scenario file rather than from a
   command line default. `AC-DEMO-02`
3. The Demo shall record a video of the simulation it ran. `AC-DEMO-03`
4. The Demo shall record only frames the simulator produced, with no overlay,
   annotation or composition added afterwards. `AC-DEMO-04`
5. When the video encoder is absent, the Demo shall run the scenario and say
   that no video was recorded. `AC-DEMO-05`
6. The Demo shall print what the scenario did, including the decisions it
   published and what the safety layer overrode. `AC-DEMO-06`
