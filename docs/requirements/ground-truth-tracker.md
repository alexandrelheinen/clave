# Ground-truth tracker

## Intent

Decouple arm manipulation, trajectory execution, and chute sorting from visual
perception and tracker estimation errors.

During development and tuning of the physical manipulation layer (reachability,
approach and retreat trajectories, clearance above belt barriers, and gripper
actuation), errors in segmentation or tracking association obscure physical
defects. Supplying the selector and downstream motion planning with ground-truth
object states directly from the physics engine allows developers to isolate and
validate the arm control loop independently.

This specification introduces a configuration and command-line option to feed
downstream decision components from ground-truth MuJoCo state while preserving
concurrent tracker execution and diagnostic observation.

## Scope

**In.** A configuration option and command-line flag enabling ground-truth
target feeding. Derivation of `GraspMarker` representations directly from
MuJoCo physics state (`model` and `data`) for active objects on the belt.
Routing ground-truth markers into `Selector` and `TaskMachine`. Concurrent
execution of visual perception, segmentation, and tracker settling. Visual scene
markers reflecting the active feeding source.

**Out.** Modifying the internal state or beliefs of `Tracker` during
ground-truth feeding. Changes to the physical robot kinematic solver, motion
polynomial formulation, or safety checks. Eliminating tracker debug telemetry or
logs.

## Constraints

- **The tracker runs concurrently.** Enabling ground-truth feeding shall not
  bypass camera rendering, mask inference, or tracker state updates. The
  tracker shall continue to observe evidence and settle records at each capture
  interval so tracking telemetry and diagnostic metrics remain available.
- **Contract compatibility.** Downstream consumers (`Selector`, `TaskMachine`,
  and trajectory planners) shall consume `GraspMarker` instances without
  requiring branch-specific logic or separate interfaces.
- **Physical fidelity.** Ground-truth poses, dimensions, and orientations shall
  be derived directly from MuJoCo bodies and geoms rather than simulated sensor
  cues.
- **No breaking configuration defaults.** Ground-truth mode is disabled by
  default; normal runs execute with perception-derived tracker beliefs.

## Acceptance criteria

`AC-GT-01`: The system shall expose a `ground_truth_tracker` boolean in
configuration and a `--ground-truth-tracker` flag (with `--gt` and
`--gt-tracker` aliases) on `clave sim`, defaulting to false.

`AC-GT-02`: When `ground_truth_tracker` is enabled, the system shall compute
`GraspMarker` targets directly from MuJoCo bodies and geoms for all active
objects on the belt.

`AC-GT-03`: When `ground_truth_tracker` is enabled, the system shall execute
perception, tracker observation, and tracker settling at the configured capture
interval without interruption.

`AC-GT-04`: When `ground_truth_tracker` is enabled, `Selector` and `TaskMachine`
shall plan and execute picks using the ground-truth markers.

`AC-GT-05`: When `ground_truth_tracker` is enabled, scene visualization markers
shall display the ground-truth grasp poses passed to the selector.

`AC-GT-06`: A ground-truth marker's identity shall be the spawn serial of the
object it describes rather than the pool slot that object rides in, because a
slot is reused as soon as the object in it leaves the belt: a consumer that
remembers what it has already served would otherwise be remembering a place,
and would refuse to serve the second object to occupy it.

## Traceability

Ids begin at `AC-GT-01` and are append-only. Tests guarding these requirements
shall reference their identifier in the test function name or docstring.

## Design notes

**Why the tracker continues to run.** Bypassing the tracker entirely would
prevent developers from comparing tracker estimates against ground truth in the
same run. Running both concurrently allows side-by-side verification, logging,
and metric computation while guaranteeing that pick execution follows truth.

**Naming convention.** The codebase already defines `Role.GROUND_TRUTH` in
`clave.tracker.evidence` and `GroundTruth` payloads for simulator association.
Using `ground_truth_tracker` preserves consistency with this established
taxonomy.
