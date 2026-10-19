# Pick behaviour: reach, descent lateral, wrist

## Intent

Three operator complaints on seed-0 GT runs: the queue commits to an object
the planner cannot serve while a better candidate sits behind it; the jaw
jabs sideways in the last fraction of the descent; the wrist stays folded
backwards (wrist_2 near 270°) through the visit. A fourth complaint is that
the tool only reaches the grasp yaw at the end of the descent, so the jaw
closes with the wrist still turning.

## Scope

**In.** Trying the next queue head when `plan_pick` refuses; descent retarget
aiming without inventing lateral drift over the remaining time; choosing the
parallel-jaw yaw (θ or θ+π) closest to the tool's current yaw; among
tool-down IK solutions for a target, preferring the extended reach branch
(positive elbow, shoulder lift below the horizon) over the folded wrist;
turning the tool onto the grasp yaw at a configured wrist rate from the moment
that yaw is known, instead of over the whole approach.

**Out.** Changing `exit_weight`, the reach annulus, or replacing the damped
least-squares solver; changing the grasp yaw tolerance, the align limit, or
how the grasp yaw is predicted (AC-MOVE-62).

## Evidence (pre-fix, seed 0, 24 s)

- Descent `|vy|` peaked at 0.94 m/s at z≈1.09 m while HOLD stayed at 0.
- `retarget_descent` aimed with `_drift_velocity`, so `vy × remaining` became
  a lateral end shift the quintic had to cover in ~0.3 s.
- IK seeds kept `wrist_2 ≈ 270°`; commits 2/3/5 blended 68–128° of yaw.
- Track 4 missed `plan_pick` while track 3 was still in the queue.
- On a 180 s dense run (0.25 m/s belt, `configs/debug/high-flow.yml`, seed 0)
  on `main` `7e49b60`, at 26 closures the tool stood 19.2, 19.8, 19.9, 20.0,
  and 20.0 degrees from the commanded yaw at five of them, right at the 20
  degree `grasp_yaw_tolerance_radians` gate, and 4.0 and 5.7 degrees at two
  more.

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

`AC-BEHAVE-04`: When `solve` finds more than one tool-down joint solution
for a target, it shall return the extended-reach branch (elbow angle
positive after wrap to (−π, π], shoulder lift at or below zero) rather
than the folded branch that parks with `wrist_2` near 270°. Returned
angles shall be folded into (−π, π] inside the joint limits.

`AC-BEHAVE-05`: A pick is an attempt only once the jaw is commanded shut.
Every attempt shall be released over its chute and counted as placed.
The run report shall give the attempt count and the place count, and
the two shall be equal. A visit given up before the jaw shuts, and an
object no interception was planned for, are not attempts. The jaw shall
stay open at the grasp pose while the tool yaw is outside the configured
tolerance of the commanded grasp yaw, and the plan clock shall wait with
it. If the wrist has not arrived when the align limit runs out, the
visit shall be given up before the jaw shuts. Once the jaw is commanded
shut, the flange shall stay at the grasp height and ride with the belt
until the fingers have travelled the configured fraction of the driver
stroke, or until the close dwell has elapsed when a package stops the
fingers short of that fraction. A wait for the wrist shall ride with
the belt the same way, with the jaw still open. A close whose release, including that seat and the release
dwell, would run past the time the caller has left shall be given up
before the jaw shuts. A close whose nearest object sits farther from
the pinch than the configured gap shall be given up before the jaw
shuts. The belt shift that keeps the pinch over the package during a
wait shall be given back only past the configured margin, so the release
stays within that margin of the chute the plan aimed at and a pinch that
is already on the package is not dragged back by the whole wait. After
the arcs run out, the arm shall hold the
release pose with the jaw opening for the configured release dwell, so
the next visit cannot start while the fingers are still shut.

`AC-BEHAVE-06`: When a visit's grasp yaw is known, the commanded tool yaw
shall turn from the yaw it stands at onto the grasp yaw over the shortest
quintic whose peak rate is the configured wrist yaw rate
(`grasp_yaw_rate_radians_per_second`), starting at the instant the plan or its
re-aim was made, and shall then hold the grasp yaw for the rest of the
approach and the descent. When that turn would not finish before the pick, the
turn shall spread over the whole time to the pick, as before. When a re-aim
changes the grasp yaw, the turn shall start again from the yaw commanded at
that instant under the same rate. The turn shall take the nearer of the two
parallel-jaw yaws (AC-BEHAVE-03 still holds).

## Test plan

| Criterion | Test |
| --- | --- |
| `AC-BEHAVE-01` | `test_a_missed_head_yields_to_the_next_candidate` |
| `AC-BEHAVE-02` | `test_descent_retarget_does_not_project_lateral_drift`, existing AC-MOVE-63 |
| `AC-BEHAVE-03` | `test_commanded_yaw_picks_the_nearer_parallel_grip` |
| `AC-BEHAVE-04` | `test_the_solver_prefers_an_extended_reach_over_a_folded_wrist` |
| `AC-BEHAVE-05` | `test_the_arm_holds_the_release_until_the_object_can_fall`, `test_the_jaw_stays_open_until_the_wrist_matches`, `test_a_wrist_that_cannot_match_is_not_an_attempt`, `test_the_rise_waits_until_the_fingers_have_closed`, `test_a_close_that_cannot_finish_is_not_an_attempt`, `test_a_far_object_is_not_an_attempt`, `test_the_release_is_still_the_planned_chute` |
| `AC-BEHAVE-06` | `test_the_yaw_turn_finishes_at_the_configured_rate`, `test_the_yaw_turn_spreads_over_the_approach_when_the_rate_cannot_make_it`, `test_the_tool_reaches_the_grasp_yaw_early_in_the_approach` |
