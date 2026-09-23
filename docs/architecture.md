# Architecture

How CLAVE turns a frame from a simulated conveyor into a pick decision another
project can act on, and where the boundaries between its parts fall.

[README.md](../README.md) states the problem this solves.
[measurements.md](measurements.md) carries the numbers quoted here and how each
one was obtained. This document describes the system as it stands; it does not
narrate how it got there, which is what git and the tags are for.

## The split

Python perceives and proposes. Rust checks and decides. The two never share an
address space: they meet at a JSON datagram over a Unix socket, and the crate
that can override a model links no tensor library.

That boundary is the whole point rather than an accident. A safety layer that
loaded the model would inherit its version of a tensor library, its export step,
and its failure modes, so it could not claim to fail differently from the thing
it checks. The cost is one process hop and the latency it adds, which is
measured rather than assumed.

```
MuJoCo world ──frame + joints──► Predictor ──Proposal (JSON)──► [process boundary]
                                                                       │
                                     Rust: Envelope ──► Resolver ──► PickDecision (CBOR)
                                                                       │
                                                  ROS 2 /clave/pick_decisions ──► FRET
```

## Blocks

### World

`clave.world`, holding `scene`, `belt`, `arm`, `objects` and `config`.

A MuJoCo model built from YAML: a conveyor, scanned waste objects, a UR10e
manipulator on a pedestal beside the belt, and the bins each material class
routes to.
Every tunable comes from configuration, and a missing key fails at load naming
itself, because a numeric default buried in Python is a default nobody reviews.

| In | Out |
| --- | --- |
| Scene configuration and a seed | Rendered frames from each configured camera, arm joint values, object labels with position and material class, reachable window geometry |

### The arm

A Universal Robots UR10e, adopted from MuJoCo Menagerie and vendored under
`third_party/mujoco_menagerie_ur10e/`. A validated model derived from
manufacturer CAD outranked an arm authored here, and one model is copied rather
than a 2.3 GB collection pinned to obtain 35 MB of it.

**Six axes serve a four-axis task.** The line needs a position over the belt and
a rotation of the tool about the vertical, with the tool held pointing down. Two
degrees of freedom are surplus. That is deliberate and it is the price of the
fidelity requirement in [CONTRIBUTING.md](../CONTRIBUTING.md): the machines that
suit this task exactly, a SCARA or a delta, have no validated open model.

**There is no prismatic axis and none can be made.** Locking revolute joints
removes freedom; it never produces translation along a fixed axis. A vertical
descent is a task-space constraint instead: inverse kinematics is solved at each
waypoint with the tool axis held down, which is what an industrial linear move
does.

Reachability follows from that. A six-axis arm under an orientation constraint
has no closed-form workspace, so the region the system trusts was **measured by
sweeping the compiled model**, not derived from link lengths:

| Bound | Trusted | Measured |
| --- | --- | --- |
| Inner radius | 0.25 m | unreachable inside 0.200 m |
| Outer radius | 1.25 m | 1.266 m to 1.309 m by bearing |
| Vertical band about the base | -0.05 m to +0.45 m | solutions past both ends |

Every trusted bound sits inside the measured one, so the region under-permits
rather than over-permits. `clave.world.arm.reaches` applies it, and the safety
envelope carries the same numbers, so the proposer and the checker cannot read
the same geometry two ways. A test re-sweeps the region and fails if any point
it admits stops solving.

Unlike the arm it replaced, axis 1 turns plus or minus 360 degrees, so the
annulus has no missing wedge.

#### Where it stands

Beside the belt, on a pedestal, at 0.70 m from the centreline.

| Option | Belt coverage | Why not chosen |
| --- | --- | --- |
| **Pedestal beside the belt, 0.60 to 0.75 m out** | the full 1.00 m | chosen |
| Pedestal at 0.85 m or further | misses the far edge | Past 0.75 m the far edge leaves the annulus |
| Inverted on a gantry | almost nothing | A six-axis arm above a plane is near-singular pointing straight down; a sweep found 3 of 27 sample points reachable |
| A smaller arm such as the UR5e | needs a narrower belt | 0.923 m of reach misses the far edge at every offset tried |

The pedestal is a parallelepiped from the floor to the arm's mounting face. It
is machine frame and nothing measures it, but an arm floating at working height
describes no installation anybody could build. Its half-diagonal stays inside
the 0.25 m inner radius, so the arm cannot drive into the support carrying it.

#### Cycle time

