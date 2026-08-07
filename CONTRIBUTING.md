# Contributing to CLAVE

This document is the **single source of truth** for how humans and AI agents
contribute to CLAVE (Cross-Language Architecture for Vision & Edge). It defines
Specification-Driven Development (SDD), the V-cycle lifecycle, quality gates,
and agent policy.

Do not duplicate these rules in other files. `AGENTS.md`, `CLAUDE.md`,
`CURSOR.md`, and `.github/copilot-instructions.md` exist only as thin entry
points that point here.

For coding conventions (C# / Rust style, naming, memory rules), see
[docs/guidelines.md](docs/guidelines.md). That file covers *how* code is
written; this file covers *how work is planned, specified, verified, and merged*.

## Table of contents

1. [Ecosystem context](#ecosystem-context)
2. [Development setup](#development-setup)
3. [Spec-driven development (SDD)](#spec-driven-development-sdd)
4. [V-cycle software development lifecycle](#v-cycle-software-development-lifecycle)
5. [Combining SDD, V-cycle, and TDD](#combining-sdd-v-cycle-and-tdd)
6. [Quality gates](#quality-gates)
7. [Definition of Ready and Definition of Done](#definition-of-ready-and-definition-of-done)
8. [Pull request and merge policy](#pull-request-and-merge-policy)
9. [Rules for AI agents](#rules-for-ai-agents)
10. [Reference documents](#reference-documents)
11. [Pre-merge checklist](#pre-merge-checklist)

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

## Spec-driven development (SDD)

**Spec-driven development** treats written specifications—not code—as the
primary artifact. Code, tests, and design notes are derived from and validated
against those specs.

### What a spec must contain

| Element | Purpose | Where it lives |
| --- | --- | --- |
| **Intent** | Why the change exists | Issue title/body or PR summary |
| **Scope** | What is in and out of bounds | Issue or PR description |
| **Acceptance criteria** | Observable conditions of done | Issue checklist or PR test plan |
| **Traceability** | Link to roadmap phase / `FR-*` when applicable | Issue, PR, or test comments |
| **Constraints** | Non-negotiable rules (no native SDKs in Phase 0, TreatWarningsAsErrors, …) | This file + [docs/guidelines.md](docs/guidelines.md) |
| **Design notes** | Interfaces, modules, edge cases (when non-trivial) | PR description or `docs/` |

Write acceptance criteria in concrete, testable language (EARS-style: "When …,
the system shall …").

### SDD workflow in this repo

1. **Specify** — Intent, scope, and acceptance criteria in an issue or PR.
2. **Plan** — Map affected V-cycle levels, docs, and test levels.
3. **Task** — Focused, rebase-friendly commits; each traces to a criterion.
4. **Implement and verify** — Stubs/tests before heavy implementation when useful; run quality gates locally before push.
5. **Review** — Code matches the spec; tests prove criteria. **Humans merge; agents do not.**

### Rigor levels

| Level | When to use |
| --- | --- |
| **Spec-first** | Any merged change (minimum) |
| **Spec-anchored** | Public API, architecture, or `docs/` changes |
| **Spec-as-source** | Large or AI-assisted features (explicit task breakdown before coding) |

### Rules

- Do not implement without a written spec (issue or PR with acceptance criteria).
- When requirements change mid-task, update the spec first, then code and tests.
- Regressions: failing test first, then fix.
- Do not add duplicate workflow documentation outside this file and
  [docs/guidelines.md](docs/guidelines.md).

---

## V-cycle software development lifecycle

Each level has a descending artifact (specification or design) and an ascending
validation method. Both sides of a level must be addressed before moving on.

```text
Level 1 — Functional specification  ◄──────────────►  Acceptance / smoke validation
  Level 2 — Architecture & interfaces  ◄──────────►  Contract / integration tests
    Level 3 — Module stubs & public API  ◄────────►  xUnit + cargo unit tests
      Level 4 — Implementation & private code  ◄──►  Full validate.sh + CI
```

An imperative order (implement, add, fix…) always implies the **full V-cycle**—not
just the code.

| Phase | Left (specify / design) | Right (verify) |
| --- | --- | --- |
| 1 | Requirements and acceptance criteria | Acceptance / CLI smoke |
| 2 | System design: boundaries, failure modes | Cross-module scenarios |
| 3 | Module API and stubs | Unit tests |
| 4 | Implementation | Full local + CI gates |

---

## Combining SDD, V-cycle, and TDD

```text
SDD (what & why)  →  V-cycle (structure each level)  →  TDD (build each unit)
     spec                 design ↔ tests                    red → green → refactor
```

At the unit level, prefer TDD: failing test → minimal code → refactor.

---

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

Additional rules:

- No secrets in the tree (use examples under `config/` only).
- Nullable reference types enabled; warnings are errors.
- Prefer rebase-friendly, unitary commits (one logical step each).
- Conventional commit subjects encouraged (`feat:`, `fix:`, `docs:`, `test:`,
  `ci:`, `chore:`, …).

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

1. Treat this file as the constitution; thin bridges only elsewhere.
2. Prefer small, reviewable diffs; do not expand scope beyond the active phase.
3. Phase 0 / early phases: **no** RealSense, OpenCVSharp, ONNX Runtime, TorchSharp,
   or EtherCAT native bindings unless the task explicitly advances that phase.
4. Do not vendor arco / fret / luthier / bossa / website into this repo.
5. Run `./scripts/validate.sh` before claiming done; fix failures yourself.
6. Never commit secrets, credentials, or machine-local telemetry overrides.
7. Do not merge PRs; leave merge to the owner.
8. When blocked on missing toolchains, install via `./scripts/setup.sh` or document
   the exact blocker—do not invent green CI.

Conflict resolution order:

1. Direct maintainer request in the active task
2. [CONTRIBUTING.md](CONTRIBUTING.md) (this file)
3. [docs/guidelines.md](docs/guidelines.md)
4. [docs/specification.md](docs/specification.md)
5. Modern .NET / Rust best practices

---

## Reference documents

| Document | Role |
| --- | --- |
| [README.md](README.md) | Product identity, architecture diagram, build entry |
| [docs/specification.md](docs/specification.md) | Functional / Phase 0 spec |
| [docs/architecture.md](docs/architecture.md) | Module boundaries |
| [docs/roadmap.md](docs/roadmap.md) | Phased MAF-aligned plan |
| [docs/guidelines.md](docs/guidelines.md) | Coding conventions |

---

## Pre-merge checklist

- [ ] Spec / PR acceptance criteria are clear and testable
- [ ] Scope matches the roadmap phase (no premature native SDKs)
- [ ] Unit tests cover new behavior (xUnit and/or cargo)
- [ ] `./scripts/validate.sh` exits 0 locally
- [ ] Docs updated if architecture or public API changed
- [ ] No secrets or machine-local config committed
- [ ] PR has Summary + Test plan; owner will merge
