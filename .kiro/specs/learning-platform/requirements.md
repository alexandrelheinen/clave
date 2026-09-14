# Requirements Document

## Project Description (Input)
v0.1.0 shortlisted three corpora and a platform stack, and v0.2.0 fixed the
class vocabulary, but nothing in this repository can yet fetch a corpus, record
a run, or reproduce a result. CLAVE has no Python package, no test runner, no
lint configuration, and no way to say which version of which data produced which
number.

That gap is load-bearing for everything after it. v0.6.0 builds a training set,
v0.7.0 trains every shortlisted candidate, and v0.8.0 compares them. A
comparison between two candidates is worthless if the two runs cannot be shown
to have seen the same data, and a number nobody can reproduce is an anecdote.

This feature stands up the platform those steps run on. It brings the Python
toolchain the house standards require, a corpus manifest that resolves every
artifact by checksum so that no binary is committed and no fetch is ambiguous, a
run record carrying the seed, the configuration and the environment that
produced a result, and a determinism rule stating what reproducible means in
numeric terms.

It also inherits an obligation from v0.1.0: the table schemas in the research
documents were specified to be mechanically checkable, and enforcement was
deferred to this step precisely because a checker would have settled the Python
toolchain as a side effect of a documentation step.

The deliverable is code. No model is trained, no large corpus is downloaded, and
no accuracy is claimed.

## Introduction

This is the first executable code CLAVE owns, so it sets conventions the rest of
the project inherits: where Python lives, how it is linted and typed, how tests
are laid out, and how the gate runs it.

Two properties matter more than features. Every artifact the platform touches
resolves by checksum, so that a corpus swapped upstream is detected rather than
silently trained on. And a run is reproducible, meaning the same seed and the
same configuration produce the same metrics within a stated tolerance, checked
by a test rather than asserted in prose.

The platform is deliberately framework-agnostic at its core. PyTorch is the
chosen framework and is declared as a dependency, but the manifest, the run
record, and the determinism machinery do not import it, so they can be tested
without a heavy install and so a later change of framework does not invalidate
them.

## Boundary Context

- **In scope**: the Python package layout and toolchain, the corpus manifest
  format and its checksum verification, the fetch tool, the run record, the
  seeding and determinism rules, the checker that enforces the research document
  table schemas, and the gate wiring that runs all of it.
- **Out of scope**: training anything, which is v0.7.0. Building a dataset,
  which is v0.6.0. Choosing model architectures, which v0.1.0 shortlisted and
  v0.4.0 selects from. Downloading a multi-gigabyte corpus, which is a network
  operation for an operator rather than part of a gate. Any GPU-specific code
  path, since no accelerator has been confirmed.
- **Adjacent expectations**: v0.1.0's shortlist supplies the framework and the
  corpora and is not revisited. `scripts/validate.sh` is the only gate, so
  anything this feature adds runs there and nowhere else. The house Python
  standards in `standards/guidelines/languages/py.md` are not negotiable here.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `TOOLCHAIN`, `MANIFEST`, `FETCH`, `RUN`, `REPRO`, and `CHECK`. Ids are
append-only.

## Requirements

### Requirement 1: Python toolchain

**Objective:** As anyone adding Python to this repository, I want the layout,
lint, type and test configuration fixed once, so that the second contributor
does not invent a second convention.

#### Acceptance Criteria

1. The Platform shall define a Python package under a `src/` layout with tests
   in a directory mirroring it, as the house standards require.
   `AC-TOOLCHAIN-01`
2. The Platform shall configure lint, type checking, and test running in one
   project file rather than in scattered tool configs. `AC-TOOLCHAIN-02`
3. When the gate runs, the Platform shall run lint, type checking, and tests,
   and shall fail the gate if any of them fails. `AC-TOOLCHAIN-03`
4. While no Python source exists, the gate shall skip the Python chain rather
   than failing, matching how it already treats the Rust chain.
   `AC-TOOLCHAIN-04`
