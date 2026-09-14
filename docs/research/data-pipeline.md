# The data pipeline, and two bugs it found

> Roadmap step: v0.6.0 · Spec: [.kiro/specs/data-pipeline/](../../.kiro/specs/data-pipeline/)

This step turns the simulated world into datasets v0.7.0 can train on and
v0.8.0 can score. It records rollouts as frames paired with the labels the world
already holds, partitions them so nothing leaks, reports what the result
contains, and resolves each dataset by digest.

Building it exposed two defects in the world delivered at v0.5.0. Both were
silent, and one of them would have produced a dataset of entirely black images
that trained without complaint.

## What a recorded dataset contains

A first dataset, recorded from the shipped configuration at seed 0:

| Property | Value |
| --- | --- |
| Rollouts | 6 |
| Examples | 240 frames at 320 by 240 |
| Split | 160 train, 40 validation, 40 test, partitioned by rollout |
| Material classes present | 8 of 11 |
| Material classes absent | `M-04`, `M-09`, `M-11` |

Measured per-class instance counts:

| Class | Instances |
| --- | --- |
| `M-01` PET | 312 |
| `M-02` HDPE | 264 |
| `M-03` PP | 221 |
| `M-05` Aluminum | 182 |
| `M-06` Ferrous | 153 |
| `M-07` Glass | 130 |
| `M-08` Cardboard | 109 |
| `M-10` Beverage carton | 91 |

These are counted from the examples present, never from what the configuration
requested. Two facts follow that a reader should not have to derive.

**Three classes have no instances at all.** The world's object set covers eight
of the taxonomy's eleven, so `M-04`, `M-09` and `M-11` will appear as columns of
zeros in any confusion matrix computed from this data. That is an absence in the
data, not a failure of a model, and v0.8.0 cannot tell the difference unless
somebody writes it down.

**The classes present are imbalanced by a factor of three.** `M-01` appears 312
times and `M-10` 91 times. The cause is mechanical rather than interesting: the
object pool cycles through the declared set in order, so objects spawned earlier
are visible in more frames. A model trained on this without reweighting will
learn the prior along with the task.

## The two bugs

### Every frame was black

The overhead camera was created with the quaternion `[0, 1, 0, 0]`, a 180 degree
rotation about the x axis. That reads as "point it downward" and does the
opposite: a MuJoCo camera already looks along its own negative z, so an identity
orientation at height points straight down, and rotating it aims it at the sky.

The first dataset recorded 240 frames whose every pixel was zero. Nothing failed.
The physics ran, the labels were correct, the digests computed, the splits
partitioned, and the composition table looked entirely reasonable. The only
symptom was a test asserting that two different seeds produce different frames,
which failed because all frames were identically black.

A model trained on that dataset would have converged to predicting the class
prior and reported a plausible-looking accuracy.

### Objects rolled off the belt

Object positions in the recorded labels showed lateral coordinates beyond the
belt's own half width, and heights below its surface. Cylinders landing from a
drop tip over and roll, and the belt had no side guides.

This did not fail anything at v0.5.0, because the tests there asked whether
objects entered the reachable window and enough of them did. It would have
degraded the dataset quietly: fewer objects reaching the arm, and labels
recording positions off the belt as though they were on it.

The belt now has side guides, which a real sorting line has anyway. After the
fix, zero recorded labels sit off the belt or below its surface.

Neither bug contradicts anything v0.5.0 claimed. The reachable window, the belt
speed and the 1.13 second time budget are geometry and are unaffected. What
changed is that more objects now survive to reach the window.

## Design decisions worth knowing

**Splits partition by rollout, never by frame.** Two frames of one object half a
second apart are almost perfectly correlated. A frame-level split would put near
duplicates on both sides of the train and test boundary and inflate every number
computed afterwards, leaving no trace a reader could spot. The split verifies
that no rollout appears twice and fails rather than reporting a leak.

**Composition is measured, not requested.** The counts above come from the
examples present. A pipeline that reported the proportions its configuration
asked for would have described the black dataset exactly as it describes this
one.

**Datasets resolve by digest and are never committed.** Two training runs can be
shown to have seen the same bytes. Flipping one byte of one archive makes the
read refuse.

**Labels come from the simulator.** The world knows each object's material class,
so an example is labeled by construction and the usual source of label noise does
not arise. The cost is appearance: these are parametric primitives, so a
classifier trained only on them learns shape rather than material.

## The scripted expert

Imitation learning needs a teacher, and this is it: among the objects currently
inside the reachable window, it takes the one nearest the exit, because that one
has least time remaining. It resolves the channel from the material class through
the taxonomy, and it emits nothing when nothing is reachable rather than a
decision naming nothing.

It is deliberately simple. If a learned policy matches it exactly, that says the
imitation worked, not that the behavior is good.

## What is not proven

**No corpus has been fetched.** The ingestion path exists, applies the taxonomy's
corpus mappings, records an ambiguity when a label spans several classes, and
keeps an unmapped label rather than discarding it. It has been exercised against
a fixture and never against ZeroWaste, TACO or SpectralWaste. Its first real test
comes when an operator downloads one and records its digest through the manifest.

**No held-out set of real imagery exists**, for the same reason. The gap between
simulated primitives and photographs therefore remains unmeasured, and it is the
largest unknown standing between this pipeline and a model that works on a real
line.

**Nothing was trained.** No accuracy is claimed anywhere in this document. The
only numbers here are counts and measurements of what was recorded.
