"""Run-length packing for instance masks.

Shared by the MuJoCo render bridge and the learned detector so both produce the
same `PixelMask` shape without either importing the other.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.tracker.evidence import PixelMask


def runs_of(covered: NDArray[np.bool_]) -> tuple[tuple[int, int, int], ...]:
    """Return the horizontal runs of a boolean pixel mask.

    Args:
        covered: A height by width boolean array.

    Returns:
        One `(row, start_column, length)` triple per run.
    """
    runs: list[tuple[int, int, int]] = []
    for row in np.flatnonzero(covered.any(axis=1)):
        columns = np.flatnonzero(covered[row])
        breaks = np.flatnonzero(np.diff(columns) > 1)
        starts = np.concatenate(([0], breaks + 1))
        ends = np.concatenate((breaks, [len(columns) - 1]))
        for start, end in zip(starts, ends, strict=True):
            runs.append((int(row), int(columns[start]), int(end - start + 1)))
    return tuple(runs)


def pixel_mask_from_array(covered: Any) -> PixelMask | None:
    """Build a `PixelMask` from a boolean array, or None when empty.

    Args:
        covered: Height by width mask. Truthy pixels belong to the instance.

    Returns:
        The packed mask, or None when no pixel is set.
    """
    array = np.asarray(covered, dtype=bool)
    if array.ndim != 2:
        raise ValueError(f"a mask array must be 2-D, got shape {array.shape}")
    packed = runs_of(array)
    if not packed:
        return None
    height, width = array.shape
    return PixelMask(width=int(width), height=int(height), runs=packed)
