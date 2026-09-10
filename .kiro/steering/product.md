# Product Overview

CLAVE sorts recyclable waste traveling on a conveyor belt. A camera
watches the line, a neural network classifies each object, a tracker
follows it across frames, and the pipeline decides which channel the
object belongs in and when to reach for it, inside a latency budget the
system measures rather than assumes.

The name expands to Coleta de Lixo Através de Visão Embarcada, Portuguese
for embedded-vision waste collection, which places the project in the same
family as arco, fret, luthier, and bossa.

## Core Capabilities

- **Classification behind a contract.** The model identifies the material
  class of each object. It is a replaceable component, not the center of
  the system.
- **Multi-object tracking.** Objects keep an identity across frames,
  including when they overlap or pass behind one another.
- **Position prediction.** The pipeline predicts where an object will be
  when the effector reaches it, rather than reporting where the camera saw
  it.
- **A measured latency budget.** Capture to pick command is budgeted and
  measured at p99, with explicit backpressure when inference falls behind.
- **Pick scheduling.** Channel assignment, contention between two objects
  arriving together, and a defined destination for low-confidence objects.

## Target Use Cases

A recycling sorting line where a fixed camera observes a moving belt and a
downstream effector removes objects into per-material channels. The belt
speed and the effector reach set the budget the pipeline has to hold.

## Value Proposition

The classifier is the easy half. Classifying an object on a belt is a
solved exercise with public datasets, and a model on its own sorts
nothing. The engineering sits in the deterministic pipeline around it,
which is where Rust earns its place and where every requirement worth
specifying lives.

## Boundaries

CLAVE decides what to pick and when, then publishes that decision. Motion
planning belongs to ARCO, and effector trajectories belong to FRET. Sibling
projects are reached through a published contract; their source trees are
never vendored into this repository.

---
_Focus on patterns and purpose, not exhaustive feature lists_
