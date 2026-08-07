# CLAVE architecture

Phase 0 architecture for **CLAVE** — stubs that compile and test. See
[specification.md](specification.md) and [roadmap.md](roadmap.md).

## 1. System view

```text
┌─────────────┐
│  Clave.Cli  │  smoke / future operator entry
└──────┬──────┘
       │
       ├──────────────┬──────────────┬──────────────┐
       ▼              ▼              ▼              ▼
 Clave.Host     Clave.Vision   Clave.Capture   Clave.Bus
 Telemetry        Observation    PointCloud     EtherCAT
 FrameBuffer      pipeline stub  stub           stub
       │              │              │
       └──────────────┴──────────────┘
                      ▼
               Clave.Interop
            RingBufferHandle (managed)
                      ⋮ Phase 5
               rust/clave-core
                  SampleRing
```

## 2. Module responsibilities

| Project | Responsibility | Depends on |
| --- | --- | --- |
| Clave.Cli | Console identity + exercises stubs | Host, Vision, Capture, Bus, Interop |
| Clave.Host | Bounded channels, frame views | Interop |
| Clave.Vision | Observation records, pipeline stub | Interop |
| Clave.Capture | Synthetic capture / point clouds | Interop |
| Clave.Bus | Fieldbus master stub | — |
| Clave.Interop | Managed handles; future FFI surface | — |
| clave-core | Auditable ring buffer (Rust) | — |

## 3. Design principles

1. **Low allocation on hot paths** — prefer `Span` / `ref struct` / bounded channels.
2. **Stub-first V-cycle** — public shapes and tests before native backends.
3. **Cross-language seams** — Interop owns the future C ABI boundary; Rust stays publish=false.
4. **Sibling contracts, not vendoring** — align observation/point-cloud ideas with fret/luthier later via docs and DTOs, not submodules.
5. **Fail closed on quality** — TreatWarningsAsErrors, Nullable enable, deny unsafe_op_in_unsafe_fn in Rust.

## 4. Configuration

Example telemetry knobs live in `config/telemetry.example.yml`. Local overrides
(`config/telemetry.yml`) are gitignored.

## 5. Future seams (not Phase 0)

| Seam | Direction |
| --- | --- |
| Vision ↔ fret | Observation DTO compatibility |
| Capture ↔ luthier | Point cloud / calibration documentation |
| Host ↔ bossa | Telemetry channel semantics (concepts only) |
| Interop ↔ Rust | `cdylib` C ABI + P/Invoke |
