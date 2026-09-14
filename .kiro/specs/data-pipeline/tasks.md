# Implementation Plan

No task carries `(P)`. The example types in 1.1 are a prerequisite for every
other module, and the recorder, splits and dataset all operate on them.

- [ ] 1. Foundation: labeled examples and the expert

- [ ] 1.1 Define the example types
  - Carry object identity, material class, channel, belt position, and whether
    the object was inside the reachable window at capture.
  - Carry per example the frame, its labels, simulated time, seed, world
    configuration digest, and whether the example is synthetic or real.
  - Reject a material class outside the taxonomy.
  - Write the failing tests first.
  - Observable: a label round trips, and an invented class is refused by name.
  - _Requirements: 1.1, 1.2, 1.5_
  - _Boundary: clave.data.examples_

- [ ] 1.2 Implement the scripted expert
  - Select among objects currently inside the reachable window, preferring the
    one nearest the window exit since it has least time remaining.
  - Resolve the decision channel from the material class through the taxonomy.
  - Emit nothing when no object is reachable.
  - Observable: two runs at one seed produce the same decisions, and an empty
    window produces no decision rather than a decision naming nothing.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Boundary: clave.data.expert_

- [ ] 2. Core: recording, splitting, composition

- [ ] 2.1 Implement the rollout recorder
  - Step the world, capture frames offscreen, and emit one example per captured
    frame with the labels the world already holds.
  - Record the seed, the world configuration digest and the simulated time.
  - Observable: two rollouts at one seed and one configuration record identical
    examples, and every label carries a taxonomy class.
  - _Requirements: 1.3, 1.4_
  - _Boundary: clave.data.recorder_
  - _Depends: 1.1_

- [ ] 2.2 Implement splits
  - Partition into train, validation and test at configured proportions,
    dividing by rollout rather than by frame.
  - Verify no rollout appears in more than one part and fail rather than report
    a leaking split.
  - Fail naming the proportions when they do not sum to one.
  - Observable: two splits at one seed are identical, and a hand-constructed
    overlapping partition fails.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Boundary: clave.data.splits_
  - _Depends: 1.1_

- [ ] 2.3 Implement composition reporting
  - Count examples and per-class instances from the examples actually present,
    never from the requested proportions.
  - Name the taxonomy classes with no instances, per split part as well as
    overall.
  - Observable: a dataset whose configuration asked for a class it never
    produced reports that class as absent.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Boundary: clave.data.composition_
  - _Depends: 2.2_

- [ ] 3. Core: versioning and ingestion

- [ ] 3.1 Implement dataset write and read
  - Write per-rollout archives plus one description carrying the digest, the
    seed, the configuration digest and the composition.
  - Verify the digest on read and refuse a mismatch.
  - Keep datasets out of the repository.
  - Observable: a written dataset reads back, and flipping one byte makes the
    read refuse.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Boundary: clave.data.dataset_
  - _Depends: 2.3_

- [ ] 3.2 Implement corpus ingestion
  - Map a corpus label onto taxonomy classes using the mappings the taxonomy
    document records.
  - Record an ambiguity when a label spans several classes rather than choosing
    one, and keep an unmapped label rather than discarding its example.
  - Keep real examples separable from synthetic ones.
  - Observable: ZeroWaste's rigid_plastic maps to four classes and is recorded
    as ambiguous, and an invented label survives as unmapped.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Boundary: clave.data.ingest_
  - _Depends: 1.1_

- [ ] 4. Integration and validation

- [ ] 4.1 Expose the recording command
  - Add a command that records rollouts, splits them, reports composition, and
    writes a described dataset.
  - Observable: the command runs from a clean checkout and prints a composition
    table.
  - _Requirements: 4.1, 5.2_
  - _Depends: 3.1, 3.2_

- [ ] 4.2 Record a dataset and report what it contains
  - Run the command and capture its output.
  - State that no corpus has been fetched and that ingestion is exercised
    against a fixture rather than against real imagery.
  - Observable: a real dataset exists on disk with a digest, its composition is
    recorded, and the fixture-only status of ingestion is stated.
  - _Requirements: 6.5_
  - _Depends: 4.1_
