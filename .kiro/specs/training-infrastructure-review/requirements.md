# Requirements Document

## Project Description (Input)
CLAVE plans to learn a perception and pick policy, and has committed to nine
minor versions that get it there, but nobody has yet established what the field
already offers. The roadmap at `.kiro/steering/roadmap.md` schedules this
review as v0.1.0 precisely because every step after it spends real effort on a
choice made here: v0.3.0 picks a deep learning framework and a corpus store,
v0.4.0 puts at least three architectures per learned stage behind one
interface, and v0.5.0 through v0.7.0 build the world and the training runs that
those choices determine. Choosing any of them from memory or reputation would
commit the project to months of work on an unexamined assumption.

The people who carry that risk are the ones who will implement the later steps,
which for this repository means a maintainer working with agents. An agent asked
to "pick a detector" with nothing written down will pick whatever is most
frequently mentioned in its training data, which is a popularity measure rather
than a fit measure, and it will not notice that a license forbids the use or
that the project was last touched three years ago.

This feature produces the document that removes that failure mode. It surveys
waste perception corpora, candidate open-source architectures for perception and
for the pick policy, and the training infrastructure needed to run them, then
states which options advance and which do not, with the reason attached to each.
Every candidate carries its license, a maintenance signal, and an explicit
verdict against CLAVE's constraints. The review also states the compute budget,
meaning what hardware is actually available and what one training run on it is
expected to cost, because an architecture that cannot be trained on the hardware
at hand is not a candidate regardless of its published numbers.

Simulation is not an open question and the review treats it as fixed. CLAVE
reuses FRET's MuJoCo physics SITL, the ROBOTIS OpenMANIPULATOR-X with four
revolute joints and a parallel gripper, the OpenMANIPULATOR-Y with six revolute
joints, both loaded from the `robotis_mujoco_menagerie` submodule, and FRET's
robot-agnostic `PickPlaceFSM` as the scripted expert that imitation learning
will record demonstrations from. A candidate that cannot work inside those
constraints is rejected on those grounds, and the rejection is written down
rather than left implicit.

The deliverable is a document under `docs/research/`. No model is trained, no
corpus is downloaded, and no code lands. The review ends with a shortlist that
v0.3.0 and v0.4.0 consume directly, so that the next two steps start from a
decision with a recorded reason rather than from a blank page.

## Introduction

This feature delivers the bibliographic review that opens CLAVE's road to
v1.0.0. It answers three questions the later steps cannot answer for
themselves: which waste perception corpora exist and which are usable, which
open-source architectures are worth putting behind CLAVE's interfaces, and what
infrastructure training them actually requires.

The review is a screening instrument rather than a literature summary. Its
value comes from the verdicts, meaning the list of what advances and the
recorded reason each rejected option did not, so that a later reader can tell
whether a rejection still holds when circumstances change. A survey that
describes ten options without choosing between them would leave v0.3.0 and
v0.4.0 exactly where they started.

Two constraints shape every verdict. Simulation is fixed to FRET's stack and
its ROBOTIS arms, so an architecture that assumes a different simulator, a
different robot, or a data modality CLAVE cannot produce is out regardless of
its published results. And the compute available to this project is finite, so
an approach whose training cost exceeds it is out even when it is technically
the strongest. Both constraints are stated in the document rather than applied
silently.

## Boundary Context

- **In scope**: the survey of corpora, architectures, and training
  infrastructure; the screening of every surveyed option against CLAVE's
  constraints; the compute budget and the hardware it assumes; the shortlist
  that v0.3.0 and v0.4.0 consume; and the review document itself, published
  under `docs/research/`.
- **Out of scope**: downloading or redistributing any corpus, training or
  evaluating any model, writing any code, and selecting the single architecture
  CLAVE will ship, which v0.4.0 decides from this shortlist. The material
  taxonomy and the sorting doctrine belong to v0.2.0 and are not settled here.
  Benchmark numbers produced by CLAVE do not exist yet and the review reports
  only what its sources report.
