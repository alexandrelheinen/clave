# The world was not sized for the arm it contains

> Roadmap step: v1.0.1, a patch to the world of v0.5.0 · Spec:
> [.kiro/specs/sorting-world/](../../.kiro/specs/sorting-world/)

Watching the v1.0.0 demonstration is what exposed this. The objects on the belt
are visibly too large for the manipulator reaching over them, and they travel
faster than it moves. Both observations turned out to be measurable, and both
were true.

Everything below comes from measuring the pinned ROBOTIS OpenMANIPULATOR-X and
the committed world. No number here is quoted from a datasheet.

## The gripper opens 55.7 mm and every object was wider

The gripper joint runs from -0.010 m to 0.019 m, and both fingers mirror it.
Projecting the finger mesh vertices onto the opening axis gives the clear gap
between the facing surfaces:

| Gripper joint | Clear opening |
| --- | --- |
| -0.010 m, closed | -2.3 mm, the pads meet |
| +0.019 m, open | **55.7 mm** |

Against the object set v0.5.0 shipped, where a cylinder is grasped across its
diameter and a box across its width:

| Object | Grasp width before | Fits a 55.7 mm gripper |
| --- | --- | --- |
| `drink_bottle` | 60 to 76 mm | No |
| `milk_jug` | 90 to 116 mm | No |
| `yogurt_tub` | 70 to 96 mm | No |
| `drink_can` | 62 to 68 mm | No |
| `food_can` | 72 to 88 mm | No |
| `glass_bottle` | 64 to 80 mm | No |
| `shipping_box` | 140 to 220 mm | No |
| `beverage_carton` | 66 to 84 mm | No |

**Not one of the eight fit.** The world spawned objects the manipulator could
never have closed on, and every rollout recorded from it described a task the
arm was unable to perform.

The object set is now sized under a declared bound, `arm.max_grasp_width_meters`
at 45 mm, which leaves about 10 mm of approach margin under the measured
opening. `clave.world.objects` refuses to build a world whose objects exceed it,
because the sizes are randomized and a reviewer reads the range rather than the
draw.

The cost is honest and worth stating: these are the small containers a 56 mm
gripper can hold, not the two litre bottles a recovery facility sees. A realistic
object set needs a larger gripper, which is a different arm rather than a
different number in a file.

## The belt outran the arm by up to fifteen times

Driving the effector toward points on the belt with the controller v0.5.1
shipped, and timing how far it travels:

| Target | Distance from base | Result |
| --- | --- | --- |
| (+0.12, -0.15) | 0.226 m | Reached, 0.132 m in 1.30 s, **0.102 m/s** |
| (+0.00, -0.15) | 0.191 m | 0.038 m short after 6 s |
| (+0.12, -0.05) | 0.314 m | 0.106 m short after 6 s |
| (+0.00, +0.00) | 0.341 m | 0.107 m short after 6 s, effectively motionless |

The belt ran at 0.10 to 0.30 m/s. Even at its slowest it matched the effector's
best case, and at its fastest it was three times quicker than the one target the
arm actually converged on. The belt now runs at 0.04 to 0.10 m/s, at or below
the speed the arm can cover ground.

## The centerline of the belt was unreachable

The pattern above is not the controller failing. Sweeping the four arm joints on
a 17 point grid, 83,521 combinations, and keeping the effector poses that land
in the grasp band from 5 to 60 mm above the belt surface:

| Property | Measured |
| --- | --- |
| Poses in the grasp band | 10,693 |
| Farthest from the arm base | **0.266 m** |
| At 0.34 m laterally, the old belt centerline | **unreachable** |
| At 0.30 m laterally | unreachable |
| At 0.22 m laterally | 289 poses, x from -0.084 to +0.108 |
| At 0.18 m laterally | 408 poses, x from -0.166 to +0.190 |

