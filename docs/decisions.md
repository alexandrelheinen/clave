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

## D-09: the object set is real and covers four classes instead of six

**Date**: 2026-09-15 · **Step**: v1.0.4, a patch to the world of v0.5.0

**The standard**: `AC-ASSET-02` in the `sorting-world` spec asks that the object
set cover at least six of the taxonomy's material classes, and
`tests/world/objects_test.py` enforces it. The set that satisfied it was eight
parametric primitives, whose material was chosen in a configuration file and
whose appearance was a colored cylinder.

**What was scoped**: every object is now a scanned package, and the set covers
four classes: `M-02` high-density polyethylene, `M-04` other plastics, `M-06`
ferrous metal and `M-09` paperboard. `AC-ASSET-02` is not satisfied and the
test now asserts four with a reference to this entry.

**Why**: the gripper on the pinned OpenMANIPULATOR-X opens 55.7 mm, measured
from its finger meshes. Every scanned object in the collections this project
pins was measured against that: 1,030 in Google's Scanned Objects and 87 across
two YCB sets. 276 fit under 52 mm, and of those the ones that are recyclable
packaging rather than plant saucers, hard drives or toys reach four classes.

Nothing made of the missing six fits. A soda can is 66 mm across, a bleach
bottle 68 mm, a mustard bottle 67 mm, the narrowest drinking cup 57 mm, and no
glass container in either collection is under 52 mm at all.

So the choice was between six classes of colored cylinders and four classes of
photographs. [v0.6.0](research/data-pipeline.md) already recorded what the
primitives cost: "a classifier trained only on them learns shape rather than
material". Four real classes teach a classifier something a camera could
recognize; six synthetic ones teach it that PET is a yellow cylinder.

**What this costs, stated plainly**:

1. **Two classes fewer than the criterion asks for**, and six of eleven with no
   object at all.
2. **The material label is now inferred rather than true by construction.** A
   supplement tub is taken as HDPE and a candy carton as paperboard, from what
   the package is. The synthetic world knew each object's material because it
   chose it. This is label noise that did not exist before.
3. **The class balance is worse.** Six of the fourteen objects are paperboard
   and one is metal, because that is what fits.

**Reversal condition**: a wider gripper. At about 72 mm the set gains the
mustard bottle, the tomato soup can, the bleach cleanser and the cracker box,
which adds nothing new to the class list; at 85 mm it gains drinking cups for
`M-03`. Glass and aluminum need a container neither collection has at any size,
so those two classes need a different source rather than a different arm.
Restoring the primitives would satisfy the criterion in the same commit that
undoes the reason for this entry.

## D-10: the SCARA is built rather than adapted from an existing arm model

**Date**: 2026-09-16 · **Step**: the SCARA migration

**The standard**: `docs/guidelines.md` and the family's asset policy say to
reference a maintained upstream model rather than vendor a hand-built one, which
is why the manipulator, the meshes and the conveyor modules all arrive through
pinned submodules.

**What was scoped**: `src/clave/world/mjcf/irb910sc.xml` is written in this repository
instead of adapted from a model in MuJoCo Menagerie, the ROBOTIS collection, or
the `robot_descriptions` catalog.

**Why not lock axes on an existing arm.** The obvious cheap route is to take a
Franka Panda, an FR3, an LBR iiwa 14 or a UFactory Lite 6 and freeze joints
until four remain. It does not work, and the reason is topology rather than
tuning. A SCARA is **RRPR**: two revolute axes about the vertical, one
*prismatic* vertical axis, then one revolute about the vertical. Every arm named
above is all-revolute, RRRRRR or RRRRRRR. Freezing a joint removes a degree of
freedom; it never converts a revolute joint into a prismatic one, so the P in
RRPR has no source. What a locked six-axis arm actually produces is a four-axis
all-revolute arm whose vertical motion comes from coordinated pitch joints, so
height and radius stay coupled: it moves inward as it moves down. A SCARA's
vertical axis is decoupled by construction, and that decoupling is the property
the pick depends on.

The workspaces differ in shape as well as size. A SCARA sweeps an annulus,
0.222 m to 0.650 m here, extruded over a 0.180 m stroke. A locked revolute arm
sweeps a spherical shell with singularities in different places. Reach coverage,
which is what CLAVE measures, would be measured on the wrong solid.

The speeds differ by more than an order of magnitude where it counts. ABB
publishes axis 4 at 2400 deg/s and a 1 kg picking cycle of 0.385 s. A Panda's
joints run near 150 deg/s. Picks per minute is the headline number of a sorting
line, so simulating a Panda and labeling it a SCARA would put a figure in the
benchmark that no SCARA would ever produce.

