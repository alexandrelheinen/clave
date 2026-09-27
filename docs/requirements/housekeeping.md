# Housekeeping after v1.6.0

Status: landed

## Intent

Bring the living documents and the operator harness in line with the tagged
line. The latest tag is v1.6.0. Work that was still open under earlier names
continues as later minors. Stale claims that the jaw never closed, or that
there is no tracker, no longer belong in the architecture page.

## Scope

**In.** Rewriting the roadmap ladder from v1.7.0. Correcting architecture,
README, benchmark copy, and requirement status lines. Deleting the duplicate
detection-training guide and the duplicate frame-sampling essay once their
content lives in the training pipeline and the frame-sampling requirement.
Removing the `ppo-mlp` candidate that never trained. Splitting the operator
sim harness so clearance, overlay and report live beside `debug_run` rather
than inside it. Regenerating the project-page still and simulation film from
the current world.

**Out.** The learned tracker, the hold proof, and cycle time to a chute.
Those stay v1.7.0 through v1.9.0. Changing control behaviour. Changing the
published corpus.

## Acceptance criteria

Ids begin at `AC-CLEAN-01`. Append-only.

`AC-CLEAN-01`: The roadmap shall list open minors only as versions greater
than v1.6.0, and shall name the open steps v1.7.0, v1.8.0 and v1.9.0.

`AC-CLEAN-02`: `docs/architecture.md` shall not claim that no tracker exists
or that the gripper has never closed. It shall name the proposal-loop
identity gap and the open hold.

`AC-CLEAN-03`: The candidate registry shall not list `ppo-mlp`, and the
optional candidates extra shall not require `stable-baselines3` or
`gymnasium`.

`AC-CLEAN-04`: Clearance measurement, the debug overlay and the run report
shall live in modules under `clave.sim` other than `debug_run.py`, and the
existing sim tests shall still pass.

`AC-CLEAN-05`: The README simulation table shall match the shipped world:
belt width 0.50 m, two detection cameras, and the object count the world
spawns.

## Traceability

| ID | Guard |
| --- | --- |
| `AC-CLEAN-01` | `docs/roadmap.md` ladder tables |
| `AC-CLEAN-02` | `docs/architecture.md` "What is absent" |
| `AC-CLEAN-03` | `tests/candidates/registry_test.py` |
| `AC-CLEAN-04` | `tests/sim/` |
| `AC-CLEAN-05` | `README.md` simulation table against `configs/world/sorting_line.yml` |
