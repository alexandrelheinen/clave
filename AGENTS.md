# AGENTS Instructions

This file is a bridge only. **Do not add rules here.**

Shared engineering guidelines live in [.guidelines/](.guidelines/) (a git
submodule):

- [.guidelines/workflow/sdd.md](.guidelines/workflow/sdd.md), [integration.md](.guidelines/workflow/integration.md), [tdd.md](.guidelines/workflow/tdd.md) — how work gets done
- [.guidelines/agents/writing.md](.guidelines/agents/writing.md) — how any prose should read
- [.guidelines/style/naming.md](.guidelines/style/naming.md) — naming
- [.guidelines/languages/cs.md](.guidelines/languages/cs.md), [rs.md](.guidelines/languages/rs.md) — C# and Rust

For CLAVE's own project context, ecosystem, quality gates, and merge
policy, read [CONTRIBUTING.md](CONTRIBUTING.md). For CLAVE-specific coding
notes on top of the shared baseline, read
[docs/guidelines.md](docs/guidelines.md).

Conflict order: direct maintainer request > CONTRIBUTING.md > `.guidelines/`
> `docs/guidelines.md` > `docs/specification.md` > modern .NET / Rust best
practices.

## Pre-push gates (mandatory)

```bash
./scripts/validate.sh
```

Do not push or update a PR until validate exits 0.

## Cursor Cloud notes

- Install toolchains with `./scripts/setup.sh` if `dotnet` or `cargo` is
  missing.
- Phase 0 has no hardware SDKs; do not add RealSense/OpenCV/ONNX/SOEM
  unless the task advances that roadmap phase.
- Do not merge PRs; owner merges manually.
