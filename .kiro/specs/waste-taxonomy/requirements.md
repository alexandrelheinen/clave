# Requirements Document

## Project Description (Input)
CLAVE classifies an object on a belt and routes it to a channel, and neither
the set of classes nor the routing has been written down. v0.1.0 shortlisted
three corpora whose label sets disagree with each other and with recovery
facility practice: SpectralWaste labels object kinds such as film and trash
bags, TrashNet labels six coarse materials, and TACO labels sixty categories
of litter. Nothing yet says which of those CLAVE adopts, how they relate, or
what a classifier is actually predicting.

Every later step depends on that answer. v0.5.0 tags each simulated mesh with a
material class and places one bin per channel. v0.6.0 maps corpus labels onto
the taxonomy in order to build a training set. v0.8.0 reports per-class
accuracy and a confusion matrix, which is meaningless if the classes are not
fixed. A class renamed between those steps silently corrupts every number
downstream.

The people carrying that risk are whoever implements those steps, which for
this repository means a maintainer working with agents. An agent asked to
"classify the waste" with nothing written down will invent a plausible class
list, and a plausible class list is the problem: it will look reasonable,
disagree quietly with what a sorting line actually separates, and only fail
when the system is measured against reality.

This feature writes the taxonomy down. It defines the material classes CLAVE
sorts, grounded in what a recovery facility physically separates rather than in
what is convenient to label. It maps everyday objects onto those classes, so
that tagging a mesh or an image is a lookup rather than a judgment call. It
defines the channel each class routes to, including where a low-confidence
object goes. And it maps the shortlisted corpora onto the taxonomy, naming the
labels that do not map instead of dropping them.

The deliverable is a document under `docs/`. No code lands. Nothing is trained.
The taxonomy is a contract that later specs consume, so it is versioned and its
class identifiers are append-only.

## Introduction

This feature fixes the vocabulary the rest of CLAVE is measured in. A material
class is not an implementation detail: it appears in the pick decision CLAVE
publishes, in the bins the simulated world lays out, in the training labels, and
in every accuracy number the benchmark reports.

Two things make it harder than writing a list. Recovery facilities separate by
what their machinery can physically distinguish, meaning magnets take ferrous
metal, eddy currents take aluminum, and optical sorters take plastics by resin,
so a taxonomy that ignores that separates classes no line would separate. And
the corpora CLAVE will train on do not label materials at all in one case, so
the mapping from corpus label to material class carries real information loss
that has to be recorded rather than hidden.

The taxonomy is also a routing decision. Classes exist so that objects reach
channels, and a class that no channel accepts is a class CLAVE has no reason to
predict. Low-confidence objects need a defined destination, because a sorting
line cannot pause to think.

## Boundary Context

- **In scope**: the material classes and their definitions, the mapping from
  everyday objects to classes, the channel each class routes to, the
  low-confidence rule, the mapping from each shortlisted corpus label set onto
  the taxonomy including what fails to map, the class identifier scheme and its
  stability rules, and the document itself.
- **Out of scope**: choosing a classifier, which is v0.4.0. Building the
  simulated bins, which is v0.5.0. Building the training set, which is v0.6.0.
  Confidence thresholds expressed as numbers, which depend on a trained model
  and belong to v0.8.0. The physical channel hardware. Any claim about accuracy.
- **Adjacent expectations**: v0.1.0's shortlist supplies the corpora whose
  labels are mapped, and is not revisited here. The line operator supplies the
  physical channel count in a real deployment, so the taxonomy states the
  mapping from class to channel as a configuration rather than a constant. The
  pick decision contract consumes the class identifier, so a rename is a
  breaking change to that contract.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the scheme
`pick-decision-contract` established, with areas `CLASS`, `OBJECT`, `CHANNEL`,
`MAP`, and `DOC`. Ids are append-only: a criterion that is removed leaves its
number retired rather than reused.

Verification is document review, as in `training-infrastructure-review`, since
the deliverable is prose and tables. Every criterion is written so two reviewers
reading the document reach the same verdict.

## Requirements

### Requirement 1: Material classes

**Objective:** As the engineer who will label meshes, build a training set, and
report per-class accuracy, I want a fixed set of material classes with stable
identifiers, so that the same word means the same thing at every step.

#### Acceptance Criteria

1. The Taxonomy shall define every material class CLAVE sorts, each with a
   stable identifier, a one-sentence definition, and the physical property that
   distinguishes it. `AC-CLASS-01`
