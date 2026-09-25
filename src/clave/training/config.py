"""Training configuration.

Every hyperparameter lives in a file. A learning rate buried in code cannot be
swept, and a run whose settings are not recorded cannot be compared with
another.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from clave.errors import ClaveError
from clave.experiment.run import config_digest


class TrainingConfigError(ClaveError):
    """The training configuration is missing a key."""


@dataclass(frozen=True)
class TrainingConfig:
    """Everything a run needs, and nothing defaulted in code.

    Attributes:
        candidate: Registry name of the architecture to train.
        dataset: Directory holding the dataset to read.
        checkpoints: Directory to write checkpoints and the run record into.
        epochs: How many passes over the training split.
        batch_size: Examples per optimizer step.
        learning_rate: Optimizer step size.
        seed: Seed for initialization, the frame-sample phases, and shuffling.
        samples_per_crossing: Looks kept while an object crosses the camera
            footprint along the belt. A shorter crossing keeps every frame.
        window_exit_meters: Belt coordinate where the reachable window ends,
            used to replay the scripted expert.
        act_chunk_size: Actions an action chunking policy predicts per
            observation. Shorter than the benchmarked default on purpose.
    """

    candidate: str
    dataset: Path
    checkpoints: Path
    epochs: int
    batch_size: int
    learning_rate: float
    seed: int
    samples_per_crossing: int
    window_exit_meters: float
    act_chunk_size: int

    @property
    def digest(self) -> str:
        """Digest over the settings, so two runs are comparable by value."""
        return config_digest(
            {
                "candidate": self.candidate,
                "epochs": self.epochs,
                "batch_size": self.batch_size,
                "learning_rate": self.learning_rate,
                "seed": self.seed,
                "samples_per_crossing": self.samples_per_crossing,
                "window_exit_meters": self.window_exit_meters,
                "act_chunk_size": self.act_chunk_size,
            }
        )

    @classmethod
    def load(cls, path: Path, candidate: str | None = None) -> TrainingConfig:
        """Read a configuration file.

        Args:
            path: The YAML file.
            candidate: Overrides the candidate named in the file, so one file
                serves several architectures.

        Returns:
            The configuration.

        Raises:
            TrainingConfigError: If a required key is absent, naming it.
        """
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or "training" not in raw:
            raise TrainingConfigError(f"{path} has no 'training' section")
        section: dict[str, Any] = raw["training"]

        def need(key: str) -> Any:
            if key not in section:
                raise TrainingConfigError(
                    f"required configuration key 'training.{key}' is missing"
                )
            return section[key]

        return cls(
            candidate=candidate or need("candidate"),
            dataset=Path(need("dataset")),
            checkpoints=Path(need("checkpoints")),
            epochs=int(need("epochs")),
            batch_size=int(need("batch_size")),
            learning_rate=float(need("learning_rate")),
            seed=int(need("seed")),
            samples_per_crossing=_samples_per_crossing(need("samples_per_crossing")),
            window_exit_meters=float(need("window_exit_meters")),
            act_chunk_size=int(need("act_chunk_size")),
        )


def _samples_per_crossing(value: object) -> int:
    """Read how many looks a crossing keeps.

    Args:
        value: The YAML value.

    Returns:
        The count.

    Raises:
        TrainingConfigError: If the value is not an integer of at least one.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TrainingConfigError(
            f"training.samples_per_crossing is {value!r}; it must be an integer "
            f"of at least one"
        )
    return value
