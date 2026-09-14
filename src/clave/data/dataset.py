"""Writing and reading datasets.

A dataset is a claim about what a model saw, so it resolves by digest. Two
training runs can then be shown to have seen the same bytes rather than assumed
to have.

Nothing is committed. Datasets are produced by a command and live outside the
repository, the same way corpora do.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from clave.data.composition import PartComposition, compose_parts
from clave.data.examples import Rollout
from clave.errors import ClaveError

DESCRIPTION_FILE = "dataset.json"


class DatasetError(ClaveError):
    """A dataset is malformed, or its contents do not match its digest."""


@dataclass(frozen=True)
class DatasetDescription:
    """Everything needed to identify a dataset and know what it holds.

    Attributes:
        digest: SHA-256 over the rollout archives, in a fixed order.
        seed: Seed the dataset was recorded under.
        config_digest: Digest of the world configuration used.
        example_count: Total captured frames.
        parts: Split part name to the rollout identities it holds.
        composition: Part name to its measured composition.
    """

    digest: str
    seed: int
    config_digest: str
    example_count: int
    parts: dict[str, list[str]]
    composition: dict[str, dict[str, object]]


def _archive_digest(paths: list[Path]) -> str:
    """Digest a set of archives in a fixed order."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write(
    root: Path,
    rollouts: tuple[Rollout, ...],
    parts: dict[str, tuple[str, ...]],
    seed: int,
    config_digest: str,
) -> DatasetDescription:
    """Write a dataset and describe it.

    Args:
        root: Directory to write into; created if absent.
        rollouts: The recorded rollouts.
        parts: Split part name to rollout identities.
        seed: Seed the recording ran under.
        config_digest: Digest of the world configuration used.

    Returns:
        The description, which is also written as JSON beside the archives.
    """
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for rollout in rollouts:
        path = root / f"{rollout.rollout_id}.npz"
        np.savez_compressed(
            path,
            frames=np.stack([example.frame for example in rollout.examples]),
            times=np.array([example.simulated_time for example in rollout.examples]),
            labels=np.array(
                json.dumps(
                    [
                        [label.as_dict() for label in example.labels]
                        for example in rollout.examples
                    ]
                )
            ),
        )
        written.append(path)

    compositions = compose_parts(rollouts, parts)
    description = DatasetDescription(
        digest=_archive_digest(written),
        seed=seed,
        config_digest=config_digest,
        example_count=sum(len(rollout.examples) for rollout in rollouts),
        parts={name: list(members) for name, members in parts.items()},
        composition={
            name: _composition_as_dict(value) for name, value in compositions.items()
        },
    )
    (root / DESCRIPTION_FILE).write_text(
        json.dumps(asdict(description), indent=2, sort_keys=True) + "\n"
    )
    return description


def _composition_as_dict(value: PartComposition) -> dict[str, object]:
    """Render a composition as plain data."""
    return {
        "example_count": value.example_count,
        "class_counts": value.class_counts,
        "absent_classes": list(value.absent_classes),
    }


def read(root: Path) -> DatasetDescription:
    """Read a dataset description and verify its contents.

    Args:
        root: The dataset directory.

    Returns:
        The description.

    Raises:
        DatasetError: If the description is absent, or the archives no longer
            digest to what the description records. A silently changed dataset
            is the failure this whole module exists to prevent.
    """
    path = root / DESCRIPTION_FILE
    if not path.is_file():
        raise DatasetError(f"{path} is missing; this is not a dataset directory")
    raw = json.loads(path.read_text())
    observed = _archive_digest(list(root.glob("*.npz")))
    if observed != raw["digest"]:
        raise DatasetError(
            f"{root} digests to {observed}, but its description records "
            f"{raw['digest']}; the contents changed"
        )
    return DatasetDescription(**raw)


def load_split(root: Path, part: str) -> tuple[Rollout, ...]:
    """Load the rollouts belonging to one split part.

    The archive format is this module's, so reading it is too. Training reads
    through here rather than opening archives itself.

    Args:
        root: The dataset directory.
        part: Split part name, such as `train`.

    Returns:
        The rollouts in that part, with frames and labels restored.

    Raises:
        DatasetError: If the dataset does not verify, or the part is unknown.
            Verification happens first, so training can never read a dataset
            whose contents changed since it was described.
    """
    from clave.data.examples import Example, ObjectLabel

    description = read(root)
    if part not in description.parts:
        known = ", ".join(sorted(description.parts))
        raise DatasetError(f"unknown split part {part!r}; this dataset has {known}")

    rollouts: list[Rollout] = []
    for rollout_id in description.parts[part]:
        archive = np.load(root / f"{rollout_id}.npz", allow_pickle=False)
        frames = archive["frames"]
        times = archive["times"]
        per_frame = json.loads(str(archive["labels"]))
        examples = tuple(
            Example(
                frame=frames[index],
                labels=tuple(
                    ObjectLabel(
                        object_id=item["object_id"],
                        material_class=item["material_class"],
                        channel=item["channel"],
                        position=tuple(item["position"]),
                        in_reachable_window=item["in_reachable_window"],
                        bbox=tuple(item["bbox"]) if item.get("bbox") else None,
                    )
                    for item in labels
                ),
                simulated_time=float(times[index]),
                seed=description.seed,
                config_digest=description.config_digest,
            )
            for index, labels in enumerate(per_frame)
        )
        rollouts.append(
            Rollout(rollout_id=rollout_id, seed=description.seed, examples=examples)
        )
    return tuple(rollouts)