**What this gives up**, stated plainly: vendor-validated inertia tensors,
collision meshes matching the real housings, and joint friction and damping
identified against hardware. The model carries link lengths, joint ranges, joint
speeds, stroke and footprint from ABB's published specification, and inertias
inferred from primitive geometry at a uniform density.

**Why that is acceptable here**: CLAVE measures reachability and timing. It runs
no torque control, no force control and no contact-rich manipulation, so
inertial accuracy changes settling behavior rather than whether a point falls
inside the workspace. The moment CLAVE does force control, this model needs
re-derivation from a real inertial model, and that is a reversal condition
rather than a detail.

**Precedent**: FRET built its own SCARA the same way, as
`src/fret/urdf/scara.xacro`, a parametric model over primitives with independent
kinematic parameters, L1 0.325 m and L2 0.275 m over a 0.200 m stroke. That file
was removed when FRET moved to the OpenMANIPULATOR-X. Building from published
kinematics is the family's established approach for this class of arm rather
than an invention here.

**Reversal condition**: if a validated SCARA model appears in Menagerie or
`robot_descriptions` under a usable license, adopt it and delete this asset. If
CLAVE takes on force control, re-derive the inertias first.

## D-11: a wider effector does not recover the missing material classes

**Date**: 2026-09-16 · **Step**: the SCARA migration

**The standard**: `AC-ASSET-02` asks the object set to cover at least six
material classes. `D-09` recorded that it covers four, and named the 55.7 mm
gripper as the cause.

**What was scoped**: the object set covers four classes after the re-selection,
the same four as before. `AC-ASSET-02` remains unmet.

**What changed and what did not**: the SCARA carries a suction cup rather than a
parallel jaw, so the selection bound is the 0.180 m spline stroke rather than a
gripper opening, and no width limit applies at all. Measuring every one of the
1,030 scanned models and the pinned YCB subset against the new bound put 836 of
them inside it, against 153 under the old one. Four YCB packages the jaw had
refused are now in the set: a 102.5 mm master chef can, a tomato soup can, a
potted meat can and a mustard bottle. Ferrous metal went from one object to
four, which matters because the benchmark recorded it as the weakest supported
class.

**Why the classes stayed empty**: they were never blocked by the effector.
Searching both collections for the missing types returns nothing usable. There
is no PET bottle, no individual aluminum beverage can, no glass container, no
corrugated box and no beverage carton. What the "jar" search finds is a shelf of
JarroDophilus supplement bottles, which are HDPE. What the "can" search finds is
12-pack trays, which are corrugated multipacks rather than the cans inside them.
Exactly one bottle exists among the 836 models that fit.

`D-09` attributed the gap to the gripper, and this measurement shows that was
the wrong cause. Google Scanned Objects is a retail-shelf scan of toys, shoes,
supplements and electronics, and the pinned YCB subset is ten manipulation
benchmark items. Neither is a waste stream, and no change to the arm makes them
one.

**Reversal condition**: adopting an asset source that actually contains beverage
and container packaging closes this. Until one lands, a claim that CLAVE sorts
eleven material classes is not supportable by the world it runs.

## D-12: the behavior-cloning baseline barely transfers to a realistic line

**Date**: 2026-09-16 · **Step**: the SCARA migration

**The standard**: `workflow/tdd.md` and the project's own reporting rules say a
demonstration shows what the system does rather than what it was hoped to do.

**What was scoped**: `runs/demos/trained-models.mp4` records a configuration
that publishes 5 decisions over 25 simulated seconds. That is a working loop
running on a policy that is mostly wrong, and the number is reported rather than
presented as a success.

**What was measured**: retraining both candidates on a world-matched dataset,
the classifier is fine and the policy is weak. `resnet50-baseline` reaches 0.997
confidence on held-out frames, well clear of the 0.30 presence floor. The policy
regresses a pick point 0.445 m from the expert's choice on average, and the
runtime associates a prediction to an object only within 0.12 m, so only 7 of
134 demonstrations produce a usable proposal.

Dataset size is what moved it off zero and not much further. At 150 frames and
26 demonstrations the policy proposed nothing at all in a 25 second run. At 982
frames and 134 demonstrations it proposes enough to publish 5 decisions, while
the mean error moved only from 0.434 m to 0.445 m. Training to convergence does
not help either: the loss plateaus at 0.0126 after 150 epochs and stays there.

