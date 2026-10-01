# Ordering the pick queue

The ant colony should not replace the walk that orders the queue. On the
feeder spacing the line runs, a mean of 1.55 tracks sit in the reachable
window and the two solvers name the same first track on every epoch of a
rolling belt. The colony takes 1.55 ms to do it. The walk takes 0.006 ms.
When the belt is packed to a mean of 4.1 tracks, which is the density at
which a tour is a real decision, the colony's first track matches the walk
on 35% of epochs and the lateness along its tour is 3.00 s against the
walk's 2.14 s. The shipped solver stays the greedy walk.

A second replay asks the same solvers about a field the belt does not
have. Twelve, twenty-four, or thirty-six points move in a 4 m square,
nothing damps the move, and three other robots each delete a point
before the planner looks. The order that holds together is a repair of
the previous permutation: survivors keep their relative order, and each
new id is inserted where it adds the least length. With 21 points still
visible that repair runs 9.8% over a 2-opt polish of the walk, and 95%
of epochs fall inside 20% of the polish, while 83% of the edges that
still have both ends survive. At 33 visible points the repair runs 31.5%
over and 20% of epochs stay inside that band. The warm colony, eight
ants and twenty iterations at evaporation 0.50, runs 22% over there,
inside the band on 40% of epochs, and keeps 47% of those edges. The
call takes 148 ms. The walk takes 0.85 ms and runs 11.5% over the polish.
Five iterations, the setting in which a carried trail has to stand in
for a short search, averages 30.4 m and 35.5 m against a polished path
of 18.6 m.

The comparison is `python -m clave.control.order_study`. It writes
`runs/debug/order-solvers/study.json`. The figures below are that file at
seed 0, with the sample sizes and the colony parameters recorded in it.
Scenes sit in the reachable window of [measurements.md](../measurements.md),
from -1.034 m to 1.034 m along the belt and within the feeder's lateral
range. The flange starts at the park pose. Travel time for the lateness
clock is distance divided by the configured speed bound of 1 m/s, and the
allowance is belt left divided by the belt speed of 0.30 m/s. A real visit
also descends, dwells and delivers, so the lateness compares orders. It
does not predict missed picks.

## The traveling salesman problem

A traveling salesman instance is a complete graph on n vertices with a
cost on every edge. A tour is a cyclic permutation. The problem asks for
the cycle of least total cost:

```
minimize over permutations π of {0, ..., n-1}
    sum over k of c(π(k), π(k+1)), with π(n) = π(0)
```

The decision version is NP-complete. The Euclidean case, where the cost is
a straight-line distance in the plane, is still NP-hard, and the best
polynomial guarantees sit a fixed fraction above the optimum. None of that
hardness is doing any work at the size of this belt.

The arm does not return to its start between objects, and it does not
choose where to start. The flange is already somewhere. The problem that
matches the words "shortest tour" is an open path with a fixed first
vertex. Number the tracks 1 through n, write a_i for the anchor of track
i, and write p_0 for the flange. A permutation π of the tracks has length

```
L(π) = sum over k = 1..n of || p_{k-1} - a_{π(k)} ||
```

with p_k = a_{π(k)} after each visit. There is no edge back to the flange.
That is the open traveling salesman problem, or the shortest Hamiltonian
path from a prescribed start.

## What the queue is actually scoring

[Arm control](../requirements/arm-control.md) scores a single step, not a
finished path. From a standing position p the cost of taking track i next is

```
c(p, i) = || p - a_i || + w * s_i
```

where s_i is the belt the object has left, in meters, and w is the
dimensionless exit weight. Both terms are meters. The shipped walk picks

```
h(p) = argmin over i of c(p, i)
```

then stands at that anchor and repeats on what remains.

Sum the same step along a whole permutation and the exit terms separate:

```
J(π) = sum_k c(p_{k-1}, π(k))
     = L(π) + w * sum_i s_i
```

