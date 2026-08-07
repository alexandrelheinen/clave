# CLAVE specification (Phase 0)

This document is the project-level functional specification for **CLAVE**
(**C**ross-**L**anguage **A**rchitecture for **V**ision & **E**dge). Feature-level
specs live in issues and PR descriptions. Methodology: [CONTRIBUTING.md](../CONTRIBUTING.md).

## 1. Intent

Provide a private specialization lab for high-reliability perception and
interop: low-allocation C# hosts, vision/ONNX pipelines (later), 3D
capture/calibration concepts, EtherCAT bus concepts, and auditable Rust hot
paths. CLAVE is the clef for reading the industrial stack that complements
arco / fret / luthier / bossa.

## 2. Phase 0 scope

**In scope**

- Repository scaffolding: solution, Rust crate, docs, scripts, CI
- Compile-and-test stubs with zero native hardware/SDK dependencies
- Agent bridges pointing at CONTRIBUTING
- Local `./scripts/validate.sh` matching CI

**Out of scope**

- RealSense, OpenCVSharp, ONNX Runtime, TorchSharp, SOEM/EtherCAT hardware
- Git submodules of sibling repos
- Harvest-robot product features
- Logo / branding assets beyond textual identity

## 3. Functional requirements (Phase 0)

| ID | Requirement | Verification |
| --- | --- | --- |
| FR-P0-01 | Solution builds on net8.0 with Nullable and TreatWarningsAsErrors | `dotnet build Clave.sln` |
| FR-P0-02 | Host telemetry channel supports bounded write/read | Host.Tests |
| FR-P0-03 | FrameBuffer exposes length over `ReadOnlySpan<byte>` | Host.Tests |
| FR-P0-04 | Vision stub emits synthetic Observation | Cli smoke |
| FR-P0-05 | Capture stub emits synthetic point cloud | Cli smoke |
| FR-P0-06 | Bus stub configures/starts/stops without hardware | Cli smoke |
| FR-P0-07 | Interop RingBufferHandle validates capacity | Interop.Tests |
| FR-P0-08 | Rust SampleRing overwrites when full | `cargo test` |
| FR-P0-09 | validate.sh and CI run both language gates | `./scripts/validate.sh` |

## 4. MAF module mapping

| MAF focus | CLAVE home | Phase |
| --- | --- | --- |
| .NET memory + async (Span, ValueTask, Channels) | Clave.Host | 0 stub → 1 |
| Vision / ONNX in .NET | Clave.Vision | 0 stub → 2 |
| RealSense / calib / point clouds | Clave.Capture (+ docs) | 0 stub → 3 |
| EtherCAT concepts | Clave.Bus | 0 stub → 4 |
| Rust auditability + FFI | rust/clave-core + Clave.Interop | 0 stub → 5 |

## 5. Non-functional constraints

- MIT license; Copyright (c) 2026 Alexandre Loeblein Heinen
- English documentation
- No secrets in repository
- Deterministic builds (`Directory.Build.props`)
- Rebase-friendly history; owner merges manually
