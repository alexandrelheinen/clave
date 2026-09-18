# Agent instructions

This file is a bridge only. **Do not add rules here.**

Shared standards live in [standards/](standards/README.md), whose
[guidelines](standards/guidelines/) submodule carries method, writing,
naming, and per-language style.

Start with these:

- [workflow/sdd.md](standards/guidelines/workflow/sdd.md),
  [workflow/tdd.md](standards/guidelines/workflow/tdd.md),
  [workflow/integration.md](standards/guidelines/workflow/integration.md)
  for how work gets done
- [agents/writing.md](standards/guidelines/agents/writing.md) for how any
  prose should read
- [style/naming.md](standards/guidelines/style/naming.md) for naming
- [languages/rs.md](standards/guidelines/languages/rs.md) and
  [languages/py.md](standards/guidelines/languages/py.md) for Rust and
  Python style

For CLAVE's own context, quality gates, and merge policy, read
[CONTRIBUTING.md](CONTRIBUTING.md). For coding notes specific to CLAVE,
read [docs/guidelines.md](docs/guidelines.md).

Precedence when documents disagree is defined in
[standards/README.md](standards/README.md#precedence).

## Method

A feature gets a document under [docs/requirements/](docs/requirements/)
before it gets code. Do not assume a change is small enough to skip the
spec: the floor in
[workflow/sdd.md](standards/guidelines/workflow/sdd.md#gating-rule) is a
few written bullet points. Acceptance criterion ids are append-only and
the tests that guard them reference them by id.

## Pre-push gate (mandatory)

```bash
./scripts/validate.sh
```

Do not push or update a pull request until it exits 0. Do not describe a
gate as passing without having run it, and do not claim hardware
validation without evidence.
