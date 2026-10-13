# Probabilistic sorting

Status: phases 1 through 3 of the plan are the implementation this
document covers. The reasoned cost default is recorded below. The
channel change and the estimator stay open.

The phased work is
[docs/plan/probabilistic-sorting.md](../plan/probabilistic-sorting.md).
Phases 4 through 7 stay gated on wiring that default into the resolver
and on an explicit later change of the routing rule. The default rule
stays `confidence_floor`.

This follows the spec-anchored bar in
[.guidelines/workflow/sdd.md](../../.guidelines/workflow/sdd.md): an
architecture change, written down so the disagreement happens here.

## Intent

CLAVE already names a material class and a confidence, then sends the object
to the channel that class maps to, or to reject when the confidence is below
a floor. That rule treats the leading class as if it were known, and it
treats every mistake as equal. A scrap-metal object placed with the paper
does more damage than paper placed with the metal, which is the case
chapter 2 of Dellaert and Hutchinson is written to make precise.

This specification says how that chapter's sense, think, and act loop lands
in CLAVE: a probability over the taxonomy, sensor models as conditional
distributions, and a channel chosen by expected cost. The geometric pick,
the safety envelope, and the learned pick timing stay where they are.

## Scope

**In scope:**

- The category of one tracked object, as a distribution over `M-01` through
  `M-11` and `reject`.
- Sensor models for evidence CLAVE already has, and the posterior formed
  from them with GTSAM's discrete types.
- The channel decision, as the action of minimum expected cost, checked in
  Rust from the operator's cost table.
- An offline estimate of the prior and of those sensor models from labeled
  operational counts.
- A regression fixture that repeats the arithmetic in the chapter, so the
  library pin is doing the calculation the chapter does.

**Out of scope:**

- Motion, grasping, cycle time, and the safety envelope. The chapter
  assumes the arm places the commanded object in the commanded bin with no
  error. CLAVE does not, and this work does not adopt that assumption.
- Which object to pick, and when. Several objects share the belt. The
  scripted expert and the behavior-cloning policy keep that choice.
- The book's five category names and three bins as a replacement for
  [waste-taxonomy.md](../waste-taxonomy.md). They appear only inside the
  regression fixture.
- A conductivity probe, a scale, or any other sensor the cell does not
  have. The interface admits a new factor later. This specification adds
  none.
- SLAM, pose graphs, and the rest of GTSAM. The dependency is the discrete
  layer the chapter imports.
- Vendoring the chapter's notebooks, or copying their prose. The code cells
  are BSD. The prose is not licensed for redistribution.
- Reinforcement learning. The chapter's learning section estimates
  probability tables by counting. Pick timing stays supervised imitation.
- Raising the Python baseline from 3.12 to 3.13.

## The chapter

Chapter 2, "A Trash Sorting Robot," in Frank Dellaert and Seth Hutchinson,
*Introduction to Robotics and Perception*. The text and the notebooks were
read from `gtbook/robotics` commit `a0a07de9` (10 September 2026). The
rendered pages are:

