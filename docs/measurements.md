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

## Workspace geometry

The manipulator's declared reach came from link geometry and was recorded as an
upper bound nobody had checked. A solved pose sweep in the grasp band, 5 to
60 mm above the belt surface, checked it.

| Quantity | Value |
| --- | --- |
| Farthest solved pose from the arm base | 0.266 m |
| Solved poses at 0.22 m lateral offset | 289, x from -0.084 to +0.108 |
| Solved poses at 0.18 m lateral offset | 408, x from -0.166 to +0.190 |
| Solved poses at 0.30 m and beyond | none |

The gripper joint runs from -0.010 m to 0.019 m with both fingers mirroring it,
which opens to **55.7 mm**. Every object in the original set was wider than that,
so none of them could be grasped. The object set is now sized to fit, at 38 to
44 mm of grasp width, which leaves roughly 10 mm of approach margin.

That constrains what the line represents, and the constraint is worth stating
plainly: these are small containers. A line sorting real household packaging
needs a gripper opening two to three times wider, and every number on this page
would move with it.

## The world

| Quantity | Value | Read by |
| --- | --- | --- |
| Belt length | 1.20 m | `configs/world/sorting_line.yml` |
| Belt width | 0.16 m | same |
| Belt speed | 0.04 to 0.10 m/s | same |
| Arm offset from belt centerline | 0.14 m | same |
| Declared reach | 0.25 m, under the 0.266 m measured | safety envelope |
| Reachable window | 0.414 m | derived from the above |
| Time budget per object | 4.14 s at the fastest belt speed | window divided by belt speed |

Reachability is a distance rather than a coordinate. `clave.world.belt.within_reach`
measures object to arm base in three dimensions, and the conveyor, the recorder
and the runtime all use it. Testing a coordinate against the window called
objects reachable off to the far side of the belt where the effector cannot go,
which made the expert and the safety layer disagree about the same geometry.

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
