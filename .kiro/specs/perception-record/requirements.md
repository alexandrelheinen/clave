# Perception record

## Intent

Build the record every consumer downstream already claims to read.
`docs/perception-contract.md` specifies how CLAVE describes one piece of waste
without naming the sensor that saw it. No code produces that description.
`clave-decision` documents its object id as "the identity the tracker assigned",
`configs/world/sorting_line.yml` names a module `clave.tracker` that has never
been written, and `src/clave/runtime/inference.py` matches a proposed point to
the nearest labeled object and calls the result an identity.

This spec builds everything the contract describes except the association rule,
which `learned-tracker` supplies as a trained model. The split is deliberate:
what is here is data, geometry and arithmetic, testable without a checkpoint,
and it is what the learned rule plugs into.

Two people are served. An operator adding a near-infrared sensor to the line
should edit one list and touch nothing else. And anyone reading a CLAVE number
should be able to tell what the system observed from what the simulator told it,
which today they cannot.

## Scope

**In.** The belt frame correction. The `Evidence` envelope and its five
payloads. `Track` and `WasteObject`. Propagation of an observation through time
by belt speed. The `Detection` adapter over a segmentation render, the
`GroundTruth` adapter and its refusal on hardware, and the `Code` adapter with
a barcode decoder and a GTIN to bill-of-materials resolver. The material
posterior, its conflict rule and the code-derived prior. The mass band. The
association protocol that `learned-tracker` implements. The test that proves a
sensor change edits one file.

**Out.** The association algorithm, which is `learned-tracker` and which is why
this spec ships only the ground-truth implementation of the protocol, named so
that nobody mistakes it for perception. The end effector, specified separately,
which is why no grasp criterion appears below even though `WasteObject` carries
grasp geometry. Training or retraining perception and policy models. The object
set, settled by `D-11`. The R2 upload application.

## Constraints

- **One frame.** Every observation is expressed in the belt frame. The frame the
  documents describe is corrected to the frame the code uses rather than the
  reverse, because the committed golden vectors, the safety envelope and every
  number in `docs/measurements.md` are already expressed against it.
- **One clock.** Every observation carries the monotonic instant it was taken.
  Without it, an observation cannot be propagated and association becomes
  guesswork.
- **A variant states what was measured, never what should be done.** No adapter
  resolves a channel, and none decides a grasp.
- **Adding a payload variant is additive.** A consumer that does not know a
  variant keeps working, because it reads the fused record rather than the
  evidence stream.
- **`GroundTruth` travels the path real sensors travel.** Simulation supplies
  labels through the same union, so the training pipeline cannot come to depend
  on a shape that exists only in simulation.
- **No sensor appears in `WasteObject`.** `evidence` names roles, so a consumer
  can report that a decision used a code without knowing which camera read it.
- **Conflict resolves by recency and confidence, never by source priority.**
  Trusting a sensor for being that sensor means adding one silently reorders
  every existing one.
- **Nothing in this spec is learned.** It trains nothing and loads no
  checkpoint, which is what keeps it testable on a machine with no deep
  learning framework, the property `learning-platform` established and every
  step since has kept.
- **The posterior has only one producer today, and it is the simulator.** No
  per-instance classifier exists: the model in `clave.runtime.inference` is
  whole-frame and multi-label, and the line carries no spectral sensor. So
  `material`, and the `density` and mass band that follow from it, are
  restatements of `GroundTruth.material_class` until a `Material` producer
  lands. `AC-TRACK-49` requires the record to say so rather than let a reader
  assume otherwise, because a record that quietly launders a simulator label
  into a perceived one is the exact failure this spec exists to end.
- **The sensing gate does not cover the belt it stands over.** Measured by
  sweeping objects across the belt and reading the segmentation render,
  `gate_wide` images 0.800 m of the 1.00 m width and the three code cameras
  image 73 percent of it with two dead bands near y = 0.12 m to 0.22 m on each
  side. This caps `AC-TRACK-15` geometrically and it is a defect in the world
  rather than in the tracker, so it is recorded against `sorting-world` and this
  spec measures against the gate as it stands rather than repairing it.

