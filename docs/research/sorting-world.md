# The sorting world, and what it decides

> Roadmap step: v0.5.0 · Spec: [.kiro/specs/sorting-world/](../../.kiro/specs/sorting-world/)

[v0.4.0](model-candidates.md) measured every candidate's latency and could not
say whether any of them was fast enough, because no belt speed, field of view or
effector reach had ever been fixed. Calling Faster R-CNN "marginal" was a
judgment, not a verdict.

This world fixes those numbers. It is a MuJoCo conveyor carrying class-tagged
objects past a ROBOTIS OpenMANIPULATOR-X, with one bin per channel, and it
produces the one quantity every latency has to fit inside: the time an object
spends within the arm's reach.

## The geometry

| Quantity | Value |
| --- | --- |
| Belt length | 2.00 m |
| Belt width | 0.50 m |
| Belt surface height | 0.35 m |
| Arm offset from belt centerline | 0.34 m |
| Reachable radius | 0.38 m |
| **Reachable window** | **0.339 m** |
| Belt speed range | 0.10 to 0.30 m/s |
| Channels | 7 bins, with `CH-FIBER` shared by `M-08` and `M-10` |
| Material classes represented | 8 of the taxonomy's 11 |

The window is the chord the reachable sphere cuts through the belt centerline.
Everything upstream of a pick has to complete inside it.

## The time budget

Window divided by belt speed:

| Belt speed | Time budget per object |
| --- | --- |
| 0.10 m/s | 3.39 s |
| 0.20 m/s | 1.70 s |
| 0.30 m/s | 1.13 s |

**1.13 seconds is the number that matters**, because it is what the world
produces at the fastest belt speed the configuration allows.

## The verdict on v0.4.0

Perception latency as a fraction of the tightest budget:

| Candidate | Measured | Share of 1.13 s | Verdict |
| --- | --- | --- | --- |
| resnet50-baseline | 29.0 ms | 2.6 percent | Fits, but cannot localize |
| act | 31.6 ms | 2.8 percent | Fits |
| faster-rcnn-mobilenetv3 | 391.7 ms | 34.6 percent | **Fits**, leaving 0.74 s to plan and execute a pick |
| sam2 | 1229.2 ms | 108.8 percent | **Fails.** Exceeds the entire budget before the arm has moved |
| diffusion-policy | 15479.1 ms | 1370 percent | **Fails** by more than an order of magnitude |

Three things follow.

**Faster R-CNN is viable, not merely marginal.** v0.4.0 could not say this. At
0.30 m/s it consumes about a third of the budget and leaves roughly 0.74 seconds
for planning and motion, which is a real margin rather than a hopeful one. At
slower belt speeds it is comfortable.

**SAM 2's rejection is now arithmetic rather than judgment.** Its encoder alone
exceeds the whole budget at the fastest belt speed and leaves 0.07 seconds at
0.20 m/s. There is no belt speed in the configured range at which SAM 2 leaves
usable time, since even at 0.10 m/s it consumes 36 percent before the mask
decoder runs.

**Diffusion Policy is not close.** At 15.5 seconds per action it is slower than
the object's entire transit of the two-meter belt, at any configured speed.

## What the world does

Objects are free bodies. While one rests on the belt its travel velocity is
driven to the belt speed; vertical motion, rotation and contact stay with
physics, so collisions with bins and the arm remain real. This is a driven
constraint rather than a friction model, which means objects do not slip. A real
line has slip, and this world does not reproduce it.

An object that passes the window unpicked is left alone and continues to the end
of the belt. A real line does not stop, so a missed pick is a throughput loss
rather than a fault, and v0.8.0 should count the two separately.

Every object carries its material class at spawn, so a rollout recorded here is
labeled by construction rather than by a labeling pass afterwards.

## Reproducibility

Verified across five seeds, running 25 simulated seconds each:

| Seed | Belt speed | Budget | Spawned | Entered window | Unstable |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.227 m/s | 1.493 s | 12 | 8 | No |
| 1 | 0.202 m/s | 1.677 s | 12 | 5 | No |
| 3 | 0.117 m/s | 2.898 s | 12 | 6 | No |
| 7 | 0.225 m/s | 1.508 s | 12 | 5 | No |
| 11 | 0.126 m/s | 2.700 s | 12 | 5 | No |

Every tunable is a configuration key. Nothing in the world package carries a
numeric default, and a missing key fails at load naming itself.

## One bug worth recording

The first stable-looking build was not stable. Pooled objects waiting to be
spawned were parked below the floor, and a MuJoCo plane collides from above
only, so they fell forever, gained unbounded velocity, and drove the solver to a
NaN at about 2.9 simulated seconds. It surfaced as a suspiciously low spawn
count at one seed rather than as an error.

Parked slots are now pinned each step with zero velocity. `AC-SCENE-03` exists
for this class of defect, and it caught it.

## Limitations

**Objects are parametric primitives, not scanned meshes.** Mass, footprint and
grasp width are represented; appearance is not. A perception model trained only
on these frames would learn shape and not material, which makes synthetic frames
from this world useful for the pick policy and weak for the classifier.
Integrating a scanned object set is the obvious next refinement.

**The reachable radius is derived from link geometry, not from a solved
workspace.** It is an upper bound: some poses inside 0.38 m are not achievable
given joint limits, so the real window is at most this wide and possibly
narrower. A narrower window shortens the budget and tightens every verdict
above.

**No arm motion was executed.** The budget says how long there is; it does not
show that the manipulator can complete a pick in that time. That is v0.7.0's
problem, and if it cannot, the budget arithmetic here becomes optimistic.
