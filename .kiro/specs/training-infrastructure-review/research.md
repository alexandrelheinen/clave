# Research and Design Decisions

## Summary

- **Feature**: `training-infrastructure-review`
- **Discovery Scope**: New Feature, with integration-focused discovery against
  the sibling repositories rather than against a local codebase, since CLAVE
  holds no application code yet.
- **Key Findings**:
  - FRET already ships an artifact of exactly this kind,
    `docs/vision/algorithm-selection.md`, which screens detector options through
    a weighted criteria table and records a verdict per candidate. The family
    has a house pattern for this decision, so CLAVE adopts it rather than
    inventing a second one.
  - The failure this spec defends against is a candidate advancing with an
    unchecked license or an unchecked maintenance state, which shows up as a
    missing table cell. Enforcing that mechanically would require the whole
    Python toolchain, which v0.3.0 is scheduled to decide, so this spec fixes
    the structural contract and leaves enforcement to the step that owns the
    tooling.
  - Simulation is not a variable. FRET fixes the simulator, the two
    manipulators, and the scripted expert, which removes a large part of the
    search space before the survey begins and turns several otherwise
    attractive options into rejections on stated grounds.

## Research Log

### The family already has a selection-document pattern

- **Context**: Before designing a document structure, check whether a sibling
  project has solved the same problem, since `agents/claude.md` puts shared
  precedent above invention.
- **Sources Consulted**: `docs/vision/algorithm-selection.md`,
  `docs/vision/README.md`, and `docs/roadmap.md` in the FRET repository.
- **Findings**:
  - FRET's selection document carries a goal, a selection status naming the
    chosen option, a weighted evaluation-criteria table with stable ids
    (`C1` through `C6`), a candidates table with a status column, and an
    interface section describing the contract that survives a change of
    algorithm.
  - FRET states a numeric fixture gate alongside the criteria, so a candidate
    is measured rather than argued about.
  - FRET's vision README carries a "Locked product decisions" table, separating
    settled questions from open ones.
- **Implications**: CLAVE's review adopts the same skeleton. The criteria table
  with stable ids is what makes a rejection re-examinable later, which is what
  `AC-SCREEN-04` requires. The locked-decisions idea maps onto the screening
  constraints stated once before any verdict, which is `AC-SCREEN-01`.

### What the simulation constraint actually removes

- **Context**: `AC-SCREEN-02` and `AC-SCREEN-03` require every option to be
  judged against FRET's stack. The design needs to know how much that
  constrains, because a constraint that rejects nothing is decoration.
- **Sources Consulted**: FRET `docs/robots/open_manipulator_x.md`,
  `docs/robots/six_dof.md`, `third_party/README.md`, `.gitmodules`, and the MJCF
  scenes under `src/fret/mjcf/`.
- **Findings**:
  - The manipulators are the ROBOTIS OpenMANIPULATOR-X, four revolute joints
    plus a parallel gripper, and the OpenMANIPULATOR-Y, six revolute joints,
    both loaded from the `robotis_mujoco_menagerie` submodule.
  - Control runs through a robot-agnostic `PickPlaceFSM` into ARCO's
    `JointSpaceMPC`, and grasping uses physics pad contact with adhesion rather
    than a kinematic carry.
  - FRET's asset policy keeps large mesh sources as pinned submodules and
    converts them into MuJoCo-friendly form through import scripts, rather than
    vendoring copies.
- **Implications**: A policy architecture that assumes a parallel-jaw force
  controller, a tactile sensor, or a mobile base has no counterpart here and is
  rejected on `AC-SCREEN-02` grounds. A policy that needs teleoperated human
  demonstrations rather than scripted ones fails `AC-SCREEN-03`, because the
  only expert available is `PickPlaceFSM`. Recording these as rejections with a
  named constraint is more useful than omitting the options.

### Corpus and asset candidates that exist today

- **Context**: `AC-CORPUS-01` requires at least four corpora including one
  captured on an operating line. The design needs confidence that the floor is
  reachable before setting it.
- **Sources Consulted**: The ZeroWaste dataset paper, the
  `AgaMiko/waste-datasets-review` index, and the `kevinzakka/mujoco_scanned_objects`
  repository, all recorded in `.kiro/steering/roadmap.md` under candidate inputs.
