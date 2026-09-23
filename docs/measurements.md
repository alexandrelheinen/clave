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
| Belt width | 0.50 m | same, narrowed; see below |
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

### Narrowing the belt to 0.50 m

The belt was 1.00 m wide and the reason for narrowing it is reach margin
rather than cost. Sweeping 51 lateral samples through the same reachability
test the safety layer applies:

| | 1.00 m belt | 0.50 m belt |
| --- | --- | --- |
| Radius at the near edge, x = 0 | 0.200 m | **0.450 m** |
| Radius at the far edge, x = 0 | 1.200 m | **0.950 m** |
| Lateral samples reachable | 51 of 51 | 51 of 51 |
| Window along travel at the far edge | 0.70 m | **1.62 m** |

The near-edge figure is the one that mattered and it was a defect rather
than a margin: 0.200 m is inside the 0.25 m dead zone the annulus leaves
around the base, so a strip of the belt nearest the arm could not be reached
at all near x = 0 even though every lateral position was reachable somewhere
in its travel. The far edge sat at 1.200 m against a 1.25 m outer limit,
where the arm is most extended and its lag against a moving command is
worst.

Narrowing also brings the whole belt inside what the sensing gate images.
The optical calculation and the measured extent disagree, at 1.100 m across
and 0.780 m, and that disagreement does not have to be settled here: 0.50 m
of belt is inside both, so the defect the roadmap carried about the gate not
covering the belt it stands over is closed either way.

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

**These figures predate the object set losing `master_chef_can` and are
stale.** It was one of the only two objects that ever decoded, so the yield
below is now an overstatement by roughly half and has to be re-measured. The
numbers are left visible rather than deleted, because a reader comparing an
old report needs to see what they were.

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

## The end effector

A Robotiq 2F-85 from MuJoCo Menagerie, at the same commit the arm came from,
bolted to `attachment_site`. Everything below is read off the compiled model
rather than off a datasheet.

| Quantity | Measured |
| --- | --- |
| Flange to pinch point | 155.8 mm |
| Pad separation, fully open | 98.4 mm between pad body origins |
| Pad separation, fully closed | 14.9 mm between pad body origins |
| Command range | 0 to 255, which is the scale a real 2F-85 takes |
| Force range | plus or minus 5 N at the tendon |

`arm.max_grasp_width_meters` is the catalogue stroke of 85 mm rather than the
98.4 mm measured between body origins, because the clear opening between pad
faces is the smaller figure and the catalogue states it.

Lowering that bound from 180 mm refuses `master_chef_can`, a cylinder
102.5 by 103.2 mm that does not fit in any orientation, so it left the object
set. The set is 17 objects and the class coverage did not move: `M-02`,
`M-04`, `M-06` and `M-09`.

### How near the flange gets to an object

The jaw's clear opening, measured between the pad faces with the gripper
open, is **85.2 mm**, which agrees with the catalogue stroke to 0.2 mm. An
object of width `w` therefore leaves `(85.2 - w) / 2` of side clearance, and
a flange that misses by more than that closes the jaw onto the object rather
than around it.

Three corrections have moved that miss:

| | Gap to the object | Objects that straddle |
| --- | --- | --- |
| Commanding the observed pose | 102 mm | 0 of 17 |
| With interception | 86 mm | 0 of 17 |
| With interception and the servo lead | **19 mm** | **14 of 17** |

The three that still do not are `mustard_bottle` and `potted_meat_can` at
57.7 mm, and `tomato_soup_can` at 67.8 mm, whose clearances are 13.7, 13.7
and 8.7 mm.

The servo lead is what did most of it. Sweeping a target across the
workspace, the steady-state lag divided by the commanded speed is 38.6,
34.6, 34.0, 33.2, 32.8 and 32.8 milliseconds at 0.15 through 1.00 metres
per second: flat, which makes it a time constant rather than a distance.
Commanding the pose the reference will hold 33 ms from now cancels 92 to 97
percent of it, leaving 0.8 to 0.9 mm at every speed, and the loop now
reports the flange holding its commanded pose to under a millimetre.

**What is left is perception rather than control.** The flange tracks what
it is told to within a millimetre, so most of the remaining 19 mm is the
tracker's own estimate, whose residual against a belt-carried anchor was
measured at a mean of 13.4 mm over 231 observations.

