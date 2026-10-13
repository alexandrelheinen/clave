"""Choose a channel by expected cost.

The same sum the routing crate computes. This module does not import
GTSAM. Normalization of a count table stays with the product that builds
the posterior.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from clave.belief.errors import BeliefError
from clave.belief.floor import reserve_floor
from clave.tracker.fusion import OUTCOMES


@dataclass(frozen=True)
class CostDecision:
    """The channel a posterior minimizes, and the class it still reports.

    Attributes:
        channel: The channel id with the lowest expected cost. Ties keep
            the lowest id.
        expected_cost: That channel's expected cost.
        leading_class: The first maximum among the taxonomy weights.
        leading_weight: The probability of that class.
    """

    channel: int
    expected_cost: float
    leading_class: str
    leading_weight: float


def floored_class(class_id: str, floor: float) -> tuple[float, ...]:
    """Return a posterior that puts the spare mass on one class.

    Args:
        class_id: An outcome name. A ground-truth label is one of these.
        floor: The smallest weight any outcome may hold.

    Returns:
        One probability per outcome.

    Raises:
        BeliefError: If `class_id` is not an outcome.
    """
    if class_id not in OUTCOMES:
        raise BeliefError(f"{class_id!r} is not an outcome")
    spike = tuple(1.0 if name == class_id else 0.0 for name in OUTCOMES)
    return reserve_floor(spike, floor)


def minimizing_channel(
    posterior: Sequence[float], rows: Sequence[tuple[int, Sequence[float]]]
) -> CostDecision:
    """Return the channel with the lowest expected cost.

    Args:
        posterior: One probability per outcome, in `OUTCOMES` order.
        rows: Channel id and one cost per outcome. Rows are visited in
            channel-id order, and a tie keeps the earlier id.

    Returns:
        The decision. The leading class is the first maximum of the eleven
        taxonomy weights. The reject outcome is not a class.

    Raises:
        BeliefError: If the posterior or a row has the wrong width, or a
            weight is not a finite non-negative number.
    """
    weights = _weights(posterior)
    if not rows:
        raise BeliefError("an expected-cost decision needs a cost row")
    ordered = sorted(rows, key=lambda row: row[0])
    best_channel, best_costs = ordered[0]
    best_cost = _expected(best_costs, weights, best_channel)
    for channel, costs in ordered[1:]:
        total = _expected(costs, weights, channel)
        if total < best_cost:
            best_channel = channel
            best_cost = total
    leading = 0
    classes = weights[:-1]
    for index, weight in enumerate(classes):
        if weight > classes[leading]:
            leading = index
    return CostDecision(best_channel, best_cost, OUTCOMES[leading], classes[leading])


def _expected(
    costs: Sequence[float], weights: tuple[float, ...], channel: int
) -> float:
    """Return the expected cost of one channel."""
    if len(costs) != len(weights):
        raise BeliefError(
            f"channel {channel} has {len(costs)} costs and the posterior "
            f"has {len(weights)} outcomes"
        )
    return math.fsum(cost * weight for cost, weight in zip(costs, weights, strict=True))


def _weights(posterior: Sequence[float]) -> tuple[float, ...]:
    """Read one finite non-negative weight per outcome."""
    if len(posterior) != len(OUTCOMES):
        raise BeliefError(
            f"a posterior spans {len(OUTCOMES)} outcomes and this one spans "
            f"{len(posterior)}"
        )
    weights: list[float] = []
    for value in posterior:
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise BeliefError(f"a posterior weight of {value!r} is not usable")
        weights.append(number)
    return tuple(weights)
