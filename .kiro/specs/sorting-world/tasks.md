# Implementation Plan

No task carries `(P)`. Configuration in 1.1 is a prerequisite for everything,
and the scene, belt and reachability all act on one model.

- [ ] 1. Foundation: configuration and the object set

- [ ] 1.1 Implement configuration loading and range resolution
  - Load every tunable from YAML, failing at load on a missing key and naming
    it, with no default embedded in code.
  - Express each randomizable quantity as a two-element range, and reject an
    inverted range naming the key.
  - Resolve ranges through the platform's seeding entry point rather than adding
    a second source of randomness.
  - Write the failing tests first.
  - Observable: a complete configuration loads, an incomplete one names the key
    it is missing, and no numeric default appears in Python or MJCF.
  - _Requirements: 4.1, 4.2, 4.3_
  - _Boundary: clave.world.config_

- [ ] 1.2 Declare the object set with material classes
  - Declare each object with a name, a taxonomy class identifier, a primitive
    shape, and size and density ranges.
  - Reject a class identifier outside the taxonomy, naming the object.
  - Cover at least six distinct material classes.
  - Observable: every object resolves to a taxonomy class, and an invented class
    fails at load naming the object.
  - _Requirements: 2.1, 2.2, 2.4_
  - _Boundary: clave.world.objects_

- [ ] 2. Core: the scene and the belt

- [ ] 2.1 Assemble the scene
  - Build a model containing the conveyor surface, the manipulator attached from
    the pinned submodule, and one bin per distinct channel.
  - Fail with a message naming the submodule and the command that fixes it when
    it is not checked out.
  - Expose the simulation timestep.
  - Observable: the model builds, carries one bin per channel, and steps for a
    thousand steps without a physics instability.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Boundary: clave.world.scene_
  - _Depends: 1.1, 1.2_

- [ ] 2.2 Implement the spawner and the belt drive
  - Spawn objects at the configured rate and placement, recording each object's
    identity and material class.
  - Drive each on-belt object's horizontal velocity to the belt speed, leaving
    vertical motion, rotation and contact to physics.
  - Leave an object that passes the reachable window alone, so it continues to
    the end of the belt rather than being removed.
  - Observable: two builds at one seed place objects identically, two seeds do
    not, and an object on the belt reaches belt speed within a few steps.
  - _Requirements: 2.3, 3.1, 3.3, 3.4, 4.4, 4.5_
  - _Boundary: clave.world.belt_
  - _Depends: 2.1_

- [ ] 3. Integration

- [ ] 3.1 Report reachability and the time budget
  - Derive the manipulator's reachable radius from its link geometry and the
    belt segment that falls inside it.
  - Report the per-object time budget the belt speed and that window imply, and
    report when a travelling object enters the window.
  - Add a command that builds the world, steps it, and prints the report.
  - Observable: the command prints a radius, a window extent, a belt speed and a
    time budget, and reports at least one object entering the window.
  - _Requirements: 3.2, 5.1, 5.2, 5.3_
  - _Depends: 2.2_

- [ ] 4. Validation

- [ ] 4.1 Run the world and compare the budget against v0.4.0
  - Execute the command and capture its output.
  - State whether the measured detector latency from v0.4.0 fits inside the time
    budget this world implies, which is the question v0.4.0 could not answer.
  - Observable: the gate passes with the world tests included, and the
    comparison is recorded rather than left for a reader to compute.
  - _Requirements: 5.3_
  - _Depends: 3.1_