**Why**: the baseline is a 0.02 M parameter network chosen at v0.4.0 as the
deliberate simple comparator, and it worked while the reachable workspace was
0.24 m across. It is now 1.3 m across, and 0.44 m of error is about what
predicting the mean of that spread produces. The model has learned roughly the
mean, which is the expected behavior of a network that small regressing world
coordinates over a range that large from a 96 by 96 frame.

**What is not scoped**: the classifier, the scripted expert, the safety layer
and the publisher all work. `runs/demos/sorting-line.mp4` shows the scripted
expert publishing 6 decisions with zero safety overrides, and the trained
configuration publishes 5 with zero overrides at 54.5 ms median latency, so the
path from frame to published decision is intact end to end.

**Reversal condition**: a policy that predicts a pick point relative to the
object rather than in world coordinates, or one with capacity matched to the
workspace, should close this. Either is a model change rather than a
configuration change, so it belongs in its own step.

## D-13: the manipulator is a UR10e from Menagerie, and two of its axes go unused

**Date**: 2026-09-16 · **Step**: the SCARA migration

**This reverses D-10.** That entry argued a SCARA had to be built here because
no validated model exists, and dismissed the cost with "appearance does not
enter any measurement CLAVE takes". The premise was wrong rather than
mispriced. CLAVE publishes stills and videos, those are how the project reads
to anyone who does not run it, and the hand-built arm rendered as capsules on a
stick. `CONTRIBUTING.md` now carries physical fidelity as a requirement, and
this entry is what that requirement decides.

**What was scoped**: the arm is a Universal Robots UR10e from MuJoCo Menagerie,
on a pedestal beside the belt. The hand-built SCARA is deleted. `AC-ARM` claims
about cycle time are withdrawn until something grasps.

### Why this one

**Practical.** Menagerie carries 72 models and not one parallel mechanism: no
delta, no Stewart platform, no SCARA, no gantry. The machines that suit this
task best are the ones nobody has published. Among what exists, the UR10e is
the only arm that covers a 1.00 m belt. Sweeping inverse kinematics with the
tool held vertical, it reaches every lateral position from a pedestal 0.60 m to
0.75 m off the centreline. A UR5e misses the far edge at every offset tried,
and every other candidate reaches under 0.95 m where the UR10e reaches 1.308 m.

**Risk.** A delta is the right machine and was costed honestly. URDF cannot
express a closed kinematic chain, so a delta description carries meshes and
broken loops and nothing else; the loop closures would be hand-authored
`equality/connect` constraints, which is exactly where MuJoCo users report
instability, and closed chains usually want a smaller timestep than the 0.002 s
this project runs. That is an unbounded schedule risk against a bounded one.

**Reality.** Universal Robots arms are deployed in recycling and logistics, so
the scene depicts a configuration somebody actually runs rather than a
plausible-looking assembly. The model is BSD-3-Clause and maintained by people
who are not us.

**Precision.** The model is derived from the vendor's published URDF through a
documented pipeline and carries 20 CAD meshes. Its geometry is checkable
against something outside this repository, which is what no arm authored here
can offer.

### What it costs

**It is slower, and that is the headline cost.** Published pick-and-place cycle
times put delta robots near 0.3 s and above 120 cycles a minute, SCARAs at 0.28
to 0.50 s at their sweet spot, six-axis industrial arms at 0.4 to 0.8 s, and
collaborative arms such as the UR10e slowest of the four because their safety
envelope limits acceleration. A line built on this arm gives up most of the
throughput a delta would deliver.

That cost is currently theoretical, which is why it is acceptable now and will
not stay acceptable. Nothing in CLAVE grasps, and `D-12` records the policy at
0.445 m of pick-point error, so the project cannot substantiate any
picks-per-minute figure with any manipulator. The moment it can, this trade is
worth reopening.

**Two degrees of freedom go unused.** The task needs four: a position over the
belt and a rotation of the tool about the vertical, with the tool held pointing
down. The UR10e has six. The surplus is not wasted in the sense of being
harmful, because redundancy buys obstacle avoidance the SCARA never had, but a
reader should know the arm is deliberately operated below its capability and
that no part of CLAVE exercises its full pose freedom.

**Vertical motion is a task-space constraint rather than a joint.** No arm in
Menagerie has a prismatic axis and none can be given one: locking revolute
joints removes freedom and never creates translation. A vertical descent is
achieved by solving inverse kinematics at every waypoint with the tool held
down, which is what an industrial linear move does. It follows that the
workspace is not a closed-form annulus and has to be swept numerically, which
`clave.world.arm` does.

**Reversal condition**: a validated delta or SCARA model appearing in Menagerie
or an equivalent collection, or CLAVE reaching the point where throughput is
measurable and the cycle time above becomes a real constraint rather than a
note.

