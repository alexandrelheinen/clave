# Product Overview

CLAVE learns and executes a perception-action policy for sorting recyclable
waste on a moving conveyor belt. A neural architecture fuses visual
perception, object tracking, and pick timing into an end-to-end learned
policy trained via imitation and reinforcement learning. The policy runs
under hard safety constraints enforced by a Rust core that handles hardware
interlocks and collision prevention.

The name expands to Coleta de Lixo Através de Visão Embarcada, Portuguese
for embedded-vision waste collection, which places the project in the same
family as arco, fret, luthier, and bossa.

## Core Capabilities

- **Learned perception-action policy.** The system maps visual streams
  directly to pick coordinates and timing through an end-to-end neural
  policy, replacing handcoded decision rules.
- **Neural tracking.** Objects maintain identity across frames through
  learned representations, handling severe occlusion and overlapping
  geometries without explicit geometric heuristics.
- **Spatial-temporal reasoning.** The policy reasons over continuous
  representations of conveyor state, not discrete frame snapshots, predicting
  where objects will be when reached.
- **Safety-constrained inference.** Neural decisions are always checked
  against hard safety constraints enforced in Rust: collision checks,
  actuator limits, and hardware interlocks prevent unsafe actions.
- **Robust learning.** The policy is trained via domain randomization in
  MuJoCo simulation to bridge the gap between simulation and real conveyor
  dynamics, object slip, and lighting variations.

## Target Use Cases

A recycling sorting line where a fixed camera observes a moving belt and a
downstream effector removes objects into per-material channels. The belt
speed, object properties, and effector constraints shape the policy's
learned behavior.

## Value Proposition

The easy problem is pattern recognition on images. The hard problem is
learning what to pick, when to pick it, and how to do so reliably under
physical variation. CLAVE solves this by training a policy that learns
robust pick decisions through interaction with simulation. The hybrid
architecture, learned inference plus deterministic safety, is where Rust
earns its place and where every safety-critical requirement lives.

## Boundaries

CLAVE learns a policy and executes it with safety guarantees. Policy training
runs in FRET's MuJoCo simulation, and FRET is also the consumer of the
decision CLAVE publishes: its planner nodes call ARCO as a synchronous
library, so CLAVE does not address ARCO directly. BOSSA carries telemetry in
a later hardware era and has no role in the simulation line. Sibling projects
are reached through published contracts; their source trees are never vendored
into this repository.

---
_Focus on patterns and purpose, not exhaustive feature lists_
