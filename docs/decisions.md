# Decisions

An append-only log of places where a gate or a constraint was deliberately
scoped, loosened, or changed, with the reason. Anyone asking "why is this weaker
than the standards say" should find the answer here.

Entries are never edited once landed. A decision that is reversed gets a new
entry saying so.

## D-01: the candidate adapters are outside the coverage denominator

**Date**: 2026-09-14 · **Step**: v0.4.0 `model-candidates`

**The standard**: `workflow/tdd.md` gates line coverage at 80 to 90 percent on
core library code and forbids lowering a gate to make CI pass.

**What was scoped**: `src/clave/candidates/perception.py` and
`src/clave/candidates/policy.py` are omitted from the coverage denominator. The
80 percent floor is unchanged and applies to everything else.

**Why**: those two modules are adapter shims. Each function is two or three
lines calling an upstream constructor, and none can execute without PyTorch,
torchvision, lerobot, diffusers or stable-baselines3, which together exceed a
gigabyte. The gate deliberately does not install them, because the platform's
contract is that the registry is readable and the rest of the system testable
without any of them.

Testing them with mocks would assert that a constructor was called with the
arguments the test passed it, which proves nothing about whether the
architecture loads. Their real test is the benchmark sweep, which loads every
one from upstream and whose output is committed as
[docs/research/model-candidates.md](research/model-candidates.md).

**What is not scoped**: `tests/candidates/adapters_test.py` does exercise the
adapters through `pytest.importorskip`, so on a machine with the libraries
installed they run. They simply do not count toward the floor, because a
coverage number that swings by fifteen points depending on whether an optional
library happens to be present measures the environment rather than the tests.

**Reversal condition**: if the candidate libraries ever become required rather
than optional, this entry is superseded and the modules return to the
denominator.

## D-02: the decision socket is an AF_UNIX datagram rather than SOCK_SEQPACKET

**Date**: 2026-09-14 · **Step**: `pick-decision-contract`, which is off the v0.x ladder

**The standard**: the approved design for `pick-decision-contract` selects a
Unix domain socket in `SOCK_SEQPACKET` mode, opened through
`std::os::unix::net`, and forbids a third-party transport dependency.

**What was scoped**: `clave-publish` opens an `AF_UNIX` socket in `SOCK_DGRAM`
mode instead, through `std::os::unix::net::UnixDatagram`.

**Why**: the standard library exposes no way to open a `SOCK_SEQPACKET`
socket. `std::os::unix::net` gives `UnixStream` for `SOCK_STREAM` and
`UnixDatagram` for `SOCK_DGRAM`, and nothing else. Opening a seqpacket socket
means calling `socket(AF_UNIX, SOCK_SEQPACKET, 0)` through `libc`, which brings
both a third-party dependency the design forbids and an `unsafe` block into a
crate that declares `#![forbid(unsafe_code)]`.

Every property the transport choice rested on survives the substitution. An
`AF_UNIX` datagram socket on Linux is reliable, delivers in order, and keeps
one record per send, so record boundaries still come from the kernel and the
framing bug class a length-prefixed stream would introduce is still absent. It
is testable in process through `UnixDatagram::pair()`, which is what the
no-hardware constraint needs.

**What is not scoped**: the sink trait, the discard policy in front of it, and
the counters are unchanged, so a later seqpacket or shared-memory sink slots in
behind the same seam without touching the policy.

**What changes**: a datagram socket is connectionless, so a departed consumer
surfaces as `ECONNREFUSED` where a seqpacket socket would report a broken
connection. Both map to a refusal, which is the behavior the requirement asks
for either way.

**Reversal condition**: if the standard library gains seqpacket support, or if
a measurement on the target board shows the datagram path is the constraint,
the sink is replaced behind the existing trait and this entry is superseded.

## D-03: the confidence field is float32 on the wire

**Date**: 2026-09-14 · **Step**: `pick-decision-contract`, which is off the v0.x ladder

**The standard**: the approved design names `Confidence(f32)` in its Rust
interface and `float64` in its data contract table. The two cannot both hold.

**What was scoped**: the wire carries the confidence as a CBOR four byte float,
matching the Rust type. The published CDDL schema and the golden vectors say
`float32`, and the design's table row is superseded.

**Why**: widening to `float64` on the wire would make decoding lossy in the
narrowing direction, and Rust offers no checked `f64` to `f32` conversion, so
the codec would need an `as` cast in a crate where `clippy::as_conversions` is
denied. Keeping one width end to end costs four bytes per message and keeps the
round trip exact, which is what the round trip requirement asks for. Every
other float in the contract stays `float64`.

**Reversal condition**: a classifier that genuinely reports confidence at
double precision. Widening the field raises the contract version, the same as
any other shape change.
## D-04: the named confusion gate is looser than the per-class accuracy gate

**Date**: 2026-09-14 · **Step**: v0.8.0 `validation-harness`

