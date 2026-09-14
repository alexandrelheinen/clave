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
DEFAULT_GATES = Path("configs/validation/gates.yml")


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


def _world_probe(root: Path, seconds: float, seed: int) -> int:
    """Build the sorting world, run it, and report its reachability budget.

    Args:
        root: Repository root.
        seconds: Simulated seconds to run.
        seed: Seed for belt speed, placement and spawn timing.

    Returns:
        A process exit code. Non-zero when the belt never enters the arm's
        reach, which would make the world useless for picking.
    """
    import mujoco
    import numpy as np

    from clave.world import belt, config, scene

    raw = config.load(root / "configs" / "world" / "sorting_line.yml")
    rng = np.random.default_rng(seed)
    model, data, plan = scene.build(raw, rng, root)
    spawn = config.require(raw, "spawn")
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "interval_seconds", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(config.require(spawn, "entry_margin_meters", "spawn")),
    )
    report = conveyor.report
    print(f"  reach radius      {report.reach_radius:.3f} m")
    print(f"  belt offset       {report.belt_offset:.3f} m")
    print(f"  reachable window  {report.window_length:.3f} m")
    print(f"  belt speed        {report.belt_speed:.3f} m/s")
    print(f"  time budget       {report.time_budget:.3f} s per object")
    print(f"  channels          {len(plan.channels)} bins")

    for _ in range(int(seconds / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)

    print(f"  simulated         {data.time:.2f} s")
    print(f"  spawned           {len(conveyor.active)}")
    print(f"  entered window    {len(conveyor.entered_window())}")
    if not report.reachable:
        print("  FAILED   the belt never enters the arm's reach")
        return 1
    return 0


def _validate_run(root: Path, outcomes: Path, gates: Path | None) -> int:
    """Score recorded outcomes against the configured gates and print a report.

    Args:
        root: Repository root.
        outcomes: The records file to score.
        gates: The gate configuration, defaulting to the committed one.

    Returns:
        A process exit code. Non-zero when any gate is unmet, because an unmet
        gate is a failure rather than a number in a table.
    """
    from clave.validation.gates import GateConfig
    from clave.validation.outcomes import load_outcomes
    from clave.validation.report import ValidationReport

    report = ValidationReport.build(
        load_outcomes(outcomes),
        GateConfig.load(gates if gates is not None else root / DEFAULT_GATES),
    )
    print(report.render())
    return 0 if report.passed else 1


def _record_dataset(root: Path, out: Path, seed: int) -> int:
    """Record rollouts, split them, and write a described dataset.

    Args:
        root: Repository root.
        out: Directory to write the dataset into.
        seed: Base seed; each rollout uses a derived seed.

    Returns:
        A process exit code.
    """
    from clave.data import dataset, splits
    from clave.data.recorder import record
    from clave.world import config

    raw = config.load(root / "configs" / "data" / "recording.yml")
    rec = config.require(raw, "recording")
    proportions = {
        name: float(value) for name, value in config.require(raw, "splits").items()
    }
    count = int(config.require(rec, "rollouts", "recording"))

    rollouts = []
    for index in range(count):
        rollouts.append(
            record(
                root=root,
                seed=seed + index,
                seconds=float(config.require(rec, "seconds_per_rollout", "recording")),
                capture_interval_seconds=float(
                    config.require(rec, "capture_interval_seconds", "recording")
                ),
                height=int(config.require(rec, "frame_height", "recording")),
                width=int(config.require(rec, "frame_width", "recording")),
                rollout_id=f"rollout_{index:03d}",
            )
        )
        print(f"  recorded rollout_{index:03d}: {len(rollouts[-1].examples)} examples")

    plan = splits.split(tuple(r.rollout_id for r in rollouts), proportions, seed)
    description = dataset.write(
        out, tuple(rollouts), plan.parts, seed, rollouts[0].examples[0].config_digest
    )

    print(f"  digest            {description.digest[:16]}...")
    print(f"  examples          {description.example_count}")
    for name in ("train", "validation", "test", "overall"):
        part = description.composition[name]
        absent = list(part["absent_classes"])  # type: ignore[call-overload]
        present = dict(part["class_counts"])  # type: ignore[call-overload]
        print(
            f"  {name:16s}  {part['example_count']:4d} frames, "
            f"{len(present)} classes present, {len(absent)} absent"
        )
    return 0


def _train(root: Path, config_path: Path, candidate: str | None) -> int:
    """Train one candidate from a configuration file.

    Args:
        root: Repository root.
        config_path: Path to the training configuration.
        candidate: Overrides the candidate named in the file.

    Returns:
        A process exit code. Non-zero when the candidate could not be loaded.
    """
    from clave.training.config import TrainingConfig
    from clave.training.runner import train

    config = TrainingConfig.load(root / config_path, candidate)
    run = train(config, config.window_exit_meters)
    if run.unavailable_reason is not None:
        print(f"  UNAVAILABLE  {config.candidate}: {run.unavailable_reason}")
        return 1
    print(f"  candidate     {run.candidate}")
    print(f"  machine       {run.machine}, {run.threads} threads")
    print(f"  dataset       {run.dataset_digest[:16]}...")
    for epoch in run.epochs:
        print(
            f"  epoch {epoch.index:2d}      loss {epoch.loss:10.4f}   "
            f"{epoch.seconds:8.1f} s"
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
    world = sub.add_parser("world-probe", help="build the sorting world and report it")
    world.add_argument("--seconds", type=float, default=12.0)
    world.add_argument("--seed", type=int, default=0)
    rec = sub.add_parser("record-dataset", help="record a labeled dataset")
    rec.add_argument("--out", type=Path, default=Path("datasets/synthetic"))
    rec.add_argument("--seed", type=int, default=0)
    tr = sub.add_parser("train", help="train a candidate from a configuration")
    tr.add_argument("--config", type=Path, default=Path("configs/training/default.yml"))
    tr.add_argument("--candidate", type=str, default=None)
    validate = sub.add_parser(
        "validate-run", help="score recorded outcomes against the validation gates"
    )
    validate.add_argument("--outcomes", type=Path, required=True)
    validate.add_argument("--gates", type=Path, default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == "verify-manifest":
            return _verify_manifest(args.root)
        if args.command == "check-research":
            return _check_research(args.root)
        if args.command == "bench-candidates":
            return _bench_candidates(args.warmup, args.repetitions)
        if args.command == "world-probe":
            return _world_probe(args.root, args.seconds, args.seed)
        if args.command == "record-dataset":
            return _record_dataset(args.root, args.out, args.seed)
        if args.command == "train":
            return _train(args.root, args.config, args.candidate)
        if args.command == "validate-run":
            return _validate_run(args.root, args.outcomes, args.gates)
        return _record(args.root, args.name, args.path)
    except ClaveError as exc:
        print(f"  FAILED   {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
