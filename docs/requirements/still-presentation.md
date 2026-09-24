# Still presentation

## Intent

Published figures of the sorting line need a dedicated CLI entry and lighting
that reads as a photograph on a project page, not as a debug viewport. The
runtime world keeps its single overhead light for datasets; stills opt into
presentation lighting without touching that world file.

## Scope

**In.** A `clave still` subcommand; presentation lighting that matches the
FRET project-page style (low headlight diffuse, grazing directional fills,
scene spotlights suppressed); still scenario capture instants that match
what their descriptions claim; an arm that starts parked and rides at
approach height over a reachable package rather than chasing object centres
below the belt.

**Out.** Changing dataset or training lighting. Post-process tonemapping,
depth of field, or composites. Replacing the scripted expert with the full
task machine.

## Acceptance criteria

Ids begin at `AC-STILL-01`. Append-only.

`AC-STILL-01`: The CLI exposes `clave still` with a scenario name and an
output directory. `clave sim` does not carry a `--still` flag.

`AC-STILL-02`: When a still scenario supplies `lighting`, the compiled model
activates only the presentation lights that scenario declares (plus the
MuJoCo headlight), and the scene's default overhead light and the arm
spotlight are inactive.

`AC-STILL-03`: Presentation lights may be directional. A still's `quality`
section may set `shadowsize` and `offsamples` on the compiled model.

`AC-STILL-04`: Every shipped still scenario loads, and its description of
how many packages and classes are on the belt matches a capture at its
stated seed and instant.

`AC-STILL-05`: At the capture instant the flange sits above the belt surface
inside the trusted reach annulus, and within a package's major extent of a
reachable package in the belt plane (the arm is serving the line, not
parked beside it or buried below the belt).

## Test plan

| Criterion | Test |
| --- | --- |
| `AC-STILL-01` | `test_still_is_its_own_subcommand` |
| `AC-STILL-02` | `test_presentation_lighting_suppresses_scene_lights` |
| `AC-STILL-03` | `test_presentation_lights_may_be_directional` |
| `AC-STILL-04` | `test_every_shipped_still_matches_its_belt_claim` |
| `AC-STILL-05` | `test_the_arm_serves_the_belt_at_capture` |
