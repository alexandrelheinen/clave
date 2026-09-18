# The validation protocol, and the gates it applies

This document states how a candidate is scored and what counts as passing. Both
halves are written before any candidate exists, which is the point: a threshold
chosen after seeing a result describes that result instead of gating it.

**No candidate has been trained, and no accuracy figure in this repository is a
measurement.** The harness computes metrics from recorded outcomes, and the only
records it has been exercised on are synthetic fixtures built inside the test
suite. Every threshold below is a target somebody chose or a budget somebody
derived, and none of them has met a real distribution.

## What the harness is

A scorer. It takes a list of records, one per object presented to the system,
computes metrics, compares each against a threshold read from
[configs/validation/gates.yml](../configs/validation/gates.yml), and prints a
report whose first section says what was scored and whose second says what that
means.

It trains nothing, loads no checkpoint, and steps no simulator. Every metric is
a pure function of the records, so a number in a report can be rechecked by
reading the records and the function beside each other, on a machine with no
GPU.

Run it with:

```bash
clave validate-run --outcomes <records.json>
```

The command exits non-zero when any gate is unmet.

## What a record means

A record describes an object that entered the arm's reachable window. An object
that never entered the window is outside the boundary, because nothing could
have been done about it.

| Situation | Counted as |
| --- | --- |
| Grasped, and placed in the channel its true class belongs in | Correct route, and a successful pick |
| Grasped, and placed in the reject channel while its class has a material channel | Reject, and a successful pick |
| Grasped, and placed in a different material channel | Misroute, and a successful pick |
| Left the window untouched | Missed pick, and no routing outcome at all |

The split in the last two rows is the one
[docs/waste-taxonomy.md](waste-taxonomy.md) asks for. A missed pick is a
throughput loss, since the line does not stop and the object continues to
whatever the end of the belt does with it. A misroute contaminates a bale. They
have different causes and different fixes, so counting them together tells
nobody which to work on.

A reject sits between the two: the material is not recovered, and no bale is
contaminated. It gets its own count rather than being folded into either
neighbor.

The record type is a placeholder. v0.6.0 owns rollout capture and its format
supersedes this one. The metric functions read named fields and never open a
file, so the handover replaces one reader rather than rewriting the metrics.

## What is measured

**Classification.** A confusion matrix over all eleven taxonomy classes, plus
per-class accuracy. A class with no records reports as unmeasured rather than as
accurate, and an object for which nothing was predicted is counted apart from
one predicted wrongly, since a model that abstains and a model that guesses
wrong call for different responses.

**Generalization.** Accuracy over object instances seen during training is
computed separately from accuracy over instances never seen, and the drop
between them is its own number.

**Picking and routing.** Presented, picked, missed, correct routes, rejects, and
misroutes, with every rate taken over the objects presented so they share one
denominator. The end to end sorting rate, meaning objects both picked and
correctly routed, is reported beside the pick success rate rather than instead of
it, because one falls when the grasp fails and the other when the classification
does.

**Timing.** Decision latency, meaning frame to published decision, and cycle
time, meaning decision to placement. Both are summarized at the median, the 95th
and the 99th percentile, with the sample count attached. The tail is what
matters: a pipeline that averages well and misses one object in a hundred drops
that object on the floor.

**The three named confusions.** Reported individually rather than folded into
general error, which is what the taxonomy asks of this step.

| Id | Name | Classes | Why a color camera cannot separate them |
| --- | --- | --- | --- |
| `CONF-01` | Transparent resins | `M-01`, `M-03`, `M-04` | Clear PET, clear PP and clear PS share color and shape; a facility separates them by near-infrared absorption |
| `CONF-02` | Can metals | `M-05`, `M-06` | An aluminum beverage can and a steel food can are both cylindrical metal; a facility separates them magnetically |
| `CONF-03` | Fiber flute | `M-08`, `M-09` | The flute that distinguishes corrugated board from paperboard is visible edge-on and invisible face-on |

Each one reports the group's record count, how many were predicted as another
member of the same group, and how many were wrong in some other way. The last
number is there so a low confusion rate on a group that is wrong most of the
time cannot read as a success. Every one of these records is also counted in the
general matrix, so naming a confusion removes nothing from the aggregate.

## The percentile method

Nearest rank: the value at index `ceil(fraction * count) - 1` of the sorted
series. The result is a sample the system actually produced rather than an
interpolation between two of them, and stating the method once removes the class
of argument where two tools disagree about p99 by a millisecond.

The sample count travels with every percentile, because p99 over eleven samples
is the maximum wearing a percentile's name.

## The gates

Every threshold lives in
[configs/validation/gates.yml](../configs/validation/gates.yml). Nothing in the
Python carries a numeric default, and a missing key fails at load naming itself,
so moving a gate means editing a file that shows up in a diff.

| Gate | Threshold | Basis |
| --- | --- | --- |
| `overall-accuracy` | at least 0.80 | Target. Chosen before any run |
| `per-class-accuracy:M-NN`, one per class | at least 0.60 | Target. Below the aggregate because a rare class carries fewer records and the named confusions concentrate their damage |
| minimum class support | 30 records | At thirty records one error moves accuracy by 3.3 points, which is the coarsest resolution worth calling a measurement |
| `pick-success-rate` | at least 0.90 | Target |
| `misroute-rate` | at most 0.05 | Target. Tighter than the pick gate because a misroute contaminates a bale while a missed pick costs one pick |
| `named-confusion:CONF-NN`, one per confusion | at most 0.35 | Target. Looser on purpose, see below |
| `decision-latency-p99` | at most 0.45 s | Derived from the 1.13 s per-object budget and the 391.7 ms perception latency in [measurements.md](measurements.md) |
| `cycle-time-p99` | at most 1.13 s | Derived: the reachable window divided by the fastest configured belt speed |
| `generalization-drop` | at most 0.10 | Target. A candidate that only memorized shows a large positive drop |

Two properties of the gate set are worth stating plainly.

**An unmet gate is a failure, not a number.** The command exits non-zero, the
report says which gates were unmet and by how much, and no summary line reports
a metric without its threshold beside it.

**A class nobody tested does not pass.** A class with fewer records than the
minimum support fails its gate as unmeasured. Without that rule a run covering
three classes would clear eight gates on empty denominators, which is the quiet
way a report becomes untrue.

The named confusion gate is looser than the per-class accuracy gate
deliberately. These three separations are unavailable from a color image, so the gate asks whether the
model is worse than the sensor limit rather than whether it is perfect.

## What this does not prove

**Nothing about any model.** No candidate has been trained, so the harness has
scored no real run. The fixtures in the test suite exist to prove the arithmetic
and the failure paths, and they are labeled as fixtures in the provenance field
every records file carries.

**Nothing about the thresholds.** The two timing gates rest on the sorting
world's 1.13 second budget, which that document derives from link geometry rather
than from a solved workspace and calls an upper bound. The accuracy gates rest on
nothing measured at all. First contact with a trained candidate is expected to
move at least one of them, and moving one is a spec change.

**Nothing about the reject threshold.** The taxonomy defers the confidence
threshold behind the reject channel to this step. It is a property of a trained
model's confidence distribution, which does not exist, so the harness counts
rejects and reports the rate while the gate on it waits for a model.

**Nothing about cycle time comparability.** The harness trusts the cycle time in
the record and does not check that it was measured between the same two events
across candidates. That becomes the benchmark's problem when it compares them.