The line carries a budget of **1.0 second** from a published decision to the
effector reaching the pick point. It is a target rather than a derivation:
published pick-and-place cycles put delta robots near 0.3 s, SCARAs at 0.28 to
0.50 s, six-axis industrial arms at 0.4 to 0.8 s, and collaborative arms behind
all three.

**It is unmeasured, not met.** Nothing in CLAVE grasps, so the harness reports
cycle time as unmeasured rather than passing a gate vacuously.

### Sensing

Cameras are a list in configuration, each with an `id`, a `role`, a position
and an optical description. Nothing downstream reads a camera directly: the
tracker fuses by role, and [perception-contract.md](perception-contract.md)
specifies the record every consumer actually reads.

All of them look straight down. A nadir view keeps the image plane parallel to
the belt, so pixel to world is a scale factor rather than a homography that
varies across the frame, an object's footprint in pixels is its footprint on the
belt, and a barcode lies parallel to the sensor where it is most legible.
Objects travel in a single layer, so from directly above nothing occludes
anything. A tilt buys a little height information and costs all of that, so the
tilted views in this repository are for presentation stills only.

The cameras form a **gate** upstream of the arm. An object is seen once, under
controlled light, and is then carried to the arm by a belt whose speed is known,
so the tracker propagates it by dead reckoning rather than re-detecting it in
every frame.

| Sensor | Role | Parts | Across the belt | Along travel | Resolution |
| --- | --- | --- | --- | --- | --- |
| `gate_wide` | detection | IMX264 + Fujinon 8 mm | 1.100 m | 0.920 m | 0.449 mm per pixel |
| `gate_code_left`, `_center`, `_right` | code | IMX264 + Fujinon 16 mm | 0.385 m each | 0.322 m each | 0.157 mm per pixel |

A camera names the parts it is built from and the field of view is derived, so
an angle in this repository cannot drift away from hardware anybody could order.
The sensor is a Sony IMX264, 2/3 inch and 2448 by 2048 at a 3.45 micrometre
pitch; the lenses are Fujinon HF-XA-5M, specified for that sensor class.

The long sensor axis lies across the belt rather than along it. `fovy` is a
vertical field of view and therefore sets the across-belt axis for a nadir
camera, so a sensor laid out along travel spends its long side on the direction
the object crosses anyway and leaves its short side to cover the width. Turning
every camera a quarter turn is most of why the gate covers the belt at all.

Both roles cover the full 1.00 m width, swept and recorded in
[measurements.md](measurements.md). The three code cameras stand 0.33 m apart
while each sees 0.385 m across, so they overlap and tile the belt instead of
sampling it.

The split between the two roles is forced by arithmetic rather than chosen. An
EAN-13 narrow module is about 0.33 mm, and decoding wants roughly two pixels
across it, so 0.165 mm per pixel is the floor. The wide camera is nearly three
times coarser than that, which is ample for detecting and classifying an object
and useless for reading its barcode. The code cameras reach 0.157 mm per pixel.

### Predictor

`clave.runtime.inference`, behind the `Predictor` protocol.

| In | Out |
| --- | --- |
| Frame, arm joints, object labels, window exit coordinate | `Prediction` with object id, material class, confidence and pick point, or `None` when nothing should be picked |

Two implementations satisfy that protocol. `ScriptedPredictor` is the expert the
policies imitate, choosing the reachable object nearest the window exit because
it has the least time remaining. It sees world state rather than pixels, so it
proves nothing about perception and exists so the boundary, the safety layer and
the publisher can run on a machine with no deep learning framework installed.
`CheckpointPredictor` loads the trained models and is where reported figures come
from.

The object id is not recovered from pixels. `associate()` matches the predicted
point to the nearest labeled object within a radius, so identity is ground truth
borrowed from the simulator. The proposal loop has no tracker yet, and this is
where one plugs in. The operator harness in `clave.sim` already drives
`clave.tracker` and `clave.control` together for debug runs, separate from the
proposal path to Rust.

### Learned stages

Perception and policy are separate models, trained separately by supervised
imitation of the scripted expert. No reinforcement learning runs anywhere in the
repository: the arm is inert during data collection, so no reward can be earned.
`ppo-mlp` appears in the candidate registry, but it is built against a stock
gym environment purely to obtain observation and action shapes for a forward
pass benchmark, and it is never trained or stepped.

