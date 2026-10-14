# Pick behaviour: reach, descent lateral, wrist

## Intent

Three operator complaints on seed-0 GT runs: the queue commits to an object
the planner cannot serve while a better candidate sits behind it; the jaw
jabs sideways in the last fraction of the descent; the wrist stays folded
backwards (wrist_2 near 270°) through the visit.

## Scope

**In.** Trying the next queue head when `plan_pick` refuses; descent retarget
aiming without inventing lateral drift over the remaining time; choosing the
parallel-jaw yaw (θ or θ+π) closest to the tool's current yaw; among
tool-down IK solutions for a target, preferring the extended reach branch
(positive elbow, shoulder lift below the horizon) over the folded wrist.

**Out.** Changing `exit_weight`, the reach annulus, or replacing the damped
least-squares solver.

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
stay open through the approach and the descent. The pose held when the
jaw shuts shall be the start of the hold, including when the pick instant
still falls inside the descent, so the close is not commanded on a
descent that is still moving onto the package. The jaw shall
stay open at that pose while the tool yaw is outside the configured
tolerance of the commanded grasp yaw, and the plan clock shall wait with
it. If the wrist has not arrived when the align limit runs out, the
visit shall be given up before the jaw shuts. Once the jaw is commanded
shut, the flange shall stay at the grasp height and ride with the belt
until the fingers have travelled the configured fraction of the driver
stroke, or until the close dwell has elapsed when a package stops the
fingers short of that fraction. A wait for the wrist shall ride with
the belt the same way, with the jaw still open. A close whose release,
including that seat and the release dwell, would run past the time the
caller has left shall be given up
before the jaw shuts. A close whose nearest object sits farther from
the pinch than the configured gap shall be given up before the jaw
shuts. The belt shift that keeps the pinch over the package during a
wait shall be given back only past the configured margin, so the release
stays within that margin of the chute the plan aimed at and a pinch that
is already on the package is not dragged back by the whole wait. After
the arcs run out, the arm shall hold the
release pose with the jaw opening for the configured release dwell, so
the next visit cannot start while the fingers are still shut.

`AC-BEHAVE-06`: The grasp aim shall carry a package forward at the belt's
running speed. A measured along-belt velocity from the contact that just
resolved, including travel back up the belt or a spike ahead of the belt,
shall not be the speed the aim uses. Lateral velocity may still be carried
for the drift horizon.

`AC-BEHAVE-07`: When the arm descends on a package, the flange shall already
be within 5 mm of that package in the horizontal plane, and moving at the
belt's running speed, before any part of the open jaw is lower than the
package's top. The descent from there shall stay inside those 5 mm, with
the jaw open, and shall cover the same along-belt travel the package does.
Between the first contact of the jaw with the target and the jaw being
commanded shut, the target's horizontal displacement and its rotation
relative to the belt shall stay about zero. The run report shall give that
displacement and that rotation, and the lowest the jaw sat above the
package's top while the pinch was more than 5 mm off it, one figure per
visit. The servo lead shall stay on along the belt and vertically through
the descent and the hold. Switching it off leaves the flange one lead-time
upstream, about 8 mm at the shipped belt speed, while the jaw is already
below the package. The across-belt component of that lead shall stay off.

## Test plan

| Criterion | Test |
| --- | --- |
| `AC-BEHAVE-01` | `test_a_missed_head_yields_to_the_next_candidate` |
| `AC-BEHAVE-02` | `test_descent_retarget_does_not_project_lateral_drift`, existing AC-MOVE-63 |
| `AC-BEHAVE-03` | `test_commanded_yaw_picks_the_nearer_parallel_grip` |
| `AC-BEHAVE-04` | `test_the_solver_prefers_an_extended_reach_over_a_folded_wrist` |
| `AC-BEHAVE-05` | `test_the_arm_holds_the_release_until_the_object_can_fall`, `test_the_jaw_stays_open_until_the_wrist_matches`, `test_a_wrist_that_cannot_match_is_not_an_attempt`, `test_the_rise_waits_until_the_fingers_have_closed`, `test_a_close_that_cannot_finish_is_not_an_attempt`, `test_a_far_object_is_not_an_attempt`, `test_the_release_is_still_the_planned_chute`, `test_the_close_stays_on_the_hold_when_the_pick_falls_in_the_descent` |
| `AC-BEHAVE-06` | `test_a_contact_velocity_does_not_aim_the_jaw_ahead` |
| `AC-BEHAVE-07` | `test_the_descent_is_vertical_in_the_object_frame`, `test_the_jaw_is_over_the_package_before_any_part_drops_below_it`, `test_a_package_that_rides_the_belt_does_not_count_as_shoved`, `test_a_shove_before_the_jaw_shuts_is_the_slide_and_the_turn`, `test_the_descent_keeps_the_along_belt_lead`, `test_a_gap_in_the_plan_does_not_split_one_visit` |
