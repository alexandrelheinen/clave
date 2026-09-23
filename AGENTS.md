# AGENTS.md

This file provides guidance to AI coding agents (Antigravity, Gemini, Claude, Cursor, and other agents) when working with code in this repository.

CLAVE learns and executes a perception-action policy for waste sorting on a
conveyor belt. A neural architecture fuses visual perception, object
tracking, and pick timing into an end-to-end learned policy. The policy
runs with hard safety guarantees: a Rust core enforces collision checks and
hardware interlocks. [README.md](README.md) has the problem in full,
including why learned policies under safety constraints matter more than
classifiers alone. Read it before designing anything.

@.guidelines/workflow/sdd.md
@.guidelines/workflow/integration.md
@.guidelines/workflow/tdd.md
@.guidelines/agents/writing.md
@.guidelines/style/naming.md
@.guidelines/languages/rs.md
@.guidelines/languages/py.md
@.guidelines/languages/sh.md

## Read when the task touches them

| Topic | Document |
| --- | --- |
| What the project does, and the engineering problem behind it | [README.md](README.md) |
| Project constitution, quality gates, merge policy | [CONTRIBUTING.md](CONTRIBUTING.md) |
| What each block does, its inputs and outputs | [docs/architecture.md](docs/architecture.md) |
| Every measured number a gate or a config value rests on | [docs/measurements.md](docs/measurements.md) |
| The version ladder, release criteria, and the open defects each step closes | [docs/roadmap.md](docs/roadmap.md) |
| What a feature has to do, and the ids its tests reference | [docs/requirements/](docs/requirements/) |
| Why an option was chosen over the ones the field actually uses | [docs/research/](docs/research/) |
| The mathematics the arm's motion is planned with | [docs/trajectory-formulation.md](docs/trajectory-formulation.md) |
| How a waste object is described, independently of which sensor saw it | [docs/perception-contract.md](docs/perception-contract.md) |
| Coding notes specific to CLAVE | [docs/guidelines.md](docs/guidelines.md) |
| Guidelines, toolchain, and how to install it | [.guidelines/README.md](.guidelines/README.md) |
| A skill or plugin telling you to do what the guidelines forbid | [.guidelines/integrations/toolkits.md](.guidelines/integrations/toolkits.md) |
| Commits, branching, review, integration | [.guidelines/workflow/](.guidelines/workflow/) |
| Comments and error handling across languages | [.guidelines/style/comments.md](.guidelines/style/comments.md), [.guidelines/style/errors.md](.guidelines/style/errors.md) |
| Python, for model training and dataset tooling | [.guidelines/languages/py.md](.guidelines/languages/py.md) |
| Rust, for the safety layer and bridge | [.guidelines/languages/rs.md](.guidelines/languages/rs.md) |
| Shell, for anything under `scripts/` | [.guidelines/languages/sh.md](.guidelines/languages/sh.md) |

Conflict order: direct maintainer request > CONTRIBUTING.md > `.guidelines/`
> `docs/guidelines.md`.

## Method

Specification-driven development runs on plain documents, with no toolkit
driving it. A feature gets a document under `docs/requirements/<feature>.md`
before it gets code, carrying the intent, the scope, the acceptance criteria
and the traceability ids that
[.guidelines/workflow/sdd.md](.guidelines/workflow/sdd.md) asks for. Structural
choices go in [docs/architecture.md](docs/architecture.md), and a constraint
that moves says why in the document that carries it.

