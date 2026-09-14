# Implementation Plan

## Note on task type

`rules/tasks-generation.md` excludes documentation tasks from a task plan. That
rule targets padding, meaning a README task listed beside real implementation.
Here the document is the deliverable: `design.md` commits this spec to exactly
one artifact, `docs/research/training-infrastructure-review.md`, and no code.
Applying the rule literally would produce an empty plan. The tasks below are
therefore authoring tasks, and the deviation is deliberate.

## Note on parallelism

No task carries `(P)`. Every task writes into the same file, which is shared
mutable state under the parallel-safety rules, so concurrent execution would
conflict regardless of how separate the subject matter looks. Tasks 2.1 through
2.5 are independent in content and their research can be gathered concurrently,
but their results must be written into the registers one at a time.
`_Boundary:_` is recorded anyway, because ownership of a table cell is what
keeps the survey tasks from overwriting the screening task.

- [ ] 1. Foundation: fix the method and open the longest-lead request

- [ ] 1.1 Create the review skeleton and state the screening constraints
  - Create `docs/research/training-infrastructure-review.md` with the section
    order fixed in the design: screening constraints, criteria tables, compute
    budget, shortlist, candidate registers, open questions.
  - State constraints `S1` through `S4` once, before any other section, with the
    wording from the design.
  - Record that `S3` applies only to pick-policy architectures and that other
    rows record it as not applicable.
  - Leave every other section present but empty, including open questions, so
    later tasks have a place to write into.
  - Observable: the file exists at the required path, its first substantive
    section is the four constraints, every later section heading is present, and
    it contains no candidate rows yet.
  - _Requirements: 5.1, 5.2, 5.3, 7.1_
  - _Boundary: Screening constraints_

- [ ] 1.2 Request the hardware inventory from the maintainer
  - Ask for accelerator model, memory, and whether access is continuous or
    shared, which is the input `AC-COMPUTE-01` needs and no agent can observe.
  - Ask before any survey work, because this is the only input with an external
    lead time and the survey can proceed while it is outstanding.
  - Record the request and the date it was made in the open questions section
    created by 1.1, so an unanswered request stays visible.
  - Observable: the open questions section names the outstanding request and its
    date, and no later task is blocked waiting on the answer.
  - _Requirements: 4.1_
  - _Boundary: Open questions_

- [ ] 1.3 Declare the register schemas and the verdict vocabulary
  - Write the three register headers exactly as the design specifies, in the
    declared column order, with no rows beneath them.
  - State the closed verdict vocabulary and the meaning of each term, including
    why `Baseline` and `Advance (provisional)` exist.
  - State that no cell may be blank, that absence is written as a dash or `n/a`,
    and that the verdict and failed-constraint cells are owned by the screening
    task rather than by the survey tasks.
  - Observable: all three header rows are present, and a reader can tell which
    cells are mandatory and which task fills each one without reading the spec.
  - _Requirements: 1.2, 2.2_
  - _Boundary: Register schemas_

- [ ] 1.4 Declare the per-domain criteria tables
  - Write one weighted criteria table per survey domain with stable ids
    `C-CORPUS-n`, `C-ARCH-n`, `C-INFRA-n` and weights of High, Medium, or Low.
  - State in one sentence how a criterion differs from a constraint, so a reader
    does not confuse a comparative score with a pass-fail rule.
  - Include only criteria the shortlist will actually cite when ordering
    survivors, since the design treats an uncited criteria table as decoration.
  - Observable: each survey domain has a criteria table whose ids are stable
    enough for the shortlist to cite in task 3.3.
  - _Requirements: 3.3_
  - _Boundary: Criteria tables_

- [ ] 2. Core: populate the registers with surveyed facts

- [ ] 2.1 Populate the corpus register
  - Survey at least four waste perception corpora, including at least one whose
    imagery comes from an operating sorting line.
  - Fill every declared column except the verdict and failed-constraint cells,
    including how each corpus differs from a conveyor viewed by a fixed overhead
    camera.
  - Keep a corpus that cannot be retrieved from a working public source as a row,
    cite the reference that documents it such as its paper or index entry, and
    record the failed retrieval as a dated note beneath the register, so the
    source still resolves and screening can verdict the row `Unavailable`.
  - Observable: the register holds at least four rows, every cell except the two
    screening-owned ones is filled, and at least one row records operating-line
    capture conditions.
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 7.2_
  - _Boundary: Corpus register_