**The standard**: the gates in `configs/validation/gates.yml` apply one bar to
classification quality, and a validation harness that sets an easier bar for the
errors a model is most likely to make is a harness that grades on a curve.

**What was scoped**: `max_named_confusion_rate` is 0.35, while
`min_per_class_accuracy` is 0.60, which is an error ceiling of 0.40. The looser
number applies only to the three groups
[docs/waste-taxonomy.md](waste-taxonomy.md) names as unresolvable from a color
image: `M-01` against `M-03` against `M-04` when transparent, `M-05` against
`M-06`, and `M-08` against `M-09` face-on.

**Why**: those three separations are made by near-infrared absorption, by a
magnet, and by an edge-on view of a flute. CLAVE observes the belt with a color
camera and has none of them. Holding a color-only classifier to the same bar
inside those groups as outside them would gate on a sensor CLAVE does not have,
and the run would fail for a reason no amount of training changes.

The gate still exists because the groups carry real signal a model should learn:
beverage cans are taller and narrower than food cans, opaque PET and PP differ,
and a corrugated box seen from any angle but face-on shows its flute. A rate
above 0.35 inside a group means the model has not learned the signal that is
there, which is a training problem and not a sensor limit. The gate separates
those two cases, which is the whole reason the taxonomy asked for these three to
be reported by name.

**What is not scoped**: the named confusions stay inside the general confusion
matrix and inside overall accuracy, both of which apply the ordinary bar. This
entry loosens one gate, not the aggregate.

**Reversal condition**: a near-infrared or magnetic sensor entering the pipeline
removes the reason for this gate, at which point the three groups return to the
ordinary per-class bar. A first measurement showing a trained candidate well
under 0.35 is also reason to tighten it, since a gate nothing ever approaches
gates nothing.

## D-05: Python runs inference and Rust never loads a model

**Date**: 2026-09-14 · **Step**: v0.9.0 `sitl-runtime`

**The standard**: [docs/guidelines.md](guidelines.md) and
`.kiro/steering/tech.md` both say the inference runtime is chosen at the
learning-platform step. v0.3.0 deferred it, and nothing since has chosen it, so
the standard names a decision that was never made.

**What was scoped**: Python runs every model and Rust runs none. The two
processes exchange a versioned JSON proposal over a Unix datagram, specified in
`crates/clave-safety/contract/proposal.md`. No Rust crate in this workspace
links a machine learning framework, and a test on the safety crate's manifest
checks that.

**Why**: the safety layer earns its place by being unable to fail the way the
model fails. A crate that loaded the model would share its tensor library, its
export step, and its version skew, and "inference proposes, a deterministic
layer disposes" would describe two halves of one dependency rather than two
independent things.

Three alternatives were considered:

| Option | Why not |
| --- | --- |
| Export to ONNX and run it in Rust through `ort` | Adds a large native dependency to the component the gate cannot do without, plus an export step that can diverge from the trained model without saying so |
| TorchScript through `tch-rs` | Links libtorch into the crate that most needs to stay small enough to audit |
| Reimplement the architectures in a pure Rust framework | Two implementations of one architecture, drifting apart from the first bug fix |

**What is not scoped**: the transport. v0.10.0 hands the decision to FRET over
ROS 2 and may replace the datagram with something else. What this entry fixes is
which side owns inference, not which pipe carries the result.

**The cost, measured**: a process boundary adds a round trip that an in-process
design would not pay. `docs/research/sitl-runtime.md` reports the measured
frame-to-decision latency against the per-object time budget, so the price of
this decision is a number rather than an assertion.

**Reversal condition**: a measurement showing the boundary consuming a
meaningful share of the per-object budget. At that point the honest move is a
shared-memory transport rather than linking a model into the safety crate, since
the property being protected is the absence of shared code and not the presence
of a socket.

## D-06: the decision reaches ROS 2 as a standard message, not a CLAVE one

**Date**: 2026-09-15 · **Step**: v0.10.0 `decision-publisher`

**The standard**: `standards/guidelines/workflow/sdd.md` asks that a
cross-project boundary be specified before it is implemented, and CLAVE already
publishes a decision under a CDDL schema with golden vectors. Adding a second
encoding of the same decision needs a reason and a rule for keeping the two
honest.

**What was scoped**: CLAVE publishes `vision_msgs/msg/Detection3DArray` on
`/clave/pick_decisions`, mapped in
`crates/clave-decision/contract/ros-decision.md`. No ROS interface package is
defined in this repository. The material class and the resolved channel travel
as two hypotheses in one detection, read by prefix, and the window duration
travels in `bbox.size.x`.

**Why a standard type**: defining a message means an interface package, which
means `rosidl` and a colcon build inside a repository whose gate is cargo and
pytest. A consumer would then need to build CLAVE's package before it could
subscribe. A standard type costs two documented reuses of a field and buys a
subscriber that needs nothing from here, plus `ros2 topic echo`, `rosbag` and
RViz working with no plugin.

