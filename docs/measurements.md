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

A Universal Robots UR10e, from MuJoCo Menagerie at commit `8161bba2`. Published
figures come from Universal Robots; swept figures were measured against the
compiled model in this repository.

| Quantity | Value | Source |
| --- | --- | --- |
| Axes | 6, all revolute | model |
| Reach | 1.308 m, measured by sampling joint space | swept |
| Payload | 12.5 kg | published |
| Mass | 32.7 kg | model |
| Axis 1 range | plus or minus 360 degrees | model |
| Visual meshes | 20, from manufacturer CAD via the ROS-Industrial description | upstream |

### Workspace, as swept

A six-axis arm under an orientation constraint has no closed-form workspace, so
this was measured rather than derived. Inverse kinematics was solved with the
tool axis held vertical, from a base 0.70 m off the belt centreline, at an
object top 0.05 m above the arm's mounting face.

| Lateral position on the belt | Reachable span along the belt | Radius from base |
| --- | --- | --- |
| -0.500 m | -1.25 to +1.15 m | 0.200 to 1.266 m |
| -0.250 m | -1.20 to +1.20 m | 0.450 to 1.282 m |
| 0.000 m | -1.10 to +1.10 m | 0.700 to 1.304 m |
| +0.250 m | -0.90 to +0.90 m | 0.950 to 1.309 m |
| +0.500 m | -0.50 to +0.50 m | 1.200 to 1.300 m |

Focused sweeps put the inner limit between 0.175 m, unreachable, and 0.200 m,
reachable, and found solutions from the base plane to 0.55 m above it.

The region the system trusts sits strictly inside all of that:

| Bound | Trusted | Measured |
| --- | --- | --- |
| Inner radius | 0.25 m | 0.200 m |
| Outer radius | 1.25 m | 1.266 m at worst bearing |
| Vertical band about the base | -0.05 m to +0.45 m | past both ends |

Under-permitting is the point. A checker that admits a point the arm cannot
reach is how a proposer and a checker come to disagree, which cost this project
a 47 percent override rate on an earlier arm.

### Where it can stand

Belt coverage with the tool held vertical, by pedestal offset from the centreline.

| Offset | UR10e | UR5e |
| --- | --- | --- |
| 0.60 m | full 1.00 m belt | misses the far edge |
| 0.70 m | full 1.00 m belt | misses the far edge |
| 0.75 m | full 1.00 m belt | misses the far edge |
| 0.85 m | misses the far edge | misses the far edge |

Mounted inverted on a gantry above the belt, the UR10e reached 3 of 27 sample
points: a six-axis arm pointing straight down while extended is near-singular.
That is why this arm stands beside the line where the previous one hung over it.

### Cycle time

| Machine class | Published pick-and-place cycle |
| --- | --- |
| Delta | near 0.3 s, above 120 cycles per minute |
| SCARA | 0.28 to 0.50 s at its sweet spot |
| Six-axis industrial | 0.4 to 0.8 s |
| Collaborative, including the UR10e | behind all three, limited by the safety envelope |

CLAVE's budget is **1.0 second**, enforced by
`max_cycle_time_p99_seconds`. It is unmeasured rather than met: nothing grasps,
so there is no placement to measure to.

## The world

| Quantity | Value | Read by |
| --- | --- | --- |
| Belt length | 3.00 m | `configs/world/sorting_line.yml` |
| Belt width | 1.00 m | same |
| Belt surface height | 0.90 m | same |
| Belt speed | 0.25 to 0.35 m/s | same |
| Arm base, the pedestal top | 0.90 m, 0.70 m off the belt centerline | same |
| Pedestal footprint | 0.30 by 0.30 m, floor to 0.90 m | same |
| Tool band | base minus 0.05 m to base plus 0.45 m | swept, see above |
| Reachable window | 2.071 m of centerline, from -1.034 m to +1.034 m | swept, see below |

The pedestal's half-diagonal is 0.212 m, inside the 0.25 m inner radius, so the
arm cannot drive into the support carrying it.

The window is swept at 2 mm along the belt centerline through the same
reachability test the safety layer applies, over the belt's full extent rather
than from the origin: the belt is centered on the origin, so a sweep that starts
there measures the downstream half and reports 1.036 m for a window that is
twice that. At the configured belt speeds the window is 5.92 s of travel at
0.35 m/s and 8.28 s at 0.25 m/s, and 6.60 s at the 0.31 m/s a fixed seed draws.

## Sensing

| Sensor | Role | Parts | Across the belt | Along travel | Resolution |
| --- | --- | --- | --- | --- | --- |
| `gate_wide` | detection | IMX264 + 8 mm, 1.042 m standoff | 1.100 m | 0.920 m | 0.449 mm per pixel |
| three code cameras | code | IMX264 + 16 mm, 0.730 m standoff | 0.385 m each | 0.322 m each | 0.157 mm per pixel |

Every camera names the parts it is built from and the angle is derived, so no
field of view in this project can drift from hardware somebody could order. The
sensor is a Sony IMX264, 2/3 inch, 2448 by 2048 at a 3.45 micrometre pitch, so
an active area of 8.446 by 7.066 mm. The lenses are Fujinon HF-XA-5M, C-mount,
specified for a 2/3 inch sensor at that exact pitch. The resolutions above
assume a render at the sensor's own 2448 pixels; a coarser render spreads the
same field over fewer pixels and resolves proportionally less.

