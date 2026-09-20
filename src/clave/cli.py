"""Command entry points the gate calls.

The gate calls a stable command rather than a module path, so internal layout
can change without editing shell.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from clave.corpus.artifacts import record_digest, verify
from clave.corpus.manifest import Manifest
from clave.errors import ClaveError

DEFAULT_MANIFEST = Path("corpora/manifest.toml")
DEFAULT_GATES = Path("configs/validation/gates.yml")
LOGGER = logging.getLogger(__name__)


def _log_output(*values: object, file: Any = None) -> None:
    """Write command output through logging and write to standard streams."""
    level = logging.WARNING if file is sys.stderr else logging.INFO
    LOGGER.log(level, " ".join(str(value) for value in values))
    print(*values, file=file if file is not None else sys.stdout)


def _configure_logging(level: str) -> None:
    """Configure the process-wide log level selected by the operator."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.debug("logging configured at %s", level.upper())


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
            _log_output(f"  remote   {name}: not fetched locally")
            continue
        result = verify(artifact, local)
        if result.available:
            _log_output(f"  ok       {name}")
        else:
            _log_output(f"  FAILED   {name}: {result.status.value}")
            failures += 1
    return 1 if failures else 0


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
    _log_output(record_digest(manifest[name], path))
    _log_output(
        "Review this digest, then add it to the manifest by hand.", file=sys.stderr
    )
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

    _log_output(
        f"{'candidate':28s} {'stage':11s} "
        f"{'params':>10s} {'median':>12s} {'spread':>10s}"
    )
    for spec, result, note in sweep(warmup=warmup, repetitions=repetitions):
        if result is None or result.median_latency_seconds is None:
            _log_output(
                f"{spec.name:28s} {spec.stage.value:11s} "
                f"{'-':>10s} {'-':>12s} {'-':>10s}  {note}"
            )
            continue
        _log_output(
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
        config.require_range(spawn, "spacing_meters", "spawn"),
        config.require_range(spawn, "lateral_offset_meters", "spawn"),
        config.require_range(spawn, "drop_height_meters", "spawn"),
        entry_margin=float(config.require(spawn, "entry_margin_meters", "spawn")),
    )
    report = conveyor.report
    _log_output(
        f"  reach annulus     {report.reach_min:.3f} to {report.reach_max:.3f} m"
    )
    _log_output(f"  belt offset       {report.belt_offset:.3f} m")
    _log_output(f"  reachable window  {report.window_length:.3f} m")
    _log_output(f"  belt speed        {report.belt_speed:.3f} m/s")
    _log_output(f"  time budget       {report.time_budget:.3f} s per object")
    _log_output(f"  channels          {len(plan.channels)} chutes")

    for _ in range(int(seconds / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)

    _log_output(f"  simulated         {data.time:.2f} s")
    _log_output(f"  spawned           {len(conveyor.active)}")
    _log_output(f"  entered window    {len(conveyor.entered_window())}")
    if not report.reachable:
        _log_output("  FAILED   the belt never enters the arm's reach")
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
    _log_output(report.render())
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
        _log_output(
            f"  recorded rollout_{index:03d}: {len(rollouts[-1].examples)} examples"
        )

    plan = splits.split(tuple(r.rollout_id for r in rollouts), proportions, seed)
    description = dataset.write(
        out, tuple(rollouts), plan.parts, seed, rollouts[0].examples[0].config_digest
    )

    _log_output(f"  digest            {description.digest[:16]}...")
    _log_output(f"  examples          {description.example_count}")
    for name in ("train", "validation", "test", "overall"):
        part = description.composition[name]
        absent = list(part["absent_classes"])  # type: ignore[call-overload]
        present = dict(part["class_counts"])  # type: ignore[call-overload]
        _log_output(
            f"  {name:16s}  {part['example_count']:4d} frames, "
            f"{len(present)} classes present, {len(absent)} absent"
        )
    return 0


def _train(
    root: Path,
    config_path: Path,
    candidate: str | None,
    sync: bool = False,
) -> int:
    """Train one candidate from a configuration file.

    Args:
        root: Repository root.
        config_path: Path to the training configuration.
        candidate: Overrides the candidate named in the file.
        sync: Upload checkpoint to R2 and register run in D1 on completion.

    Returns:
        A process exit code. Non-zero when the candidate could not be loaded.
    """
    from clave.training.config import TrainingConfig
    from clave.training.runner import train

    config = TrainingConfig.load(root / config_path, candidate)
    run = train(config, config.window_exit_meters)
    if run.unavailable_reason is not None:
        _log_output(f"  UNAVAILABLE  {config.candidate}: {run.unavailable_reason}")
        return 1
    _log_output(f"  candidate     {run.candidate}")
    _log_output(f"  machine       {run.machine}, {run.threads} threads")
    _log_output(f"  dataset       {run.dataset_digest[:16]}...")
    for epoch in run.epochs:
        _log_output(
            f"  epoch {epoch.index:2d}      loss {epoch.loss:10.4f}   "
            f"{epoch.seconds:8.1f} s"
        )
    if sync and run.completed:
        try:
            from clave.storage import (
                D1Client,
                R2Client,
                load_d1_config,
                load_r2_config,
                push_training_run,
            )
            from clave.training.runner import _checkpoint_path, run_record_path

            r2 = R2Client(load_r2_config())
            d1: D1Client | None = None
            try:
                d1 = D1Client(load_d1_config())
            except Exception as d1_err:
                _log_output(
                    f"  note     D1 tracking unavailable: {d1_err}", file=sys.stderr
                )

            ckpt_path = _checkpoint_path(config)
            rec_path = run_record_path(config.checkpoints, config.candidate)
            key = push_training_run(ckpt_path, rec_path, r2, d1)
            _log_output(f"  synced        checkpoint to R2: {key}")
        except Exception as exc:
            # Offline independence (AC-DATA-08)
            _log_output(
                f"  WARNING  remote sync failed: {exc}; local artifacts retained",
                file=sys.stderr,
            )
    return 0


def _benchmark(
    root: Path,
    config_path: Path,
    out: Path,
    sync: bool = False,
) -> int:
    """Run every configuration the benchmark names and report the comparison.

    Args:
        root: Repository root.
        config_path: The benchmark configuration.
        out: Where the evidence pack and the run directories go.
        sync: Upload evidence pack to R2 and register benchmark in D1 on completion.

    Returns:
        A process exit code. Non-zero when a gate the benchmark could evaluate
        was not met, because an unmet gate is a failure rather than a row in a
        table.
    """
    from clave.benchmark.config import BenchmarkConfig
    from clave.benchmark.pack import EvidencePack, score
    from clave.benchmark.suite import run_configuration
    from clave.candidates.bench import _machine
    from clave.corpus.artifacts import digest_of
    from clave.experiment.run import environment
    from clave.validation.gates import GateConfig

    config = BenchmarkConfig.load(root / config_path)
    gates = GateConfig.load(root / config.gates)
    machine, threads = _machine()

    scored = []
    for configuration in config.configurations:
        _log_output(f"  running         {configuration.name}")
        result = run_configuration(root, config, configuration, out / "runs")
        if not result.available:
            _log_output(f"  UNAVAILABLE     {result.unavailable_reason}")
        scored.append(score(result, gates))

    pack = EvidencePack(
        config=config,
        scored=scored,
        machine=machine,
        threads=threads,
        environment=environment(),
        world_digest=digest_of(root / "configs" / "world" / "sorting_line.yml"),
    )
    pack.write(out / "benchmark.json")
    _log_output(pack.render())
    _log_output(f"  evidence pack   {out / 'benchmark.json'}")
    if sync:
        try:
            from clave.storage import (
                D1Client,
                R2Client,
                load_d1_config,
                load_r2_config,
                push_benchmark,
            )

            r2 = R2Client(load_r2_config())
            d1: D1Client | None = None
            try:
                d1 = D1Client(load_d1_config())
            except Exception as d1_err:
                _log_output(
                    f"  note     D1 tracking unavailable: {d1_err}", file=sys.stderr
                )

            pack_key = push_benchmark(out / "benchmark.json", r2, d1)
            _log_output(f"  synced        evidence pack to R2: {pack_key}")
        except Exception as exc:
            # Offline independence (AC-DATA-08)
            _log_output(
                f"  WARNING  remote sync failed: {exc}; local artifacts retained",
                file=sys.stderr,
            )
    return 0 if pack.passed else 1


def _still(root: Path, name: str, out: Path) -> int:
    """Capture a still of the world and report where the frames went.

    Args:
        root: Repository root.
        name: Scenario name, matching a file under configs/stills/.
        out: Where the PNGs go.

    Returns:
        A process exit code.
    """
    from clave.demo.still import StillError, StillScenario, capture

    stills = root / "configs" / "stills"
    for candidate in (name, name.replace("-", "_")):
        path = stills / f"{candidate}.yml"
        if path.is_file():
            break
    else:
        available = sorted(
            entry.stem.replace("_", "-") for entry in stills.glob("*.yml")
        )
        raise StillError(f"no still named {name!r}. Available: {', '.join(available)}")
    scenario = StillScenario.load(path)
    _log_output(f"  {scenario.description}")
    written = capture(root, scenario, out)
    _log_output(
        f"  seed            {scenario.seed}, captured at "
        f"{scenario.capture_at_seconds:.2f} simulated seconds"
    )
    _log_output(f"  size            {scenario.width} x {scenario.height}")
    for file in written:
        _log_output(f"  wrote           {file}")
    return 0


def _dataset_push(root: Path, path: Path) -> int:
    """Push local dataset to Cloudflare R2 and register in D1 (AC-DATA-02, AC-DATA-04).

    Args:
        root: Repository root.
        path: Path to dataset directory.

    Returns:
        Exit code.
    """
    from clave.storage import (
        D1Client,
        R2Client,
        load_d1_config,
        load_r2_config,
        push_dataset,
    )

    r2_config = load_r2_config()
    r2 = R2Client(r2_config)

    d1: D1Client | None = None
    try:
        d1_config = load_d1_config()
        d1 = D1Client(d1_config)
    except Exception as exc:
        _log_output(f"  note     D1 registration unavailable: {exc}", file=sys.stderr)

    dataset_dir = root / path if not path.is_absolute() else path
    uploaded, skipped = push_dataset(dataset_dir, r2, d1)
    _log_output(f"  dataset push complete: {uploaded} uploaded, {skipped} skipped")
    return 0


def _dataset_pull(root: Path, digest: str, out: Path) -> int:
    """Pull a dataset from Cloudflare R2 by digest and verify locally (AC-DATA-03).

    Args:
        root: Repository root.
        digest: SHA-256 digest of dataset.
        out: Target directory.

    Returns:
        Exit code.
    """
    from clave.storage import R2Client, load_r2_config, pull_dataset

    r2_config = load_r2_config()
    r2 = R2Client(r2_config)

    destination = (root / out / digest) if not out.is_absolute() else (out / digest)
    description = pull_dataset(digest, destination, r2)
    _log_output(f"  verified dataset {description.digest[:16]}... in {destination}")
    _log_output(f"  examples        {description.example_count}")
    return 0


def _storage_init_db() -> int:
    """Initialize Cloudflare D1 tables for datasets, training runs, and benchmarks.

    Returns:
        Exit code.
    """
    from clave.storage import D1Client, load_d1_config

    d1_config = load_d1_config()
    d1 = D1Client(d1_config)
    d1.init_schema()
    _log_output("  database schema initialized in Cloudflare D1")
    return 0


def _runs_list(limit: int) -> int:
    """List historical training runs and benchmark scores from D1 (AC-DATA-07).

    Args:
        limit: Max entries per table.

    Returns:
        Exit code.
    """
    from clave.storage import D1Client, load_d1_config

    d1_config = load_d1_config()
    d1 = D1Client(d1_config)

    training_runs = d1.list_training_runs(limit=limit)
    benchmarks = d1.list_benchmarks(limit=limit)

    _log_output("Training Runs:")
    if not training_runs:
        _log_output("  no training runs recorded")
    else:
        _log_output(
            f"  {'run_id':28s} {'candidate':12s} {'epochs':>6s} {'loss':>10s} "
            f"{'created_at':19s}"
        )
        for r in training_runs:
            loss_val = r.get("final_loss")
            loss_str = f"{loss_val:.4f}" if loss_val is not None else "-"
            _log_output(
                f"  {str(r.get('run_id', '-')):28s} "
                f"{str(r.get('candidate', '-')):12s} "
                f"{str(r.get('epochs', '-')):>6s} "
                f"{loss_str:>10s} "
                f"{str(r.get('created_at', '-'))[:19]:19s}"
            )

    _log_output("Benchmarks:")
    if not benchmarks:
        _log_output("  no benchmarks recorded")
    else:
        _log_output(
            f"  {'benchmark_id':32s} {'configuration':20s} {'accuracy':>8s} "
            f"{'p99 ms':>8s} {'verdict':8s}"
        )
        for b in benchmarks:
            acc = b.get("overall_accuracy")
            acc_str = f"{acc:.3f}" if acc is not None else "-"
            p99 = b.get("decision_latency_p99_seconds")
            p99_str = f"{p99 * 1000:.1f}" if p99 is not None else "-"
            verdict = "PASSED" if b.get("passed") else "FAILED"
            _log_output(
                f"  {str(b.get('benchmark_id', '-')):32s} "
                f"{str(b.get('configuration_name', '-')):20s} "
                f"{acc_str:>8s} "
                f"{p99_str:>8s} "
                f"{verdict:8s}"
            )
    return 0


def _checkpoint_pull(
    root: Path,
    candidate: str,
    config_digest: str | None,
    dataset_digest: str | None,
    latest: bool,
    out: Path,
) -> int:
    """Pull model weights and run record from R2 (and D1 if latest).

    Args:
        root: Repository root.
        candidate: Candidate architecture name.
        config_digest: Optional hyperparameter digest.
        dataset_digest: Optional dataset digest.
        latest: Look up latest run in D1.
        out: Target directory (e.g. checkpoints/).

    Returns:
        Exit code.
    """
    from clave.storage import (
        D1Client,
        R2Client,
        load_d1_config,
        load_r2_config,
        pull_training_checkpoint,
        restore_latest_checkpoint,
    )

    r2 = R2Client(load_r2_config())
    destination = (root / out) if not out.is_absolute() else out

    if latest or not (config_digest and dataset_digest):
        d1 = D1Client(load_d1_config())
        ckpt, rec = restore_latest_checkpoint(candidate, destination, r2, d1)
    else:
        ckpt, rec = pull_training_checkpoint(
            candidate, config_digest, dataset_digest, destination, r2
        )

    _log_output(f"  restored checkpoint: {ckpt}")
    _log_output(f"  restored run record: {rec}")
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
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
        help="logging verbosity (default: INFO)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-manifest", help="verify every locally present artifact")
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

    # dataset subcommands
    ds = sub.add_parser("dataset", help="manage datasets in local and remote storage")
    ds_sub = ds.add_subparsers(dest="dataset_action", required=True)
    ds_push = ds_sub.add_parser("push", help="push a local dataset to R2 and D1")
    ds_push.add_argument("path", type=Path, help="path to local dataset directory")
    ds_pull = ds_sub.add_parser("pull", help="pull a dataset from R2 by digest")
    ds_pull.add_argument("digest", type=str, help="SHA-256 digest of dataset")
    ds_pull.add_argument(
        "--out", type=Path, default=Path("datasets"), help="destination directory"
    )

    # storage subcommands
    st = sub.add_parser("storage", help="storage operations")
    st_sub = st.add_subparsers(dest="storage_action", required=True)
    st_sub.add_parser("init-db", help="initialize D1 database schema")

    # runs subcommands
    rn = sub.add_parser("runs", help="view experiment and training runs")
    rn_sub = rn.add_subparsers(dest="runs_action", required=True)
    rn_list = rn_sub.add_parser("list", help="list historical runs and benchmarks")
    rn_list.add_argument("--limit", type=int, default=20, help="max rows to display")

    # checkpoint subcommands
    ck = sub.add_parser("checkpoint", help="manage trained model checkpoints")
    ck_sub = ck.add_subparsers(dest="checkpoint_action", required=True)
    ck_pull = ck_sub.add_parser("pull", help="pull a model checkpoint from R2")
    ck_pull.add_argument("candidate", type=str, help="candidate name (e.g. act)")
    ck_pull.add_argument(
        "--config-digest", type=str, default=None, help="config digest"
    )
    ck_pull.add_argument(
        "--dataset-digest", type=str, default=None, help="dataset digest"
    )
    ck_pull.add_argument(
        "--latest", action="store_true", help="restore latest recorded run from D1"
    )
    ck_pull.add_argument(
        "--out", type=Path, default=Path("checkpoints"), help="output directory"
    )

    tr = sub.add_parser("train", help="train a candidate from a configuration")
    tr.add_argument("--config", type=Path, default=Path("configs/training/default.yml"))
    tr.add_argument("--candidate", type=str, default=None)
    tr.add_argument(
        "--sync", action="store_true", help="upload checkpoint and record run in D1"
    )
    validate = sub.add_parser(
        "validate-run", help="score recorded outcomes against the validation gates"
    )
    validate.add_argument("--outcomes", type=Path, required=True)
    validate.add_argument("--gates", type=Path, default=None)
    bench_suite = sub.add_parser(
        "benchmark", help="compare every configuration in one table"
    )
    bench_suite.add_argument(
        "--config", type=Path, default=Path("configs/benchmark/default.yml")
    )
    bench_suite.add_argument("--out", type=Path, default=Path("runs/benchmark"))
    bench_suite.add_argument(
        "--sync", action="store_true", help="upload evidence pack and record in D1"
    )
    sim = sub.add_parser(
        "sim",
        help="run the sorting-line simulation",
        description=(
            "Run the sorting-line simulation. By default the tracker debug "
            "view is shown, annotating the rollout with markers and beliefs. "
            "Use --still to capture still frames instead."
        ),
    )
    sim.add_argument("--out", type=Path, default=Path("runs/debug/tracker"))
    sim.add_argument("--seconds", type=float, default=14.0)
    sim.add_argument("--seed", type=int, default=0)
    sim.add_argument("--no-window", action="store_true")
    sim.add_argument("--video", action="store_true")
    sim.add_argument(
        "--telemetry",
        action="store_true",
        help="write PlotJuggler-compatible CSV telemetry",
    )
    sim.add_argument(
        "--telemetry-rate",
        type=float,
        default=100.0,
        help="telemetry samples per simulated second (default: 100)",
    )
    sim.add_argument(
        "--telemetry-out",
        type=Path,
        default=None,
        help="telemetry CSV path (default: <out>/telemetry.csv)",
    )
    sim.add_argument(
        "--trajectory-seconds",
        type=float,
        default=2.0,
        help="future trajectory shown in the debug view (default: 2)",
    )
    sim.add_argument(
        "--log-level",
        dest="command_log_level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=None,
        help="logging verbosity (default: INFO)",
    )
    sim.add_argument(
        "--fps",
        type=int,
        default=None,
        help="playback rate, or the rate configs/debug/tracker.yml names",
    )
    sim.add_argument(
        "--view",
        default=None,
        help="which view in configs/debug/tracker.yml to film from",
    )
    sim.add_argument(
        "--still",
        nargs="?",
        const="thumbnail",
        default=None,
        metavar="SCENARIO",
        help=(
            "capture still frames instead of running the simulation. "
            "Names a scenario under configs/stills/ (default: thumbnail)"
        ),
    )
    sim.add_argument(
        "--still-out",
        type=Path,
        default=Path("runs/stills"),
        help="output directory for stills (used with --still)",
    )

    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "command_log_level", None) or args.log_level)
    LOGGER.debug(
        "parsed CLI arguments: command=%s root=%s log_level=%s",
        args.command,
        args.root,
        getattr(args, "command_log_level", None) or args.log_level,
    )
    try:
        if args.command == "verify-manifest":
            return _verify_manifest(args.root)
        if args.command == "bench-candidates":
            return _bench_candidates(args.warmup, args.repetitions)
        if args.command == "world-probe":
            return _world_probe(args.root, args.seconds, args.seed)
        if args.command == "record-dataset":
            return _record_dataset(args.root, args.out, args.seed)
        if args.command == "dataset":
            if args.dataset_action == "push":
                return _dataset_push(args.root, args.path)
            if args.dataset_action == "pull":
                return _dataset_pull(args.root, args.digest, args.out)
        if args.command == "storage" and args.storage_action == "init-db":
            return _storage_init_db()
        if args.command == "runs" and args.runs_action == "list":
            return _runs_list(args.limit)
        if args.command == "checkpoint" and args.checkpoint_action == "pull":
            return _checkpoint_pull(
                args.root,
                args.candidate,
                args.config_digest,
                args.dataset_digest,
                args.latest,
                args.out,
            )
        if args.command == "train":
            return _train(args.root, args.config, args.candidate, sync=args.sync)
        if args.command == "sim":
            if args.still is not None:
                return _still(args.root, args.still, args.still_out)
            return _debug_tracker(args.root, args)
        if args.command == "benchmark":
            return _benchmark(args.root, args.config, args.out, sync=args.sync)
        if args.command == "validate-run":
            return _validate_run(args.root, args.outcomes, args.gates)
        return _record(args.root, args.name, args.path)
    except ClaveError as exc:
        _log_output(f"  FAILED   {exc}", file=sys.stderr)
        return 1


