# Plan for probabilistic sorting

Status: phases 1 through 7 are settled. The channel decider loads
the reasoned cost default when `routing.rule` is `expected_cost`.
`clave estimate-belief` writes prior and sensor counts from a count
log and does not edit the cost file.
`configs/debug/expected-cost.yml` selects `expected_cost` and names
that default. `clave sim` reads it only when `--routing` points at a
file. Phase 7 keeps the shipped rule on `confidence_floor`. An
operator opts in.

The specification is
[docs/spec/probabilistic-sorting.md](../spec/probabilistic-sorting.md).

Each phase is one change, with its own review. A phase does not begin by
borrowing unfinished work from the next one. Acceptance criteria cite the
ids in the specification. Those ids are append-only.

The line's behavior does not change in phases 1 through 3. Phase 4 is the
first one that can change a channel, and only when `routing.rule` is
`expected_cost`. The default stays `confidence_floor`. An operator opts
in.

## Phase 1. Pin GTSAM and lock the chapter's arithmetic

Add `gtsam==4.3.0` as an optional extra. The core dependency list stays as it is. Record
the BSD license next to the pin. Resolve it with `uv lock` so the wheel
and numpy land in `uv.lock` together. Repeat the import against that
resolution. The check on 13 October 2026 used numpy 2.5.4, while the lock
at that date recorded numpy 2.2.6, so this phase is where those two meet.

Add a test module that calls `DiscreteDistribution`, `DiscreteConditional`,
and `DecisionTreeFactor` the way sections 2.1, 2.4, and 2.5 do.

The fixture covers:

- Prior counts `200/300/250/200/50` normalize to 0.20, 0.30, 0.25, 0.20,
  0.05.
- Prior-only expected costs are 3.2, 0.6, 3.4, and 1.0, and the minimizing
  action is the metal bin.
- The posterior `(0.2, 0.3, 0.1, 0.1, 0.3)` minimizes at the nop.
- Conductivity false, multiplied by the prior and normalized, matches
  0.331, 0.497, 0.042, 0.050, 0.079 to three decimal places.
- Weight 50 g, conductivity false, and a cardboard detection yield a
  posterior of about 0.757 on cardboard and 0.235 on scrap metal.

The fixture lives under `tests/` and is skipped when the extra is absent,
except on the gate. The gate installs the extra. `./scripts/validate.sh`
is the place that install is added, so a machine running the gate cannot
skip the fixture in silence.

No module under `src/clave` imports `gtsam` in this phase. The runtime,
the router, and the fusion fold are untouched.

`gtbook` is not installed. `gtbook==0.0.41` cannot be, on Python 3.12.
`gtbook==0.0.38` waits for the optional inspection extra in phase 2, and
only if a notebook is actually added. This phase adds neither.

**Acceptance.** `AC-SORT-10`, `AC-SORT-11`, `AC-SORT-19`, `AC-SORT-20`.

**Stops.** No posterior builder, no configuration keys, no proposal
fields.

## Phase 2. Build CLAVE's posterior with the same types

Add a module whose only job is the product in `AC-SORT-01`. It owns the
GTSAM keys. Callers pass probabilities and counts. They never see a key.

Load `prior_counts` and discrete sensor tables from routing configuration
when the rule is `expected_cost`. Refuse a missing key by name
(`AC-SORT-03`). The `confidence_floor` path does not read those keys
(`AC-SORT-21`).

Apply the existing posterior floor after normalization (`AC-SORT-22`).
A test feeds the chapter's 50 g Gaussian, which underflows paper and can
to zero, and shows the floor lifts those entries.

Keep `Detection` and `Height` out of the product. Keep the code
down-weight: a test with a sharp visual belief shows the code factor
moves the posterior less than the same factor on a flat belief.

Wire a mass factor only behind the function `AC-SORT-04` describes, and
do not call it from the runtime (`AC-SORT-05`, `AC-SORT-06`). Shipped
configuration has no conductivity table and no mass table.