- **Adjacent expectations**: FRET supplies the simulator, the manipulators, and
  the scripted expert, and is not expected to change to accommodate a candidate.
  The maintainer supplies the hardware inventory the compute budget is computed
  against, since no agent can observe what machines this project may use. A
  reader of the shortlist is expected to consult the recorded reason before
  reopening a rejected option.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the scheme
`pick-decision-contract` established, with areas `CORPUS`, `ARCH`, `INFRA`,
`COMPUTE`, `SCREEN`, `SHORTLIST`, and `DOC`. Ids are append-only: a criterion
that is removed leaves its number retired rather than reused, so a reference in
an old commit never resolves to different text.

Verification for this feature is document review rather than a compiled test
suite, because the deliverable is prose and tables. Every criterion below is
written so that a reviewer can check it by reading the document and reach the
same verdict as any other reviewer. Where a criterion asserts that a field is
always present, the design phase decides whether a script enforces it.

## Requirements

### Requirement 1: Waste perception corpus survey

**Objective:** As the engineer who will build CLAVE's data pipeline, I want every
candidate corpus described in comparable terms, so that I can tell which ones
match a conveyor sorting line before spending effort fetching them.

#### Acceptance Criteria

1. The Review shall survey at least four waste perception corpora, including at
   least one whose imagery was captured on an operating sorting line. `AC-CORPUS-01`
2. When the Review names a corpus, the Review shall record its license, its
   approximate size, its annotation type, and the conditions its imagery was
   captured under. `AC-CORPUS-02`
3. When the Review records a corpus, the Review shall state how its imagery
   differs from a conveyor belt viewed by a fixed overhead camera. `AC-CORPUS-03`
4. If a corpus carries a license that forbids the use CLAVE intends, then the
   Review shall reject it and record the license clause as the reason. `AC-CORPUS-04`
5. If a corpus cannot be retrieved from a working public source, then the Review
   shall record it as unavailable rather than listing it as a candidate. `AC-CORPUS-05`

### Requirement 2: Candidate architecture survey

**Objective:** As the engineer who will implement the model interface at v0.4.0, I
want at least three viable open-source architectures for each learned stage, so
that the interface is designed against real alternatives rather than one
assumed winner.

#### Acceptance Criteria

1. The Review shall identify at least three open-source perception architectures
   and at least three open-source pick-policy architectures that pass screening.
   `AC-ARCH-01`
2. When the Review names an architecture, the Review shall record its license,
   the date of its most recent upstream release or commit, and whether
   pretrained weights are published under a license CLAVE can use. `AC-ARCH-02`
3. When the Review names a pick-policy architecture, the Review shall state what
   training signal it requires, distinguishing demonstrations from reward, so
   that the data pipeline at v0.6.0 knows what it has to produce. `AC-ARCH-03`
4. When the Review names an architecture, the Review shall record the published
   result its authors claim and the task that result was measured on, and shall
   attribute both to a citation. `AC-ARCH-04`
5. The Review shall include at least one deliberately simple baseline per stage,
   so that a later benchmark can show what the sophisticated options are worth.
   `AC-ARCH-05`

### Requirement 3: Training infrastructure survey

**Objective:** As the engineer who will stand up the learning platform at v0.3.0,
I want the infrastructure options named and judged against FRET's stack, so that
the platform is chosen for fit rather than familiarity.

#### Acceptance Criteria

1. The Review shall survey the deep learning frameworks, the simulation
   execution options, and the environment and experiment interfaces that the
   surveyed architectures require. `AC-INFRA-01`
2. When the Review names an infrastructure option, the Review shall state
   whether it runs against FRET's existing MuJoCo stack without forking it.
   `AC-INFRA-02`
3. When two infrastructure options serve the same purpose, the Review shall
   state the tradeoff between them in terms a later reader can act on, rather
   than presenting them as equivalent. `AC-INFRA-03`