## Acceptance criteria

### Frame and clock

`AC-TRACK-01`: The system shall express every observation in the belt frame,
with `x` along belt travel, `y` across it, `z` measured from the floor, and the
origin at the center of the belt on the centerline.

`AC-TRACK-02`: When a sensor reports in its own frame, the adapter wrapping it
shall convert, and no consumer of `WasteObject` shall receive pixel or camera
coordinates. An instance mask is pixel-indexed by definition, so it may travel
inside `Evidence`, which is adapter-side, and shall not appear in the record.

`AC-TRACK-03`: The system shall carry a monotonic instant on every observation.

`AC-TRACK-04`: When an observation taken at `t0` is consumed at `t1`, the system
shall propagate it by translating it `speed * (t1 - t0)` along `x`, proved by a
test that advances the clock rather than moving the object.

`AC-TRACK-05`: When the documents and the code disagree about the belt frame,
the documents shall be corrected, and no committed golden vector shall change.

### Evidence

`AC-TRACK-06`: The system shall carry evidence as an envelope of `source_id`,
`role`, `observed_at`, `confidence` and one tagged payload.

`AC-TRACK-07`: The system shall admit exactly the payload variants `Detection`,
`Material`, `Code`, `Height` and `GroundTruth`, and no variant shall carry an
instruction, a channel or a grasp.

`AC-TRACK-08`: When a runtime is configured for hardware, the adapter boundary
shall refuse `GroundTruth`, naming the source that offered it.

`AC-TRACK-09`: When evidence carries a payload no fusion rule knows, the system
shall report the miss and leave the track otherwise unchanged, and the emitted
`WasteObject` shall keep its shape, proved by a test that folds one.

`AC-TRACK-10`: When the detection camera renders a frame, the `Detection`
adapter shall report an oriented footprint in the belt frame and an instance
mask, derived from the render rather than from object state.

### Codes

`AC-TRACK-11`: When a barcode camera renders a frame carrying a legible symbol,
the `Code` adapter shall decode it and report the symbology, the digits and the
quad in the belt frame.

`AC-TRACK-12`: When a decoded symbol fails its check digit, the system shall
discard it rather than emit evidence.

`AC-TRACK-13`: The system shall resolve a GTIN to a packaging bill of materials
rather than to a material class, so a jar returning glass, plastic and aluminum
components states that one of them carries the label.

`AC-TRACK-14`: When a GTIN is not in the committed table, the system shall emit
the code with no bill of materials rather than guessing one.

`AC-TRACK-15`: The system shall measure the decode yield over a recorded rollout
and record it in `docs/measurements.md`, whatever it turns out to be.

### Tracks and fusion

`AC-TRACK-16`: The system shall hold one `Track` per object, carrying a
`track_id`, a footprint propagated by belt speed, a height estimate, a posterior
over the eleven taxonomy classes plus reject, every associated code, and the
sources that contributed.

`AC-TRACK-17`: When a `Code` associates to a track, it shall stay associated as
the track propagates, so a symbol read at the gate is still attached a metre
downstream.

`AC-TRACK-18`: When visual evidence and a code-derived prior disagree, the
system shall combine them so that a code never overrides a confident visual
reading.

`AC-TRACK-19`: When two pieces of evidence conflict, the system shall resolve by
recency and confidence and never by which source produced them.

`AC-TRACK-20`: The system shall decide association behind one protocol, and this
spec shall supply exactly one implementation of it, which reads the simulator's
object id and is named so that no reader mistakes it for perception.

### The record

`AC-TRACK-21`: The system shall emit `WasteObject` as the only record a consumer
reads, and no field of it shall name a sensor.

`AC-TRACK-22`: The system shall report mass as a band rather than a number, and
shall narrow that band when a GTIN resolved to a packaging mass.

`AC-TRACK-23`: The system shall leave `channel` to the routing policy rather
than resolving it in perception.

