# Decisions

An append-only log of places where a gate or a constraint was deliberately
scoped, loosened, or changed, with the reason. Anyone asking "why is this weaker
than the standards say" should find the answer here.

Entries are never edited once landed. A decision that is reversed gets a new
entry saying so.

## D-01: the candidate adapters are outside the coverage denominator

**Date**: 2026-09-14 · **Step**: v0.4.0 `model-candidates`

**The standard**: `workflow/tdd.md` gates line coverage at 80 to 90 percent on
core library code and forbids lowering a gate to make CI pass.

**What was scoped**: `src/clave/candidates/perception.py` and
`src/clave/candidates/policy.py` are omitted from the coverage denominator. The
80 percent floor is unchanged and applies to everything else.

**Why**: those two modules are adapter shims. Each function is two or three
lines calling an upstream constructor, and none can execute without PyTorch,
torchvision, lerobot, diffusers or stable-baselines3, which together exceed a
gigabyte. The gate deliberately does not install them, because the platform's
contract is that the registry is readable and the rest of the system testable
without any of them.

Testing them with mocks would assert that a constructor was called with the
arguments the test passed it, which proves nothing about whether the
architecture loads. Their real test is the benchmark sweep, which loads every
one from upstream and whose output is committed as
[docs/research/model-candidates.md](research/model-candidates.md).

**What is not scoped**: `tests/candidates/adapters_test.py` does exercise the
adapters through `pytest.importorskip`, so on a machine with the libraries
installed they run. They simply do not count toward the floor, because a
coverage number that swings by fifteen points depending on whether an optional
library happens to be present measures the environment rather than the tests.

**Reversal condition**: if the candidate libraries ever become required rather
than optional, this entry is superseded and the modules return to the
denominator.

## D-02: the decision socket is an AF_UNIX datagram rather than SOCK_SEQPACKET

**Date**: 2026-09-14 · **Step**: `pick-decision-contract`, which is off the v0.x ladder

**The standard**: the approved design for `pick-decision-contract` selects a
Unix domain socket in `SOCK_SEQPACKET` mode, opened through
`std::os::unix::net`, and forbids a third-party transport dependency.

**What was scoped**: `clave-publish` opens an `AF_UNIX` socket in `SOCK_DGRAM`
mode instead, through `std::os::unix::net::UnixDatagram`.

**Why**: the standard library exposes no way to open a `SOCK_SEQPACKET`
socket. `std::os::unix::net` gives `UnixStream` for `SOCK_STREAM` and
`UnixDatagram` for `SOCK_DGRAM`, and nothing else. Opening a seqpacket socket
means calling `socket(AF_UNIX, SOCK_SEQPACKET, 0)` through `libc`, which brings
both a third-party dependency the design forbids and an `unsafe` block into a
crate that declares `#![forbid(unsafe_code)]`.

Every property the transport choice rested on survives the substitution. An
`AF_UNIX` datagram socket on Linux is reliable, delivers in order, and keeps
one record per send, so record boundaries still come from the kernel and the
framing bug class a length-prefixed stream would introduce is still absent. It
is testable in process through `UnixDatagram::pair()`, which is what the
no-hardware constraint needs.

**What is not scoped**: the sink trait, the discard policy in front of it, and
the counters are unchanged, so a later seqpacket or shared-memory sink slots in
behind the same seam without touching the policy.

**What changes**: a datagram socket is connectionless, so a departed consumer
surfaces as `ECONNREFUSED` where a seqpacket socket would report a broken
connection. Both map to a refusal, which is the behavior the requirement asks
for either way.

**Reversal condition**: if the standard library gains seqpacket support, or if
a measurement on the target board shows the datagram path is the constraint,
the sink is replaced behind the existing trait and this entry is superseded.

## D-03: the confidence field is float32 on the wire

**Date**: 2026-09-14 · **Step**: `pick-decision-contract`, which is off the v0.x ladder

**The standard**: the approved design names `Confidence(f32)` in its Rust
interface and `float64` in its data contract table. The two cannot both hold.

**What was scoped**: the wire carries the confidence as a CBOR four byte float,
matching the Rust type. The published CDDL schema and the golden vectors say
`float32`, and the design's table row is superseded.

**Why**: widening to `float64` on the wire would make decoding lossy in the
narrowing direction, and Rust offers no checked `f64` to `f32` conversion, so
the codec would need an `as` cast in a crate where `clippy::as_conversions` is
denied. Keeping one width end to end costs four bytes per message and keeps the
round trip exact, which is what the round trip requirement asks for. Every
other float in the contract stays `float64`.

**Reversal condition**: a classifier that genuinely reports confidence at
double precision. Widening the field raises the contract version, the same as
any other shape change.
