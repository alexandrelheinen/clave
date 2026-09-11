# Requirements Document

## Project Description (Input)
CLAVE decides which channel a piece of waste belongs in and when to reach
for it, while ARCO and FRET carry out the motion that follows from that
decision. Nothing in this repository defines what CLAVE hands them. No
crate exists, the workspace and its Rust gates have not landed, and the
sibling projects have no type to compile against, so integration work on
either side would be guessing at a shape that can still change.

This feature defines the pick decision as a serializable type owned by
CLAVE, together with the mechanism that delivers it to a consumer. A
decision names the material class the classifier assigned and the channel
CLAVE resolved from that class, so a consumer can act on the channel
directly while a log retains the reasoning behind it. The schema is
versioned, round-trips through serialization without loss, and is
documented well enough that a consumer adapts to it rather than importing
CLAVE's source.

Delivery is in scope, but the transport is not chosen at this phase.
Requirements state what a consumer observes, meaning every decision
arrives once, in order, and inside the stated latency budget. The design
phase selects the mechanism and records why it beat the alternatives.

The first crate also brings the workspace it lives in: edition 2024, the
lint tiers from the shared Rust guidelines with the hardened tier applied
to the pipeline crate, overflow checks in release, a committed deny.toml,
and the Rust half of scripts/validate.sh switching on.

## Introduction

CLAVE decides what to pick off the belt and when, then hands that decision
to the projects that move the effector. This feature defines what a
decision contains, how a consumer reads it without depending on CLAVE's
internals, how it reaches that consumer, and what happens when the
consumer cannot keep up. It is the first feature to land code, so it also
brings the workspace and the quality gates the repository already
describes.

A decision carries the material class, the channel CLAVE resolved for it,
the pose the object will hold when the effector arrives, the window during
which it is reachable, the confidence behind the class, and the identity
the tracker assigned. Everything a consumer needs to reach for the object
is in the decision, so nothing that CLAVE already estimated has to be
estimated a second time downstream.

## Boundary Context

- **In scope**: the content of a decision, its versioned schema and its
  documentation, the resolution from material class to channel including
  the low-confidence case, delivery to a consumer with a stated ordering
  and overflow policy, the publication latency budget and its benchmark,
  and the workspace and gates that first code brings with it.
- **Out of scope**: capture, inference, and tracking, which produce the
  estimates a decision reports; motion planning and effector execution,
  which belong to ARCO and FRET; the physical channel hardware; the choice
  of transport mechanism, which the design phase makes and records.
- **Adjacent expectations**: the line operator supplies the mapping from
  material class to physical channel, including which channel is the
  reject channel. A consumer implements against the published contract
  rather than importing CLAVE's source, and CLAVE does not import a
  sibling's types.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, with areas `DECISION`, `SCHEMA`,
`PUBLISH`, `LATENCY`, and `BUILD`. Ids are append-only: a removed
criterion leaves its number retired rather than reused, so a reference in
an old commit never resolves to different text. Every criterion below is
referenced by at least one test naming its id, which keeps the mapping
greppable from either direction.

## Requirements

### Requirement 1: Decision content

**Objective:** As a consumer moving the effector, I want each decision to
carry everything needed to reach for one object, so that I do not
re-derive estimates CLAVE has already made.

#### Acceptance Criteria

1. `AC-DECISION-01` When CLAVE resolves an object to a channel, CLAVE
   shall publish a decision carrying the material class, the resolved
   channel, the pick pose, the pick time window, the classifier
   confidence, and the object identity.
2. `AC-DECISION-02` CLAVE shall draw the material class of every decision
   from the fixed set of classes named in the contract.
3. `AC-DECISION-03` When CLAVE publishes a decision, CLAVE shall state the
   pose the object is predicted to hold during the pick time window,
   rather than the pose observed when the object was captured.
4. `AC-DECISION-04` CLAVE shall express the pick time window as an
   earliest and a latest time at which the object is reachable.
5. `AC-DECISION-05` CLAVE shall resolve the channel for a decision from
   the operator-supplied mapping from material class to channel.
6. `AC-DECISION-06` If the classifier confidence for an object falls below
   the configured threshold, then CLAVE shall resolve that object to the
   reject channel and publish it as an ordinary decision.
7. `AC-DECISION-07` If the configured mapping names no channel for an
   object's material class, then CLAVE shall resolve that object to the
   reject channel and record the unmapped class.
8. `AC-DECISION-08` While an object has not been resolved to a channel,
   CLAVE shall publish no decision for it.