Compare the builder to a small hand-computed product of two categorical
likelihoods, independent of the book's numbers, so a bug that satisfies
the fixture and fails on twelve outcomes still has a test (`AC-SORT-01`).

Optional: an extra named so that it cannot be confused with the runtime
extra, pinning `gtbook==0.0.38` and a bounded `kaleido`, used by nothing
on the proposal path (`AC-SORT-19`). Skip the extra if no notebook needs
it. Do not pin `gtbook==0.0.41`.

**Acceptance.** `AC-SORT-01`, `AC-SORT-03`, `AC-SORT-04`, `AC-SORT-05`,
`AC-SORT-06`, `AC-SORT-19`, `AC-SORT-21`, `AC-SORT-22`.

**Stops.** The proposal datagram is still version 1. The router still
sees a class and a confidence. Tracks in the simulator still fold beliefs
with the Python product they use now, until phase 3 switches the category
fold.

## Phase 3. Fold evidence as likelihoods

Connect the builder to a track's category belief.

A `Material` hard label becomes a row of the configured detector table,
scaled by the recency weight fusion already computes (`AC-SORT-02`). The
soft vector from the perception head is not that row. If the head is the
only source of a label, the hard label is its argmax, and the confidence
is the scale. Document that in the module, next to the loss, so a later
calibration has a place to land.

A `Code` payload becomes the existing `code_prior` vector, scaled by the
down-weight, then a `DecisionTreeFactor`.

`GroundTruth` still folds in simulation and is still refused when the
runtime is configured for hardware. The estimator in phase 5 is allowed
to read it from logs. The live fold does not start treating it as a
harmless sensor.

Run the existing fusion tests. Where the GTSAM product and the old
power-and-multiply disagree, the specification wins on the category
posterior, and the test is updated with the id it guards. Geometry,
association, and mass bands do not move.

**Acceptance.** `AC-SORT-01`, `AC-SORT-02`, `AC-SORT-05`, `AC-SORT-06`,
`AC-SORT-22`, and the fusion tests that already guard the floor, the code
down-weight, and the refusal of an unknown payload.

**Stops.** No channel changes. `WasteObject.material` remains the leading
class. The confidence floor still routes.

## Phase 4. Decide the channel by expected cost

The reasoned default from open question 1 is
[configs/routing/expected-cost-default.yml](../../configs/routing/expected-cost-default.yml).
This phase loads that file. It does not invent a second table. The
mechanism can be tested against the book's fixture and against
synthetic tables. The simulator's `routing.rule` does not flip in the
same change as the load. The shipped rule stays `confidence_floor`.

Bump the proposal contract to version 2 with a `posterior` field
(`AC-SORT-17`, `AC-SORT-18`). Version 1 stays valid for a runtime whose
rule is `confidence_floor`.

In `clave-routing`, compute the sum in `AC-SORT-07` in Rust from the
posterior and the cost table. Do not add a GTSAM crate (`AC-SORT-16`).
Refuse a table that prices residue below reject on any sorted channel
(`AC-SORT-09`). When reject wins, publish reject and keep the leading
class (`AC-SORT-08`).

Golden vectors for the decision contract stay valid. The new behavior is
a new vector, not an edited old one: a posterior whose mode maps to
channel 8, and whose expected cost selects a different sorted channel,
has to be representable. State that in the contract text so a consumer
is not surprised.

Measure the added latency from posterior construction through the
resolver on the development machine, and record it in
[measurements.md](../measurements.md) if it is going to be cited. Do not
cite it before that run.

**Acceptance.** `AC-SORT-07`, `AC-SORT-08`, `AC-SORT-09`, `AC-SORT-16`,
`AC-SORT-17`, `AC-SORT-18`, `AC-SORT-21`.

**Stops.** The default configuration remains `confidence_floor`. Phase 4
does not add the estimator. Phase 4 does not extend the narrative.

## Phase 5. Estimate tables from operational counts

`clave estimate-belief` reads a count log and writes `prior_counts` and
`sensor_cpts`. Image corpora and tracker evidence do not store a hard
sensor reading beside the ground-truth category, so the log format is
the count log in the specification. The command does not recover a
label from a video, and it does not parse a motion log.