The arm sat 0.34 m from the belt centerline with a declared reach of 0.38 m.
That 0.38 m came from link geometry, and [v0.5.0](sorting-world.md) recorded it
as an upper bound that nobody had checked. Checked, it is 0.266 m in the band
where a grasp happens, so **the manipulator could not reach the middle of its
own belt**.

That single fact explains the override rate v1.0.0 reported: 65 percent of what
the recommended configuration proposed, and 47 percent of what the scripted
expert proposed, lay outside the workspace. The safety layer was not being
strict. It was refusing picks that were geometrically impossible.

The arm now sits 0.14 m from the centerline of a 0.16 m belt, so the far edge is
0.22 m away, inside the 289 pose band. The declared reach is 0.25 m, under the
0.266 m measured.

## Reachability is now a distance, not a coordinate

An object was called reachable when its coordinate along belt travel fell inside
the window, which is the chord the reachable sphere cuts through the centerline.
An object is rarely on the centerline, so that test called objects reachable at
the window's edge and off to the far side, where the effector cannot go.

`clave.world.belt.within_reach` now measures the distance from the object to the
arm base in three dimensions, and the conveyor, the recorder and the runtime all
use it. The effect on one 20 second run with the scripted expert:

| | Before | After |
| --- | --- | --- |
| Proposals | 30 | 30 |
| Overridden on reach | 7 | **0** |
| Published | 23 | 30 |

The expert and the safety layer now agree, which they should: they were reading
the same geometry through two different tests and only one of them was right.

## What the rescaled world looks like

| Quantity | v1.0.0 | v1.0.1 |
| --- | --- | --- |
| Belt length | 2.00 m | 1.20 m |
| Belt width | 0.50 m | 0.16 m |
| Belt speed | 0.10 to 0.30 m/s | 0.04 to 0.10 m/s |
| Arm offset from centerline | 0.34 m | 0.14 m |
| Declared reach | 0.38 m | 0.25 m |
| Reachable window | 0.339 m | 0.414 m |
| Time budget per object | 1.13 s at the fastest belt | 4.14 s at the fastest belt |
| Object grasp width | 60 to 220 mm | 38 to 44 mm |
| Objects entering reach, 20 s at seed 0 | 4 of 12 | 11 of 12 |

## What it changed downstream

**Every measurement taken before this describes a different world.** The dataset
was re-recorded, all three candidates retrained, and the benchmark rerun. The
numbers in [benchmark.md](benchmark.md) are from the rescaled world; the ones in
this document's tables marked "before" are from the old one and are kept only
for the comparison.

**The latency gates are now far more conservative than the budget requires.**
`max_decision_latency_p99_seconds` is 0.45 s, derived when the budget was
1.13 s. The budget is now 4.14 s at the fastest belt speed. The gate is left
where it is: a tighter gate than the physics demands costs nothing, and moving
it would be a decision rather than an edit.

**A slow belt moved the bottleneck.** With the belt at 0.078 m/s an object stays
within reach for 5.3 seconds, so objects accumulate: a measured mean of 2.67
objects inside the workspace per captured frame, peaking at 6. The scripted
expert emits one decision per frame, so it now covers 123 of 227 presented
objects where it used to cover 231 of 249. Its accuracy fell from 92.8 percent
to 54.2 percent, and every point of that fall is coverage rather than
misclassification: it is still right about every object it decides.

That is a real property of the rescaled line rather than a regression. A faster
belt hid it by keeping at most one object in reach at a time. What it says is
that the next bottleneck is decision rate, not decision latency, and a decider
that handles one object per frame is the thing to fix.

## What this does not fix

**The controller still does not converge on every reachable target.** The sweep
shows the poses exist; the damped least squares controller reaches some of them
and stalls short of others. That is a controller problem, and v0.5.1 declined to
build a pick state machine here on purpose, because FRET already owns one.

**Nothing grasps.** A gripper that now fits the objects has still never closed
on one.

**The object set is a scale model.** Sizing objects to a 56 mm gripper produces
a set of small containers. A line that sorts real household packaging needs a
gripper that opens two to three times wider, and every number here would move
with it.