**Why two hypotheses rather than one**: an object below the confidence floor
keeps its material class and goes to the reject channel, so a decision carries
`M-01` and `channel:0` at the same time. A consumer that recomputed the channel
from the class would defeat the floor. `ObjectHypothesisWithPose` is a labeled
assertion with a score, which is what both of these are.

**Why the window rides in `bbox`**: a `Detection3D` carries a bounding box, and
CLAVE estimates a pick point rather than an object extent, so the field would
otherwise be zeroed. A decision without its window cannot be checked for
staleness by a subscriber that received it late. The reuse is documented in the
contract rather than left for a reader to infer, and it is the one place in the
mapping where a field is used for something other than its name.

**What keeps the two encodings honest**: the ROS publisher decodes the CBOR that
was published. It never builds a message from the proposal that produced the
decision, which would be easier and would create a second path free to drift
from the contract with no test noticing. The Python decoder is tested against
the committed golden vectors, which is the same check a consumer in another
language runs.

**Reversal condition**: FRET writing the subscriber and finding the two reuses
confusing or insufficient. At that point an interface package becomes the better
trade, and the cost is a colcon build this repository does not have today.

## D-07: a record with no prediction carries no decision latency

**Date**: 2026-09-15 · **Step**: v1.0.0 `benchmark-suite`

**The standard**: `ObjectOutcome.decision_latency_seconds` was a required float,
and `ValidationSummary` summarized it over every record. v0.8.0 shipped that way
and nothing had produced a real record yet.

**What was scoped**: the field is now `float | None`, a record whose
`predicted_class` is absent must carry `None`, and the latency summary is taken
over the records that carry a value.

**Why**: the benchmark is the first thing to produce records from a live run,
and a run presents objects the system says nothing about. Under the old shape
each of those needed a number, and the only available number was zero. Zero is
not a missing measurement; it reads as a decision taken instantly, and enough of
them would drag a p99 below the budget while the system was in fact deciding
nothing at all.

The alternative was to drop the undecided objects from the record set. That
would have been worse, because it would also drop them from the confusion
matrix, and an object the system never classified is exactly the kind of failure
a sorting line cares about.

**What is not scoped**: `cycle_time_seconds` was already optional and is
unchanged. No threshold moved.

**Reversal condition**: none expected. If a later design makes every presented
object carry a decision by construction, the `None` branch becomes dead rather
than wrong.

## D-08: the world is sized to its manipulator, and the old measurements stand

**Date**: 2026-09-15 · **Step**: v1.0.1, a patch to the world of v0.5.0

**The standard**: v0.5.0 built a conveyor two meters long and half a meter wide,
running at up to 0.30 m/s, carrying objects 60 to 220 mm across, with the arm
0.34 m from the centerline and a declared reach of 0.38 m. Every measurement
from v0.5.0 to v1.0.0 was taken in that world.

**What was scoped**: the belt is now 1.20 m by 0.16 m at 0.04 to 0.10 m/s, the
arm sits 0.14 m from the centerline with a declared reach of 0.25 m, and objects
are 38 to 44 mm across. Reachability is a distance in three dimensions rather
than a coordinate along belt travel. `clave.world.objects` refuses to build a
world whose objects exceed the gripper's opening.

**Why**: three measurements, all in
[world-scale.md](research/world-scale.md). The gripper's clear opening is 55.7
mm, taken from the finger mesh vertices, and not one of the eight objects fit
inside it. The effector covers ground at about 0.10 m/s while the belt ran up to
three times faster. And a forward kinematics sweep over 83,521 joint
combinations put the effector at most 0.266 m from its base in the grasp band,
which means the arm could not reach the middle of its own belt.

The last of those explains a number this project had been reporting for two
releases without understanding it. v1.0.0 recorded that 65 percent of the
recommended configuration's proposals were overridden and called the safety
layer's work evidence that it was not decorative. Most of that work was refusing
picks that were geometrically impossible rather than badly chosen. After the
rescale the control is overridden 2.2 percent of the time instead of 47.

**What is not scoped**: the gates. `max_decision_latency_p99_seconds` stays at
0.45 s although the time budget rose from 1.13 s to 4.14 s, because a gate
tighter than the physics demands costs nothing and moving it is a decision
rather than an edit.

**What this invalidates**: every accuracy, latency and composition figure taken
before this describes a different world. The dataset was re-recorded, all three
candidates retrained, and the benchmark rerun.
[benchmark.md](research/benchmark.md) carries the rescaled numbers. The reports
for v0.5.0, v0.6.0, v0.7.0 and v0.9.0 carry a note at the top pointing here and
are otherwise left standing, because they record what was measured at the time
and rewriting them would erase the trail that led to this entry.

**Reversal condition**: a larger gripper. The object set is small because the
gripper is, and a line sorting real household packaging needs one that opens two
to three times wider, which is a different arm rather than a different number.
