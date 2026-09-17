# The decision on ROS 2

CLAVE publishes its pick decision twice, in two encodings, for two audiences.
`pick-decision.cddl` beside this file specifies the CBOR a consumer reads off a
Unix datagram. This file specifies the ROS 2 message carrying the same decision
for a consumer on the middleware, which is how FRET receives it.

The two never disagree, because the ROS publisher decodes the CBOR that was
published rather than rebuilding the decision from the proposal that produced
it. Everything the CDDL says about units, frames and the time reference holds
here unchanged.

## Topic and type

| Property | Value |
| --- | --- |
| Topic | `/clave/pick_decisions` |
| Type | `vision_msgs/msg/Detection3DArray` |
| Reliability | Reliable |
| History | Keep last, depth 10 |
| Durability | Volatile |
| Frame | Named per run in `configs/runtime/sitl.yml`, `runtime.belt_frame` |

One message carries one decision, in `detections[0]`. The array type is used
rather than a bare `Detection3D` so a later version can publish several
decisions for one frame without changing the topic's type.

A standard message type is used rather than a message package defined here, so
a consumer needs nothing from this repository to subscribe, and `ros2 topic
echo`, `rosbag` and RViz all work without a plugin.

**Durability is volatile on purpose.** A decision names a window during which an
object is reachable, so a late subscriber that received a decision from a
previous run would be told to reach for an object that left the belt minutes
ago. A subscriber that starts late receives the next decision rather than the
last one.

## The mapping

Writing `d` for `detections[0]`:

| Field | Carries | Unit |
| --- | --- | --- |
| `header.frame_id`, `d.header.frame_id` | The frame every coordinate is in | Name |
| `header.stamp`, `d.header.stamp` | The instant the object becomes reachable, from the pick window | Seconds and nanoseconds on the system monotonic clock |
| `d.id` | The identity the tracker assigned | Decimal string |
| `d.results[0].hypothesis.class_id` | Material class | Taxonomy identifier, `M-01` to `M-11` |
| `d.results[0].hypothesis.score` | Classifier confidence behind that class | 0.0 to 1.0 |
| `d.results[0].pose.pose.position` | The pick point | Meters in the named frame |
| `d.results[0].pose.pose.orientation` | The pick yaw, as a rotation about the frame's z axis | Quaternion |
| `d.results[1].hypothesis.class_id` | The channel the operator's mapping resolved | `channel:<n>` |
| `d.results[1].hypothesis.score` | Always `1.0` | Routing is deterministic |
| `d.bbox.center` | The pick point again, so a viewer shows it | Meters |
| `d.bbox.size.x` | How long the object stays reachable | Seconds |

`d.results[0].pose.covariance` and `d.bbox.size.y`, `d.bbox.size.z` are zero.
CLAVE estimates neither a pose covariance nor an object extent, and a zero says
so more honestly than a fabricated number.

## Two hypotheses, read by prefix

A `Detection3D` carries a list of labeled hypotheses, and CLAVE asserts two
things about an object: what it is made of, and where it goes. Both are
published, and neither can be derived from the other.

The reason is the reject path. An object the classifier is unsure of keeps its
material class and is routed to the reject channel, so a decision can read
`M-01` and `channel:0` at once. A consumer that recomputed the channel from the
class would send that bottle to the PET bin, which is the failure the confidence
floor exists to prevent.

Read the list by prefix rather than by index:

| Prefix | Meaning |
| --- | --- |
| `M-` | A material class from `docs/waste-taxonomy.md` |
| `channel:` | A channel number from the operator's mapping |

The two prefixes are disjoint by construction: taxonomy identifiers are
`M-NN`, and the taxonomy's own channel names are `CH-*`, which this contract
does not use because the decision carries the operator's channel number rather
than a name.

## What a subscriber should check

1. **The frame.** Act only on the frame you were configured for. A pick point in
   the wrong frame is a collision.
2. **The window.** `header.stamp` is when the object becomes reachable and
   `bbox.size.x` is how long it stays so. A decision whose window has closed by
   the time it arrives should be discarded, not executed.
3. **The clock.** Every time in this contract is the Linux system monotonic
   clock, shared between processes on one machine and meaningless on another.
   A subscriber on a different machine cannot compare these values to its own.
4. **The channel.** Route by `channel:<n>`, never by recomputing from the class.

## What this contract does not carry

An object extent, a segmentation mask, a grasp width, a pose covariance, and any
statement about how the decision was reached. A subscriber that needs the full
decision including the contract version reads the CBOR on the Unix datagram,
which is the authoritative encoding.

## Worked example

The nominal golden vector, `vectors/v1/nominal.hex`, published on this topic and
read back with `ros2 topic echo`:

```yaml
header: {stamp: {sec: 9, nanosec: 0}, frame_id: belt}
detections:
- header: {stamp: {sec: 9, nanosec: 0}, frame_id: belt}
  results:
  - hypothesis: {class_id: M-01, score: 0.9399999976158142}
    pose:
      pose:
        position: {x: 0.412, y: -0.085, z: 0.031}
        orientation: {x: 0.0, y: 0.0, z: 0.49991445538358353, w: 0.866074787358768}
  - hypothesis: {class_id: 'channel:3', score: 1.0}
  bbox:
    center: {position: {x: 0.412, y: -0.085, z: 0.031}}
    size: {x: 0.25, y: 0.0, z: 0.0}
  id: '4815162342'
```

A PET bottle at 0.412 m along the belt, 0.085 m to one side, rotated 1.047
radians about the belt normal, routed to channel 3, reachable from monotonic
second 9 for a quarter of a second.

The coordinates exercise the encoding rather than describe a pick anybody could
make. In the belt frame `z` is measured from the floor, so this vector's
`z = 0.031` sits well below a belt surface at 0.90 and the safety layer would
refuse it on `belt_surface`. That is deliberate: these bytes are frozen and test
a decoder, and a vector whose numbers were adjusted to stay plausible as the
line's geometry changed would prove nothing about either.