### Flying a planned pick

Planning the whole visit as timed arcs, rather than stepping a reference
toward a pose, closes the control side of the problem. Over a 20 second
rollout on the shipped line, the flange reaches the pose the plan asks for
at the instant the jaw shuts with a mean error of **2.7 mm and a worst of
3.4 mm**, and no visit faults.

Two things had to be true before that number appeared, and both were wrong
on the first attempt:

| | Arrival error, mean | Worst |
| --- | --- | --- |
| Plan fixed at commit | 48.1 mm | 275.4 mm |
| Re-aimed, no room to re-aim | 58.4 mm | 281.4 mm |
| Re-aimed, with margin and a reach check | **2.7 mm** | **3.4 mm** |

The middle row is the instructive one. Re-aiming the approach at a fresher
estimate is refused unless the arc has room to move, and the bisection
returns the soonest feasible interception, which by construction sits
exactly on whichever ceiling binds. At a margin of 1.00 the shipped line
managed one correction per visit, all of them inside the last half second;
at 1.15 a correction lands on every capture of the approach. The margin
also pushes the interception further downstream, which can put the grasp
pose outside the annulus, so the plan falls back to the soonest
interception where it does.

### What the jaw's clearance above the belt was

Measured by replaying a recorded run's own state through the compiled model:
6001 samples at 100 Hz from a 60 second ground-truth run on 2026-09-21, every
sample's `qpos`, `qvel` and `ctrl` restored and `mj_forward` called, then the
gripper's collision geoms, the tool axis and the belt contacts read out of the
result.

**The transport model was extrapolating the wrong axis.** The plan is given a
velocity to predict the object with, and it was being given the object's
measured three-axis velocity. On the belt those components are:

| Component | Median \|v\| | p90 \|v\| | Worst \|v\| |
| --- | --- | --- | --- |
| Along the belt (x) | 0.250 m/s | 0.267 m/s | 0.754 m/s |
| Across the belt (y) | 0.022 m/s | 0.250 m/s | 2.127 m/s |
| Vertical (z) | 0.027 m/s | 0.111 m/s | 1.782 m/s |

over 17209 samples of objects resting on the belt, whose x velocity matches the
belt because the belt drives it. Predicted forward over an interception, the
vertical component moves the commanded grasp plane by:

| Transport velocity given to the plan | Grasp plane asked for | Error |
| --- | --- | --- |
| The belt's own, `(0.260, 0, 0)` | 1.0758 m | — |
| `(0.260, 0, −0.027)`, the median vertical | 1.0449 m | **−30.9 mm** |
| `(0.260, −0.250, −0.110)`, the p90 pair | 0.9596 m | **−116 mm** |

The belt surface is at 0.900 m and the marker's own floor puts the grasp plane
at 1.0678 m at its lowest, so the median case asks the jaws to descend 31 mm
below every floor the world and the marker enforce.

**The jaws reached the belt.** In the same run the lowest gripper collision
geometry fell to **0.8993 m**, a 0.7 mm penetration of a surface at 0.900 m, the
pinch point fell to **0.8839 m**, and **343 of 6001 samples** had a contact
between a pad and the belt. The tool axis left the belt normal by up to 23.6°
while descending, **48.1° while holding** and **57.8° while retreating**, and
during the hold the flange travelled along the belt at 0.05 to 0.07 m/s where
the belt was moving at 0.26 m/s: the pads were pinned by friction to the belt
the position actuators were pushing them into.

**The jaw's geometry was misdescribed.** Read in the tool's own frame, one pad
box measures 8.0 mm along the closing direction, 22.0 mm across it and 37.5 mm
tall, against the 12 × 40 × 50 mm the effector configuration claimed: a quarter
turn from the real pad and a different size in every direction. And the pinch
site, which is the pose every marker and every commanded flange pose is
expressed against, is not the lowest part of the jaw at all: the pads reach
**160.3 mm below the flange with the jaw open and 173.5 mm with it shut**,
against the 155.8 mm of the pinch point, so a clearance quoted there is 4.5 to
17.7 mm more generous than the jaw's own. The marker's floor of 12.2 mm above
the surface therefore put the pads **5.5 mm inside the belt** while the marker's
own plane said they were clear.

