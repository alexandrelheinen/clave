# Learned tracker

## Intent

Supply the rule that decides which observation belongs to which object, and
supply it as a learned model rather than as a geometric gate.

`perception-record` builds everything `docs/perception-contract.md` describes
except that rule, and ships one implementation of the association protocol which
reads the simulator's object id. So identity is still ground truth, and the
record says so. This spec replaces that implementation with a trained model and
takes identity away from the simulator for the first time.

The model is given a physical state rather than pixels: the object's footprint,
the proposed pick point, a barcode when one decoded, and the previous state of
the track. It learns the association and the update. That keeps its inputs
quantities the safety layer can also reason about, and it is what distinguishes
this from a classifier bolted onto a distance threshold.

## Scope

**In.** `Stage.TRACKING` and the registry entries it admits. The runtime
configuration key naming a tracking checkpoint. Re-recording rollouts against
the current world. The training adapter that pairs consecutive frames, the
association objective, and the trained candidate. The stated outcome when two
objects cross or touch and segment as one. The runtime swap away from
`associate()`. The comparison against the ground-truth associator.

**Out.** The contract types, the adapters and the fusion rules, which are
`perception-record`. Retraining perception or policy, which is a separate
model change and which the maintainer has placed outside the current focus.
Reinforcement learning, since every trained model in CLAVE is supervised. The
end effector. The object set, which is settled.

## Constraints

- **The model consumes a physical state, not a frame.** Footprint, pick point,
  optional code, previous track state. This is the maintainer's framing, and it
  is what keeps a tracking decision auditable against the same geometry the
  safety layer checks.
- **Identity is derived, never copied.** `object_id` is a training label. It is
  never an input at inference and a test has to prove it.
- **The swap is invisible above the protocol.** Nothing in
  `perception-record`, the runtime, the safety layer or the publisher changes,
  which is the property `docs/perception-contract.md` promises in its change
  table.
- **Training data matches the world it will run in.** The rollouts under
  `datasets/synthetic` carry a `config_digest` that no longer matches
  `configs/world/sorting_line.yml`, and their `arm_joints` has four entries
  rather than the `UR10e`'s six, so they were recorded against the previous
  manipulator and cannot be trained on as they stand.
- **The registry stays readable without the heavy libraries.** A tracking
  candidate is described without being loaded, the same as every other, because
  the quality gate does not install PyTorch.
- **Nothing is claimed on an agent's word.** A candidate is trained when
  `./scripts/validate.sh` exits 0 and the numbers are recorded.
- **An unflattering result is published.** The precedent is already set: a
  working loop running a mostly wrong model was reported as exactly that.

## Acceptance criteria

### The platform gap

`AC-TRACK-27`: The system shall admit a tracking stage alongside perception and
policy, so a tracking candidate has a place in the registry.

`AC-TRACK-28`: The system shall name a tracking checkpoint in the runtime
configuration, in the same shape the perception and policy checkpoints are
named.

`AC-TRACK-29`: When the registry is read on a machine with no deep learning
framework installed, a tracking candidate shall be described without being
loaded.

`AC-TRACK-30`: When rollouts are recorded for tracking, their `config_digest`
shall match the world configuration in the working tree, and a training run
shall refuse a dataset whose digest does not.

### Training

`AC-TRACK-31`: The system shall build training pairs from consecutive frames of
one rollout, using `object_id` as the correspondence label alone.

`AC-TRACK-32`: The system shall present the model with the object footprint, the
pick point, the decoded code where one exists, and the previous track state, and
shall present it with nothing else.

`AC-TRACK-33`: When a model runs at inference, `object_id` shall not be
reachable from its inputs, proved by a test that asserts the input tensor is
constructed without it.

`AC-TRACK-34`: The system shall train a tracking candidate from one command, in
the same shape every other candidate trains.

`AC-TRACK-35`: The system shall record the tracking run's seed, configuration
digest, dataset digest and environment, so a reported figure traces to the world
that produced it.

### Behavior

`AC-TRACK-36`: When a rollout is replayed, the tracker shall hold one identity
per object across its frames, and that identity shall be derived from
observation rather than read from the simulator.

`AC-TRACK-37`: When two objects pass each other, the system shall produce a
stated outcome, and a test shall assert that outcome rather than assert that no
failure occurred.

`AC-TRACK-38`: When two objects touch and are segmented as one, the system shall
produce a stated outcome, and a test shall assert it.

`AC-TRACK-39`: When an observation arrives for an object the tracker has not
seen, the system shall open a new track rather than attach it to the nearest
existing one.

`AC-TRACK-40`: When an object leaves the belt, the system shall retire its track
rather than hold it open, and shall not reuse its `track_id`.

### The swap

`AC-TRACK-41`: When the tracker is in use, the runtime shall consume
`WasteObject` and shall not call `associate()`.

`AC-TRACK-42`: When the association implementation is replaced, no test above
the association protocol shall change, proved by the diff.

