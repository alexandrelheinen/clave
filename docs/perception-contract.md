# The perception contract

How CLAVE describes one piece of waste, and why that description does not name
the sensor, the camera count, or the tracker that produced it.

[architecture.md](architecture.md) describes the system this sits inside.
This document specifies an interface rather than reporting an implementation:
it is what a tracker has to satisfy, and what every consumer downstream is
allowed to assume.

## The problem it solves

A sorting line accumulates sensors. Today the gate carries one wide camera for
detection and three narrow ones for barcodes. Tomorrow it might carry a depth
sensor, a near-infrared spectrometer that separates PET from PLA where a color
camera cannot, a second gate after a tumbler, or a line-scan reader replacing
the three narrow cameras with one.

If the policy, the safety layer and the publisher each read sensors directly,
every one of those changes edits every consumer. So they do not read sensors.
They read one record, and the only code that knows a camera exists is the code
that converts that camera's output into evidence.

## Two invariants that make it possible

Everything below rests on two properties, and neither is negotiable.

**One frame.** Every observation is expressed in the belt frame: `x` along belt
travel, `y` across it, `z` up from the belt surface, origin at the upstream
edge on the centerline. A sensor reports in its own frame, and the adapter that
wraps it converts. A consumer never sees pixels or camera coordinates.

**One clock.** Every observation carries the monotonic instant it was taken.
Because the belt speed is known, an observation at `t0` can be propagated to any
later `t1` by translating it `speed * (t1 - t0)` along `x`. That is what lets a
barcode read at the gate attach to an object picked a metre downstream, and what
lets two cameras that fired 8 ms apart describe the same object.

Take either invariant away and the fusion below becomes guesswork about which
observation refers to what.

## Evidence

An adapter converts one sensor reading into one or more `Evidence` values. The
envelope is common; the payload is a tagged union.

```
Evidence
  source_id     which sensor, for provenance and for debugging only
  role          detection | code | depth | spectral | ground_truth
  observed_at   monotonic nanoseconds
  confidence    0.0 to 1.0, the adapter's own certainty
  payload       one of the variants below
```

| Variant | Carries | Produced by |
| --- | --- | --- |
| `Detection` | oriented footprint box in belt frame, instance mask, estimated height | the wide camera |
| `Material` | distribution over the 11 taxonomy classes plus reject | the classifier on any imaging sensor |
| `Code` | symbology, decoded digits, quad in belt frame | a barcode camera |
| `Height` | measured z of the object's upper surface | depth, or stereo across two cameras |
| `GroundTruth` | the simulator's label | simulation only, and refused in a real deployment |

Two rules give the union its value. A variant states what was *measured*, never
what should be *done*, so no adapter decides a channel or a grasp. And adding a
variant is additive: a consumer that does not know about `Spectral` keeps
working, because it reads the fused record rather than the evidence stream.

`GroundTruth` is deliberately in the same union as the rest. It is how
simulation supplies labels through the same path real sensors use, so the
training pipeline cannot accidentally depend on a shape that only exists in
simulation. A runtime configured for hardware refuses it at the adapter
boundary.

## Fusion

The tracker holds one belief per object and folds evidence into it.

```
Track
  track_id        stable for the object's life on the belt
  footprint       oriented box, propagated by belt speed between observations
  height          current estimate with its uncertainty
  material        posterior over the 11 classes plus reject
  codes           every Code that has been associated, with its source
  contributors    which source_ids have been folded in
  first_seen      monotonic
  last_updated    monotonic
```

**Association** is geometric and temporal. Evidence propagated to the track's
current time is associated when it falls inside a gate around the track's
footprint. A `Code` associates when its quad falls inside the track's mask,
which is what lets a barcode belong to an object rather than to a position.

**Material** combines a visual likelihood with a barcode-derived prior. A GTIN
does not name a material: a single product resolves to a packaging bill of
materials, and a jar that returns glass, plastic and aluminium components tells
you only that one of them carries the label. So a code contributes a prior
weighted by which component is plausibly the one being looked at, and it never
overrides a confident visual observation. Where the code resolves to a single
rigid component, that prior is close to decisive.

**Conflict** is resolved by recency and confidence, never by source priority. A
sensor is not trusted because of what it is; it is trusted because of what it
reported and how sure it was. Otherwise adding a sensor silently reorders every
existing one.

## The record a consumer reads

```
WasteObject
  track_id
  observed_at          when this description was settled
  valid_until          when belt travel invalidates the pose

  footprint            oriented box: center, major extent, minor extent, yaw
  height
  grasp_point          where the end effector should meet the object
  grasp_axis           the footprint's minor axis
  grasp_width          the minor extent, for a jaw; ignored by a suction cup
  surface_normal       for a suction cup; vertical for a flat-lying object

  material             taxonomy class, M-01 to M-11, or reject
  material_confidence
  density              from the material
  mass                 estimate
  mass_uncertainty     a band, not a number, and the reason is below

  channel              resolved by the routing policy, not by perception
  evidence             which roles contributed, for auditing
```

Three properties of this record are load-bearing.

**No sensor appears in it.** `evidence` names roles rather than cameras, so a
consumer can report that a decision used a code without knowing which of three
cameras read it.

**Mass carries a band.** Density times footprint volume is weak: a PET bottle
empty or half full differs tenfold, and that difference decides whether a
suction cup holds. A single number would invite a consumer to trust it. Where a
GTIN resolved, the packaging mass replaces the estimate and the band narrows.

**The channel is resolved, not perceived.** Perception says what the object is;
the routing policy says where that class goes on this line. Channel numbers
belong to the operator, which is why they are configuration and why they live
behind the same resolver the safety layer already calls.

## What changes when the architecture changes

This is the test the contract has to pass.

| Change | What has to change |
| --- | --- |
| Add a fourth barcode camera | One entry in `cameras`. Nothing else |
| Replace three code cameras with one line-scan | The adapter for that sensor. Nothing else |
| Add a depth sensor | A `Height` adapter, and the fusion rule that prefers measured height over the class prior |
| Add a near-infrared sensor | A new `Material` producer. Fusion already combines material evidence |
| Move the gate further upstream | One position in `cameras`. Dead reckoning already spans the gap |
| Swap the tracker for a learned one | Nothing downstream, provided it still emits `WasteObject` |
| Add a second arm | Nothing in perception. A second consumer reads the same records |

If a change in that left column forces an edit outside the right column, the
abstraction has leaked and the leak is a defect rather than a fact of life.

## What this does not settle

**How the material posterior is parameterized.** A distribution over 12
outcomes, or 11 with an abstention threshold, changes the training loss, and
that choice belongs with the model rather than with this contract.

**Whether `reject` is a predicted class or an absence of confidence.** The
record above admits either, and the fusion rule differs between them.

**Tracking through occlusion.** Objects travel in a single layer under a nadir
camera, so occlusion is rare rather than absent. Two objects that touch and are
segmented as one are a failure this contract describes but does not prevent.
