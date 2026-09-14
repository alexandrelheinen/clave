# Requirements Document

## Project Description (Input)
Every piece exists and none of them are connected. The world runs, models are
trained, the decision contract is published, the routing resolver is written,
and nothing takes a frame and produces a decision.

This feature closes the loop CLAVE owns: a frame leaves the simulator, inference
proposes a pick, a safety layer in Rust accepts or overrides it, and the
resulting decision is published. It stops at CLAVE's boundary. Handing the
decision to FRET so it drives the manipulator is v0.10.0, which was split out
when this step was narrowed on 2026-09-14.

It also has to make a decision that v0.3.0 deliberately deferred and nobody has
made since: how Rust consumes a model trained in Python. Both
`docs/guidelines.md` and `.kiro/steering/tech.md` still say the inference
runtime is "chosen at the learning-platform step", and it was not. Choosing it
mid-implementation is what this specification exists to prevent, so it is
settled here in the open.

The safety layer is the part that justifies Rust being in this project at all.
CLAVE's constitution says inference proposes and a deterministic layer disposes.
Until now that layer has been a claim.

## Introduction

This feature is the first time anything in CLAVE runs end to end.

Two properties decide whether it is worth having. A proposal that would put the
effector outside its reachable workspace must be overridden rather than
published, because publishing it makes the safety layer decorative. And the
latency from frame to published decision must be measured at p99 against a
stated budget, because v0.5.0 established that an object is reachable for only
1.13 seconds at the fastest configured belt speed.

The models this runs were trained on 240 frames of parametric primitives. The
loop will run correctly and decide badly, and the report says so. What is being
proven is the mechanism.

## Boundary Context

- **In scope**: the boundary by which Rust consumes inference results, the
  safety layer and its geometric checks, the runtime that drives the loop, the
  published decision, and the measured p99 latency from frame to decision.
- **Out of scope**: handing the decision to FRET or ROS 2, which is v0.10.0.
  Moving the manipulator in response to a decision. Training, metrics and gates.
  Any claim that a decision is correct. Hardware of any kind.
- **Adjacent expectations**: the pick decision contract is already merged and is
  consumed rather than redesigned. The routing resolver already maps a class and
  a confidence to a channel or a reject, and is not reimplemented. The world
  supplies frames and the arm's reachable geometry.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `BRIDGE`, `SAFETY`, `LOOP`, and `RTBENCH`. Ids are append-only and none of
these areas collides with an existing spec.

## Requirements

### Requirement 1: The inference boundary

**Objective:** As the engineer who will change either side of this, I want the
boundary between Python inference and Rust safety stated explicitly, so that the
choice v0.3.0 deferred is recorded rather than assumed.

#### Acceptance Criteria

1. The Runtime shall carry inference results from Python to Rust across a
   documented boundary whose format is versioned. `AC-BRIDGE-01`
2. The Runtime shall not require the Rust side to load, execute or link a deep
   learning framework. `AC-BRIDGE-02`
3. When the Rust side receives a proposal whose version it does not recognize,
   the Runtime shall reject it rather than interpret it. `AC-BRIDGE-03`
4. When the Rust side receives a malformed proposal, the Runtime shall report
   the failure and continue rather than terminating. `AC-BRIDGE-04`
5. The Runtime shall document the boundary's format so a consumer can implement
   against it without reading CLAVE's source. `AC-BRIDGE-05`

### Requirement 2: The safety layer

**Objective:** As anyone who will eventually let this drive a physical arm, I want
a deterministic layer that can override the model, so that "inference proposes,
Rust disposes" is a mechanism rather than a slogan.

#### Acceptance Criteria

1. When a proposal names a pick point outside the manipulator's reachable
   workspace, the Safety Layer shall override it rather than publish it.
   `AC-SAFETY-01`
2. When a proposal names a pick point below the belt surface, the Safety Layer
   shall override it. `AC-SAFETY-02`
3. When a proposal names a pick point outside the belt's extent, the Safety
   Layer shall override it. `AC-SAFETY-03`
4. When the Safety Layer overrides a proposal, the Runtime shall record which
   check failed. `AC-SAFETY-04`
5. The Safety Layer shall read its workspace envelope from configuration rather
   than from a constant in code. `AC-SAFETY-05`
6. The Safety Layer shall reach a verdict for every proposal, with no input
   leaving it undecided. `AC-SAFETY-06`
7. When a proposal carries a confidence below the configured floor, the Runtime
   shall route it to the reject channel rather than to its class channel.
   `AC-SAFETY-07`

### Requirement 3: The loop

**Objective:** As a reader deciding whether CLAVE works at all, I want one command
that runs the whole thing, so that the claim is demonstrable rather than
architectural.

#### Acceptance Criteria

1. When the runtime is started, the Runtime shall step the simulated world,
   produce a decision per captured frame where an object is reachable, and
   publish it. `AC-LOOP-01`
2. The Runtime shall use a trained candidate loaded from a checkpoint.
   `AC-LOOP-02`
3. When no object is reachable in a frame, the Runtime shall publish nothing
   rather than a decision naming nothing. `AC-LOOP-03`
4. The Runtime shall report how many proposals were accepted, overridden and
   rejected over a run. `AC-LOOP-04`
5. The Runtime shall state that the models it runs were trained on a dataset too
   small for any decision to be meaningful. `AC-LOOP-05`

### Requirement 4: Measured latency

**Objective:** As whoever judges whether this could ever run on a line, I want the
frame-to-decision latency measured at p99, so that it can be held against the
1.13 second window an object is reachable for.

#### Acceptance Criteria

1. When the runtime runs, the Runtime shall measure the latency from frame
   capture to published decision. `AC-RTBENCH-01`
2. The Runtime shall report that latency at the 99th percentile, not as a mean.
   `AC-RTBENCH-02`
3. The Runtime shall report the measured latency against the per-object time
   budget the world implies. `AC-RTBENCH-03`
4. The Runtime shall record the hardware a measurement was taken on.
   `AC-RTBENCH-04`