Do not start implementing a feature that has no written spec. The rigor
scales with the change, and the floor in
[.guidelines/workflow/sdd.md](.guidelines/workflow/sdd.md#gating-rule) is a few
written bullet points before code. A maintainer may waive it for a given
change; nobody may waive it on the maintainer's behalf.

Acceptance criterion ids are append-only. Never renumber one and never reuse
one, even after the requirement it named is gone, and reference the id from
the test that guards it so the mapping is greppable in both directions.
`docs/requirements/learned-tracker.md` records which numbers are already
spent.

## Language

**Rust** for the safety layer: collision checking, actuator limits, hardware
interlocks, and the process-boundary check on every proposal. The hardened lint
tiers in [.guidelines/languages/rs.md](.guidelines/languages/rs.md) are not
suggestions. Arithmetic overflow, casts, and unwraps fail silently in this
domain and turn into physical faults.

**Python** for policy training: imitation learning from a scripted expert
today, with reinforcement learning and broader domain randomization on the
roadmap. Trained policies are versioned and deployed, never kept in training
form at runtime. Python proposes over a Unix datagram; Rust never loads
weights.

## Prose

Everything committed follows
[.guidelines/agents/writing.md](.guidelines/agents/writing.md), including
commit messages, PR bodies, specs, and code comments. The `caveman` plugin
compresses agent output and contradicts that rule, so `.caveman.json` at
the repository root sets its mode to `off`. Invoke it with `/caveman` when
you want it and leave it off for anything that lands in the repository. See
[.guidelines/README.md](.guidelines/README.md#caveman-is-switched-off-in-this-repository).

## Setup and validation

New to the repo? Clone and set up with:

```bash
git clone --recurse-submodules https://github.com/alexandrelheinen/clave.git
cd clave
./scripts/setup.sh
```

The setup script reports which tools are missing and how to install them. It
does not install toolchains silently; it is a dry run that lets the developer
choose their installation method.

## Common tasks

- **Specification**: Write `docs/requirements/<feature>.md` before the code,
  and reference its acceptance criterion ids from the tests that guard them.
- **Run a single test**: `cargo nextest run -p <crate> <test_name>` (nextest is
  the runner, not cargo test directly).
- **Run benchmarks**: `cargo bench -p <crate>` in a crate with a `benches/`
  directory.
- **Check formatting only**: `cargo fmt --all --check` (no `--check` flag to apply
  fixes).
- **Run clippy only**: `cargo clippy --all-targets --all-features -- -D warnings`.
- **Check coverage**: `cargo llvm-cov --all-features` (shows HTML report path).

## Crate layout

Crates go in `crates/<name>/` organized by responsibility:

**Safety-layer crates** (collision, actuators, interlocks, safety checks):
- Hardened lint tier: arithmetic and cast safety are enforced.
- Unit tests colocated in `#[cfg(test)] mod tests`.
- Integration tests in `tests/` against simulated conveyor geometry.
- Criterion benchmarks in `benches/` proving latency budgets.

**Inference crates** (proposal encoding, envelope checks, decision publish):
- Baseline lint tier.
- Unit and integration tests for contract enforcement.
- Benchmarks for inference latency on the development machine.

**Shared utility crates**:
- Baseline tier unless they support safety-layer code.

See [docs/guidelines.md](docs/guidelines.md) for which components are Rust
(safety, inference wrappers) and which are Python (training, domain
randomization).

## Hybrid safety and learned behavior

The system splits responsibility: Rust handles safety invariants (no
collisions, no overflows, hardware limits), while neural networks provide
perception and policy. Every policy decision is checked against safety
constraints before physical action. A policy that tries to reach past an
actuator limit is overridden by the safety layer.

Latency is measured end to end, from the frame leaving the simulator to a
safety-checked decision FRET can act on. Every component states its latency
budget at p99 and proves it with a benchmark. Inference latency counts
toward that budget rather than sitting outside it.

The policy interface (input/output dimensions, quantization) is defined as a
Rust type in this repo. Trained policies are versioned separately and fetched
by deployment scripts, never committed. See
[docs/roadmap.md](docs/roadmap.md) for the ladder to v1.0.0 and what each
step has to prove before it is tagged.

## Pre-push gate (mandatory)

```bash
./scripts/validate.sh
```

Do not push or update a pull request until it exits 0. Do not describe a
gate as passing without having run it, and do not claim hardware
validation without evidence.
