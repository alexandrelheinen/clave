"""Offline counts for the category prior and the discrete sensor tables.

The command reads a count log and writes ``prior_counts`` and ``sensor_cpts``.
It does not start the simulator, and it does not write the cost table or a
behavior-cloning checkpoint.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from clave.belief.errors import BeliefError
from clave.tracker.fusion import OUTCOMES

# The count log's version. The sorting specification defines the record shape.
LOG_VERSION = 1

# One pseudo-count per cell, the discrete estimator rule in the sorting
# specification. The product normalizes the table later. This is not a
# configuration knob.
PSEUDO_COUNT = 1

# Behavior-cloning checkpoints are `{candidate}.pt` under a `checkpoints`
# directory. The estimator refuses both shapes and does not import the trainer.
_CHECKPOINT_SUFFIX = ".pt"
_CHECKPOINT_DIR = "checkpoints"

# The reasoned default. The estimator refuses to write this path.
COST_FILE = Path("configs/routing/expected-cost-default.yml")

_TOP_KEYS = frozenset({"version", "records"})
_RECORD_KEYS = frozenset({"category", "readings", "mass", "kind"})
_EXCLUDED_KINDS = frozenset({"grasp_failed", "overridden", "collision"})

_HEADER = (
    "# prior_counts and sensor_cpts, in OUTCOMES order.\n"
    "# One pseudo-count is added to every cell.\n"
    "# This file is not the cost table.\n"
)


@dataclass(frozen=True)
class MassEstimate:
    """Sample mean and unbiased variance for one category.

    Attributes:
        mean: The sample mean of the masses.
        variance: The unbiased sample variance, divided by N - 1.
    """

    mean: float
    variance: float


@dataclass(frozen=True)
class _Observation:
    """One category observation that is allowed to move the counts."""

    category: str
    readings: tuple[tuple[str, str], ...]
    mass: float | None


@dataclass(frozen=True)
class CountTables:
    """The tables the estimator writes.

    Attributes:
        prior_counts: One count per outcome, including the pseudo-count.
        sensors: Conditional counts per sensor, in `OUTCOMES` order.
        mass: Mean and unbiased variance for categories with a mass series.
    """

    prior_counts: tuple[float, ...]
    sensors: dict[str, tuple[tuple[float, ...], ...]]
    mass: dict[str, MassEstimate]


def estimate_belief(
    source: Path,
    destination: Path,
    *,
    root: Path,
    cost_files: Sequence[Path] = (),
) -> CountTables:
    """Read a count log and write prior and sensor tables.

    Args:
        source: The count log.
        destination: Where the count file is written.
        root: Repository root. Relative paths are joined to it.
        cost_files: Extra cost files the command must not overwrite. The
            reasoned default is always protected, whether or not it is listed.

    Returns:
        The tables that were written.

    Raises:
        BeliefError: If the destination is protected, the log is not a count
            log, a mass series cannot yield an unbiased variance, or the log
            has no discrete sensor reading.
    """
    log_path = _under_root(source, root)
    out_path = _under_root(destination, root)
    _refuse_destination(out_path, root, cost_files)
    tables = _tables(_observations(_load_log(log_path)))
    _write(out_path, tables)
    return tables


def _under_root(path: Path, root: Path) -> Path:
    """Join a relative path to `root` and leave an absolute path alone."""
    if path.is_absolute():
        return path
    return root / path


def _refuse_destination(
    destination: Path, root: Path, cost_files: Sequence[Path]
) -> None:
    """Refuse a cost file or a checkpoint path before any write."""
    target = destination.resolve()
    protected = [_under_root(COST_FILE, root).resolve()]
    protected.extend(_under_root(path, root).resolve() for path in cost_files)
    if target in protected:
        raise BeliefError(
            f"{destination} is a cost file, and the estimator does not write it"
        )
    if _is_checkpoint(target, root):
        raise BeliefError(
            f"{destination} is a checkpoint path, and the estimator does not write it"
        )
    if destination.exists() and not destination.is_file():
        raise BeliefError(f"{destination} is not a file")


def _is_checkpoint(destination: Path, root: Path) -> bool:
    """A `.pt` file, or a path under a `checkpoints` directory, is a checkpoint."""
    if destination.suffix == _CHECKPOINT_SUFFIX:
        return True
    try:
        relative = destination.relative_to(root.resolve())
    except ValueError:
        relative = destination
    return _CHECKPOINT_DIR in relative.parts


def _load_log(source: Path) -> Any:
    """Read the count log, naming the path when it is missing or not YAML."""
    if not source.is_file():
        raise BeliefError(f"count log {source} is not a file")
    try:
        return yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BeliefError(f"count log {source} is not YAML") from exc


def _observations(loaded: Any) -> list[_Observation]:
    """Keep counting records and drop failed grasps, overrides, and collisions."""
    if not isinstance(loaded, dict):
        raise BeliefError("a count log is a mapping with version and records")
    unknown = set(loaded) - _TOP_KEYS
    if unknown:
        name = sorted(unknown)[0]
        raise BeliefError(f"a count log has an unknown field {name!r}")
    if loaded.get("version") != LOG_VERSION:
        found = loaded.get("version")
        raise BeliefError(f"a count log version of {found!r} is not {LOG_VERSION}")
    records = loaded.get("records")
    if not isinstance(records, list):
        raise BeliefError("a count log needs a records list")
    kept: list[_Observation] = []
    for index, record in enumerate(records):
        observation = _observation(record, index)
        if observation is not None:
            kept.append(observation)
    return kept


def _observation(record: Any, index: int) -> _Observation | None:
    """Parse one record. An excluded kind contributes nothing."""
    where = f"records[{index}]"
    if not isinstance(record, dict):
        raise BeliefError(f"{where} is not a record")
    unknown = set(record) - _RECORD_KEYS
    if unknown:
        name = sorted(unknown)[0]
        raise BeliefError(f"{where} has an unknown field {name!r}")
    kind = record.get("kind")
    if kind is not None:
        if kind not in _EXCLUDED_KINDS:
            raise BeliefError(
                f"{where} kind {kind!r} is not grasp_failed, overridden, or collision"
            )
        return None
    category = record.get("category")
    if not isinstance(category, str) or category not in OUTCOMES:
        raise BeliefError(f"{where} category {category!r} is not an outcome")
    readings = _readings(record.get("readings"), where) if "readings" in record else ()
    mass = _mass(record.get("mass"), where) if "mass" in record else None
    if not readings and mass is None:
        raise BeliefError(f"{where} needs a sensor reading or a mass")
    return _Observation(category, readings, mass)


def _readings(raw: Any, where: str) -> tuple[tuple[str, str], ...]:
    """Read a sensor name mapped to a hard label."""
    if not isinstance(raw, dict) or not raw:
        raise BeliefError(f"{where} readings need one sensor")
    parsed: list[tuple[str, str]] = []
    for name, reading in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise BeliefError(f"{where} has a sensor name that is empty")
        if not isinstance(reading, str) or reading not in OUTCOMES:
            raise BeliefError(
                f"{where} sensor {name!r} reading {reading!r} is not an outcome"
            )
        parsed.append((name, reading))
    return tuple(parsed)


def _mass(raw: Any, where: str) -> float:
    """Read one finite mass. A boolean is not a mass."""
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise BeliefError(f"{where} mass {raw!r} is not a reading")
    value = float(raw)
    if not math.isfinite(value):
        raise BeliefError(f"{where} mass {raw!r} is not a reading")
    return value


def _tables(observations: Sequence[_Observation]) -> CountTables:
    """Add one pseudo-count per cell, then the observations."""
    width = len(OUTCOMES)
    index = {name: position for position, name in enumerate(OUTCOMES)}
    prior = [PSEUDO_COUNT] * width
    sensors: dict[str, list[list[int]]] = {}
    masses: dict[str, list[float]] = {}
    for observation in observations:
        prior[index[observation.category]] += 1
        for sensor, reading in observation.readings:
            table = sensors.get(sensor)
            if table is None:
                table = [[PSEUDO_COUNT for _ in range(width)] for _ in range(width)]
                sensors[sensor] = table
            row = table[index[observation.category]]
            column = index[reading]
            row[column] += 1
        if observation.mass is not None:
            masses.setdefault(observation.category, []).append(observation.mass)
    mass = _mass_estimates(masses)
    if not sensors:
        raise BeliefError("the count log has no discrete sensor reading")
    return CountTables(
        prior_counts=tuple(float(value) for value in prior),
        sensors={
            name: tuple(tuple(float(value) for value in row) for row in table)
            for name, table in sensors.items()
        },
        mass=mass,
    )


def _mass_estimates(masses: Mapping[str, Sequence[float]]) -> dict[str, MassEstimate]:
    """Store a mean and an unbiased variance, or refuse a one-sample series."""
    estimates: dict[str, MassEstimate] = {}
    for category in OUTCOMES:
        samples = masses.get(category)
        if not samples:
            continue
        count = len(samples)
        if count < 2:
            raise BeliefError(
                f"{category} has {count} mass sample, and an unbiased "
                "variance needs two"
            )
        mean = math.fsum(samples) / count
        # Bessel's correction: the unbiased sample variance divides by N - 1.
        squared = math.fsum((sample - mean) ** 2 for sample in samples)
        estimates[category] = MassEstimate(mean, squared / (count - 1))
    return estimates


def _write(destination: Path, tables: CountTables) -> None:
    """Write the count file. The caller has already refused protected paths."""
    payload: dict[str, Any] = {
        "version": LOG_VERSION,
        "prior_counts": [int(value) for value in tables.prior_counts],
        "sensor_cpts": {
            name: [[int(value) for value in row] for row in table]
            for name, table in tables.sensors.items()
        },
    }
    if tables.mass:
        payload["mass"] = {
            category: {"mean": estimate.mean, "variance": estimate.variance}
            for category, estimate in tables.mass.items()
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = _HEADER + yaml.safe_dump(payload, sort_keys=False)
    destination.write_text(text, encoding="utf-8")
