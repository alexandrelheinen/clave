# Implementation Plan

- [x] 1. The benchmark

- [x] 1.1 Load the configurations to compare
  - Read the configurations, seeds and run length from YAML, failing on a
    missing key by naming it.
  - Write the failing tests first.
  - Observable: the shipped file loads and names its configurations; deleting a
    key fails naming that key.
  - _Requirements: 1.1, 2.1_
  - _Boundary: clave.benchmark.config_

- [x] 1.2 Turn a run into scored outcomes
  - One record per object that entered the reachable window, with the true class
    from the world and the predicted class from the decision published for it.
  - Carry `picked = False` on every record, which is what makes pick success and
    cycle time unmeasurable rather than zero.
  - Observable: an object with no decision carries no predicted class, and the
    record count equals the number of objects that entered the window.
  - _Requirements: 1.2, 1.3_
  - _Boundary: clave.benchmark.suite_
  - _Depends: 1.1_

- [x] 1.3 Run every configuration and score it
  - The same seeds and the same world for each, scoring through the v0.8.0
    harness rather than a second metric implementation.
  - A configuration whose checkpoint or library is absent is recorded with its
    reason and does not stop the others.
  - Observable: the suite returns one result per configuration, including the
    unavailable ones.
  - _Requirements: 1.1, 1.2, 2.3_
  - _Boundary: clave.benchmark.suite_
  - _Depends: 1.2_

- [x] 1.4 Write the evidence pack and the table
  - Seeds, digests, machine and every measurement, as JSON a later reader parses
    without this package, plus the comparison table and the recommendation.
  - Name every metric that could not be measured and why.
  - Observable: the pack round-trips through JSON and the recommendation names a
    configuration that is present in the results.
  - _Requirements: 1.2, 1.3, 1.4, 2.1, 2.2_
  - _Boundary: clave.benchmark.pack_
  - _Depends: 1.3_

- [x] 1.5 One command
  - `clave benchmark` runs the suite from the committed configuration and prints
    the table.
  - Observable: the command runs end to end and its exit status reflects whether
    every gate the benchmark could evaluate passed.
  - _Requirements: 1.5_
  - _Boundary: clave.cli_
  - _Depends: 1.4_

- [x] 2. The demonstration

- [x] 2.1 Record video from a stepped world
  - Raw frames to ffmpeg on standard input, on the video's own cadence rather
    than the decision cadence, with nothing drawn on a frame.
  - An absent encoder is reported rather than fatal.
  - Observable: a short render produces a playable file; with ffmpeg hidden, the
    recorder reports its absence and the caller continues.
  - _Requirements: 3.3, 3.4, 3.5_
  - _Boundary: clave.demo.video_

- [x] 2.2 Load and run a scenario
  - Every tunable from a scenario file: predictor, seed, duration, belt speed
    override, video size and frame rate.
  - Observable: a scenario loads, and a missing key fails naming itself.
  - _Requirements: 3.1, 3.2_
  - _Boundary: clave.demo.scenario_
  - _Depends: 2.1_

- [x] 2.3 One command, and what it prints
  - `clave demo <scenario>` runs the named scenario, records the video and
    prints the decisions published and the overrides the safety layer applied.
  - Observable: one line of command produces a video file and a printed summary.
  - _Requirements: 3.1, 3.6_
  - _Boundary: clave.cli_
  - _Depends: 2.2_

- [x] 3. Report

- [x] 3.1 Write the release report
  - The comparison, the recommendation, every unmeasured metric with its reason,
    and what a human has to check before any of this touches hardware.
  - Observable: a reader can tell what was verified in simulation and what was
    not verified at all.
  - _Requirements: 1.3, 1.4_
  - _Depends: 1.5, 2.3_
