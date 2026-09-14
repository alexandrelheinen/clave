# CLAVE

<img src="docs/images/clave.svg" alt="CLAVE Logo" width="120" align="left">

**CLAVE** = **C**oleta de **L**ixo **A**través de **V**isão **E**mbarcada

CLAVE sorts recyclable waste traveling on a conveyor belt through a learned
perception-action policy. A neural architecture fuses visual perception,
object tracking, and pick timing into an end-to-end system trained via
imitation and reinforcement learning. The policy runs against the clock with
hard safety guarantees: a Rust core handles hardware interlocks and emergency
stops, while neural inference provides perception and decision-making. Models
train in Python and MuJoCo simulation; optimized inference runs on the BOSSA
edge runtime.

<br clear="left">

*Clave* is Portuguese for the musical clef, which places the project in the
same family as **arco**, **fret**, **luthier**, and **bossa**.

## What this project is about

The hard problem is not classification—it is learning a policy that maps
visual streams to physical actions. Classifying an object on a belt is a
solved exercise; predicting what to pick, when to pick it, and where to
route it under conveyor motion, variable material properties, and hardware
constraints is where the engineering lives.

CLAVE addresses this by replacing handcoded scheduling rules with a learned
policy network trained end-to-end:

- **Neural perception**: Continuous spatial-temporal representations of the
  conveyor state, replacing frame-by-frame snapshots.
- **Learned tracking**: Neural tracking networks that handle severe
  occlusion, illumination changes, and overlapping objects without
  geometric heuristics.
- **Policy learning**: A perception-action loop trained via imitation
  learning on human demonstrations and reinforcement learning in MuJoCo
  simulation, learning robust pick timing under physical variation.
- **Hybrid safety**: Neural inference handles perception and decision-making,
  while a Rust safety layer enforces hard interlocks and collision checks,
  ensuring the physical system never enters an unsafe state.

The split between learned policy and deterministic safety is where Rust
earns its place, and the perception pipeline becomes a replaceable
component behind a contract.

## Status

No application code has landed yet. The first crate lands with the first
specification.

## Ecosystem

CLAVE is one project in a family that shares a method and a set of
guidelines. Contracts point at siblings; source trees are never vendored
between them.

| Project | Role |
| --- | --- |
| **CLAVE** (this repo) | Learned perception-action policy, safety interlocks |
| **[ARCO](https://github.com/alexandrelheinen/arco)** | Motion planning for continuous trajectory waypoints |
| **[FRET](https://github.com/alexandrelheinen/fret)** | Training environment, kinematic constraints, reward functions |
| **[Luthier](https://github.com/alexandrelheinen/luthier)** | Photogrammetry for sim-to-real calibration |
| **[BOSSA](https://github.com/alexandrelheinen/bossa)** | Edge inference runtime, neural telemetry logging |

CLAVE learns and executes a perception-to-action policy. FRET provides the
training environment and kinematic constraints for policy learning. ARCO
receives continuous trajectory waypoints from CLAVE and executes them. BOSSA
runs neural inference on ARM hardware and logs activation patterns and
latency metrics. Luthier supplies calibration data for sim-to-real transfer.

## Repository layout

| Path | Contents |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | The constitution: quality gates, merge policy, agent rules |
| [docs/guidelines.md](docs/guidelines.md) | Coding notes specific to CLAVE, on top of the shared baseline |
| [standards/](standards/README.md) | Shared guidelines, the SDD method, and the agent toolchain |
| `.kiro/` | Committed specifications and the steering documents agents read as project memory |
| `scripts/` | Toolchain setup and the local quality gate |

## Getting started

```bash
git clone --recurse-submodules https://github.com/alexandrelheinen/clave.git
cd clave
./scripts/setup.sh
./scripts/validate.sh
```

If the clone already exists without submodules, run
`git submodule update --init --recursive` first.

## License

MIT. See [LICENSE](LICENSE).
