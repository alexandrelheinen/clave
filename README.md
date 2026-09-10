# CLAVE

<img src="docs/images/clave.svg" alt="CLAVE Logo" width="120" align="left">

**CLAVE** = **C**oleta de **L**ixo **A**través de **V**isão **E**mbarcada

CLAVE sorts recyclable waste travelling on a conveyor belt. A camera watches
the line, a neural network classifies each object, a tracker follows it
across frames, and the pipeline decides which channel it belongs in and when
to reach for it, all inside a latency budget it measures rather than
assumes. Models train in Python and ship as ONNX; everything that runs
against the clock is Rust.

<br clear="left">

*Clave* is Portuguese for the musical clef, which places the project in the
same family as **arco**, **fret**, **luthier**, and **bossa**.

## What this project is about

The classifier is the easy half. Classifying an object on a belt is a
solved exercise with public datasets, and a model on its own proves
nothing. The engineering sits in the deterministic pipeline around it:

- Predicting where an object will be when the effector reaches it, rather
  than where the camera saw it.
- Tracking objects across frames, including overlapping and occluded ones.
- Holding a latency budget from capture to pick command, measured at p99,
  with explicit backpressure when inference falls behind.
- Scheduling picks: which channel, what happens when two objects arrive
  together, and where low-confidence objects go.

That is where Rust earns its place, and the classifier becomes a
replaceable component behind a contract.

## Status

No application code has landed yet. The first crate lands with the first
specification.

## Ecosystem

CLAVE is one project in a family that shares a method and a set of
guidelines. Contracts point at siblings; source trees are never vendored
between them.

| Project | Role |
| --- | --- |
| **CLAVE** (this repo) | Perception, tracking, and pick decision under a latency budget |
| **[ARCO](https://github.com/alexandrelheinen/arco)** | Motion planning and control algorithms |
| **[FRET](https://github.com/alexandrelheinen/fret)** | ROS 2 and MuJoCo effector trajectories |
| **[Luthier](https://github.com/alexandrelheinen/luthier)** | Photogrammetry and point clouds |
| **[BOSSA](https://github.com/alexandrelheinen/bossa)** | Edge runtime and telemetry on ARM Linux |

Motion belongs to ARCO and FRET. CLAVE decides what to pick and when, and
publishes that decision.

## Repository layout

| Path | Contents |
| --- | --- |
| [CONTRIBUTING.md](CONTRIBUTING.md) | The constitution: quality gates, merge policy, agent rules |
| [docs/guidelines.md](docs/guidelines.md) | Coding notes specific to CLAVE, on top of the shared baseline |
| [standards/](standards/README.md) | Shared guidelines, the SDD method, and the agent toolchain |
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