Every admissible track is visited once, so the second sum is the same for
every permutation. The permutation that minimizes J is the permutation that
minimizes L. The exit weight, which is the whole reason the cost looks the
way it does, cancels out of the comparison between complete tours.

For two tracks the cancellation is visible by hand. The nearer track first
is never a longer open path than the farther track first, because the edge
between them is paid either way and the start edge is shorter. A positive
exit weight can still make the walk take the farther track, and that
lengthens L. On the drawn scenes with w = 1, that happened on 30% of the
two-track instances and the mean extra travel was 2.4%. The weight is
doing what it was configured to do. A solver that minimizes J will undo it.

The walk never looks at J. It looks at the next step, because the arm
executes the head and the set usually changes before the suffix is flown.
Measured occupancy in the workspace has mean 2.67 and peak six. The queue
is rebuilt when a track appears, when one retires, or when an anchor moves,
and belt travel alone does not rebuild it: every slack loses the same
meters, and a common term cannot reorder c.

A score that makes the first visit matter inside a sum, which is what
"keep the best tour and serve its first track" needs, discounts later
steps:

```
C_γ(π) = sum over k of γ^{k-1} * c(p_{k-1}, π(k)),    0 < γ ≤ 1
```

At γ = 1 this is J, and the weight cancels. As γ falls, the head's step
dominates and the weight can change which tour wins. γ is the colony's
position discount. The walk does not use it. The walk is already the case
where only the next step is scored.

The belt itself punishes arrival time. With arm speed v_a and belt speed
v_b the arrival and the lateness of visit k are

```
T_k = (1 / v_a) * sum over j = 1..k of || p_{j-1} - a_{π(j)} ||
ℓ_k = max(0, T_k - s_{π(k)} / v_b)
```

and the total lateness is the sum of ℓ_k. This is a traveling salesman
problem with deadlines, in the family of the traveling repairman and the
orienteering problem, not the plain open path. The step cost c is a scalar
stand-in for it, applied one decision at a time.

## Ways to search the path

1. Enumerate the permutations. The cost is n!, and the answer is exact.
   On the machine that produced the study file, one six-track instance
   took 11 ms and one eight-track instance took 880 ms. Four tracks took
   0.27 ms. The study uses this as the reference and does not offer it as
   a runtime solver.
2. Held-Karp dynamic programming, O(n² 2^n), computes the same optimum.
   It is the practical exact method once n is past the range where n! is
   comfortable. At a peak of six it is unnecessary beside enumeration.
3. Nearest neighbor, the shipped walk. Each step is the cheapest legal
   edge out of the vertex just reached. On a general cost matrix the path
   can be arbitrarily far from the optimum. On this window the gaps are
   the ones in the tables below.
4. Insertion constructions (nearest, cheapest, farthest) build a path by
   growing it. They are the same family as the walk: one pass, no memory,
   a guarantee only under extra assumptions.
5. Christofides' algorithm gives a closed tour at most 3/2 the optimum on
   a metric. The queue's path is open, the start is fixed, and c is not a
   metric edge cost once the exit term depends on the destination alone.
   The guarantee does not transfer.
6. 2-opt, 3-opt and Lin-Kernighan exchange edges of a finished path. They
   are what large Euclidean instances are actually solved with. At eight
   tracks an exchange has nothing to find that enumeration has not already
   settled.
7. A mixed-integer formulation with subtour elimination (Dantzig, Fulkerson
   and Johnson, or Miller, Tucker and Zemlin) is exact and spends its time
   building the model. That overhead is the whole budget at this n.
8. Ant system, and the later ant colony variants (elitist, rank-based,
   max-min, ant colony system). The implementation here is the 1996 ant
   system. Pheromone is kept when the vertex set changes, which is the
   usual way the method is stretched to a set that gains and loses tracks.
9. Simulated annealing, genetic algorithms and tabu search are the same
   kind of answer as the colony: a stochastic search sitting beside an
   exact method that already fits in the rebuild.
