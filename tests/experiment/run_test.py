"""Tests for the run record."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from clave.corpus.manifest import Manifest
from clave.errors import UnknownArtifactError
from clave.experiment.run import RunRecord, config_digest


@pytest.fixture
def manifest(tmp_path: Path) -> Manifest:
    """A manifest with one verified and one unverified artifact."""
    path = tmp_path / "manifest.toml"
    path.write_text(
        '[[artifact]]\nname = "smoke"\nsource = "x"\nsha256 = "deadbeef"\n\n'
        '[[artifact]]\nname = "pending"\nsource = "y"\n'
    )
    return Manifest.load(path)


def test_record_carries_seed_config_artifacts_and_environment(
    manifest: Manifest,
) -> None:
    """AC-RUN-01, AC-RUN-02, AC-RUN-03."""
    record = RunRecord.create(7, {"lr": 0.1}, ["smoke"], manifest)
    assert record.seed == 7
    assert record.config_sha256 == config_digest({"lr": 0.1})
    assert record.artifacts == {"smoke": "deadbeef"}
    assert record.environment["python"].startswith("3.")
    assert "numpy" in record.environment


def test_config_digest_ignores_key_order() -> None:
    """AC-RUN-02: two equivalent configurations digest identically."""
    assert config_digest({"a": 1, "b": 2}) == config_digest({"b": 2, "a": 1})


def test_unverified_artifact_is_recorded_as_having_no_digest(
    manifest: Manifest,
) -> None:
    """AC-RUN-01: the record does not invent a digest it does not have."""
    record = RunRecord.create(1, {}, ["pending"], manifest)
    assert record.artifacts == {"pending": None}


def test_unknown_artifact_raises_before_anything_is_written(
    manifest: Manifest, tmp_path: Path
) -> None:
    """AC-RUN-05: an unidentifiable input fails the run."""
    with pytest.raises(UnknownArtifactError, match="ghost"):
        RunRecord.create(1, {}, ["ghost"], manifest)
    assert not list(tmp_path.glob("*.json"))


def test_record_reloads_without_importing_project_code(
    manifest: Manifest, tmp_path: Path
) -> None:
    """AC-RUN-04: a later tool reads it with the standard library alone."""
    out = tmp_path / "run.json"
    RunRecord.create(3, {"lr": 0.5}, ["smoke"], manifest).write(out)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import json;print(json.load(open({str(out)!r}))['seed'])",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    assert proc.stdout.strip() == "3"
    assert json.loads(out.read_text())["artifacts"] == {"smoke": "deadbeef"}
