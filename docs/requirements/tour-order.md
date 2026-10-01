# Tour order

Status: implemented

See [workflow/sdd.md](../../.guidelines/workflow/sdd.md) for how this fits
the process. The comparison that decides which solver the line should keep
is [object-order-solvers.md](../research/object-order-solvers.md).

## Intent

The queue that hands the arm its next object is built by one construction,
and that construction is buried inside `Selector`. Replacing it means
editing the selector. This spec pulls the construction out behind a solver
the runtime configuration names, ships the construction that is already
there, and adds an ant-colony solver beside it so the two can be timed,
scored, and discarded or kept on evidence rather than on the shape of the
idea.

The audience is whoever decides whether a colony should order the belt.
The arm is not that audience: the shipped name stays the greedy walk, and
nothing in the task machine changes.

## Scope

**In scope:**

- A solver interface that takes the admissible tracks, the flange position,
  and the exit weight, and returns a permutation of those tracks.
- The greedy walk the selector already runs, as one solver.
- An ant-system solver that keeps pheromone between rebuilds, drops it when
  a track leaves, and scores a tour with a configurable discount on later
  visits.
- Configuration that selects the solver at load and holds every colony
  parameter.
- A study that scores both solvers against an exhaustive reference on
  travel, on the first visit, on stability, and on time.

**Out of scope:**

- Changing the anchor radius, the exit weight, or when the queue rebuilds.
- A third runtime solver. Exhaustive search is the study's reference and
  is not selectable on the line.
- Persisting pheromone across a process restart.
- Retuning the task machine, the servo, or the safety envelope around
  whichever head comes back.

## Acceptance criteria

`AC-ORDER-01`: When `selection.solver` is `nearest_neighbor`, the system
shall order the admissible markers by the greedy construction
`AC-MOVE-01` and `AC-MOVE-02` name, and a tie in that cost shall keep the
marker that appears earlier in the request.

`AC-ORDER-02`: The system shall read `selection.solver` when the control
configuration loads, and shall refuse a missing name or a name that is
not a solver, and the refusal shall name the solvers that exist.

`AC-ORDER-03`: When `selection.solver` is `ant_colony`, the system shall
return each admissible track once, and shall return an empty order when
no track is admissible.

`AC-ORDER-04`: The ant-colony solver shall keep pheromone on edges whose
tracks are still present, and two solvers constructed with the same
settings shall return the same orders for the same sequence of requests.

`AC-ORDER-05`: The system shall read every ant-colony parameter from
`selection.ant_colony` and shall refuse a missing key by name. It shall
refuse a count below one, an evaporation outside the open-closed unit
interval, a heuristic weight below zero, a pheromone weight, deposit, or
initial pheromone that is not strictly positive, a position discount
outside the open-closed unit interval, or a seed that is not a
non-negative integer.

`AC-ORDER-06`: When a track is removed from the set the colony is told to
retain, the colony shall drop every pheromone edge that names that track.

`AC-ORDER-07`: The study shall score both solvers on open-path length
against an exhaustive reference, on whether the first visit agrees, on
how the order moves when the same request is repeated and when the set
changes, and on the time a call takes.

## Traceability

| ID | Test(s) |
|---|---|
| `AC-ORDER-01` | `tests/control/order_test.py::test_nearest_neighbor_keeps_the_greedy_order_and_its_tie_break`, and the shipped-solver cases in `tests/control/selection_test.py` (`AC-MOVE-01`, `AC-MOVE-02`) |
| `AC-ORDER-02` | `tests/control/settings_test.py::test_an_unknown_solver_names_the_ones_that_exist`, `test_an_absent_key_fails_at_load_naming_itself` |
| `AC-ORDER-03` | `tests/control/order_test.py::test_the_ant_colony_returns_each_admissible_track_once` |
| `AC-ORDER-04` | `tests/control/order_test.py::test_two_colonies_agree_and_pheromone_outlives_a_call` |
| `AC-ORDER-05` | `tests/control/settings_test.py::test_an_absent_ant_colony_key_fails_at_load`, `test_a_colony_parameter_outside_its_range_is_refused` |
| `AC-ORDER-06` | `tests/control/order_test.py::test_retiring_a_track_drops_edges_that_name_it` |
| `AC-ORDER-07` | `tests/control/order_study_test.py::test_the_study_scores_both_solvers` |

## Constraints

- The shipped `selection.solver` is `nearest_neighbor`. Landing this work
  does not change the order the arm is given.
- The measured population inside the workspace has mean 2.67 and peak six
  (`docs/measurements.md`). Both solvers are for that size. A belt with
  dozens of admissible tracks at once is outside this contract.
- The colony runs when the queue rebuilds (a track appears, retires, or
  its anchor moves). It does not run on a tick that only carries the belt.
- Pheromone is process memory. A restart begins at the initial pheromone.
- The seed is configuration, so a colony run can be repeated.

## Design notes

The seam is `clave.control.order`. `Selector` builds one solver from
`SelectionSettings` and asks it for a permutation when the queue rebuilds.
`NearestNeighborSolver` is the walk that used to live in `_sorted`.
`AntColonySolver` is the ant system of Dorigo, Maniezzo and Colorni
(1996): each ant samples a permutation with probability proportional to
pheromone to the power of the pheromone weight, times a heuristic to the
power of the heuristic weight. The heuristic is the reciprocal of the
same step cost the greedy walk uses. Every ant then adds deposit over
tour score onto the edges it used, after the stored edges evaporate.

The step cost is `distance + exit_weight * distance_before_leaving`.
Summed along a full permutation with position discount 1, the exit terms
add the same constant for every permutation, because every admissible
object is visited once. A search that minimizes that sum is minimizing
open-path length, and the exit weight does not change which permutation
wins. The greedy walk never looks at that sum. It looks at the next step,
which is why an object about to leave the window can outrank a nearer
one. The position discount, strictly below one, is what makes a later
visit cheaper in the colony's score, so the first visit can feel the
weight. At one, the colony is searching for a short path.

Pheromone is keyed by track id. The flange is an edge source with an id
no track may use. `retain` deletes edges that name a track outside the
live set. A track that appears starts at the initial pheromone, so a
colony that has concentrated on an old tour is slow to put the newcomer
first. That lag is the behavior the study is there to measure, not a
side effect to be smoothed over in the solver.

## Open questions

Whether `ant_colony` remains in the tree after the comparison is read.
Both solvers ship, the default stays `nearest_neighbor`, and deleting
one is a separate change.