10. Re-solve the one-step rule h(p) when the set changes. For the head,
    which is the decision the arm executes, that rule is exact. It is what
    the selector already does.

## The greedy walk

`NearestNeighborSolver` is the construction that used to live inside the
selector. From the flange it takes the track of least c, stands at that
anchor, and repeats. An equal cost keeps the track that appeared earlier
in the request. It stores nothing between calls.

What it has in its favor is that it is the rule the exit weight was written
to express. A dying object outranks a nearer one by exactly w, and the
decision is available on the same rebuild that saw the object. The call is
deterministic, so a second rebuild of the same anchors returns the same
head. At the drawn sizes the median time runs from 0.007 ms at two tracks
to 0.053 ms at eight.

What it gives up is the shortest open path, on purpose when w is positive
and by the usual nearest-neighbor miss when w is zero. With w = 0 the mean
extra travel over the exhaustive path is 0 at two tracks (the algebra
above), 2.2% at three, 3.4% at four, 1.1% at five, 3.3% at six and 10% at
eight. With w = 1 the extra travel is the urgency working: 2.4%, 2.3%,
6.7%, 6.2%, 14% and 13% at those same sizes.

## The ant system

`AntColonySolver` is the ant system of Dorigo, Maniezzo and Colorni (IEEE
Transactions on Systems, Man, and Cybernetics, Part B, 1996). An ant at
vertex i steps to a remaining track j with probability

```
P(j) proportional to τ(i, j)^α * η(i, j)^β
η(i, j) = 1 / max(c(i, j), ε)
```

where τ is pheromone, α and β are the configured weights, and ε is a floor
of 1e-12 m so a track sitting on the flange does not divide by zero. The
flange is a source id no track may use. After every ant in the iteration
has a permutation, stored edges are multiplied by (1 − ρ) and each ant adds
Q / C_γ along the edges it used. Edges that have never been deposited stay
at the initial pheromone and do not evaporate, which is how a track that
just appeared remains a stranger until some ant takes it.

One rebuild runs a fixed number of iterations and returns the lowest C_γ
seen during that call, not a draw from the last iteration. The table is
kept for the next rebuild. `retain` deletes every edge that names a track
outside the live set.

The shipped parameters, in `configs/runtime/control.yml`, are eight ants,
twenty iterations, evaporation 0.2, pheromone weight 1, heuristic weight 2,
deposit 1, initial pheromone 1, position discount 1 and seed 0. They are
the 1996 ratios with a milder heuristic weight than the paper's value of 5,
so pheromone is able to move a choice, and a deposit scaled to tour scores
of a few meters. They are not a measurement on this belt. Discount 1 means
the tour the colony keeps is a short path, and the exit weight cancels, as
above. The heuristic still sees the weight, so the search is biased toward
urgent tracks even though the score it keeps is not.

What the colony has in its favor is the short path, when that is the
question. At discount 1 and w = 0 the mean travel gap against enumeration
is 0 through six tracks (the six-track cell is 12 scenes) and 0.18% at
eight tracks, where 88% of scenes were exact. Pheromone also holds a head
still: after a 30 mm planar nudge, which is past the 20 mm anchor radius
and so would rebuild the queue, the colony's head flip rate at six tracks
was 0, against 5.6% for the walk at w = 1 and 14% at w = 0.

The costs are the deadline and the time. At discount 1 and w = 1 the first track matches the walk on 70%,
90%, 95%, 80%, 75% and 75% of scenes at two through eight tracks. The
scenes where they differ are the ones where the walk paid extra travel
to serve a tighter slack. Median time is 1.55 ms at two tracks, 2.65 ms at three,
4.0 ms at four, 5.7 ms at five, 8.5 ms at six (the slowest of those twelve
calls was 12.8 ms) and 11.9 ms at eight. That is two hundred to two
hundred and fifty times the walk. Enumeration of a six-track instance
took 11 ms on the same machine, the same order of time as the colony,
and the enumeration is exact.

