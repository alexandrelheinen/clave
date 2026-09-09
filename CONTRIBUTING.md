# Contributing to CLAVE

This document is the **single source of truth** for CLAVE's own project
context: what this repo is, its ecosystem, and its specific quality gates
and merge policy. Generic method (Spec-Driven Development, the V-cycle,
TDD), writing, and naming guidelines live in [.guidelines/](.guidelines/),
a shared submodule, not here.

Do not duplicate rules from the submodule in other files. `AGENTS.md`,
`CLAUDE.md`, `CURSOR.md`, and `.github/copilot-instructions.md` exist only
as thin entry points that point to `.guidelines/` and this file.

For coding conventions (C# / Rust style, naming, memory rules), see
[docs/guidelines.md](docs/guidelines.md) for what is specific to CLAVE, and
[.guidelines/languages/cs.md](.guidelines/languages/cs.md) /
[.guidelines/languages/rs.md](.guidelines/languages/rs.md) for the shared
baseline.

## Table of contents

1. [Ecosystem context](#ecosystem-context)
2. [Development setup](#development-setup)
3. [Quality gates](#quality-gates)
4. [Definition of Ready and Definition of Done](#definition-of-ready-and-definition-of-done)
5. [Pull request and merge policy](#pull-request-and-merge-policy)
6. [Rules for AI agents](#rules-for-ai-agents)
7. [Reference documents](#reference-documents)
8. [Pre-merge checklist](#pre-merge-checklist)

---

## Ecosystem context

CLAVE is one project in a musical-named family that shares SDD + V-cycle
methodology. Bridge contracts toward siblings later; **do not vendor** their
source trees into this repository.

| Project | Role |
| --- | --- |
| **[CLAVE](https://github.com/alexandrelheinen/clave)** (this repo) | Cross-language lab: .NET hosts, vision/capture/bus stubs, Rust hot paths |
| **[ARCO](https://github.com/alexandrelheinen/arco)** | Motion planning and control algorithms |
| **[FRET](https://github.com/alexandrelheinen/fret)** | ROS 2 planning + control stack; observation contracts CLAVE may align with |
| **[Luthier](https://github.com/alexandrelheinen/luthier)** | Photogrammetry → colored point clouds; calibration / 3D path inspiration |
| **[BOSSA](https://github.com/alexandrelheinen/bossa)** | Edge runtime + telemetry for IoT on ARM Linux |
| **[Personal website](https://alexandrelheinen.pages.dev)** | Methodology articles and portfolio (not product code for CLAVE) |

### What CLAVE provides

| Artifact | Role |
| --- | --- |
| `Clave.sln` (.NET 8) | Host (Phase 1 telemetry), Vision, Capture, Bus, Interop, Cli + xUnit tests |
| `rust/clave-core` | Auditable ring-buffer stub (`SampleRing`) |
| `./scripts/validate.sh` | Local gate matching CI |
| `docs/host-telemetry.md` | Full-mode policies and GC profiling notes |

Specification stack:

| Level | Specification artifacts | Validation artifacts |
| --- | --- | --- |
| 1 — Functional | [docs/specification.md](docs/specification.md), [docs/roadmap.md](docs/roadmap.md) | Acceptance criteria / smoke CLI |
| 2 — Architecture | [docs/architecture.md](docs/architecture.md), [docs/host-telemetry.md](docs/host-telemetry.md), README module map | Project references + contract stubs |
| 3 — Module API | Public types under `src/` and `rust/clave-core` | xUnit + `cargo test` |
| 4 — Implementation | Host hardened in Phase 1; native backends in later phases | Full `./scripts/validate.sh` + CI |

---

## Development setup

**Requirements:**

- .NET SDK 8.0 (see `global.json`; `rollForward: latestFeature`)
- Stable Rust toolchain (`rustc`, `cargo`)
- Git

```bash
git clone https://github.com/alexandrelheinen/clave.git
cd clave
./scripts/setup.sh
./scripts/build.sh
./scripts/validate.sh
```

`mise` is not required unless you choose to pin toolchains locally yourself.

---

## Method

Spec-Driven Development, the V-cycle, and TDD are defined once in
[.guidelines/workflow/sdd.md](.guidelines/workflow/sdd.md),
[.guidelines/workflow/integration.md](.guidelines/workflow/integration.md),
and [.guidelines/workflow/tdd.md](.guidelines/workflow/tdd.md). Follow those.
CLAVE's own additions: acceptance criteria and specs may reference a
roadmap phase or `FR-*` id (see [docs/specification.md](docs/specification.md)),
and non-negotiable constraints specific to this repo (no native SDKs before
the matching roadmap phase, `TreatWarningsAsErrors`) live in
[docs/guidelines.md](docs/guidelines.md).

## Quality gates

Before every push on a PR branch, run:

```bash
./scripts/validate.sh
```

This must exit 0. It runs:

1. `dotnet build Clave.sln` (TreatWarningsAsErrors)
2. `dotnet test Clave.sln`
3. `cargo test --manifest-path rust/clave-core/Cargo.toml`

CI (`.github/workflows/ci.yml`) runs the same validate script on pull requests
and pushes to `main`, with .NET 8 and stable Rust.

Additional rule specific to this repo: no secrets in the tree, use examples
under `config/` only. Commit format and PR hygiene follow
[.guidelines/workflow/commits.md](.guidelines/workflow/commits.md).

---

## Definition of Ready and Definition of Done

**Ready**

- Written intent, scope, and acceptance criteria exist.
- Roadmap phase / out-of-scope native deps considered.
- Test approach identified (unit minimum).

**Done**

- Acceptance criteria demonstrated by tests or documented smoke steps.
- `./scripts/validate.sh` passes.
- Docs updated when architecture or public contracts change.
- PR description includes Summary and Test plan.
- Owner (human) merges.

---

## Pull request and merge policy

- Branch from an up-to-date `main`.
- Keep history rebase-friendly; avoid noisy merge commits on feature branches.
- PR body: intent, acceptance checklist, phase note (e.g. Phase 0 only).
- **Owner merges manually.** Agents open/update PRs but never merge.
- Do not claim hardware or native-SDK validation without evidence.

---

## Rules for AI agents

General agent behavior (evidence, no fabrication, small diffs, git safety)
follows [.guidelines/agents/claude.md](.guidelines/agents/claude.md). CLAVE
adds:

1. Phase 0 / early phases: **no** RealSense, OpenCVSharp, ONNX Runtime,
   TorchSharp, or EtherCAT native bindings unless the task explicitly
   advances that phase.
2. Do not vendor arco / fret / luthier / bossa / website into this repo.
3. When blocked on missing toolchains, install via `./scripts/setup.sh` or
   document the exact blocker; do not invent green CI.

Conflict resolution order:

1. Direct maintainer request in the active task
2. [CONTRIBUTING.md](CONTRIBUTING.md) (this file)
3. [.guidelines/](.guidelines/) (shared method, writing, naming, style)
4. [docs/guidelines.md](docs/guidelines.md) (CLAVE-specific coding notes)
5. [docs/specification.md](docs/specification.md)
6. Modern .NET / Rust best practices

---

## Reference documents

| Document | Role |
| --- | --- |
| [README.md](README.md) | Product identity, architecture diagram, build entry |
| [.guidelines/](.guidelines/) | Shared method, writing, naming, and per-language style (submodule) |
| [docs/specification.md](docs/specification.md) | Functional / Phase 0 spec |
| [docs/architecture.md](docs/architecture.md) | Module boundaries |
| [docs/roadmap.md](docs/roadmap.md) | Phased MAF-aligned plan |
| [docs/guidelines.md](docs/guidelines.md) | CLAVE-specific coding notes |

---

## Pre-merge checklist

- [ ] Spec / PR acceptance criteria are clear and testable
- [ ] Scope matches the roadmap phase (no premature native SDKs)
- [ ] Unit tests cover new behavior (xUnit and/or cargo)
- [ ] `./scripts/validate.sh` exits 0 locally
- [ ] Docs updated if architecture or public API changed
- [ ] No secrets or machine-local config committed
- [ ] PR has Summary + Test plan; owner will merge
