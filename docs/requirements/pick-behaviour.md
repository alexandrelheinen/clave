# Pick behaviour: reach, descent lateral, wrist

## Intent

Three operator complaints on seed-0 GT runs: the queue commits to an object
the planner cannot serve while a better candidate sits behind it; the jaw
jabs sideways in the last fraction of the descent; the wrist stays folded
backwards (wrist_2 near 270°) through the visit.

## Scope

**In.** Trying the next queue head when `plan_pick` refuses; descent retarget
aiming without inventing lateral drift over the remaining time; choosing the
parallel-jaw yaw (θ or θ+π) closest to the tool's current yaw.

**Out.** Changing `exit_weight`, reach annulus, or rewriting IK.

## Evidence (pre-fix, seed 0, 24 s)

- Descent `|vy|` peaked at 0.94 m/s at z≈1.09 m while HOLD stayed at 0.
- `retarget_descent` aimed with `_drift_velocity`, so `vy × remaining` became
  a lateral end shift the quintic had to cover in ~0.3 s.
- IK seeds kept `wrist_2 ≈ 270°`; commits 2/3/5 blended 68–128° of yaw.
- Track 4 missed `plan_pick` while track 3 was still in the queue.

## Acceptance criteria

Ids begin at `AC-BEHAVE-01`. Append-only.

`AC-BEHAVE-01`: When the queue head has no feasible interception, the task
machine shall try later queue members on the same capture before parking.

`AC-BEHAVE-02`: A descent retarget shall aim the grasp with belt-axis
transport only (no lateral drift projection over the remaining descent),
so the splice does not invent cross-belt motion in the last fraction of a
second. A fresher object *position* may still move the end (AC-MOVE-63).

`AC-BEHAVE-03`: When a grasp yaw is commanded, the system shall pick θ or
θ+π (parallel jaw) so the commanded yaw is the one nearest the tool's
current yaw, wrapping on (−π, π].

## Test plan

| Criterion | Test |
| --- | --- |
| `AC-BEHAVE-01` | `test_a_missed_head_yields_to_the_next_candidate` |
| `AC-BEHAVE-02` | `test_descent_retarget_does_not_project_lateral_drift`, existing AC-MOVE-63 |
| `AC-BEHAVE-03` | `test_commanded_yaw_picks_the_nearer_parallel_grip` |
