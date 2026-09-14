# The decision, on ROS 2

> Roadmap step: v0.10.0 · Spec: [.kiro/specs/decision-publisher/](../../.kiro/specs/decision-publisher/)

v0.9.0 closed the loop inside CLAVE and left the decision on a Unix datagram
where nothing outside this repository could hear it. This step puts it on ROS 2,
which is the middleware FRET runs on, and stops there.

Nothing here plans, moves or grasps. That is the point rather than an omission,
and the reasoning is in the roadmap: FRET already has a pick-and-place state
machine, a joint-space controller and ARCO planning behind them, all running
against the same OpenMANIPULATOR arms CLAVE simulates. A second copy in this
family would be a liability.

## What was read before anything was written

The scope came from reading FRET rather than assuming it.

| What FRET has | Where |
| --- | --- |
| A ROS 2 Jazzy stack with OM-X and OMY pick-and-place in MuJoCo physics | `src/fret/control/`, `src/fret/ros/` |
| A robot-agnostic `PickPlaceFSM` taking an object position and a flag that starts a cycle | `src/fret/control/pick_place_fsm.py` |
| `PickPlaceWaypoints.with_pick`, written so an estimate can replace the pick pose | The same file |
| A camera pipeline producing that estimate today | `src/fret/vision/` |

CLAVE's decision substitutes for the pose FRET's own camera pipeline supplies.
That is the slot, and it is the reason this step is a message rather than a
subsystem.

**One fact changes what could be promised.** FRET builds its
`PickPlaceObservation` inside in-process simulation runners rather than from a
subscription, so **no FRET topic exists to publish into**. The subscriber is
FRET's to write, in FRET's repository, and
[ros-decision.md](../../crates/clave-decision/contract/ros-decision.md) is what
it writes against. Nothing below claims an arm moved.

## What is published

One `vision_msgs/msg/Detection3DArray` per decision on `/clave/pick_decisions`.
A standard message type rather than one defined here, so a subscriber needs
nothing from this repository and the ordinary ROS tools work with no plugin.
The mapping, the quality of service and the two documented reuses of a field are
in the contract; `D-06` in [decisions.md](../decisions.md) records why the type
was chosen and what it costs.

The publisher decodes the CBOR the runtime published rather than rebuilding the
message from the proposal that produced the decision. Rebuilding would have been
easier and would have created a second path free to drift from the contract with
no test noticing. The Python decoder is checked against the committed golden
vectors, which is the same check a consumer in another language runs before it
sees a live decision.

## What was measured

A full loop run at seed 0, 20 simulated seconds, with an independent
`ros2 topic echo` subscribed throughout. ROS 2 Jazzy, sourced from
`/opt/ros/jazzy`.

| Quantity | Value |
| --- | --- |
| Frames captured | 40 |
| Proposals | 31 |
| Overridden by the safety layer | 7, all on reach |
| Decisions published by the runtime | 24 |
| Decisions that arrived back on the Unix datagram | 24 |
| Decisions put on the ROS 2 topic | 24 |
| Messages an independent subscriber captured | 24 |

Four counts of the same 24 decisions, taken at four points in the chain,
agreeing. That is what this step set out to prove.

What the subscriber saw, without having read any CLAVE source:

| Property | Observed |
| --- | --- |
| Distinct object identities | 8 |
| Material classes | `M-01`, `M-02`, `M-03`, `M-05`, `M-06`, `M-10` |
| Channels | `channel:1`, `channel:2`, `channel:3`, `channel:5`, `channel:6`, `channel:8` |
| Frame | `belt`, on every message |

Every class-to-channel pair matches `configs/runtime/sitl.yml`, so the routing
the Rust resolver performed is observable from outside the process that
performed it. The window duration in `bbox.size.x` shrank from 1.36 s to 0.94 s
across consecutive decisions about one object, which is the object travelling
toward the far edge of the reachable window at the configured belt speed.

Latency from frame capture to published decision was a median of 0.9 ms and a
p99 of 2.7 ms for the scripted expert, against 0.46 ms and 7.04 ms for the same
predictor without ROS at v0.9.0. Both runs are 31 proposals, which is too few
for either p99 to mean much, and the ROS publication happens after the
measurement stops. What can be said is that adding the publisher did not move
the loop into a different regime.

## Running without ROS

`clave run-sitl --ros` on a machine with no ROS installation runs the loop,
reports that nothing was published and why, and exits zero:

```
  decisions back  7
  published       0 on ROS 2
  NO ROS          rclpy is not importable. Source a ROS 2 installation, such as: source /opt/ros/jazzy/setup.bash
```

A missing consumer is not a reason to refuse to decide. The same holds for a
decision ROS refuses to carry after a context shuts down: it is counted and
named rather than raised out of the loop.

## What is tested, and where

| Test | Runs where |
| --- | --- |
| The golden vectors decode into every documented field | Everywhere |
| An unknown contract version is refused by version | Everywhere |
| Bytes that are not a decision are reported rather than raised | Everywhere |
| Every field reaches the message, with the frame, the window and the yaw | Everywhere |
| The runtime hands every published decision to its sink, and the sink's bytes decode | Wherever the runtime builds |
| A subscriber on a real ROS graph receives the documented fields | Only where ROS is installed |
| A publication ROS refuses is counted | Only where ROS is installed |

The mapping is computed before ROS is involved, which is why most of it is
testable on a machine with no installation. **The gate has no ROS installation,
so the last two skip there.** They were run here against Jazzy, and the counts
in this document come from that run. A reader who wants to repeat it sources a
distribution and runs the suite with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, because
ROS ships pytest plugins that a current pytest refuses to load.

## What this does not show

**FRET has no subscriber.** Nothing in FRET changed, and nothing proves the
mapping is usable in anger until FRET writes one. The contract document is the
mitigation and it is a weak one; the strong version is a pull request against
FRET, which is outside this step's boundary.

**No arm moved.** A decision reaching a topic is not a pick. Cycle time, from
decision to placement, stays unmeasured, and v1.0.0's benchmark will report it
as unmeasured rather than substituting a number from a controller CLAVE wrote to
measure itself.

**The conveyor scene is still CLAVE's alone.** FRET's manipulator scenes are
tabletop, and a belt carrying moving objects is the theme of its v1.5. Until
that exists, a decision published here describes a world FRET cannot yet
simulate.

**Nothing measures the hop.** The latency figures stop when the decision is
published on the Unix datagram. What the ROS publication, the middleware and a
subscriber add to that is unmeasured, and on a real line it is the number that
would matter.

**Nothing ran on hardware.** There is no camera, no belt and no arm on this
machine.