A frozen scene is not quite frozen for the colony. Repeated calls, pheromone
carried, changed the head on 0.7% of steps at three tracks with w = 1 and
on 2.4% at six tracks. The walk changed it on none.

Lowering the discount to 0.5 pulls the colony back toward the walk: at
w = 1 the first-track agreement becomes 95%, 95%, 100%, 90%, 92% and 88%.
The travel gap comes back with it (5.4% at six tracks, 8.2% at eight). A
colony tuned to imitate the walk is a slow walk.

## A belt that gains and loses tracks

The scripted arrival is three tracks at x = 0.30, 0.60 and 0.90 m, each
with 1.20 m of belt left, and a flange at the origin a meter above them.
After the colony has been called eight times on that set, a fourth track
appears at x = 1.10 m with 0.04 m of belt left. The step costs at w = 1
are about 2.24, 2.37 and 2.55 for the settled tracks and 1.53 for the
arrival, so the walk takes the arrival. That is not a close call.

With one iteration and one ant the colony's heads on the twelve calls after
the arrival begin 1, 99, 99, and the arrival is not first until the second
call. With five iterations the heads begin 2, 1, 1, 99, so the arrival
waits through three rebuilds, and later calls still drop it. With the
shipped twenty iterations the first call does take it, and the second call
names track 1 again before settling. With fifty iterations every call takes
it. The smooth reroute, the finite iteration count that eases onto the new
set, is the one-iteration and five-iteration rows. They are late, and they
do not stay on the new head. The iteration count that stays on the new head
has already jumped there.

The rolling belt is the same question without a script. Tracks enter at the
upstream end of the window and leave at 1.034 m. Slack is the meters
remaining to that exit, so sliding with the belt does not change relative
urgency. Only births, deaths and the changing distance to the parked flange
do. An epoch is long enough that a new track is due about every five
epochs.

At the feeder spacing of 1.20 m the window holds a mean of 1.55 tracks.
Head agreement is 100% and the lateness matches, because there is rarely a
tour to disagree about. The colony's median call is 1.55 ms against 0.006
ms. At a spacing of 0.45 m, chosen so about five tracks sit in the window
at once, near the measured peak of six, the mean occupancy is 4.1, head
agreement falls to 35%, and mean lateness is 3.00 s for the colony against
2.14 s for the walk. Carried pheromone is the mechanism that was supposed
to absorb an arrival. On a belt that keeps arriving, it holds an old head
past the point where the deadline has moved.

## A field shared with other robots

The replay is `python -m clave.control.order_fleet`. It writes
`runs/debug/order-solvers/fleet.json`. The figures below are that file
at seed 0, forty epochs, four robots. The square is 4 m on a side. Every
point moves at 0.35 m/s and a call happens every 0.25 s, so each point
travels 87.5 mm between calls. Before the call the generator replaces a
fraction 0.08 of the ids, rounded to a count, and then removes three
more, drawn from the live ids and fixed before any solver runs. The
planner sees 9, 21, and 33 points. From one of its epochs to the next
the set loses a mean of 2.8, 4.2, and 5.2 ids. The depot stays at the
center. The exit weight is zero, so the score is open-path length, which
is the quantity a pheromone keyed by track id can remember. Urgency
belongs to the belt study above.

The reference is 2-opt, first improvement, started from the greedy walk.
A reversal is kept when the two boundary edges shorten. It is a local
path. At nine visible points a fresh colony of twenty iterations and
evaporation 0.20 is shorter than that path on 20% of epochs, and the
mean lengths are 10.32 m and 10.35 m. A ratio below one means that
colony found a shorter path than this 2-opt descent.
Within 10% and within 20% count epochs whose length is at most that
factor times the 2-opt length.

Edge keep is the share of successive pairs, the depot included, that
still have both ends and that the next order still traverses as a pair.
A head change is counted only on epochs where the previous head is still
present. The Kendall fraction is the share of shared pairs whose
relative order changed. The repair scores zero there because keeping
that relative order is the method.

