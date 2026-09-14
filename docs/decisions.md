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
