"""The offline count estimator."""

from __future__ import annotations

import math
import random
from pathlib import Path

import pytest
import yaml

from clave.belief.errors import BeliefError
from clave.belief.estimate import COST_FILE, PSEUDO_COUNT, estimate_belief
from clave.belief.model import load_routing_belief
from clave.cli import main
from clave.tracker.fusion import OUTCOMES

ROOT = Path(__file__).resolve().parents[2]
WIDTH = len(OUTCOMES)


def _log(records: list[object]) -> dict[str, object]:
    """A version-1 count log."""
    return {"version": 1, "records": records}


def _run(
    tmp_path: Path, records: list[object], name: str = "counts.yml"
) -> dict[str, object]:
    """Estimate one log and return the written document."""
    source = tmp_path / "log.yml"
    source.write_text(yaml.safe_dump(_log(records), sort_keys=False), encoding="utf-8")
    destination = tmp_path / name
    estimate_belief(source, destination, root=tmp_path)
    loaded = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _raises(tmp_path: Path, payload: object, match: str) -> None:
    """A bad log raises and leaves the destination unwritten."""
    source = tmp_path / "log.yml"
    source.write_text(yaml.safe_dump(payload), encoding="utf-8")
    destination = tmp_path / "refused.yml"
    with pytest.raises(BeliefError, match=match):
        estimate_belief(source, destination, root=tmp_path)
    assert not destination.exists()


def _with_cost(written: dict[str, object]) -> dict[str, object]:
    """Attach a cost table the estimator did not write."""
    channels = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    return {
        "rule": "expected_cost",
        "prior_counts": written["prior_counts"],
        "sensor_cpts": written["sensor_cpts"],
        "channels": channels,
        "cost": [
            {"channel": index, "costs": [1.0] * WIDTH} for index in range(WIDTH)
        ],
    }


def test_ac_sort_12_pseudo_counts_load_through_the_category_model(
    tmp_path: Path,
) -> None:
    """One labeled pair gains one pseudo-count per cell and loads with a cost table."""
    written = _run(
        tmp_path,
        [{"category": "M-01", "readings": {"material": "M-02"}}],
        name="nested/counts.yml",
    )
    true = OUTCOMES.index("M-01")
    reading = OUTCOMES.index("M-02")
    prior = written["prior_counts"]
    assert isinstance(prior, list)
    assert prior[true] == PSEUDO_COUNT + 1
    assert all(
        value == PSEUDO_COUNT for index, value in enumerate(prior) if index != true
    )
    table = written["sensor_cpts"]
    assert isinstance(table, dict)
    material = table["material"]
    assert material[true][reading] == PSEUDO_COUNT + 1
    assert all(cell >= PSEUDO_COUNT for row in material for cell in row)
    assert "cost" not in written
    assert "mass" not in written
    model = load_routing_belief(_with_cost(written))
    assert model is not None
    assert model.prior_counts[true] == float(PSEUDO_COUNT + 1)
    assert model.likelihood("material", reading)[true] == float(PSEUDO_COUNT + 1)


def test_ac_sort_12_a_known_conditional_is_closer_than_uniform(tmp_path: Path) -> None:
    """A large sample from a known table lands closer than a uniform table."""
    sharp = 0.64
    rest = (1.0 - sharp) / (WIDTH - 1)
    draws = 12_000
    rng = random.Random(0)
    records: list[object] = []
    for _ in range(draws):
        true = rng.randrange(WIDTH)
        weights = [rest] * WIDTH
        weights[true] = sharp
        reading = rng.choices(range(WIDTH), weights=weights, k=1)[0]
        records.append(
            {
                "category": OUTCOMES[true],
                "readings": {"material": OUTCOMES[reading]},
            }
        )
    written = _run(tmp_path, records)
    sensors = written["sensor_cpts"]
    assert isinstance(sensors, dict)
    table = sensors["material"]
    assert sum(sum(row) for row in table) == WIDTH * WIDTH * PSEUDO_COUNT + draws
    uniform = 1.0 / WIDTH
    for row_index, row in enumerate(table):
        total = float(sum(row))
        estimated = [value / total for value in row]
        truth = [rest] * WIDTH
        truth[row_index] = sharp
        estimated_l1 = math.fsum(
            abs(left - right) for left, right in zip(estimated, truth, strict=True)
        )
        uniform_l1 = math.fsum(abs(uniform - right) for right in truth)
        assert estimated_l1 < uniform_l1
        assert estimated[row_index] > 0.55


