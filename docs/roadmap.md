# CLAVE roadmap

Phased delivery for the CLAVE specialization lab. Phase acceptance criteria
belong in issues/PRs; this file sequences the work.

## Phase 0 — Scaffold (complete)

- Repository layout, MIT license, .gitignore
- README, CONTRIBUTING, docs stubs, thin agent bridges
- `Clave.sln` (net8.0) with Host / Vision / Capture / Bus / Interop / Cli
- xUnit tests; Rust `clave-core` with `SampleRing`
- `./scripts/validate.sh` + GitHub Actions CI
- **No** RealSense / OpenCV / ONNX / EtherCAT native dependencies

## Phase 1 — Module 1 (Host telemetry) — current

- Span / ValueTask / Channels host hardening
- GC profiling notes and drop/full-mode policies (`Wait`, `DropOldest`, `DropWrite`)
- Expand Host tests around backpressure
- See [specification.md](specification.md) (`FR-P1-*`) and [host-telemetry.md](host-telemetry.md)

## Phase 2 — Module 2 (Vision) — next

- OpenCVSharp + ONNX Runtime vision sidecar contract
- Observation shapes compatible with fret observations
- Keep native packages optional / behind feature flags when introduced

## Phase 3 — Module 3 (Capture)

- RealSense capture → point cloud path toward luthier
- Calibration documentation
- Synthetic stub remains for CI without hardware

## Phase 4 — Bus (optional hardware)

- EtherCAT / SOEM concepts in Clave.Bus
- Hardware validation remains owner-gated

## Phase 5 — Rust interop

- Stable C ABI from `clave-core`
- P/Invoke from Clave.Interop
- Agent audit checklist for unsafe boundaries

## Status legend

| Status | Meaning |
| --- | --- |
| Current | Active implementation target |
| Next | Immediately following current |
| Planned | Sequenced but not started |
| Optional | May slip or stay stubbed without hardware |
| Complete | Accepted on main |
