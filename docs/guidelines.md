# CLAVE coding guidelines

Authoritative **coding** conventions for CLAVE. Workflow, SDD, V-cycle, and merge
policy live in [CONTRIBUTING.md](../CONTRIBUTING.md)—do not duplicate them here.

## General

- English for identifiers, comments, and docs.
- Prefer small, unitary changes with clear intent.
- No secrets, credentials, or machine-local overrides in git.
- Phase discipline: do not pull native SDKs before the matching roadmap phase.

## C# / .NET

- Target **net8.0**; respect `Directory.Build.props` (Nullable, ImplicitUsings,
  TreatWarningsAsErrors, Deterministic).
- Prefer `Span` / `ReadOnlySpan`, `ref struct` views, and `ValueTask` on hot paths.
- Use `System.Threading.Channels` for telemetry; document full-mode behavior.
- Public APIs should be nullable-aware; avoid `null!` except at proven boundaries.
- Do not use `FrameBuffer` (ref struct) inside async methods—factor sync helpers.
- Tests: xUnit; name methods `Method_Scenario_Expected`.

## Rust

- Edition 2021; `publish = false` for `clave-core` until an intentional release.
- `#![deny(unsafe_op_in_unsafe_fn)]`.
- Prefer safe APIs; any future `unsafe` requires documented invariants and tests.
- Crate types: `cdylib` + `rlib` to prepare FFI without exposing it in Phase 0.

## Interop

- Phase 0: managed stubs only (`RingBufferHandle`).
- Phase 5+: C ABI ownership stays in Rust; P/Invoke surface stays in Clave.Interop.
- Do not scatter `DllImport` across Host/Vision/Capture.

## Documentation

- Update `docs/` when module boundaries or public contracts change.
- Keep README module map and architecture diagram in sync with the solution.
