# Technology Stack

## Architecture

A staged pipeline: capture, inference, tracking, then pick decision. Every
queue between two stages is bounded, and every bounded queue names what
happens when it fills, meaning block, drop the oldest, or drop the newest.
There is no default policy. A stage that cannot state its policy is not
designed yet.

Model training sits outside the pipeline and hands over an ONNX artifact.
A Python process is never in the loop at runtime.

## Core Technologies

- **Language on the clock**: Rust, edition 2024, resolver 3, toolchain
  pinned in `rust-toolchain.toml` with the same floor as `rust-version` in
  `Cargo.toml`.
- **Language off the clock**: Python, for model training and dataset
  tooling.
- **Handover format**: ONNX, loaded by the Rust runtime.
- **Layout**: one Cargo workspace per repository, crates under
  `crates/<name>/`, shared metadata and lints in `[workspace.package]` and
  `[workspace.lints]`.

No application code has landed yet. The first crate arrives with the first
approved specification, and the Rust gates below activate with it.

## Development Standards

### Lint tiers

Pipeline crates take the hardened tier from
`standards/guidelines/languages/rs.md`: `arithmetic_side_effects`,
`as_conversions`, `indexing_slicing`, and the cast lints all deny. A frame
index that silently wraps or a cast that silently truncates is a fault in
this domain, not a style question. Tooling crates, dataset preparation, and
anything offline take the baseline tier.

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

Anything in the capture-to-decision path states its latency budget in its
crate documentation and carries a Criterion benchmark under `benches/`.
Budgets are measured at p99, not at the mean, because a pipeline that
averages well and misses one frame in a hundred still drops that object on
the floor. Moving a budget is a specification change, not an
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

- **Rust owns the clock, Python owns the training.** The split is drawn at
  the ONNX artifact, so the classifier can be replaced without touching the
  pipeline.
- **Model artifacts are referenced, never committed.** A model is named by
  version and checksum and fetched by a script. Datasets are public ones
  (TrashNet, TACO, ZeroWaste) referenced by URL.
- **Standards are pinned submodules.** `standards/guidelines` and
  `standards/cc-sdd` sit at tags, so any commit reproduces the rules that
  applied when it was written. Moving a pin is its own commit.
- **Prose compression is switched off.** `.caveman.json` at the repository
  root sets caveman to `off`, because its plugin registers a `SessionStart`
  hook and would otherwise compress prose that lands in the repository.

---
_Document standards and patterns, not every dependency_