The long sensor axis lies **across** the belt. `fovy` is a vertical field of
view, so it sets the image height axis, and for a nadir camera that axis is the
across-belt one. Laying the long side along travel spends it on a direction the
object crosses anyway and leaves the short side to cover the width, which is
what the line did before these figures were measured.

| Coverage of the 1.00 m belt width | Swept |
| --- | --- |
| `gate_wide` | 1.000 m, 100 percent |
| the three code cameras together | 100 percent, overlapping between 0.13 m and 0.20 m each side |

Swept rather than trusted to the arithmetic. One object is stepped laterally at
10 mm and the segmentation render is read at each position. `gate_wide` returns
pixels across the whole width. The code cameras return them over -0.500 m to
-0.130 m, -0.200 m to +0.200 m and +0.130 m to +0.500 m, so they overlap rather
than butt together and the belt is tiled rather than sampled.

An EAN-13 narrow module is about 0.33 mm and decoding wants roughly two pixels
across it, so 0.165 mm per pixel is the floor. The wide camera is nearly three
times coarser and cannot decode a barcode at all; the code cameras reach
0.157 mm per pixel, which clears the floor rather than sitting on it.

The offscreen framebuffer is sized from the declared sensors. MuJoCo defaults it
to 640 by 480 and this project raised it to 1920 by 1080, which silently capped
a 2448 pixel sensor. A camera that cannot be rendered at its own resolution has
a resolution that means nothing.

Measured decode yield, over five seeds at the sensor's native resolution:

| Denominator | Decodes | Yield |
| --- | --- | --- |
| Objects crossing the gate | 2 of 45 | 4.4 percent |
| Objects inside a code camera's band | 2 of 45 | 4.4 percent |

Both denominators coincide now that the gate covers the belt. They did not
before: at the previous optics only 29 of 45 crossings were inside a band, and
the same two decodes read as 3.4 percent or 2.2 percent depending on which was
quoted. The measurement reports both for that reason.

| Class | Crossings | Decoded |
| --- | --- | --- |
| `M-06` ferrous metal | 20 | 2 |
| `M-02` HDPE | 15 | 0 |
| `M-04` other plastic | 5 | 0 |
| `M-09` paperboard | 5 | 0 |

Every decode is a steel can, and the headline figure hides that. The two read
were `037600138727` and `077623000618`, on the potted meat can and the master
chef can.

The decoder tries each frame at full scale and then at half, which recovers the
sugar box from its texture and recovers nothing extra from a rendered gate
frame. So the rendered yield is 2 either way, and the limit is not the reader.
A barcode wrapped around a can foreshortens non-linearly under a nadir view, and
most packages present no readable symbol from directly above at all, which is
why a real line uses omnidirectional readers. Cropping to the object's
segmentation bounds before decoding returns zero, because the crop clips the
barcode's quiet zone.

Five of the eighteen objects carry a symbol this project can read at all, which
bounds the rendered figure before any optics argument: `silicon_bottle`,
`pudding_box` and `sugar_box` from their textures, and `master_chef_can` and
`potted_meat_can` only from rendered frames, because the render unwraps a
cylinder the flat texture presents at an angle no detector reads.

The yield is low and the cause is not the optics. A barcode wrapped around a can
foreshortens non-linearly under a nadir view, and most packages present no
readable symbol from directly above at all, which is why a real line uses
omnidirectional readers. Cropping to the object's segmentation bounds before
decoding returns zero, because the crop clips the barcode's quiet zone.

## The object set

Selection was bounded by the previous arm's 0.180 m spline stroke. The UR10e's
vertical band is 0.50 m, so that bound no longer binds, and the set below is
inherited rather than re-derived. The end effector is specified separately and
is what will set the next bound.

| | 55.7 mm jaw | 0.180 m stroke |
| --- | --- | --- |
| Scanned models admitted | 153 of 1,030 | 836 of 1,030 |
| YCB packages admitted | 4 of 9 | 8 of 9 |
| Objects in the set | 14 | 18 |
| Classes covered | 4 of 11 | 4 of 11 |

The four YCB packages the jaw refused, measured from the compiled mesh:

| Mesh | Footprint | Height | Class |
| --- | --- | --- | --- |
| `002_master_chef_can` | 102.5 by 103.2 mm | 140.8 mm | `M-06` |
| `005_tomato_soup_can` | 67.8 by 67.9 mm | 101.8 mm | `M-06` |
| `010_potted_meat_can` | 57.7 by 85.2 mm | 101.7 mm | `M-06` |
| `006_mustard_bottle` | 57.7 by 95.9 mm | 191.4 mm | `M-02` |

`003_cracker_box` is the one package still refused, at 214.5 mm against a
210 mm ceiling.

Class coverage did not move, and the reason is that searching both collections
for the missing types returns no PET bottle, no individual aluminum can, no
glass container, no corrugated box and no beverage carton. One bottle exists
among the 836 models that fit. The effector was never the binding constraint.

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
were derived when the budget was 1.13 s; the budget is 5.92 s at the fastest
belt speed the configuration allows. They are left where they are, because a
tighter gate than the physics demands costs nothing and moving one is a
deliberate decision rather than an edit.

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
