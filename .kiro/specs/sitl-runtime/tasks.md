# Implementation Plan

No task carries `(P)`. The proposal format is a prerequisite for both sides of
the boundary, and the loop depends on everything before it.

- [x] 1. Foundation: the boundary

- [x] 1.1 Define the proposal and its wire format
  - Carry a version, an object id, a material class, a confidence and a pick
    point, decoded in Rust without linking any machine learning library.
  - Refuse an unrecognized version rather than interpreting it, and report a
    malformed payload without terminating.
  - Write the failing tests first.
  - Observable: a proposal round-trips, an unknown version is refused by
    version, and the safety crate's manifest names no machine learning
    dependency.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Boundary: clave-safety proposal_

- [x] 1.2 Document the boundary
  - Record the format so a consumer can implement against it without reading
    CLAVE's source, and record the choice and its rejected alternatives in
    docs/decisions.md.
  - Observable: the format has a written description with field names, types and
    the version rule, and a decision entry names ONNX, TorchScript and
    reimplementation as the options not taken.
  - _Requirements: 1.5_
  - _Boundary: documentation_

- [x] 2. Core: the safety layer

- [x] 2.1 Implement the workspace envelope
  - Read the arm base, reachable radius, belt surface height and belt extent
    from configuration, with no geometric constant in code.
  - Observable: the envelope loads from a file and a missing key fails naming it.
  - _Requirements: 2.5_
  - _Boundary: clave-safety envelope_

- [x] 2.2 Implement the checks and the verdict
  - Override a pick point outside the reachable radius, below the belt surface,
    or outside the belt's extent, naming which check failed.
  - Reach exactly one verdict for every proposal.
  - Observable: a swept grid of points yields exactly one verdict each, and a
    point beyond reach is overridden with the reach check named.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_
  - _Boundary: clave-safety verdict_
  - _Depends: 2.1_

- [x] 2.3 Route low confidence to reject rather than overriding it
  - Use the existing resolver so a confidence below the floor becomes a reject
    route rather than a safety override.
  - Observable: a low-confidence proposal inside the envelope is published to
    the reject channel and does not increment the override count.
  - _Requirements: 2.7_
  - _Boundary: clave-safety verdict_
  - _Depends: 2.2_

- [x] 3. Core: the loop

- [x] 3.1 Implement the Python side
  - Step the world, run a trained candidate loaded from a checkpoint, and emit a
    proposal for the object the policy selects.
  - Emit nothing when no object is reachable.
  - Observable: running the loop produces proposals on the boundary, and a frame
    with nothing reachable produces none.
  - _Requirements: 3.1, 3.2, 3.3_
  - _Boundary: clave.runtime_
  - _Depends: 1.1_

- [x] 3.2 Measure frame to decision latency
  - Time from frame capture to published decision, report the 99th percentile
    rather than a mean, and record the hardware.
  - Observable: a run reports a p99 figure and the machine it came from.
  - _Requirements: 4.1, 4.2, 4.4_
  - _Boundary: clave.runtime_
  - _Depends: 3.1_

- [x] 4. Integration and report

- [x] 4.1 Run the loop end to end and count outcomes
  - Report proposals, accepted, overridden by check, and rejected on confidence.
  - Observable: one command runs the world, the model, the safety layer and the
    publisher, and prints the counts.
  - _Requirements: 3.4_
  - _Depends: 2.3, 3.2_

- [x] 4.2 Write the report
  - State the measured p99 against the per-object time budget the world implies.
  - State that the models were trained on a dataset too small for any decision
    to be meaningful, and that nothing was validated on hardware.
  - Observable: a reader can tell what the loop proves and what it does not.
  - _Requirements: 3.5, 4.3_
  - _Depends: 4.1_
