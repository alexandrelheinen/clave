# Measurements

Every number in this repository that a configuration value, a gate or a design
decision rests on, with how it was obtained and what reads it.

A figure here describes simulation on one development machine. None of it
describes hardware, and none of it describes real world accuracy.
[architecture.md](architecture.md) describes the system these numbers come from.

## The development machine

Every latency figure below was taken here, so a figure moves if the machine
does.

| Condition | Value |
| --- | --- |
| CPU | AMD Ryzen 7 7735U, 8 cores and 16 threads |
| Accelerator | None. Integrated AMD Radeon 680M, no CUDA runtime, no ROCm path |
| Memory | 7 GiB available to WSL |
| Method | 2 untimed warm-up iterations discarded, then 5 timed runs, median reported with the full spread |
| Input | One synthetic 3x96x96 frame and a 6-dimensional state, generated from a fixed seed |

## Candidate forward pass cost

| Candidate | Stage | Parameters | Median latency | Spread |
| --- | --- | --- | --- | --- |
| `resnet50-baseline` | Perception | 23.53 M | 29.0 ms | 6.1 ms |
| `faster-rcnn-mobilenetv3` | Perception | 18.98 M | 391.7 ms | 28.1 ms |
| `sam2` | Perception | 38.96 M | 1229.2 ms | 41.5 ms |
| `behavior-cloning-baseline` | Policy | 0.02 M | 0.4 ms | 0.1 ms |
| `act` | Policy | 51.60 M | 31.6 ms | 5.1 ms |
| `ppo-mlp` | Policy | 0.01 M | 0.2 ms | 0.0 ms |
| `diffusion-policy` | Policy | 262.95 M | 15479.1 ms | 295.5 ms |

Two candidates are ruled out by cost alone on this machine. `sam2` exceeds the
per-object budget before the arm has moved, and `diffusion-policy` exceeds it by
more than three orders of magnitude. Both remain in the registry, because a
machine with an accelerator would measure them differently and the registry
records what was screened rather than what survived.

## The manipulator

A SCARA in the geometry of an ABB IRB 910SC-3/0.65. Every figure below is from
ABB's published product specification, not from this project, which is what
makes the model checkable against something outside it.

| Quantity | Value |
| --- | --- |
| Arm 1, shoulder to elbow | 0.400 m on the 0.65 variant; 0.200 and 0.300 on the others |
| Arm 2, elbow to spline | 0.250 m on all three variants |
| Axis 1, shoulder rotation | plus or minus 140 degrees, 415 deg/s |
| Axis 2, elbow rotation | plus or minus 150 degrees, 659 deg/s |
| Axis 3, spline travel | 0.180 m, 1.02 m/s, 250 N down force |
| Axis 4, spline rotation | plus or minus 400 degrees, 2400 deg/s |
| Payload | 3 kg rated, 6 kg maximum |
| 1 kg picking cycle | 0.385 s |
| Repeatability | 0.015 mm on axes 1 and 2 |
| Base footprint | 160 by 160 mm |

Two of those decide the shape of the workspace. The link lengths set an outer
radius of 0.650 m, and the 150 degree stop on axis 2 folds the tool no closer
than **0.222 m** to the shoulder, which is the dead zone. The 140 degree stop on
axis 1 removes a wedge behind the arm.

That wedge is not a detail. Ignoring it and treating the workspace as a plain
annulus overstates the pick window on the belt centerline by a factor of two,
which a sweep caught and the closed-form chord did not.

## Workspace, as swept

Reachability measured through the same test the safety layer applies, at
0.30 m/s.

| Lateral position | Travel inside the workspace | Pick time |
| --- | --- | --- |
| centerline | 0.428 m | 1.43 s |
| 0.10 m out | 0.746 m | 2.49 s |
| 0.20 m out | 0.974 m | 3.25 s |
| 0.30 m out | 1.130 m | 3.77 s |
| 0.40 m out | 1.024 m | 3.41 s |
| 0.50 m out, belt edge | 0.830 m | 2.77 s |

Every one of 51 lateral samples across the 1.00 m belt is reachable somewhere in
its travel, so the belt is covered end to end. The centerline is the worst case
for pick time rather than the best, because the dead zone sits directly under
the arm and an object crossing the centerline spends part of its travel inside
it.

## The world

| Quantity | Value | Read by |
| --- | --- | --- |
| Belt length | 3.00 m | `configs/world/sorting_line.yml` |
| Belt width | 1.00 m | same |
| Belt surface height | 0.90 m | same |
| Belt speed | 0.25 to 0.35 m/s | same |
| Arm mounting face | 1.659 m, over the belt centerline | same |
| Shoulder | 0.251 m below the mounting face, at 1.408 m | derived |
| Tool travel | belt surface plus 0.030 m to plus 0.210 m | the 0.180 m stroke, positioned |

