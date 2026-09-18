# The proposal boundary

This is the format inference speaks to the safety layer. It is written down
here so a producer can implement it without reading CLAVE's source, in the same
way `crates/clave-decision/contract/pick-decision.cddl` states the published
decision.

It is an internal boundary rather than a cross-project contract. Anything
leaving CLAVE leaves as a pick decision in CBOR; this format exists only
between the process that runs a model and the process that checks what the
model proposed.

## Transport

One proposal per `AF_UNIX` datagram, UTF-8 JSON, no framing and no length
prefix. Record boundaries come from the kernel, which is the same reasoning
the published decision follows.

A zero-length datagram is the stop signal. It carries no version and no fields,
so it cannot be mistaken for a proposal the runtime refuses to read.

The producer binds the decision and the outcome sockets before starting the
runtime, because connecting a datagram socket to a path nothing is bound to
fails immediately rather than waiting.

## Fields

| Field | Type | Unit and meaning |
| --- | --- | --- |
| `version` | integer | Wire version. This build implements 1 |
| `object_id` | integer | Identity the tracker assigned, carried unchanged into the decision |
| `material_class` | string | Taxonomy identifier, `M-01` to `M-11`, from `docs/waste-taxonomy.md` |
| `confidence` | number | Classifier confidence, 0.0 to 1.0 inclusive |
| `x_meters` | number | Proposed pick point along belt travel, belt frame |
| `y_meters` | number | Proposed pick point across the belt, belt frame |
| `z_meters` | number | Proposed pick point normal to the belt surface, belt frame |
| `yaw_radians` | number | Proposed rotation about the belt normal |
| `reference_time_nanos` | integer | Instant the pose is predicted for, system monotonic clock |
| `window_start_nanos` | integer | Earliest instant the object is reachable |
| `window_end_nanos` | integer | Latest instant the object is reachable |

Every field is required. The frame, the units and the clock are the ones the
published decision uses, so nothing is converted at the boundary.

## What the runtime refuses

| Condition | Response |
| --- | --- |
| `version` is not 1 | The whole proposal is refused, on the version alone, before any other field is read |
| The payload is not JSON, or a field is missing or of the wrong type | Refused, naming what the decoder expected |
| A coordinate is not finite | Refused, naming the field |
| `material_class` is outside the taxonomy | Refused, naming the identifier |
| `confidence` is outside 0.0 to 1.0 | Refused |
| `window_end_nanos` precedes `window_start_nanos` | Refused |
| `reference_time_nanos` falls outside the window | Refused |

A refusal is reported on the outcome socket and the loop continues. One
unreadable datagram does not stop a conveyor.

## The outcome

The runtime answers every proposal with one JSON datagram, so a producer can
time a round trip and count what happened without parsing CBOR.

```json
{"verdict": "accepted", "object_id": 7, "channel": 1, "reject_reason": null}
{"verdict": "accepted", "object_id": 7, "channel": 0, "reject_reason": "below_threshold"}
{"verdict": "overridden", "check": "reach"}
{"verdict": "refused", "reason": "proposal declares version 2, which this build does not implement"}
```

`check` is one of `reach`, `belt_surface` or `belt_extent`. `reject_reason` is
`below_threshold`, `unmapped_class`, or absent when the object was sorted.

An accepted proposal also produces one published decision on the decision
socket, encoded as `pick-decision.cddl` specifies. An overridden one produces
nothing there, which is what the safety layer is for.

## Versioning

`version` moves whenever a field is added, removed, or changes meaning. A
runtime that meets a version it does not implement stops visibly rather than
reading fields under the wrong meaning, so a producer upgraded ahead of its
runtime fails loudly on the first datagram.
