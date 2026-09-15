# The loop, closed and measured

> Roadmap step: v0.9.0 · Spec: [.kiro/specs/sitl-runtime/](../../.kiro/specs/sitl-runtime/)

> **The geometry in this document was superseded at v1.0.1.** The belt, the arm
> offset, the reach radius, the belt speed and the object sizes were all
> rescaled after a solved workspace sweep found the manipulator could not reach
> the middle of its own belt and its gripper could not close on any object in
> the set. [world-scale.md](world-scale.md) carries the measurements and the new
> values. What this document records is what was measured at the time, and it is
> left standing rather than rewritten.


Every piece existed and none of them were connected. The world ran, models were
trained, the decision contract was published and the routing resolver was
written, and nothing took a frame and produced a decision. This is the step
where a frame leaves the simulator, inference proposes a pick, a deterministic
layer in Rust accepts or overrides it, and the surviving decision is published
on the wire another project will read.

It also settles the choice v0.3.0 deferred and nobody made since. Python runs
inference and Rust never loads a model, recorded as `D-05` in
[docs/decisions.md](../decisions.md) with the three alternatives it beat.

What the loop proves is a mechanism. The models it runs saw 240 frames of
parametric primitives, so a decision it produces says nothing about whether the
object was classified correctly, and this document makes no claim that one was.

## What runs

Two predictors cross the same boundary, which is what makes the cost of
inference separable from the cost of everything else.

| Predictor | What proposes the pick |
| --- | --- |
| `scripted-expert` | The teacher the policies were trained to imitate, reading the world rather than the frame |
| `resnet50-baseline + behavior-cloning-baseline` | The trained checkpoints, reading the rendered frame and the arm's joint angles |

The classifier says what is on the belt and abstains when no class clears a
configured presence floor; the policy says where to reach. Both were trained at
v0.7.0 on the 240 frame dataset v0.6.x recorded.

## Measurement conditions

| Condition | Value |
| --- | --- |
| CPU | AMD Ryzen 7 7735U, 8 threads as PyTorch reported them |
| Accelerator | None. `torch.cuda.is_available()` is false |
| PyTorch | 2.11.0+cu130, running on CPU |
| Frame | 320 by 240, rendered offscreen through OSMesa |
| Simulated time | 20 seconds per run, capturing every 0.5 simulated seconds |
| Belt speed | 0.227 m/s, drawn at seed 0 |
| Reachable window | 0.339 m, so the per-object budget is 1.493 s |
| Transport | One `AF_UNIX` datagram per proposal, one per published decision |

Latency is measured from the moment the frame exists to the moment the runtime
has published the decision and answered. Rendering is excluded, because a camera
on a real line produces the frame and charging that to the pipeline would
measure the simulator.

## The measurement

| Predictor | Samples | Median | p99 | Share of the 1.493 s budget |
| --- | --- | --- | --- | --- |
| `scripted-expert` | 31 | 0.46 ms | 7.04 ms | 0.5 percent |
| Trained checkpoints | 34 | 64.6 ms | 84.6 ms | 5.7 percent |

Held against the tightest budget the world allows, 1.13 s at 0.30 m/s, the
trained loop consumes 7.5 percent and leaves a little over a second for a pick
that nothing in CLAVE yet executes.

**The process boundary is not the cost.** The scripted run pays everything the
trained run pays except inference: it encodes a proposal, crosses a socket,
runs three geometric checks, resolves a channel, encodes a decision in CBOR,
publishes it and answers. That is 0.46 ms at the median. `D-05` bought a safety
layer sharing no code with any model, and the measured price of the separation
is under a millisecond per frame.

Two numbers deserve their caveats. A p99 over 34 samples is the worst sample
rather than a percentile in any useful sense, so read both figures as the
observed spread of a short run. And the median difference between the two rows,
roughly 64 ms, is the classifier and the policy running on a 320 by 240 frame,
which is close to what v0.4.0 measured for ResNet-50 at 96 by 96 once the larger
input is accounted for.

## What the safety layer did

Counted by the runtime itself rather than by the producer:

| Outcome | `scripted-expert` | Trained checkpoints |
| --- | --- | --- |
| Proposals received | 31 | 34 |
| Accepted and sorted | 24 | 21 |
| Overridden, beyond reach | 7 | 11 |
| Overridden, below the belt surface | 0 | 2 |
| Overridden, off the belt | 0 | 0 |
| Rejected on confidence | 0 | 0 |
| Refused as unreadable | 0 | 0 |
| Decisions published | 24 | 21 |

Every published decision arrived back on the decision socket, so the count the
runtime reports and the count the producer received agree.

The scripted expert is the teacher, and the layer overrode it seven times. That
is the most useful thing in this document.

## Why the teacher gets overridden

The expert decides reachability by one coordinate: an object is reachable when
its position along the belt falls inside the window v0.5.0 computed. That window
is the chord the reachable sphere cuts through the belt **centerline**, and an
object is rarely on the centerline. Spawn places objects up to 0.15 m either
side of it.

Working the geometry through from the committed configuration, where the arm
base sits at y = -0.34 m with a reach of 0.38 m:

| Lateral placement | Distance from the arm base | Reachable window |
| --- | --- | --- |
| -0.15 m | 0.190 m | 0.658 m |
| -0.10 m | 0.240 m | 0.589 m |
| -0.05 m | 0.290 m | 0.491 m |
| 0.00 m | 0.340 m | 0.339 m |
| +0.05 m | 0.390 m | 0.000 m |
| +0.10 m | 0.440 m | 0.000 m |
| +0.15 m | 0.490 m | 0.000 m |

An object more than about 0.04 m to the far side of the centerline is not
reachable anywhere along the belt. Since spawn draws the lateral offset
uniformly from a 0.30 m band, roughly a third of objects are unreachable from
the moment they land, and the expert proposes them anyway because its test does
not look sideways.

This does not contradict v0.5.0, which stated its reachable radius was an upper
bound derived from link geometry rather than a solved workspace. It sharpens it:
the 0.339 m window is the centerline value, the window is a function of lateral
placement, and for a third of placements it is zero. The arithmetic above is
derived from `configs/world/sorting_line.yml` and is reproducible from it.

Two consequences follow, and neither is a defect in this step. The expert that
taught every imitation policy at v0.7.0 demonstrated picks that could not have
been executed, so the demonstrations carry an error the policies learned. And
the throughput of any policy trained on them is bounded by a placement
distribution that puts a third of the objects out of reach.

## What this does not show

**No decision here is known to be correct.** The classifier was trained on 240
frames of parametric primitives for three epochs. A run where every proposal
survived the safety layer would say nothing more than this one does.

**Nothing tracks.** CLAVE has no tracker, so the identity a proposal carries
comes from the simulator by matching the predicted point to the nearest labeled
object within a configured radius. Every identity in these runs is ground truth.
A prediction matching no object inside the radius is dropped rather than
published under some other object's identity, which is the only part of this
that a real deployment could keep.

**Nothing moves.** The runtime publishes a decision and stops. Handing it to
FRET so the manipulator acts on it is v0.10.0, and until that exists the cycle
time from decision to placement is unmeasured.

**Nothing ran on hardware.** There is no camera, no belt and no arm on this
machine, and no figure in this document was taken from one.

**The envelope is a sphere intersected with a box.** A real workspace is
neither, so the checks over-permit near the edges of reach. They are an upper
bound on what is safe rather than a guarantee, and the table above is a case
where the upper bound was still tight enough to catch something real.
