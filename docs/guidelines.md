# CLAVE-specific coding notes

The shared baseline for C#/.NET and Rust style, naming, and error handling
lives in [.guidelines/languages/cs.md](../.guidelines/languages/cs.md) and
[.guidelines/languages/rs.md](../.guidelines/languages/rs.md). This file
covers only what is specific to CLAVE. Workflow, SDD, V-cycle, and merge
policy live in [CONTRIBUTING.md](../CONTRIBUTING.md).

## General

- Phase discipline: do not pull native SDKs before the matching roadmap
  phase.

## C# / .NET

- Prefer `Span` / `ReadOnlySpan`, `ref struct` views, and `ValueTask` on
  hot paths.
- Use `System.Threading.Channels` for telemetry; choose an explicit
  `TelemetryFullMode` (`Wait` / `DropOldest` / `DropWrite`). See
  [host-telemetry.md](host-telemetry.md).
- Do not use `FrameBuffer` (ref struct) inside async methods; factor sync
  helpers instead.

## Rust

- `publish = false` for `clave-core` until an intentional release.
- Crate types: `cdylib` + `rlib`, to prepare FFI without exposing it in
  Phase 0.

## Interop

- Phase 0: managed stubs only (`RingBufferHandle`).
- Phase 5+: C ABI ownership stays in Rust; the P/Invoke surface stays in
  `Clave.Interop`.
- Do not scatter `DllImport` across Host/Vision/Capture.

## Documentation

- Update `docs/` when module boundaries or public contracts change.
- Keep the README module map and architecture diagram in sync with the
  solution.
