# CLAVE-specific coding notes

The shared baseline for Rust and Python style, naming, and error handling
lives in
[.guidelines/languages/rs.md](../.guidelines/languages/rs.md)
and
[.guidelines/languages/py.md](../.guidelines/languages/py.md).
This file covers only what is specific to CLAVE. Method, gates, and merge
policy live in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Physical and kinematic variable naming: `who_what_where`

Variables representing physical quantities, spatial poses, velocities, and
measurements follow a structured grammar. The complete vocabulary of tokens,
entities, reference frames, and units is exhaustively defined in the
[Physical Variables Glossary](glossary.md).

```
[who_]what[_where][_unit]
```

Where:
- **`who`**: The body or entity the variable belongs to (e.g. `camera`,
  `flange`, `object`, `jaw`, `belt`, `chute`).
- **`what`**: The physical property or measurement (e.g. `position`,
  `velocity`, `acceleration`, `pose`, `yaw`, `speed`, `force`, `torque`).
  Qualifiers (`target`, `current`, `min`, `max`) precede `who` or `what`:
  `target_flange_position_world`, `max_belt_speed`.
- **`where`**: The coordinate frame of reference the quantity is expressed in
  (e.g. `world`, `camera`, `belt`, `flange`, `base`, `joint`).
- **`unit`**: Required **only when the quantity is not in standard SI units**.
  SI units ($m$, $m/s$, $m/s^2$, $rad$, $rad/s$, $kg$, $s$, $N$) are the
  default and **never** take a unit suffix. Non-SI quantities append the unit
  name explicitly (`deg`, `mm`, `ms`, `nanos`, `px`).

### Examples

| Variable | Meaning |
|---|---|
| `flange_position_world` | Flange position in the world reference frame ($m$, SI) |
| `object_velocity_belt` | Object velocity in the conveyor belt reference frame ($m/s$, SI) |
| `camera_pose_world` | 3D pose of the camera in world coordinates (SI) |
| `flange_yaw_deg` | Flange rotation in degrees (non-SI unit suffix required) |
| `capture_timestamp_nanos` | Sensor acquisition timestamp in nanoseconds (non-SI) |
| `detection_bbox_px` | Detection bounding box in camera pixel coordinates (non-SI) |

### Abstraction and omission rules

Good software abstraction models general operations without coupling them to
specific bodies or frames. Omit segments when an abstraction does not need them:

1. **Omitting `who` (Entity abstraction)**:
   Algorithms that operate on generic spatial coordinates regardless of which
   physical body is moving omit the body prefix. A frame transformation or
   spatial planner takes a `position_world` or `velocity_base`, not an
   `object_position_world`.
   ```python
   # Generic frame transformation: works for any body
   def to_camera_frame(position_world: Point) -> Point: ...
   ```

2. **Omitting `where` (Frame abstraction)**:
   Quantities that are frame-invariant (such as scalar distances, speeds, norms,
   or clearances), or local algorithms that operate strictly in a local or
   implied canonical space, omit the reference frame.
   ```python
   # Frame-invariant scalar quantities
   jaw_opening = 0.085  # meters (SI)
   grasp_clearance = 0.020  # meters (SI)
   ```

3. **Omitting both `who` and `where` (Pure mathematical abstraction)**:
   Core mathematical formulation (splines, PID loops, numerical solvers,
   numerical integration) operates on abstract states. In these components,
   `position`, `velocity`, and `acceleration` stand alone without body or frame
   bindings.
   ```python
   # Pure trajectory segment: uncoupled from body and frame
   @dataclass(frozen=True)
   class State:
       position: Point
       velocity: Point
       acceleration: Point
   ```

### Counts and collections

- Integer counts take a `_count` suffix: `sensor_count`, `chute_count`, not
  `num_sensors` or `n_chutes`.
- Collections are plural nouns, not suffixed with `_list` or `_array`:
  `chute_mouths`, `candidates`, `tracks`, not `chute_mouth_list`.
