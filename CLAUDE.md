# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CLAVE learns and executes a perception-action policy for waste sorting on a
conveyor belt. A neural architecture fuses visual perception, object
tracking, and pick timing into an end-to-end learned policy. The policy
runs with hard safety guarantees: a Rust core enforces collision checks and
hardware interlocks. [README.md](README.md) has the problem in full,
including why learned policies under safety constraints matter more than
classifiers alone. Read it before designing anything.

This file is a bridge for everything else. Rules live in the documents it
points at, and it should stay short enough that every line earns its place
in context.

## Always loaded

@standards/guidelines/agents/claude.md
@standards/guidelines/agents/writing.md
@standards/guidelines/workflow/sdd.md
@standards/guidelines/workflow/tdd.md
@standards/guidelines/style/naming.md
@standards/guidelines/languages/rs.md

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
| What the line currently achieves, and how good the code is | [docs/reports/](docs/reports/) |
| The mathematics the arm's motion is planned with | [docs/guidance-formulation.md](docs/guidance-formulation.md) |
| How a waste object is described, independently of which sensor saw it | [docs/perception-contract.md](docs/perception-contract.md) |
| Coding notes specific to CLAVE | [docs/guidelines.md](docs/guidelines.md) |
| Standards, toolchain, and how to install it | [standards/README.md](standards/README.md) |
| A skill or plugin telling you to do what the guidelines forbid | [integrations/toolkits.md](standards/guidelines/integrations/toolkits.md) |
| Commits, branching, review, integration | [workflow/](standards/guidelines/workflow/) |
| Comments and error handling across languages | [style/comments.md](standards/guidelines/style/comments.md), [style/errors.md](standards/guidelines/style/errors.md) |
| Python, for model training and dataset tooling | [languages/py.md](standards/guidelines/languages/py.md) |
| Shell, for anything under `scripts/` | [languages/sh.md](standards/guidelines/languages/sh.md) |

## Method

Specification-driven development runs on plain documents, with no toolkit
driving it. A feature gets a document under `docs/requirements/<feature>.md`
before it gets code, carrying the intent, the scope, the acceptance criteria
and the traceability ids that
[workflow/sdd.md](standards/guidelines/workflow/sdd.md) asks for. Structural
choices go in [docs/architecture.md](docs/architecture.md), and a constraint
that moves says why in the document that carries it.

Do not start implementing a feature that has no written spec. The rigor
scales with the change, and the floor in
[workflow/sdd.md](standards/guidelines/workflow/sdd.md#gating-rule) is a few
written bullet points before code. A maintainer may waive it for a given
change; nobody may waive it on the maintainer's behalf.

Acceptance criterion ids are append-only. Never renumber one and never reuse
one, even after the requirement it named is gone, and reference the id from
the test that guards it so the mapping is greppable in both directions.
`docs/requirements/learned-tracker.md` records which numbers are already
spent.

## Language

**Rust** for the safety layer: collision checking, actuator limits, hardware
interlocks, and the zero-copy bridge to neural inference. The hardened lint
tiers in [languages/rs.md](standards/guidelines/languages/rs.md) are not
suggestions. Arithmetic overflow, casts, and unwraps fail silently in this
domain and turn into physical faults.

**Python** for policy training: imitation learning from human demonstrations,
reinforcement learning in MuJoCo simulation via FRET, and domain
randomization for sim-to-real transfer. Trained policies are versioned and
deployed, never kept in training form at runtime.

## Prose

Everything committed follows
[agents/writing.md](standards/guidelines/agents/writing.md), including
commit messages, PR bodies, specs, and code comments. The `caveman` plugin
compresses agent output and contradicts that rule, so `.caveman.json` at
the repository root sets its mode to `off`. Invoke it with `/caveman` when
you want it and leave it off for anything that lands in the repository. See
[standards/README.md](standards/README.md#caveman-is-switched-off-in-this-repository).

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

## Development loop

After any code change, run the local quality gate:

```bash
./scripts/validate.sh
```

The gate checks the standards submodules and runs the full Rust quality chain
once a `Cargo.toml` exists: formatting, clippy, tests, coverage, documentation,
and dependency advisories. CI runs the same script as its only gate, so the
two cannot disagree. Do not push or update a pull request until it exits 0,
and never describe a gate as passing without having run it.

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

**Inference crates** (policy loading, embeddings, shared memory, action sampling):
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
