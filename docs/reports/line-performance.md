# What the line does, as configured

Measured on the configuration in this branch, over rollouts of 90 to 180
simulated seconds at seed 0. Every figure here came from
`clave debug-tracker`; none is estimated or carried over from an earlier
configuration. Where a figure replaced an earlier one, the earlier one is
shown beside it rather than deleted.

## Throughput

| Quantity | Value |
| --- | --- |
| Feed setpoint | 0.250 objects per second |
| Rate achieved | 0.256 objects per second |
| Belt speed commanded | 0.304 m/s, off both drive limits |
| Drive range | 0.250 to 0.350 m/s |
| Objects released | every 1.00 to 1.40 m of belt travel |

The loop holds. It is worth saying what "holds" means here: the belt sits
at 0.304 m/s against the 0.300 m/s the mean spacing predicts, which is 4
mm/s, and the measured rate sits 0.006 objects per second above setpoint.
Both are inside the noise of counting twenty-two objects in a ninety second
window.

## The arm

| Quantity | Value |
| --- | --- |
| Visits completed | 38 in 180 s |
| Objects given up for want of an interception | 32 |
| Faults | 0 |
| Flange to the pose it was sent to, median | 2.5 mm |
| The same, worst | 4.1 mm, none above 50 mm |

**Read the median, not the mean.** An earlier configuration produced
sixteen visits at 2 to 4 mm and one at 688 mm, and a mean over that set
reads 43 mm, which describes no visit that happened. It was reported that
way here until the distribution was looked at. The command-line report now
prints the median, the worst, and how many exceeded 50 mm.

That outlier has not recurred since the delivery leg landed, and thirty
eight visits is not enough to say it is gone. It was never explained: it
completed without a fault, so the servo accepted every pose it was given
and the arm did not reach one of them.

Thirty two objects were given up for want of an interception against
thirty eight served, which is the price of the delivery. The arm is busy
carrying for about a second and a half per visit, and objects arriving in
that window are past reach by the time it is free.

## The delivery

A visit now ends over the chute its object routes to, rather than at the
retreat. Before this leg existed the plan ran out fifty millimetres above
the belt and the jaw opened there, which dropped the object back where it
came from.

| Quantity | Value |
| --- | --- |
| Objects placed down a chute | 1 |
| Misrouted | 0 of 1 |
| Visits completed | 38 |
| Grasps that held to the retreat | 8 of 38 |

One placement in thirty-eight visits is the first end-to-end sort this
line has done: detected, tracked, intercepted, grasped, carried and
released into the channel its class routes to, with the channel correct.
It is also one, and the gap between it and the eight grasps that held
through the retreat is where the next work is. Seven objects were in the
jaw at the top of the lift and were not in it over the mouth.

The delivery arc is the only one of the five that no interception
constrains, so its duration comes from the distance and the speed ceiling
rather than from a solve. A rest-to-rest quintic peaks at 15/8 of its mean
speed, so taking that as the duration touches the ceiling once and stays
inside it everywhere else. Whether 15/8 of the mean is also what the grip
survives is the open question those seven objects are asking.

## The grasp

| Quantity | Value |
| --- | --- |
| Grasps that held to the retreat | 8 of 38 |
| Objects placed down a chute | 1 |
| Jaw to the nearest object when it shut, best | 25 mm |
| The same, typical | 30 to 80 mm |
| The same, worst | 1277 mm |

Eight in thirty eight is the honest figure for this configuration and it is
not a good one. What the jaw-gap column says is why: the arm arrives where it
was sent to within 2 mm, and where it was sent is 30 to 60 mm from the
object on a good visit. The jaw's clear opening is 85.2 mm, so an object
60 mm wide leaves 12.6 mm of side clearance, and a 30 mm error closes the
jaw onto it rather than around it.

## How the figures moved

Each row is the same measurement under a different configuration, in the
order the changes landed.

| | Visits | Arrival, median | Jaw gap | Grasps held |
| --- | --- | --- | --- | --- |
| 1.00 m belt, fed by time | 16 | 2 mm | 94 to 644 mm | 0 of 5 |
| 0.50 m belt, metered feed | 39 | 2 mm | 18 to 339 mm | 8 of 39 |
| Plus the velocity filter | 39 | 2 mm | 21 to 277 mm | 10 of 39 |
| Plus retirement and pick-zone coverage | 17 | 2 mm | 19 to 741 mm | 4 of 17 |
| Plus the delivery leg | 38 | 2.5 mm | 25 to 1277 mm | 8 of 38, 1 placed |

The last row needs its explanation attached, because read alone it says the
change made things worse and that is not what happened.

Before retirement, a track was never dropped, so an object that left the
sensing gate was re-detected as a *new* track with a new identity. The
machine records what it has served by identity, so the same object was
served repeatedly: 59 visits over a run carrying 46 objects, the same
objects picked at twice. Retirement plus continuous coverage collapses that
to 17 visits over 46 objects, which is a worse service rate and an honest
one.

The grasp rate per visit tells the same story from the other side: 4 of 17
is 24 percent, against 10 of 39 at 26 percent. Statistically the same, on
samples this size, and 8 of 38 at 21 percent is the same again.

## What limits it

Not the arm. The flange reaches its commanded pose to 2 mm, and every
figure above that is worse than 2 mm is the pose being wrong.

The pose comes from the tracker. Measured against the nearest object a
record could describe:

| Where the record sits | Median error |
| --- | --- |
| Inside the sensing gate | 9 mm |
| Through the arm's reach | 42 mm |

Nine millimetres is the segmentation's own noise and is near the floor for
this sensor at this standoff. Forty-two is what the estimate degrades to
across the reach, and a velocity filter recovers four of it. The remaining
thirty-odd is not modelling error: it is the interval between observations
and the fact that an object's motion off the belt axis is not predictable
from the belt.

Two directions remain and they are different in kind. Observing more often
in the pick zone shortens the interval the estimate has to bridge, which is
a sensing change. Approaching sooner after the last observation shortens
the same interval from the other end, which is a layout and cycle-time
change: the interception currently runs two to three seconds, and the
estimate ages by that much before the jaw arrives.
