# Simulation Consolidation

## Intent

The CLI historically exposed multiple commands to run a simulation (`demo`, `run-sitl`, `debug-tracker`, `still`). This fragmented the developer experience and led to confusion over which command to use for what purpose. 

This specification consolidates these simulation executions into a single common interface (`clave sim`).

## Scope

**In.** Consolidating the simulation entry points in `src/clave/cli.py` into a single `sim` command. Defaulting the `sim` command to the marker-displaying debug view. Adding a `--still` flag to generate still frames. Removing `demo`, `run-sitl`, `debug-tracker`, and `still` commands.
**Out.** Changes to the underlying rendering, physics loop, or tracking logic beyond wiring them to the new CLI.

## Acceptance Criteria

- **[SIM-C-01]** The `clave` CLI exposes a `sim` command.
- **[SIM-C-02]** The `clave demo`, `clave run-sitl`, `clave debug-tracker`, and `clave still` commands are removed.
- **[SIM-C-03]** `clave sim` runs the tracker debugging visualization by default.
- **[SIM-C-04]** `clave sim --still` generates still frames.