| Stage | In | Out | Loss |
| --- | --- | --- | --- |
| Perception | Frame, `(B, 3, 96, 96)` float32 | `(B, 11)` logits, one per material class | Binary cross entropy, multilabel because several objects share a frame |
| Policy | Frame plus arm state `(B, 6)` | `(B, 3)` pick point in meters | Mean squared error against the position the expert chose |

Candidates live behind one interface in `clave.candidates`, described without
being loaded so the registry is readable on a machine with none of the heavy
libraries installed. That property is what keeps the quality gate independent of
PyTorch.

### Proposal boundary

`clave.runtime.proposal` encodes, `clave.runtime.bridge` carries, and
`crates/clave-safety` reads. The format is stated once, in
`crates/clave-safety/contract/proposal.md`.

A proposal carries the object id, material class, confidence, pick point, yaw,
and the instants bounding the reachable window. The encoder validates before
sending, refusing anything the runtime would refuse, because a producer that
ships a bad message and reads the complaint back has learned nothing the local
check could not have told it.

### Safety

`crates/clave-safety`, under the hardened lint tier.

| In | Out |
| --- | --- |
| Proposal, plus an `Envelope` read from configuration | `Verdict::Accepted`, or `Overridden` naming the check that refused |

The envelope holds the arm base, the reach radius, the belt surface height and
the belt extents. Four checks run against it: `Reach`, `ToolHeight`,
`BeltSurface` and `BeltExtent`. A proposal that survives all four becomes a
decision; one that does not is overridden and the failing check travels back to
the caller.

### Routing

`crates/clave-routing` turns a material class and a confidence into a channel.
Channel numbers belong to the line rather than to the taxonomy, so they are
configuration. Anything below the confidence floor goes to the reject channel
whatever its class.

### Decision contract

`crates/clave-decision` defines `PickDecision`, carrying a version, the object
id, material class, channel, pose, window and confidence. It is CBOR on the
wire, specified by `pick-decision.cddl` and pinned by committed golden vectors,
so an outside consumer implements the specification rather than mirroring the
Rust source.

The constructor enforces the one invariant binding two fields: the pose has to
be predicted for an instant inside the window. That makes "the pose the object
will hold when the effector arrives" a checked property rather than a comment.
The object identity is carried through, never minted and never rewritten.

A message carrying an unrecognized version is refused whole, and no field past
the version is read.

### Publication

`crates/clave-publish` handles the transport with its latency counters and
overflow policy. `clave.ros.publisher` maps a decision onto
`vision_msgs/Detection3D` on `/clave/pick_decisions`, which is what FRET's
pick and place state machine consumes. The mapping is computed before ROS is
touched, so it is testable on a machine with no ROS installation.

## Taxonomy

Eleven material classes, `M-01` to `M-11`, defined in
[waste-taxonomy.md](waste-taxonomy.md) and grounded in recovery facility
practice. Identifiers are append-only. The classifier's output head is sized to
that count, so changing the taxonomy changes every trained head.

Three of the eleven sit in groups a color camera cannot fully separate. The
validation gates treat those named confusions more loosely than ordinary errors
on purpose, asking whether a model is worse than the sensor limit rather than
whether it is perfect.

## Reproducibility

No binary lands in git. Corpora resolve through `corpora/manifest.toml` with
checksums, meshes come from pinned submodules, and benchmark inputs are
generated from a seed through one seeding entry point rather than downloaded.
A training run records its configuration digest, its dataset digest and its
environment, so a figure can be traced to the world that produced it.

## Debug narrative

`clave sim --log-level DEBUG` tells the visit as it happens: why the queue
changed, which object the arm committed to and by which phases, whether the
jaw closed, which chute the object crossed, and the collisions, acceleration
spikes, and losses of control a watch reports when an episode begins. A
physics tick and a capture that repeat the same decision are not lines. The
sentences
and the watches are specified in
[requirements/simulation-narrative.md](requirements/simulation-narrative.md).
The watch does not command the arm. `--no-progress` turns the step bar off
so it does not redraw over those lines.

## What is absent

Naming these here keeps a reader from inferring them from the presence of
nearby machinery.

- **No tracker.** Object identity is ground truth from the simulator.
- **No reinforcement learning.** Every trained model is supervised.
- **No grasping.** The gripper has never closed on an object, so pick success
  rate and cycle time are unmeasurable by construction rather than unmeasured
  by omission.
- **No hardware.** Nothing in this repository has touched a camera, a belt or
  an arm, and no number in it describes real world accuracy.