def test_ac_sort_13_mass_stores_the_mean_and_the_unbiased_variance(
    tmp_path: Path,
) -> None:
    """Mass samples store the mean and the variance divided by N - 1."""
    written = _run(
        tmp_path,
        [
            {"category": "M-08", "mass": 1},
            {"category": "M-08", "mass": 2},
            {"category": "M-08", "mass": 3},
            {"category": "M-09", "mass": 5},
            {"category": "M-09", "mass": 5},
            {"category": "M-01", "readings": {"material": "M-01"}},
        ],
    )
    mass = written["mass"]
    assert isinstance(mass, dict)
    assert mass["M-08"]["mean"] == 2
    assert mass["M-08"]["variance"] == 1
    assert mass["M-09"]["mean"] == 5
    assert mass["M-09"]["variance"] == 0
    prior = written["prior_counts"]
    assert isinstance(prior, list)
    assert prior[OUTCOMES.index("M-08")] == PSEUDO_COUNT + 3
    assert "M-01" in OUTCOMES
    _raises(
        tmp_path,
        _log(
            [
                {
                    "category": "M-08",
                    "mass": 1,
                    "readings": {"material": "M-08"},
                }
            ]
        ),
        "unbiased variance",
    )


def test_ac_sort_14_a_checkpoint_and_the_cost_file_are_not_written(
    tmp_path: Path,
) -> None:
    """The estimator leaves checkpoints and the cost file untouched."""
    source = (ROOT / "src" / "clave" / "belief" / "estimate.py").read_text(
        encoding="utf-8"
    )
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    ]
    assert all("gtsam" not in line for line in imports)
    assert all("clave.sim" not in line for line in imports)
    assert all("clave.training" not in line for line in imports)
    assert all("clave.data.expert" not in line for line in imports)
    assert all("clave.runtime" not in line for line in imports)

    reasoned = ROOT / COST_FILE
    before = reasoned.read_bytes()
    with pytest.raises(BeliefError, match="cost file"):
        estimate_belief(tmp_path / "missing.yml", reasoned, root=ROOT)
    assert reasoned.read_bytes() == before

    payload = b"checkpoint-bytes"
    checkpoint = tmp_path / "checkpoints" / "policy.pt"
    checkpoint.parent.mkdir()
    checkpoint.write_bytes(payload)
    loose = tmp_path / "policy.best.pt"
    loose.write_bytes(payload)
    for path in (checkpoint, loose):
        with pytest.raises(BeliefError, match="checkpoint"):
            estimate_belief(tmp_path / "missing.yml", path, root=tmp_path)
        assert path.read_bytes() == payload

    operator = tmp_path / "operator-cost.yml"
    operator.write_text("keep\n", encoding="utf-8")
    with pytest.raises(BeliefError, match="cost file"):
        estimate_belief(
            tmp_path / "missing.yml",
            operator,
            root=tmp_path,
            cost_files=(operator,),
        )
    assert operator.read_text(encoding="utf-8") == "keep\n"

    written = _run(tmp_path, [{"category": "M-01", "readings": {"material": "M-01"}}])
    assert written["prior_counts"]
    assert checkpoint.read_bytes() == payload
    assert reasoned.read_bytes() == before

    code = main(
        [
            "--root",
            str(tmp_path),
            "estimate-belief",
            "--in",
            "missing.yml",
            "--out",
            "operator-cost.yml",
            "--cost",
            "operator-cost.yml",
        ]
    )
    assert code == 1
    assert operator.read_text(encoding="utf-8") == "keep\n"


def test_ac_sort_15_a_failed_grasp_an_override_and_a_collision_are_not_counts(
    tmp_path: Path,
) -> None:
    """A grasp failure, an override, and a collision do not move the tables."""
    written = _run(
        tmp_path,
        [
            {"category": "M-01", "readings": {"material": "M-01"}},
            {
                "kind": "grasp_failed",
                "category": "M-05",
                "readings": {"material": "M-05"},
                "mass": 99,
            },
            {"kind": "overridden", "category": "M-06"},
            {"kind": "collision", "category": "M-07", "mass": 40},
        ],
    )
    prior = written["prior_counts"]
    assert isinstance(prior, list)
    assert prior[OUTCOMES.index("M-01")] == PSEUDO_COUNT + 1
    for name in ("M-05", "M-06", "M-07"):
        assert prior[OUTCOMES.index(name)] == PSEUDO_COUNT
    assert "mass" not in written
    sensors = written["sensor_cpts"]
    assert isinstance(sensors, dict)
    assert list(sensors) == ["material"]
    row = sensors["material"][OUTCOMES.index("M-05")]
    assert all(cell == PSEUDO_COUNT for cell in row)