- [ ] 2.2 Populate the architecture register for the perception stage
  - Survey open-source perception architectures, recording license, most recent
    upstream release or commit, and whether usable pretrained weights exist.
  - Record the published result each author claims and the task it was measured
    on, with a citation covering both.
  - Record an estimated training cost per row, as wall-clock time on the stated
    hardware, or `pending budget` while the inventory is outstanding.
  - Include at least one deliberately simple comparator among the candidates, so
    screening has something to verdict `Baseline`.
  - Record `n/a` in the training-signal column, which applies to the policy
    stage only.
  - Observable: at least four perception rows exist, giving the three-advancing
    floor headroom before screening, and every cell except the two
    screening-owned ones is filled with a citation that resolves.
  - _Requirements: 2.2, 2.4, 2.5, 7.2_
  - _Boundary: Architecture register_

- [ ] 2.3 Populate the architecture register for the policy stage
  - Survey open-source pick-policy architectures under the same schema.
  - State for each what training signal it needs, distinguishing demonstrations
    from reward, since the data pipeline at v0.6.0 has to produce it.
  - Record an estimated training cost per row on the same basis as 2.2.
  - Include at least one deliberately simple comparator among the candidates.
  - Observable: at least four policy rows exist, each training-signal cell names
    demonstrations, reward, or both, and every cell except the two
    screening-owned ones is filled.
  - _Requirements: 2.2, 2.3, 2.4, 2.5, 7.2_
  - _Boundary: Architecture register_

- [ ] 2.4 Populate the infrastructure register for deep learning frameworks
  - Survey the deep learning frameworks the surveyed architectures require,
    recording license and purpose.
  - State for each whether it runs against FRET's existing MuJoCo stack without
    forking it.
  - Where two frameworks serve the same purpose, name the competing option and
    state the tradeoff in one clause a later reader can act on.
  - Record what each needs for reproducibility, covering seed control and
    environment pinning.
  - Observable: every framework row is complete except the screening-owned
    cells, and no two frameworks serving the same purpose lack a stated tradeoff.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.2_
  - _Boundary: Infrastructure register_

- [ ] 2.5 Populate the infrastructure register for simulation execution and experiment interfaces
  - Survey the simulation execution options and the environment or experiment
    interfaces the surveyed architectures require, under the same schema.
  - State for each whether it runs against FRET's existing MuJoCo stack without
    forking it, which is the constraint most likely to reject an option here.
  - Name the competing option and the tradeoff wherever two serve the same
    purpose, and record reproducibility requirements per row.
  - Observable: every execution and interface row is complete except the
    screening-owned cells, and the register now covers all three option classes
    required by 3.1.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.2_
  - _Boundary: Infrastructure register_

- [ ] 3. Integration: budget, verdicts, and the shortlist

- [ ] 3.1 State the compute budget
  - If the inventory requested in 1.1 has arrived, name accelerator model,
    memory, and whether access is continuous or shared, and convert every
    `pending budget` cell into wall-clock time with its governing assumption
    named.
  - If it has not arrived, declare the section unresolved on its first line and
    record that no candidate may be rejected under `S4` while it stays
    unresolved.
  - This is an explicit integration task: converting `pending budget` writes into
    the architecture register, which 2.2 and 2.3 otherwise own, so the crossing
    is declared rather than hidden inside a local edit.
  - Observable: the budget section declares resolved or unresolved in its first
    line, and no architecture row still reads `pending budget` once it is
    resolved.
  - _Requirements: 4.1, 4.2, 4.4_
  - _Boundary: Compute budget, Estimated training cost column of the architecture register_
  - _Depends: 1.2, 2.2, 2.3_

- [ ] 3.2 Apply the screening constraints and record a verdict per row
  - Judge every row in all three registers against `S1` through `S4`, applying
    the same constraints to every option.
  - Fill the verdict and failed-constraint cells, which this task alone owns,
    using only the closed vocabulary, and populate the failed-constraint cell
    exactly when the verdict is `Reject`.
  - Verdict `Unavailable` for a row whose source cell records a failed
    retrieval, and `Baseline` for the simple comparators placed in 2.2 and 2.3.
  - Reject a corpus whose license forbids CLAVE's intended use, citing the
    clause, and reject an architecture whose estimated training cost exceeds the
    budget regardless of its published results.
  - Mark an otherwise advancing architecture `Advance (provisional)` while the
    budget is unresolved.
  - Observable: no row lacks a verdict, no `Reject` lacks a constraint id, and no
    `Reject` cites `S4` while the budget is unresolved.
  - _Requirements: 1.4, 2.1, 4.3, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: Verdict and failed-constraint cells across all registers_
  - _Depends: 2.1, 2.5, 3.1_

