"""Command entry points the gate calls.

The gate calls a stable command rather than a module path, so internal layout
can change without editing shell.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clave.corpus.artifacts import record_digest, verify
from clave.corpus.manifest import Manifest
from clave.errors import ClaveError
from clave.research.tables import check_all

DEFAULT_MANIFEST = Path("corpora/manifest.toml")


def _verify_manifest(root: Path) -> int:
    """Parse the manifest and verify every artifact present locally.

    An unverified entry is reported, not failed: most corpora are large and are
    fetched by an operator rather than by a gate.

    Args:
        root: Repository root.

    Returns:
        A process exit code.
    """
    manifest = Manifest.load(root / DEFAULT_MANIFEST)
    failures = 0
    for name, artifact in sorted(manifest.artifacts.items()):
        local = root / artifact.source
        if not local.is_file():
            print(f"  remote   {name}: not fetched locally")
            continue
        result = verify(artifact, local)
        if result.available:
            print(f"  ok       {name}")
        else:
            print(f"  FAILED   {name}: {result.status.value}")
            failures += 1
    return 1 if failures else 0


def _check_research(root: Path) -> int:
    """Check the research documents against their declared schemas.

    Args:
        root: Repository root.

    Returns:
        A process exit code.
    """
    problems = check_all(root)
    for problem in problems:
        print(f"  FAILED   {problem}")
    if not problems:
        print("  ok       research tables match their schemas")
    return 1 if problems else 0


def _record(root: Path, name: str, path: Path) -> int:
    """Report the digest of a local artifact for review.

    Args:
        root: Repository root.
        name: Artifact name in the manifest.
        path: Where the bytes are stored locally.

    Returns:
        A process exit code.
    """
    manifest = Manifest.load(root / DEFAULT_MANIFEST)
    print(record_digest(manifest[name], path))
    print("Review this digest, then add it to the manifest by hand.", file=sys.stderr)
    return 0


def _bench_candidates(warmup: int, repetitions: int) -> int:
    """Load and benchmark every shortlisted candidate, printing a table.

    Args:
        warmup: Untimed iterations per candidate.
        repetitions: Timed iterations per candidate.

    Returns:
        A process exit code. Zero even when a candidate is unavailable, since a
        missing optional dependency is a normal state on this hardware.
    """
    from clave.candidates.registry import sweep

    print(
        f"{'candidate':28s} {'stage':11s} "
        f"{'params':>10s} {'median':>12s} {'spread':>10s}"
    )
    for spec, result, note in sweep(warmup=warmup, repetitions=repetitions):
        if result is None or result.median_latency_seconds is None:
            print(
                f"{spec.name:28s} {spec.stage.value:11s} "
                f"{'-':>10s} {'-':>12s} {'-':>10s}  {note}"
            )
            continue
        print(
            f"{spec.name:28s} {spec.stage.value:11s} "
            f"{result.parameter_count / 1e6:9.2f}M "
            f"{result.median_latency_seconds * 1000:11.1f}ms "
            f"{(result.spread_seconds or 0) * 1000:9.1f}ms"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run a CLAVE command.

    Args:
        argv: Arguments, defaulting to the process arguments.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(prog="clave", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-manifest", help="verify every locally present artifact")
    sub.add_parser("check-research", help="check research document table schemas")
    record = sub.add_parser("record-digest", help="report a digest for review")
    record.add_argument("name")
    record.add_argument("path", type=Path)
    bench = sub.add_parser(
        "bench-candidates", help="load and benchmark every candidate"
    )
    bench.add_argument("--warmup", type=int, default=3)
    bench.add_argument("--repetitions", type=int, default=10)

    args = parser.parse_args(argv)
    try:
        if args.command == "verify-manifest":
            return _verify_manifest(args.root)
        if args.command == "check-research":
            return _check_research(args.root)
        if args.command == "bench-candidates":
            return _bench_candidates(args.warmup, args.repetitions)
        return _record(args.root, args.name, args.path)
    except ClaveError as exc:
        print(f"  FAILED   {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