`AC-TRACK-43`: The system shall report identity recovery against the
ground-truth associator `perception-record` ships, and shall publish that
comparison whatever it shows.

`AC-TRACK-44`: When a tracking checkpoint is absent, the runtime shall fail
naming it and the command that trains it, rather than falling back to the
ground-truth associator silently.

## Traceability

Ids are append-only and never reused. `AC-TRACK-01` through `AC-TRACK-26` were
spent by the perception record, whose document is in git history; this spec
continues at `AC-TRACK-27` and spends through `AC-TRACK-29`.
[motion-estimate.md](motion-estimate.md) continues at `AC-TRACK-30`, sharing
this prefix because it is the same tracker. Tests name the id they guard in
a test name or a comment.

## Design notes

**Why the inputs are physical.** A tracker fed raw frames would need the
recorder, the dataset and the objective to carry imagery, and its decisions
would be auditable only through the model. Feeding it the footprint, the pick
point, the code and the previous track state means every input already appears
in `WasteObject` or in `Track`, so a wrong association can be examined against
the same numbers the safety layer sees. It also makes the model small enough to
train on rollouts this project can record in an afternoon.

**Why propagation is the input that makes it learnable.** Captures are 0.5 s
apart and the belt runs at about 0.31 m/s, so an object advances roughly
0.157 m between consecutive observations while the objects themselves are
0.05 m to 0.10 m across. Successive detections of one object do not overlap.
Matching on raw position would therefore be matching on a gap larger than the
object, which is why the propagated footprint rather than the observed one is
what the model compares.

**Why the data has to be re-recorded first.** `datasets/synthetic` holds 982
frames across 36 rollouts with per-frame `object_id`, `position`, `bbox` and
capture time, which is exactly the supervision this needs, so no recorder change
is required. But its `config_digest` is `9fd32bba` against the working tree's
`f43162ff`, and its `arm_joints` has four entries where the `UR10e` has six.
Those rollouts describe the previous manipulator's world. Re-recording is a
command rather than a code change, and `AC-TRACK-30` makes the mismatch fail
loudly instead of training quietly on the wrong world.

**What "a stated outcome" means for crossing and merging.**
`docs/perception-contract.md` names two objects segmented as one as a failure it
describes but does not prevent, and objects travel in a single layer under a
nadir camera, so this is rare rather than absent. The requirement is not that
the tracker survive it. The requirement is that whatever it does is written
down, tested, and visible in the record, so a downstream consumer reading two
`WasteObject` values with one `track_id`, or one value where two objects were,
can tell that is what happened.

**Why a ground-truth comparison and not a bare accuracy number.** An identity
accuracy figure on its own says nothing about whether the model beat the thing
it replaced. `perception-record` ships the ground-truth associator precisely so
this number has a denominator, and `AC-TRACK-43` requires the comparison to be
published even when the learned model loses, which follows the precedent of
reporting a model that does not work yet rather than withholding it.

**Where a state estimator would and would not pay.** Nothing in CLAVE
estimates a velocity or a covariance today. Propagation is dead reckoning
with the belt speed taken as known, which it is: it comes from configuration
here and would come from an encoder on a line. `clave-decision` publishes a
zero pose covariance and says in its contract that a zero is more honest than
a fabricated number.

Two questions get confused when a filter is proposed, and the measurements
separate them. Over 231 observations of the shipped world, the residual
between a live grasp point and its anchor carried along the belt has a median
of 0.0 mm, so the estimate carries no bias. Along travel it reaches 72.2 mm
and across the belt 22.3 mm, the second being an order smaller because an
object rides the belt rather than crossing it: its velocity is parallel to
belt travel, and what little lateral motion exists comes from the drop and
from the side guides.

So the 102 mm by which the arm trails an object it is tracking is not
estimation error. It is latency: a pose is decided once per 0.5 s capture and
the belt carries the object 157 mm in that time. Filtering does not fix
latency and prediction does, and prediction here needs a velocity that is
already known. That is why interception is arithmetic over the belt speed and
introduces no estimator.

Where an estimator does pay is association, which is this spec. A covariance
is a principled association gate, and the roadmap already records the defect
it would close: `association_radius_meters` is a global constant sized for a
belt six times narrower than the one the world runs, and the repair recorded
there is that the radius becomes the track's own propagated footprint plus a
gate. A Mahalanobis distance is that gate. It also buys outlier rejection,
which matters more than it sounds: one residual in the same measurement run
reached 229 mm, which is too large to be sensor noise and is most likely one
object carried as two tracks. A filter without a gate would absorb that jump
and degrade the estimate; with a gate it is refused and reported.

The condition that would change this: if belt speed stops being known, or if
objects slip on the belt rather than riding it, then velocity has to be
estimated and a filter earns its place in propagation too. Neither is true of
the world as it stands.

**What is deliberately not settled here.** How the material posterior is
parameterized, and whether `reject` is a predicted class or an absence of
confidence, both of which `docs/perception-contract.md` leaves open and both of
which belong with the perception model rather than with the tracker.
