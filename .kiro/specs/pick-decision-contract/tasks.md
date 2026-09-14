# Implementation Plan

No task carries `(P)`. The workspace in 1.1 has to exist before any crate
compiles inside it, the contract types in 1.2 and 1.3 are what routing and
delivery are written against, and the codec in 1.4 is what the publisher
queues.

- [ ] 1. Foundation: the workspace and the contract

- [ ] 1.1 Land the workspace and switch the Rust gate on
  - Create the root manifest with edition 2024, resolver 3, the baseline lint
    tier in `[workspace.lints]`, a release profile that keeps overflow checks
    on, and the shared dependency versions.
  - Pin the toolchain and the components the gate needs, and commit
    `rustfmt.toml` and `deny.toml` beside the manifest.
  - Apply the hardened lint tier in the two crates that sit on the
    capture-to-decision path, and say in their crate documentation why.
  - Observable: the Rust half of the existing validation script stops skipping
    and runs formatting, lint, test, documentation, dependency, and coverage
    checks, and the same script is what continuous integration runs.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: workspace root_

- [ ] 1.2 Define the value types and the fixed class set
  - Give every field of a decision a newtype or an enumeration, so a channel
    cannot be passed where an object identity belongs.
  - Carry the eleven material classes from the taxonomy with explicit
    discriminants, append-only, one variant per `M-<NN>` identifier.
  - Write the failing tests first, covering the class set against the taxonomy
    and the window expressed as an earliest and a latest time.
  - Observable: a window that is not ordered is rejected, and the class set
    matches the taxonomy identifier for identifier.
  - _Requirements: 1.2, 1.4_
  - _Boundary: clave-decision::material, clave-decision::window_

- [ ] 1.3 Implement the validating constructor
  - Take the object identity, the class, the resolved channel, the predicted
    pose, the window, and the confidence, and reject any combination that
    breaks an invariant rather than trusting the caller.
  - Check that the pose reference time falls inside the window, which is what
    turns the predicted-pose requirement into a checked property.
  - Carry the object identity given to it without minting or rewriting one.
  - Observable: a decision carries all six values and its contract version, and
    an inverted window, a confidence outside zero to one, and a pose timed
    outside the window are each refused.
  - _Requirements: 1.1, 1.3, 1.9_
  - _Boundary: clave-decision::decision_

- [ ] 1.4 Implement the codec and the version rule
  - Encode to CBOR with named fields, fixed width floats, and class variants
    carried as their names.
  - Read the version before anything else and reject a whole message whose
    version the crate does not know, so a malformed remainder never reaches a
    field decoder.
  - Run every decoded message back through the validating constructor, so
    hostile bytes cannot produce a decision an invariant forbids.
  - Observable: a decision survives a round trip with every field bit for bit,
    including edge floats, and a message carrying an unknown version is refused
    whole.
  - _Requirements: 2.1, 2.2, 2.3, 2.6_
  - _Boundary: clave-decision::codec_

- [ ] 1.5 Publish the schema and the golden vectors
  - Write the CDDL schema naming the unit, the coordinate frame, and the time
    reference of every field, and stating what a consumer does with a version
    it does not recognize.
  - Commit a worked example per contract version as hex bytes beside the values
    they decode to, and leave an existing version directory untouched.
  - Observable: a consumer can implement the wire format from the committed
    schema and check an implementation against the committed bytes, without
    reading this repository's source.
  - _Requirements: 2.3, 2.4, 2.5, 2.6_
  - _Boundary: clave-decision/contract_

- [ ] 2. Core: routing and delivery

