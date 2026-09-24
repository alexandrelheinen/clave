# Debug-run hot path

## Intent

Cut wall time on headless debug simulations without changing control
behaviour. The post-IK profile still spent seconds on jaw-mesh clearance,
quintic peak sampling, and offscreen RGB renders that a `--no-window` run
without video does not need.

## Scope

**In.** Jaw clearance measurement cost; `Segment.peaks` / `sample` arithmetic;
skipping the watching-camera RGB path when no live window, no video, and no
frame dump was asked for.

**Out.** Changing `segment_sample_count` or `bisection_passes` defaults.
Bypassing segmentation under ground-truth feeding (`AC-GT` concurrent tracker
rule). Moving IK into Rust.

## Acceptance criteria

Ids begin at `AC-PERF-01`. Append-only.

`AC-PERF-01`: When the debug run has no live window, no video, and frame
dumps are off, it shall not construct the watching RGB renderer, shall not
call its `render`, and shall write zero PNG frames. Segmentation and the
physics loop still run.

`AC-PERF-02`: When `--no-window` is set and `--video` is not, frame dumps
default to off. `--frames` forces PNG captures in that mode. `--video` still
renders on its own cadence.

`AC-PERF-03`: Jaw clearance for mesh collision geoms shall use each geom's
local AABB (`geom_size` half-extents) under the same support formula as a
box, which never overstates clearance relative to the true mesh. Box,
sphere, cylinder, and capsule geoms stay exact.

`AC-PERF-04`: `Segment.peaks` shall agree with sampling the open unit grid
through the same Hermite basis as before (within floating-point noise), and
shall not allocate a fresh linspace or basis stack on every call for a fixed
sample count.

## Test plan

| Criterion | Test |
| --- | --- |
| `AC-PERF-01` | `test_headless_without_frames_skips_rgb_render` |
| `AC-PERF-02` | `test_no_window_defaults_frames_off_unless_forced` |
| `AC-PERF-03` | `test_mesh_jaw_clearance_uses_aabb_not_vertices`, existing `AC-MOVE-53` jaw tests |
| `AC-PERF-04` | `test_peaks_match_sampled_polynomial_on_cached_grid` |
