"""Loading the category model, and the rule that ignores it."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from clave.belief.errors import BeliefError
from clave.belief.model import CONFIDENCE_FLOOR, load_routing_belief
from clave.tracker.fusion import OUTCOMES

ROOT = Path(__file__).resolve().parents[2]
WIDTH = len(OUTCOMES)


def _routing() -> dict[str, object]:
    """One complete expected-cost block, with a row for every channel."""
    channels = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    table = [[1.0] * WIDTH for _ in range(WIDTH)]
    return {
        "rule": "expected_cost",
        "prior_counts": [1.0] * WIDTH,
        "sensor_cpts": {"material": table},
        "channels": channels,
        "cost": [{"channel": index, "costs": [1.0] * WIDTH} for index in range(WIDTH)],
    }


def test_ac_sort_03_a_missing_table_names_the_key() -> None:
    """Expected cost refuses a missing prior, sensor table, and cost row by name."""
    missing_prior = _routing()
    del missing_prior["prior_counts"]
    with pytest.raises(BeliefError, match="routing.prior_counts"):
        load_routing_belief(missing_prior)

    missing_sensors = _routing()
    del missing_sensors["sensor_cpts"]
    with pytest.raises(BeliefError, match="routing.sensor_cpts"):
        load_routing_belief(missing_sensors)

    missing_row = _routing()
    cost = missing_row["cost"]
    assert isinstance(cost, list)
    del cost[4]
    with pytest.raises(BeliefError, match=r"routing.cost.*channel 4"):
        load_routing_belief(missing_row)


def test_ac_sort_21_the_confidence_floor_does_not_read_the_tables() -> None:
    """A floor rule ignores a garbage table, including when the rule is absent."""
    garbage = _routing()
    garbage["rule"] = CONFIDENCE_FLOOR
    garbage["prior_counts"] = "not counts"
    assert load_routing_belief(garbage) is None
    del garbage["rule"]
    assert load_routing_belief(garbage) is None


def test_an_unknown_rule_is_refused() -> None:
    """A rule the loader does not know fails at load."""
    routing = _routing()
    routing["rule"] = "cheapest_label"
    with pytest.raises(BeliefError, match="routing.rule"):
        load_routing_belief(routing)


def test_ac_sort_06_shipped_configuration_has_no_conductivity() -> None:
    """The shipped sensor and routing files name no conductivity table."""
    for path in (ROOT / "configs").rglob("*"):
        if path.is_file():
            assert "conductivity" not in path.read_text(encoding="utf-8").lower()
    routing = yaml.safe_load((ROOT / "configs" / "runtime" / "sitl.yml").read_text())
    assert load_routing_belief(routing["routing"]) is None