## D-14: one Menagerie model is copied rather than the collection pinned

**Date**: 2026-09-17 · **Step**: the manipulator migration

**The standard**: [roadmap.md](../.kiro/steering/roadmap.md) says assets are
referenced and never vendored. Meshes arrive through pinned submodules, which is
how the ROBOTIS arms, the YCB objects and the scanned packages all reach this
repository.

**What was scoped**: `third_party/mujoco_menagerie_ur10e/` is a verbatim copy of
one directory from MuJoCo Menagerie at commit `8161bba2`, committed here rather
than pinned as a submodule.

**Why**: Menagerie is a single repository holding 72 models and 2.3 GB. CLAVE
uses one of them, 35 MB. CI checks out submodules recursively on every job, so
pinning the collection would move 2.3 GB to obtain 1.5 percent of it, on every
run, forever. There is no sparse form of a submodule that `actions/checkout`
will honor.

The files are ASCII OBJ rather than binaries, so this does not breach the
separate rule that no binary lands in git. It costs a one-time 35 MB in history
and nothing per clone after that.

**What is not scoped**: the provenance. `PROVENANCE.md` in that directory names
the upstream commit, keeps the model's own `LICENSE` and `CHANGELOG`, and states
how to update it. Nothing in the directory is edited. The physical fidelity
requirement in `CONTRIBUTING.md` asks for a model derived from manufacturer CAD
and maintained outside this repository, and a copy satisfies both as long as it
stays a copy.

**Reversal condition**: Menagerie publishing per-model repositories or releases,
or `actions/checkout` gaining sparse submodule support, makes pinning cheap
enough to prefer.

## D-15: a published figure may carry geometry, never an overlay

**Date**: 2026-09-17 · **Step**: the published visuals

**The standard**: [agents/claude.md](../standards/guidelines/agents/claude.md),
No fabricated evidence, forbids post-processed overlays on captured output and
decorative output presented as real feedback. A test sends one flat gray frame
through the encoder and reads the same gray back, which proves nothing is drawn
on a frame after the renderer made it.

**What was scoped**: the three figures the project page publishes carry a ring
at the arm's reach radii, a plane at each end of the reachable window, and a
marker over each package in the color of the channel it routes to.

**Why**: a still of the line shows a belt and an arm, and the page's argument is
about where the arm can reach and how long an object stays there. A reader
cannot see a workspace. The choice is between explaining it and publishing a
figure that illustrates nothing.

**Why this is not an overlay**: every one of those shapes is geometry standing
in the scene before the model is compiled, so the renderer produces it with the
perspective, occlusion and shadow of everything else, and the encoder still
writes exactly the pixels it was handed. The flat-gray test is untouched.

**What is not scoped**: the quantities. A radius is read from the resolved
layout, a window edge from the same sweep the safety layer consults, and a
marker's color from the taxonomy channel of the object it stands over. Nothing
in the still's own file states a distance, so a figure cannot describe a
workspace the world does not have.

**What it costs**: the annotations reach the scene as an argument whose default
adds nothing, the same way presentation lighting does, and they add no body, no
coordinate, no degree of freedom and no mass. A test asserts that against a
world built without them. The videos carry none of this: they run the measured
loop, and the trained models read the frames it renders.

**Reversal condition**: a figure whose annotation cannot be derived from the
world would have to be drawn somewhere else and labeled as a diagram, not
published as a render.

## D-16: the gate is specified as commercial optics, and the belt is covered

**Date**: 2026-09-17 · **Step**: Block D, ahead of `perception-record`

**The standard**: [CONTRIBUTING.md](../CONTRIBUTING.md), Physical fidelity, asks
that hardware appearing in what CLAVE publishes come from something real rather
than be authored here. `docs/architecture.md` states that the cameras form a
gate the belt passes through.

**What was measured**: the gate did not cover the belt, and no document said so.
Stepping one object laterally and reading the segmentation render, `gate_wide`
returned pixels over 0.800 m of a 1.00 m belt while `spawn.lateral_offset_meters`
places objects out to 0.42 m, so the detection camera could not see every object
it exists to detect. The three code cameras covered 73 percent with a dead band
of about 0.10 m on each side where no barcode could be read at all.

**Why it went unnoticed**: `fovy` is a vertical field of view, so it sets the
image height axis, and for a nadir camera whose image is wider than it is tall
that axis lies across the belt. Every figure this project quoted as what a
camera "covers across" was the along-travel extent, which is the larger of the
two. The tables read as though the gate covered 1.252 m of a 1.00 m belt.