- [ ] 3.3 Produce the shortlist grouped by consuming step
  - Group advancing entries under the step that consumes them, meaning
    infrastructure and corpora for v0.3.0 and architectures for v0.4.0.
  - Order entries within each group by the criteria tables from 1.4, and name
    the criterion that decided any close call.
  - State each entry's reason in terms of the screening constraints rather than
    as praise.
  - If either stage has fewer than three advancing architectures, state that the
    roadmap target is unmet and name what would have to change, which is a valid
    outcome rather than a defect to repair.
  - Observable: a reader starting v0.3.0 or v0.4.0 can act on the shortlist
    without reading the registers below it, and every criteria table declared in
    1.4 is cited at least once.
  - _Requirements: 2.1, 6.1, 6.2, 6.3_
  - _Boundary: Shortlist_
  - _Depends: 3.2_

- [ ] 3.4 Complete the open questions section
  - Add what the review could not determine to the section opened in 1.1,
    including the compute budget if it stayed unresolved and the mesh-source
    divergence from the roadmap.
  - State for each open question who can close it and what would close it.
  - Observable: every question the review left open is visible in one section
    rather than implied by an omission elsewhere.
  - _Requirements: 6.4_
  - _Boundary: Open questions_
  - _Depends: 3.1, 3.3_

- [ ] 4. Validation

- [ ] 4.1 Run the structural checks and report failures to their owning section
  - Verify each register header matches the declared schema exactly, that no cell
    anywhere is blank, and that every architecture row carries an estimated
    training cost.
  - Verify every verdict is in the closed vocabulary, that failed-constraint
    cells are populated exactly for rejections, and that the budget section
    declares its state on its first line with no `S4` rejection outstanding
    against an unresolved budget.
  - Verify the corpus floor of four rows and the per-stage architecture floor of
    three advancing entries. A floor that is not met is reported as an unmet
    target for 3.3 to declare, not repaired by adding candidates here.
  - Report any failure to the task that owns the section rather than editing it,
    since validation does not own registers, the budget, or the shortlist.
  - Observable: all nine structural checks in the design have been run and their
    results recorded, with any failure attributed to its owning task.
  - _Requirements: 1.1, 2.1, 2.5, 4.4_
  - _Boundary: Validation_
  - _Depends: 3.3, 3.4_

- [ ] 4.2 Run the four content checks
  - Verify every rejection names a constraint that actually explains it, rather
    than one chosen to justify a preference formed first.
  - Verify every advancing entry's reason is stated in constraint terms rather
    than as praise, which is what separates a screening from an endorsement.
  - Verify every dated claim is one that can expire and every claim that can
    expire is dated, and that every external fact carries a resolving citation.
  - Verify the shortlist is actionable without reading the surveys, by reading it
    alone and checking that no entry needs the register to be understood.
  - Verify no estimate, unmeasured number, or unreproduced result is presented as
    CLAVE's own.
  - Observable: all four content checks in the design have been run and their
    results recorded, and the review reports only what its cited sources report.
  - _Requirements: 5.5, 7.2, 7.3, 7.4, 7.5_
  - _Boundary: Validation_
  - _Depends: 4.1_

- [ ] 4.3 Repair the reported defects and re-run the checks
  - Repair every defect 4.1 and 4.2 attributed to an owning section, editing that
    section under the rules the owning task worked to.
  - Leave an unmet candidate floor unrepaired, since 6.3 makes declaring it the
    correct outcome, and confirm the shortlist declares it.
  - Re-run the structural and content checks after repair, and repeat until they
    report no defect other than a declared unmet floor.
  - This is an explicit integration task: it edits registers, the budget, and the
    shortlist, which the 2.x and 3.x tasks own, so the crossing is declared
    rather than smuggled into validation.
  - Observable: the checks report no outstanding defect, and the document is in
    the state the spec describes rather than merely inspected.
  - _Requirements: 6.3_
  - _Boundary: Every section, as an explicit remediation pass_
  - _Depends: 4.1, 4.2_