Pseudo-count is 1 per cell (`AC-SORT-12`). A mass series stores the
sample mean and the unbiased variance (`AC-SORT-13`). One mass sample
has no unbiased variance, and the command refuses it. The command
refuses a checkpoint path and the cost file (`AC-SORT-14`).

A failed grasp, an override, and a collision are not rows
(`AC-SORT-15`).

A synthetic sensor with a known conditional is an estimator test. After
the pseudo-count, on a sample large enough that the pseudo-count is not
the dominant term, the recovered table sits closer to the generating
table than a uniform table does. That result is about the estimator.

**Acceptance.** `AC-SORT-12`, `AC-SORT-13`, `AC-SORT-14`, `AC-SORT-15`.

**Stops.** The command does not launch `clave sim` and does not change
`routing.rule`. A count estimate enters the cost cells only through a
reviewed edit of the reasoned default.

## Phase 6. Close the loop in simulation

Select `expected_cost` for a debug configuration that names the reasoned
default. Leave the shipped runtime file on `confidence_floor`. Open
question 2 keeps that default unless an operator opts in.

Extend the simulation narrative with one line per routing decision: the
leading class, the chosen channel, and the expected cost of that channel.
Heartbeat logs stay off the terminal, as
[simulation-narrative.md](../requirements/simulation-narrative.md)
already requires.

On one seed, run the same arrivals under both rules. Record where the
channels differ. The interesting difference is an object the confidence
floor would sort, and expected cost would reject or divert, because the
cost of the likely mistake outweighs the cost of the nop. If the reviewed
table cannot produce that difference, say so in the run notes. Do not
tune the table until it does.

When this phase changes routing behavior, run the 30 second simulation
the repository asks for after algorithm work, with video, under
`runs/debug/` and the pull-request identifier. The video is evidence for
that phase's review. This planning document does not stand in for it.

**Acceptance.** A debug run under `expected_cost` emits the decision line,
`AC-SORT-08` holds on that run's rejects, and the paired-rule comparison
is in the run folder. `AC-SORT-21` still holds for the default
configuration.

**Stops.** Deleting `confidence_floor` is not part of this phase.

## Phase 7. Retire the floor, if the review says so

The review keeps the floor.

The phase 6 run is seed 0, 30 simulated seconds, ground truth, and
`configs/debug/expected-cost.yml`. Six arrivals. The confidence-floor
chute and the expected-cost chute match on each of them: HDPE, mixed
paper, ferrous, HDPE, other plastic, mixed paper. The printed expected
costs are 0.028, 0.029, 0.024, 0.028, 0.025, and 0.029. The reasoned
default prices a correct placement at 0 and reject at 2, so a class
spike still minimizes on the mapped channel. That run rejected nothing
and misrouted nothing. The cost table was not edited.

Removing `Resolver`'s confidence comparison, the `confidence_floor`
key, and version 1 of the proposal would retire `AC-SORT-21`. That
deletion needs new ids, written before the code, and this review does
not spend them. `AC-SORT-07` through `AC-SORT-09` and `AC-SORT-21`
still hold. The shipped file stays on `confidence_floor`.

## What this plan will not do

It will not replace the tracker, the arm, or the safety checks. It will
not copy the five textbook categories into the taxonomy. It will not
train a policy by counting, and it will not put GTSAM in the Rust
workspace. It will not vendor `gtbook/robotics`.

## Order

Phase 1 has no predecessor. Phase 2 depends on the pin. Phase 3 depends
on the builder. Phase 4 depends on the builder and on a reviewed cost
table, and it can be developed against synthetic tables in parallel with
phase 3 once phase 2 has landed. Phase 5 depends on the file format from
phase 2 and can proceed without phase 4. Phase 6 depends on phases 3, 4,
and the reviewed table. Phase 7 depends on phase 6 and on the default
decision.

An implementer who reaches phase 4 without a cost table stops at the
synthetic tests and leaves the simulator on `confidence_floor`.