**What was scoped**: a camera now names the parts it is built from and the field
of view is derived from them. `configs/world/sorting_line.yml` carries a
`sensors` catalog and a `lenses` catalog, and each camera names one of each plus
which belt axis its long sensor side spans. `fovy_degrees` is no longer a
configurable key, and a test refuses one.

The parts are a Sony IMX264, 2/3 inch, 2448 by 2048 at a 3.45 micrometre pitch,
and Fujinon HF-XA-5M C-mount lenses, which are specified for exactly that sensor
class. `gate_wide` takes the 8 mm at a 1.042 m standoff and the code cameras
take the 16 mm at 0.730 m. Every camera is turned a quarter turn so its long
axis lies across the belt.

**What that buys**: both roles now cover the full width, swept and recorded in
[measurements.md](measurements.md). The code cameras stand 0.33 m apart while
each sees 0.385 m, so they overlap rather than butt together, and they resolve
0.157 mm per pixel against a 0.165 mm floor. Decode yield went from 2.2 percent
of objects to 4.4 percent, with every crossing now readable rather than 64
percent of them.

**Why turning the cameras was most of it**: a sensor laid out along belt travel
spends its long side on a direction the object crosses anyway and leaves its
short side to cover the width it has to see. That was free to correct and it is
the larger half of the gain; the lens and the standoff supply the rest.

**What it costs**: every frame `gate_wide` renders is different, so the world
digest changes and the checkpoints trained at v0.7.0 saw a gate that no longer
exists. That cost is smaller than it looks. `D-12` already records those models
as barely transferring, at 0.445 m of policy error, and the recorded dataset
under `datasets/synthetic` already carried a `config_digest` that did not match
the working tree and four arm joints where the `UR10e` has six, so it described
the previous manipulator's world before this change touched anything.

**What is not scoped**: the render sizes. The models still see 320 by 240, which
is a landscape aspect against a portrait sensor, so a rendered frame spans more
belt along travel than the sensor would. Across-belt coverage is unaffected,
because it depends only on `fovy` and the standoff, and the decode figures above
were measured at the sensor's own 2448 pixels. Matching the render aspect to the
sensor changes what every trained model sees and belongs with the step that
retrains them.

**Reversal condition**: a line whose belt is wider than 1.10 m, or a standoff
the building cannot give, needs a different focal length from the same series
rather than a wider angle invented here. The catalog is the constraint, and a
camera naming a part the catalog does not declare now fails at load.

## D-17: one overlay is allowed, and it is quarantined from everything published

**Date**: 2026-09-19 · **Step**: `tracker-debug-view`

**The standard**: [agents/claude.md](../standards/guidelines/agents/claude.md),
No fabricated evidence, forbids post-processed overlays on captured output.
`D-15` records that a published figure may carry geometry standing in the scene
and never an overlay, and a flat-gray test proves nothing is drawn on a frame
after the renderer made it.

**What was scoped**: `clave.tracker.debug_view` draws the tracker's records onto
a rendered frame. Boxes, labels, and a full property listing, all of it painted
on afterwards, which is exactly the shape the rule forbids.

**Why this is not the thing the rule prohibits**: a published figure argues
something to a reader who cannot run the code, so anything drawn on it is a
claim they have no way to check, and the honest answer is to put the geometry in
the scene where the renderer produces it with everything else. A debug view
argues nothing. It is read by somebody with the records open beside it, and its
entire purpose is to show which number belongs to which place. Applying the rule
here would not protect a reader, it would remove the only way to see the
algorithm work.

**What the separation rests on**: not a convention. `debug_view` imports nothing
from `clave.demo` and never touches `open_recorder`, and a test asserts both.
Debug output goes to `runs/debug/` through OpenCV rather than through the
encoder the figures use. The flat-gray tests guarding `demo` and `still` are
untouched and still pass. Every frame carries a caption saying it is a debug
render of the tracker alone.

**What keeps it honest**: every value drawn is read from a `WasteObject` field
and none is computed for display, proved by a test that compares each drawn
string against the record it annotates. And every field is drawn rather than a
chosen subset, because choosing what to show is choosing what to miss: the
defect that motivated this view was one object running as two tracks, visible
only in the `evidence` set, which a view showing footprint and material would
have hidden behind two plausible boxes.

**What is not scoped**: publication. No frame this produces may appear in
`docs/images/`, in the README, or in any artifact presented as what CLAVE sees.
A figure needs the `D-15` treatment, which is geometry in the scene.

**Reversal condition**: if a debug frame is ever published, this entry is what
was violated, and the fix is to build the figure the way `D-15` requires rather
than to loosen this.