**What cannot be attributed, and why that is recorded here.** This run was made
at 23:17 on 2026-09-21 and the tree it ran at is not written beside it. The phase
timeline does not reproduce: the plan's `DESCEND` leg is **0.40 s** from the
configuration and from a plan rebuilt at the run's own recorded state, while the
telemetry's `DESCEND` column spans 0.79 to 0.80 s in all four visits. Every
figure above is a statement about the state the run reached, which is
independent of which code commanded it; the phase durations are not, which is
what `AC-MOVE-52` exists for.

**What the three control fixes changed, measured the same way.** A 24 second
run of the same line (`clave sim --seconds 24 --telemetry --gt`), whose own
metadata file records the revision and the configuration digests it flew under:

| | Before | After |
| --- | --- | --- |
| Smallest jaw clearance above the belt | −0.7 mm | **−1.4 mm, for 1 tick of 2400** |
| Ticks with a pad-to-belt contact | 343 of 6001 | **1 of 2400** |
| Tool axis off the belt normal, worst | 57.8° | **32.7°** |
| Flange to the pose the plan asked for | 2.7 mm | 2.7 mm, unchanged |

**The residual is one tick of one retreat, and its cause is in the same
telemetry rather than guessed.** At that instant the commanded flange is rising
at 0.13 m/s while the achieved flange falls 15 mm below the plane it had been
holding: the lift is breaking the jaw free of an object it has just closed on,
and the geometry is carried down with it. Two repairs are visible and neither is
taken here, because choosing between them needs this transient measured over
more than one visit: lift more slowly until the break-free transient is inside
the clearance, or take the clearance with a margin sized to the transient. Both
are now measurable figures rather than arguments.

### Why the jaw still holds nothing

