# Implementation Plan

No task carries `(P)`. Configuration and adapters are prerequisites for the
runner, and every task lands in one package.

- [ ] 1. Foundation: configuration and dataset adapters

- [ ] 1.1 Implement training configuration
  - Read candidate name, epochs, batch size, learning rate, dataset path,
    checkpoint directory and seed from a file, with no default in code.
  - Fail at load naming a missing key.
  - Write the failing tests first.
  - Observable: a complete configuration loads and an incomplete one names the
    key it lacks.
  - _Requirements: 1.2_
  - _Boundary: clave.training.config_

- [ ] 1.2 Implement dataset adapters
  - Read only the training split, verifying the dataset digest first.
  - For detection, use visible labels alone; for classification, build a
    multi-label presence target over the taxonomy classes.
  - For the policy stage, replay the scripted expert and pair each observation
    with the decision it took.
  - Observable: an adapter given a dataset never reads validation or test, and a
    detection adapter drops labels whose objects are not in frame.
  - _Requirements: 1.3, 1.4, 1.5_
  - _Boundary: clave.training.adapters_

- [ ] 2. Core: objectives and the run loop

- [ ] 2.1 Implement per-candidate objectives
  - Multi-label cross entropy for the classifier, the detector's own composite
    loss, and mean squared error on the expert's pick position for the policies.
  - Observable: each objective returns a finite scalar on one batch from the
    recorded dataset.
  - _Requirements: 1.1_
  - _Boundary: clave.training.objectives_
  - _Depends: 1.2_

- [ ] 2.2 Implement the run loop with checkpoints and cost
  - Seed through the existing entry point, write a checkpoint each epoch, and
    resume from the recorded epoch when a checkpoint exists.
  - Record seed, configuration digest, dataset digest, environment, per-epoch
    loss and per-epoch wall-clock.
  - Report a candidate whose library is absent as unavailable rather than
    raising.
  - Observable: a killed run restarted continues at the next epoch, and a run
    record reloads with the standard library alone.
  - _Requirements: 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2_
  - _Boundary: clave.training.runner_
  - _Depends: 2.1_

- [ ] 3. Integration and report

- [ ] 3.1 Expose the training command
  - Add a command taking a candidate name and a configuration.
  - Observable: the command trains a candidate end to end and writes a run
    record.
  - _Requirements: 1.1_
  - _Depends: 2.2_

- [ ] 3.2 Train every candidate the available signal supports
  - Run each trainable candidate and capture measured per-epoch cost.
  - Observable: every trained candidate has a run record carrying measured
    wall-clock on the stated hardware.
  - _Requirements: 3.1, 3.2_
  - _Depends: 3.1_

- [ ] 3.3 Write the report
  - State measured cost beside the v0.1.2 estimate, and name any verdict a
    measurement contradicts.
  - Name every shortlisted candidate not trained, identifying the missing signal
    rather than blaming the architecture, and state when a stage target is unmet.
  - State the dataset size, present no accuracy as evidence, say whether each run
    converged or stopped early, and state that nothing was evaluated on real
    imagery.
  - Observable: a reader can tell what was measured, what was estimated, what was
    not trained and why, and what is still unknown.
  - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_
  - _Depends: 3.2_
