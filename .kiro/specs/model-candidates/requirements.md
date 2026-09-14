# Requirements Document

## Project Description (Input)
v0.1.2 named which architectures advance and rejected two on a compute budget
that turned out to be CPU-only. Every number behind those verdicts is an
estimate. Nothing has been loaded, nothing has run, and no parameter count or
latency in this project has been measured.

v0.7.0 trains these candidates and v0.8.0 compares them. Both depend on the
shortlist being real rather than plausible. If the Faster R-CNN cost estimate is
wrong by a factor of five, the perception shortlist has one entry and the
roadmap target is unmet; nobody will discover that by reading the review again.

This feature puts every shortlisted architecture behind one interface, loads it,
runs a forward pass, and records what it actually costs on the hardware this
project has. Replacing estimates with measurements is the point. A candidate
that cannot be loaded is recorded as such rather than carried forward on its
reputation.

The interface matters as much as the numbers. v0.7.0 trains against it and
v0.9.0 loads a trained policy through it, so it has to hide each library's
conventions without leaking any one architecture's assumptions into the shape.

Heavy dependencies stay optional. The gate must not require a multi-gigabyte
install, so the platform imports them lazily and the tests skip when they are
absent.

## Introduction

This step converts a shortlist into a measured comparison. Its value is the
numbers and the interface, in that order.

Two constraints shape it. The hardware is a mobile CPU inside 7 GiB with no
accelerator, so a measurement here is a measurement of the worst case CLAVE will
run in, which is the useful case. And the candidates come from four different
libraries with four different conventions, so the interface has to be narrow
enough that adding a fifth does not change it.

Nothing is trained. A forward pass on a fixture is not an accuracy claim, and
the deliverable says so.

## Boundary Context

- **In scope**: the candidate interface, an adapter per shortlisted
  architecture, a deterministic fixture, the measurement of parameter count and
  single-frame latency, the record of which candidates loaded, and the document
  reporting all of it.
- **Out of scope**: training, fine-tuning, accuracy, and any claim about
  sorting quality. Selecting the single architecture CLAVE ships, which follows
  from v0.7.0 and v0.8.0 rather than from load-time cost. Corpus fetching.
  Anything requiring an accelerator.
- **Adjacent expectations**: v0.1.2's shortlist supplies the candidates and is
  not reopened, though a measurement that contradicts an estimate is reported
  back to it. The taxonomy supplies the class count an output head is sized to.
  The gate must stay runnable without the heavy dependencies installed.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `IFACE`, `ADAPT`, `BENCH`, and `REPORT`. Ids are append-only.

## Requirements

### Requirement 1: The candidate interface

**Objective:** As the engineer writing the training loop at v0.7.0, I want one
interface every candidate satisfies, so that swapping architectures is a
configuration change rather than a rewrite.

#### Acceptance Criteria

1. The Platform shall define one interface that every candidate implements,
   carrying its identity, its stage, its license, and its source.
   `AC-IFACE-01`
2. When a candidate is described, the Platform shall report whether it is a
   perception or a pick-policy candidate. `AC-IFACE-02`
3. The Platform shall allow a candidate to be described without being loaded, so
   the registry can be inspected on a machine with no heavy dependency
   installed. `AC-IFACE-03`
4. The Platform shall not require any candidate's library to be importable at
   package import time. `AC-IFACE-04`
5. If a candidate's library is absent, then the Platform shall report the
   candidate as unavailable naming the missing dependency, rather than raising
   an unhandled import error. `AC-IFACE-05`

### Requirement 2: Adapters for the shortlisted architectures

**Objective:** As a reviewer of the shortlist, I want each advancing architecture
actually loaded from its upstream library, so that the shortlist describes
software that exists rather than software that is reputed to.

#### Acceptance Criteria

1. The Platform shall provide an adapter for every architecture the v0.1.2
   shortlist advances. `AC-ADAPT-01`
2. When an adapter loads a candidate, the Platform shall load it from its
   upstream library rather than from a reimplementation. `AC-ADAPT-02`
3. The Platform shall size a perception candidate's output to the class count
   fixed by the taxonomy. `AC-ADAPT-03`
4. If an adapter cannot load its candidate, then the Platform shall record the
   failure and its reason rather than substituting another candidate.
   `AC-ADAPT-04`

### Requirement 3: Measurement

**Objective:** As whoever plans v0.7.0, I want measured cost rather than
estimated cost, so that the schedule rests on this hardware instead of on an
assumption about it.

#### Acceptance Criteria

1. When a candidate is benchmarked, the Platform shall report its parameter
   count. `AC-BENCH-01`
2. When a candidate is benchmarked, the Platform shall report single-frame
   forward-pass latency measured on the machine it ran on. `AC-BENCH-02`
3. The Platform shall discard warm-up iterations before measuring, so a
   reported latency is not dominated by first-call initialization.
   `AC-BENCH-03`
4. The Platform shall report the number of repetitions behind a latency figure
   and a measure of its spread, so a single unlucky sample is visible.
   `AC-BENCH-04`
5. The Platform shall drive every candidate with a fixture generated
   deterministically from a seed rather than from a committed binary.
   `AC-BENCH-05`
6. The Platform shall record the hardware and the thread count a measurement was
   taken on. `AC-BENCH-06`

### Requirement 4: The delivered report

**Objective:** As a reader deciding whether the shortlist survives contact with
reality, I want the measurements next to the estimates they replace.

#### Acceptance Criteria

1. The Report shall be published under `docs/research/` as a document committed
   to this repository. `AC-REPORT-01`
2. When the Report states a measurement, the Report shall distinguish it from
   the v0.1.2 estimate it replaces. `AC-REPORT-02`
3. If a measurement contradicts a v0.1.2 verdict, then the Report shall say so
   and name the verdict affected. `AC-REPORT-03`
4. The Report shall state that no candidate was trained and that no accuracy was
   measured. `AC-REPORT-04`
5. The Report shall record any shortlisted candidate that failed to load, with
   the reason. `AC-REPORT-05`
