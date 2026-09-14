# Requirements Document

## Project Description (Input)

v0.9.0 closed the loop inside CLAVE: a frame leaves the simulator, inference
proposes, the Rust safety layer disposes, and a decision is published on a Unix
datagram in the contract's CBOR encoding. Nothing outside CLAVE can hear it.

This step puts the decision on ROS 2, which is the middleware FRET runs on, in a
form FRET's pick-and-place state machine can consume. It stops there. CLAVE
gains no planner, no controller and no second simulator, because FRET already
has all three and a second copy in this family would be a liability rather than
an asset.

The scope was set on 2026-09-15 after reading FRET rather than assuming it.
FRET is a ROS 2 Jazzy stack running OpenMANIPULATOR-X and OpenMANIPULATOR-Y
pick-and-place in MuJoCo, with ARCO planning and a joint-space controller
behind it. Its `PickPlaceObservation` takes an object position and a flag that
starts a cycle, and `PickPlaceWaypoints.with_pick` exists so a vision estimate
can replace the pick pose. CLAVE's decision substitutes for the ball pose
FRET's own camera pipeline supplies today.

## Introduction

One property decides whether this step is worth having: a subscriber that has
never read CLAVE's source must be able to act on what it receives. That means
the topic, the message type, the frame, the units and the meaning of every
field are written down, and a test proves a subscriber receives what the
document describes.

## Boundary Context

- **In scope**: the ROS 2 topic, the message type and the field mapping; the
  node that publishes it; its documentation; the seam in the runtime that feeds
  it.
- **Out of scope**: anything that plans, moves or grasps. A conveyor scene in
  FRET. Changes to FRET. The decision contract itself, which is merged and is
  consumed rather than redesigned. Hardware.
- **Adjacent expectations**: FRET does not subscribe to this topic today,
  because its manipulator pipeline builds `PickPlaceObservation` in process
  rather than from a subscription. The subscriber is FRET's to write, in FRET's
  repository, and this specification is what it writes against. Nothing here
  claims the arm moved.

## Traceability

Acceptance criteria use `AC-<AREA>-<NN>`, continuing the project scheme, with
areas `ROSPUB` and `ROSMAP`. Ids are append-only and neither area collides with
an existing spec.

## Requirements

### Requirement 1: Publication

**Objective:** As the engineer writing the subscriber in FRET, I want CLAVE's
decision to arrive on a ROS 2 topic, so that the integration is a message rather
than a subsystem.

#### Acceptance Criteria

1. The Publisher shall publish one message per decision the runtime publishes,
   on a named ROS 2 topic. `AC-ROSPUB-01`
2. The Publisher shall take its decisions from the bytes the runtime published
   rather than from the proposal that produced them, so the ROS view and the
   contract cannot diverge. `AC-ROSPUB-02`
3. When ROS 2 is not installed, the Runtime shall run the loop and say that
   nothing was published rather than failing. `AC-ROSPUB-03`
4. When a published decision cannot be decoded, the Publisher shall report it
   and continue rather than terminating. `AC-ROSPUB-04`
5. The Publisher shall state its topic, message type and quality of service in
   documentation a consumer can implement against without reading CLAVE's
   source. `AC-ROSPUB-05`

### Requirement 2: The field mapping

**Objective:** As that same engineer, I want every field of the decision to
arrive with its unit, its frame and its meaning intact, so that a subscriber can
act on it without guessing.

#### Acceptance Criteria

1. The Publisher shall carry the object identity, the material class, the
   classifier confidence, the resolved channel and the pick point in one
   message. `AC-ROSMAP-01`
2. The Publisher shall name the coordinate frame the pick point is expressed in.
   `AC-ROSMAP-02`
3. The Publisher shall carry the pick window, so a subscriber can tell whether a
   decision it received is still actionable. `AC-ROSMAP-03`
4. The Publisher shall distinguish a material class from a channel in the
   message rather than requiring a consumer to resolve one from the other,
   because a low-confidence object carries a class and a reject channel at the
   same time. `AC-ROSMAP-04`
5. The Publisher shall use a standard ROS 2 message type rather than defining
   one, so a consumer needs no interface package from this repository.
   `AC-ROSMAP-05`