Colony weights other than the iteration count and the evaporation come
from the runtime file: eight ants, pheromone weight 1, heuristic weight
2, deposit 1, initial pheromone 1, position discount 1. A cold colony is
a new solver every epoch. A warm colony is one solver, and an edge that
names a deleted id is dropped when the call starts. The best-of-call row
returns the shortest tour the call saw. The last-iteration row returns
the shortest tour of the final iteration. Deposit uses every ant either
way, so those two rows differ in the tour they hand back.

| Seen | Method | Ratio | Within 20% | Edges kept | Head changes | ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 9 | 2-opt from the walk | 1.000 | 100% | 0.42 | 0.61 | 0.10 |
| 9 | nearest neighbor | 1.090 | 92% | 0.47 | 0.48 | 0.06 |
| 9 | repair | 1.052 | 98% | 0.72 | 0.44 | 0.03 |
| 9 | warm, 20 iterations, evaporation 0.20 | 1.018 | 100% | 0.38 | 0.60 | 14.3 |
| 9 | warm, 20 iterations, evaporation 0.50 | 1.045 | 100% | 0.38 | 0.57 | 14.2 |
| 9 | cold, 20 iterations, evaporation 0.20 | 0.999 | 100% | 0.43 | 0.54 | 14.5 |
| 9 | warm, 5 iterations, evaporation 0.20 | 1.035 | 100% | 0.35 | 0.68 | 3.6 |
| 21 | 2-opt from the walk | 1.000 | 100% | 0.46 | 0.47 | 0.56 |
| 21 | nearest neighbor | 1.077 | 88% | 0.46 | 0.25 | 0.29 |
| 21 | repair | 1.098 | 95% | 0.83 | 0.10 | 0.10 |
| 21 | warm, 20 iterations, evaporation 0.20 | 1.060 | 98% | 0.47 | 0.43 | 63 |
| 21 | warm, 20 iterations, evaporation 0.50 | 1.101 | 85% | 0.53 | 0.40 | 63 |
| 21 | cold, 20 iterations, evaporation 0.20 | 1.174 | 58% | 0.32 | 0.47 | 63 |
| 21 | warm, 5 iterations, evaporation 0.20 | 1.362 | 10% | 0.26 | 0.55 | 16 |
| 33 | 2-opt from the walk | 1.000 | 100% | 0.32 | 0.41 | 2.3 |
| 33 | nearest neighbor | 1.115 | 85% | 0.43 | 0.24 | 0.85 |
| 33 | repair | 1.315 | 20% | 0.86 | 0.06 | 0.24 |
| 33 | warm, 20 iterations, evaporation 0.20 | 1.227 | 30% | 0.37 | 0.23 | 149 |
| 33 | warm, 20 iterations, evaporation 0.50 | 1.221 | 40% | 0.47 | 0.15 | 148 |
| 33 | cold, 20 iterations, evaporation 0.20 | 1.540 | 0% | 0.21 | 0.66 | 148 |
| 33 | warm, 5 iterations, evaporation 0.20 | 1.637 | 0% | 0.20 | 0.61 | 38 |

Colony rows are the best tour of the call. The file holds the rest of
the grid. No five-iteration row at 21 or 33 visible points lands inside
20% on more than 10% of epochs. The longest is the warm colony at
evaporation 0.50 and five iterations: ratio 1.917 at 33 points, mean
length 35.5 m.

At nine visible points every row in the table is inside 20% on at least
92% of epochs. Length is cheap. The repair keeps 72% of surviving edges
at a 5.2% gap. The twenty-iteration warm colony at evaporation 0.20
keeps 38% at a 1.8% gap. Retention and length are already separating.

