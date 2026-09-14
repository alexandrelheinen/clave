# Contributing to CLAVE

This document is the single source of truth for CLAVE's own project
context: what this repository is, its quality gates, and its merge policy.
Generic method, writing, and naming rules live in
[standards/](standards/README.md) and are not repeated here.

`AGENTS.md`, `CLAUDE.md`, `CURSOR.md`, and
`.github/copilot-instructions.md` are thin bridges that point here and at
the standards. Do not write rules into them.

## Table of contents

1. [What this repository is](#what-this-repository-is)
2. [Ecosystem context](#ecosystem-context)
3. [Development setup](#development-setup)
4. [Method](#method)
5. [Quality gates](#quality-gates)
6. [Definition of Ready and Definition of Done](#definition-of-ready-and-definition-of-done)
7. [Pull request and merge policy](#pull-request-and-merge-policy)
8. [Rules for AI agents](#rules-for-ai-agents)
9. [Documented deviations](#documented-deviations)

---

## What this repository is

CLAVE is a learned perception-action system for waste sorting under hard
safety constraints. A neural policy network fuses visual perception, object
tracking, and pick timing into an end-to-end learned policy trained via
imitation and reinforcement learning. The policy runs under a deterministic
safety layer in Rust that enforces collision checks, actuator limits, and
hardware interlocks. See [README.md](README.md) for the problem statement.

## Ecosystem context

CLAVE belongs to a family of projects sharing one method and one set of
guidelines. Point contracts at siblings; never vendor their source trees
into this repository.

| Project | Role |
| --- | --- |
| **CLAVE** (this repo) | Learned perception-action policy, safety interlocks |
| **[ARCO](https://github.com/alexandrelheinen/arco)** | Motion planning for continuous trajectory waypoints |
| **[FRET](https://github.com/alexandrelheinen/fret)** | Training environment, kinematic constraints, reward functions |
| **[Luthier](https://github.com/alexandrelheinen/luthier)** | Photogrammetry for sim-to-real calibration |
| **[BOSSA](https://github.com/alexandrelheinen/bossa)** | Edge inference runtime, neural telemetry logging |

## Development setup

Requirements: git, a stable Rust toolchain, and Node for the cc-sdd
installer.

```bash
git clone --recurse-submodules https://github.com/alexandrelheinen/clave.git
cd clave
./scripts/setup.sh
./scripts/validate.sh
```

`scripts/setup.sh` reports what is missing and how to install it rather
than installing toolchains behind your back. The agent toolchain, meaning
cc-sdd and the Claude Code plugins, is documented in
[standards/README.md](standards/README.md).

## Method

Spec-driven development and TDD are defined in
[workflow/sdd.md](standards/guidelines/workflow/sdd.md) and
[workflow/tdd.md](standards/guidelines/workflow/tdd.md), and executed
through the cc-sdd skills. Enter through `/kiro-discovery <idea>`.

Specifications are committed under `.kiro/specs/`. A feature without an
approved spec does not get implemented, and a spec is approved by the
maintainer at its phase gate, not by the agent that wrote it.

## Quality gates

Before every push on a branch:

```bash
./scripts/validate.sh
```

It must exit 0, and CI runs the same script so the two cannot disagree.
The Rust gates it will run once the first crate lands are fixed by
[languages/rs.md](standards/guidelines/languages/rs.md): `cargo fmt
--check`, `cargo clippy -D warnings`, `cargo nextest run`, doc tests,
`cargo doc` with warnings denied, `cargo deny check`, and coverage at 80%
or better. Those are not per-PR negotiations.

No secrets in the tree, ever. Commit format and PR hygiene follow
[workflow/commits.md](standards/guidelines/workflow/commits.md).

## Definition of Ready and Definition of Done

**Ready**

- An approved spec exists with testable acceptance criteria.
- The test approach is identified, unit tests at minimum.
- Any new dependency has a stated reason.

**Done**

- Acceptance criteria are demonstrated by tests, referenced by their id.
- `./scripts/validate.sh` exits 0.
- Documentation is updated when a public contract or a boundary changed.
- The pull request states intent and how it was tested.
- The maintainer merges.

## Pull request and merge policy

- Branch from an up-to-date `main`.
- Keep history rebase-friendly and commits atomic.
- Scale the evidence in the pull request body to the blast radius of the
  change, per
  [agents/claude.md](standards/guidelines/agents/claude.md).
- Agents open and update pull requests. The maintainer merges, unless the
  maintainer asks otherwise in the active task.

## Rules for AI agents

General agent behavior, including the no-fabricated-evidence rule, follows
[agents/claude.md](standards/guidelines/agents/claude.md). CLAVE adds:

1. Do not claim a gate passed without running it. Do not claim inference
   latency or policy performance without evidence from the target BOSSA
   hardware.
2. Do not vendor arco, fret, luthier, or bossa into this repository. Safety
   contracts point outward; source does not come in.
3. Do not commit trained policies to the repository. Policies are versioned
   and fetched by deployment scripts.
4. Do not implement ahead of an approved spec. Policy training strategies,
   safety constraints, and hardware limits must be specified before
   implementation.
5. Requirements come from a spec, never from commit history or training
   metrics. Policy performance data is archived but not a substitute for
   specification and test evidence.
6. When writing training code or policy interfaces, follow Python and Rust
   style rules from [standards/guidelines/languages/](standards/guidelines/languages/),
   and document policy versioning and interface contracts in crate docs.

The precedence order when documents disagree is in
[standards/README.md](standards/README.md#precedence).

## Documented deviations

The shared guidelines allow a project to deviate on purpose, provided the
deviation is written down. CLAVE has one. Where an installed skill or
plugin disagrees with the guidelines instead, the answer is in
[integrations/toolkits.md](standards/guidelines/integrations/toolkits.md),
not here.

- **Project name.** `style/naming.md` requires US English everywhere.
  CLAVE's name and its expansion, Coleta de Lixo Através de Visão
  Embarcada, are Portuguese, matching the musical family the project
  belongs to. This covers the name alone. Identifiers, comments,
  documentation, commit messages, and log strings stay in US English, so
  do not translate them and do not anglicize the name.