4. The Review shall state what each option requires for reproducibility,
   covering seed control and environment pinning. `AC-INFRA-04`

### Requirement 4: Compute budget

**Objective:** As the maintainer deciding whether this plan is affordable, I want
the training cost stated against hardware that actually exists, so that no step
of the roadmap is scheduled on compute the project does not have.

#### Acceptance Criteria

1. The Review shall state the hardware it assumes, naming accelerator model,
   memory, and whether access is continuous or shared. `AC-COMPUTE-01`
2. When the Review estimates a training cost, the Review shall express it in
   wall-clock time on the stated hardware and shall name the assumption the
   estimate rests on. `AC-COMPUTE-02`
3. If an architecture cannot be trained within the stated budget, then the
   Review shall reject it and record the budget as the reason, regardless of its
   published results. `AC-COMPUTE-03`
4. If the hardware inventory has not been supplied when the Review is written,
   then the Review shall record that the budget is unresolved rather than
   assuming a machine. `AC-COMPUTE-04`

### Requirement 5: Screening against CLAVE's constraints

**Objective:** As a reader deciding whether to reopen a rejected option, I want
every option screened against the same stated constraints, so that a verdict can
be re-examined when a constraint changes instead of being taken on trust.

#### Acceptance Criteria

1. The Review shall state the screening constraints once, before any verdict, and
   shall apply the same constraints to every surveyed option. `AC-SCREEN-01`
2. When the Review screens an option, the Review shall state whether it works
   with FRET's MuJoCo simulation and the ROBOTIS manipulators without requiring
   a different simulator or robot. `AC-SCREEN-02`
3. When the Review screens a pick-policy architecture, the Review shall state
   whether FRET's scripted pick-and-place expert can supply the training signal
   that architecture needs. `AC-SCREEN-03`
4. When the Review rejects an option, the Review shall record which constraint it
   failed, so that a later change to that constraint identifies the options worth
   revisiting. `AC-SCREEN-04`
5. The Review shall not advance an option on popularity, citation count, or
   general reputation alone. `AC-SCREEN-05`

### Requirement 6: The shortlist that later steps consume

**Objective:** As the engineer starting v0.3.0 or v0.4.0, I want a shortlist I can
act on directly, so that the next step begins from a recorded decision rather
than repeating this survey.

#### Acceptance Criteria

1. The Review shall end with a shortlist naming which corpora, architectures, and
   infrastructure options advance, grouped by the roadmap step that consumes
   them. `AC-SHORTLIST-01`
2. When the Review advances an option, the Review shall state the reason in terms
   of the screening constraints rather than in general praise. `AC-SHORTLIST-02`
3. When the shortlist names fewer than three viable architectures for a learned
   stage, the Review shall state that the roadmap target is unmet and name what
   would have to change. `AC-SHORTLIST-03`
4. The Review shall state what it could not determine, so that an open question
   is visible rather than resolved by silence. `AC-SHORTLIST-04`

### Requirement 7: Form of the delivered document

**Objective:** As a reader returning to this document a year later, I want every
claim traceable to a source and every fact dated where it can expire, so that I
can tell which parts are still true.

#### Acceptance Criteria

1. The Review shall be published under `docs/research/` as a document committed
   to this repository. `AC-DOC-01`
2. When the Review states a fact about a third-party project, corpus, or result,
   the Review shall attribute it to a citation a reader can follow. `AC-DOC-02`
3. When the Review states a claim about an external project that is expected to
   change, the Review shall date the claim, so that a reader knows when to
   recheck it. `AC-DOC-03`
4. The Review shall not present an estimate, a measurement CLAVE has not taken,
   or a result CLAVE has not reproduced as though the project had produced it.
   `AC-DOC-04`
5. While no corpus has been fetched and no model has been trained, the Review
   shall report only what its cited sources report. `AC-DOC-05`
