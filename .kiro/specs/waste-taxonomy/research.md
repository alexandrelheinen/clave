# Research and Design Decisions

## Summary

- **Feature**: `waste-taxonomy`
- **Discovery Scope**: New Feature, with discovery against published recovery
  facility practice and against the corpus shortlist delivered at v0.1.0.
- **Key Findings**:
  - A recovery facility separates by what its machinery can physically
    distinguish, meaning overhead magnets for ferrous metal, eddy current
    separators for aluminum, and optical sorting for plastics by resin. A
    taxonomy that ignores the mechanism invents classes no line separates.
  - Which resin codes a facility accepts is a local decision rather than a
    universal one, so any globally fixed acceptance list is wrong somewhere.
  - SpectralWaste, the best-matched corpus from v0.1.0, does not label materials
    at all. Its six classes are object kinds such as film and trash bags, so the
    mapping onto material classes carries real information loss.

## Research Log

### What a recovery facility physically separates

- **Context**: `AC-CLASS-02` requires every class to name the mechanism a
  facility uses to separate it, so the design needed to know what those
  mechanisms are before fixing a table schema around them.
- **Sources Consulted**: the Association of Plastic Recyclers glossary and its
  plastic recycling process pages, the US EPA materials recovery pages, and the
  Wikipedia materials recovery facility article, all read on 2026-09-14.
- **Findings**:
  - Ferrous metal is pulled by overhead magnets; non-ferrous metal, chiefly
    aluminum, is pushed out by eddy current separators.
  - Plastics are separated by resin through optical sorters, with PET and HDPE
    the primary targets and PP increasingly accepted.
  - Glass is crushed and screened by size, and color separation is a further
    step that not every facility performs.
  - Paper and old corrugated containers are separated by disk screens and baled
    separately.
- **Implications**: the class table carries a separation-mechanism column, and a
  class whose mechanism reads `none` is visible as a class no line separates.
  That column is the design's main defense against an invented taxonomy.

### Regional variation is the norm, not the exception

- **Context**: `AC-DOC-08` requires hedging claims that vary by region.
- **Sources Consulted**: as above, plus extension-service guidance on resin
  identification codes read on 2026-09-14.
- **Findings**: acceptance of PVC, LDPE, PS and PP differs by program, and
  several sources disagree about whether PS is recyclable at all.
- **Implications**: the class-to-channel mapping is specified as configuration
  supplied per deployment rather than as a constant, which is `AC-CHANNEL-05`.
  Fixing it globally would encode one locality into the system.

### The best corpus does not label materials

- **Context**: `AC-MAP-03` anticipates a corpus labeling something other than
  material. The design needed to know whether that case is real.
- **Sources Consulted**: `docs/research/training-infrastructure-review.md` and
  the SpectralWaste paper.
- **Findings**: SpectralWaste labels film, basket, video tape, filaments, trash
  bags and cardboard. Only cardboard is a material; the rest are object kinds or
  contaminants.
- **Implications**: the corpus mapping tables carry a loss column, and each is
  followed by a statement of what the corpus labels instead and which classes it
  cannot teach. Without those, a reader would assume a corpus supports classes it
  has no signal for.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks and Limitations | Notes |
|---|---|---|---|---|
| Single document with fixed tables | Classes, objects, channels and corpus maps in one file | Every reference resolves locally; no cross-file drift | Long file | Selected |
| Class table only, mappings deferred | Define classes now, map corpora at v0.6.0 | Smaller step | Hides the loss at the corpus boundary until after the corpus is chosen, which is exactly when it stops being actionable | Rejected |
| Machine-readable class registry | Classes in YAML, consumed by later code | Enforceable | No consumer exists until v0.5.0, so the format would be guessed | Rejected as premature |

## Design Decisions

### Decision: Carry a separation-mechanism column

- **Context**: an agent asked to list waste classes produces a plausible list
  that quietly disagrees with what a line separates.
- **Alternatives Considered**: definitions alone; definitions plus the mechanism.
- **Selected Approach**: the mechanism column, with `none` permitted and
  meaningful.
- **Rationale**: it converts an unfalsifiable judgment into a checkable claim. A
  reviewer can ask what machine performs the separation, and a class that cannot
  answer is visible.
- **Trade-offs**: it ties the taxonomy to current sorting technology.
- **Follow-up**: revisit if a deployment uses a different separation method.

### Decision: Class-to-channel mapping is configuration

- **Context**: `AC-CHANNEL-03` and `AC-CHANNEL-05` require a deployment with
  fewer channels than classes to be expressible.
- **Alternatives Considered**: one channel per class as a constant; a
  configurable mapping with a shared-channel flag.
- **Selected Approach**: configurable, with a shared-channel column.
- **Rationale**: the class count is a property of the material stream and the
  channel count is a property of the installed hardware. Binding them would make
  the taxonomy unusable on any line with a different effector count.
- **Trade-offs**: a consumer has to read configuration rather than assume.
- **Follow-up**: v0.5.0 lays out bins from this configuration.

### Decision: Confidence thresholds stay out of boundary

- **Context**: `AC-CHANNEL-02` needs a reject rule, which invites a number.
- **Selected Approach**: the taxonomy states that low-confidence objects go to
  reject and does not say what low means.
- **Rationale**: a threshold is a measured quantity that depends on a trained
  model. Writing one here would be a guess that later steps would inherit as
  though it were considered.
- **Follow-up**: v0.8.0 sets it against validation data.

## Risks and Mitigations

- The class list is invented rather than grounded. Mitigated by the
  separation-mechanism column and by citation under `AC-DOC-07`.
- Local practice is presented as universal. Mitigated by `AC-DOC-08` and by
  making channel assignment configuration.
- A class is renamed later and silently corrupts downstream numbers. Mitigated
  by the append-only identifier rule and by the stability section naming the
  pick decision contract as the consumer a rename breaks.
- The taxonomy is treated as validated. Mitigated by `AC-DOC-10`, which requires
  the document to state that no line was observed.

## References

- [The Plastic Recycling Process](https://plasticsrecycling.org/how-recycling-works/the-plastic-recycling-process/), Association of Plastic Recyclers, read 2026-09-14.
- [Plastics Recycling Glossary](https://plasticsrecycling.org/plastics-recycling-glossary/), Association of Plastic Recyclers, read 2026-09-14.
- [Materials Recovery Center](https://www3.epa.gov/recyclecity/recovery.htm), US EPA, read 2026-09-14.
- [Materials recovery facility](https://en.wikipedia.org/wiki/Materials_recovery_facility), read 2026-09-14.
- [docs/research/training-infrastructure-review.md](../../../docs/research/training-infrastructure-review.md), the corpus shortlist this taxonomy maps.
