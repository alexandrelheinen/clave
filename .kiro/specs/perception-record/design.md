# Perception record, design

How `clave.tracker` satisfies `requirements.md`, and which decisions are load
bearing enough that changing one would change the rest.

Three independent designs were produced under different angles and judged
against every criterion. This document takes the structure of the one that
scored highest, grafts what the others found, and repairs the flaws the
judges exposed in all three. Where a choice was contested, the reason it went
one way is stated rather than left as taste.

## What the design has to survive

Four properties, each of which killed at least one proposal.

**Identity cannot leak through the detection path.** The segmentation render is
keyed by the MuJoCo geometry name, and that name is the simulator's object id.
An adapter that passes it through hands the tracker the answer.

**The seam has to be narrow enough to diff.** `learned-tracker` replaces one
implementation and nothing else. If what an associator may read is a discipline
rather than a type, that promise is unenforceable.

**Out-of-order evidence has to weigh less, not more.** The contract anticipates
two cameras firing 8 ms apart. A recency weight of the form `k ** elapsed`
inverts when elapsed is negative, which makes the older reading win in exactly
the case the criterion exists for.

**The gate has to be on the only path.** A refusal on a boundary object that
nothing forces callers through is opt-in, and an opt-in refusal of
`GroundTruth` on hardware is not a refusal.

## Modules

Ten modules under `src/clave/tracker/`. The three proposals ran to eighteen and
nineteen, which the judges called out: sixteen new error classes for one spec
buys separation nobody asked for and costs a reader the ability to hold the
package in their head. Modules merge here wherever two of them shared a reason
to change.

| Module | Holds | Imports nothing heavier than |
| --- | --- | --- |
| `belt_frame.py` | `Footprint`, propagation, elapsed time, the nadir projection from pixels to belt metres | `clave.world.config` |
| `evidence.py` | `Role`, the five payloads, the `Evidence` envelope | `belt_frame` |
| `sensors.py` | `SensorSpec` read from the `cameras` block, lookup by role, `NadirOptics` | `clave.world.config` |
| `intake.py` | `Deployment`, and the gate every piece of evidence passes | `evidence`, `sensors` |
| `association.py` | `Cue`, `Association`, the `Associator` protocol, `SimulatorIdentity` | `belt_frame`, `evidence` |
| `fusion.py` | the posterior, the recency weight, the fold table, the mass band | `clave.taxonomy`, `evidence` |
| `track.py` | `Track`, `WasteObject`, `settle` | `fusion`, `belt_frame` |
| `tracker.py` | the one mutable driver that owns state and calls the rest | everything above |
| `codes.py` | symbology, check digits, the decoder protocol, the GTIN catalog | `belt_frame` |
| `adapters/` | one module per role, plus `render.py` | the above, and MuJoCo in one file |

`adapters/render.py` is the only module in the package that imports MuJoCo, and
it does so inside its functions. Nothing else in `clave.tracker` imports MuJoCo,
OpenCV or torch at module scope, so the whole package is importable on the
quality gate and most of it is testable without a render.

`Range` comes from `clave.world.config` rather than a new interval type. Two
interval types in one repository is how two of them drift.

## The seam

Everything the two-spec split promises rests on three names.

```python
@dataclass(frozen=True)
class Cue:
    """Everything an associator may look at, and nothing else."""

    observed_at_nanos: int
    footprint: Footprint | None
    digits: str | None
    pick_point: tuple[float, float, float] | None
    height_meters: float | None
    previous: TrackSummary | None


class Associator(Protocol):
    """Decides which track an observation belongs to."""

    @property
    def name(self) -> str: ...

    def associate(self, cue: Cue, tracks: tuple[Track, ...]) -> Association: ...
```

`Cue` is a closed six-field type, and that is the point. `AC-TRACK-32` in
`learned-tracker` says the model is presented with the footprint, the pick
point, an optional code and the previous track state and with nothing else.
Making that a type rather than a rule turns it into something a reviewer checks
by reading one dataclass, and turns `AC-TRACK-26` and `AC-TRACK-42` into a diff
of one file.

An associator is a pure function of its two arguments. It reads no clock, opens
no file, draws no random number and keeps nothing between calls. Every track it
receives has already been propagated to `cue.observed_at_nanos` by the caller,
so no implementation dead reckons and `belt_frame.propagate` has exactly one
call site. `Tracker` is what holds state.

Returning an `Association` whose `track_id` is `None` means open a new track.
Returning the nearest track at any distance would let an observation of empty
belt join a real object's history, which is the mistake `associate()` in
`clave.runtime.inference` already declines to make and the one thing about it
worth keeping.

## How the ground-truth associator works, which is where two proposals failed

Both losing designs shipped a `SimulatorIdentity` that reads `object_id` off
the evidence, and both therefore could not associate a `Detection`, because
`AC-TRACK-45` requires the detection path to discard the only identity it has.
One raised on every detection; the other invented a handshake between two keys
that cannot be equal.