def test_two_sensors_on_one_record_count_the_category_once(tmp_path: Path) -> None:
    """Two hard readings on one record increment the prior a single time."""
    written = _run(
        tmp_path,
        [
            {
                "category": "M-03",
                "readings": {"material": "M-03", "code": "reject"},
            }
        ],
    )
    prior = written["prior_counts"]
    assert isinstance(prior, list)
    assert prior[OUTCOMES.index("M-03")] == PSEUDO_COUNT + 1
    sensors = written["sensor_cpts"]
    assert isinstance(sensors, dict)
    assert set(sensors) == {"material", "code"}


def test_a_motion_log_is_refused(tmp_path: Path) -> None:
    """A file that is not a count log is not searched for a category."""
    _raises(tmp_path, {"frames": [{"pose": [0.0, 0.0, 0.0]}]}, "frames")


def test_a_malformed_count_log_names_the_problem(tmp_path: Path) -> None:
    """Each broken record fails before a count file is written."""
    destination = tmp_path / "counts.yml"
    with pytest.raises(BeliefError, match="not a file"):
        estimate_belief(tmp_path / "missing.yml", destination, root=tmp_path)
    source = tmp_path / "log.yml"
    source.write_text("[\n", encoding="utf-8")
    with pytest.raises(BeliefError, match="not YAML"):
        estimate_belief(source, destination, root=tmp_path)
    assert not destination.exists()

    _raises(tmp_path, None, "mapping")
    _raises(tmp_path, [1], "mapping")
    _raises(tmp_path, {"version": 1, "records": [], "frames": []}, "unknown field")
    _raises(tmp_path, {"version": "1", "records": []}, "version")
    _raises(tmp_path, {"version": 1, "records": "nope"}, "records list")
    _raises(tmp_path, _log(["nope"]), "not a record")
    _raises(
        tmp_path,
        _log([{"category": "M-01", "pose": [0.0]}]),
        "unknown field",
    )
    _raises(tmp_path, _log([{"kind": "missed"}]), "kind")
    _raises(tmp_path, _log([{"category": "battery"}]), "not an outcome")
    _raises(
        tmp_path,
        _log([{"category": "M-01", "readings": "material"}]),
        "readings",
    )
    _raises(tmp_path, _log([{"category": "M-01", "readings": {}}]), "readings")
    _raises(
        tmp_path,
        _log([{"category": "M-01", "readings": {"": "M-01"}}]),
        "sensor name",
    )
    _raises(
        tmp_path,
        _log([{"category": "M-01", "readings": {1: "M-01"}}]),
        "sensor name",
    )
    _raises(
        tmp_path,
        _log([{"category": "M-01", "readings": {"material": "pet"}}]),
        "not an outcome",
    )
    _raises(tmp_path, _log([{"category": "M-01", "mass": True}]), "mass")
    _raises(tmp_path, _log([{"category": "M-01", "mass": "heavy"}]), "mass")
    _raises(tmp_path, _log([{"category": "M-01", "mass": float("inf")}]), "mass")
    _raises(tmp_path, _log([{"category": "M-01"}]), "sensor reading or a mass")
    _raises(
        tmp_path,
        _log([{"category": "M-08", "mass": 1}, {"category": "M-08", "mass": 2}]),
        "discrete sensor",
    )
    folder = tmp_path / "a-directory"
    folder.mkdir()
    with pytest.raises(BeliefError, match="not a file"):
        estimate_belief(source, folder, root=tmp_path)


def test_a_destination_outside_the_root_is_written(tmp_path: Path) -> None:
    """A path that is not under the root, and is not a checkpoint, is allowed."""
    source = tmp_path / "log.yml"
    source.write_text(
        yaml.safe_dump(
            _log([{"category": "M-01", "readings": {"material": "M-01"}}]),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    destination = tmp_path.parent / f"{tmp_path.name}-counts.yml"
    try:
        estimate_belief(source, destination, root=tmp_path)
        assert destination.is_file()
    finally:
        destination.unlink(missing_ok=True)


def test_the_command_writes_a_count_file(tmp_path: Path) -> None:
    """The CLI writes the count file and does not start the simulator."""
    source = tmp_path / "log.yml"
    source.write_text(
        yaml.safe_dump(
            _log([{"category": "M-02", "readings": {"material": "M-02"}}]),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "--root",
            str(tmp_path),
            "estimate-belief",
            "--in",
            "log.yml",
            "--out",
            "nested/counts.yml",
        ]
    )
    assert code == 0
    written = yaml.safe_load(
        (tmp_path / "nested" / "counts.yml").read_text(encoding="utf-8")
    )
    assert isinstance(written, dict)
    prior = written["prior_counts"]
    assert isinstance(prior, list)
    assert prior[OUTCOMES.index("M-02")] == PSEUDO_COUNT + 1
