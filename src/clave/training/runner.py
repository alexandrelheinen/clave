"""The training run loop.

Records what a run cost, survives interruption, and refuses to read a dataset
whose contents changed since it was described.

The numbers this produces are costs, not accuracies. The dataset is small enough
that a loss curve here describes optimization on a toy.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from clave.candidates.bench import _machine
from clave.candidates.registry import REGISTRY
from clave.experiment.run import environment
from clave.experiment.seeding import seed_everything
from clave.training.adapters import training_examples
from clave.training.config import TrainingConfig
from clave.training.objectives import OBJECTIVES, batches_for


def run_record_path(checkpoints: Path, candidate: str) -> Path:
    """Where one candidate's run record lives.

    Per candidate rather than per directory: a single shared file means each
    run silently erases the one before it, and a comparison across
    architectures is exactly what these records exist for.
    """
    return checkpoints / f"{candidate}.run.json"


@dataclass(frozen=True)
class EpochRecord:
    """What one epoch cost and achieved."""

    index: int
    loss: float
    seconds: float


@dataclass
class TrainingRun:
    """A run and everything that produced it."""

    candidate: str
    seed: int
    config_digest: str
    dataset_digest: str
    machine: str
    threads: int
    environment: dict[str, str]
    epochs: list[EpochRecord] = field(default_factory=list)
    completed: bool = False
    unavailable_reason: str | None = None

    def write(self, path: Path) -> None:
        """Write the run as JSON a later tool can read without this package."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")


def _candidate_for(name: str) -> Any:
    """Find a candidate in the registry by name."""
    for candidate, _ in REGISTRY:
        if candidate.spec.name == name:
            return candidate
    raise KeyError(f"no candidate named {name!r} in the registry")


def train(config: TrainingConfig, window_exit: float) -> TrainingRun:
    """Train one candidate, checkpointing and measuring each epoch.

    Args:
        config: The run settings.
        window_exit: Belt coordinate where the reachable window ends, used by
            the policy adapter to replay the expert.

    Returns:
        The run record, whether it trained or reported the candidate
        unavailable.

    Raises:
        DatasetError: If the dataset does not verify.
        KeyError: If the candidate has no objective, meaning the simulation
            produces no signal it can learn from.
    """
    import torch

    from clave.data.dataset import read as read_dataset

    machine, threads = _machine()
    dataset_digest = read_dataset(config.dataset).digest
    run = TrainingRun(
        candidate=config.candidate,
        seed=config.seed,
        config_digest=config.digest,
        dataset_digest=dataset_digest,
        machine=machine,
        threads=threads,
        environment=environment(),
    )

    # Seed before the model is constructed, not after. Weight initialization
    # draws from the global generator, so seeding afterwards leaves the one
    # thing a run most needs to reproduce entirely unseeded.
    seed_everything(config.seed)

    if config.candidate == "act":
        # ACT is built with a chunk size suited to this data rather than the
        # upstream default v0.4.0 benchmarked. Recorded in the run's config
        # digest, so the two are never mistaken for one another.
        from clave.candidates.base import Candidate
        from clave.candidates.policy import ACT, build_act

        loaded = Candidate(ACT, lambda: build_act(config.act_chunk_size)).load()
    else:
        loaded = _candidate_for(config.candidate).load()
    if not loaded.loaded:
        run.unavailable_reason = loaded.unavailable_reason
        run.write(run_record_path(config.checkpoints, config.candidate))
        return run

    model: Any = loaded.model
    objective = OBJECTIVES[config.candidate]
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    examples = training_examples(config.dataset)

    start_epoch = _resume(config, model, optimizer)
    for epoch in range(start_epoch, config.epochs):
        model.train()
        began = time.perf_counter()
        total, batches = 0.0, 0
        for batch in batches_for(
            config.candidate,
            examples,
            config.batch_size,
            window_exit,
            config.act_chunk_size,
        ):
            optimizer.zero_grad()
            loss = objective(model, batch)
            loss.backward()
            optimizer.step()
            total += float(loss.detach())
            batches += 1
        run.epochs.append(
            EpochRecord(
                index=epoch,
                loss=total / max(batches, 1),
                seconds=time.perf_counter() - began,
            )
        )
        _checkpoint(config, model, optimizer, epoch)
        run.write(run_record_path(config.checkpoints, config.candidate))

    run.completed = True
    run.write(run_record_path(config.checkpoints, config.candidate))
    return run


def _checkpoint_path(config: TrainingConfig) -> Path:
    """Where a candidate's checkpoint lives."""
    return config.checkpoints / f"{config.candidate}.pt"


def _checkpoint(config: TrainingConfig, model: Any, optimizer: Any, epoch: int) -> None:
    """Write a checkpoint from which training can continue."""
    import torch

    config.checkpoints.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "candidate": config.candidate,
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            # An architecture whose shape depends on a hyperparameter cannot be
            # rebuilt from its name alone. ACT's action chunk is one of those,
            # and a checkpoint that does not carry it can only be loaded by a
            # reader that guesses the same number.
            "act_chunk_size": config.act_chunk_size,
        },
        _checkpoint_path(config),
    )


def _resume(config: TrainingConfig, model: Any, optimizer: Any) -> int:
    """Restore a checkpoint if one exists, returning the epoch to start at.

    A checkpoint written by a different candidate is refused rather than loaded,
    since restoring mismatched weights would fail confusingly much later.
    """
    import torch

    path = _checkpoint_path(config)
    if not path.is_file():
        return 0
    state = torch.load(path, weights_only=False)
    if state.get("candidate") != config.candidate:
        raise ValueError(
            f"{path} holds a checkpoint for {state.get('candidate')!r}, "
            f"not {config.candidate!r}"
        )
    model.load_state_dict(state["model"])
    optimizer.load_state_dict(state["optimizer"])
    return int(state["epoch"]) + 1
