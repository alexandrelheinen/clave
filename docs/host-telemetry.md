# Host telemetry and GC notes (Phase 1)

Notes for low-allocation hosting with `Clave.Host`. Aligns with MAF Module 1
(Span / ValueTask / Channels). Methodology: [CONTRIBUTING.md](../CONTRIBUTING.md).

## Full-mode policies

| Mode | When channel is full | Use when |
| --- | --- | --- |
| `Wait` | Writer blocks (or `TryWrite` returns false) | Completeness matters; consumer keeps up on average |
| `DropOldest` | Oldest buffered item is discarded | Prefer freshest samples (sensor streams) |
| `DropWrite` | New item is discarded; `DroppedCount` increments on `TryWrite` | Prefer not stalling producers; measure loss |

Configure via `TelemetryChannelOptions` (see `config/telemetry.example.yml`).

## Allocation discipline

1. Prefer `ValueTask` / `ValueTask<T>` on channel read/write hot paths (already the public API).
2. Keep `FrameBuffer` (`readonly ref struct`) out of async methods — factor sync helpers (see Cli).
3. Bound every telemetry channel; never unbounded `Channel.CreateUnbounded` for host telemetry.
4. Prefer value types or pooled buffers for high-rate payloads; reference-type items allocate per write.
5. Use `Slice` / `CopyTo` / `TryCopyTo` on `FrameBuffer` instead of allocating intermediate arrays.

## Backpressure checklist

- Capacity too small + `Wait` → producer stalls; watch task queue growth.
- Capacity too small + `DropOldest` / `DropWrite` → silent loss; monitor `DroppedCount` (DropWrite) or consumer lag.
- After `Complete()`, `WaitToWriteAsync` returns false; drain remaining reads.

## GC profiling (local)

No special CLAVE tooling required. Typical workflow on a host process:

```bash
# Live counters (allocations, GC heap, pause time)
dotnet-counters monitor --process-id <pid> \
  System.Runtime[gc-heap-size,gen-0-gc-count,alloc-rate]

# Heap dump when Gen2 or LOH pressure is suspected
dotnet-gcdump collect -p <pid> -o host.gcdump
```

Interpretation tips:

- Rising `alloc-rate` with stable item size often means per-message heap objects — consider structs or ArrayPool.
- Gen0 churn under load is expected; Gen2 / LOH growth under steady state is a smell.
- Channel item lifetime should be short; holding references in consumers defeats bounded-buffer intent.

## Out of scope (later phases)

- Native vision / capture SDKs
- Cross-process telemetry buses
- Automatic GC mode switching (`Server` vs `Workstation`) — document host process settings separately when deploying