At 21 visible points that warm colony is the shortest method in the
table aside from the reference itself: 6.0% over, inside 10% on 33 of
the 40 epochs, mean length 16.0 m against the reference 15.1 m. The walk is
7.7% over, at 16.3 m. Edge keep is 0.47 for the colony and 0.46 for the
walk. The surviving head changes on 43% of epochs for the colony and on
25% for the walk. The calls take 63 ms and 0.29 ms. The cold colony at
the same iteration count is 17%
over and keeps 32% of edges, so the carried trail is what makes the
warm row short. The repair keeps 83% of edges, changes the surviving
head on 10% of epochs, and runs 9.8% over, inside 20% on 95% of epochs
and inside 10% on 45%. Five iterations drops the warm row to 36% over,
mean length 20.5 m.

At 33 visible points the walk is the short cheap tour: 11.5% over
(20.7 m against 18.6 m), inside 20% on 85% of epochs, edge keep 0.43,
head change 0.24, 0.85 ms. The best colony row is warm, twenty
iterations, evaporation 0.50: 22% over (22.7 m), inside 20% on 40% of
epochs and inside 10% on 10%, edge keep 0.47, head change 0.15, 148 ms.
Evaporation 0.20 runs 23% over, keeps 0.37 of the edges, and changes
the head on 23% of surviving epochs. The last-iteration tour is the
longer of the two reports. At this size and evaporation 0.50 its ratio
is 1.265 against 1.221 for the call's best tour, edge keep is 0.45
against 0.47, and the head-change rate is 0.15 in both rows. A cold
twenty-iteration colony runs 54% over at evaporation 0.20 and 44.5%
over at 0.50, with edge keep near 0.21.
Five warm iterations sit at 64% and 92% over. A trail laid down by
those tours and then trusted is a long tour. The 2-opt polish keeps
32% of edges and changes the head on 41% of surviving epochs, in 2.3 ms.
Re-solving a local path every epoch is short, and the order moves.

At 33 points the higher evaporation is both the shorter warm colony and
the one that keeps more edges. At 21 points the lower evaporation is
the shorter one (6.0% against 10.1%) and keeps slightly fewer edges
(0.47 against 0.53). Carried pheromone shortens the path once the
iteration count is high enough to deposit on decent tours. The repair
is the method whose successive edges survive. Past about twenty visible
points that survival is a long path: 31.5% over the reference at 33
points, with a fifth of epochs still inside 20%.

## What to keep

Keep the greedy walk as the only solver the line runs. It is the rule the
exit weight expresses, it is deterministic, and at the occupancy this belt
actually has, the shortest-path gap is a few percent on scenes where a
path exists at all. The anchor radius and the rebuild-on-change rule are
already the stability mechanism. They hold the order still between real
events, and they let a new track win on the rebuild that first contains it.

Keep the solver seam in `clave.control.order` only as long as a second
construction is under test. The colony can leave. Eight parameters in the
runtime file, a pheromone table, and a 200-fold slower call are a standing
cost for a method that misses the head the weight was added to protect.
If a later change really wants the shortest open path rather than the
urgent head, enumeration at the measured peak of six is exact and, at
11 ms, the same order of time as the colony, with no seed and no discount
to misunderstand. That would be a different product decision, because it
throws away the exit weight. It is not a reason to keep the ants.

On the shared field, keep the walk as well if one construction has to
cover every size in the replay. At 33 visible points it runs 11.5% over
the polished path, inside 20% on 85% of epochs, in 0.85 ms. The colony
row that comes closest runs 22% over, inside that band on 40% of epochs,
in 148 ms. The surviving head changes on 15% of epochs, against 24% for
the walk, and edge keep is 0.47 beside the walk's 0.43. Add the repair
when a requirement says a stolen point must leave the rest of the order
alone. It keeps 86% of surviving edges, and the surviving head changes
on 6% of epochs. Give it a length check. At 33 points the repair runs
31.5% over and 20% of epochs stay inside 20% of the polish. At 21 points
95% of epochs are inside that band and the mean gap is 9.8%. When the
requirement is the short path, polish the walk with 2-opt. At 33 points
that costs 2.3 ms. Enumeration no longer fits at this size, and the
colony remains the longer tour.