`AC-TRACK-24`: The system shall set `valid_until` to the instant the propagated
footprint centre reaches the reachable window exit at 1.034 m, which is the
sweep recorded in `docs/measurements.md` rather than a tolerance chosen here.

### The abstraction holds

`AC-TRACK-25`: When a camera of an existing role is added or moved, the change
shall be confined to `configs/world/sorting_line.yml`, proved by a test that
adds one and asserts the record is unchanged in shape. A new role, or a sensor
whose output shape differs, costs one adapter and nothing else, which is what
the contract's change table states.

`AC-TRACK-25b`: When no camera produces a role the tracker was configured to
fuse, the system shall say so at load rather than emit records silently missing
that evidence.

`AC-TRACK-26`: When the association implementation is replaced, nothing above
the protocol shall change, which is the property `learned-tracker` depends on.

### What the first draft of this spec got wrong

These criteria were added after an adversarial design review refuted claims the
earlier draft rested on. They are numbered from 45 because `AC-TRACK-27` through
`AC-TRACK-44` belong to `learned-tracker` and ids are never reused.

`AC-TRACK-45`: When the `Detection` adapter reads a segmentation render, it
shall discard the geometry name that render is keyed by, and no value derivable
from `ObjectLabel.object_id` shall reach a `Track` or a `WasteObject` through
the detection path.

`AC-TRACK-46`: When a pixel footprint is converted into the belt frame, the
system shall scale it at the object's estimated upper surface rather than at the
belt plane, and shall record where that height came from.

`AC-TRACK-47`: When the decode yield is reported, the system shall state both
denominators, meaning decodes per object crossing the gate and decodes per
object inside a code camera's measured lateral band.

`AC-TRACK-48`: The system shall place the `GroundTruth` refusal on the only path
by which evidence enters a track, so that no caller reaches a track without
passing it.

`AC-TRACK-49`: When any field of `WasteObject` derives from `GroundTruth` rather
than from a sensor, the record shall disclose that, so a reader can separate
what was perceived from what was supplied without reading the code.

`AC-TRACK-50`: The system shall state how every adapter derives its
`confidence`, and no adapter shall report a constant without naming in its
documentation why the constant is correct.

`AC-TRACK-51`: When a class receives zero weight from every folded payload, the
posterior shall remain a proper distribution under a floor that is configuration
rather than a constant in code.

`AC-TRACK-52`: When the barcode decoder runs in the quality gate, it shall
decode a committed fixture, so that a zero rendered yield reports a property of
the optics rather than a broken decoder.

`AC-TRACK-53`: When evidence arrives out of order, meaning an observation older
than the track's last update, the system shall not weight it above a newer one.

## Traceability

Ids are append-only and never reused. `AC-TRACK-01` through `AC-TRACK-26` are
new; nothing in the repository used the `TRACK` prefix before this spec. Tests
name the id they guard in a test name or a comment, so the mapping is greppable
in both directions.

`AC-MIGRATE-01` is satisfied in part by the direct implementation work the
roadmap records beside this spec, which renames `Check::Stroke` and corrects
the comments that named the previous manipulator. That work is not part of this
spec and lands separately.

## Design notes

**Why the documents move and not the frame.** Three places state that the belt
frame has its origin at the upstream edge with `z` up from the belt surface:
`docs/perception-contract.md`, `crates/clave-decision/src/pose.rs` and
`configs/runtime/sitl.yml`. Every coordinate on the wire is MuJoCo world, with
the belt from -1.50 m to +1.50 m, the arm base at (0, -0.70, 0.90) and the belt
surface at 0.90 m. Translating to the documented frame would touch the committed
golden vectors, which `crates/clave-decision/contract/vectors/v1/README.md`
freezes on the grounds that a vector that changes proves nothing, along with the
envelope JSON and every measurement. The sentence is what is wrong.

