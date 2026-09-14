# CLAVE-specific coding notes

The shared baseline for Rust and Python style, naming, and error handling
lives in
[standards/guidelines/languages/rs.md](../standards/guidelines/languages/rs.md)
and
[standards/guidelines/languages/py.md](../standards/guidelines/languages/py.md).
This file covers only what is specific to CLAVE. Method, gates, and merge
policy live in [CONTRIBUTING.md](../CONTRIBUTING.md).

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

**Inference runtime**: Hosted on BOSSA edge hardware (ARM Linux), typically
ONNX Runtime or TensorRT. Wrapped by Rust code that enforces the policy
interface contract.

## Hardened by default

Safety-layer crates take the hardened lint tier from
[languages/rs.md](../standards/guidelines/languages/rs.md#hardened-for-real-time-unsafe-and-ffi-crates).
A coordinate that silently overflows, a bound check that silently truncates,
or an actuator limit that silently wraps is a fault in this domain, not a
style question.

Neural inference wrapper crates, policy serialization, training tooling, and
anything that runs offline take the baseline tier.

## Latency is a tested property

The entire perception-to-safety-check path has a latency budget measured at
p99. Every safety-layer crate states its budget in documentation and carries
Criterion benchmarks under `benches/`. Neural inference latency is measured
on target BOSSA hardware and is a constraint on model size and quantization.
A system that averages well and misses one frame in a hundred still drops
that object on the floor. A change that moves a budget is a spec change,
not an implementation detail.

## Inference throughput and batching

Neural inference is single-frame, no batching across conveyor objects.
Throughput depends on model complexity, target hardware (BOSSA ARM device),
and quantization strategy. Every policy release documents minimum and
expected inference latency at the target quantization level. Inference
latency is part of the overall budget, not separate from safety checks.

## Policy artifacts

Trained policies are not committed to this repository. A policy is named by
training timestamp and checksum, fetched by a deployment script, and
versioned in a policy registry. Training metadata (imitation data source,
RL environment configuration, domain randomization seeds, performance
metrics) is archived and versioned to enable policy retraining and
comparison.

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

CLAVE publishes trajectory waypoints and pick timing. Motion planning and
execution belong to [ARCO](https://github.com/alexandrelheinen/arco). Policy
training uses FRET and MuJoCo simulation from
[FRET](https://github.com/alexandrelheinen/fret). Neural inference runs on
[BOSSA](https://github.com/alexandrelheinen/bossa). Sim-to-real calibration
uses [Luthier](https://github.com/alexandrelheinen/luthier). Define contracts
as serializable types in CLAVE and let consumers adapt; do not import a
sibling's types and do not vendor a sibling's source.
