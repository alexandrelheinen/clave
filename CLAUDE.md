# Claude instructions

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

## Before push

```bash
./scripts/validate.sh
```

Do not push or update a pull request until it exits 0, and never describe
a gate as passing without having run it.
