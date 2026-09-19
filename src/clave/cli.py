"""Command entry points the gate calls.

The gate calls a stable command rather than a module path, so internal layout
can change without editing shell.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from clave.corpus.artifacts import record_digest, verify
from clave.corpus.manifest import Manifest
from clave.errors import ClaveError

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
    print(f"  reach annulus     {report.reach_min:.3f} to {report.reach_max:.3f} m")
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


def _run_sitl(
    root: Path,
    config_path: Path,
    scripted: bool,
    directory: Path,
    seconds: float | None,
    publish_to_ros: bool,
) -> int:
    """Run the software-in-the-loop runtime and report what it did.

    Args:
        root: Repository root.
        config_path: Path to the runtime configuration.
        scripted: Run the scripted expert instead of the trained checkpoints.
        directory: Where the sockets, the runtime configuration and the record
            go.
        seconds: Overrides how many simulated seconds to run, which is how a
            measurement gets enough samples for a percentile to mean anything.
        publish_to_ros: Put every published decision on a ROS 2 topic.

    Returns:
        A process exit code.
    """
    from clave.runtime import loop
    from clave.runtime.inference import (
        CheckpointPredictor,
        Predictor,
        ScriptedPredictor,
    )

    settings = loop.RuntimeSettings.load(root / config_path)
    if seconds is not None:
        settings = loop.RuntimeSettings(**{**vars(settings), "seconds": seconds})
    predictor: Predictor
    if scripted:
        predictor = ScriptedPredictor()
    else:
        predictor = CheckpointPredictor(
            checkpoints=root / settings.checkpoints,
            perception=settings.perception,
            policy=settings.policy,
            presence_floor=settings.presence_floor,
            association_radius=settings.association_radius_meters,
        )
    report = loop.run(root, settings, predictor, directory, publish_to_ros)
    loop.write_record(directory / "sitl.json", report)

    print(f"  predictor       {report.predictor}")
    print(f"  machine         {report.machine}, {report.threads} threads")
    size = f"{report.frame_width}x{report.frame_height}"
    print(f"  frames          {report.frames} at {size}")
    print(f"  proposals       {report.proposals}, {report.silent_frames} silent frames")
    for name in sorted(report.counters):
        print(f"  {name:22s}  {report.counters[name]}")
    print(f"  decisions back  {report.decisions_received}")
    if publish_to_ros:
        print(f"  published       {report.published_to_ros} on ROS 2")
        if report.ros_unavailable_reason is not None:
            print(f"  NO ROS          {report.ros_unavailable_reason}")
    print(
        f"  budget          {report.budget_seconds:.3f} s at "
        f"{report.belt_speed:.3f} m/s"
    )
    print(
        f"  latency         median {report.percentile(0.50) * 1000:.1f} ms, "
        f"p99 {report.percentile(0.99) * 1000:.1f} ms"
    )
    print(
        "  The models saw 240 frames of parametric primitives. This measures "
        "the mechanism, not whether a decision is right."
    )
    return 0


def _benchmark(root: Path, config_path: Path, out: Path) -> int:
    """Run every configuration the benchmark names and report the comparison.

    Args:
        root: Repository root.
        config_path: The benchmark configuration.
        out: Where the evidence pack and the run directories go.

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
        print(f"  running         {configuration.name}")
        result = run_configuration(root, config, configuration, out / "runs")
        if not result.available:
            print(f"  UNAVAILABLE     {result.unavailable_reason}")
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
    print()
    print(pack.render())
    print()
    print(f"  evidence pack   {out / 'benchmark.json'}")
    return 0 if pack.passed else 1


