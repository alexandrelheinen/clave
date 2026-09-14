# Waste taxonomy

> Roadmap step: v0.2.0 · Spec: [.kiro/specs/waste-taxonomy/](../.kiro/specs/waste-taxonomy/)

This document fixes the vocabulary the rest of CLAVE is measured in. A material
class appears in the pick decision CLAVE publishes, in the bins the simulated
world lays out, in every training label, and in every accuracy number the
benchmark reports.

It is a contract rather than a description. Class identifiers are append-only,
and [Stability rules](#stability-rules) states which decisions a consumer may
depend on.

No sorting line was observed. Every class below is derived from published
recovery facility practice, cited inline, and the list is a proposal until
somebody checks it against a real facility. Which materials a facility actually
accepts varies by region and operator, so claims that vary are hedged rather
than presented as universal.

## Material classes

`Id` is `M-<NN>`, assigned in order and never reused. `Separation mechanism`
names what a recovery facility physically uses; a class reading `none` is a
class no line separates mechanically, which is a signal rather than an
oversight.

| Id | Class | Definition | Distinguishing property | Separation mechanism | Channel | Shared channel |
| --- | --- | --- | --- | --- | --- | --- |
| `M-01` | PET | Polyethylene terephthalate, resin code 1 | Rigid, usually transparent, thin wall, seam at base of bottles | Near-infrared optical sorting | `CH-PET` | No |
| `M-02` | HDPE | High-density polyethylene, resin code 2 | Rigid, opaque, waxy surface, thicker wall than PET | Near-infrared optical sorting | `CH-HDPE` | No |
| `M-03` | PP | Polypropylene, resin code 5 | Rigid, often translucent, flexible hinge tolerant | Near-infrared optical sorting | `CH-PP` | No |
| `M-04` | Other plastic | Plastics outside codes 1, 2 and 5, including film, PVC, LDPE, PS and multi-resin items | Flexible film, or rigid plastic matching none of the three above | Near-infrared optical sorting where accepted; film is often removed upstream because it wraps machinery | `CH-PLASTIC-OTHER` | No |
| `M-05` | Aluminum | Non-ferrous metal packaging, chiefly beverage cans and foil | Non-magnetic, light, thin wall, deforms easily | Eddy current separator | `CH-ALU` | No |
| `M-06` | Ferrous metal | Steel and tinplate packaging, chiefly food cans | Magnetic, heavier wall, rolled seam | Overhead magnet | `CH-FERROUS` | No |
| `M-07` | Glass | Container glass of any color | Rigid, heavy for its size, fractures rather than deforms | Crushed then screened by size; color separation is a further step not every facility performs | `CH-GLASS` | No |
| `M-08` | Corrugated cardboard | Old corrugated containers, meaning fluted board between two liners | Fluted cross-section, large flat panels | Disk screen, which lifts large flat items from the stream | `CH-FIBER` | Yes |
| `M-09` | Mixed paper | Paperboard, newsprint and office paper | Flat, single-ply, no flute | Disk screen | `CH-FIBER` | Yes |
| `M-10` | Beverage carton | Liquid packaging board, meaning paper laminated with polyethylene and sometimes aluminum | Rectangular, printed, rigid but light, often gabled or brick shaped | Optical sorting or manual picking, depending on facility | `CH-FIBER` | Yes |
| `M-11` | Residue | Material not recoverable in this stream | Defined by exclusion | `none` | `CH-REJECT` | Yes |

Sources for the separation mechanisms:
[Association of Plastic Recyclers](https://plasticsrecycling.org/how-recycling-works/the-plastic-recycling-process/),
[US EPA materials recovery](https://www3.epa.gov/recyclecity/recovery.htm),
and [materials recovery facility](https://en.wikipedia.org/wiki/Materials_recovery_facility),
all read on 2026-09-14.

### Classes a color camera cannot separate

CLAVE observes the belt with a color camera. Three separations that a recovery
facility performs are not available from that signal alone, and the classes are
kept separate anyway, because the taxonomy describes what the line sorts rather
than what one sensor can see.

**`M-01` against `M-03` against parts of `M-04`.** Clear PET, clear PP and clear
PS are the same color and similar in shape. A facility separates them by
near-infrared absorption, which reads the resin rather than the appearance. A
color-only classifier is guessing between them whenever the item is
transparent and unlabeled.

**`M-05` against `M-06`.** An aluminum beverage can and a steel food can are
both cylindrical metal. A facility separates them magnetically. Shape and
proportion carry some signal, since beverage cans are taller and narrower than
food cans, but a crushed can carries much less.

**`M-08` against `M-09`.** Corrugated board and flat paperboard differ by a
fluted layer that is visible edge-on and invisible face-on.

These three are the expected failure modes of any classifier CLAVE trains, and
v0.8.0 should report them as named confusions rather than as generic error. They
are the reason the reject channel exists.

## Object lookup

Tagging a mesh or reviewing a label should be a lookup, not a judgment call.
`Ambiguity` holds a dash when the assignment is unambiguous from appearance.

| Object | Class | Basis | Ambiguity |
| --- | --- | --- | --- |
| Clear water or soda bottle | `M-01` | PET is the standard resin for carbonated and still drink bottles, and is accepted by most curbside programs ([Illinois Extension, 2025](https://extension.illinois.edu/blogs/flowers-fruits-and-frass/2025-09-14-understanding-recycling-resin-identification-codes)) | - |
| Opaque milk jug | `M-02` | HDPE is the standard resin for milk and water jugs ([APR](https://plasticsrecycling.org/how-recycling-works/the-plastic-recycling-process/)) | - |
| Detergent or shampoo bottle | `M-02` | HDPE is standard for household liquid containers ([APR](https://plasticsrecycling.org/how-recycling-works/the-plastic-recycling-process/)) | Some are PP; the wall feel differs but the appearance often does not |
| Yogurt tub | `M-03` | PP is standard for dairy tubs and is now widely accepted ([Illinois Extension, 2025](https://extension.illinois.edu/blogs/flowers-fruits-and-frass/2025-09-14-understanding-recycling-resin-identification-codes)) | - |
| Margarine or ice cream tub | `M-03` | As above | Some tubs are HDPE |
| Plastic bottle cap | `M-03` | Caps are typically PP even on PET bottles ([APR glossary](https://plasticsrecycling.org/plastics-recycling-glossary/)) | Governed by the bottle when still attached; see the multi-material rule below |
| Aluminum beverage can | `M-05` | Non-ferrous, removed by eddy current ([EPA](https://www3.epa.gov/recyclecity/recovery.htm)) | Indistinguishable from `M-06` by color alone |
| Steel food can | `M-06` | Ferrous, removed by overhead magnet ([EPA](https://www3.epa.gov/recyclecity/recovery.htm)) | Indistinguishable from `M-05` by color alone |
| Aerosol can | `M-06` | Usually steel bodied | May be aluminum; many programs exclude aerosols entirely as a pressure hazard, which varies by operator |
| Glass bottle | `M-07` | Container glass ([EPA](https://www3.epa.gov/recyclecity/recovery.htm)) | Color separation is a further step not every facility performs |
| Glass jar | `M-07` | As above | As above |
| Corrugated shipping box | `M-08` | Old corrugated containers are baled separately ([MRF](https://en.wikipedia.org/wiki/Materials_recovery_facility)) | Flattened boxes are the normal presentation and hide the flute |
| Cereal or shoe box | `M-09` | Paperboard is a mixed paper grade, not OCC ([MRF](https://en.wikipedia.org/wiki/Materials_recovery_facility)) | Visually close to `M-08` when face-on |
| Milk or juice carton | `M-10` | Liquid packaging board, sorted optically or by hand depending on facility | Acceptance varies by operator |
| Paper coffee cup | `M-11` | Paper with a bonded polyethylene liner, which most fiber mills reject | Some facilities accept them; this is a regional variation |
| Plastic carrier bag | `M-04` | Film plastic, which wraps rotating machinery and is commonly excluded from curbside ([Illinois Extension, 2025](https://extension.illinois.edu/blogs/flowers-fruits-and-frass/2025-09-14-understanding-recycling-resin-identification-codes)) | Many programs route film to residue rather than to a plastics channel |
| Bubble wrap or stretch film | `M-04` | As above | As above |
| Foam cup or tray | `M-04` | Polystyrene, resin code 6, which several sources describe as not recyclable in practice | Often routed to `M-11` by an operator; a per-deployment decision |
| Pizza box | `M-08` | Corrugated board by construction | Grease contamination causes many facilities to route it to `M-11`; appearance does not reveal contamination |
| Blister pack | `M-04` | Mixed PVC or PET with a foil backing | Multi-material; the backing may trigger a metal sorter |

Twenty rows, covering bottles, cans, boxes, tubs, cartons, and bags.

### Multi-material objects

An object made of more than one material takes the class of the component that
governs its routing on a real line, which is the component the sorting machinery
responds to first. A capped PET bottle is `M-01`, because it is sorted as a
bottle and the cap travels with it. A blister pack is `M-04`, because the plastic
carries the bulk. The remaining components are recorded in the ambiguity cell
rather than lost.

## Channel policy

**Every class routes to a channel, and the mapping is configuration.** The class
count is a property of the material stream; the channel count is a property of
the installed effector. Binding them would make this taxonomy unusable on any
line with a different number of channels, so a deployment supplies the mapping
and the table above records only a default.

**One reject channel, `CH-REJECT`.** It receives `M-11`, and it receives any
object the pipeline cannot route with confidence regardless of predicted class.
What counts as insufficient confidence is a measured quantity that depends on a
trained model, so it is set at v0.8.0 and deliberately not fixed here. Writing a
number now would be a guess that later steps would inherit as though it had been
considered.

**A channel may serve several classes.** `CH-FIBER` carries `M-08`, `M-09` and
`M-10` in the default mapping, which is how a deployment with fewer channels
than classes is expressed. A deployment with more effectors can split them; one
with fewer can merge further.

**An object not picked in time continues down the belt.** The reachable window
is bounded by belt speed and effector reach, and CLAVE does not stop the line.
An object that leaves the window untouched is carried to whatever the line does
with its end-of-belt stream, which is outside CLAVE's boundary. A missed pick is
therefore a throughput loss rather than a misroute, and v0.8.0 should count the
two separately, because they have different causes and different fixes.

## Corpus label mappings

One table per corpus shortlisted in
[the v0.1.0 review](research/training-infrastructure-review.md).

### ZeroWaste

Four foreground material types are annotated; everything else is background
([Bashkirova et al., CVPR 2022](https://arxiv.org/abs/2106.02740), read
2026-09-14). Splits are 3,002 train, 572 validation and 929 test images, with a
further 6,212 unlabeled frames captured under the same conditions.

| Corpus label | Maps to | Loss |
| --- | --- | --- |
| cardboard | `M-08`, `M-09`, `M-10` | Merges all three fiber classes: the label covers parcel packaging, boxboard such as cereal boxes, and carton food packaging, which CLAVE routes to one channel but counts separately |
| soft_plastic | `M-04` | Film. Resin is not recorded |
| rigid_plastic | `M-01`, `M-02`, `M-03`, `M-04` | Spans every rigid plastic class. The label covers food containers and bottles without recording resin, which is the distinction `M-01` through `M-03` exist to make |
| metal | `M-05`, `M-06` | Ferrous and non-ferrous are merged, which is the distinction a magnet makes and a color camera cannot |

**What it labels instead of material.** It does label material, which makes it
the only shortlisted corpus whose vocabulary is the same kind of thing as
CLAVE's. What it does not do is separate within a material family: four labels
stand where CLAVE has ten recoverable classes.

**Classes it supplies no signal for.** `M-07` glass and `M-11` residue. Glass is
not among the annotated foreground types, and residue is unlabeled background,
so neither receives a positive example.

ZeroWaste advanced at [v0.1.2](research/training-infrastructure-review.md) once
the maintainer confirmed CLAVE is personal research, which satisfies its
NonCommercial term. It is now the strongest corpus in the shortlist: an
operating recovery-facility conveyor, localization annotations, and roughly five
times SpectralWaste's labeled volume. Its four labels are coarse, but they are
coarse in the direction CLAVE can refine later rather than orthogonal to it.

### SpectralWaste

| Corpus label | Maps to | Loss |
| --- | --- | --- |
| film | `M-04` | Resin is not recorded, so PE film and PP film collapse together |
| basket | `M-03`, `M-04` | An object kind rather than a material; the resin varies by basket |
| video tape | `M-11` | A contaminant in this stream rather than a material class |
| filaments | `M-11` | A contaminant; tangles machinery, which is why the corpus labels it |
| trash bags | `M-04` | The bag is film; its contents are unknown and unlabeled |
| cardboard | `M-08` | The only direct material match; `M-08` against `M-09` is not distinguished |

**What it labels instead of material.** SpectralWaste labels object kinds and
contaminants, chosen for what disrupts a sorting line rather than for what the
material is. Only cardboard is a material class. Material is not recoverable
from the other five labels without the hyperspectral channel that CLAVE has no
sensor for.

**Classes it supplies no signal for.** `M-01`, `M-02`, `M-05`, `M-06`, `M-07`,
`M-09` and `M-10`. Seven of eleven classes, which is most of the taxonomy.
SpectralWaste is the best-matched corpus in the shortlist by scene and the
weakest by label coverage, and both facts have to be carried forward together.

### TACO

TACO uses a hierarchical taxonomy of 60 categories under 28 supercategories,
plus `Unlabeled litter` for ambiguous objects
([TACO paper](https://arxiv.org/abs/2003.06975), read 2026-09-14).

| Corpus label | Maps to | Loss |
| --- | --- | --- |
| clear_plastic_bottle | `M-01` | - |
| other_plastic_bottle | `M-01`, `M-02`, `M-04` | Resin is not recorded, so the target class is undetermined |
| plastic_bottle_cap | `M-03` | Governed by the bottle when attached |
| metal_bottle_cap | `M-06` | Too small to pick individually on a belt |
| drink_can | `M-05` | Steel drink cans, where used, would be `M-06` and are not distinguished |
| aluminium_foil | `M-05` | Foil is often too light for reliable eddy current recovery |
| pop_tab | `M-05` | Too small to pick individually |
| glass_bottle | `M-07` | Color is not recorded |
| corrugated_carton | `M-08` | - |
| other_carton | `M-09`, `M-10` | Carton spans paperboard and liquid packaging board |
| drink_carton | `M-10` | - |
| normal_paper | `M-09` | - |
| paper_cup | `M-11` | Polyethylene lining is not recorded in the label |
| tissues | `M-11` | Not recoverable |
| disposable_plastic_cup | `M-03`, `M-04` | Resin is not recorded |
| plastic_lid | `M-03` | Too small to pick individually |
| plastic_straw | `M-11` | Too small to pick individually and commonly excluded |
| plastic_utensils | `M-04` | Resin is not recorded |
| other_plastic_wrapper | `M-04` | Film |
| single-use_carrier_bag | `M-04` | Film |
| crisp_packet | `M-11` | Metallized film, not recoverable in a single stream |
| styrofoam_piece | `M-04` | Often routed to `M-11` by operator policy |
| disposable_food_container | `M-03`, `M-04` | Resin is not recorded |
| other_plastic | `M-04` | The label is already a residual category |
| rope&strings | `M-11` | A contaminant that tangles machinery |
| Unlabeled litter | `unmapped` | Ambiguous by construction; the corpus uses it for what its own taxonomy cannot place |

**This mapping is incomplete and is recorded as such.** Twenty-six labels are
mapped above, out of 60 categories. The authoritative list is the COCO
`annotations.json` in the [TACO repository](https://github.com/pedropro/TACO),
which was not read for this document. Neither the paper nor the project website
publishes the full taxonomy as text, and the website did not respond on
2026-09-14. Completing the mapping requires reading that file, and it is listed
under [Open questions](#open-questions) rather than approximated. `AC-MAP-01`
and `AC-MAP-02` are therefore partially unmet for TACO.

**Classes it supplies no signal for, on the mapped subset.** None entirely.
TACO touches every class at least once, which is what its category breadth buys.
What it lacks is belt context, not vocabulary.

### TrashNet

| Corpus label | Maps to | Loss |
| --- | --- | --- |
| glass | `M-07` | Color is not recorded |
| paper | `M-09` | - |
| cardboard | `M-08` | - |
| plastic | `M-01`, `M-02`, `M-03`, `M-04` | One label spans four classes; resin is not recorded at all |
| metal | `M-05`, `M-06` | One label spans both metals; ferrous against non-ferrous is not recorded |
| trash | `M-11` | - |

**What it labels instead of objects.** TrashNet labels whole images rather than
regions, so it carries no localization at all. A consumer expecting a bounding
box or a mask gets nothing, which makes TrashNet a classifier sanity check
rather than a source of detection training data.

**Classes it supplies no signal for.** `M-10`, and it cannot separate `M-01`
from `M-02` from `M-03` from `M-04`, nor `M-05` from `M-06`. Six of eleven
classes are reachable only as a coarse group.

## Stability rules

| Element | Safe to change? | Why |
| --- | --- | --- |
| Class identifiers `M-<NN>` | No | Consumed by the pick decision contract, by mesh tags at v0.5.0, by training labels at v0.6.0, and by the confusion matrix at v0.8.0. A rename breaks all four silently. |
| The set of classes | No | Adding, merging or retiring a class invalidates every tagged mesh and every reported metric. A retired class keeps its identifier rather than having it reused. |
| The residue class `M-11` | No | The reject rule depends on exactly one existing. |
| Class display names | Yes | Presentation only. The identifier carries the meaning. |
| Definitions and distinguishing properties | Yes | Clarification does not change what the class denotes. |
| The object lookup | Yes | It is a convenience for taggers. Adding rows or refining an ambiguity note breaks nothing. |
| The default class-to-channel mapping | Yes | It is a default, and a deployment overrides it. |
| Channel identifiers | Partly | A deployment may rename them, but `CH-REJECT` must exist, since the reject rule names it. |

## Open questions

**The class list has not been checked against a real sorting line.** Closed by
somebody visiting or consulting a recovery facility. Everything here is derived
from published practice, and a taxonomy derived that way is a proposal. The most
likely errors are a class that no line separates in practice and a missing class
that every line does.

**The TACO mapping is incomplete.** Closed by reading `annotations.json` from the
TACO repository and mapping the remaining categories. Twenty-six of sixty are
mapped. No claim in this document depends on the unmapped remainder, but v0.6.0
cannot build a TACO training set without it.

**ZeroWaste's coarse labels have to be refined, not just mapped.** It is now
mapped and is the strongest corpus in the shortlist, but three of its four
labels span several CLAVE classes: `rigid_plastic` covers four, `cardboard`
covers three, and `metal` covers two. Training on it directly teaches a model to
predict the coarse label, not the class. Closed at v0.6.0 by deciding whether
CLAVE trains a coarse head and refines it, trains only on the classes a corpus
separates, or relabels a subset. That is a real design decision, not a mapping
exercise.

**Its NonCommercial term binds anything trained on it.** A model trained on
ZeroWaste cannot later be used commercially without retraining. Closed only by
CLAVE's intent staying personal research.

**Film handling is an operator decision, not a taxonomy decision.** `M-04`
carries film, and many facilities route film to residue because it wraps
rotating machinery. Whether CLAVE picks film into a plastics channel or into
reject is a per-deployment configuration, and no default here is right
everywhere.

**Three confusions are expected and unmeasured.** PET against PP against PS when
transparent, aluminum against steel, and corrugated against paperboard face-on.
Named here so v0.8.0 reports them specifically rather than folding them into
general error. No number is attached, because nothing has been measured.