- **Findings**:
  - ZeroWaste is conveyor imagery from a full-scale recovery facility, which is
    the only shortlisted corpus whose capture conditions match CLAVE's scene.
  - TACO and TrashNet differ from CLAVE's scene in background and clutter, which
    is a difference the review has to state rather than gloss.
  - `mujoco_scanned_objects` supplies ready MJCF models of household items under
    CC-BY 4.0 meshes with MIT XML. This is a mesh source rather than a
    perception corpus, and it has neither an annotation type nor capture
    conditions to record.
- **Implications**: The floor of four corpora is reachable. Mesh sources do not
  fit the corpus schema and no approved requirement covers them, so they move
  out of boundary and are surveyed at v0.5.0 next to the world that consumes
  them.

### Enforcing completeness without a heavyweight pipeline

- **Context**: The requirements state that verification is document review, and
  leave to design the question of whether a script enforces always-present
  fields.
- **Sources Consulted**: `scripts/validate.sh`, `scripts/setup.sh`,
  `standards/guidelines/languages/sh.md`, `standards/guidelines/languages/py.md`,
  and `.github/workflows/ci.yml` in this repository.
- **Findings**:
  - `validate.sh` is the single gate, CI runs it as its only step, and it
    already skips the Rust chain until a `Cargo.toml` exists, so conditional
    steps are an established shape in that script.
  - The repository has no Python tooling yet, and no Rust workspace either, so
    any checker is the first executable artifact CLAVE owns.
  - `standards/guidelines/languages/py.md` mandates a `src/` layout, `ruff`,
    `mypy --strict`, `pytest` with mirrored tests, and a coverage gate of 80 to
    90 percent. A checker written in Python is therefore not one file; it is the
    whole Python toolchain plus its wiring into the gate.
- **Implications**: Mechanical enforcement is worth having, but standing up the
  Python toolchain is scheduled at v0.3.0 as part of `learning-platform`. A
  documentation step should not settle that question early and by side effect.
  This spec instead fixes the format contract that makes enforcement cheap when
  it lands, meaning exact table headers, stable criterion ids, and a closed
  verdict vocabulary.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks and Limitations | Notes |
|---|---|---|---|---|
| Single review document | One file under `docs/research/` carrying constraints, tables, and shortlist | Shortlist sits next to the evidence behind it; no cross-file drift | Long file | Selected |
| Document set with index | An index plus one file per survey domain | Each domain readable alone | Verdicts drift from evidence across files; an index invites a reader to stop at it | Rejected |
| Machine-readable register plus rendered prose | Candidates in YAML, document generated from it | Strongest guarantee of structural validity | Needs a generator and a rendering step for a one-off document | Rejected as speculative machinery |
| Prose review with no structural rules | Conventional literature review | Cheapest to write | The exact defect this spec exists to prevent, a candidate advancing without a recorded license, becomes invisible | Rejected |

## Design Decisions

### Decision: Adopt FRET's selection-document skeleton

- **Context**: The review needs a structure that makes verdicts re-examinable.
- **Alternatives Considered**:
  1. Invent a structure fitted to CLAVE's three survey domains.
  2. Adopt the skeleton FRET already uses for `algorithm-selection.md`.
- **Selected Approach**: Adopt FRET's skeleton, meaning a goal, screening
  constraints stated once, a weighted criteria table with stable ids, candidate
  tables carrying a verdict column, and a shortlist.
- **Rationale**: A reader who has read one selection document in this family can
  read the other without relearning the form, and the stable criterion ids are
  precisely the mechanism `AC-SCREEN-04` needs so that a later change to a
  constraint identifies which rejections to revisit.
- **Trade-offs**: CLAVE inherits a shape designed for one decision and applies
  it to three survey domains, so the criteria table is per domain rather than
  global.
- **Follow-up**: Confirm during implementation that per-domain criteria tables
  stay readable and do not drift into three unrelated rubrics.

### Decision: Fix the format contract now, defer mechanical enforcement to v0.3.0

- **Context**: Twelve of the thirty-two criteria assert that a field is always
  present. Reviewer attention is the weakest possible enforcement for that class
  of claim, so mechanical checking is attractive.
- **Alternatives Considered**:
  1. Reviewer diligence alone, with no structural rules.
  2. A Python checker wired into `scripts/validate.sh` as part of this spec.
  3. A structural contract specified now, enforced when the toolchain exists.
- **Selected Approach**: The third. This spec fixes exact table headers, stable
  criterion ids, and a closed verdict vocabulary, so that a checker written
  later needs no change to the document. Enforcement lands with the Python
  toolchain at v0.3.0.
