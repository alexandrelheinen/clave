# Perception record, tasks

Ordered so that each task lands a failing test first, and so that no task
depends on one below it. Every task names the criteria it closes, and a task is
done when `./scripts/validate.sh` exits 0 rather than when it looks finished.

Tasks 1 through 4 need no render, no MuJoCo and no OpenCV, which is deliberate:
the geometry and the fusion arithmetic are provable from literals, and pushing
them first means the parts that need a GPU-adjacent path arrive after the rules
they feed are already locked in.

## 1. The belt frame and the clock

- [ ] `belt_frame.py` with `Footprint`, `propagate`, `elapsed_seconds`.
- [ ] Ban `time.monotonic_ns` inside the package and add the test that greps for
  it, so every instant stays an argument.
- [ ] `NadirOptics.metres_per_pixel(height_meters, render_height)`, taking the
  object's upper surface rather than the belt plane, and taking the render size
  separately from `SensorSpec.resolution`.
- [ ] Derive the window exit from `ReachReport.window_edges[1]` rather than
  `window_length / 2.0`, and correct `clave.runtime.loop` to read the same.

Closes `AC-TRACK-01`, `AC-TRACK-03`, `AC-TRACK-04`, `AC-TRACK-24`,
`AC-TRACK-46`. `AC-TRACK-05` is already closed on the fix branch.

## 2. Evidence, sensors and the intake gate

- [ ] `evidence.py`: `Role`, the five payloads, the `Evidence` envelope, with
  `__post_init__` refusing a payload that carries a channel or a grasp.
- [ ] `sensors.py`: read the `cameras` block into `SensorSpec`, look up by role,
  never by id.
- [ ] `intake.py`: `Deployment`, and a gate that refuses `GroundTruth` under
  `HARDWARE` naming the source that offered it.
- [ ] Put the gate on the only path into a track, so no caller reaches `Tracker`
  around it, and test that the bypass does not exist.
- [ ] Remove the two `DETECTION_CAMERA = "gate_wide"` constants in
  `clave.data.recorder` and `clave.runtime.loop`, resolving by role instead.
- [ ] Add the test that no camera id declared in `configs/world/sorting_line.yml`
  appears as a string literal under `src/clave`. It fails on the current tree at
  `recorder.py:24` and `loop.py:28`, verified.

Closes `AC-TRACK-06`, `AC-TRACK-07`, `AC-TRACK-08`, `AC-TRACK-48`, and the
non-vacuous half of `AC-TRACK-25`.

## 3. The posterior, the fold and the mass band

- [ ] `fusion.py`: the twelve-slot posterior with a configured floor.
- [ ] `weight_of(confidence, elapsed_seconds)` accepting no `source_id`, with
  elapsed clamped at zero.
- [ ] The fold table as an explicit dict with one documented miss branch.
- [ ] The mass band over `clave.world.config.Range`, narrowing when a GTIN
  resolved a packaging mass.
- [ ] The source-swap test: fold two disagreeing readings, fold them again with
  `source_id` and `role` exchanged, assert equality to 1e-12.
- [ ] The out-of-order test: fold a reading older than `last_updated` and assert
  it does not outweigh the newer one.

Closes `AC-TRACK-09`, `AC-TRACK-18`, `AC-TRACK-19`, `AC-TRACK-22`,
`AC-TRACK-51`, `AC-TRACK-53`.

## 4. Tracks, the seam and the record

- [ ] `association.py`: `Cue` as a closed six-field dataclass, `Association`,
  the `Associator` protocol.
- [ ] `SimulatorIdentity`, asymmetric by design: a `GroundTruth` cue matches by
  `object_id`, a `Detection` cue matches geometrically against the propagated
  footprint. Name it so no reader mistakes it for perception.
- [ ] `track.py`: `Track`, `WasteObject` with `provenance` and without
  `channel`, grasp geometry as computed properties, `settle`.
- [ ] `tracker.py`: the one mutable driver.
- [ ] `tests/tracker/association_contract.py`, a shared conformance suite not
  named `*_test.py`, so `learned-tracker` runs the identical clauses against its
  model.
- [ ] Correct `docs/perception-contract.md` to drop `channel` from the record
  listing, in the same change, so the two cannot disagree.

Closes `AC-TRACK-16`, `AC-TRACK-17`, `AC-TRACK-20`, `AC-TRACK-21`,
`AC-TRACK-23`, `AC-TRACK-26`, `AC-TRACK-49`.

## 5. The detection adapter

- [ ] `adapters/render.py` as the only MuJoCo importer, importing inside its
  functions.
- [ ] `PixelMask` as run-length triples, so the adapter's input is a literal.
- [ ] Second-moment extraction for the oriented footprint, with `oriented` set
  false when the eigenvalues are too close to separate.
- [ ] Discard the geometry name, and add the test that no value in the resulting
  `Evidence`, `Track` or `WasteObject` is derivable from the producing object's
  `object_id`.
- [ ] The resolution-invariance test: render one instant at 320 by 240 and 640
  by 480 and assert the belt-frame centres agree to a millimetre.

Closes `AC-TRACK-02`, `AC-TRACK-10`, `AC-TRACK-45`.

## 6. Codes and the catalog

- [ ] `codes.py`: symbology, the UPC-A and EAN-13 check digit computed here
  rather than trusted from the detector, the decoder protocol, the OpenCV
  implementation.
- [ ] `configs/perception/packaging.yml`, GTIN to a packaging bill of materials,
  including `037600138727` which the potted meat can actually carries.
- [ ] The code-derived prior, weighted by which component is plausibly the one
  being looked at, never overriding a confident visual reading.
- [ ] An unknown GTIN yields a `Code` with no bill of materials.
- [ ] Move `opencv-python-headless` into the `dev` extra so the decoder runs on
  the gate, and add the committed fixture it must decode.

Closes `AC-TRACK-11`, `AC-TRACK-12`, `AC-TRACK-13`, `AC-TRACK-14`,
`AC-TRACK-50`, `AC-TRACK-52`.

## 7. The yield measurement

- [ ] `measure_decode_yield` behind a `FrameSource` protocol so the counting is
  testable against a fake.
- [ ] Report every denominator: decodes per object crossing the gate, and
  decodes per object inside a code camera's measured band.
- [ ] Record the achieved figures in `docs/measurements.md`. The current
  measurement is 1 decode over 29 readable presentations and 45 crossings across
  five seeds, so 3.4 percent and 2.2 percent.

Closes `AC-TRACK-15`, `AC-TRACK-47`.

## 8. The sensor-change proof and the sweep

- [ ] Add a fifth camera of an existing role in a test fixture, assert the
  record's key set is unchanged, and assert the new `source_id` reached a
  track's contributor set so the test is not vacuous.
- [ ] Assert that removing the camera producing a configured role fails at load
  rather than emitting records silently missing it.

Closes `AC-TRACK-25`, `AC-TRACK-25b`.

## Not in this spec

The runtime swap and the latency budget are `AC-TRACK-41` in `learned-tracker`,
because swapping the runtime onto a record whose identity still comes from the
simulator would change what is published without changing what is known.

Widening `gate_wide` from 45 degrees to about 62 so the detection camera covers
the belt is a `sorting-world` change awaiting a decision, recorded in the
roadmap with its blast radius. This spec measures against the gate as it stands.
