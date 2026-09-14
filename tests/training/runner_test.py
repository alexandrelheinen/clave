"""Tests for the training run loop."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from clave.training.config import TrainingConfig
from clave.training.runner import run_record_path, train

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "configs" / "training" / "default.yml"
DATASET = ROOT / "datasets" / "synthetic"

needs_dataset = pytest.mark.skipif(
    not (DATASET / "dataset.json").is_file(),
    reason="no recorded dataset; run `clave record-dataset` first",
)


def config_for(tmp_path: Path, candidate: str, epochs: int = 1) -> TrainingConfig:
    """A one-epoch configuration writing into a temporary directory."""
    base = TrainingConfig.load(SHIPPED, candidate)
    return replace(base, dataset=DATASET, checkpoints=tmp_path, epochs=epochs)


@needs_dataset
def test_a_run_records_seed_digests_and_environment(tmp_path: Path) -> None:
    """AC-RESUME-03 and AC-COST-02."""
    pytest.importorskip("torch")
    config = config_for(tmp_path, "behavior-cloning-baseline")
    run = train(config, config.window_exit_meters)
    assert run.seed == config.seed
    assert run.config_digest == config.digest
    assert len(run.dataset_digest) == 64
    assert run.threads >= 1
    assert run.machine


@needs_dataset
def test_epoch_records_carry_loss_and_wall_clock(tmp_path: Path) -> None:
    """AC-COST-01."""
    pytest.importorskip("torch")
    config = config_for(tmp_path, "behavior-cloning-baseline")
    run = train(config, config.window_exit_meters)
    assert run.epochs
    assert run.epochs[0].seconds > 0
    assert run.epochs[0].loss >= 0


@needs_dataset
def test_a_run_record_reloads_without_importing_project_code(tmp_path: Path) -> None:
    """AC-RESUME-04."""
    pytest.importorskip("torch")
    config = config_for(tmp_path, "behavior-cloning-baseline")
    train(config, config.window_exit_meters)
    raw = json.loads(run_record_path(tmp_path, "behavior-cloning-baseline").read_text())
    assert raw["candidate"] == "behavior-cloning-baseline"
    assert raw["completed"] is True


@needs_dataset
def test_a_checkpoint_is_written_and_a_restart_resumes(tmp_path: Path) -> None:
    """AC-RESUME-01 and AC-RESUME-02."""
    pytest.importorskip("torch")
    first = config_for(tmp_path, "behavior-cloning-baseline", epochs=1)
    train(first, first.window_exit_meters)
    assert (tmp_path / "behavior-cloning-baseline.pt").is_file()

    second = replace(first, epochs=2)
    resumed = train(second, second.window_exit_meters)
    # Epoch 0 already happened, so a resumed run records only the new epoch.
    assert [epoch.index for epoch in resumed.epochs] == [1]


@needs_dataset
def test_one_seed_twice_gives_the_same_first_epoch_loss(tmp_path: Path) -> None:
    """AC-RESUME-05: reproducibility across processes, not within one.

    Two runs in one interpreter share a global generator, so the second inherits
    whatever state the first left behind. That passes even when weight
    initialization is unseeded, which is the defect this exists to catch, so
    each run happens in a fresh interpreter.
    """
    import subprocess
    import sys

    pytest.importorskip("torch")
    script = (
        "import sys;from pathlib import Path;from dataclasses import replace;"
        "from clave.training.config import TrainingConfig;"
        "from clave.training.runner import train;"
        f"b=TrainingConfig.load(Path({str(SHIPPED)!r}),'behavior-cloning-baseline');"
        f"c=replace(b,dataset=Path({str(DATASET)!r}),"
        "checkpoints=Path(sys.argv[1]),epochs=1);"
        "r=train(c,c.window_exit_meters);print(r.epochs[0].loss)"
    )
    losses = []
    for name in ("a", "b"):
        out = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / name)],
            capture_output=True,
            text=True,
            check=True,
        )
        losses.append(float(out.stdout.strip().splitlines()[-1]))
    assert losses[0] == pytest.approx(losses[1], abs=1e-6)


@needs_dataset
def test_a_checkpoint_from_another_candidate_is_refused(tmp_path: Path) -> None:
    """Restoring mismatched weights would fail confusingly much later."""
    pytest.importorskip("torch")
    config = config_for(tmp_path, "behavior-cloning-baseline")
    train(config, config.window_exit_meters)
    (tmp_path / "behavior-cloning-baseline.pt").rename(tmp_path / "act.pt")
    with pytest.raises(ValueError, match="behavior-cloning-baseline"):
        train(config_for(tmp_path, "act"), 0.17)


@needs_dataset
def test_two_candidates_do_not_overwrite_each_others_records(tmp_path: Path) -> None:
    """A shared record file would erase the comparison it exists for."""
    pytest.importorskip("torch")
    config = config_for(tmp_path, "behavior-cloning-baseline")
    train(config, config.window_exit_meters)
    assert run_record_path(tmp_path, "behavior-cloning-baseline").is_file()
    assert not run_record_path(tmp_path, "resnet50-baseline").is_file()