- [ ] 2.1 Implement the channel map and the resolver
  - Validate the operator-supplied mapping when it is loaded rather than once
    per object, and refuse a mapping that sends residue anywhere but the reject
    channel.
  - Test the confidence against the threshold before the class is looked up, so
    a low-confidence object never reaches a sorted channel even when its class
    is mapped.
  - Send an unmapped class to the reject channel with a reason that separates
    it from the low-confidence route.
  - Observable: resolution is total, meaning every class and every confidence
    produces a channel, and the two routes to the reject channel are
    distinguishable by their reason.
  - _Requirements: 1.5, 1.6, 1.7, 1.8_
  - _Boundary: clave-routing_

- [ ] 2.2 Implement the transport seam and the in-memory sink
  - Define the sink over an encoded frame rather than over a decision, so the
    schema stays on the contract side of the seam.
  - State in the trait that a send never blocks, and give it an outcome that
    separates an accepted record from one the transport refused.
  - Implement the in-memory sink the tests run against, including a refusing
    mode for the no-consumer case.
  - Observable: a sink reports refusal instead of waiting, and a refused frame
    is still owned by the caller.
  - _Requirements: 3.1, 3.2, 3.5_
  - _Boundary: clave-publish::sink_

- [ ] 2.3 Implement the publisher, its ring, and its counters
  - Hold a ring sized at construction, discard the oldest frame when a new one
    arrives at a full ring, and count that discard separately.
  - Check expiry immediately before a send rather than on a timer, and count an
    expired frame separately from an overflowed one.
  - Keep the counter identity, meaning that what was published equals what was
    delivered plus what was discarded either way plus what is still queued.
  - Observable: a frame leaves the ring in exactly one of three ways, each way
    moves exactly one counter, and no path blocks.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: clave-publish::publisher, clave-publish::counters_

- [ ] 2.4 Implement the socket sink
  - Send one encoded decision as one record over a Unix socket in seqpacket
    mode, so record boundaries come from the kernel.
  - Map a transport that would wait, and a peer that has gone, to a refusal
    rather than to an error, so a consumer that dies does not stall the
    pipeline.
  - Observable: a socket pair inside one test process carries decisions in
    order, and dropping the reading end leaves the publisher running.
  - _Requirements: 3.2, 3.5_
  - _Boundary: clave-publish::uds_

- [ ] 3. Integration

- [ ] 3.1 Prove the delivery contract against both sinks
  - Write one conformance suite generic over the sink and run it against the
    in-memory sink and against a real socket pair.
  - Cover a consumer that never reads and a consumer that disconnects partway,
    asserting the counters stay consistent in both.
  - Observable: ordering and the counter identity are proved per backend rather
    than assumed from the one the unit tests used.
  - _Requirements: 3.1, 3.2, 3.5, 3.6_
  - _Depends: 2.2, 2.3, 2.4_

- [ ] 3.2 Add the property tests
  - Generate arbitrary decisions and assert the round trip reproduces every
    field, which is where the input space is larger than the examples anyone
    would think to write.
  - Generate arbitrary publish sequences and assert the counter identity after
    each one.
  - Observable: both properties hold over generated input, and a failure prints
    the shrunk case that broke it.
  - _Requirements: 2.2, 3.3, 3.4_
  - _Depends: 1.4, 2.3_

- [ ] 4. Validation and measurement

- [ ] 4.1 Measure the publication budget
  - Record one duration per publication over a real socket, report the 99th
    percentile beside the median, and fail the run when the 99th percentile
    sits above the budget.
  - State the budget in the crate documentation as a share of the
    capture-to-delivery budget it belongs to.
  - Observable: the benchmark prints a percentile rather than a mean alone, and
    an over-budget measurement ends the run non-zero.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Depends: 2.4_

- [ ] 4.2 Run the gate and record what it reported
  - Execute the validation script and capture its output verbatim, including
    the test count and the coverage number.
  - Name anything the local machine cannot verify, meaning every latency figure
    is a development machine figure and not a target board figure.
  - Observable: the script exits zero, and the report separates what was run
    from what was concluded.
  - _Requirements: 5.1, 5.2, 5.3, 5.5_
  - _Depends: 3.1, 3.2, 4.1_
