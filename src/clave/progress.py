"""A frame bar for a long training or validation run.

The bar is the live view. The run record and the validation score stay the
numbers a later command prints. tqdm is optional at import time so a tree
checked without it still trains.
"""

from __future__ import annotations

from typing import Any

from clave.data.dataset import DatasetDescription


def frame_total(description: DatasetDescription, part: str) -> int | None:
    """Frames stored for one split part.

    Args:
        description: A dataset description already read from disk.
        part: Split part name, such as `train` or `validation`.

    Returns:
        The sum of archive frame counts, or None when the part or a file
        record is missing. None leaves the bar without a known length.
    """
    members = description.parts.get(part)
    if members is None:
        return None
    by_name = {item.name: item for item in description.files}
    total = 0
    for rollout_id in members:
        recorded = by_name.get(f"{rollout_id}.npz")
        if recorded is None:
            return None
        total += recorded.frame_count
    return total if total > 0 else None


def examples_in(batch: Any) -> int:
    """How many examples one training batch holds.

    Classification and policy batches lead with the image tensor. Detection
    batches lead with a list of images. An action-chunking batch is a
    dictionary keyed the way the policy names an observation.

    Args:
        batch: One batch yielded by the candidate's adapter.

    Returns:
        The example count.
    """
    payload = batch["observation.image"] if isinstance(batch, dict) else batch[0]
    shape = getattr(payload, "shape", None)
    if shape is not None and len(shape) > 0:
        return int(shape[0])
    return len(payload)


class Progress:
    """Counts frames and keeps the latest metric on the bar.

    Attributes:
        completed: Frames reported so far.
        metrics: The latest values shown beside the bar.
    """

    def __init__(self, total: int | None, desc: str, unit: str) -> None:
        """Open a bar.

        Args:
            total: Frames expected, or None when the length is unknown.
            desc: Short label, such as the epoch.
            unit: What one step is, usually a frame.
        """
        self.completed = 0
        self.metrics: dict[str, float] = {}
        self._bar = _open_bar(total, desc, unit)

    def update(self, n: int = 1, **metrics: float) -> None:
        """Advance the bar and replace the metrics it shows.

        Args:
            n: Frames just finished. Zero refreshes the metrics only.
            metrics: Named values, printed with four digits.
        """
        self.completed += n
        if metrics:
            self.metrics = dict(metrics)
        if self._bar is None:
            return
        if metrics:
            self._bar.set_postfix(
                {key: f"{value:.4f}" for key, value in metrics.items()},
                refresh=n == 0,
            )
        if n:
            self._bar.update(n)

    def close(self) -> None:
        """Finish the bar.

        A detector skips a frame with nothing visible, and a policy skips a
        frame with no demonstration, so the count can stop short of the
        archive length. The finished bar shows the frames that were actually
        used.
        """
        if self._bar is None:
            return
        total = self._bar.total
        if total is not None and self._bar.n < total:
            self._bar.total = self._bar.n
            self._bar.refresh()
        self._bar.close()
        self._bar = None

    def __enter__(self) -> Progress:
        """Return the bar."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the bar when the block leaves."""
        self.close()


def _open_bar(total: int | None, desc: str, unit: str) -> Any:
    """Open a tqdm bar, or nothing when the library is absent."""
    try:
        from tqdm import tqdm
    except ImportError:
        return None
    return tqdm(
        total=total,
        desc=desc,
        unit=unit,
        disable=None,
        dynamic_ncols=True,
        leave=True,
    )
