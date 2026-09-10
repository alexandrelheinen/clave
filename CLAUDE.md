# Claude instructions

This file is a bridge. Rules live in the documents it points at, and it
should stay short enough that every line earns its place in context.

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
| Project constitution, quality gates, merge policy | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Coding notes specific to CLAVE | [docs/guidelines.md](docs/guidelines.md) |
| Standards, toolchain, and how to install it | [standards/README.md](standards/README.md) |
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

Do not start implementing a feature that has no approved spec. A change
small enough to skip the spec is a change `/kiro-discovery` will route
directly, which is a decision it makes rather than one to assume.

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

## Before push

```bash
./scripts/validate.sh
```

Do not push or update a pull request until it exits 0, and never describe
a gate as passing without having run it.
