# Research and Design Decisions

## Summary

- **Feature**: `pick-decision-contract`
- **Discovery Scope**: New Feature, full discovery
- **Key Findings**:
  - No published source reports a p99 for local delivery of a small
    message. Every available number is a median, a mean, or a 95th
    percentile, so the 5 ms budget in Requirement 4 has to be defended by
    a benchmark this project runs, not by a citation.
  - JSON cannot satisfy Requirement 2.2. With default features it lost one
    unit in the last place on 29 percent of random f64 values, and it
    cannot represent NaN or infinity at any setting.
  - Positional binary formats corrupt silently when a producer runs ahead
    of a consumer, which is the exact failure Requirement 2.3 exists to
    prevent.

## Research Log
### Transport selection for local delivery

- **Context**: Requirement 3 commits to ordered, exactly-once delivery to a
  consumer process with a discard-oldest overflow policy, and Requirement 4
  sets a 5 ms p99 publication budget. The requirements phase deliberately
  deferred the mechanism to this phase.
- **Sources consulted**:
  - [Linux IPC Shootout](https://victoranderssen.com/blog/linux-ipc-benchmark/),
    1 May 2026: median round-trip at 128 bytes, shared memory 430 ns,
    Unix datagram 4,800 ns, Unix stream 7,740 ns. Method is sound
    (`CLOCK_MONOTONIC_RAW`, pinned cores, 200 warmup and 5000 timed
    rounds); it does not state its hardware, which is its weakness.
  - [IPC in Rust ping-pong](https://3tilley.github.io/posts/simple-ipc-ping-pong/),
    12 June 2024: mean per operation on Linux, shared memory 0.173 us,
    pipes 4.80 us, UDP 9.12 us, TCP 10.93 us.
  - [iceoryx2 benchmarks](https://github.com/eclipse-iceoryx/iceoryx2/blob/main/benchmarks/README.md):
    vendor self-benchmark, average with a busy-wait receiver, 64 KB
    payload, iceoryx2 240 ns against Unix domain socket 23,000 ns.
  - [rusty-comms](https://github.com/redhat-performance/rusty-comms): emits
    p50, p95, p99, and p99.9, but publishes no results, only expected
    ranges in its README.
  - [Kronauer et al., ROS 2 multi-node latency](https://www.barkhauseninstitut.org/fileadmin/user_upload/Publikationen/2021/2021_Kronauer_Latency.pdf),
    2021: 95th percentile, sub-millisecond at 3 nodes on a desktop, rising
    toward 4 ms at 23 nodes, and 15 to 20 ms on a Raspberry Pi class board.
- **Findings**:
  - No source publishes a p99 for local delivery of a small message. Every
    number above is a median, a mean, or a 95th percentile. The evidence
    orders the candidates; it does not size the budget.
  - At 100 to 300 bytes, a Unix stream round-trip median near 7.7 us is
    roughly 4 us one way, under 0.1 percent of the 5 ms budget. Scheduler
    wake-up, page faults, and allocator behavior dominate the tail long
    before the transport choice does.
  - iceoryx2 0.9.3 (MIT or Apache-2.0, updated 8 July 2026) is the fastest
    option and the only one with native discard-oldest, but its POSIX layer
    pulls `bindgen` and `cc` as build dependencies, so every build machine
    needs a C compiler and libclang.
  - The ZeroMQ and nanomsg bindings are stale: `zmq` 0.10.0 last published
    November 2022, `nng` 1.0.1 December 2021, and the pure-Rust `zeromq`
    0.6.0 is described by its own upstream as not production ready.
  - ROS 2 from Rust cannot be exercised in continuous integration without
    provisioning a ROS 2 install, a discovery daemon, and multicast.
  - A Unix socket can be tested in process with `UnixStream::pair()`, no
    broker and no hardware, which is what Requirement 5 needs from every
    test in this repository.
- **Implications**: Unix domain socket in `SOCK_SEQPACKET` mode, behind a
  narrow sink trait, with the discard-oldest ring in front of the transport
  rather than inside it. Record boundaries then come from the kernel, which
  deletes the framing bug class a length-prefixed stream would introduce,
  and one overflow policy with one counter serves every backend.
### Serialization format and float fidelity

- **Context**: Requirement 2.2 demands that every field survive a
  serialize and deserialize round trip with its value and precision
  intact, and Requirements 2.4 through 2.6 require a contract a consumer
  can implement without reading this repository's source.
- **Sources consulted**: a harness built and run on this machine on
  11 September 2026 against a struct matching the decision shape, release
  build, over 5,000 random finite f64 values, 4,986 random finite f32
  values, and edge values; plus
  [rust_serialization_benchmark](https://github.com/djkoloski/rust_serialization_benchmark)
  regenerated 10 September 2026,
  [RFC 8949](https://www.rfc-editor.org/rfc/rfc8949.html),
  [RFC 8610](https://www.rfc-editor.org/rfc/rfc8610.html), the
  [MessagePack specification](https://github.com/msgpack/msgpack/blob/master/spec.md),
  the [postcard wire format](https://postcard.jamesmunns.com/wire-format),
  and [serde-rs/json#707](https://github.com/serde-rs/json/issues/707).
- **Findings**:
  - Speed does not decide this. The slowest candidate measured 861 ns per
    round trip, which is 0.017 percent of the 5 ms budget. Message sizes
    ranged from 44 bytes (postcard) to 172 bytes (JSON).
  - JSON with default features lost precision on 1,448 of 5,000 f64 values,
    each off by one unit in the last place. The non-default
    `float_roundtrip` feature brought failures to zero. JSON also cannot
    carry NaN or infinity at all: the encoder writes `null` and the decoder
    then rejects it.
  - A 64-bit nanosecond timestamp read by a JavaScript consumer through
    `JSON.parse` is silently wrong above 2^53 - 1.
  - Positional formats corrupt silently across a version skew. With a field
    inserted mid-structure, postcard and bincode both decoded a V2 message
    into a V1 structure with no error and wrong values. Named formats
    rejected or decoded correctly.
  - bincode is unmaintained. Version 3.0.0, published 16 December 2025,
    contains only a `compile_error!`, and the repository is archived.
  - The two leading Rust CBOR crates are not interoperable in one
    direction. ciborium 0.2.2 emits the shortest lossless float encoding
    under RFC 8949 preferred serialization, so an f64 of 1.0 leaves as a
    half-float, and cbor4ii 1.2.3 rejects that tag. cbor4ii keeps fixed
    width, and its output decodes in ciborium and in any RFC 8949 library.
  - A fieldless enum serializes as its variant name in JSON, CBOR, and
    MessagePack, and as a positional index in postcard and bincode, where
    reordering variants silently remaps every label.
  - An explicit integer version field is the only mechanism tested that
    turns a producer running ahead of a consumer into a deterministic
    rejection. Serde attributes such as `default`, `alias`, and `other`
    buy tolerant reads, which converts a contract break into a silent
    default and works against Requirement 2.3.
- **Implications**: CBOR through cbor4ii, fixed width floats, named
  fields, string-named class variants, an explicit version as the first
  field, and a published CDDL schema with golden vectors. JSON is excluded
  by 2.2 on the float result alone, postcard and bincode by the silent
  skew and by bincode being dead.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks and limitations | Notes |
| --- | --- | --- | --- | --- |
| Policy in front of transport | A bounded ring owning the discard policy and counters, with a narrow sink trait behind it | One policy and one counter for every backend; the policy is testable with no syscalls | The seam has one real implementation today | Selected |
| Policy inside each transport | Each backend implements its own overflow behavior | Uses a backend's native discard, such as the one iceoryx2 offers | Requirement 3.3 would be re-implemented and re-proved per backend, and a silent drop in one backend would go unnoticed | Rejected |
| Messaging library | Adopt ZeroMQ or nanomsg for queueing and delivery | Patterns already built | Bindings last published in 2022 and 2021, a C system dependency, and drops that are hard to count | Rejected |
| Middleware contract | Publish on a ROS 2 topic | A sibling already speaks it | Cannot run in continuous integration without a discovery daemon and multicast, and it is a heavy dependency this repository forbids before a spec calls for it | Rejected here, revisit at the system boundary |

## Design Decisions

### Decision: Unix domain socket in SOCK_SEQPACKET mode

- **Context**: Requirement 3 needs ordered delivery to a separate process,
  Requirement 4 sets a 5 ms p99 budget, and Requirement 5 requires every
  test to run with no hardware.
- **Alternatives considered**:
  1. Shared memory through iceoryx2, roughly twenty times faster.
  2. ZeroMQ or nanomsg.
  3. ROS 2 from Rust.
- **Selected approach**: A Unix domain socket in `SOCK_SEQPACKET` mode
  behind the sink trait, with one implementation and one in-memory fake.
- **Rationale**: At the message size this contract carries, the transport
  spends under 0.1 percent of the budget, so the choice is decided by
  testability and dependency weight rather than by speed. The socket needs
  no unsafe code, no C toolchain, and no broker, and `UnixStream::pair()`
  drives it inside a single test process. `SOCK_SEQPACKET` takes record
  boundaries from the kernel, which removes the framing bug class that a
  length-prefixed stream introduces.
- **Trade-offs**: Roughly 4 microseconds one way rather than roughly 0.2,
  and a copy per message rather than a loaned buffer.
- **Follow-up**: Measure p99 and p99.9 on the target board before the
  budget is treated as met. If the socket turns out to be the constraint,
  a second sink implementation is the intended response.

### Decision: CBOR through cbor4ii, with fixed width floats

- **Context**: Requirement 2.2 requires lossless round trips including
  precision, and Requirements 2.4 through 2.6 require a contract a
  consumer implements without reading this source.
- **Alternatives considered**:
  1. JSON, universally readable.
  2. MessagePack through rmp-serde, one float encoding per width and one
     maintained crate.
  3. postcard, the smallest and fastest measured.
- **Selected approach**: CBOR encoded by cbor4ii, named fields, class
  variants carried as their names, floats at fixed width.
- **Rationale**: JSON is excluded by the measured float loss and by its
  inability to carry NaN or infinity. postcard is excluded because a field
  inserted mid-structure decoded into wrong values with no error, which
  defeats Requirement 2.3. CBOR carries an IETF standard number and a
  schema language in CDDL, which is what Requirement 2.4 has to point a
  consumer at.
- **Trade-offs**: 114 bytes and 410 nanoseconds against postcard's 44
  bytes and 130 nanoseconds, which is 0.008 percent of the budget.
- **Follow-up**: Golden vectors guard the encoding, because the strongest
  argument against CBOR is that its own Rust ecosystem disagrees on float
  width. ciborium output does not decode in cbor4ii. This project produces
  with cbor4ii, whose output decodes everywhere, so the asymmetry runs in
  the project's favor, and the vectors are what proves it still does.

### Decision: An explicit version field, rejected on mismatch

- **Context**: Requirement 2.3 requires a version raise when the shape or
  the class set changes, and 2.6 requires stated behavior for a consumer
  meeting a version it does not know.
- **Alternatives considered**:
  1. Tolerant reads through serde `default`, `alias`, and `other`.
  2. A schema language alone, with no version in the message.
- **Selected approach**: A mandatory version as the first field, and a
  consumer that rejects an entire message carrying a version it does not
  know.
- **Rationale**: Tolerant reads turn a contract break into a silent
  default, which is the opposite of the visible, coordinated change the
  requirement asks for. Rejecting on the version also makes an unrecognized
  class impossible in an accepted message, because the message never
  reaches the class field.
- **Trade-offs**: A producer upgraded ahead of its consumer stops that
  consumer rather than degrading it. That is the intended behavior on a
  line where a wrong pick is worse than no pick.
- **Follow-up**: The contract documentation states this rule, so a consumer
  author does not invent a tolerant reader.

### Decision: Three crates on a straight dependency line

- **Context**: The feature carries a wire type, a routing policy, and a
  delivery mechanism, which are three separate reasons to change.
- **Alternatives considered**:
  1. One crate holding all three.
  2. Two crates, folding routing into delivery.
- **Selected approach**: `clave-decision` holds the type, the codec, and
  the schema and depends on nothing in the workspace. `clave-routing`
  resolves a class to a channel. `clave-publish` queues and delivers.
- **Rationale**: The contract crate stays free of input and output and of
  policy, which is what lets its version move independently. Routing and
  delivery are different pipeline stages and a reviewer should be able to
  see a change to one without reading the other.
- **Trade-offs**: Three manifests rather than one, for a first feature.
- **Follow-up**: If routing stays a map lookup after the pipeline grows, it
  folds back without touching the contract.

### Decision: The time reference is the system monotonic clock

- **Context**: Requirement 2.4 requires a stated time reference, and
  Requirement 1.4 puts two timestamps in every decision.
- **Selected approach**: Nanoseconds on the Linux system monotonic clock,
  shared between processes on one machine and valid within one boot.
- **Rationale**: A monotonic reading cannot jump backward when the wall
  clock is corrected, and the transport already limits a consumer to the
  same machine, so a machine-local reference costs nothing today.
- **Trade-offs**: The reference stops being meaningful the moment a
  consumer moves to another machine.
- **Follow-up**: Recorded as a revalidation trigger in the design.

## Risks and Mitigations

- The 5 ms budget rests on no published p99. Mitigation: a Criterion
  benchmark reports p99 and fails above the budget, and the number is
  re-measured on the target board before anyone calls Requirement 4 met.
- The two leading Rust CBOR crates disagree on float width. Mitigation:
  golden vectors committed per schema version, decoded by the test suite
  on every run.
- A decision that grows to carry an image crop breaks the small-message
  premise the transport choice rests on. Mitigation: an open question in
  the design proposing a maximum encoded size, for the maintainer to
  accept or drop at the design gate.
- A consumer author may write a tolerant reader out of habit and defeat
  the version rule. Mitigation: the published contract states the rejection
  rule, and a golden vector carries an unknown version for a consumer to
  test against.

## References

- [RFC 8949, Concise Binary Object Representation](https://www.rfc-editor.org/rfc/rfc8949.html), the wire format.
- [RFC 8610, CDDL](https://www.rfc-editor.org/rfc/rfc8610.html), the schema language the contract ships in.
- [MessagePack specification](https://github.com/msgpack/msgpack/blob/master/spec.md), the rejected alternative's float encoding.
- [postcard wire format](https://postcard.jamesmunns.com/wire-format), the positional format that skewed silently.
- [serde-rs/json#707](https://github.com/serde-rs/json/issues/707), the JSON float precision issue reproduced here.
- [rust_serialization_benchmark](https://github.com/djkoloski/rust_serialization_benchmark), third-party size and speed comparison, regenerated 10 September 2026.
- [Linux IPC Shootout](https://victoranderssen.com/blog/linux-ipc-benchmark/), median local transport latencies, 1 May 2026.
- [ROS 2 multi-node latency, Kronauer et al.](https://www.barkhauseninstitut.org/fileadmin/user_upload/Publikationen/2021/2021_Kronauer_Latency.pdf), 95th percentile figures for the rejected middleware.
