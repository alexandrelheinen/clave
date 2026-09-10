# CLAVE-specific coding notes

The shared baseline for Rust and Python style, naming, and error handling
lives in
[standards/guidelines/languages/rs.md](../standards/guidelines/languages/rs.md)
and
[standards/guidelines/languages/py.md](../standards/guidelines/languages/py.md).
This file covers only what is specific to CLAVE. Method, gates, and merge
policy live in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Language split

Rust owns anything that runs against the clock: capture, inference,
tracking, and the pick decision. Python owns training and dataset work,
and hands over an ONNX artifact. A Python process is never in the loop at
runtime.

## Hardened by default

The pipeline crates are real-time crates, so they take the hardened lint
tier from
[languages/rs.md](../standards/guidelines/languages/rs.md#hardened-for-real-time-unsafe-and-ffi-crates)
rather than the baseline. A frame index that silently wraps or a cast that
silently truncates is a fault in this domain, not a style question.

Tooling crates, dataset preparation, and anything that runs offline take
the baseline tier.

## Latency is a tested property

Anything in the capture-to-decision path states its latency budget in its
crate documentation and has a Criterion benchmark under `benches/`. A
change that moves a budget is a spec change, not an implementation detail.

Measure at p99, not at the mean. A pipeline that averages well and misses
one frame in a hundred still drops that object on the floor.

## Backpressure is explicit

Every queue between stages is bounded, and every bounded queue names what
happens when it fills: block, drop the oldest, or drop the newest. There
is no default. A stage that cannot state its policy is not designed yet.

## Model artifacts

ONNX files are not committed to this repository. Reference a model by
version and checksum, and fetch it in a script. Datasets are public ones
(TrashNet, TACO, ZeroWaste) referenced by URL, never vendored.

## Contracts toward siblings

CLAVE publishes a pick decision. Motion planning and execution belong to
[ARCO](https://github.com/alexandrelheinen/arco) and
[FRET](https://github.com/alexandrelheinen/fret). Define the contract as a
serializable type in CLAVE and let the consumer adapt to it; do not import
a sibling's types and do not vendor a sibling's source.