- **Rationale**: `py.md` requires a `src/` layout, `ruff`, `mypy --strict`,
  `pytest`, and a coverage gate. Writing a checker here would settle CLAVE's
  Python toolchain as a side effect of a documentation step, which is the
  decision `learning-platform` is scheduled to make deliberately. The structural
  contract captures most of the value at none of that cost, because a table with
  a declared header and a closed vocabulary is already far easier to review by
  eye than free prose.
- **Trade-offs**: Between this step and v0.3.0, a missing license cell is caught
  by a human or not at all. The review is a single document reviewed once, so
  the exposure is bounded.
- **Follow-up**: `learning-platform` inherits an explicit obligation to enforce
  this contract. Recorded as a revalidation trigger in `design.md`.

### Decision: Defer simulated mesh sources to v0.5.0

- **Context**: The roadmap lists simulated object meshes among the candidate
  inputs for this step, but no approved requirement covers them. `AC-CORPUS-02`
  asks for annotation type and capture conditions, neither of which a 3D mesh
  set has, so meshes do not fit the corpus schema either.
- **Alternatives Considered**:
  1. Add a second table with a mesh-specific schema, expanding scope past the
     approved requirements.
  2. Return to the requirements phase and add a mesh requirement.
  3. Place mesh sources out of boundary and leave them to `sorting-world`.
- **Selected Approach**: The third. Mesh sources are surveyed at v0.5.0, where
  the world that consumes them is built.
- **Rationale**: Design must not invent requirements. The survey is also better
  placed next to its consumer, since whether a mesh set is usable depends on the
  scene being assembled and on the material taxonomy that v0.2.0 settles, and
  neither exists yet.
- **Trade-offs**: The roadmap's candidate table for v0.1.0 mentions meshes, so
  the roadmap and this spec disagree until one is amended. Recorded as an open
  question for the maintainer rather than resolved unilaterally.
- **Follow-up**: Either amend the roadmap entry or accept the divergence
  explicitly.

### Decision: Record the compute budget as unresolved rather than assume hardware

- **Context**: `AC-COMPUTE-04` anticipates that the hardware inventory may not
  be available when the review is written.
- **Alternatives Considered**:
  1. Block the review until the maintainer supplies the inventory.
  2. Assume a common accelerator and note the assumption.
  3. Record the budget as unresolved and let the rest of the review proceed.
- **Selected Approach**: The third. The budget section carries an explicit
  unresolved state that the checker recognizes, and any verdict that depends on
  the budget is recorded as provisional until it resolves.
- **Rationale**: Blocking wastes the survey work, which does not depend on the
  hardware. Assuming a machine is the fabrication `AC-DOC-04` forbids.
- **Trade-offs**: The shortlist may carry provisional entries, so the reader has
  to be told which ones and why.
- **Follow-up**: Resolving the budget is a maintainer input, tracked as an open
  question rather than a task an agent can close.

## Risks and Mitigations

- The review becomes a literature summary that describes without deciding.
  Mitigated by `AC-SCREEN-05` and by a verdict column the checker requires to be
  populated from a fixed vocabulary.
- Claims about third-party projects expire silently. Mitigated by `AC-DOC-03`,
  which dates any claim expected to change, matching the rule in
  `agents/writing.md` that a claim about something outside the project carries
  a date.
- A required field is left blank and no gate catches it before v0.3.0.
  Mitigated only partially, by declaring exact headers and a closed verdict
  vocabulary so a gap is visible to a reader rather than buried in prose. This
  is an accepted residual risk, not a solved one.
- The survey is performed by an agent and reports results it did not verify.
  Mitigated by `AC-DOC-02` and `AC-DOC-04`, which require attribution and forbid
  presenting an unreproduced result as the project's own.

## References

- [FRET algorithm-selection.md](https://github.com/alexandrelheinen/fret/blob/main/docs/vision/algorithm-selection.md), the house pattern this design adopts.
- [ZeroWaste dataset](https://openreview.net/pdf?id=DAkP1TT_Ubm), conveyor imagery from an operating recovery facility.
- [waste-datasets-review](https://github.com/AgaMiko/waste-datasets-review), an index of litter and waste image datasets.
- [mujoco_scanned_objects](https://github.com/kevinzakka/mujoco_scanned_objects), MJCF models of Google Scanned Objects.
- [.kiro/steering/roadmap.md](../../steering/roadmap.md), the ladder this review opens and the candidate inputs it starts from.
