"""The floor under a category distribution.

A zero entry never recovers under multiplication. Reserving the floor first,
and sharing only what remains, keeps every outcome reachable. Lifting each
weight and then dividing puts the lifted ones back under the floor.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def reserve_floor(weights: Sequence[float], floor: float) -> tuple[float, ...]:
    """Return a distribution in which every outcome holds at least `floor`.

    Args:
        weights: A distribution, in outcome order.
        floor: The smallest weight any outcome may hold.

    Returns:
        A distribution summing to one. The ordering of `weights` is unchanged.
    """
    reserved = floor * len(weights)
    spare = 1.0 - reserved
    excess = [max(0.0, value - floor) for value in weights]
    total = math.fsum(excess)
    if total <= 0.0:
        return (1.0 / len(weights),) * len(weights)
    return tuple(floor + spare * value / total for value in excess)
