# AGENTS Instructions

Automated agents working in this repository must follow
[CONTRIBUTING.md](CONTRIBUTING.md) as the **single source of truth** for
development workflow, SDD, the V-cycle, quality gates, and agent policy.

For coding conventions (C# / Rust), follow [docs/guidelines.md](docs/guidelines.md).

**Do not duplicate** workflow or V-cycle rules in this file. When instructions
conflict, resolve in this order:

1. Direct maintainer request in the active task
2. [CONTRIBUTING.md](CONTRIBUTING.md)
3. [docs/guidelines.md](docs/guidelines.md)
4. [docs/specification.md](docs/specification.md)
5. Modern .NET / Rust best practices

An imperative order (implement, add, fix…) always implies the full V-cycle
described in [CONTRIBUTING.md](CONTRIBUTING.md), not code alone.

## Pre-push gates (mandatory)

```bash
./scripts/validate.sh
```

Do not push or update a PR until validate exits 0.

## Cursor Cloud notes

- Install toolchains with `./scripts/setup.sh` if `dotnet` or `cargo` is missing.
- Phase 0 has no hardware SDKs; do not add RealSense/OpenCV/ONNX/SOEM unless the
  task advances that roadmap phase.
- Do not merge PRs; owner merges manually.
