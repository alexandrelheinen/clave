# The benchmark, and what it says

> Roadmap step: v1.0.0 · Spec: [.kiro/specs/benchmark-suite/](../../.kiro/specs/benchmark-suite/)

Ten steps produced numbers under ten sets of conditions. This is the one
comparison: every configuration CLAVE can actually run, over the same seeds, the
same world and the same protocol, from one command.

The headline is not flattering and it is the point of running the benchmark
rather than assuming the answer. **No trained configuration beats a constant
predictor.**

## What was run

`clave benchmark`, 24 seeds, 20 simulated seconds each, 480 simulated seconds
per configuration, on an AMD Ryzen 7 7735U with no accelerator, in the world
rescaled at v1.0.1.

| Configuration | Presented | Decided | Accuracy | Decision p99 | Overridden | Gates passed |
| --- | --- | --- | --- | --- | --- | --- |
| `scripted-expert` | 227 | 123 | 54.2% | 0.9 ms | 15 of 691 | 4 of 20 |
| `resnet50 + behavior-cloning` | 227 | 120 | 11.5% | 146.4 ms | 142 of 542 | 4 of 20 |
| `resnet50 + act` | 227 | 124 | 9.7% | 192.7 ms | 0 of 450 | 4 of 20 |

A record is one object that entered the arm's reachable window, which is the
population the validation harness defines: an object that never came within
reach is outside the boundary, since nothing could have been done about it.

**A predictor that always named the most common class would score 19.4%.** Both
trained configurations sit below that. Whatever the loss curves at v0.7.0 showed,
neither learned anything a constant does not already do.

The scripted expert is a control rather than a competitor. It reads the world
instead of the frame, so what it measures is the ceiling imitation could reach
and the loop's cost with inference removed, 0.9 ms.

**Its 54.2% is coverage, not classification.** It decided about 123 of the 227
objects presented and was right about every one of them; the missing 46 percent
are objects it never decided about at all. The cause is measured in
[world-scale.md](world-scale.md): the rescaled belt is slow enough that a mean
of 2.67 objects sit inside the workspace at once, peaking at six, and the expert
emits one decision per frame. The next bottleneck in this pipeline is decision
rate rather than decision latency.

## What could not be measured

The release criteria name five headline metrics. Two of them have no value to
report, and that is stated here rather than omitted or filled with a zero.

| Metric | Why it is unmeasured |
| --- | --- |
| Pick success rate | Nothing in CLAVE grasps an object, so every record carries `picked = False`. The rate would be zero by construction rather than by measurement |
| Cycle time | There is no placement to measure to, for the same reason |
| Generalization drop | The benchmark runs the world the models trained on, so every instance is a seen one and the unseen partition is empty |

Both missing metrics need something to execute a pick, which is FRET's half of
the integration and waits on FRET's own v1.5. Until then the two gates that
depend on them fail for every configuration, including the control, and they
fail on absence rather than on performance.

`AC-BENCH-03` exists because a pick success rate of zero is arithmetically true
and reads as a result.

## What the gates say

Twenty gates, of which the control passes nine. The failures divide into three
kinds and only one of them is about a model.

**Absent by construction.** `pick-success-rate` and `cycle-time-p99` fail for
every row because nothing picks. `generalization-drop` fails because the unseen
partition is empty.

**Short of support.** The gates require 30 records before a class's accuracy
counts as measured. Five of the eight classes present clear it and three do not:
`M-06`, `M-07`, `M-08` and `M-10` each carry 24. Three classes carry none at
all, because the world's object set covers eight of the taxonomy's eleven, which
[v0.6.0](data-pipeline.md) already recorded. Those gates fail as unmeasured
rather than passing on a thin denominator, which is what `min_class_support`
was written to do.

| Class | Records |
| --- | --- |
| `M-01` PET | 46 |
| `M-02` HDPE | 43 |
| `M-03` PP | 34 |
| `M-05` Aluminum | 30 |
| `M-06` Ferrous | 24 |
| `M-07` Glass | 24 |
| `M-08` Cardboard | 24 |
| `M-10` Beverage carton | 24 |

**Actually failed.** The trained rows miss `overall-accuracy` by a wide margin,
0.177 and 0.129 against a 0.80 threshold, and they miss per-class accuracy in
every class that has support. That is the real result, and it is what the
numbers above already say.

## The recommendation

**`resnet50 + behavior-cloning`**, at 11.5% against 9.7% for
`resnet50 + act`, at a p99 decision latency of 146.4 ms against 192.7 ms. The
gap is four records out of 227, which is inside what a handful of objects would
move, so this is a latency choice rather than an accuracy one.

