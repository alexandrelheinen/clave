# Requirements Document

## Project Description (Input)
CLAVE has a taxonomy, a platform, and measured candidates, and nowhere to run
any of them. v0.6.0 generates labeled rollouts, v0.7.0 trains against them, and
v0.8.0 validates on scenes training never saw. All three need a world, and none
exists.

The world is also where several numbers stop being abstract. v0.4.0 measured
Faster R-CNN at 391.7 ms and called it marginal, which is a judgment rather than
a verdict because no belt speed, field of view, or effector reach has ever been
fixed. This feature fixes them, and in doing so turns a latency measurement into
a pass or a fail.

The scene reuses FRET's stack rather than rebuilding it: MuJoCo physics, and the
ROBOTIS OpenMANIPULATOR-X loaded from the same pinned submodule FRET uses. What
CLAVE adds is the part FRET does not have, meaning a conveyor, waste objects
carrying material classes, and one bin per channel.

Every tunable is configuration. FRET treats a hardcoded numeric default as a
defect, and a world whose belt speed is buried in Python cannot be randomized,
which is the entire point of building it.

## Introduction

This feature delivers the simulated sorting line: a belt carrying objects past a
manipulator, with one bin per channel from the taxonomy.

Two properties decide whether it is useful later. Every object carries a
material class, so a rollout is labeled by construction rather than by a
labeling pass afterwards. And every knob that could vary between runs is a
configuration key with a randomization range, so v0.7.0 can randomize without
editing the scene.

The world is deliberately geometric rather than photorealistic. Objects are
parametric primitives sized from their real counterparts, not scanned meshes.
That is a stated limitation rather than an oversight, and the document says what
it costs.

## Boundary Context

- **In scope**: the MuJoCo scene, the conveyor, the object set with its material
  classes, the bins, the configuration schema and its randomization ranges, the
  seeded spawner, and the reachability check that proves an object enters the
  arm's workspace.
- **Out of scope**: training, any policy, and any perception model. Recording
  rollouts, which is v0.6.0. Reward functions, which v0.7.0 needs. Scanned
  object meshes, which are a refinement recorded as an open question. Any change
  to FRET.
- **Adjacent expectations**: the taxonomy supplies the material classes and the
  channels. FRET supplies the manipulator through a pinned submodule and is not
  modified. The platform supplies seeding, and this feature adds no second
  source of randomness.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `SCENE`, `ASSET`, `BELT`, `CONFIG`, and `REACH`. Ids are append-only.

## Requirements

### Requirement 1: The scene

**Objective:** As the engineer generating rollouts at v0.6.0, I want a scene that
steps in MuJoCo with a belt, an arm and bins, so that a rollout has somewhere to
happen.

#### Acceptance Criteria

1. The World shall build a MuJoCo model containing a conveyor surface, a
   manipulator, and one bin per channel. `AC-SCENE-01`
2. The World shall load the manipulator from a pinned submodule rather than from
   a vendored copy. `AC-SCENE-02`
3. When the World is stepped, the World shall advance without a physics
   instability. `AC-SCENE-03`
4. The World shall expose the simulation timestep it runs at. `AC-SCENE-04`

### Requirement 2: Objects and their material classes

**Objective:** As whoever builds the training set, I want every object to carry
its material class, so that a rollout is labeled by construction.

#### Acceptance Criteria

1. The World shall place objects drawn from a declared object set, each carrying
   a material class identifier from the taxonomy. `AC-ASSET-01`
2. The World shall cover at least six distinct material classes across its
   object set. `AC-ASSET-02`
3. When an object is spawned, the World shall record its material class and its
   identity, so a later consumer does not have to infer either. `AC-ASSET-03`
4. If an object's declared material class is not in the taxonomy, then the World
   shall reject the configuration naming the offending object. `AC-ASSET-04`

### Requirement 3: The conveyor

**Objective:** As the engineer measuring whether a detector is fast enough, I want
the belt to move at a stated speed, so that latency becomes a pass or a fail
instead of a judgment.

#### Acceptance Criteria

1. The World shall carry objects along the belt at a configured speed.
   `AC-BELT-01`
2. The World shall state the time an object spends inside the arm's reachable
   window, given the belt speed and the window's extent. `AC-BELT-02`
3. When an object leaves the reachable window unpicked, the World shall continue
   carrying it rather than removing or stopping it. `AC-BELT-03`
4. The World shall spawn objects at a configured rate. `AC-BELT-04`

### Requirement 4: Configuration and randomization

**Objective:** As the engineer randomizing domains at v0.7.0, I want every tunable
in configuration with a stated range, so that randomizing needs no code change.

#### Acceptance Criteria

1. The World shall read every tunable from a configuration file rather than from
   a default embedded in code or in the scene description. `AC-CONFIG-01`
2. If a required configuration key is absent, then the World shall fail at load
   naming the missing key, rather than substituting a value. `AC-CONFIG-02`
3. The World shall express each randomizable quantity as a range rather than a
   single value. `AC-CONFIG-03`
4. When the World is built twice from one seed and one configuration, the World
   shall produce identical object placements. `AC-CONFIG-04`
5. When the World is built from two seeds, the World shall produce different
   object placements. `AC-CONFIG-05`

### Requirement 5: Reachability

**Objective:** As a reader deciding whether this world can host a pick at all, I
want proof that an object reaches the arm, so that the scene is not merely a
picture.

#### Acceptance Criteria

1. The World shall state the manipulator's reachable radius and the belt segment
   that falls inside it. `AC-REACH-01`
2. When an object travels the belt, the World shall report that it entered the
   reachable window. `AC-REACH-02`
3. The World shall report the per-object time budget that the belt speed and the
   reachable window imply. `AC-REACH-03`
