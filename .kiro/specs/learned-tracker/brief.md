# Brief: learned-tracker

## Problem

`perception-record` builds everything the perception contract describes except
the one rule that makes a track a track: which observation belongs to which
object. Its only association implementation reads the simulator's object id, so
identity is still ground truth and the record it produces is honest about
saying so.

This spec supplies the rule, and it supplies it as a learned model rather than
as a geometric gate. The reason is the one the README already states: CLAVE
exists to learn a perception-action policy, and tracking networks that hold an
identity through occlusion and overlap without geometric heuristics are named in
its list of what it is for. A hand-tuned distance threshold is the thing the
project set out not to build.

## Current State

The model sees a physical state rather than pixels. It is given, per candidate
pairing, the object's footprint, the proposed pick point, a barcode when one
decoded, and the previous state of the track. It learns the association and the
update. That framing is the maintainer's, and it is what keeps the model
grounded in quantities the safety layer can also reason about.

Three platform gaps stand between here and a trained model, one fewer than a
first reading suggests.

`Stage` in `src/clave/candidates/base.py` has exactly two values, `PERCEPTION`
and `POLICY`. There is no tracking stage, so the registry has nowhere to put a
tracking candidate and `configs/runtime/sitl.yml` has no key naming a tracking
checkpoint.

`clave.training.objectives` has no objective for association, and
`clave.training.adapters` has no batch builder that pairs consecutive frames.

The fourth gap is not a gap. Recorded rollouts under `datasets/synthetic`
already carry, per frame, every object's `object_id`, `position`, `bbox` and
capture time, with identity stable across the frames of one rollout. That is
the supervision an association model needs, so the correspondence is derivable
from data already on disk and the recorder does not change.

One measured fact sets the difficulty. Captures are 0.5 s apart and the belt
runs at about 0.31 m/s, so an object moves roughly 0.157 m between consecutive
observations while the objects themselves are 0.05 m to 0.10 m across. An
object's successive detections do not overlap, which is why propagation by belt
speed is the input that makes the problem learnable and why nearest-neighbour
matching on raw positions would not be.

## Desired Outcome

A trained tracking candidate holds one identity across the frames of one
rollout, derived from observation rather than read from the simulator. It
reports what it does when two objects pass each other or touch and segment as
one, rather than leaving that undefined. The runtime consumes `WasteObject` and
no longer calls `associate()`.

The model is measured against the ground-truth associator `perception-record`
ships, so the report says how much of the simulator's identity the model
actually recovered.

## Approach

Open the three platform gaps, then train against them.

`Stage.TRACKING` joins the enum, the registry gains tracking candidates, and the
runtime configuration gains the key that names a tracking checkpoint. A training
adapter pairs consecutive frames from existing rollouts, using `object_id` as
the correspondence label and nothing else from it. An objective scores the
association, and the trainer runs it through the same one-command path every
other candidate uses.

The model consumes the physical state and not the frame, so it is small, it
trains on data already recorded, and its inputs are quantities that appear in
`WasteObject` rather than activations that do not.

It lands behind the association protocol `perception-record` defines, which is
what makes the contract's own claim true: swapping the tracker changes nothing
downstream, provided it still emits `WasteObject`.

## Scope

- **In**: `Stage.TRACKING` and the registry entries, the runtime checkpoint key,
  the frame-pairing training adapter, the association objective, at least one
  trained tracking candidate with recorded numbers, the stated outcome for
  crossing and merged objects, the runtime swap away from `associate()`, and the
  comparison against the ground-truth associator.
- **Out**: the contract types, the adapters and the fusion rules, all of which
  are `perception-record`. Retraining perception or policy, which `D-12` records
  as a separate model change. The end effector. The object set, settled by
  `D-11`.

## Boundary Candidates

- The registry and configuration change, which is platform work and touches no
  model.
- The dataset adapter and the objective, which are training work and produce no
  runtime behavior.
- The trained candidate itself.
- The runtime swap, which is the only part that changes what the loop publishes.

## Out of Boundary

- Reinforcement learning. Every trained model in CLAVE is supervised and this
  one is too.
- Occlusion handling beyond what a single layer under a nadir camera produces.
- Any claim about real-world tracking accuracy, because nothing here runs on
  hardware.

## Upstream / Downstream

- **Upstream**: `perception-record` for the association protocol, the record and
  the evidence. `model-candidates` for the candidate interface.
  `learning-platform` for reproducibility. `data-pipeline` for the rollouts this
  trains on.
- **Downstream**: `benchmark-suite`, which gains a tracking row.
  `validation-harness`, which gains an identity metric.

## Existing Spec Touchpoints

- **Extends**: `model-candidates`, which owns `Stage` and the registry.
  `training-application`, which owns the objectives and the adapters.
  `sitl-runtime`, which owns `associate()` and the loop that calls it.
- **Adjacent**: `validation-harness` and `benchmark-suite` both report on this
  but neither is changed by it beyond gaining a number.

## Constraints

- **The model consumes a physical state, not a frame.** Footprint, pick point,
  optional code, and previous track state. This is the maintainer's framing and
  it is what keeps the inputs auditable.
- **Identity is derived, never copied.** `object_id` is a training label and
  never an input at inference, and a test has to prove it.
- **The swap is invisible downstream.** Nothing above the association protocol
  changes, which is the property `docs/perception-contract.md` asks for in its
  change table.
- **Nothing is claimed on an agent's word.** A candidate is trained when
  `./scripts/validate.sh` exits 0 and the numbers are recorded, per the roadmap's
  own rule.
- **The comparison is published even when it is unflattering.** `D-12` is the
  precedent: a working loop running a mostly wrong model is reported as that.
