"""The training run loop.

Records what a run cost, survives interruption, and refuses to read a dataset
whose contents changed since it was described.

The numbers this produces are costs, not accuracies. The dataset is small enough
that a loss curve here describes optimization on a toy.
"""

from __future__ import annotations

import gc
import json
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from clave.candidates.bench import _machine
from clave.candidates.registry import REGISTRY
from clave.experiment.run import environment
from clave.experiment.seeding import seed_everything
from clave.progress import Progress, examples_in, frame_total
from clave.training.config import TrainingConfig
from clave.training.memory import (
    MemoryBudget,
    release_freed_pages,
    require_within_budget,
)
from clave.training.objectives import OBJECTIVES, batches_for
from clave.training.sample import (
    FrameSample,
    SampleError,
    build_frame_sample,
    capture_interval_seconds,
)

LOGGER = logging.getLogger(__name__)


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
    input_side_pixels: int
    resident_limit_bytes: int
    sample_digest: str = ""
    epochs: list[EpochRecord] = field(default_factory=list)
    completed: bool = False
    unavailable_reason: str | None = None

    def write(self, path: Path) -> None:
        """Write the run as JSON a later tool can read without this package."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")


def _training_rollouts(dataset: Path) -> Any:
    """Yield one training rollout at a time so an epoch does not hold the corpus."""
    from clave.data.dataset import iter_split

    return iter_split(dataset, "train")


def _candidate_for(name: str) -> Any:
    """Find a candidate in the registry by name."""
    for candidate, _ in REGISTRY:
        if candidate.spec.name == name:
            return candidate
    raise KeyError(f"no candidate named {name!r} in the registry")


def train(
    config: TrainingConfig,
    window_exit: float,
    *,
    budget: MemoryBudget,
    world: Path,
) -> TrainingRun:
    """Train one candidate, checkpointing and measuring each epoch.

    Args:
        config: The run settings.
        window_exit: Belt coordinate where the reachable window ends, used by
            the policy adapter to replay the expert.
        budget: Resident-memory ceiling and the image side the step resizes to.
        world: Sorting-line configuration. The sample reads the detection
            camera's along-travel footprint from it.

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
    description = read_dataset(config.dataset)
    release_freed_pages()
    dataset_digest = description.digest
    run = TrainingRun(
        candidate=config.candidate,
        seed=config.seed,
        config_digest=config.digest,
        dataset_digest=dataset_digest,
        machine=machine,
        threads=threads,
        environment=environment(),
        input_side_pixels=budget.input_side_pixels,
        resident_limit_bytes=budget.resident_limit_bytes,
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

    start_epoch, sample = _resume(config, model, optimizer)
    if sample is None:
        sample = _draw_sample(config, description, world)
        sample.write(_sample_path(config))
    run.sample_digest = sample.digest
    catalogued = frame_total(description, "train")
    LOGGER.info(
        "sample %s of %s frames, %s per crossing, %s",
        sample.frame_count,
        catalogued if catalogued is not None else "unknown",
        config.samples_per_crossing,
        sample.digest[:16],
    )
    for param_group in optimizer.param_groups:
        param_group.setdefault("initial_lr", config.learning_rate)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=max(config.epochs, 1),
        eta_min=config.learning_rate * 0.01,
        last_epoch=start_epoch - 1,
    )

    for epoch in range(start_epoch, config.epochs):
        LOGGER.info("epoch %s/%s", epoch + 1, config.epochs)
        model.train()
        began = time.perf_counter()
        total, batches = 0.0, 0
        with Progress(
            sample.frame_count,
            f"epoch {epoch + 1}/{config.epochs}",
            "frame",
            repeats=config.epochs,
            repeat_index=epoch,
        ) as bar:
            for rollout in _training_rollouts(config.dataset):
                rollout_id = rollout.rollout_id
                indexes = sample.picks.get(rollout_id)
                if indexes is None:
                    raise SampleError(f"sample has no pick for rollout {rollout_id}")
                pending = [rollout.examples[index] for index in indexes]
                del rollout
                gc.collect()
                release_freed_pages()
                random.Random(f"{config.seed}:{epoch}:{rollout_id}").shuffle(pending)
                while pending:
                    chunk = tuple(pending[: config.batch_size])
                    del pending[: config.batch_size]
                    for batch in batches_for(
                        config.candidate,
                        chunk,
                        config.batch_size,
                        window_exit,
                        config.act_chunk_size,
                        augment=True,
                        input_side=budget.input_side_pixels,
                    ):
                        optimizer.zero_grad()
                        loss = objective(model, batch)
                        loss.backward()
                        optimizer.step()
                        total += float(loss.detach())
                        batches += 1
                        seen = examples_in(batch)
                        del batch, loss
                        gc.collect()
                        release_freed_pages()
                        resident = require_within_budget(budget.resident_limit_bytes)
                        bar.update(
                            seen,
                            loss=total / batches,
                            rss_mib=resident / (1024 * 1024),
                        )
                    del chunk
        scheduler.step()
        run.epochs.append(
            EpochRecord(
                index=epoch,
                loss=total / max(batches, 1),
                seconds=time.perf_counter() - began,
            )
        )
        _checkpoint(config, model, optimizer, epoch, budget.input_side_pixels, sample)
        run.write(run_record_path(config.checkpoints, config.candidate))
        LOGGER.info(
            "epoch %s loss %.4f in %.1fs",
            epoch + 1,
            run.epochs[-1].loss,
            run.epochs[-1].seconds,
        )

    run.completed = True
    run.write(run_record_path(config.checkpoints, config.candidate))
    return run


