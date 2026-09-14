# Implementation Plan

## Note on task type

As in `training-infrastructure-review`, the sole deliverable is a Markdown
document and the design commits to no code, so these are authoring tasks. The
task rules exclude documentation tasks to prevent padding; applying that
literally here produces an empty plan. The deviation is deliberate.

## Note on parallelism

No task carries `(P)`. Every task writes into `docs/waste-taxonomy.md`, which is
shared mutable state under the parallel-safety rules. The three corpus mappings
are independent in content and can be researched concurrently, but they are
written one at a time. `_Boundary:_` is recorded so ownership of a table is
unambiguous.

- [ ] 1. Foundation: fix the vocabulary everything else references

- [ ] 1.1 Create the skeleton and the material class table
  - Create `docs/waste-taxonomy.md` with the six sections in the design order:
    classes, objects, channels, corpus mappings, stability rules, open questions.
  - Write the class table with the exact declared header, one row per material
    class, each carrying its definition, the property that distinguishes it, and
    the mechanism a recovery facility uses to separate it.
  - Include exactly one residue class for material that is not recyclable in
    this stream, and mark exactly one channel as the reject destination.
  - Where two classes cannot be told apart from a single overhead color image,
    say so in the distinguishing-property cell and state whether they are merged
    or kept separate.
  - Cite a source for every separation-mechanism claim, and hedge any claim that
    varies by region or operator rather than presenting it as universal.
  - Observable: the class table is complete with no blank cells, exactly one
    residue row exists, and every mechanism claim carries a citation.
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 3.1, 3.3, 5.1, 5.2, 5.3_
  - _Boundary: Class table_

- [ ] 1.2 Declare the identifier scheme and the stability rules
  - State that class identifiers take the form `M-<NN>`, are assigned in order,
    and are never reused, so a retired class keeps its number.
  - Write the stability section naming which decisions a consumer may depend on
    and which are safe to change, with class ids and the residue class
    load-bearing and display names not.
  - Name the pick decision contract as the consumer a rename would break.
  - Observable: a reader can tell, for any element of the taxonomy, whether
    changing it breaks a downstream consumer.
  - _Requirements: 1.3, 5.4_
  - _Boundary: Identifier scheme, Stability rules_

- [ ] 2. Core: the lookups that make the vocabulary usable

- [ ] 2.1 Write the object to class lookup
  - Map at least fifteen everyday container objects onto class ids, covering at
    minimum bottles, cans, boxes, tubs, cartons, and bags.
  - Cite for each assignment the practice or standard that justifies it.
  - Record an object whose material cannot be judged from appearance alone as
    ambiguous, naming what would resolve it.
  - For a multi-material object, put the governing material in the class cell
    and the rest in the ambiguity cell.
  - Observable: at least fifteen rows exist with no blank cells, all six
    container kinds appear, and every class id referenced exists in the class
    table.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: Object lookup_

- [ ] 2.2 Write the channel policy
  - State that every class routes to a channel and that the class-to-channel
    mapping is configuration supplied per deployment rather than a constant.
  - Define the single reject channel and state that it receives anything the
    system cannot route with confidence, without fixing a numeric threshold,
    which belongs to v0.8.0.
  - State that a channel may be shared by several classes, which is how a
    deployment with fewer channels than classes is expressed.
  - State what happens to an object not picked before it leaves the reachable
    window, and what that means for the line.
  - Observable: no object on the belt has an undefined destination under the
    four rules, including the unpicked case.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Boundary: Channel policy_

- [ ] 2.3 Map the SpectralWaste label set
  - Write one row per SpectralWaste label with its target class ids or
    `unmapped`, and state in the loss cell what the mapping discards.
  - State what SpectralWaste labels instead of material, since it labels object
    kinds such as film and trash bags, and whether material is recoverable from
    those labels.
  - State which classes SpectralWaste supplies no training signal for.
  - Observable: every SpectralWaste label appears, and the two closing
    statements are present.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: Corpus mappings_

- [ ] 2.4 Map the TACO label set
  - Write the TACO mapping under the same schema, recording a label that spans
    more than one class with all of them rather than picking one.
  - State which classes TACO supplies no training signal for.
  - Observable: every TACO label appears with a target or `unmapped`, and the
    supplies-no-signal statement is present.
  - _Requirements: 4.1, 4.2, 4.4, 4.5_
  - _Boundary: Corpus mappings_

- [ ] 2.5 Map the TrashNet label set
  - Write the TrashNet mapping under the same schema.
  - State that TrashNet labels whole images rather than objects, and what that
    costs a consumer expecting localization.
  - State which classes TrashNet supplies no training signal for.
  - Observable: all six TrashNet labels appear, and the two closing statements
    are present.
  - _Requirements: 4.1, 4.2, 4.3, 4.5_
  - _Boundary: Corpus mappings_

- [ ] 3. Integration

- [ ] 3.1 Cross-check references and write the open questions
  - Verify every class id referenced by the object lookup and the corpus
    mappings exists in the class table, and that no id is used twice.
  - Write the open questions section, naming who can close each and what closing
    it requires, including that no sorting line was observed and that ZeroWaste
    stays unmapped pending the license decision.
  - State plainly that the class list is derived from published practice and is
    a proposal until checked against a real facility.
  - Observable: no dangling class reference exists, and the document nowhere
    claims validation against a line.
  - _Requirements: 5.5_
  - _Boundary: Open questions, cross-reference integrity_
  - _Depends: 2.1, 2.3, 2.4, 2.5_

- [ ] 4. Validation

- [ ] 4.1 Run the structural checks and report failures to their owning section
  - Verify the class table header matches the schema exactly, that no cell in
    any table is blank, and that every id matches `M-<NN>` with no duplicates.
  - Verify exactly one residue class and exactly one reject channel exist, and
    that every class id referenced elsewhere resolves.
  - Verify the object lookup meets its row and coverage floors, and that one
    mapping table exists per shortlisted corpus with both closing statements.
  - Report any failure to the task that owns the section rather than editing it.
  - Observable: all seven structural checks in the design have been run and
    their results recorded, with any failure attributed to its owning task.
  - _Requirements: 1.1, 2.1, 4.1_
  - _Boundary: Validation_
  - _Depends: 3.1_

- [ ] 4.2 Run the content checks
  - Verify every separation mechanism names something a facility physically
    does, and that a class with no mechanism is flagged rather than assigned one
    to fill the cell.
  - Verify every object assignment cites a basis that actually supports it, and
    that every claim varying by region or operator is hedged.
  - Verify no number is presented as measured and nothing claims a line was
    observed.
  - Observable: all four content checks in the design have been run and their
    results recorded.
  - _Requirements: 5.2, 5.3, 5.5_
  - _Boundary: Validation_
  - _Depends: 4.1_

- [ ] 4.3 Repair the reported defects and re-run the checks
  - Repair every defect 4.1 and 4.2 attributed to an owning section, editing
    that section under the rules its owning task worked to.
  - Re-run both check sets after repair and repeat until they report nothing
    outstanding.
  - This is an explicit integration task: it edits tables owned by the 1.x and
    2.x tasks, so the crossing is declared rather than hidden in validation.
  - Observable: the checks report no outstanding defect, and the document is in
    the state the spec describes rather than merely inspected.
  - _Requirements: 5.4_
  - _Boundary: Every section, as an explicit remediation pass_
  - _Depends: 4.1, 4.2_
