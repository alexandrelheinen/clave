"""Tests for the command entry points the gate calls."""

from pathlib import Path

import pytest

from clave.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_verify_manifest_passes_on_the_real_repository(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-TOOLCHAIN-03: the gate's command succeeds on a clean tree."""
    assert main(["--root", str(ROOT), "verify-manifest"]) == 0
    assert "ok       smoke" in capsys.readouterr().out


def test_check_research_passes_on_the_real_repository(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-CHECK-01: the checker passes against the delivered document."""
    assert main(["--root", str(ROOT), "check-research"]) == 0
    assert "ok" in capsys.readouterr().out


def test_verify_manifest_fails_when_bytes_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-FETCH-02: a mutated artifact fails the gate, non-zero."""
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
    """AC-FETCH-04: the command reports rather than writes."""
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
    """AC-MANIFEST-03: the gate fails and names the entry."""
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
