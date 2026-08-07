# CLAVE architecture

Architecture for **CLAVE**. Phase 0 delivered stubs; Phase 1 hardens Host
telemetry. See [specification.md](specification.md) and [roadmap.md](roadmap.md).

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
 Full-mode + GC notes (Phase 1)
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
| Clave.Host | Bounded channels with full-mode policy, frame views | Interop |
| Clave.Vision | Observation records, pipeline stub | Interop |
| Clave.Capture | Synthetic capture / point clouds | Interop |
| Clave.Bus | Fieldbus master stub | — |
| Clave.Interop | Managed handles; future FFI surface | — |
| clave-core | Auditable ring buffer (Rust) | — |

## 3. Host telemetry (Phase 1)

`TelemetryChannel<T>` wraps `System.Threading.Channels` with:

- `TelemetryChannelOptions` — capacity, `TelemetryFullMode`, single-reader/writer hints
- Hot-path `ValueTask` write/read and wait APIs
- `DroppedCount` for `DropWrite` loss accounting
- `FrameBuffer` Span slices and copies without allocating the view type

Operator notes: [host-telemetry.md](host-telemetry.md). Example knobs:
`config/telemetry.example.yml`.

## 4. Design principles

1. **Low allocation on hot paths** — prefer `Span` / `ref struct` / bounded channels.
2. **Stub-first V-cycle** — public shapes and tests before native backends.
3. **Cross-language seams** — Interop owns the future C ABI boundary; Rust stays publish=false.
4. **Sibling contracts, not vendoring** — align observation/point-cloud ideas with fret/luthier later via docs and DTOs, not submodules.
5. **Fail closed on quality** — TreatWarningsAsErrors, Nullable enable, deny unsafe_op_in_unsafe_fn in Rust.
6. **Explicit backpressure** — full-mode policy is part of the public contract, not an afterthought.

## 5. Configuration

Example telemetry knobs live in `config/telemetry.example.yml`. Local overrides
(`config/telemetry.yml`) are gitignored. Phase 1 constructs options in code;
a YAML loader is not required.

## 6. Future seams

| Seam | Direction |
| --- | --- |
| Vision ↔ fret | Observation DTO compatibility |
| Capture ↔ luthier | Point cloud / calibration documentation |
| Host ↔ bossa | Telemetry channel semantics (concepts only) |
| Interop ↔ Rust | `cdylib` C ABI + P/Invoke |
