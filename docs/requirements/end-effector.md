# The end effector

## Intent

Give the arm something to close. The UR10e is vendored bare: it ends at a
flange, `docs/architecture.md` says under what is absent that the gripper
has never closed on an object, and pick success rate and cycle time are
reported as unmeasurable by construction rather than unmeasured by
omission. Everything above the flange is built and tested; this is what
makes those two numbers exist.

## Scope

**In.** A parallel-jaw gripper on the flange, its geometry, its joints and
its actuators. Closing on an object and holding it against belt motion and
gravity. Opening to release. The grasp phases the task machine already has
names for. Re-sweeping the object set against the jaw that lands. Pick
success rate as a measured figure.

**Out.** Suction, and the reasons are below. Force control and slip
detection, which need a sensor the model does not carry. Regrasping,
in-hand manipulation, and any recovery from a failed grasp beyond counting
it. Two-arm or multi-arm layouts.

## The decision, and why it goes against the stream

[The survey](../research/sorting-outputs-and-effectors.md) is clear that
municipal packaging lines use suction and construction waste lines use
fingers, and CLAVE's object set is packaging: cans, boxes, bottles. By
process realism the answer is suction.

**It is a parallel jaw anyway, and the reason is the simulator.** MuJoCo
Menagerie carries a Robotiq 2F-85, from the same collection the UR10e came
from, with published figures: 85 mm stroke, 5 kg payload, grip force
programmable from 20 to 235 N, 0.05 mm repeatability, 1.3 kg, on an
ISO 9409-1-50-4-M6 flange, which is what the UR10e wrist presents. It
carries no suction model, and MuJoCo has no vacuum primitive. A suction pick
is simulated by welding the tool to the object when a scripted condition
holds.

That is the whole decision. A jaw closing is contact physics the solver
works out, so a grasp that fails because the object squirted out of the
fingers is a result. A weld that appears when the tool is near enough is a
scripted success: it proves the plumbing runs and says nothing about whether
a pick would hold. `agents/claude.md` forbids presenting the second as the
first, and `D-13` already set the precedent that a validated open model
outranks one authored here.

**Two arguments that are often made and are not the reason.** That waste can
be crushed because it is not a product is true, and it removes the usual
objection to squeezing hard, but it argues against nothing that suction
does. That a waste surface is dirty and unstable is also true and is
documented against deformable, folded and crushed items specifically; it
does not extend to the rigid packaging this object set is made of, which is
exactly where suction performs best.

**What this costs, recorded rather than buried.** Throughput. The suction
systems the survey describes run 80 to 140 picks per minute; the fingered
machine it describes runs about 38. Any rate CLAVE reports is a rate for the
effector it simulates and not for the effector this line would install, and
the report has to say so. A suction effector remains the honest thing to add
if a vacuum model arrives that is more than a conditional weld.

## Constraints

- **The model is adopted, not authored**, and vendored the way the UR10e
  was, with its provenance and licence recorded beside it.
- **The jaw opens 85 mm and the world admits 180 mm, and the world will
  refuse to load until that is settled.** Swept against the compiled meshes
  rather than interpolated: at 85 mm the set goes from 18 objects to 17 and
  the class coverage does not move, staying at `M-02`, `M-04`, `M-06` and
  `M-09`. The single casualty is `master_chef_can`, 102.5 mm across its
  narrowest horizontal axis, and its class keeps three other objects. So the
  cost is one object in eighteen and no class.

  Until the object set or `arm.max_grasp_width_meters` changes, building the
  shipped world with an 85 mm limit raises, naming that can. That is the
  existing graspability check doing its job, and it is the first thing this
  step has to resolve rather than a surprise to meet later.
- **Grip force is configuration.** The gripper's own range is 20 to 235 N
  and what this line uses inside it is a YAML key.
- **The safety layer does not learn about the gripper.** It checks a pose
  against a workspace envelope and that does not change. What changes is
  that the pose now has a jaw on the end of it, which is the arm's geometry
  and not the envelope's.
- **A failed grasp is reported, not retried.** Recovery is out of scope and
  counting is the point.

## Acceptance criteria

Ids begin at `AC-GRIP-01`. They are append-only and never reused.

`AC-GRIP-01`: The system shall mount the gripper on the flange of the
compiled arm, and a test shall confirm the tool site every commanded pose is
expressed against moves with it.

`AC-GRIP-02`: The system shall read the grip force, the closing speed and
the open and closed positions from configuration, and shall fail at load
naming any that is absent.

`AC-GRIP-03`: The system shall refuse at load any object whose grasp width
exceeds the jaw's stroke, so a world cannot spawn what its own effector
cannot close on.

`AC-GRIP-04`: The system shall admit the object set against the adopted jaw
and record the objects and classes it admits, and shall refuse at load any
object the jaw cannot close on.

`AC-GRIP-05`: When the task machine reaches its grasp phase, the system
shall close the jaw, and when it reaches its release phase, shall open it.

`AC-GRIP-06`: When the jaw is closed on an object, the system shall hold it
against belt motion and gravity while the arm travels, proved by the object
moving with the flange rather than by the jaw being commanded shut.

`AC-GRIP-07`: When a grasp fails, the system shall count it and name the
object, rather than retrying or reporting the visit as served.

`AC-GRIP-08`: The system shall report pick success rate as a measured
figure, and shall report it beside the effector it was measured with.

`AC-GRIP-09`: The system shall report cycle time from a published decision
to the object crossing a chute opening, which is the figure `AC-CYCLE-01`
has carried as unmeasured since it was written.

`AC-GRIP-10`: The system shall state, wherever it reports a pick rate, that
the rate is for a parallel jaw and that the suction systems this stream
normally runs are faster.

`AC-GRIP-11`: The system shall record the vendored model's provenance and
licence beside it, as the arm's is recorded.

## Design notes

**Why the grasp phases already exist.** The task machine's phases are
FRET's `PickPlaceState` with grasp, placement and release removed, and the
removal was deliberate so that adding them later would be filling gaps
rather than rewriting. This is the spec that fills them.

**Why a failed grasp is interesting.** It is the first thing in CLAVE that
can fail for a physical reason rather than a logical one. A pose outside the
envelope is refused by arithmetic; a jaw that closes on a tumbling package
and comes away empty is the simulator disagreeing with the plan, and that
disagreement is the whole value of having contact physics under the
controller.

**Why not the wider jaw.** A Robotiq 2F-140 would keep all eighteen objects,
and Menagerie does not carry one: it has the 2F-85 and no other Robotiq
model. Authoring a 140 mm variant would put an unvalidated model beside a
validated one to save a single tuna-can-sized object, which is the trade
`D-13` already declined in the other direction.

**What the effector does not fix.** The 24.9 mm the flange currently trails
a moving pose by is actuator lag, not grasp error, and a jaw does not change
it. Closing on an object that is 24.9 mm from where the jaw expected it is
a grasp offset, and whether the jaw tolerates that is one of the things this
makes measurable.