2. When the Taxonomy defines a class, the Taxonomy shall state the mechanism a
   recovery facility uses to separate that material, so a class no line
   separates is visible as such. `AC-CLASS-02`
3. The Taxonomy shall state that class identifiers are append-only, and that a
   retired class keeps its identifier rather than having it reused.
   `AC-CLASS-03`
4. If two classes cannot be distinguished from a single overhead color image,
   then the Taxonomy shall say so and state whether they are merged or kept
   separate. `AC-CLASS-04`
5. The Taxonomy shall include exactly one class for material that is not
   recyclable in this stream. `AC-CLASS-05`

### Requirement 2: Object to class mapping

**Objective:** As whoever tags a simulated mesh or reviews a labeled image, I
want a lookup from everyday object to material class, so that tagging is a
lookup rather than a judgment call made differently each time.

#### Acceptance Criteria

1. The Taxonomy shall map at least fifteen everyday container objects onto
   material classes, covering at minimum bottles, cans, boxes, tubs, cartons,
   and bags. `AC-OBJECT-01`
2. When the Taxonomy maps an object, the Taxonomy shall name the class and cite
   the practice or standard that justifies the assignment. `AC-OBJECT-02`
3. If an object's material cannot be determined from its appearance alone, then
   the Taxonomy shall record it as ambiguous and name what would resolve it.
   `AC-OBJECT-03`
4. If an object is made of more than one material, then the Taxonomy shall state
   which material governs its routing. `AC-OBJECT-04`

### Requirement 3: Channel routing

**Objective:** As the engineer building the pick decision and the simulated
bins, I want each class routed to a named channel with a defined fallback, so
that no object on the belt has an undefined destination.

#### Acceptance Criteria

1. The Taxonomy shall assign every material class to a channel. `AC-CHANNEL-01`
2. The Taxonomy shall define exactly one reject channel and state that it
   receives any object the system cannot route with confidence.
   `AC-CHANNEL-02`
3. When the Taxonomy assigns a class to a channel, the Taxonomy shall state
   whether that channel is shared with other classes, so a deployment with
   fewer channels than classes is expressible. `AC-CHANNEL-03`
4. If an object is not picked before it leaves the reachable window, then the
   Taxonomy shall state what happens to it. `AC-CHANNEL-04`
5. The Taxonomy shall state the class-to-channel mapping as configuration
   supplied per deployment rather than as a constant of the system.
   `AC-CHANNEL-05`

### Requirement 4: Corpus label mapping

**Objective:** As the engineer building the training set at v0.6.0, I want each
shortlisted corpus mapped onto the taxonomy with its losses named, so that I
know what a corpus can and cannot teach before I spend effort on it.

#### Acceptance Criteria

1. The Taxonomy shall map the label set of every corpus shortlisted at v0.1.0
   onto the material classes. `AC-MAP-01`
2. When a corpus label does not map onto any class, the Taxonomy shall list it
   as unmapped rather than dropping it silently. `AC-MAP-02`
3. When a corpus labels something other than material, the Taxonomy shall say
   what it labels instead and whether that is recoverable as a material class.
   `AC-MAP-03`
4. When a single corpus label spans more than one material class, the Taxonomy
   shall record the ambiguity rather than picking one class for it.
   `AC-MAP-04`
5. The Taxonomy shall state, per corpus, which classes it cannot supply any
   training signal for. `AC-MAP-05`

### Requirement 5: Form of the delivered document

**Objective:** As a reader returning to this document after the taxonomy has
been used by four other steps, I want its claims sourced and its stability rules
explicit, so that I can tell what is safe to change.

#### Acceptance Criteria

1. The Taxonomy shall be published under `docs/` as a document committed to this
   repository. `AC-DOC-06`
2. When the Taxonomy states a fact about recovery facility practice or a
   material standard, the Taxonomy shall attribute it to a citation a reader can
   follow. `AC-DOC-07`
3. When the Taxonomy states a claim about practice that varies by region or
   operator, the Taxonomy shall say so rather than presenting local practice as
   universal. `AC-DOC-08`
4. The Taxonomy shall name which of its decisions are safe to change and which
   would break a consumer that already depends on them. `AC-DOC-09`
5. The Taxonomy shall not present a class list as validated against a real
   sorting line, because none has been observed. `AC-DOC-10`
