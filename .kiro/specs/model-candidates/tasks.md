# Implementation Plan

No task carries `(P)`. The interface in 1.1 is a prerequisite for every adapter,
and the adapters share one registry file.

- [ ] 1. Foundation: the interface and the fixture

- [ ] 1.1 Define the candidate interface
  - Define the spec carrying name, stage, license, source, and the dependency
    its adapter needs, constructible without importing anything heavy.
  - Define a load result that is either a model or an unavailable reason naming
    the missing dependency, so an absent library never raises through.
  - Write the failing tests first, covering construction with no optional
    dependency installed and the unavailable path.
  - Observable: the module imports on a machine with no torch, and a spec
    reports its stage and license.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Boundary: clave.candidates.base_

- [ ] 1.2 Implement the deterministic fixture
  - Generate frames and states from a seed through the existing seeding entry
    point rather than adding a second source of randomness.
  - Observable: two runs at one seed produce identical arrays, two seeds do not,
    and no binary is committed.
  - _Requirements: 3.5_
  - _Boundary: clave.candidates.fixture_

- [ ] 2. Core: adapters and measurement

- [ ] 2.1 Implement the perception adapters
  - Adapt the advancing perception architectures, loading each from its upstream
    library rather than reimplementing it.
  - Size the classifier output to the class count fixed by the taxonomy.
  - Record a load failure with its reason rather than substituting a candidate.
  - Observable: each perception candidate either loads with a parameter count or
    reports why it did not.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: clave.candidates.perception_

- [ ] 2.2 Implement the policy adapters
  - Adapt the advancing policy architectures from their upstream libraries, and
    implement the behavior cloning baseline in-project since it has no upstream.
  - Observable: each policy candidate either loads with a parameter count or
    reports why it did not.
  - _Requirements: 2.1, 2.2, 2.4_
  - _Boundary: clave.candidates.policy_

- [ ] 2.3 Implement the benchmark
  - Run and discard warm-up iterations, then time repeated single-frame forward
    passes, reporting the median, the spread, and the repetition count.
  - Record the hardware and the thread count the measurement was taken on.
  - Observable: a benchmark result carries a parameter count, a latency with its
    spread, and the machine it came from.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_
  - _Boundary: clave.candidates.bench_
  - _Depends: 1.2_

- [ ] 3. Integration

- [ ] 3.1 Build the registry and expose the command
  - List every architecture the v0.1.2 shortlist advances, one entry each.
  - Add a command that loads and benchmarks the registry and prints a table.
  - Observable: the command runs from a clean checkout and reports every
    candidate as benchmarked or unavailable.
  - _Requirements: 2.1, 1.3_
  - _Depends: 2.1, 2.2, 2.3_

- [ ] 4. Validation and report

- [ ] 4.1 Run the benchmark and record the measurements
  - Execute the command on this machine and capture its output verbatim.
  - Observable: every shortlisted candidate has a measured parameter count and
    latency, or a recorded reason it has neither.
  - _Requirements: 3.1, 3.2, 3.6_
  - _Depends: 3.1_

- [ ] 4.2 Write the report
  - Publish the measurements under `docs/research/`, each beside the v0.1.2
    estimate it replaces.
  - Name any v0.1.2 verdict a measurement contradicts, rather than editing the
    review from here.
  - State that nothing was trained and no accuracy was measured, and record any
    candidate that failed to load.
  - Observable: a reader can tell, for every candidate, what was measured, what
    was estimated, and what is still unknown.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Depends: 4.1_
