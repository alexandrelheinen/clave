# Changelog

The product version is the git tag. Package metadata in `pyproject.toml`
and the crate manifests stays on its own numbers.

## v1.6.5

Centers at 0.125 m on the belt the shipped line already runs.

- The shipped figure 0.125 is a feed setpoint in objects per second.
  The drive range is 0.25 to 0.35 m/s, so that setpoint already holds
  the belt at 0.25 m/s. It is not a belt speed of 0.125 m/s.
- The shipped stills at seed 11 and 28.75 s now show three packages
  and three classes. A tall package that the origin test left sitting
  now rides the belt, and it is on the belt at that instant.
- The belt used to decide a package was on it from the body origin.
  Six of the ten packages stand with that origin above the height
  tolerance, so they were not driven. The next package was pushed
  through the stalled one and the step overflowed below 0.22 m centers.
  The drive now follows the bottom of the collision geometry. A package
  the arm has lifted is still not driven.
- A package that leaves the belt past a side guide, still at belt
  height, returns to the pool. A lifted package does not.
- While two packages touch, the belt leaves the velocity the contact
  solver just produced. A linear speed past
  `contact_speed_limit_meters_per_second` (1.0 m/s) is cut back, so a
  deep overlap cannot throw a package at many times belt speed.
- A pick counts as an attempt only once the jaw is commanded shut, and
  every attempt has to be placed. The jaw stays open at the grasp pose
  while the tool yaw is outside 0.35 rad of the command, and the visit
  is given up before the close if the wrist has not arrived in 0.50 s.
  After the arcs run out the arm holds the release pose for 0.40 s with
  the jaw opening, so the next visit cannot drag the object back off
  the chute. The belt ride during the close is given back only past
  0.08 m, so the release stays inside the mouth.
- Every package is turned onto a face that lies flat and still fits the
  jaw, and a face taller than 55 mm is scaled down to that. A round
  package stands on its flat end, so the can stays and does not roll.
  The compiler recenters the scan and a quarter turn used to swing that
  centre out across the belt, so a grasp or a camera aimed at the body
  missed the package. The geom position cancels that shift: the centre
  lies on the body and the bottom lies at the body's height. Clearing
  the spin left a tall face free to tip during the contact step and
  then ride on its side, where the jaw closes and the package does not
  rise. Until the arm touches it, the flat pose is restored.
  Until the arm touches it, the belt carries it at belt speed with no
  lateral velocity and no rotation. The constraint stops at that
  contact, so the grasp can lift it. On the seed-0 high-flow run,
  thirty seconds, ground truth: 3 attempts, 3 placed, lifts 105, 131
  and 122 mm. The feed measured 2.000 of 0.125 objects/s with the belt
  at 0.250 m/s.
- `configs/debug/high-flow.yml` spaces centers at 0.125 m and names a
  pool of 64. At 0.25 m/s that is 2.0 objects per second, ten times the
  flow the v1.6.2 seed carried. Packages may touch. The shipped rate
  and the shipped drive range are unchanged.

`AC-RATE-14` and `AC-RATE-15` hold.

## v1.6.4

A closer feed on the belt the shipped line already runs.

- v1.6.3 reached ten times the v1.6.2 flow by running the belt at 2.40 m/s.
  The arm had no interception and picked nothing.
- `configs/debug/high-flow.yml` keeps the shipped setpoint of 0.125
  objects per second and the drive floor of 0.25 m/s, and spaces package
  centers at 0.22 m. The two largest packages have bounding radii that
  sum to 0.180 m, so 0.125 m centers, which ten times the flow would
  need at this belt speed, can interpenetrate once a package tips.
  0.19 m clears those radii and still jams: a stalled package is caught
  by the next one and the step overflows.
- At 0.25 m/s and 0.22 m the line carries 1.14 objects per second. The
  controller holds the drive floor because the setpoint is below what
  that floor delivers. The shipped world file is unchanged.

`AC-RATE-13` holds.

## v1.6.3

A reproducible feed faster than one arm clears.

- `configs/debug/high-flow.yml` names 2.0 objects per second and a belt
  at 2.40 m/s. That is ten times the flow the v1.6.2 seed carried
  (about six arrivals in thirty seconds). The shipped drive stops at
  0.35 m/s, so the shipped setpoint cannot reach this rate, and
  `--belt-speed` alone is trimmed back toward that setpoint.
- `clave sim --feed` applies the file for one run. The shipped world
  file keeps its rate and its drive range. A `--belt-speed` on the
  same command wins over the speed in the file.
- This patch does not add an arm. The task machine, the chutes and the
  safety envelope stay one arm.

`AC-RATE-12` holds.

## v1.6.2

Probabilistic sorting on the tagged line.

- A category posterior over `M-01` through `M-11` and `reject`, folded
  with GTSAM when an operator selects expected cost.
- Expected-cost channel selection beside the confidence floor. Proposal
  version 2 carries the posterior. Version 1 stays valid while the rule
  is the confidence floor.
- `clave estimate-belief` writes prior and sensor counts from a count
  log. It does not edit the cost file and does not write a checkpoint.
- `configs/debug/expected-cost.yml` names the reasoned default. `clave
  sim --routing` uses it. The narrative emits one line per new routing
  decision.
- Phase 7 keeps `configs/runtime/sitl.yml` on `confidence_floor`. Seed 0
  for 30 seconds under ground truth and the debug file routed six
  arrivals. The floor chute and the expected-cost chute matched on each.
  The cost table was not edited, and the floor was not removed.

`AC-SORT-01` through `AC-SORT-22` hold, including `AC-SORT-21`.

Earlier tags are the GitHub releases.