It is a recommendation between two configurations that both fail, which is worth
saying plainly. If CLAVE had to run something today it would run this one, and
the honest reason is that the cheaper policy is not worse than the expensive one
on this data.

The two policies now decide about nearly the same number of objects, 120 against
124, so the coverage difference that separated them before the rescale is gone.
What is left is latency, where behavior cloning is 46 ms cheaper at the 99th
percentile, and both sit far under the 4.14 s the rescaled belt allows.

## What the safety layer did

| Configuration | Proposals | Overridden | Share |
| --- | --- | --- | --- |
| `scripted-expert` | 691 | 15 | 2.2% |
| `resnet50 + behavior-cloning` | 542 | 142 | 26.2% |
| `resnet50 + act` | 450 | 0 | 0% |

The control is now overridden 2.2 percent of the time against 47 percent before
the rescale, and the recommended configuration 26 percent against 65 percent.
[world-scale.md](world-scale.md) explains the fall: the arm could not reach the
middle of its own belt, so most of what any proposer suggested was
geometrically impossible, and the layer was refusing physics rather than
judgment.

What remains is a real signal. The expert, which reads the world and tests
reachability the same way the layer does, is overridden 2.2 percent of the time,
and that residue is objects crossing the boundary between the proposal and the
check. The trained policy is overridden twelve times more often than that,
because it regresses a pick point from pixels and its points land outside the
workspace.

The layer is doing less work than the v1.0.0 numbers suggested, and what it
still catches is the model rather than the world.

## Reproducibility

Every configuration ran twice during this step, once at three seeds and once at
twenty-four. At twenty-four seeds the run was repeated after a change to the
evidence pack, and the accuracy of all three configurations was identical to the
digit: 92.8%, 17.7% and 12.9%. Latency differed between the two runs, which is
wall-clock time on a shared machine and is expected to.

The evidence pack at `runs/benchmark/benchmark.json` carries the seeds, the
benchmark configuration digest, the world configuration digest, the machine, the
library versions, the per-class support and every gate outcome, so a number can
be traced to what produced it without this package.

## What a human has to check before any of this touches hardware

Nothing in this repository has run on hardware, and the list below is not a
formality.

1. **Nothing here executes a pick.** The entire motion half of the problem is
   unexercised: no grasp, no placement, no collision with a real object, no
   recovery from a failed grasp.
2. **The workspace envelope is a sphere intersected with a box.** It
   over-permits near the edges of reach. A real installation needs the solved
   workspace of the installed arm, not this bound.
3. **The safety layer has never been tested against a real actuator limit.** It
   checks a proposed point against configuration; it does not read an encoder,
   a torque, or a limit switch.
4. **Every timestamp is the local monotonic clock.** A consumer on another
   machine cannot interpret one. A real line with more than one computer needs a
   time reference this contract does not have.
5. **No model here is fit to route material.** At 17.7% against a constant's
   18.5%, sending this to a real channel would contaminate every bale.
6. **The classifier has never seen a photograph.** It trained on 240 frames of
   parametric primitives. [ZeroWaste](corpus-ingestion.md) is fetched and
   measured and nothing has trained on it.
7. **Nothing tracks.** Object identity comes from the simulator. A real line
   needs a tracker, and every identity-dependent number here assumes one that
   does not exist.

## What v1.0.0 means, and what it does not

It means the pipeline runs end to end in simulation and that one command
reproduces the comparison from a seed and a manifest. Every stage exists: a
taxonomy, a world, a data pipeline, trained candidates, a validation harness, a
runtime with a safety layer, a published contract on ROS 2, and this benchmark.

It does not mean any of it works well. The most useful thing this release
produces is a measured statement of how far a trained CLAVE is from a usable
one, and the distance is large: from 17.7% to a gate at 80%, with an untrained
localization stage, no tracker, and nothing that picks.

## What would move the numbers

Named in the order of expected effect, from what the measurements here support.

**Train on real imagery.** ZeroWaste is fetched, digested and mapped: 4,503
images, 26,766 annotated regions, on an operating recovery-facility conveyor.
Every model in this table trained on parametric primitives, which teaches shape
and not material.

**Get a localizing detector into the loop.** `faster-rcnn-mobilenetv3` trains
and runs and is not in this table, because turning a pixel box into a world pick
point needs a camera model CLAVE has not built. That is the single missing piece
between a detector and a pick point, and building it would also give the pick
policy a target it does not have to invent.

**Fix the expert before imitating it again.** The teacher proposes objects that
cannot be reached, so the demonstrations every policy learned from contain picks
that could never have executed. A reachability test that accounts for lateral
placement would change the training signal, not just the benchmark.

**An accelerator.** [v0.4.0](model-candidates.md) rejected four architectures on
measured cost on this machine. All four are ordinary choices on a machine with a
CUDA GPU.
