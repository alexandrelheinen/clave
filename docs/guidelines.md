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

## The mathematics: name the object, then call the function

The arithmetic in this repository decides where a jaw closes, so an error in it
is a physical fault and not a matter of taste. Code here writes the mathematics
in the language of mathematics: a vector is an array and its algebra is
numpy's, a scalar field over a grid is one expression, and a quantity that
numpy names is called by that name.

The reason is legibility. These are 3-vectors at a few hundred hertz, where
arithmetic cost is irrelevant, and `np.linalg.norm(a - b) <= tol` is the same
text as the specification it implements. A square root of a sum of three
indexed squares is a second implementation of that specification, and the two
can disagree in a way no reviewer notices without evaluating both.

### Where the primitives live

Scalar values of a physical quantity and the small algebra around them are
declared once in `clave.control.trajectory` and imported from there:

| Primitive | Use it for |
|---|---|
| `as_vector`, `as_point` | Crossing the tuple/array seam, once at each end |
| `norm`, `distance` | A length or a separation, never written longhand |
| `clip` | A value held between zero and a ceiling |
| `bisect_feasible` | The smallest input satisfying a monotone boolean predicate |
| `soonest_feasible` | The same, from a lower bound with no known upper bound |

A second copy of any of these in a caller is a second place for the tolerance,
the floor or the frame to be wrong. If a caller needs a variant, it belongs in
`trajectory.py` where the first one is tested.

### Vectors, tuples and the seam

- **A vector crossing a seam is a tuple; between seams it is an array.** The
  public dataclasses (`Point`, `Candidate`, `GraspMarker`, `State`) carry plain
  three-tuples because that is what a reader of an interface wants to see.
  Anywhere the code does arithmetic, convert once at the top with `as_vector`
  and back once at the bottom with `as_point`, and say at the seam why.
- **Broadcast instead of looping.** Evaluating a trajectory at 65 instants is
  one matrix product over the samples, not 65 evaluations of a scalar function:
  `np.linspace` samples, `np.stack` assembles, `axis=` selects. A `for` loop
  whose body is a formula is a formula that has not been written yet.
- **Element-wise index arithmetic is not algebra.** Rotating a set of vertices
  is `verts @ rotation.T + origin`; advancing a pose is
  `position + velocity * seconds`. Written as three indexed expressions
  instead, the operation loses its name, the axis each term moved is implicit,
  and a term on the wrong axis reads as correct. The exception is a change to
  one named component, where naming the component is the clearest form:
  `carry` translates along the belt and says so with `p[0] + travel`.
- **A two-sided clamp is `np.clip`.** `max(0.0, min(ceiling, value + step))`
  hides which inequality bound and makes a reader evaluate the expression to
  find out. `float(np.clip(value + step, 0.0, ceiling))` is the inequality.
  A floor on one named component is the exception, and `max(0.0, velocity[0])`
  says which component it is.

### Optimization, root finding and linear algebra

- **A monotone boolean predicate is a bisection.** When the question is "what
  is the smallest duration that satisfies these ceilings", and larger inputs
  satisfy them at least as well, that is a bisection on monotonicity:
  `bisect_feasible`, or `soonest_feasible` when only a lower bound is known
  and the passing end has to be bracketed by doubling. `scipy.optimize.bisect`
  and `brentq` solve `f(x) == 0` for a continuous `f`, and a boolean is not
  that, so a general solver is the wrong primitive where a bisection is exact.
- **A continuous objective with a derivative is scipy's, not ours.** If the
  question really is "minimize this smooth function", reach for
  `scipy.optimize.minimize` with a documented method, and pass the gradient
  when it is known. Hand-rolled gradient descent, golden-section search and
  Nelder-Mead are three ways to be wrong slowly.
- **A least-squares or a small linear solve is `np.linalg`.** `lstsq`, `solve`,
  `pinv` and `svd` are existing, tested and fast. Normal equations written out
  by hand are a conditioning bug filed later as a precision problem.
- **Adding scipy is a design decision, not a convenience.** It is a large
  dependency with a wide surface. Before it enters `pyproject.toml`, the
  question is whether numpy already answers the need, and for everything in
  this repository it does. Where a general solver looks like the right tool,
  the code says why it is not, the way `bisect_feasible` does, so the next
  reader does not re-litigate the choice.

### Calculus: what has a closed form, and what does not

- **A derivative that has a closed form has a closed form.** The quintic
  Hermite basis in `trajectory.py` has analytic first and second derivatives,
  and those are what is evaluated at the sample times. Never `np.diff` a
  position series to get a velocity when the velocity is a known polynomial:
  differencing divides by the step and amplifies the noise, which is how a
  two-millimetre telemetry jitter becomes a fifty-millimetre-per-second
  velocity error. Where a difference *is* the only way to read a quantity from
  telemetry, as with the jerk in the debug rollouts, say that the figure is a
  differenced one and name the resolution it was read at.
- **An integral that has a closed form has a closed form.** If the arc is a
  polynomial, the displacement is that polynomial integrated. Quadrature is for
  data, not for functions you wrote down.
- **When you do discretize, say what the truncation is.** A peak over a
  sampling is a *sampled* peak, and the sample count is the resolution of the
  claim: `trajectory.SAMPLES` for a trajectory's peak speed and acceleration,
  `task.LEG_SAMPLES` for the per-leg pose test. A maximum asserted as exact
  must be found analytically or bracketed by a solver that converges; a maximum
  over samples is a lower bound, and the docstring says so.
- **A stack of Jacobians times a stack of velocities is a matmul.** Use `@` on
  the right axes, not a comprehension over `np.dot`.

### Geometry

- **A frame is a rotation and a translation.** Rotating a set of vertices, or
  the ring of pad centers `markers._pad_places` draws, is one array expression
  rather than a per-item call.
- **Angles are `np.arctan2(y, x)`, never `np.arctan(y / x)`.** The two-argument
  form is defined on both axes and preserves the quadrant; the ratio is not and
  does not. Where a convention matters, such as a yaw about the belt normal or a
  jaw that closes along the short axis, state the convention next to the call,
  and wrap into the range you mean with `(angle + pi) % (2 * pi) - pi` written
  once rather than at every use.
- **An orientation difference is an angular difference, not a subtraction.**
  `a - b` is a number that happens to be right when the angles are away from
  the seam. Symmetries fold in once: a jaw is symmetric about 90 degrees, so
  the fold is a modulo written in one place, not a second convention.
- **A distance is a norm, and a squared distance is not one.** Do not compare a
  squared distance against a tolerance in meters, and do not write the
  Euclidean distance longhand anywhere: `norm` and `distance` exist so the
  definition has one home per frame, and so that the frame of the two operands
  is visible at the call site.
- **A nearest neighbour is an `argmin` over the norms.** A loop with a running
  minimum inside it is the same question with the answer hidden: build the
  array of candidates, take the norms over the right axis, and index the
  winner. When the candidates carry a per-candidate ceiling as well, mask them
  first and take the `argmin` over what is left.

### The review question

Before writing a `for` loop, a nested `min`/`max`, or a block of index
arithmetic here, ask: **what is the mathematical object, and is there a
function in numpy that names it?** If yes, call the function. If no, say in a
comment what the loop is and why it is not one of the named operations, because
a loop over a sequence of events is a different thing from a loop over an axis,
and that difference is worth writing down.

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