| Section | Page | Notebook |
| --- | --- | --- |
| 2 introduction | [S20](https://www.roboticsbook.org/S20_sorter_intro.html) | `S20_sorter_intro.ipynb` |
| 2.1 state | [S21](https://www.roboticsbook.org/S21_sorter_state.html) | `S21_sorter_state.ipynb` |
| 2.2 actions | [S22](https://www.roboticsbook.org/S22_sorter_actions.html) | `S22_sorter_actions.ipynb` |
| 2.3 sensors | [S23](https://www.roboticsbook.org/S23_sorter_sensing.html) | `S23_sorter_sensing.ipynb` |
| 2.4 perception | [S24](https://www.roboticsbook.org/S24_sorter_perception.html) | `S24_sorter_perception.ipynb` |
| 2.5 decision | [S25](https://www.roboticsbook.org/S25_sorter_decision_theory.html) | `S25_sorter_decision_theory.ipynb` |
| 2.6 learning | [S26](https://www.roboticsbook.org/S26_sorter_learning.html) | `S26_sorter_learning.ipynb` |
| 2.7 summary | [S27](https://www.roboticsbook.org/S27_sorter_summary.html) | `S27_sorter_summary.ipynb` |

The introduction sets the loop. An item arrives. Its category is the state.
The action is the bin, or a nop that lets the item pass. Sensors measure
the item. Perception turns those measurements into a distribution over
categories. The action is the one with the lowest expected cost under that
distribution. Counts from operation replace the tables the chapter started
with. The loop repeats for the next item.

Section 2.1 defines the state as one discrete random variable, `Category`,
with outcomes cardboard, paper, can, scrap metal, and bottle. The prior
comes from counts `200/300/250/200/50`, which normalize to 0.20, 0.30,
0.25, 0.20, 0.05. The chapter assumes every item is one of those five.

Section 2.2 defines four actions: glass bin, metal bin, paper bin, and
nop. The cost of action `a` in category `c` is a 4 by 5 table. Correct
placements cost 0. The nop costs 1 for every category. Putting scrap metal
in the paper bin costs 10, and putting paper in the metal bin costs 1. With
only the prior, the expected costs are 3.2, 0.6, 3.4, and 1.0, so the
metal bin wins. One sentence in section 2.2 swaps the cardboard and paper
probabilities. The table, the count string, and the expected-cost
arithmetic agree with each other, and the fixture follows them.

Section 2.3 models three sensors. Conductivity is binary, with
`P(true | can) = 0.9` and a conditional probability table
`99/1 99/1 10/90 15/85 95/5` in category order, false then true. A camera
detector reports bottle, cardboard, or paper, including for categories it
was not trained to name, where it is close to uniform. Weight is continuous,
a Gaussian per category, in grams: means and standard deviations
`(20, 10)`, `(5, 5)`, `(15, 5)`, `(150, 100)`, `(300, 200)`.

Section 2.4 builds a likelihood factor from each reading. A likelihood
scores categories for a fixed reading, and summing it over categories does
not produce 1. The posterior is proportional to the
product of the likelihoods and the prior, under conditional independence of
the sensors given the category. The maximum a posteriori category maximizes
that posterior. The action is chosen later, from expected cost.

Section 2.5 chooses the action by minimizing expected cost under the
posterior. With the posterior `(0.2, 0.3, 0.1, 0.1, 0.3)` the expected
costs are 2.0, 1.1, 2.4, and 1.0, and the nop wins even though paper and
bottle lead the posterior together. Minimizing the worst-case cost collapses
to the nop for every item. Choosing the mode of the prior ignores cost.

Section 2.6 estimates a discrete distribution by normalized counts, with a
pseudo-count of 1 on every bin when data are sparse. A discrete sensor
model is the same count, grouped by the conditioning category. A Gaussian
takes the sample mean and the unbiased sample variance, the divisor `N - 1`.

Section 2.7 restates the loop and records the distinction between a
probability mass function and a density. A continuous reading assigns no
probability to a single number. The Gaussian enters as a density, evaluated
at the measured weight, which is what makes it a likelihood factor on the
discrete category.

## Packages

The chapter's software exists and installs. Checked on 13 October 2026
against Python 3.12.3 on x86_64.

| Package | Pin | License | What CLAVE uses |
| --- | --- | --- | --- |
| `gtsam` | `4.3.0` | BSD, the simplified form | `DiscreteDistribution`, `DiscreteConditional`, `DecisionTreeFactor`, `DiscreteValues` |
| `gtbook` | `0.0.38`, optional extra only | Apache-2.0 | `gtbook.discrete.Variables`, and `gtbook.display` for a notebook |
| `gtbook` | `0.0.41` | Apache-2.0 | Not used. Requires Python `>=3.13` |

`gtsam` 4.3.0 is the current stable upload on PyPI. It publishes a
`cp312` wheel, `gtsam-4.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64`,
about 32 MB. Importing that wheel and running the chapter's constructors
produced the prior `(0.2, 0.3, 0.25, 0.2, 0.05)`, the prior-only expected
costs `(3.2, 0.6, 3.4, 1.0)`, a conductivity-false posterior whose paper
entry is about 0.497, and a three-sensor posterior of about 0.757 on
cardboard and 0.235 on scrap metal. The chapter describes those last two
as almost 50 percent, and as 76 percent and 23 percent.

`gtsam` 4.2 has no `cp312` wheel, so it is not a candidate on this
baseline. The book's own `environment.yml` asks for Python 3.13 and
`gtbook>=0.0.41`, which pulls `gtsam>=4.3a2`. That helper release does not
install on Python 3.12. `gtbook` 0.0.38 does install, and its `Variables`
helper accepts the same `DiscreteDistribution` constructor. `Variables` only
names keys for display. The arithmetic is GTSAM.

`gtsam` 4.3.0 declares `pytest>=9.0.1` as a runtime requirement. Production
code does not import pytest. The declaration is still a packaging defect,
and the extra that pins `gtsam` inherits it.

The notebooks live in [gtbook/robotics](https://github.com/gtbook/robotics).
Their README, at the same commit, puts the code cells and the `.py` files
under BSD and reserves the prose, including the markdown cells. CLAVE
depends on the libraries. It does not copy the notebooks in.

GTSAM's pose graphs, incremental smoothing, and geometric types are not
part of this design. Rust still does not link a tensor library, and it
does not link GTSAM either. The expected-cost step is a matrix-vector
product. The chapter computes it with ordinary array multiplication after
GTSAM has returned a probability mass function.

## Mapping

| Chapter idea | CLAVE module |
| --- | --- |
| One category in the cell | One posterior per track, in `clave.tracker` |
| Prior over categories | Counts in routing configuration, loaded into `DiscreteDistribution` |
| Bin, or nop | Channel, or the reject channel, in `clave-routing` |
| Cost table | Operator configuration beside the channel map |
| Conductivity, detector, scale | Not copied. Material, code, and a mass reading when one exists, as likelihood factors |
| Likelihood factor | `DecisionTreeFactor` on the category key |
| Conditional probability table | `DiscreteConditional` |
| Posterior | `DiscreteDistribution` of the product, then the existing probability floor |
| MAP category | The leading entry of the posterior, reported, not acted on by itself |
| Minimum expected cost | `clave-routing`, recomputed from the posterior and the cost table |
| Counts, pseudo-counts, Gaussian fit | An offline estimator, writing the configuration the loader reads |
| Sense, think, act | Adapters, then the posterior, then routing and the safety envelope, then the arm |

The split in [architecture.md](../architecture.md) stays. Python perceives
and proposes. Rust checks and decides. GTSAM sits on the Python side of
the datagram, because that is where the sensor models are. The channel is
decided again in Rust, from the posterior and from a cost table the
proposer does not own, for the same reason a pick point is checked again
against the envelope.

### State

The sample space is `OUTCOMES` in `clave.tracker.fusion`: `M-01` through
`M-11`, then `reject`. The chapter's assumption that every item belongs to
the named categories does not hold here. `M-11` is residue, and `reject`
is the outcome for an object the line will not place in a sorted channel.

The prior is a count per outcome. The book's `200/300/250/200/50` is the
fixture. The line's prior is estimated from the categories the simulator
spawns, and later from labels on a real stream if one exists. A missing
count file fails at load, naming the key.

### Actions

An action is a channel id, including the reject channel. The chapter's nop
is that reject channel: the object continues, unsorted. Several classes
already share a channel. `M-08`, `M-09`, and `M-10` share channel 8 in
`configs/runtime/sitl.yml`. The cost table has one column per outcome and
one row per channel, so a shared channel is one row with a zero in more
than one column.

The published decision keeps a material class and a channel that are
allowed to disagree. They already disagree when confidence is low: the
class is kept and the channel is reject. Expected cost is a further reason
they disagree. The class on the decision is the leading posterior class.
The channel is the minimizing action.

### Sensors

CLAVE's evidence union is already the chapter's sensor list, with different
instruments. A `Material` payload is a reading about category. A `Code`
payload is a bill of materials, already turned into a likelihood by
`code_prior`. `Detection` and `Height` say where the object is and how
tall it is. They do not enter the category product. `GroundTruth` is a
label for learning and for simulation. A runtime configured for hardware
already refuses it as a sensor, and the estimator is the only new reader
of those labels.

The perception head is not yet a likelihood. Its training loss is
multilabel binary cross-entropy over a frame that may hold several
objects, as [architecture.md](../architecture.md) specifies. A vector
from that loss does not sum to one, and it is not `P(reading | category)`. Until a calibration says
otherwise, the discrete sensor model is a conditional probability table
from the hard label to the category, which is the chapter's detector, and
the head's confidence scales the factor the way `weight_of` already scales
a fold. A calibrated per-object vector can replace that table later. It
does not replace it in the first cut.

There is no conductivity sensor. Aluminum against ferrous metal is already
called out in [waste-taxonomy.md](../waste-taxonomy.md) as a separation a
color camera does not have. The cost table can make that confusion
expensive. Inventing a probe would pretend the measurement exists.

Mass on `WasteObject` is a band from density and footprint, and the
perception contract says a single number would invite trust the estimate
has not earned. That band is not the chapter's scale. The weight factor is
omitted unless a reading is an actual mass. The Gaussian parameters wait
in configuration for that reading.

### Perception

For one track, the unnormalized posterior is the product of the prior and
one likelihood factor per sensor that reported. GTSAM multiplies
`DecisionTreeFactor` values and normalizes by constructing a
`DiscreteDistribution`. Conditional independence given the category is the
assumption behind the product. A barcode and a camera that both read the
same printed label violate it. The code factor keeps the down-weight
already in `_fold_code`, confidence times one minus the leading
probability, so a sharp visual belief leaves the code little to move.

The probability floor in `FusionSettings` stays, applied after
normalization. A Gaussian density can evaluate to a numerical zero. With
the chapter's own weight model, a reading of 50 g drives the paper and can
entries to zero in the three-sensor product. A zero entry never recovers
under multiplication. The floor is the pseudo-count idea from section 2.6,
applied to the posterior. The stored counts get their own pseudo-count in
the estimator.

The maximum a posteriori class is what the decision reports as
`material_class`, with its probability as `confidence`. Routing does not
stop there.

### Decision

Let `cost(channel, outcome)` be the operator's table. For a posterior
`P`, the resolver chooses

```text
channel* = argmin over channels of sum over outcomes of cost(channel, outcome) * P(outcome)
```

Rust computes that sum. It does not call GTSAM. A table that makes any
sorted channel cheaper than reject for `M-11` is refused at load. The
taxonomy already requires residue on the reject channel, and expected cost
has to be unable to route around that.

The book's 4 by 5 numbers are the fixture and are not the line's costs.
Damage costs for this taxonomy have not been measured. The line's first
table is the reasoned default in
[configs/routing/expected-cost-default.yml](../../configs/routing/expected-cost-default.yml),
spelled out under [Reasoned default](#reasoned-default). It is not
loaded while `routing.rule` is `confidence_floor`. Phase 5 estimates
replace it. A zero on the mapped channel, a moderate reject cost, and
a higher cost on a damaging channel is the shape taken from the
chapter. Asymmetric pairs, such as aluminum against ferrous metal, are
why a later operator might leave the confidence floor.

While the confidence floor remains the configured rule, behavior of the
line does not change. The floor is removed only after a reviewed cost
table is the rule the runtime loads.

### Learning

The estimator reads pairs `(category, sensor reading)` whose category is a
simulation label or a later audit. It writes counts. A discrete table is
those counts plus one pseudo-count per cell, normalized by GTSAM when the
conditional is built. A Gaussian mass model, if a mass sensor is ever
configured, stores the sample mean and the unbiased variance.

The estimator does not run inside the control loop, does not change the
behavior-cloning checkpoint, and does not edit the cost table. A failed
grasp, a collision, or a safety override is not a category observation.
Those events have their own counters already.

### Sense, think, act

Sense. Adapters in `clave.tracker` turn a camera frame, a barcode, and any
later instrument into `Evidence`. The tracker associates evidence with a
track. That association is geometric today and is the learned tracker in
the v1.7.0 work. This specification does not replace it.

Think. Fusion builds the category posterior with the GTSAM product.
`clave-routing` minimizes expected cost. `clave-safety` still accepts or
overrides the pose.

Act. `clave.control` flies the visit and releases into the chute for the
resolved channel. The chapter's act step cannot fail. This one can, and
the failure stays out of the probability tables.

The next item is the next track that reaches a decision, not the next
solitary object in an empty cell.

## Interfaces

### Posterior

A posterior is 12 finite probabilities in `OUTCOMES` order, summing to 1,
each at least the configured floor after the floor is applied. The type
that holds it today is `Posterior` in `clave.tracker.fusion`. The GTSAM
key and the integer encoding do not cross a process boundary.

### Proposal, version 2

`crates/clave-safety/contract/proposal.md` gains one field and a version
bump. Version 1 remains the confidence-floor message. A runtime configured
for version 2 refuses a version 1 payload before reading further fields,
which is the rule the contract already states for an unknown version.

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer | `2` when the posterior is present |
| `posterior` | array of 12 numbers | `OUTCOMES` order, sums to 1 within an absolute tolerance of `1e-6` |
| `material_class` | string | First maximum among the eleven taxonomy weights |
| `confidence` | number | Probability of that class, within an absolute tolerance of `1e-5` |

The twelfth weight is the reject outcome. It is a cost column, not a class.
A posterior that peaks there still reports the best taxonomy class.

The pose, the window, and `object_id` are unchanged. If `material_class`
or `confidence` disagrees with `posterior`, the runtime refuses the
proposal. The channel is absent on purpose. Perception still does not
choose it.

### Routing configuration

`routing.rule` is `confidence_floor` or `expected_cost`.

Under `expected_cost` the posterior builder requires `prior_counts` and
`sensor_cpts`, and the channel decider requires `cost`.

- `prior_counts`, twelve positive numbers, `OUTCOMES` order.
- `sensor_cpts`, one table per discrete sensor in use. Each row is a
  category, each entry an unnormalized count, and a row must contain at
  least one positive count.
- `cost`, one row per channel id the map knows, one column per outcome.
  Costs are finite and greater than or equal to zero. The runtime JSON
  carries these rows. `routing.cost_file` names the file they are read
  from, or `routing.cost` carries them inline.

`confidence_floor` keeps today's keys and does not read the three tables,
even when a file contains them. A file that selects `expected_cost` and
omits a table fails at load, naming the key. The two rules do not blend:
expected cost does not also apply the confidence floor. A tie in expected
cost keeps the lowest channel id.

### Decision

`PickDecision` keeps its fields. `channel` comes from expected cost when
that rule is selected. `material_class` is the leading class. Consumers
that assumed the channel is the class's mapped channel, except in the
reject case, have to tolerate a sorted channel that is not the mapped
channel of the leading class. That is the behavior the cost table exists
to produce. The CBOR contract does not gain a posterior. No current
consumer reads one.

### Estimator

An offline command reads a log of labels and hard sensor outcomes, writes
the count files, and does not start the simulator. Its inputs and outputs
are files. It has no socket.

## Data

The book's fixture, stored with the tests and not loaded as the line:

| | cardboard | paper | can | scrap metal | bottle |
| --- | --- | --- | --- | --- | --- |
| glass bin | 2 | 2 | 4 | 6 | 0 |
| metal bin | 1 | 1 | 0 | 0 | 2 |
| paper bin | 0 | 0 | 5 | 10 | 3 |
| nop | 1 | 1 | 1 | 1 | 1 |

Prior counts `200/300/250/200/50`. Conductivity table
`99/1 99/1 10/90 15/85 95/5`. Detector table
`2/88/10 2/20/78 33/33/34 33/33/34 95/2/3`, columns bottle, cardboard,
paper. Weight Gaussians as in section 2.3.

The line's prior and sensor tables, once the rule is `expected_cost`,
are configuration. The cost table that rule loads first is the reasoned
default below. Training corpora and checkpoints are unchanged. The
estimator may read a corpus that already stores labels. It does not
invent a new dataset format in the first cut. If the logged hard label
is not in an existing record, the plan's learning phase says so and
stops. It does not scrape a label out of a side channel.

### Reasoned default

This is a reasoned default, not measured data. Phase 5 estimates
replace it. The estimator writes counts and sensor tables and refuses
to write this file (`AC-SORT-14`). Putting those estimates into the
cost cells is a reviewed edit of the default, not a write the command
performs.

The file is
[configs/routing/expected-cost-default.yml](../../configs/routing/expected-cost-default.yml),
version 1. Columns are `OUTCOMES`: `M-01` through `M-11`, then
`reject`. Rows are the channel ids in
[configs/runtime/sitl.yml](../../configs/runtime/sitl.yml). The scale
is the chapter's, integers from 0 to 10. A correct placement is 0.
Reject costs 2 on a recoverable class, the moderate nop. There is no
battery class in [waste-taxonomy.md](../waste-taxonomy.md). The
pressure hazard that document does name is the aerosol, filed under
`M-06`.

| Channel | M-01 | M-02 | M-03 | M-04 | M-05 | M-06 | M-07 | M-08 | M-09 | M-10 | M-11 | reject |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 reject | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 0 | 0 |
| 1 PET | 0 | 3 | 3 | 8 | 6 | 8 | 6 | 3 | 3 | 4 | 10 | 6 |
| 2 HDPE | 3 | 0 | 2 | 5 | 6 | 8 | 6 | 3 | 3 | 4 | 10 | 6 |
| 3 PP | 3 | 2 | 0 | 5 | 6 | 8 | 6 | 3 | 3 | 4 | 10 | 6 |
| 4 other plastic | 3 | 2 | 2 | 0 | 5 | 8 | 6 | 2 | 2 | 3 | 10 | 6 |
| 5 aluminum | 3 | 3 | 3 | 4 | 0 | 8 | 5 | 3 | 3 | 3 | 10 | 6 |
| 6 ferrous | 3 | 3 | 3 | 4 | 5 | 0 | 5 | 3 | 3 | 3 | 10 | 6 |
| 7 glass | 3 | 3 | 3 | 4 | 5 | 6 | 0 | 3 | 3 | 3 | 10 | 6 |
| 8 fiber | 4 | 4 | 4 | 6 | 6 | 10 | 8 | 0 | 0 | 0 | 10 | 6 |

Reject costs 2 for every recoverable class and 0 for `M-11` and for the
reject outcome, which are already home on channel 0.

The four resin channels cost 0 on their own class. HDPE and PP swap at
2, a polyolefin mix. Other plastic in the PET channel is 8, because
`M-04` includes PVC and film, and PET in the other-plastic channel is
3, a loss of grade into a stream that is already mixed.

Aluminum and ferrous swap asymmetrically: ferrous in the aluminum
channel is 8, aluminum in the ferrous channel is 5. Steel contaminates
the higher-value non-ferrous stream, and the camera cannot separate
the two cans. A coin flip between them prefers reject over either bin.

Glass takes the chapter's metal-in-glass cells, 5 for aluminum and 6
for ferrous. Glass in the fiber channel is 8, because container glass
fractures into the fiber bale. Fiber in the glass channel stays at 3,
the chapter's mild paper-in-glass direction.

The fiber channel is 0 for `M-08`, `M-09`, and `M-10`, because those
three share channel 8 on this mapping. Ferrous in that channel is 10,
the chapter's scrap-in-paper cell, and the class includes the aerosol.
Fiber in a metal channel stays at 3, the chapter's forgiving metal bin.

`M-11` costs 0 on reject and 10 on every sorted channel, so no sorted
channel is cheaper than reject for residue. The reject outcome costs 0
on reject and 6 on every sorted channel.

## Assumptions

- Sensors that enter the product are conditionally independent given the
  category, except the code factor, which keeps its down-weight.
- A simulation label is a usable category for counting. The perception
  contract already marks those fields as simulated.
- The spawn mix in the corpus is the right prior for simulation. A
  different stream needs its own counts.
- The cost table is the reasoned default in this document until phase 5
  estimates replace it. The mechanism does not measure damage.
- GTSAM 4.3.0's discrete constructors used above stay stable for the pin.
  The pin is exact, `gtsam==4.3.0`, so a later upload does not move it.
- Numpy stays compatible with that wheel. The import check ran with numpy
  2.5.4. `uv.lock` records numpy 2.2.6. The first implementation phase
  resolves the pin inside the lock and repeats the fixture there.

## Constraints

- Python remains `>=3.12`. `gtbook` 0.0.41 is out of reach on that
  baseline and is not a reason to move it.
- The safety crate gains no native dependency. `cargo deny` does not see
  Python licenses. The license record for `gtsam` and for optional
  `gtbook` is this document, which is what
  [CONTRIBUTING.md](../../CONTRIBUTING.md) asks for before a dependency
  is adopted.
- The core modules that do not build a posterior import neither `gtsam`
  nor `gtbook`. `clave.tracker.fusion` stays importable on a machine
  without the wheel, and the product lives in a module the runtime loads
  when the rule needs it.
- Proposal version 1 and the confidence floor keep working until the cost
  table is reviewed and the configuration flips. A default flip is a
  separate change, named in the plan.
- Latency budgets in [measurements.md](../measurements.md) still apply.
  The product is twelve outcomes and a handful of factors. The first
  implementation phase that puts it on the proposal path measures it. A
  budget is not invented here.
- Acceptance-criterion ids below are append-only.

## Acceptance criteria

Ids begin at `AC-SORT-01`.

- `AC-SORT-01`: When a track's category belief is built under
  `expected_cost`, the system shall represent it as a probability mass
  function over `OUTCOMES`, obtained by normalizing the product of the
  configured prior and one likelihood factor per sensor that reported.
- `AC-SORT-02`: When a sensor reading is folded into that belief, the
  system shall enter it as a likelihood factor, and the reading shall not
  name a channel.
- `AC-SORT-03`: When `expected_cost` is selected and a prior count, a
  sensor table, or a cost row is missing, the system shall refuse to load
  and shall name the missing key.
- `AC-SORT-04`: When a reading is an actual mass, the system shall score
  each outcome by the configured Gaussian density at that mass and shall
  include the scores as a likelihood factor.
- `AC-SORT-05`: When no mass reading exists, the system shall omit the
  weight factor.
- `AC-SORT-06`: The shipped sensor configuration shall contain no
  conductivity factor.
- `AC-SORT-07`: When a version 2 proposal is accepted, the Rust resolver
  shall choose the channel that minimizes expected cost under the loaded
  cost table and the proposal's posterior.
- `AC-SORT-08`: When the reject channel minimizes expected cost, the
  system shall publish the reject channel and shall keep the leading
  class on the decision.
- `AC-SORT-09`: When a cost table makes a sorted channel cheaper than
  reject for residue, the system shall refuse the table at load.
- `AC-SORT-10`: When the book's prior, cost table, and conductivity-false
  likelihood are evaluated, the system shall reproduce expected costs
  3.2, 0.6, 3.4, and 1.0 under the prior, shall select the metal bin
  under the prior, and shall reproduce the conductivity-false posterior
  to three decimal places, beginning 0.331, 0.497, 0.042, 0.050, 0.079.
- `AC-SORT-11`: When the book's posterior `(0.2, 0.3, 0.1, 0.1, 0.3)` is
  scored with the book's cost table, the system shall select the nop.
- `AC-SORT-12`: When category and discrete-sensor counts are given to the
  estimator, the system shall add one pseudo-count per cell and shall
  write a table `AC-SORT-03` can load.
- `AC-SORT-13`: When mass samples per category are given, the system shall
  store the sample mean and the unbiased sample variance.
- `AC-SORT-14`: The behavior-cloning policy and the scripted expert shall
  keep choosing the pick. The estimator shall not modify their checkpoints
  or the cost table.
- `AC-SORT-15`: When a grasp fails or the safety layer overrides a pose,
  the estimator shall ignore that event as category evidence.
- `AC-SORT-16`: The safety envelope shall keep checking reach, tool
  height, belt surface, and belt extent, and the safety crate shall not
  link GTSAM.
- `AC-SORT-17`: A version 2 runtime shall refuse a version 1 proposal
  before reading fields past the version.
- `AC-SORT-18`: `material_class` or `confidence` on a version 2 proposal
  that disagrees with `posterior` shall be refused.
- `AC-SORT-19`: Modules that do not build a posterior shall import neither
  `gtsam` nor `gtbook`.
- `AC-SORT-20`: The repository shall not contain the chapter's notebooks
  and shall not contain their prose.
- `AC-SORT-21`: While `routing.rule` is `confidence_floor`, channel
  resolution shall keep the behavior the routing crate has now.
- `AC-SORT-22`: After normalization, every outcome shall hold at least the
  configured posterior floor.

## Traceability

| ID | Test |
| --- | --- |
| `AC-SORT-01` | `test_ac_sort_01_two_likelihoods_match_a_hand_product` |
| `AC-SORT-02` | `test_ac_sort_02_the_soft_vector_is_not_the_likelihood` |
| `AC-SORT-03` | `test_ac_sort_03_a_missing_table_names_the_key` |
| `AC-SORT-04` | `test_ac_sort_04_a_gaussian_matches_the_density_at_a_fixed_mass` |
| `AC-SORT-05` | `test_ac_sort_05_a_missing_mass_omits_the_weight_factor` |
| `AC-SORT-06` | `test_ac_sort_06_shipped_configuration_has_no_conductivity` |
| `AC-SORT-07` | `ac_sort_07_the_resolver_argmin_matches_an_independent_multiply` |
| `AC-SORT-08` | `ac_sort_08_reject_wins_and_the_leading_class_stays_on_the_decision` |
| `AC-SORT-09` | `ac_sort_09_residue_cheaper_on_a_sorted_channel_fails_load` |
| `AC-SORT-10` | `test_ac_sort_10_prior_cost_and_conductivity_match_the_chapter` |
| `AC-SORT-11` | `test_ac_sort_11_the_given_posterior_selects_nop` and `ac_sort_11_the_book_posterior_selects_the_nop` |
| `AC-SORT-12` | The estimator does not exist yet |
| `AC-SORT-13` | The estimator does not exist yet |
| `AC-SORT-14` | The estimator does not exist yet |
| `AC-SORT-15` | The estimator does not exist yet |
| `AC-SORT-16` | `ac_sort_16_the_safety_manifest_does_not_name_gtsam` |
| `AC-SORT-17` | `ac_sort_17_a_version_2_runtime_refuses_version_1_before_other_fields` |
| `AC-SORT-18` | `ac_sort_18_a_class_or_confidence_that_disagrees_with_the_posterior_is_refused` |
| `AC-SORT-19` | `test_ac_sort_19_only_the_posterior_imports_gtsam` |
| `AC-SORT-20` | `test_ac_sort_20_the_repository_has_neither_the_notebooks_nor_the_sentence` |
| `AC-SORT-21` | `test_ac_sort_21_the_confidence_floor_does_not_read_the_tables` and `ac_sort_21_resolve_keeps_the_confidence_floor_beside_a_cost_table` |
| `AC-SORT-22` | `test_ac_sort_22_the_book_weight_underflow_is_lifted_to_the_floor` |

## Risks

The wheel is large and native. The quality gate grows by that install once
the extra is on the path the gate uses. Isolating the import limits the
damage to modules that actually multiply factors.

`pytest>=9.0.1` rides in with `gtsam`. The gate already runs pytest. A
conflict would show up in the first phase, which is why that phase changes
no behavior.

`gtbook` 0.0.38 pulls `kaleido` with no upper bound. The book's later pin
caps it below 1. Leaving `gtbook` off the runtime extra avoids that solver
problem. An inspection extra that wants it has to pin `kaleido` itself.

Uncalibrated logits treated as a likelihood would put a training loss on
the wrong side of Bayes' rule. `AC-SORT-02` and the hard-label table are
the guard.

The reasoned default is not a measurement. Citing it as one would put
an unmeasured number where [measurements.md](../measurements.md)
belongs. The book's 4 by 5 numbers stay in the fixture.

The code factor's down-weight is a CLAVE correction the chapter does not
have. Dropping it to match the textbook product would double-count a
label. Keeping it has to be tested, or a later edit will delete it as an
inconsistency.

## Design notes

The posterior builder is a new module under `clave`, loaded by the runtime
when it encodes a proposal. `clave.tracker.fusion` keeps the floor, the
recency weight, and the code down-weight. Those three are the extensions.
The product itself moves to GTSAM so the fixture can call the same types
the chapter calls.

`clave-routing` gains an expected-cost function beside `Resolver::resolve`.
The confidence-floor function stays until `AC-SORT-21` is retired on
purpose. The two functions do not blend: a configuration picks one.

Integer keys inside GTSAM are allocated by the builder and discarded with
the factor. `gtbook.discrete.Variables` is not required for that. The
optional extra exists so a notebook can print a named table the way the
chapter does, and so the dependency review has a place to put `0.0.38`.
Runtime code does not import it.

## Open questions

1. Cost table. Answered: there is no measured damage data. The reasoned
   default for `M-01` through `M-11` is
   [configs/routing/expected-cost-default.yml](../../configs/routing/expected-cost-default.yml),
   version 1, copied under [Reasoned default](#reasoned-default). It is
   not measured data. Phase 5 estimates replace it. `routing.rule` in
   the shipped runtime file stays `confidence_floor`, and this file is
   not loaded there.
2. Default rule. Answered: `routing.rule` stays `confidence_floor`. An
   operator opts in by setting `expected_cost`.
3. Perception head. Answered: the first cut stands. The hard label is
   the argmax, and the likelihood is the conditional table. A calibrated
   vector does not replace that table.
