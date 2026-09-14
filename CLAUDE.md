# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CLAVE sorts recyclable waste on a conveyor belt: a camera watches the line,
a model classifies each object, a tracker follows it across frames, and the
pipeline decides which channel it belongs in and when to reach for it,
inside a measured latency budget. [README.md](README.md) has the problem in
full, including why the pipeline rather than the classifier is the hard
part. Read it before designing anything.

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
| Coding notes specific to CLAVE | [docs/guidelines.md](docs/guidelines.md) |
| Standards, toolchain, and how to install it | [standards/README.md](standards/README.md) |
| A skill or plugin telling you to do what the guidelines forbid | [integrations/toolkits.md](standards/guidelines/integrations/toolkits.md) |
| Commits, branching, review, integration | [workflow/](standards/guidelines/workflow/) |
| Comments and error handling across languages | [style/comments.md](standards/guidelines/style/comments.md), [style/errors.md](standards/guidelines/style/errors.md) |
| Python, for model training and dataset tooling | [languages/py.md](standards/guidelines/languages/py.md) |
| Shell, for anything under `scripts/` | [languages/sh.md](standards/guidelines/languages/sh.md) |

## Method

Specification-driven development runs through cc-sdd, installed as agent
skills. Start with `/kiro-discovery <idea>`, which routes the work and
names the next command; the phase chain and the reference documents are in
[standards/README.md](standards/README.md#installing-cc-sdd). Specs live in
`.kiro/specs/` and are committed.

Do not start implementing a feature that has no approved spec. Discovery
may offer to route a change straight to implementation; that is a
suggestion, not permission, and the floor in
[workflow/sdd.md](standards/guidelines/workflow/sdd.md#gating-rule) still
applies.

`.kiro/steering/` is cc-sdd's persistent project memory, holding
`product.md`, `tech.md`, and `structure.md`. Run `/kiro-steering` to
bootstrap it if it is empty, before the first discovery, so every later
skill reads the same description of the project instead of re-deriving one.

## Language

Rust for anything on the clock, which is the pipeline itself. Python for
training and dataset work, exporting to ONNX for the Rust runtime to load.
The Rust rules in
[languages/rs.md](standards/guidelines/languages/rs.md) are not
suggestions: the lint tiers, the unsafe policy, and the panic rules are
what this repository gates on.

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

- **Specification**: Start a feature with `/kiro-discovery <idea>`, which routes
  to spec creation via cc-sdd skills. Specs live in `.kiro/specs/` and must be
  approved before implementation begins.
- **Run a single test**: `cargo nextest run -p <crate> <test_name>` (nextest is
  the runner, not cargo test directly).
- **Run benchmarks**: `cargo bench -p <crate>` in a crate with a `benches/`
  directory.
- **Check formatting only**: `cargo fmt --all --check` (no `--check` flag to apply
  fixes).
- **Run clippy only**: `cargo clippy --all-targets --all-features -- -D warnings`.
- **Check coverage**: `cargo llvm-cov --all-features` (shows HTML report path).

## Crate layout

Crates go in `crates/<name>/` and follow one pattern:
- Unit tests colocated in `#[cfg(test)] mod tests` at the bottom of each file.
- Integration tests in `tests/` for the public API.
- Benchmarks in `benches/` for anything with a latency budget (pipeline stages).

See [docs/guidelines.md](docs/guidelines.md) for which parts of the pipeline are
Rust (capture, inference, tracking, pick decision—the clock) and which are Python
(training, dataset tooling—offline work).

## Real-time crate hardening

Pipeline crates take the hardened lint tier, which raises the bar on arithmetic,
casts, and unwraps. A frame index that silently wraps or a cast that silently
truncates is a fault, not a style question. Tooling crates take the baseline
tier. Document your crate in its root-level docs and state which tier it uses.

## Architecture at a glance

Staged pipeline: capture → inference → tracking → pick decision. Every queue
between stages is bounded, and every bounded queue states its overflow policy
(block, drop oldest, or drop newest) as part of the interface. The pick decision
is a serializable type published to siblings (ARCO, FRET); their source is never
vendored here. See [.kiro/steering/](.kiro/steering/) for patterns that outlive
a single feature.