The tool reaches an object top 0.030 m above the belt fully extended and clears
one 0.210 m tall fully retracted. An object taller than 0.210 m is struck by the
retracted tool, which is a real consequence of a 0.180 m stroke rather than a
modeling shortcut.

## Sensing

| Sensor | Role | Field across the belt | Resolution |
| --- | --- | --- | --- |
| `gate_wide` | detection | 1.252 m | 0.652 mm per pixel |
| three code cameras | code | 0.342 m each | 0.178 mm per pixel |

An EAN-13 narrow module is about 0.33 mm and decoding wants roughly two pixels
across it, so 0.165 mm per pixel is the floor. The wide camera is four times
coarser and cannot decode a barcode at all; the narrow cameras reach 1.9 pixels
per module, which is marginal by design.

## Validation gates

The two timing gates are derived rather than chosen. The rest are targets set
before the first run, which is the point: a threshold written after seeing a
result describes that result instead of gating it.

| Gate | Value | Basis |
| --- | --- | --- |
| `max_decision_latency_p99_seconds` | 0.45 | Derived when the per-object budget was 1.13 s and the only viable localizing perception candidate measured 391.7 ms. See the note below |
| `max_cycle_time_p99_seconds` | 1.13 | The per-object budget under the earlier geometry. See the note below |
| `min_overall_accuracy` | 0.80 | Target |
| `min_per_class_accuracy` | 0.60 | Target, set below the aggregate because a rare class carries fewer records |
| `min_class_support` | 30 | At thirty records one error moves the figure by 3.3 points, the coarsest resolution worth calling a measurement |
| `min_pick_success_rate` | 0.90 | Target |
| `max_misroute_rate` | 0.05 | Target, tighter than the pick gate because a misroute contaminates a bale while a missed pick only costs a pick |
| `max_named_confusion_rate` | 0.35 | Target, looser on purpose: these separations are unavailable from a color image |
| `max_unseen_accuracy_drop` | 0.10 | Target |

**Both timing gates are now more conservative than the physics requires.** They
were derived when the budget was 1.13 s; the budget is 4.14 s at the fastest
belt speed the configuration allows. They are left where they are, because a
tighter gate than the physics demands costs nothing and moving one is a decision
with an entry in [decisions.md](decisions.md) rather than an edit.

## End to end benchmark

One run per configuration, same seed, same world.

| Configuration | Presented | Decided | Accuracy | Decision p99 | Overridden |
| --- | --- | --- | --- | --- | --- |
| `scripted-expert` | 69 | 39 | 56.5% | 0.8 ms | 84 of 282 |
| `resnet50 + behavior-cloning` | 69 | 36 | 23.2% | 124.5 ms | 120 of 298 |
| `resnet50 + act` | 69 | 0 | 0.0% | unmeasured | 0 of 0 |

The loop costs 0.9 ms with inference removed, so the difference between the
first two rows is the cost of inference alone.

Read the expert's 56.5 percent carefully, because it is a coverage figure rather
than an accuracy one. It decided about 57 percent of the objects presented and
was right about every one of them. The missing share is objects that left the
window before it got to them, which happens because it emits one decision per
frame while a mean of 2.67 objects sit inside the workspace at a time, peaking
at 6. A slow belt keeps objects in reach for about 5.3 seconds, so they
accumulate.

That says the next bottleneck is decision rate rather than decision latency, and
a decider handling one object per frame is the thing to fix.

### What the benchmark cannot measure

| Metric | Why |
| --- | --- |
| Pick success rate | Nothing grasps, so every record carries `picked = False` and the rate would be zero by construction |
| Cycle time | There is no placement to measure to, for the same reason |
| Generalization drop | The benchmark runs the world the models trained on, so the unseen partition is empty |

### What the safety layer did

| Configuration | Proposals | Overridden | Share |
| --- | --- | --- | --- |
| `scripted-expert` | 282 | 84 | 29.8% |
| `resnet50 + behavior-cloning` | 298 | 120 | 40.3% |

A control that reads reachability the same way the safety layer does is
overridden 2.2 percent of the time. The gap between that and 29.8 percent is the
expert proposing picks against a slightly different reading of the same
geometry, not the layer being strict.

## Training signal

The trained models saw 240 frames. That supports a claim about cost and about
whether the mechanism runs. It supports no claim about accuracy, and none is
made anywhere in this repository.