def _debug_tracker(root: Path, args: Any) -> int:
    """Annotate a rollout with everything the tracker believes.

    A diagnostic rather than a demonstration. It drives `clave.tracker` directly
    because the tracker is deliberately not wired into the runtime loop yet, and
    every frame it writes says so.

    Args:
        root: Repository root.
        args: Parsed command line.

    Returns:
        Zero when the run completed.
    """
    from clave.tracker.debug_run import GRASPED_METERS, run

    LOGGER.debug(
        "sim parameters: seconds=%.3f (use sim --seconds to override), seed=%d, "
        "out=%s, video=%s, telemetry=%s, telemetry_rate=%.3f, "
        "trajectory_seconds=%.3f, window=%s, view=%s",
        args.seconds,
        args.seed,
        args.out,
        args.video,
        args.telemetry,
        args.telemetry_rate,
        args.trajectory_seconds,
        not args.no_window,
        args.view,
    )
    telemetry_path = None
    if args.telemetry:
        telemetry_path = args.telemetry_out or args.out / "telemetry.csv"
        if not telemetry_path.is_absolute():
            telemetry_path = root / telemetry_path
    report = run(
        root,
        out=args.out if args.out.is_absolute() else root / args.out,
        seconds=args.seconds,
        seed=args.seed,
        window=not args.no_window,
        video=args.video,
        fps=args.fps,
        view_name=args.view,
        telemetry_path=telemetry_path,
        telemetry_rate=args.telemetry_rate,
        trajectory_seconds=args.trajectory_seconds,
    )
    _log_output(f"  captures        {report.captures}")
    _log_output(f"  tracks open     {report.tracks}")
    _log_output(f"  markers on last {report.drawn}, as {report.geoms} geoms")
    rebuilt = ", ".join(f"{why} {count}" for why, count in report.reorders.items())
    _log_output(f"  queue rebuilt   {rebuilt}, of {report.captures} captures")
    _log_output(
        f"  head swapped    {report.head_churn} times with the old head still there"
    )
    _log_output(f"  profile         {report.profile}")
    _log_output(
        f"  feed rate       {report.measured_rate:.3f} of "
        f"{report.feed_rate:.3f} objects/s, belt at {report.belt_speed:.3f} m/s"
    )
    _log_output(f"  visits served   {len(report.served)} {list(report.served)}")
    if report.missed:
        _log_output(f"  no interception {len(report.missed)} {list(report.missed)}")
    if report.arrivals:
        # Median rather than mean, and the count of outliers beside it. The
        # mean lied: sixteen visits at 2 to 4 mm and one at 688 mm reads as
        # "43 mm", which describes no visit that happened.
        ranked = sorted(report.arrivals)
        middle = ranked[len(ranked) // 2] * 1000
        stray = sum(1 for gap in ranked if gap > 0.050)
        _log_output(
            f"  arrival error   median {middle:.1f} mm, worst "
            f"{ranked[-1] * 1000:.1f} mm, {stray} over 50 mm"
        )
    if report.jaw_gaps:
        each = ", ".join(f"{gap * 1000:.0f}" for gap in report.jaw_gaps)
        _log_output(f"  jaw to object   {each} mm when the jaw shut")
    if report.placed or report.misrouted:
        total = sum(report.placed.values())
        each = ", ".join(f"{c}: {n}" for c, n in sorted(report.placed.items()))
        _log_output(f"  placed          {total} down a chute ({each})")
        _log_output(f"  misrouted       {report.misrouted} of {total}")
    if report.lifts:
        held = sum(1 for lift in report.lifts if lift >= GRASPED_METERS)
        each = ", ".join(f"{lift * 1000:.0f}" for lift in report.lifts)
        _log_output(f"  grasps held     {held} of {len(report.lifts)}, lifts {each} mm")
    _log_output(f"  faults          {len(report.faults)}")
    for track_id, why in report.faults:
        _log_output(f"    track {track_id}: {why}")
    _log_output(f"  ended in        {report.phase}")
    if report.closest_approach is not None:
        _log_output(f"  to commanded    {report.closest_approach * 1000:.0f} mm")
    if report.closest_live is not None:
        _log_output(f"  to the object   {report.closest_live * 1000:.0f} mm")
    _log_output(f"  frames written  {report.frames_written} to {report.output}")
    if report.video_path is not None:
        _log_output(f"  video           {report.video_path}")
    if report.telemetry_path is not None:
        _log_output(f"  telemetry       {report.telemetry_path}")
    if report.windowed:
        _log_output("  window          shown live")
    else:
        _log_output(f"  window          none, {report.reason}")
    _log_output("  These frames are a debug render of the tracker alone. They are not")
    _log_output("  the runtime loop's output and must not be published as a figure.")
    _log_output("  The markers are scene geometry. Their height is a configured")
    _log_output("  standoff, because no sensor on this line estimates one.")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