- Configuration keys in YAML and JSON follow the same grammar, retaining
  non-SI suffixes when needed (`spacing_meters`, `yaw_degrees`, `timeout_ms`).

## Architecture: safety layer and learned policy

The system is a hybrid of deterministic safety in Rust and learned
perception-action in neural networks. The safety layer owns collision
checking, actuator limits, and emergency stops, and always runs them against
policy decisions before physical action. A Python process is never in the
loop at runtime; policy training happens offline in Python and MuJoCo, then
policies are versioned and deployed.

## Language split

**Rust**: The safety layer. Collision checking, actuator limits, hardware
interlocks, and zero-copy communication with neural inference. Everything
that affects hardware safety is Rust and hardened.

**Python**: Policy training. Imitation learning from human demonstrations,
reinforcement learning in MuJoCo simulation via FRET, domain randomization
for sim-to-real transfer. Trained policies are serialized and versioned.

**Inference runtime**: Python, in its own process, with Rust on the other side
of a versioned JSON proposal over a Unix datagram. Rust never loads a model,
because the layer that can override inference earns its place by sharing no code
with it. `crates/clave-safety/contract/proposal.md` specifies the boundary. Through the v1.x line everything runs on the development machine.

## Hardened by default

Safety-layer crates take the hardened lint tier from
[languages/rs.md](../.guidelines/languages/rs.md#hardened-for-real-time-unsafe-and-ffi-crates).
A coordinate that silently overflows, a bound check that silently truncates,
or an actuator limit that silently wraps is a fault in this domain, not a
style question.

Neural inference wrapper crates, policy serialization, training tooling, and
anything that runs offline take the baseline tier.

## Latency is a tested property

The entire perception-to-safety-check path has a latency budget measured at
p99. Every safety-layer crate states its budget in documentation and carries
Criterion benchmarks under `benches/`. Neural inference latency is measured
on the development machine and is a constraint on model size and quantization.
A system that averages well and misses one frame in a hundred still drops
that object on the floor. A change that moves a budget is a spec change,
not an implementation detail.

## Inference throughput and batching

Neural inference is single-frame, no batching across conveyor objects.
Throughput depends on model complexity, the machine it runs on, and the
quantization strategy. Every policy release documents minimum and expected
inference latency at the quantization level it was measured at. Inference
latency is part of the overall budget, not separate from safety checks.

## Policy and perception artifacts

Trained policies and perception models are not committed to this repository. A
model is named by candidate, configuration digest, and dataset digest, uploaded
to object storage, and retrieved via deployment commands. Training workflows,
domain randomization, and precision validation gates are documented in
[detection-training.md](detection-training.md).

Datasets for policy training use public sources where possible (COCO for
initial training, public waste datasets). Proprietary customer data for
imitation learning is archived separately with explicit consent.

## Policy training interface

The policy interface is defined as a Rust type in this repository: input
dimensions (visual embedding size), output dimensions (pick coordinate,
timing offset, channel selection), sampling strategy (deterministic vs.
stochastic), and quantization level (fp32, fp16, int8). Every policy release
documents the interface version it implements. The Rust wrapper enforces this
contract; a mismatch between policy and wrapper is a runtime error.

## Contracts toward siblings

[FRET](https://github.com/alexandrelheinen/fret) is the integration edge in
both directions. It supplies the MuJoCo simulation, the OpenMANIPULATOR arms,
and the pinned mesh submodules CLAVE trains against, and its planner nodes
consume the decision CLAVE publishes. Those nodes call
[ARCO](https://github.com/alexandrelheinen/arco) as a synchronous Python
library, so CLAVE does not address ARCO directly.
[BOSSA](https://github.com/alexandrelheinen/bossa) is a C++20 telemetry
runtime for ARM Linux and carries metrics in a later hardware era, not in the
v1.x simulation line. [Luthier](https://github.com/alexandrelheinen/luthier)
supplies photogrammetry when calibration against real geometry starts.

Define contracts as serializable types in CLAVE and let consumers adapt; do
not import a sibling's types and do not vendor a sibling's source.
