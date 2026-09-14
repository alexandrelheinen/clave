# Technology Stack

## Architecture

A hybrid system with two layers: a learned perception-action policy running
on neural inference, wrapped by a deterministic safety layer in Rust.

**Learned layer**: Spatial-temporal neural networks fuse visual perception,
object tracking, and pick decisions into an end-to-end policy trained via
imitation learning (from human demonstrations) and reinforcement learning
(in MuJoCo simulation). The policy outputs continuous pick coordinates, timing
offsets, and channel routing decisions. The maintainer settled the output shape
on 2026-09-14: a discrete pick decision carrying a pick location and a material
class, not a continuous action or a trajectory. Motion remains FRET's and
ARCO's.

**Safety layer**: A Rust runtime enforces hard invariants. Zero-copy shared
memory transfers visual embeddings to the neural inference layer and receives
action distributions back. A deterministic safety checker inspects every
action: collision checks against known geometry, actuator limit enforcement,
and emergency-stop interlocks ensure the physical system never enters an
unsafe state. Unsafe actions are overridden with safe fallbacks.

Policy training sits outside the runtime and hands over a serialized policy
artifact. A Python process is never in the loop at runtime. Through the v1.x
line the runtime executes against FRET's MuJoCo SITL, not against hardware.

## Core Technologies

- **Safety layer**: Rust, edition 2024, resolver 3, toolchain pinned in
  `rust-toolchain.toml`. Handles hardware communication, collision checking,
  and safety interlocks.
- **Inference runtime**: chosen at the `learning-platform` step of the
  roadmap, loaded by a Rust wrapper that enforces the policy interface.
- **Policy training**: Python with PyTorch or JAX for imitation and
  reinforcement learning. Domain randomization for sim-to-real transfer.
- **Training environment**: MuJoCo simulation via FRET, providing kinematic
  constraints, object dynamics, and reward functions for RL.
- **Policy format**: Serialized neural network weights plus metadata. A
  specification defines the policy interface (input/output dimensions,
  sampling strategy).
- **Layout**: one Cargo workspace per repository, crates under
  `crates/<name>/`, shared metadata and lints in `[workspace.package]` and
  `[workspace.lints]`.

No application code has landed yet. The first crate arrives with the first
approved specification, and the Rust gates below activate with it.

## Development Standards

### Lint tiers

Safety-layer crates (collision checking, actuator limits, emergency stops)
take the hardened tier from `standards/guidelines/languages/rs.md`:
`arithmetic_side_effects`, `as_conversions`, `indexing_slicing`, and the
cast lints all deny. A coordinate overflow or a silently truncated bound
check is a fault in this domain, not a style question. Neural inference
wrapper crates, policy serialization, and anything not in the safety path
take the baseline tier. Training and dataset tooling are Python and use
Python linting standards.

Lint configuration lives in `[workspace.lints]` in the root `Cargo.toml`,
never in crate-root attributes and never in CI flags. Suppress with
`#[expect(..., reason = "...")]` so the compiler reports a suppression that
outlived its problem.

### Safety and error handling

- A crate that does not need `unsafe` declares `#![forbid(unsafe_code)]`,
  which is the expected state for most crates here.
- Numeric conversions go through `From` and `TryFrom`. `as` is denied in
  the hardened tier.
- Libraries define a `thiserror` enum marked `#[non_exhaustive]` and return
  it from every fallible public function. `anyhow` appears only at the top
  layer of a binary.
- `unwrap` is denied outside tests, and `expect` states the invariant
  rather than the symptom.

### Testing

Test-driven by default, with the failing test written first and confirmed
to fail for the right reason. Unit tests are co-located in
`#[cfg(test)] mod tests`; integration tests live in `tests/` and exercise
only the public API. `cargo nextest run` is the runner, and `cargo test
--doc` runs alongside it because nextest skips doc tests. Coverage is gated
at 80% lines through `cargo llvm-cov`.

### Latency as a tested property

The entire perception-to-safety-check path has a latency budget measured at
p99. Every component in the Rust safety layer states its budget in crate
documentation and carries Criterion benchmarks under `benches/`. The neural
inference latency is measured on the development machine through the v1.x
line and becomes a constraint on model complexity and quantization strategy. A system
that averages well but misses one frame in a hundred still drops that object
on the floor. Moving a latency budget is a specification change, not an
implementation detail.

## Development Environment

### Required Tools

git, a stable Rust toolchain with `cargo-nextest`, `cargo-llvm-cov` and
`cargo-deny`, and Node for the cc-sdd installer. `./scripts/setup.sh`
reports what is missing and how to install it rather than installing
toolchains silently.

### Common Commands

```bash
# Set up: ./scripts/setup.sh
# Gate:   ./scripts/validate.sh
# Specs:  /kiro-discovery <idea>
```

`scripts/validate.sh` is the only gate. It checks the standards submodules,
then runs the full Rust chain once a `Cargo.toml` exists: `cargo fmt
--check`, clippy with warnings denied, nextest, doc tests, `cargo doc` with
`RUSTDOCFLAGS="-D warnings"`, `cargo deny check`, and coverage. CI runs the
same script as its only step, so the two cannot disagree. Nothing is pushed
until it exits 0.

## Key Technical Decisions

- **Rust owns safety, neural networks own perception-action.** The safety
  layer in Rust enforces invariants: collision checks, actuator limits, and
  emergency stops. Neural inference provides perception and policy execution
  but is always checked against safety constraints before physical action.
- **Learned policy is trained in simulation, deployed with safety checks.**
  MuJoCo simulation via FRET provides the training environment. Domain
  randomization is what a later hardware era would rely on to cross the
  simulation gap; the v1.x line measures nothing outside simulation.
- **Zero-copy shared memory between Rust and neural inference.** Visual
  embeddings flow one direction; action distributions flow back. Minimizing
  latency and memory copies is essential for real-time performance.
- **Policy artifacts are versioned separately from code.** A policy is named
  by training timestamp and checksum, fetched by a script. Training data
  (demonstrations, MuJoCo trajectories) are logged and versioned to enable
  policy retraining and debugging.
- **Standards are pinned submodules.** `standards/guidelines` and
  `standards/cc-sdd` sit at tags, so any commit reproduces the rules that
  applied when it was written. Moving a pin is its own commit.
- **Prose compression is switched off.** `.caveman.json` at the repository
  root sets caveman to `off`, because its plugin registers a `SessionStart`
  hook and would otherwise compress prose that lands in the repository.

---
_Document standards and patterns, not every dependency_