Measured on the 1.00 m belt fed by elapsed time. Narrowing the belt and
metering the feed moved every figure below without being aimed at them, and
[What the narrower, metered line does to the pick](#what-the-narrower-metered-line-does-to-the-pick)
carries the current numbers. The diagnosis did not change, only its size.

Not the control. At the instant the jaw shuts, the nearest object to the
pinch site is **94 to 619 mm away**, while the flange is 2.7 mm from the
pose it was sent to. The arm arrives exactly where it was asked to, and it
is asked to go where no object is.

The estimate it is sent to degrades with distance from the sensing gate.
Measuring every settled record against the nearest object it could describe,
over a 25 second rollout:

| Where the record sits | Records | Median | p90 |
| --- | --- | --- | --- |
| Inside the gate, x below -0.5 m | 195 | 11.7 mm | 115 mm |
| The near pick zone, -0.5 to +0.5 m | 306 | 182 mm | 387 mm |
| Downstream, above +0.5 m | 1885 | 644 mm | 2817 mm |

The gate figure matches the 13.4 mm residual above. Everything else is dead
reckoning: the only camera carrying the detection role stands at x = -1.00 m
and images 0.92 m of travel, the arm's annulus runs from about -0.9 m to
+1.1 m, and no sensor observes an object again after it leaves the gate. The
belt model carries travel along the belt exactly and carries drift across it
not at all, and an object rolling or settling drifts sideways by a mean of
10 mm over half a second and 41 mm over 2.5 seconds, against a jaw whose
narrowest side clearance is 8.7 mm.

The record count in that last row is the other half of it. Tracks are not
retired when their object leaves, so they accumulate and are dead-reckoned
indefinitely, and the arm serves them alongside the real ones.

**Adding cameras over the pick zone does not fix it on its own**, which was
worth measuring rather than assuming. With the same sensor, lens and
standoff as the gate, one camera at x = +0.30 m took the run from 1 grasp in
6 to 2 in 5; tiling the whole reachable span with two took it back to 1 in 5.
The mechanism is association: a detection carries no identity and joins the
nearest track inside a gate scaled to that track's footprint, and a track
whose prediction is already 180 mm out falls outside its own gate, so the
fresh observation opens a duplicate track instead of correcting the stale
one. Open tracks ran to 28 and 51 against about a dozen objects.

So the next thing to fix is perception downstream of the gate, and it is two
changes rather than one: a sensor that sees where the arm works, and an
association and retirement rule that lets its observations reach the track
they belong to.

### Holding the line at a feed rate

The line now carries a rate it is asked for rather than whatever the spawn
timer produced. Objects are released every so many metres of belt travel,
and a proportional-integral controller trims belt speed to hold the
measured rate on setpoint. Over a 180 second run at a setpoint of 0.250
objects per second, it settles at **0.256 objects per second with the belt
at 0.304 m/s**, which is off both drive limits and within 4 mm/s of the
0.300 m/s the mean spacing predicts.

Two corrections were needed and both are worth recording.

**The controller was a double integrator, not a PI.** Written in velocity
form, adding the proportional term to the command each tick, it accumulates
that term five hundred times a second at the physics rate: an error of a
tenth of an object per second moved the belt by 2.5 m/s in one second of
simulated time. The loop pinned itself to a drive limit on any error at all
and stayed there, which is exactly what the shipped line did before the fix,
reading 0.267 against a 0.250 setpoint while sitting at 0.250 m/s. In
positional form, with both terms added to the speed the run drew, it
settles.

**The measurement window was too short.** A rate is a count over a window,
so its uncertainty goes as the square root of the count. At this setpoint a
30 second window holds about 7 objects and estimates the rate to roughly a
third, and the loop chases that noise. Ninety seconds holds about 22 and
estimates it to roughly a fifth. A slow line cannot be metered quickly, and
that is arithmetic rather than a tuning failure.

**The pool had to start recycling.** A compiled MuJoCo model cannot gain
bodies at run time, so the line drew from a fixed pool of 22 and stopped
feeding once it was spent. A rate the line holds for ninety seconds is a
different claim from a rate the line holds, so a slot now returns to the
pool when its object runs off the end of the belt.

### What the narrower, metered line does to the pick

Neither change was aimed at the grasp, and both moved it, because a slower
belt is a shorter dead-reckoning horizon and a sparser one is a cleaner
scene. Measured over runs of 20 to 180 seconds:

| | Before | After |
| --- | --- | --- |
| Objects given up for want of an interception | 11 of 16 | **0 of 39** |
| Jaw to the nearest object when it shut | 94 to 644 mm | **18 to 339 mm**, mostly 30 to 45 |
| Grasps that held | 0 of 5 | **8 of 39** |
| Flange to the pose it was sent to | 2.2 mm | 2.1 mm |

The arm's own accuracy did not change and was never the limit. What changed
is how far the pose it is sent to has drifted by the time it gets there.
Four fifths of grasps still fail, and the failures are still the visits
whose jaw gap runs to 100 mm and beyond, which is the same open defect: no
sensor observes an object after it leaves the gate.

**One correction inside this change is below what the run can resolve, and
is worth keeping anyway.** Making belt speed variable left the tracker, the
task machine, guidance and selection all predicting with the speed the run
drew rather than the speed the belt is running at. The controller moves
0.3125 to 0.304 m/s, and 0.0085 m/s over a two and a half second
interception is 21 mm, which is the order of the jaw's side clearance.
Fixing it moved the grasp count from 10 of 40 to 8 of 39, which on forty
samples is noise either way: the binomial spread at a quarter is about
seven points. It stays because predicting with a speed the belt is not
running at is wrong whatever a forty-sample run says about it.

### What a velocity estimate recovers

The tracker now estimates a velocity per object from successive
observations and carries it between them with that, rather than asserting
the belt's speed along travel and no drift at all across. It is an
alpha-beta filter, which is the steady-state Kalman filter for a
constant-velocity model, and
[motion-estimate.md](requirements/motion-estimate.md) carries why.

Swept against ground truth over one rollout, so every setting sees
identical observations:

| Lateral velocity gain | Gate median | Pick zone median | Pick zone p90 |
| --- | --- | --- | --- |
| Replace outright, the old model | 8.9 mm | 45.6 mm | 123 mm |
| 0.10 | 9.3 mm | 41.4 mm | 132 mm |
| 0.20 | 9.1 mm | **41.1 mm** | 131 mm |
| 0.40 | 9.6 mm | 41.7 mm | 133 mm |
| 0.80 | 8.9 mm | 41.7 mm | 133 mm |
| 0.40, and learning travel velocity too | 10.0 mm | **81.4 mm** | 221 mm |

Three things to read off it.

**The filter recovers four millimetres of forty-five, and the gain hardly
matters.** Flat from 0.1 to 0.8 is what a model recovering everything a
constant-velocity assumption can recover looks like. The rest of the error
is not the filter's to remove.

**The tail gets slightly worse**, 123 mm to 131 mm, which is the price of
extrapolating a drift that is decaying as though it were constant. The
increments of lateral drift over growing horizons are 8.8, 8.1, 7.5, 6.5
and 5.3 mm, so an object that is rolling is also settling, and a constant
velocity fitted inside the gate over-predicts two seconds past it.

**Learning the travel velocity is actively harmful**, nearly doubling the
pick-zone median. The belt drives that axis rigidly, so the residual the
filter would learn from there is the segmentation's noise rather than the
object's motion. The travel gain is kept small rather than zero only
because the feed controller moves the belt and a frozen velocity goes
stale.

On the pick itself the effect is below what a run resolves: 10 of 39
grasps held with the filter against 8 of 39 without, on a binomial spread
of about seven points. The filter stays because four millimetres is real
and because asserting a drift of zero is asserting something false, not
because forty samples showed it.

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

## The three questions the belt-clearance work left open

Each of these was measured on the tree that carries the fixes, with the run's
own metadata recording the revision and the configuration digests it flew
under. Two of them turn out to be stale numbers in the documents rather than
defects in the machine, and the third is a defect with a named owner.

### What the arm aims at, with the tracker in the loop

Three picks, 24 second run, tracker-driven rather than ground truth
(`clave sim --seconds 24 --telemetry`), measured as the distance from the pinch
site to the nearest object at the instant the jaw shut:

| Pick at | Pinch x | Distance to the nearest object | Camera imaging that x |
| --- | --- | --- | --- |
| 8.51 s | −0.112 m | 123 mm | `pick_wide` |
| 14.72 s | +0.493 m | **35 mm** | `pick_wide` |
| 20.46 s | −0.394 m | **415 mm** | `gate_wide` |

The same run reaches the pose the plan asks for to 1.8 mm median and 2.7 mm
worst, so the control side is not the limit: the *aim* is. Every one of the
three picks was inside a detection camera's footprint, which is what makes this
a different statement from the one
[roadmap.md](roadmap.md#open-defects) carries. The world has **two** detection
cameras, not one: `gate_wide` at x = −1.00 m images −1.72 m to −0.28 m and
`pick_wide` at x = +0.38 m images −0.345 m to +1.105 m, which together cover the
whole reachable window of −1.036 m to +1.036 m. The floor's comment that
`gate_wide` "detects it out to x = −0.275 m and no further, so 1.31 m of the
zone the arm actually works in was never observed" describes the world before
`pick_wide` was added, and the repository still repeats its consequences.

What is left is the estimate and the identity behind it: an observation carries
no identity, and it joins the nearest track inside a gate scaled to that track's
footprint, so a track tens of millimetres out can fail to be corrected by a
fresh observation and no run reports the failure as a failure. The fix is the
association and retirement rule already specified as
[learned-tracker](requirements/learned-tracker.md) at v1.2.0, and the figures to
aim at are the 35 to 415 mm above rather than the 94 to 644 mm the roadmap
carries.

### What the actuator lag costs now

Swept against a target walking at constant speed along the belt, on the
compiled world, with and without the shipped lead:

| Lead | 0.15 m/s | 0.31 m/s | 0.60 m/s | 1.00 m/s |
| --- | --- | --- | --- | --- |
| None, steady-state lag | 5.75 mm | 10.66 mm | 19.94 mm | 32.67 mm |
| None, lag ÷ speed | 38.3 ms | 34.4 ms | 33.2 ms | 32.7 ms |
| `lead_seconds: 0.033` | **1.25 mm** | **1.08 mm** | **0.99 mm** | **1.21 mm** |

The lag is a time constant, as `servo.lead_seconds` says it is, and the lead
cancels 96 to 99 percent of it at every speed. So the lag is not an open defect:
it is a solved one whose solution the *other* number never heard about.
`task.arrival_tolerance_meters` is 0.070 m and its comment rests on "the settled
error at 24.3 mm over most of the width and 60.9 mm at the far edge", measured
before the servo carried a feedforward term — the comment even names the fix
that has since been made. At 1.0 to 1.25 mm of settled error the tolerance is
56 to 70 times the error it gates, and a stepped visit therefore counts as
arrived a long way before it has. Lowering it is a behaviour change that needs
its own run rather than a quiet edit, so it is recorded here and not taken.

### What the annulus costs

| | Meters |
| --- | --- |
| Belt length | 3.00 |
| Reachable stretch on the belt centreline | −1.036 to +1.036, **2.07** |
| Belt outside the annulus | 0.46 at each end, 31 percent of the length |
| Inner hole (0.25 m about the base) | never reaches the belt: the base stands 0.45 to 0.95 m from it |
| Trusted annulus against the measured reachable | 0.25 to 1.25 against 0.200 and 1.266 to 1.309 |

Two things follow. The trusted region is strictly inside the region the arm can
actually reach, which is the direction an interlock should err in, and the inner
hole never bites the belt, so the projection that keeps a path out of the hole
costs nothing on a pick and only shapes the swing near the base. And the belt is
longer than the arm can serve, which is why the line meters objects into the
window instead of feeding them blind: nothing in either run of this work was
refused for reach — the tracker-driven run's one refusal is `no interception`,
which is timing — and the arm served 2 to 3 visits in 24 s against a feed of
0.125 objects per second. That last pair is the figure to watch, because the arm
is serving the line's rate with no margin rather than comfortably above it.

## What the reported run turned out to be

`runs/debug/deepseek` was reported with four symptoms: the arm descending onto
empty belt, the tool not turned to the specified orientation, sudden upward
movements, and objects left to pass. Everything below is measured on that run
(`20b2765`, `clave sim --video --no-window --seconds 60 --view belt --gt
--telemetry`) or on the same command re-run at the head of the branch that
carries these fixes. **Each figure is one run at seed 0**, and the objects'
trajectories are chaotic, so the runs are comparable in mechanism and not to
within a visit; where two changes were compared they were compared on the same
run.

The first reading of this run did not account for `--gt`. Downstream selection
and planning consume markers built from MuJoCo bodies rather than the tracker's
beliefs, so a story built out of `records.txt` described a machine that was not
steering anything. What made that mistake possible was itself a defect: the run
printed its report and kept nothing, which is `AC-MOVE-55`.

| Figure | `20b2765` | With the fixes |
| --- | --- | --- |
| Visits served in 60 s | 4 | **8** |
| Time parked | 35.97 s of 60 s | none after the eighth visit |
| Visits that shut the jaws on empty belt | 2 of 4, at 267 and 246 mm | 2 of 8, at 185 and 167 mm |
| Visits given up for a stale aim | not measured, not possible | 2, each with its distance recorded |
| Arrival error against the commanded pose | median 2.8 mm, worst 113.8 mm | median 2.7 mm, worst 163.1 mm |
| Jaw to the nearest object when it shut | 57, 22, 267, 246 mm | 73, 34, 42, 59, 185, 167, 79, 23, 13 mm |
| Tool yaw off the object's own axis | 8.8, 7.3, 0.1, 19.1 deg | 6.1, 5.3, 45.0, 29.7, 13.3, 37.8, 1.8, 38.8, 23.4 deg |
| Worst vertical lurch over a visit | 52.9 m/s², on the one visit that gripped | 150.2 m/s², on a visit that gripped |
| Smallest jaw clearance above the belt | −1.4 mm, 1 tick in contact | −0.9 mm, 12 ticks in contact |
| The object pushed below the belt by the closing jaws | 27 mm | 0.9 mm |
| Tool axis off the belt normal, worst | 32.7 deg | 34.0 deg |

Four mechanisms were found; two of them are closed.

**A marker's identity was a pool slot, so each slot was served once.** The
ground-truth markers were identified by `item.index`, and the conveyor hands a
slot back the moment its object leaves the belt, so after one pass over the four
slots the task machine had served every identity the world could produce: **4
visits in 60 s and 35.97 s of it parked**, against a feed setpoint of 7.5 visits
in that time. A marker's identity is now the object's spawn serial, and the arm
serves 8.

**The plan flew a stale aim when the refinement was refused, which is the
ordinary outcome for an object that falls behind its own prediction.** No arc
takes the arm back up the belt, `refine` returns None, and the machine used to
hold the plan it had and fly it. Measured at the instant the jaws shut: the plan
was aiming at (−0.422, +0.053) with the nearest object **338 mm upstream** of
that, and at (+0.319, −0.404) with the nearest object **231 mm across the belt**
from it, in both cases while reporting an arrival error of 2.0 and 2.4 mm. The
freshest estimate is now compared with the pose the plan is aiming at: inside
the tolerance the plan flies, past it the visit is solved again from the
freshest estimate, and where no interception exists it is abandoned with its
reason and the object recorded as missed. The visits a later run gave up were
given up with their distances -- 36 and 148 mm out -- which is the figure no
arrival error can show.

**The jaw closed with ±5 N·m on parcels that weigh ten to twenty grams.** The
objects weigh 9 to 20 g, read from the compiled model, and the vendored 2F-85
ships ±5 N·m: roughly a hundred newtons at the pads. Closing drove the object
the jaw was holding **27 mm below the belt surface**, took the jaw's own
collision geometry 1.4 mm inside the belt, tilted the tool 3.7 degrees off the
belt normal and released a 52.9 m/s² lurch when the parcel escaped. The torque
is now a world parameter, applied to the vendored spec by the scene and sized by
the jaw's own stroke against the torque it is allowed: below 0.30 N·m the
linkage's friction and the tendon's preload hold the fingers and the jaw loses
part of its 83 mm stroke (0.05 N·m reaches 29 mm of 98, 0.20 reaches 80.5 of
98.4, 0.30 reaches all of it). The crush is 0.9 mm instead of 27.

**The objects turn on the belt, and a grasp yaw is claimed half a second before
it is used.** Measured at the instant the jaws shut, over nine grabs: up to
**5.4 rad/s**, which is 155 degrees over the capture interval, and 22 to 40
degrees of error between the commanded yaw and the object's own axis. Three
repairs were tried and every one cost more than it bought:

| Repair | Pad-to-belt contact | Worst vertical lurch | Grasps held |
| --- | --- | --- | --- |
| none | −0.6 mm, 4 ticks | 99 m/s² | 1 of 7 |
| the spin pinned to zero each tick | **−2.8 mm, 54 ticks** | **934 m/s²** | none of 7 |
| the spin damped, 0.3 s constant | **−18.6 mm, 17 ticks** | 170 m/s² | none of 8 |
| the yaw predicted over the whole plan | **−106.6 mm, 67 ticks** | 361 m/s² | none of 8 |

Pinning a body's rotation while the belt drags it turns the contact into a
reaction that tips the parcel over. Damping leaves the parcels flat, presenting
their narrow edge to a jaw that closes on it and pulls itself down. And 5.4
rad/s carried over a four second plan is twenty radians, which is not a
prediction but a direction drawn from a circle that has wrapped several times.
So the repair that survived is the bounded one: the marker carries the rate, and
the machine turns the tool to the yaw the object will hold *while the turn being
predicted is inside the 45 degrees a jaw's symmetry leaves useful*, commanding
the claim beyond it. What remains is the objects whose turn is past that
threshold, and no control-side answer exists for them: a parcel spinning that
fast cannot be aligned with. The honest repairs are a settling zone on the line,
or a gripper that does not need an axis.

### Why the lurch figure is not better than the run it started from

52.9 m/s² became 150.2, and the comparison is not like for like. The run at
`20b2765` served four visits, two of which shut the jaws on empty belt and never
touched anything, so its worst lurch is drawn from the one visit that gripped.
The run with the fixes served eight, six of them onto an object. What the fixes
did to the lurch is remove part of its cause: the energy in that spike was the
squeeze on a ten gram parcel, and the squeeze is seventeen times smaller than it
was. A run that grips nothing reports a low lurch for the wrong reason.

### What the prediction was actually doing, measured three ways

The first pass of this work blamed the *tracker* for the aiming errors and the
second blamed the *force* and the *yaw*. Both were wrong about the largest term.
Decomposing every visit into three numbers -- the pose the plan was aiming at,
the linear prediction of the object from the freshest capture, and where the
object actually was when the jaws shut -- says where the error lives, and it is
in the model of the *second* horizontal axis.

| Axis | Autocorrelation after 0.2 s | After 0.8 s | Speed |
| --- | --- | --- | --- |
| Along the belt | +0.85 at 0.01 s, driven by the belt | held | median 0.25 m/s |
| **Across the belt** | **+0.04** | **−0.02** | median 0.025, p90 **0.261 m/s** |
| Rotation about the belt normal | **−0.03 at 0.04 s** | −0.00 | median 0.265, p90 **17.0 rad/s** |

The object is driven along the belt and nothing drives it across: the drift is
a fraction of a second long and the *turn* is over in tens of milliseconds.
Both were being carried over the whole visit, which commits up to four seconds
ahead, so the p90 drift became **900 mm of aim error across the belt** and the
turn became a number drawn from a circle that had wrapped several times.

Measured before and after bounding the drift to the 0.30 s it lasts for:

| | Before | After |
| --- | --- | --- |
| Aim against the object's own lane at the grip | 208 and 346 mm on two visits of nine | **9 to 33 mm** on every visit |
| Jaw to the nearest object when it shut | 73, 34, 42, 59, **185**, **167**, 79, 23, 13 mm | 22, 29, 94, 36, 26, 20, **99** mm |
| Arm behind its own command while the jaws close | 50 to 80 mm, with the command outside the trusted region | inside the region, and the plan is refused when a leg leaves it |

That is the defect behind "the arm goes where there is nothing": not the
tracker, not the capture rate, but a velocity from the wrong axis multiplied by
the wrong horizon. It is also why the earlier attempts in this branch, which
aimed at the force and the yaw, did not move it.

### What is still not fixed, and what it would take

**The jaw closes near the top of a parcel and shoves it.** With the aim inside
30 mm, the jaw still holds one object in seven. The pads are 37.5 mm tall and
their lowest geometry is kept 10 mm above the belt, so the lowest pinch plane
the jaw may take is 27.7 mm above the surface, and the marker places its plane
at the object's own mid-height clamped up to that. A parcel lying 18 mm thick
therefore gets about **9 mm of pad overlap**: closing drives it down and out
rather than clamping it, and the lift is zero. The two repairs are a jaw whose
pads reach lower (a gripper change) or a grasp plane that is allowed lower for
flat objects while the pads still clear the belt (a world change, and the
clearance that made it legal is what the pads are sized against).

**The rotation of a parcel on this belt is not physical, and that is the root
of the yaw problem.** The p90 turn rate is **17.0 rad/s** and the worst is
299 rad/s: a parcel whose centre velocity the belt drives *as a constraint*
while its contact patch is free to spin is not a parcel riding a belt, and the
friction between the two winds it up. No control-side fix reaches that, which
is why bounding the yaw prediction at 45 degrees is the honest answer rather
than a shim. What it needs is the belt modelled as a *surface* moving under the
object, with friction between them, rather than a velocity imposed on the
body's centre.

A settling zone was tried as the repair this bullet points to, and measured the
same way it was rejected. Stepping the conveyor directly at seed 0 and reading
the total angular speed (the norm across all three axes) as each object crossed
the gate: damping the rotation upstream of the gate (an exponential decay of
the angular velocity at 8 per second) moved the p90 from **6.4 to 14.2 rad/s**,
and a damping torque applied through the solver made the simulation unstable
within five seconds. Damping does not settle a parcel; it freezes it mid-tumble
where the driven centre keeps winding it up. The belt model remains the only
repair that touches the cause.

**One pad contact of −98 mm appears in the report and not in the telemetry.**
The report's clearance is the minimum over every physics tick; the telemetry
series is sampled at 100 Hz. On the run above the report carries a single tick
at −98 mm while the sampled series shows 3 ticks at −0.6 mm, so the deep figure
is a sub-20 ms event that the series does not catch. It is recorded rather than
explained: nothing has been done to show whether it is a solver artefact at a
contact or a real excursion.