**Why association is a protocol with a ground-truth implementation.** The
contract's change table promises that swapping the tracker changes nothing
downstream. That promise is only testable if something else already sits on the
far side of the seam. Shipping the ground-truth implementation here means
`learned-tracker` is measured against a working system rather than against
nothing, and it means this spec can be validated before any model exists.

**What the `Detection` adapter actually sees, and the trap in it.**
`src/clave/data/recorder.py` derives exact per-object pixel bounds from a MuJoCo
segmentation render, which is what an instance segmenter produces. The adapter
converts those bounds to a belt-frame footprint.

The conversion needs a height and cannot use a constant. Under a nadir camera
the scale factor is set by the object's upper surface rather than by the belt
plane, so applying the belt-plane factor inflates the footprint of a 0.10 m
object by 13.3 percent and a 0.15 m one by 21.4 percent. That error feeds
`grasp_point`, `grasp_width` and the mass band, which is why the contract pairs
`Height` with `Detection` and why `AC-TRACK-10` cannot be satisfied by a
multiplication.

The trap is identity. `_boxes_from_segmentation` keys its result on the MuJoCo
geometry name, which is `object_<slot>`, and `clave.world.belt.Conveyor._place`
makes that slot the same integer as `SpawnedObject.index`, which
`clave.runtime.loop._labels` then hands out as `ObjectLabel.object_id`. The mask
key and the simulator's object identity are the same number. So the segmentation
render does carry cross-frame identity, and an adapter that passes the key
through would hand the tracker the answer while appearing to perceive it.
`AC-TRACK-45` requires the key to be discarded at the adapter boundary and a
test to prove nothing downstream can recover it.

What remains true is narrower and worth stating exactly. The simulator supplies
a per-frame instance mask, which is what a real segmenter supplies; it also
supplies a name that a real segmenter would not, and that name is thrown away.
Nothing here removes segmentation from the simulator, and no number this
produces is evidence that pixels were segmented by a model.

**Why the barcode decoder is worth building at the yield it actually has.** The
YCB package textures carry real printed UPC-A symbols, and they render legibly
through the gate code camera at roughly 1.9 pixels per module, matching the
figure `docs/measurements.md` derives from the EAN-13 module width. The path
works end to end: over five seeds a stock detector read `037600138727` off a
rendered gate frame, a genuine Hormel GTIN on the potted meat can, correctly an
`M-06`.

The yield is the finding. Of 45 gate crossings, 29 fell inside a code camera's
measured lateral band and one decoded, which is 3.4 percent per readable
presentation and 2.2 percent per object on the belt. `AC-TRACK-47` requires both
denominators because a single figure here is misleading in either direction.
Rectification does not rescue it: cropping to the object's segmentation bounds
drops the yield to zero by clipping the barcode's quiet zone, and upscaling that
crop fourfold only returns it to what the raw frame already gave, so the adapter
decodes the full gate frame and carries no rectification step it cannot justify.

Two causes are separable and both are real. A barcode wrapped around a can
foreshortens non-linearly under a nadir view, which is a property of the sensor
arrangement rather than a defect in the decoder and is why a real line uses
omnidirectional readers. And the three code cameras do not tile the belt, so a
third of the width is never presented to one at all.

The fusion rules are therefore tested against constructed `Code` evidence and
hold whatever the decoder achieves, and `AC-TRACK-52` keeps a committed fixture
on the gate so a future zero is read as optics rather than as breakage.

**Why mass is a band.** Density times footprint volume is weak, because a
bottle empty or half full differs tenfold and that difference decides whether a
suction cup holds. A single number invites a consumer to trust it. Where a GTIN
resolves, the packaging mass replaces the estimate and the band narrows, which
is the one case where the code is close to decisive.

**What this spec does not settle.** How the material posterior is parameterized,
and whether `reject` is a predicted class or an absence of confidence. Both
change a training loss and belong with the model.
`docs/perception-contract.md` already declines to settle them and this spec
follows it. Tracking through occlusion is likewise out: objects travel in a
single layer under a nadir camera, so two objects that touch and segment as one
are a failure this spec describes and `learned-tracker` is asked to state an
outcome for.