9. `AC-DECISION-09` When CLAVE publishes more than one decision for the
   same tracked object, CLAVE shall carry the same object identity in
   each of them.

### Requirement 2: Schema and compatibility

**Objective:** As a maintainer of a sibling project, I want a versioned
and documented schema, so that I can integrate against it without reading
or vendoring CLAVE's source.

#### Acceptance Criteria

1. `AC-SCHEMA-01` CLAVE shall carry the contract version in every
   published decision.
2. `AC-SCHEMA-02` When a decision is serialized and then deserialized,
   CLAVE shall reproduce every field with its value and precision intact.
3. `AC-SCHEMA-03` If the fields of a decision or the set of material
   classes change, then CLAVE shall raise the contract version.
4. `AC-SCHEMA-04` CLAVE shall document every field of a decision with its
   unit, its coordinate frame, and its time reference.
5. `AC-SCHEMA-05` CLAVE shall publish a worked example of a serialized
   decision that a consumer can implement against.
6. `AC-SCHEMA-06` CLAVE shall state in the contract documentation what a
   consumer is expected to do with a decision whose contract version that
   consumer does not recognize.

### Requirement 3: Delivery

**Objective:** As an operator, I want delivery to behave predictably when
the line runs faster than the consumer, so that I can tell a healthy line
from an overloaded one.

#### Acceptance Criteria

1. `AC-PUBLISH-01` When CLAVE publishes a decision and the consumer is
   keeping up, CLAVE shall deliver that decision exactly once.
2. `AC-PUBLISH-02` CLAVE shall deliver decisions in the order it published
   them.
3. `AC-PUBLISH-03` While the outbound queue is full, when CLAVE publishes
   a decision, CLAVE shall discard the oldest undelivered decision to make
   room for it.
4. `AC-PUBLISH-04` When CLAVE discards a decision, CLAVE shall increment a
   discarded-decision count that an operator can read.
5. `AC-PUBLISH-05` If no consumer is reachable, then CLAVE shall keep
   producing and discarding under the same policy rather than stalling the
   pipeline.
6. `AC-PUBLISH-06` If a decision's pick time window has already closed
   when CLAVE is about to deliver it, then CLAVE shall discard it and
   count it as missed rather than delivering a decision no consumer can
   act on.

### Requirement 4: Latency budget

**Objective:** As a maintainer, I want the publication budget measured
rather than assumed, so that a change that breaks it fails before it
reaches a line.

#### Acceptance Criteria

1. `AC-LATENCY-01` When CLAVE produces a decision, CLAVE shall deliver it
   to a connected consumer within 5 milliseconds at the 99th percentile.
2. `AC-LATENCY-02` CLAVE shall document the 5 millisecond publication
   budget as a share of the 100 millisecond capture-to-delivery budget it
   belongs to.
3. `AC-LATENCY-03` When the benchmark suite runs, the benchmark suite shall
   report the 99th percentile publication latency.
4. `AC-LATENCY-04` If measured publication latency exceeds the budget,
   then the benchmark suite shall fail rather than report the number and
   pass.

### Requirement 5: Workspace and quality gate

**Objective:** As a maintainer, I want the first code to land with the
gates this repository already describes switched on, so that every later
change is held to them from the start.

#### Acceptance Criteria

1. `AC-BUILD-01` When a contributor runs the repository validation script,
   the validation script shall run formatting, lint, test, documentation,
   dependency, and coverage checks, and exit non-zero if any of them
   fails.
2. `AC-BUILD-02` When continuous integration runs, the continuous
   integration workflow shall execute that same validation script, so a
   local result and a remote result cannot disagree.
3. `AC-BUILD-03` If line coverage falls below 80 percent, then the
   validation script shall fail.
4. `AC-BUILD-04` If an arithmetic operation on the decision path overflows
   in a release build, then CLAVE shall fault rather than produce a
   wrapped value.
5. `AC-BUILD-05` If a reference in the published documentation does not
   resolve, then the documentation build shall fail.

## Constraints

| Constraint | Value |
| --- | --- |
| Publication latency | 5 ms at p99, inside a 100 ms p99 capture-to-delivery budget |
| Overflow policy | Bounded outbound queue, discard the oldest, counted |
| Class set | Fixed and versioned; adding a class raises the contract version |
| Test environment | No camera and no belt is available, so no criterion above may require hardware to verify |
| Sibling coupling | Consumers adapt to the published contract; sibling types are never imported and sibling sources are never vendored |
| Transport | Selected and justified in the design phase, not here |
| Coverage floor | 80 percent of lines |
