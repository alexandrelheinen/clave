"""The operator's category model, loaded only for expected-cost routing.

The confidence floor does not read these tables. A missing table fails at
load and names the key.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from clave.belief.errors import BeliefError
from clave.tracker.fusion import OUTCOMES

CONFIDENCE_FLOOR = "confidence_floor"
EXPECTED_COST = "expected_cost"


@dataclass(frozen=True)
class BeliefModel:
    """Counts and costs for one line.

    Attributes:
        prior_counts: One positive count per outcome, in `OUTCOMES` order.
        sensors: Conditional counts per sensor. Each row is one true outcome
            and holds one count per hard reading, in the same order.
        cost_channels: Channel ids, paired with `cost_rows`.
        cost_rows: One non-negative cost per outcome, one row per channel.
    """

    prior_counts: tuple[float, ...]
    sensors: dict[str, tuple[tuple[float, ...], ...]]
    cost_channels: tuple[int, ...]
    cost_rows: tuple[tuple[float, ...], ...]

    def likelihood(self, sensor: str, reading: int) -> tuple[float, ...]:
        """Return P(reading | outcome) up to the row's own normalization.

        The column is the likelihood of the outcomes given that hard reading.
        Rows are normalized by the product, so the stored values may be counts.

        Args:
            sensor: Which conditional table.
            reading: The hard label's index in `OUTCOMES`.

        Returns:
            One count per outcome.

        Raises:
            BeliefError: If the sensor or the reading is unknown.
        """
        table = self.sensors.get(sensor)
        if table is None:
            raise BeliefError(f"routing.sensor_cpts has no table {sensor!r}")
        if reading < 0 or reading >= len(OUTCOMES):
            raise BeliefError(
                f"a hard reading index of {reading} is outside {len(OUTCOMES)} outcomes"
            )
        return tuple(float(row[reading]) for row in table)

    def opening_weights(self, floor: float) -> tuple[float, ...]:
        """Return the prior a new track starts from, after the floor.

        Args:
            floor: The smallest weight any outcome may hold.

        Returns:
            One probability per outcome.
        """
        from clave.belief.posterior import multiply, with_floor

        return with_floor(multiply(self.prior_counts, ()), floor)


def load_routing_belief(routing: Mapping[str, Any]) -> BeliefModel | None:
    """Load the category model, or nothing when the line uses the floor.

    Args:
        routing: The `routing` mapping from the runtime configuration.

    Returns:
        The model when `rule` is `expected_cost`, otherwise `None`. The
        confidence floor does not consult the tables, so a malformed table
        beside that rule is ignored.

    Raises:
        BeliefError: If expected-cost routing omits a table or a row, naming
            the key.
    """
    rule = routing.get("rule", CONFIDENCE_FLOOR)
    if rule == CONFIDENCE_FLOOR:
        return None
    if rule != EXPECTED_COST:
        raise BeliefError(f"routing.rule {rule!r} is not a known rule")
    prior = _counts(_require(routing, "prior_counts"), "routing.prior_counts")
    sensors = _sensors(_require(routing, "sensor_cpts"))
    channels, rows = _cost(routing)
    return BeliefModel(
        prior_counts=prior,
        sensors=sensors,
        cost_channels=channels,
        cost_rows=rows,
    )


def _require(routing: Mapping[str, Any], key: str) -> Any:
    """Read one routing key, naming it when it is absent."""
    if key not in routing:
        raise BeliefError(f"required configuration key 'routing.{key}' is missing")
    return routing[key]


def _counts(raw: Any, where: str) -> tuple[float, ...]:
    """Read one positive count per outcome."""
    if not isinstance(raw, list) or len(raw) != len(OUTCOMES):
        raise BeliefError(
            f"{where} needs {len(OUTCOMES)} counts and has "
            f"{len(raw) if isinstance(raw, list) else 'no list'}"
        )
    counts: list[float] = []
    for value in raw:
        number = float(value)
        if not math.isfinite(number) or number <= 0.0:
            raise BeliefError(f"{where} holds {value!r}, which is not a positive count")
        counts.append(number)
    return tuple(counts)


def _sensors(raw: Any) -> dict[str, tuple[tuple[float, ...], ...]]:
    """Read each sensor's conditional table."""
    if not isinstance(raw, dict) or not raw:
        raise BeliefError("routing.sensor_cpts needs one table per discrete sensor")
    sensors: dict[str, tuple[tuple[float, ...], ...]] = {}
    width = len(OUTCOMES)
    for name, rows in raw.items():
        where = f"routing.sensor_cpts.{name}"
        if not isinstance(rows, list) or len(rows) != width:
            raise BeliefError(f"{where} needs {width} rows, one per outcome")
        parsed: list[tuple[float, ...]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != width:
                raise BeliefError(f"{where} row {index} needs {width} counts")
            counts = tuple(float(value) for value in row)
            if any(not math.isfinite(value) or value < 0.0 for value in counts):
                raise BeliefError(f"{where} row {index} holds a negative count")
            if math.fsum(counts) <= 0.0:
                raise BeliefError(f"{where} row {index} is empty")
            parsed.append(counts)
        sensors[str(name)] = tuple(parsed)
    return sensors


def _cost(
    routing: Mapping[str, Any],
) -> tuple[tuple[int, ...], tuple[tuple[float, ...], ...]]:
    """Read one cost row per channel the map names."""
    raw = _require(routing, "cost")
    channels = _require(routing, "channels")
    if not isinstance(channels, dict):
        raise BeliefError("routing.channels is not a mapping")
    if not isinstance(raw, list):
        raise BeliefError("routing.cost is not a list of rows")
    by_channel: dict[int, tuple[float, ...]] = {}
    width = len(OUTCOMES)
    for index, row in enumerate(raw):
        where = f"routing.cost[{index}]"
        if not isinstance(row, dict) or "channel" not in row or "costs" not in row:
            raise BeliefError(f"{where} needs a channel and a costs list")
        channel = int(row["channel"])
        costs_raw = row["costs"]
        if not isinstance(costs_raw, list) or len(costs_raw) != width:
            raise BeliefError(f"routing.cost channel {channel} needs {width} costs")
        costs = tuple(float(value) for value in costs_raw)
        if any(not math.isfinite(value) or value < 0.0 for value in costs):
            raise BeliefError(f"routing.cost channel {channel} holds a negative cost")
        by_channel[channel] = costs
    ordered: list[int] = []
    rows: list[tuple[float, ...]] = []
    for channel in channels.values():
        number = int(channel)
        if number not in by_channel:
            raise BeliefError(
                f"required configuration key 'routing.cost' is missing a row "
                f"for channel {number}"
            )
        if number not in ordered:
            ordered.append(number)
            rows.append(by_channel[number])
    return tuple(ordered), tuple(rows)