5. The Platform shall gate line coverage at the floor the house standards set.
   `AC-TOOLCHAIN-05`

### Requirement 2: Corpus manifest

**Objective:** As the engineer who will build a training set, I want every corpus
artifact described by a committed manifest, so that two runs can be shown to have
seen the same bytes.

#### Acceptance Criteria

1. The Platform shall read a committed manifest describing each corpus artifact
   by name, source location, and expected digest. `AC-MANIFEST-01`
2. If a manifest entry has no recorded digest, then the Platform shall treat the
   entry as unverified rather than as trusted. `AC-MANIFEST-02`
3. If a manifest is malformed or names a duplicate artifact, then the Platform
   shall reject it with an error naming the offending entry. `AC-MANIFEST-03`
4. The Platform shall not require any corpus binary to be committed to the
   repository. `AC-MANIFEST-04`

### Requirement 3: Fetching and verification

**Objective:** As anyone reproducing a result, I want a fetch that refuses silently
changed data, so that an upstream swap is an error rather than a quiet difference
in my numbers.

#### Acceptance Criteria

1. When an artifact is already present locally, the Platform shall verify its
   digest against the manifest before reporting it as available.
   `AC-FETCH-01`
2. If a local artifact's digest does not match the manifest, then the Platform
   shall report a mismatch and shall not report the artifact as available.
   `AC-FETCH-02`
3. If an artifact's manifest entry is unverified, then the Platform shall refuse
   to report it as available unless the caller explicitly asks for the observed
   digest to be recorded. `AC-FETCH-03`
4. When the caller asks for a digest to be recorded, the Platform shall compute
   it from the local bytes and report it for review rather than writing it into
   the manifest silently. `AC-FETCH-04`

### Requirement 4: Run record

**Objective:** As anyone comparing two results, I want each run to carry what
produced it, so that a difference in numbers can be traced to a difference in
inputs.

#### Acceptance Criteria

1. When a run completes, the Platform shall record its seed, its configuration,
   the identity of the corpus artifacts it used, and the environment it ran in.
   `AC-RUN-01`
2. The Platform shall record a configuration by a digest of its contents, so
   that two runs with identical configuration are identifiable as such.
   `AC-RUN-02`
3. The Platform shall record the interpreter version and the versions of the
   declared dependencies present at run time. `AC-RUN-03`
4. When a run record is written, the Platform shall write it in a format a
   later tool can read without executing project code. `AC-RUN-04`
5. If a run is asked to record an artifact absent from the manifest, then the
   Platform shall reject the run rather than recording an unidentifiable input.
   `AC-RUN-05`

### Requirement 5: Reproducibility

**Objective:** As a reviewer of any number this project reports, I want
reproducibility defined numerically and tested, so that "reproducible" is a
measured property rather than a claim.

#### Acceptance Criteria

1. The Platform shall provide a single entry point that seeds every source of
   randomness it controls. `AC-REPRO-01`
2. When two runs use the same seed and the same configuration, the Platform
   shall produce metrics equal within a stated tolerance. `AC-REPRO-02`
3. The Platform shall state its tolerance as a number rather than as a
   description. `AC-REPRO-03`
4. When two runs use different seeds, the Platform shall not be required to
   produce equal metrics, and a test shall confirm the seed actually changes the
   result. `AC-REPRO-04`

### Requirement 6: Research document checker

**Objective:** As the maintainer of the research documents, I want the table
schemas enforced mechanically, so that a missing license cell fails the gate
instead of depending on a reviewer noticing.

#### Acceptance Criteria

1. The Platform shall verify that each research document table header matches
   its declared schema exactly. `AC-CHECK-01`
2. If any cell in a checked table is empty, then the Platform shall fail and
   name the row and column. `AC-CHECK-02`
3. The Platform shall verify that every verdict value is drawn from the closed
   vocabulary declared for that document. `AC-CHECK-03`
4. While a checked document is absent, the Platform shall skip its check rather
   than failing. `AC-CHECK-04`
