# The data pipeline, and two bugs it found

> Roadmap step: v0.6.0 · Spec: [.kiro/specs/data-pipeline/](../../.kiro/specs/data-pipeline/)

> **The geometry in this document was superseded at v1.0.1.** The belt, the arm
> offset, the reach radius, the belt speed and the object sizes were all
> rescaled after a solved workspace sweep found the manipulator could not reach
> the middle of its own belt and its gripper could not close on any object in
> the set. [world-scale.md](world-scale.md) carries the measurements and the new
> values. What this document records is what was measured at the time, and it is
> left standing rather than rewritten.


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

## Pixel boxes, added at v0.6.1

The first release recorded each object's world position and nothing about where
it appeared in the image, which left detectors untrainable: v0.4.0's advancing
detector needs pixel bounds and the dataset had none.

Boxes now come from a segmentation render, where MuJoCo reports a geometry id
per pixel. They are ground truth rather than a projection estimate, and an
object absent from the render is simply absent from the result.

That second property turned out to matter more than the boxes. The camera sees
roughly half the belt, so **about 18 percent of labeled objects are not in the
frame at all**. The first release could not distinguish them, and a detector
trained on those labels would have been taught to predict a box where there are
no pixels. An example now exposes its visible labels separately, and detection
training must use those.

## Proprioception, added at v0.6.2

v0.5.1 made the manipulator movable. This makes it move during recording, driven
toward whatever the scripted expert would pick, and records its four joint
angles on every captured frame.

Without the arm moving, proprioception would be a constant and carry no
information, so the two changes only mean something together.

Policies trained after this receive arm state rather than a zero vector.
Retraining on a freshly recorded dataset gives:

| Candidate | Vision only, v0.7.0 | With proprioception |
| --- | --- | --- |
| `behavior-cloning-baseline` | 0.0332 to 0.0094 | 0.0416 to 0.0137 |
| `act` | 30.07 to 4.65 | 29.11 to 4.49 |

**Those columns are not comparable and neither is evidence of anything.** The
dataset was re-recorded, and because the arm now moves and collides with objects
on the belt, the trajectories themselves differ. Behavior cloning ends higher
with proprioception than without, which says nothing about whether the extra
input helps: three epochs on 160 frames is not a measurement, and two different
datasets cannot be compared by their losses.

What can be said is narrower and worth saying: the observation now contains the
arm's state, so a policy that needs it is no longer structurally prevented from
using it, and a reward-driven candidate now has an environment it can act in.
Whether either helps is v1.0.0's benchmark to answer.

An example recorded before this, or any real photograph, carries no
proprioception. Its state is zeroed rather than dropped, so simulated and real
examples stay mixable in one batch.

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

**Nothing here was measured against a photograph.** The ingestion path applies
the taxonomy's corpus mappings, records an ambiguity when a label spans several
classes, and keeps an unmapped label rather than discarding it, and the
fixtures that prove it were written to match a table in a document. TrashNet and
ZeroWaste were fetched later and are measured in
[corpus-ingestion.md](corpus-ingestion.md); the dataset this document describes
holds neither of them.

**No held-out set of real imagery exists.** The gap between simulated primitives
and photographs therefore remains unmeasured, and it is the largest unknown
standing between this pipeline and a model that works on a real line.

**Nothing was trained.** No accuracy is claimed anywhere in this document. The
only numbers here are counts and measurements of what was recorded.