def _demo(root: Path, name: str, out: Path, runtime: Path) -> int:
    """Run one named scenario and report what it did.

    Args:
        root: Repository root.
        name: Scenario name, matching a file under configs/demos/.
        out: Where the record and the video go.
        runtime: The runtime configuration to start from.

    Returns:
        A process exit code.
    """
    from clave.demo.runner import play, summary
    from clave.demo.scenario import Scenario, ScenarioError

    demos = root / "configs" / "demos"
    # A scenario is named with hyphens and its file with underscores, as every
    # other configuration file in this repository is. Both spellings resolve,
    # so nobody has to remember which convention applies where.
    for candidate in (name, name.replace("-", "_")):
        path = demos / f"{candidate}.yml"
        if path.is_file():
            break
    else:
        available = sorted(
            entry.stem.replace("_", "-") for entry in demos.glob("*.yml")
        )
        raise ScenarioError(
            f"no scenario named {name!r}. Available: {', '.join(available)}"
        )
    scenario = Scenario.load(path, out)
    print(f"  {scenario.description}")
    print()
    report = play(root, scenario, runtime, out)
    print(summary(scenario, report))
    return 0


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
    print(f"  {scenario.description}")
    print()
    written = capture(root, scenario, out)
    print(
        f"  seed            {scenario.seed}, captured at "
        f"{scenario.capture_at_seconds:.2f} simulated seconds"
    )
    print(f"  size            {scenario.width} x {scenario.height}")
    for file in written:
        print(f"  wrote           {file}")
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
    sitl = sub.add_parser(
        "run-sitl", help="run the loop from frame to published decision"
    )
    sitl.add_argument("--config", type=Path, default=Path("configs/runtime/sitl.yml"))
    sitl.add_argument("--out", type=Path, default=Path("runs/sitl"))
    sitl.add_argument("--seconds", type=float, default=None)
    bench_suite = sub.add_parser(
        "benchmark", help="compare every configuration in one table"
    )
    bench_suite.add_argument(
        "--config", type=Path, default=Path("configs/benchmark/default.yml")
    )
    bench_suite.add_argument("--out", type=Path, default=Path("runs/benchmark"))
    still = sub.add_parser("still", help="capture a still of the world")
    still.add_argument("scenario", nargs="?", default="thumbnail")
    still.add_argument("--out", type=Path, default=Path("runs/stills"))
    dbg = sub.add_parser(
        "debug-tracker", help="annotate a rollout with everything the tracker believes"
    )
    dbg.add_argument("--out", type=Path, default=Path("runs/debug/tracker"))
    dbg.add_argument("--seconds", type=float, default=14.0)
    dbg.add_argument("--seed", type=int, default=0)
    dbg.add_argument("--no-window", action="store_true")
    dbg.add_argument("--video", action="store_true")
    dbg.add_argument("--fps", type=int, default=4)
    dbg.add_argument(
        "--view",
        default=None,
        help="which view in configs/debug/tracker.yml to film from",
    )
    demo = sub.add_parser("demo", help="run one named scenario and record it")
    demo.add_argument("scenario", nargs="?", default="sorting-line")
    demo.add_argument("--out", type=Path, default=Path("runs/demos"))
    demo.add_argument("--runtime", type=Path, default=Path("configs/runtime/sitl.yml"))
    sitl.add_argument(
        "--ros",
        action="store_true",
        help="publish every decision on a ROS 2 topic",
    )
    sitl.add_argument(
        "--scripted",
        action="store_true",
        help="propose with the scripted expert instead of the trained models",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "verify-manifest":
            return _verify_manifest(args.root)
        if args.command == "bench-candidates":
            return _bench_candidates(args.warmup, args.repetitions)
        if args.command == "world-probe":
            return _world_probe(args.root, args.seconds, args.seed)
        if args.command == "record-dataset":
            return _record_dataset(args.root, args.out, args.seed)
        if args.command == "train":
            return _train(args.root, args.config, args.candidate)
        if args.command == "still":
            return _still(args.root, args.scenario, args.out)
        if args.command == "debug-tracker":
            return _debug_tracker(args.root, args)
        if args.command == "demo":
            return _demo(args.root, args.scenario, args.out, args.runtime)
        if args.command == "benchmark":
            return _benchmark(args.root, args.config, args.out)
        if args.command == "run-sitl":
            return _run_sitl(
                args.root,
                args.config,
                args.scripted,
                args.out,
                args.seconds,
                args.ros,
            )
        if args.command == "validate-run":
            return _validate_run(args.root, args.outcomes, args.gates)
        return _record(args.root, args.name, args.path)
    except ClaveError as exc:
        print(f"  FAILED   {exc}", file=sys.stderr)
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
    from clave.tracker.debug_run import run

    report = run(
        root,
        out=args.out if args.out.is_absolute() else root / args.out,
        seconds=args.seconds,
        seed=args.seed,
        window=not args.no_window,
        video=args.video,
        fps=args.fps,
        view_name=args.view,
    )
    print()
    print(f"  captures        {report.captures}")
    print(f"  tracks open     {report.tracks}")
    print(f"  markers on last {report.drawn}, as {report.geoms} geoms")
    print(f"  visits served   {len(report.served)} {list(report.served)}")
    print(f"  faults          {len(report.faults)}")
    for track_id, why in report.faults:
        print(f"    track {track_id}: {why}")
    print(f"  ended in        {report.phase}")
    if report.closest_approach is not None:
        print(f"  to commanded    {report.closest_approach * 1000:.0f} mm")
    if report.closest_live is not None:
        print(f"  to the object   {report.closest_live * 1000:.0f} mm")
    print(f"  frames written  {report.frames_written} to {report.output}")
    if report.video_path is not None:
        print(f"  video           {report.video_path}")
    if report.windowed:
        print("  window          shown live")
    else:
        print(f"  window          none, {report.reason}")
    print()
    print("  These frames are a debug render of the tracker alone. They are not")
    print("  the runtime loop's output and must not be published as a figure.")
    print("  The markers are scene geometry. Their height is a configured")
    print("  standoff, because no sensor on this line estimates one.")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
