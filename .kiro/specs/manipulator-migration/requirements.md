# Manipulator migration

## Intent

Replace the manipulator CLAVE simulates with one whose model is maintained
outside this repository and derived from manufacturer CAD, and state a cycle
time the resulting line has to meet.

Two problems force this. The arm in the world today was authored here out of
capsules and boxes, and it renders as a toy: `CONTRIBUTING.md` now ranks
physical fidelity with the quality gates, and that arm fails the requirement it
motivated. Separately, the project has never stated how fast a pick must be, so
no configuration of belt speed, arm, and policy could ever be called adequate or
inadequate. `D-13` records the manipulator choice and what it costs; this
document is what the choice has to satisfy.

## Scope

**In.** The manipulator model and its mounting, the support structure it stands
on, the reachability test and the workspace it describes, the safety envelope
that has to agree with that test, the cycle time budget and the gate that
enforces it, and every configuration, test and document that names the old arm.

**Out.** The end effector, which is specified separately and is why no pick
success criterion appears below. The policy, which `D-12` records at 0.445 m of
error and which this migration neither improves nor worsens. The object set,
settled by `D-11`. Throughput beyond a single arm, which is a second manipulator
rather than a property of this one.

## Constraints

- **The model is adopted, never authored.** `CONTRIBUTING.md`, Physical
  fidelity. A manipulator built here from primitives is refused whatever its
  kinematics.
- **Side mounting only.** An inverted six-axis arm over the belt reaches almost
  nothing with its tool vertical, because pointing straight down while extended
  is near-singular. A sweep found 3 of 27 sample points reachable. The overhead
  configuration that suited the previous arm is unavailable to this one.
- **The arm rests on something.** A manipulator floating at working height
  describes no installation anybody could build. A parallelepiped pedestal is
  sufficient, and its dimensions are configuration rather than constants.
- **One reachability test.** The world and the safety layer read the same
  function. The previous arm carried two tests that disagreed and produced a 47
  percent override rate.
- **Measured, not declared.** A six-axis arm holding its tool vertical has no
  closed-form workspace, so reach is established by sweeping the compiled model.

## Acceptance criteria

### Manipulator

`AC-ARM-01`: When the world is built, the system shall load the manipulator from
a model derived from manufacturer CAD and maintained outside this repository.

`AC-ARM-02`: When the manipulator model is absent from a checkout, the system
shall fail naming the file, because the file is committed rather than generated.

`AC-ARM-03`: The system shall mount the manipulator beside the belt, on a
pedestal whose footprint and height come from configuration.

`AC-ARM-04`: When the pedestal is placed, the system shall keep it outside the
volume the arm sweeps, so the manipulator cannot drive into its own support.

### Workspace

`AC-REACH-04`: When asked whether a point is reachable, the system shall answer
by solving inverse kinematics with the tool held vertical, rather than by
comparing a distance against a radius.

`AC-REACH-05`: The world and the safety envelope shall reach the same verdict
for the same point, through the same geometry.

`AC-REACH-06`: When the line is configured, every lateral position across the
belt shall be reachable at some point in its travel, established by a sweep
recorded in `docs/measurements.md`.

### Cycle time

`AC-CYCLE-01`: The system shall carry a configured budget of **1.0 second** from
the instant a pick decision is published to the instant the effector reaches the
pick point.

`AC-CYCLE-02`: When a run reports cycle times, the validation harness shall fail
the run if the 99th percentile exceeds the configured budget.

`AC-CYCLE-03`: When no pick is executed, the harness shall report cycle time as
unmeasured rather than as zero or as passing, because nothing in CLAVE grasps
and a gate that passes vacuously is worse than one that reports its own silence.

`AC-CYCLE-04`: The system shall record, in `docs/measurements.md`, the
manipulator's published cycle time alongside the budget, so a reader can see
whether the budget is ambitious or slack for the machine chosen.

### Migration completeness

`AC-MIGRATE-01`: When the migration lands, no configuration, test, document or
asset shall name the previous manipulator.

`AC-MIGRATE-02`: When the visuals are regenerated, the manipulator shall be
recognisable as the machine the model claims to be.

## Traceability

Ids are append-only. `AC-REACH-01` through `AC-REACH-03` belong to earlier
specs and are not reused. Tests reference these ids in a name or a comment so
the mapping is greppable both ways.

## Design notes

The arm is a Universal Robots UR10e, for the reasons `D-13` records: it is the
only model in MuJoCo Menagerie that covers a 1.00 m belt, at 1.308 m of reach
against 0.95 m or less for every other candidate. A sweep with the tool held
vertical puts full coverage at a pedestal 0.60 m to 0.75 m from the belt
centreline.

Vertical motion is a task-space constraint rather than a joint. No arm in
Menagerie has a prismatic axis and locking revolute joints cannot create one, so
a descent is achieved by solving inverse kinematics at each waypoint with the
tool pointing down. This is what an industrial linear move does, and it is why
`AC-REACH-04` is phrased around solving rather than measuring.

The 1.0 second budget is a target rather than a derived quantity, and it is set
where it is because published pick-and-place cycle times put collaborative arms
slowest of the four common classes: delta near 0.3 s, SCARA 0.28 to 0.50 s,
six-axis industrial 0.4 to 0.8 s, collaborative arms behind those. One second
asks the chosen arm for something near the top of its class without asking for
something its class cannot do. `AC-CYCLE-04` exists so the gap between that
budget and the machine's own figure stays visible rather than being flattened
into a single number.

The budget is unmeasurable until something grasps, which `AC-CYCLE-03` makes
explicit rather than leaving to a reader to discover from a zero.