The resolution is that the ground-truth associator is asymmetric on purpose,
and saying so is what makes it honest.

A `GroundTruth` cue carries the simulator's `object_id` and matches by it
exactly. That is the simulator supplying identity through the path real sensors
use, which is what the payload is for.

A `Detection` cue carries a footprint and no identity at all. It matches the
track whose propagated centre is nearest, inside a gate derived from the track's
own footprint rather than from a constant radius. This is what replaces
`association_radius_meters`, and it is why that key was left at 0.12 m rather
than retuned: the radius stops being a global number.

So the shipped associator is ground truth for the label and geometry for the
pixels, and the module documentation says exactly that. It is the baseline
`learned-tracker` is measured against, and `AC-TRACK-20` requires its name to
leave no room for a reader to mistake it for perception.

## Frame and clock

`time.monotonic_ns` does not appear anywhere inside `clave.tracker`, and a test
greps for it. Every instant is an argument. That single decision is what makes
propagation, recency weighting and `valid_until` provable with integer
literals, and it is why `AC-TRACK-04` can be tested by advancing a number
rather than by stepping a simulation.

`valid_until` comes from `ReachReport.window_edges[1]`, not from
`window_length / 2.0`. The two agree today only because the arm happens to sit
at the origin, so the second is a latent defect that moving the arm would
expose. `clave.runtime.loop` computes the second one, which is the deeper
version of the stale-window fix already landed.

The projection from pixels to belt metres is a scale factor rather than a
homography because every camera looks straight down, but it is not a constant.
Under a nadir camera the scale is set by the object's upper surface, so the
belt-plane factor inflates a 0.10 m object by 13.3 percent and a 0.15 m one by
21.4 percent, and that error feeds `grasp_point`, `grasp_width` and the mass
band. `NadirOptics.metres_per_pixel` therefore takes a height, and the height
comes from `Height` evidence where one exists and from a class prior otherwise,
recorded either way so a reader can tell which.

`SensorSpec.resolution` from the configuration is the sensor's native
resolution. The render height and width the projection actually divides by are a
separate argument, because `configs/data/recording.yml` renders 320 by 240
against cameras declaring 1920 by 1080, and a scale factor fitted to one and
applied to the other is wrong by the ratio. A test renders the same instant at
two sizes and asserts the belt-frame centres agree to a millimetre, which fails
on a leaked pixel coordinate as well as on a bad scale.

## The detection path

`adapters/render.py` produces a `PixelMask` per object. `PixelMask` holds
run-length triples rather than an array, so the whole input surface of the
detection adapter is a literal a test can write, and no test of the adapter
needs MuJoCo.

The adapter discards the geometry name. `AC-TRACK-45` is proved by a test that
runs the full detection path over a rendered frame and asserts that no value
anywhere in the resulting `Evidence`, `Track` or `WasteObject` equals, or is
derivable from, the `ObjectLabel.object_id` of the object that produced it.

`Footprint.oriented` is `False` when the mask's second-moment eigenvalues are
too close to separate. A can under a nadir camera is circular in plan, and a
confident random yaw on a circular footprint is worse than an absent one,
because the safety layer will act on it.

## Codes

The decoder sits behind a protocol with one shipped implementation over
OpenCV. `codes.py` owns the check digit itself rather than trusting the
detector, so `AC-TRACK-12` is testable against digit strings with no image at
all.

The GTIN catalog is `configs/perception/packaging.yml`, mapping a GTIN to a
packaging bill of materials. It resolves to components and not to a material
class, so a jar returning glass, plastic and aluminum states that one of them
carries the label rather than asserting which. An unknown GTIN yields a `Code`
with no bill of materials, never a guess.

`opencv-python-headless` joins the `dev` extra rather than sitting in an extra
the gate skips. One judge caught that a decoder in an ungated extra is new code
the coverage floor absorbs untested, which is the outcome the floor exists to
prevent. `AC-TRACK-52` keeps a committed fixture on the gate, so a zero rendered
yield reads as optics rather than as breakage.

`measure_decode_yield` reports every denominator, because the measured figures
differ by more than a factor of one and a half depending on which is used: 3.4
percent per readable presentation against 2.2 percent per object on the belt.
A single number here misleads in one direction or the other.

## Fusion

`weight_of(confidence, elapsed_seconds)` takes those two arguments and nothing
else. Source priority is not forbidden by a rule; it is unrepresentable,
because no function in `fusion.py` accepts a `source_id`. That is a stronger
reading of `AC-TRACK-19` than a documented ordering, and it is proved by folding
two disagreeing readings, then folding the same two with their `source_id` and
`role` exchanged, and asserting the posteriors agree to 1e-12.

