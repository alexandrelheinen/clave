# Implementation Plan

Tasks marked `(P)` have no ordering relationship with each other and may run in
parallel. Everything depends on 1.1, because the record type is what every
metric is a function of.

- [ ] 1. Foundation: the record

- [ ] 1.1 Define the recorded outcome and its set
  - Define the frozen record carrying the object id, the true class, the
    predicted class or none, whether the object was picked, the routed channel
    or none, whether the instance was seen during training, the decision
    latency, and the cycle time or none.
  - Define the set wrapping a tuple of records with a provenance string, and
    validate every class identifier against the taxonomy on construction.
  - Refuse a record that was not picked but carries a routed channel, since the
    two fields contradict each other.
  - Write the failing tests first: an unknown class is refused naming it, a
    contradictory record is refused, and a valid set constructs.
  - Observable: a set built from valid records exposes them, and an invalid one
    raises naming what was wrong.
  - _Requirements: 1.1, 1.3, 1.4_
  - _Boundary: clave.validation.outcomes_

- [ ] 1.2 Implement the placeholder records reader
  - Read a records file into a set, carrying the provenance the file declares.
  - State in the module docstring that the format is a placeholder v0.6.0
    supersedes, and that the metric functions do not depend on it.
  - Observable: a written file reads back to an equal set, and a file missing a
    required field fails naming it.
  - _Requirements: 1.5, 1.6_
  - _Boundary: clave.validation.outcomes_
  - _Depends: 1.1_

- [ ] 2. Core: the metrics

- [ ] 2.1 (P) Implement the confusion matrix and per-class accuracy
  - Build a matrix over the eleven taxonomy classes in taxonomy order, with rows
    indexed by the true class.
  - Count records with no prediction per true class, apart from records
    predicted as the wrong class.
  - Return no accuracy figure for a class with no records, rather than a perfect
    one.
  - Partition records into seen and unseen instances so accuracy is computable
    on each.
  - Observable: a record misclassified lands off the diagonal, a record with no
    prediction lands in neither the diagonal nor an off-diagonal cell, and a
    class with no support reports unmeasured.
  - _Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Boundary: clave.validation.metrics_
  - _Depends: 1.1_

- [ ] 2.2 (P) Implement the routing counts
  - Count presented, picked, missed, correct routes, rejects, and misroutes, and
    derive the pick success rate and the end to end sorting rate from them.
  - Decide the expected channel from a supplied class-to-channel mapping, with a
    default mapping built from the taxonomy rather than written out in code.
  - Count an object routed to the reject channel apart from one routed into the
    wrong material channel.
  - Contribute no routing outcome for an object that was never picked.
  - Observable: a set where one object is missed and one is misrouted reports one
    of each and not two of either.
  - _Requirements: 1.2, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: clave.validation.metrics_
  - _Depends: 1.1_

- [ ] 2.3 (P) Implement the percentile and the timing summaries
  - Implement the nearest-rank percentile and state the method in the docstring.
  - Summarize a series as its sample count, mean, median, 95th, 99th, and
    maximum, reporting nothing rather than zero for an empty series.
  - Summarize decision latency over every record and cycle time over the records
    that carry one.
  - Observable: p99 of a known series is an observed sample, an empty series
    reports unmeasured, and every summary carries its sample count.
  - _Requirements: 1.2, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: clave.validation.metrics_
  - _Depends: 1.1_

- [ ] 2.4 (P) Implement the named confusions
  - Declare the three confusions the taxonomy names, each with its identifier,
    display name, the class identifiers it spans, and the reason the separation
    is unavailable from a color image.
  - Compute, per confusion, the group's support, the count predicted as another
    member of the group, the count that erred outside the group, and the rate.
  - Leave the general confusion matrix computed over every record, so naming a
    confusion removes nothing from the aggregate.
  - Observable: an error inside a group and an error outside it are counted
    apart, and both still appear in the matrix.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: clave.validation.confusions_
  - _Depends: 1.1_

- [ ] 3. The gates

- [ ] 3.1 Implement threshold loading with no defaults
  - Define one field per threshold, none with a default value.
  - Read them from a configuration file, failing on an absent key by naming it
    and failing on a value that is not a number.
  - Commit the configuration with a comment per threshold recording the reason it
    was set where it was.
  - Observable: a configuration missing one key fails naming that key, and the
    committed configuration loads every threshold.
  - _Requirements: 6.1, 6.2_
  - _Boundary: clave.validation.gates, configs/validation/gates.yml_

- [ ] 3.2 Implement gate evaluation
  - Produce one outcome per gate carrying its identifier, description,
    threshold, observed value, and whether it passed.
  - Gate decision latency at the 99th percentile rather than at the mean.
  - Gate the accuracy drop from seen to unseen object instances.
  - Fail a class whose record count is below the configured minimum support as
    unmeasured rather than passing it, and fail a gate whose observed value is
    unmeasured rather than skipping it.
  - Observable: an unmet gate yields a failing outcome carrying both numbers,
    and a class nobody tested does not pass.
  - _Requirements: 6.3, 6.4, 6.5, 6.6, 6.7_
  - _Boundary: clave.validation.gates_
  - _Depends: 2.1, 2.2, 2.3, 2.4, 3.1_

- [ ] 4. Integration

- [ ] 4.1 Assemble the report
  - Build a summary from the metrics, then a report holding a run section and a
    verdict section, rendered in that order.
  - Name the provenance of the records in the run section, so a fixture is
    labeled as one.
  - List every gate in the verdict section, including the ones that passed.
  - Observable: the rendered report shows the counts before the verdicts, names
    the provenance, and shows a passing gate beside a failing one.
  - _Requirements: 7.1, 7.2, 7.3_
  - _Boundary: clave.validation.report_
  - _Depends: 3.2_

- [ ] 4.2 Expose the command
  - Add one subcommand taking a records file and a gate configuration, printing
    the report and returning non-zero when any gate is unmet.
  - Observable: the command prints a report and its exit code follows the
    verdict rather than the presence of output.
  - _Requirements: 7.4, 7.5_
  - _Boundary: src/clave/cli.py_
  - _Depends: 4.1_

- [ ] 5. The protocol document

- [ ] 5.1 Write the validation protocol
  - State what the harness measures, how a record is interpreted, the percentile
    method, and the three named confusions.
  - State every gate threshold and the reason it sits where it does, so a
    threshold is on record before any run rather than after one.
  - State plainly that no candidate has been trained, that no accuracy figure in
    this repository is a measurement, and that any records used to exercise the
    harness are fixtures.
  - Observable: a reader can tell which numbers are thresholds somebody chose and
    which numbers, if any, were measured.
  - _Requirements: 6.1, 7.2_
  - _Depends: 4.2_
