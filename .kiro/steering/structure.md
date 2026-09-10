# Project Structure

## Organization Philosophy

One Cargo workspace, crates split by pipeline stage rather than by
technical layer, so a stage owns its types, its queue policy, and its
latency budget together. Shared rules are never copied into a crate: they
live once in `standards/` and are referenced.

## Directory Patterns

### Crates
**Location**: `crates/<name>/`
**Purpose**: Rust source, one crate per pipeline stage or shared concern.
**Example**: A stage crate holds its unit tests co-located, its integration
tests in `tests/`, and its Criterion benchmarks in `benches/` when it sits
in the capture-to-decision path.

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
**Purpose**: `guidelines.md` for coding notes specific to CLAVE, and the
logo under `images/`. A gate or constraint deliberately loosened is
recorded in `docs/decisions.md`, which lands with the first such decision.
The project's one standing deviation, its Portuguese name, is recorded in
`CONTRIBUTING.md` instead.

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

- **The clock draws the boundary.** Anything between capture and the pick
  decision is Rust. Training and dataset work is Python and hands over an
  ONNX file.
- **Stages talk through bounded queues.** The overflow policy is part of
  the interface, stated where the queue is declared.
- **Contracts point outward, source does not come in.** The pick decision
  is a serializable type defined here; consumers adapt to it. ARCO, FRET,
  Luthier, and BOSSA are never vendored.
- **Documentation is timeless.** A README or a file under `docs/`
  describes what the system is, in the present tense. History belongs to
  git, the changelog, and the issue tracker.
- **Traceability runs both ways.** Every acceptance criterion is referenced
  by at least one test, and every test guarding a requirement names that
  requirement's id, so the mapping is greppable from either side.

---
_Document patterns, not file trees. New files following patterns should not require updates_
