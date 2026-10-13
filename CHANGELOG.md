# Changelog

The product version is the git tag. Package metadata in `pyproject.toml`
and the crate manifests stays on its own numbers.

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
