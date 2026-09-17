# Brief: perception-record

## Problem

Object identity in CLAVE is ground truth borrowed from the simulator, and every
consumer downstream already speaks as though it were not. `clave-decision`
documents its object id as "the identity the tracker assigned",
`configs/world/sorting_line.yml` names a module `clave.tracker` that has never
been written, and `docs/perception-contract.md` specifies a record no code
produces. The gap is not a missing optimization. It is the reason no number this
project reports is evidence that identity was recovered from observation.

The operator of a sorting line pays for that gap twice. A barcode read at the
gate cannot be attached to an object picked a metre downstream, because nothing
holds the object between the two events. And every sensor added to the line
edits every consumer, because there is no record standing between them.

## Current State

`associate()` in `src/clave/runtime/inference.py` matches a proposed pick point
to the nearest labeled object within `association_radius_meters`, which is
0.12 m. The labels come from the simulator. Nothing propagates an observation
through time, nothing fuses two sensors, and the four cameras the world
configures are read by exactly one consumer, which takes the wide one by name
and ignores the other three.

Two measured facts shape what is buildable. `src/clave/data/recorder.py` already
derives exact per-object pixel bounds from a MuJoCo segmentation render, which
is what an instance segmenter produces and what a `Detection` adapter needs.
And the YCB package textures carry real printed UPC-A barcodes that survive to
a rendered gate frame at roughly 1.9 pixels per module, so a decoder has
something real to read.

The belt frame is the third fact, and it is a defect.
`docs/perception-contract.md`, `crates/clave-decision/src/pose.rs` and
`configs/runtime/sitl.yml` all state that the frame has its origin at the
upstream edge of the working area with `z` measured up from the belt surface.
Every coordinate actually on the wire is MuJoCo world: the belt runs from
x = -1.50 m to x = +1.50 m, the arm base sits at (0, -0.70, 0.90), and the belt
surface is z = 0.90. The frame the contract names is not the frame the code
uses, which is fatal to a contract whose first invariant is that there is one
frame.

## Desired Outcome

`clave.tracker` exists and produces `WasteObject` records from `Evidence`. An
observation taken at one instant can be propagated to any later instant by belt
speed. A barcode decoded at the gate resolves to a bill of materials and
contributes a prior that never overrides a confident visual reading. Adding a
camera to `configs/world/sorting_line.yml` changes that file and nothing else,
proved by a test rather than asserted in a document.

The association rule sits behind one protocol with one implementation, so that
`learned-tracker` replaces the implementation without touching anything above
it.

## Approach

Build the contract as code, bottom up, leaving the association algorithm as the
one hole.

The belt frame is corrected by amending the three documents that describe it
rather than by translating every coordinate on the wire. The contract's sentence
is what is wrong; moving the origin would invalidate the committed golden
vectors, the envelope JSON and every measured coordinate in
`docs/measurements.md` in exchange for a tidier origin.

Evidence, its five payload variants, `Track` and `WasteObject` become frozen
dataclasses carrying monotonic instants. Propagation is one function over belt
speed and elapsed time. The `Detection` adapter reads a segmentation render, the
`GroundTruth` adapter reads world state and is refused when the runtime is
configured for hardware, and the `Code` adapter decodes UPC-A and EAN-13 from
the three narrow gate cameras and resolves the digits through a committed
bill-of-materials table.

Association is a protocol. Its only implementation here is the one that reads
the simulator's object id, named so that no reader mistakes it for perception,
and it is what `learned-tracker` replaces.

## Scope

- **In**: the belt frame correction, the `Evidence` envelope and its five
  payloads, `Track`, `WasteObject`, monotonic propagation by belt speed, the
  `Detection` and `GroundTruth` adapters, the barcode decoder, the GTIN to
  bill-of-materials resolver, the material posterior and its conflict rule, the
  mass band, the association protocol, and the test that proves adding a sensor
  edits one file.
- **Out**: the association algorithm itself, which is `learned-tracker`. The end
  effector, which is specified separately and is why no grasp criterion appears.
  Training or retraining perception and policy models. The object set, settled
  by `D-11`. The R2 upload application.

## Boundary Candidates

- The belt frame and the clock, which everything else rests on and which nothing
  else depends on.
- The evidence envelope and its payloads, which are data and carry no behavior.
- The adapters, one per sensor role, each of which knows about exactly one
  sensor and is the only code that does.
- The fusion rules, meaning the material posterior, the code prior and the mass
  band, which are arithmetic over evidence and testable without a sensor.
- The association protocol, which is the seam `learned-tracker` plugs into.

## Out of Boundary

- Any learned component. This spec trains nothing and loads no checkpoint.
- Whether `reject` is a predicted class or an absence of confidence, which
  `docs/perception-contract.md` leaves open and which belongs with the model.
- Tracking through occlusion, and the two-objects-segmented-as-one failure. This
  spec states what happens; preventing it is a model problem.

## Upstream / Downstream

- **Upstream**: `waste-taxonomy` for the eleven classes, `sorting-world` for the
  camera list and the segmentation render, `data-pipeline` for the recorder,
  `pick-decision-contract` for `BeltPoint` and the published record.
- **Downstream**: `learned-tracker`, which supplies the association
  implementation. `sitl-runtime`, whose `associate()` this eventually replaces.

## Existing Spec Touchpoints

- **Extends**: `sitl-runtime`, which owns `associate()` and the runtime
  configuration key that sizes it. `pick-decision-contract`, whose `pose.rs`
  carries one of the three false belt-frame statements.
- **Adjacent**: `sorting-world` owns the camera list this reads and must not
  gain knowledge of the tracker. `data-pipeline` owns the recorder whose
  segmentation output the `Detection` adapter consumes.

## Constraints

- **One frame and one clock.** Both invariants in
  `docs/perception-contract.md` are non-negotiable, which is why the frame
  defect is fixed here rather than worked around.
- **A variant states what was measured, never what should be done.** No adapter
  resolves a channel or a grasp.
- **Adding a payload variant is additive.** A consumer that does not know a
  variant keeps working, because it reads the fused record.
- **`GroundTruth` travels the path real sensors travel**, so the training
  pipeline cannot come to depend on a shape that exists only in simulation. A
  runtime configured for hardware refuses it at the adapter boundary.
- **Conflict resolves by recency and confidence, never by source priority**,
  because trusting a sensor for being that sensor means adding one silently
  reorders the rest.
- **The decode yield is measured and reported, not assumed.** A stock detector
  reads one of seven YCB textures at full resolution, before curvature, pose and
  gate-camera sampling take their cut. Whatever the rendered yield turns out to
  be is the number that gets published.