def _checkpoint_path(config: TrainingConfig) -> Path:
    """Where a candidate's checkpoint lives."""
    return config.checkpoints / f"{config.candidate}.pt"


def _sample_path(config: TrainingConfig) -> Path:
    """Where the stored pick for a candidate lives."""
    return config.checkpoints / f"{config.candidate}.sample.json"


def _draw_sample(config: TrainingConfig, description: Any, world: Path) -> FrameSample:
    """Draw a pick from the camera footprint and the rollout belt speeds."""
    from clave.world.config import load as load_world
    from clave.world.scene import detection_along_travel_meters

    along = detection_along_travel_meters(load_world(world))
    members = description.parts.get("train", ())
    by_name = {item.name: item for item in description.files}
    interval = 0.0
    for rollout_id in members:
        recorded = by_name.get(f"{rollout_id}.npz")
        speed = None if recorded is None else recorded.belt_speed_meters_per_second
        if speed is not None and speed > 0.0:
            interval = capture_interval_seconds(config.dataset, rollout_id)
            break
    return build_frame_sample(
        description,
        along_travel_meters=along,
        capture_interval_seconds=interval,
        samples_per_crossing=config.samples_per_crossing,
        seed=config.seed,
    )


def _checkpoint(
    config: TrainingConfig,
    model: Any,
    optimizer: Any,
    epoch: int,
    input_side_pixels: int,
    sample: FrameSample,
) -> None:
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
            "input_side_pixels": input_side_pixels,
            "sample": sample.payload(),
        },
        _checkpoint_path(config),
    )


def _resume(
    config: TrainingConfig, model: Any, optimizer: Any
) -> tuple[int, FrameSample | None]:
    """Restore a checkpoint if one exists.

    A checkpoint written by a different candidate is refused, since restoring
    mismatched weights would fail much later. A checkpoint that has weights
    and no stored pick is refused too: those weights saw every frame, and a
    new draw would train them on a different set.

    Returns:
        The epoch to start at, and the stored pick. The pick is None only
        when no checkpoint file exists.
    """
    import torch

    from clave.training.sample import resolve_stored_sample

    path = _checkpoint_path(config)
    if not path.is_file():
        return 0, None
    state = torch.load(path, weights_only=False)
    if state.get("candidate") != config.candidate:
        raise ValueError(
            f"{path} holds a checkpoint for {state.get('candidate')!r}, "
            f"not {config.candidate!r}"
        )
    raw = state.get("sample")
    stored = FrameSample.from_payload(raw) if isinstance(raw, dict) else None
    sample = resolve_stored_sample(
        stored,
        checkpoint=True,
        samples_per_crossing=config.samples_per_crossing,
    )
    model.load_state_dict(state["model"])
    optimizer.load_state_dict(state["optimizer"])
    if sample is None:
        raise SampleError(f"{path} produced no frame sample")
    return int(state["epoch"]) + 1, sample
