# Code quality, as audited

An audit of the Python surface on this branch: what the gates say, what a
search for dead configuration and dead code found, and what is left that a
reader should know about. Figures come from running the tools, not from
reading the code.

## Gates

| Gate | Result |
| --- | --- |
| `ruff check src tests` | clean |
| `ruff format --check src tests` | clean, 165 files |
| `mypy src tests`, strict | clean, 165 files |
| `pytest tests` | 686 passing, 5 skipped, in 11 minutes |
| `pytest --cov=clave` | 85% of lines, against a gate of 80% |

Strict mypy over both source and tests is the one worth naming, because it
is unusual to type test code and it is what caught two of the defects in
this branch before a run did.

## Size

| | Lines | Files |
| --- | --- | --- |
| `src/clave` | 18,841 | 87 |
| `tests` | 12,518 | 46 |

Two thirds of a line of test per line of source. The six largest modules:

| Module | Lines |
| --- | --- |
| `world/scene.py` | 1,271 |
| `tracker/debug_run.py` | 955 |
| `data/ingest.py` | 772 |
| `world/arm.py` | 697 |
| `cli.py` | 664 |
| `control/task.py` | 647 |

`world/scene.py` and `tracker/debug_run.py` are the two worth watching.
Scene assembly grew another 214 lines this branch for the chutes, and the
debug run is a driver holding the whole control loop, its instrumentation
and its reporting in one function. Neither is wrong yet and both are on the
path to being so.

## Dead configuration

Every top-level and second-level key in the three configuration files was
checked against a search of the source for something that reads it. Four
were dead and are gone:

| Key | Why it was dead |
| --- | --- |
| `structure.pedestal_radius_meters` | The pedestal became a box sized by `arm.pedestal_footprint_meters`, and these three described the cylinder it used to be |
| `structure.pedestal_plate_radius_meters` | Same |
| `structure.pedestal_plate_thickness_meters` | Same |
| `densities.densities_from_world` | Read as a switch and was not one: nothing looked at it, and the loader has always taken the bands from the world unconditionally |

The comment explaining why each mattered is kept where the reasoning still
applies, so removing the key does not remove the record of the decision.
The audit now finds nothing unread.

## Dead code

Every top-level function and class in `src/clave` was checked for a
reference outside the module defining it. Twenty came back with none, and
none of them is dead: they are dataclasses reached through attribute
access, registry entries referenced through the registry, and helpers used
within their own module. The search is a blunt instrument and its output
here is a list of false positives rather than a finding.

No `TODO`, `FIXME`, `XXX` or `HACK` marker exists in either tree.

## Suppressions

Twenty-four across source and tests. In `src/clave`, seven:

| Kind | Count | Shape |
| --- | --- | --- |
| `noqa: BLE001` | 3 | A broad catch that must not abort a sweep or a GUI probe, each with a reason |
| `noqa: PLC0415` | 1 | A conditional import inside a function, in `experiment/seeding.py` |
| `type: ignore` | 3 | Two `call-overload` in the CLI's argument parsing, one `arg-type` in validation |

Every one carries a reason on the same line. None is a blanket file-level
suppression.

## What this branch added, and what guards it

| Module | Lines | Tests naming its criteria |
| --- | --- | --- |
| `world/feed.py` | 182 | 7, `AC-RATE-01` to `10` |
| `tracker/motion.py` | 156 | 8, `AC-TRACK-30` to `35` |

Both are pure value code with no simulator dependency, which is why their
tests run in under three seconds against a synthetic plant rather than a
rollout. That was deliberate: the feed loop's settling behaviour and the
filter's gain response are properties of the algorithm, and proving them
through a two-minute simulation would prove them slowly and less
completely.

Three defects in this branch were found by a measurement rather than by a
test, and each now has a test that would have caught it:

- The feed controller written in velocity form, so its proportional term
  integrated at the physics rate. `test_a_reachable_setpoint_is_settled_onto`.
- Four consumers predicting with the belt speed the run drew rather than
  the one it is running at. No test yet; see below.
- A segmented mask one pixel across, whose projected extent rounds to zero
  and whose footprint refused to exist, ending the run.
  `test_a_mask_too_small_to_have_a_size_is_dropped`.

## What is not guarded

Stated because an audit that lists only what passes is not an audit.

**The stale belt speed has no test.** Four consumers read a commanded speed
that the run now updates every capture, and nothing fails if one of them
goes back to reading the layout's. A test would have to assert that the
tracker, the task machine, guidance and selection all see the controller's
speed, which means reaching into the debug run's wiring; that is worth
doing and is not done.

**The single 688 mm arrival outlier is not explained.** One visit in
seventeen where the arm does not reach a pose the servo accepted, with no
fault recorded. Contact with an object or a chute wall is suspected and
unconfirmed.

**The chutes have collision geometry the trajectory planner knows nothing
about.** `docs/guidance-formulation.md` already states that the arcs avoid
no obstacles, and until this branch there were none in the arm's reach.
There are four now. Nothing has demonstrated a collision and nothing
prevents one.

**Two modules sit well under the line.** Coverage is 85 percent overall
against a gate of 80, and it is not evenly spread:

| Module | Covered |
| --- | --- |
| `training/objectives.py` | 60% |
| `training/adapters.py` | 64% |
| `world/scene.py` | 87% |

The two training modules are the gap. They are the loss functions and the
model adapters, and both are exercised only where a deep learning library
is installed, which the gate's environment deliberately lacks. That is a
defensible reason for the number and not a reason to leave it: a loss
function with four tenths of its branches unrun is a loss function nobody
has checked the arithmetic of.

`world/scene.py` at 87 percent is the one this branch moved, since the
funnel builder and its two load-time refusals are new. Both refusals have
tests; the geometry that builds the walls does not, beyond the assertion
that the geoms exist.
