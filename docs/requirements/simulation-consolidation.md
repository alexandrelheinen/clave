# Simulation Consolidation

## Intent

The CLI historically exposed multiple commands to run a simulation (`demo`,
`run-sitl`, `debug-tracker`). That fragmented which entry point a developer
reached for. Runtime simulation lives under one command; presentation stills
are a separate concern and keep their own entry point.

## Scope

**In.** One `sim` command for the tracker debug rollout. Removing `demo`,
`run-sitl`, and `debug-tracker`. Presentation frames use `clave still`.

**Out.** Changes to the underlying rendering, physics loop, or tracking
logic beyond wiring them to the CLI.

## Acceptance criteria

- **[SIM-C-01]** The `clave` CLI exposes a `sim` command.
- **[SIM-C-02]** The `clave demo`, `clave run-sitl`, and `clave debug-tracker`
  commands are removed.
- **[SIM-C-03]** `clave sim` runs the tracker debugging visualization by
  default.
- **[SIM-C-05]** Presentation stills are captured with `clave still`, not
  with a flag on `sim`. See [still-presentation.md](still-presentation.md).

`SIM-C-04` named `clave sim --still` and is spent; do not reuse it.
