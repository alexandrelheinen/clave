# Implementation Plan

Unlike v0.1.0 and v0.2.0, this spec delivers code, so the task rules apply
without deviation.

No task carries `(P)`. The toolchain in 1.1 is a prerequisite for every other
task, and the three core modules land in one package whose configuration files
they share.

- [ ] 1. Foundation: the Python toolchain

- [ ] 1.1 Create the package layout and project configuration
  - Create `pyproject.toml` declaring the package, its runtime dependencies, and
    PyTorch as an optional extra that nothing in the core imports.
  - Configure ruff, mypy in strict mode, pytest, and the coverage floor the
    house standards set, all in that one file.
  - Create `src/clave/` with the package root and `tests/` mirroring it.
  - Observable: `ruff check`, `mypy --strict`, and `pytest` all run against an
    empty package and report success.
  - _Requirements: 1.1, 1.2, 1.5_

- [ ] 1.2 Wire the Python chain into the gate
  - Add a Python step to `scripts/validate.sh` running lint, type checking, and
    tests with coverage, failing the gate if any fails.
  - Guard the step on `pyproject.toml` existing, matching how the Rust chain is
    already guarded on `Cargo.toml`.
  - Observable: `./scripts/validate.sh` runs the Python chain and exits 0, and
    still exits 0 on a tree with no `pyproject.toml`.
  - _Requirements: 1.3, 1.4_

- [ ] 2. Core: corpus manifest and verification

- [ ] 2.1 Implement the manifest
  - Define the artifact entry carrying name, source, and an optional digest,
    with the absent digest expressed in the type rather than as a convention.
  - Parse the committed manifest and reject a duplicate name or a malformed
    entry with an error naming the offender.
  - Write the failing tests first, covering a valid round trip, an entry without
    a digest, and a duplicate name.
  - Observable: the tests fail for the right reason before the module exists and
    pass after it, and no manifest format admits inline binary content.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: clave.corpus.manifest_

- [ ] 2.2 Implement artifact verification
  - Return three distinct outcomes for a local artifact: verified, digest
    mismatch, and unverified entry, with availability true only for the first.
  - Implement the record-digest path so that it computes from local bytes and
    returns the digest for review without writing the manifest.
  - Commit a small fixture with a real digest so the path is exercised without a
    network call.
  - Observable: mutating one byte of the fixture turns a verified result into a
    mismatch, and the manifest file is unchanged after recording a digest.
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - _Boundary: clave.corpus.artifacts_

- [ ] 3. Core: experiment recording and determinism

- [ ] 3.1 Implement seeding and the tolerance
  - Provide one entry point seeding the standard library and NumPy, and seeding
    PyTorch only when it is importable so the core carries no hard dependency.
  - Declare the tolerance as a module constant with a numeric value.
  - Write a test proving the same seed reproduces metrics within tolerance, and
    a second proving a different seed does not, since a determinism test that
    passes for a constant function proves nothing.
  - Observable: both tests pass, and the second fails if seeding is removed.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Boundary: clave.experiment.seeding_

- [ ] 3.2 Implement the run record
  - Record seed, a configuration digest taken over a canonical serialization,
    the artifact names and digests used, the interpreter version, and the
    versions of declared dependencies present at run time.
  - Serialize as JSON, and reject construction when an artifact is absent from
    the manifest.
  - Observable: a written record reloads with `json.load` in a fresh interpreter
    that never imports project code, and an unknown artifact raises before
    anything is written.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: clave.experiment.run_
  - _Depends: 2.1_

- [ ] 4. Core: research document checker

- [ ] 4.1 Implement the table checker deferred from v0.1.0
  - Check each declared table's header against its schema exactly, report an
    empty cell naming its row and column, and check every verdict against the
    closed vocabulary declared for that document.
  - Skip a document that is absent rather than failing, so the gate stays green
    on a clone that has not reached v0.1.0.
  - Observable: the checker passes against the delivered v0.1.0 review, and
    fails with a named row when a cell is emptied in a fixture.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Boundary: clave.research.tables_

- [ ] 5. Integration and validation

- [ ] 5.1 Expose the command entry points the gate calls
  - Provide commands for verifying the manifest and checking the research
    documents, so the gate calls a stable interface rather than module paths.
  - Observable: both commands run from a clean checkout and return a non-zero
    exit code on failure.
  - _Requirements: 1.3_
  - _Depends: 2.2, 4.1_

- [ ] 5.2 Run the full gate and record the evidence
  - Run `./scripts/validate.sh` end to end and record its output.
  - Confirm coverage meets the floor, and that the research checker passes
    against the real v0.1.0 document rather than only against fixtures.
  - Observable: the gate exits 0 with the Python chain active, and the recorded
    output shows lint, types, tests, and coverage all passing.
  - _Requirements: 1.3, 1.5_
  - _Depends: 5.1_
