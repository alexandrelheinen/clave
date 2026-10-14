# Changelog

The product version is the git tag. Package metadata in `pyproject.toml`
and the crate manifests stays on its own numbers.

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
