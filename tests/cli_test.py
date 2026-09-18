"""Tests for the command entry points the gate calls."""

from pathlib import Path

import pytest

from clave.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_verify_manifest_passes_on_the_real_repository(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The gate's command succeeds on a clean tree."""

    assert main(["--root", str(ROOT), "verify-manifest"]) == 0
    assert "ok       smoke" in capsys.readouterr().out


def test_verify_manifest_fails_when_bytes_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mutated artifact fails the gate, non-zero."""
    (tmp_path / "corpora" / "fixtures").mkdir(parents=True)
    (tmp_path / "corpora" / "fixtures" / "smoke.csv").write_text("tampered\n")
    (tmp_path / "corpora" / "manifest.toml").write_text(
        '[[artifact]]\nname = "smoke"\n'
        'source = "corpora/fixtures/smoke.csv"\nsha256 = "0000"\n'
    )
    assert main(["--root", str(tmp_path), "verify-manifest"]) == 1
    assert "digest_mismatch" in capsys.readouterr().out


def test_record_digest_reports_a_digest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command reports rather than writes."""
    (tmp_path / "corpora").mkdir()
    manifest = tmp_path / "corpora" / "manifest.toml"
    manifest.write_text('[[artifact]]\nname = "x"\nsource = "x.csv"\n')
    before = manifest.read_text()
    target = tmp_path / "x.csv"
    target.write_text("hello\n")
    assert main(["--root", str(tmp_path), "record-digest", "x", str(target)]) == 0
    assert len(capsys.readouterr().out.strip()) == 64
    assert manifest.read_text() == before


def test_malformed_manifest_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate fails and names the entry."""
    (tmp_path / "corpora").mkdir()
    (tmp_path / "corpora" / "manifest.toml").write_text(
        '[[artifact]]\nname = "dup"\nsource = "a"\n\n'
        '[[artifact]]\nname = "dup"\nsource = "b"\n'
    )
    assert main(["--root", str(tmp_path), "verify-manifest"]) == 1
    assert "dup" in capsys.readouterr().err


def test_no_command_is_an_error() -> None:
    """argparse requires a subcommand."""
    with pytest.raises(SystemExit):
        main([])


def _write_outcomes(path: Path, correct: bool) -> None:
    """Write a records file whose objects are all handled the same way.

    The records are a synthetic fixture. They exercise the command and say
    nothing about any model, because no model has been trained.

    Args:
        path: Where to write.
        correct: Whether each object is classified and routed correctly.
    """
    import json

    records = [
        {
            "object_id": f"obj-{index}",
            "true_class": "M-01",
            "predicted_class": "M-01" if correct else "M-04",
            "picked": True,
            "routed_channel": "CH-PET" if correct else "CH-PLASTIC-OTHER",
            "seen_instance": index % 2 == 0,
            "decision_latency_seconds": 0.1,
            "cycle_time_seconds": 0.5,
        }
        for index in range(40)
    ]
    path.write_text(
        json.dumps(
            {"provenance": "synthetic fixture, not a measurement", "outcomes": records}
        )
    )


def test_validate_run_prints_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The harness runs from one command."""
    outcomes = tmp_path / "outcomes.json"
    _write_outcomes(outcomes, correct=True)
    main(
        [
            "--root",
            str(ROOT),
            "validate-run",
            "--outcomes",
            str(outcomes),
        ]
    )
    captured = capsys.readouterr().out
    assert "## What was run" in captured
    assert "## What was concluded" in captured
    assert "synthetic fixture, not a measurement" in captured


def test_validate_run_exits_non_zero_when_a_gate_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unmet gate is a failure, not a reported number."""
    outcomes = tmp_path / "outcomes.json"
    _write_outcomes(outcomes, correct=False)
    assert main(["--root", str(ROOT), "validate-run", "--outcomes", str(outcomes)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_validate_run_reports_a_malformed_records_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bad record fails the command naming what was wrong."""
    outcomes = tmp_path / "outcomes.json"
    outcomes.write_text('{"provenance": "fixture", "outcomes": [{"object_id": "a"}]}')
    assert main(["--root", str(ROOT), "validate-run", "--outcomes", str(outcomes)]) == 1
    assert "true_class" in capsys.readouterr().err
