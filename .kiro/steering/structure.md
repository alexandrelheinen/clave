# Project Structure

## Organization Philosophy

One Cargo workspace, crates split by responsibility: safety-critical
components in Rust, neural inference abstractions in Rust wrappers around
external runtimes. The safety layer owns collision checking, actuator
limits, and emergency stops. The inference layer owns policy loading,
embeddings, and action sampling. No mixing: a crate either enforces safety
constraints or it does not. Shared rules are never copied into a crate:
they live once in `standards/` and are referenced.

## Directory Patterns

### Crates
**Location**: `crates/<name>/`
**Purpose**: Rust source, organized by responsibility. Safety-layer crates
(collision, actuators, interlocks) are hardened and benchmarked. Inference
crates (policy loading, embeddings, shared memory) handle communication with
neural runtimes. Shared utility crates support both layers.
**Example**: A safety crate checks every pick action against collision bounds
and actuator limits before allowing execution. It holds unit tests co-located,
integration tests against simulated conveyor geometry in `tests/`, and
Criterion benchmarks in `benches/` to prove latency is within budget.

### Specifications
**Location**: `.kiro/specs/<feature>/`
**Purpose**: `requirements.md`, `design.md`, and `tasks.md` per feature,
committed. A feature without an approved spec does not get implemented, and
requirements come from the spec rather than from commit history.

### Project memory
**Location**: `.kiro/steering/`
**Purpose**: The files in this directory. Patterns and principles that
outlive a single feature.

### Shared standards
**Location**: `standards/`
**Purpose**: Two pinned submodules, `guidelines` for method, writing,
naming, and per-language style, and `cc-sdd` for the spec-driven method
and its skills. Read-only from this repository's point of view; changing a
rule means moving the pin.

### Project documentation
**Location**: `docs/`
**Purpose**: `guidelines.md` for coding notes specific to CLAVE (safety-layer
Rust hardening, neural inference integration, policy training). Training
guides and policy interface definitions live here. The logo is under
`images/`. A gate or constraint deliberately loosened is recorded in
`docs/decisions.md`, which lands with the first such decision. The project's
one standing deviation, its Portuguese name, is recorded in `CONTRIBUTING.md`
instead.

### Scripts
**Location**: `scripts/`
**Purpose**: `setup.sh` reports the toolchain, `validate.sh` is the gate.
Shell follows `standards/guidelines/languages/sh.md`.

### Agent bridge files
**Location**: repository root
**Purpose**: `AGENTS.md`, `CLAUDE.md`, `CURSOR.md`, and
`.github/copilot-instructions.md` point at `CONTRIBUTING.md` and the
standards. They hold pointers, never rules, so five copies cannot drift
apart.

## Naming Conventions

- **Crates**: `kebab-case` on disk, `snake_case` when imported.
- **Files**: `snake_case`, matching the module they define.
- **Types, traits, enum variants**: `PascalCase`.
- **Functions, methods, variables, modules**: `snake_case`.
- **Constants and statics**: `SCREAMING_SNAKE_CASE`.
- **Physical quantities**: name the quantity and not the unit, qualifier
  first, so `max_belt_speed` rather than `belt_speed_max_ms`. Counts take a
  `_count` suffix and collections are pluralized.
- **Strong types over primitives**: a value with a unit or a domain meaning
  gets a newtype, so `FrameIndex(u32)` cannot be passed where
  `SampleCount(u32)` belongs.
- **Language**: US English in identifiers, comments, documentation, commit
  messages, and log strings. The project name and its Portuguese expansion
  are the single documented exception, recorded in `CONTRIBUTING.md`.
- **Tests**: named after the behavior they prove, reading as a spec
  sentence, never after their inputs.

## Import Organization

Three groups separated by a blank line: `std`, then external crates, then
`crate`, `super`, and `self`. Stable rustfmt sorts within a group and
leaves the blank lines alone, so the layout survives a reformat. The
options that would enforce this automatically remain nightly-only as of
September 2026, which makes the grouping an author convention and a
reviewer check.

```rust
use std::collections::HashMap;
use std::sync::Arc;

use serde::Deserialize;
use tokio::sync::mpsc;

use crate::config::Config;
```

## Code Organization Principles

- **Safety layer in Rust, learned layer behind a contract.** Anything that
  affects hardware safety (collision checks, actuator limits, interlocks) is
  Rust and hardened. Policy learning and inference are Python and external
  runtimes, called through a zero-copy shared memory interface that minimizes
  latency.
- **Neural inference is wrapped by Rust.** A Rust wrapper handles embeddings,
  action sampling, and latency measurement, and enforces the contract between
  the policy and the safety layer. Which runtime it wraps is settled at the
  `learning-platform` step of the roadmap.
- **Zero-copy communication between Rust and neural inference.** Visual
  embeddings and action distributions flow through shared memory, not
  serialization. Latency is measured end-to-end: capture to safety-checked
  action.
- **Contracts point outward, source does not come in.** The policy interface
  (input dimensions, output distributions, quantization) and the decision
  CLAVE publishes are defined here, and FRET adapts to them as the consumer.
  No sibling is ever vendored.
- **Training happens in Python and MuJoCo, independent of runtime.** Policy
  training runs on development machines using PyTorch, imitation learning
  from human demonstrations, and RL in MuJoCo via FRET. Trained policies are
  versioned and fetched by deployment scripts, not committed to this repo.
- **Documentation is timeless.** A README or a file under `docs/`
  describes what the system is, in the present tense. Training data,
  demonstrations, and experiment logs are archived separately. History
  belongs to git, the changelog, and the issue tracker.
- **Traceability runs both ways.** Every acceptance criterion is referenced
  by at least one test, and every test guarding a requirement names that
  requirement's id, so the mapping is greppable from either side.

---
_Document patterns, not file trees. New files following patterns should not require updates_