Elapsed time is clamped at zero. Without the clamp, evidence older than the
track's last update produces a negative exponent and a weight above one, so the
stale reading wins. Every test in the losing proposals folded forward, so none
of them would have caught it. `AC-TRACK-53` exists because of that.

The fold table is an explicit dict from payload type to rule, with one
documented miss branch, rather than single dispatch. What happens to a payload
nobody wrote a rule for then has exactly one address to read, which is what
`AC-TRACK-09` asks to be observable.

The posterior keeps a floor from configuration, so a class every payload gave
zero weight stays in a proper distribution. The floor is a configuration key
because a numeric default buried in Python is a default nobody reviews, which is
the rule the world configuration already states about itself.

## The record

`WasteObject` carries no `channel`. The contract lists one and calls it
"resolved by the routing policy, not by perception", which means perception can
only ever write a null there. A field that is always absent is worse than an
absent field, so it is omitted and `docs/perception-contract.md` is corrected in
the same change rather than left to disagree.

Grasp geometry is computed from the footprint rather than stored beside it. A
stored `grasp_axis` can disagree with the footprint it came from; a property
cannot.

`provenance` is the field `AC-TRACK-49` adds and it is the one most likely to be
argued away later, so the reason is here. No per-instance classifier exists in
this repository: the model in `clave.runtime.inference` is whole-frame and
multi-label, and the line carries no spectral sensor. Until a `Material`
producer lands, `material`, `density` and the mass band are restatements of
`GroundTruth.material_class`. A record that does not say so launders a simulator
label into a perceived value, which is precisely what this spec exists to end.

## Where it plugs in, and where it deliberately does not

`perception-record` wires nothing into `clave.runtime.loop`. That is a decision
rather than an omission, and the judges were right that leaving it unstated
makes `AC-TRACK-21` unverifiable, since a record with no readers cannot be shown
to be the only one anybody reads.

So the criterion is proved structurally instead. `Associator` is named in
exactly one module, and the record's own tests construct `Tracker` with a stub
associator defined in the test file. The runtime swap belongs to `AC-TRACK-41`
in `learned-tracker`, because swapping the runtime onto a record whose identity
still comes from the simulator would change what is published without changing
what is known.

Latency is not budgeted here. Nothing in this spec sits on the frame to decision
path until that swap happens, and a budget stated now would be a number nobody
measured. `learned-tracker` inherits the obligation along with the wiring.

## How the sensor-change criterion is proved

Asserting that the record's key set is unchanged when a camera is added is the
criterion's own wording and is close to vacuous on its own. It is paired with a
non-vacuity check that the new camera's `source_id` reached a track's
contributor set, so the test fails if the camera was ignored rather than
absorbed.

Beside it sits the check that actually bites: no `source_id` declared in
`configs/world/sorting_line.yml` may appear as a string literal in any module
under `src/clave`. That test fails on the current tree, at
`clave.data.recorder` and `clave.runtime.loop`, both of which name `gate_wide`
in a constant. Fixing them by resolving the detection camera by role is part of
this work, and after that the test stays failing the first time somebody writes
a camera id into Python.

The criterion was also amended, because its first wording overstated the
contract. Adding a camera of an existing role is one file. A new role, or a
sensor whose output shape differs, legitimately costs one adapter, which is what
the contract's own change table says.

## Rejected alternatives

**A geometric tracker as the deliverable.** Recommended and declined by the
maintainer, who chose a learned association rule over a physical state. The
geometric matcher survives here as the ground-truth associator's detection
branch, where it is a baseline rather than the answer.

**Translating every coordinate into the frame the documents described.** It
would have rewritten frozen golden vectors, the envelope the safety layer loads
and every measured coordinate, to buy a tidier origin. The documents were wrong
and the documents moved.

**Single dispatch for the fold.** Cheaper to write and it hides the miss branch
across as many modules as register a rule.

**A `MassBand` type.** `clave.world.config.Range` already is one.

**Rectifying the barcode before decoding.** Measured rather than argued:
cropping to the object's segmentation bounds drops the yield from 3.4 percent to
zero by clipping the quiet zone, and upscaling that crop fourfold only returns
it to what the raw frame already gave.

## Open, and deliberately so

**Whether `reject` is a predicted class or an absence of confidence.**
`AC-TRACK-16` mandates eleven classes plus reject while the contract declines to
settle the question. This design holds twelve slots and treats the twelfth as a
class, which is the reading the criterion forces, and notes that the contract
should be amended rather than that the criterion should be read loosely.

**What happens when two objects touch and segment as one.** The contract names
it as a failure it describes and does not prevent. `learned-tracker` owes a
stated outcome under `AC-TRACK-38`; this spec owes the record shape that makes
the outcome visible, which is one `track_id` on one `WasteObject` with a
footprint spanning both.

**The gate does not cover the belt.** Recorded against `sorting-world` rather
than worked around here. This design measures against the gate as it stands and
`AC-TRACK-47` publishes both denominators so the optics are visible in the
number.
