"""The channel a posterior minimizes.

The sums are the ones the routing crate computes. These tests read the
reasoned default and do not edit it.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from clave.belief.decide import floored_class, minimizing_channel
from clave.belief.errors import BeliefError
from clave.runtime.loop import load_routing_policy
from clave.tracker.fusion import OUTCOMES

ROOT = Path(__file__).resolve().parents[2]
DEBUG = ROOT / "configs" / "debug" / "expected-cost.yml"


def _rows() -> tuple[tuple[int, tuple[float, ...]], ...]:
    """The reasoned default, as channel rows."""
    policy = load_routing_policy(DEBUG)
    assert policy.cost is not None
    return policy.cost


def _posterior(weights: dict[str, float]) -> tuple[float, ...]:
    """A posterior with the named outcomes set and the rest at zero."""
    values = [0.0] * len(OUTCOMES)
    for name, weight in weights.items():
        values[OUTCOMES.index(name)] = weight
    return tuple(values)


def _floor() -> float:
    """The fusion floor the simulator builds a class spike with."""
    raw = yaml.safe_load(
        (ROOT / "configs" / "perception" / "fusion.yml").read_text(encoding="utf-8")
    )
    return float(raw["posterior"]["floor"])


def test_a_mixed_fiber_and_ferrous_belief_takes_the_ferrous_channel() -> None:
    """Cardboard at 0.6 and ferrous at 0.4 minimizes on the ferrous channel."""
    decision = minimizing_channel(_posterior({"M-08": 0.6, "M-06": 0.4}), _rows())
    assert decision.channel == 6
    assert decision.expected_cost == pytest.approx(1.8)
    assert decision.leading_class == "M-08"
    assert decision.leading_weight == pytest.approx(0.6)


def test_a_split_between_aluminum_and_ferrous_takes_reject() -> None:
    """Equal metal weight makes reject cheaper than either metal channel."""
    decision = minimizing_channel(_posterior({"M-05": 0.5, "M-06": 0.5}), _rows())
    assert decision.channel == 0
    assert decision.expected_cost == pytest.approx(2.0)
    assert decision.leading_class == "M-05"
    assert decision.leading_weight == pytest.approx(0.5)


def test_a_floored_class_minimizes_on_its_mapped_channel() -> None:
    """A spike on the true class agrees with the channel map."""
    floor = _floor()
    policy = load_routing_policy(DEBUG)
    assert policy.cost is not None
    for class_id, channel in policy.channels.items():
        decision = minimizing_channel(floored_class(class_id, floor), policy.cost)
        assert decision.channel == channel
        assert decision.leading_class == class_id
    reject = minimizing_channel(floored_class("reject", floor), policy.cost)
    assert reject.channel == policy.reject_channel
    assert reject.leading_class == OUTCOMES[0]


def test_a_tie_keeps_the_lowest_channel_id() -> None:
    """Equal expected cost keeps the earlier channel id."""
    width = len(OUTCOMES)
    weights = (1.0,) + (0.0,) * (width - 1)
    rows = ((3, (1.0,) * width), (1, (1.0,) * width))
    assert minimizing_channel(weights, rows).channel == 1


def test_a_posterior_of_the_wrong_width_is_refused() -> None:
    """The posterior has one weight per outcome."""
    with pytest.raises(BeliefError, match="outcomes"):
        minimizing_channel((1.0,), ((0, (0.0,) * len(OUTCOMES)),))


def test_an_empty_table_is_refused() -> None:
    """A decision needs a row to minimize over."""
    with pytest.raises(BeliefError, match="cost row"):
        minimizing_channel((0.0,) * len(OUTCOMES), ())


def test_a_negative_weight_is_refused() -> None:
    """A weight has to be a finite non-negative number."""
    weights = [0.0] * len(OUTCOMES)
    weights[0] = -0.1
    with pytest.raises(BeliefError, match="not usable"):
        minimizing_channel(tuple(weights), ((0, (0.0,) * len(OUTCOMES)),))


def test_a_non_finite_weight_is_refused() -> None:
    """NaN is not a probability the sum can use."""
    weights = [0.0] * len(OUTCOMES)
    weights[0] = math.nan
    with pytest.raises(BeliefError, match="not usable"):
        minimizing_channel(tuple(weights), ((0, (0.0,) * len(OUTCOMES)),))


def test_a_row_of_the_wrong_width_is_refused() -> None:
    """A cost row has one cell per outcome."""
    with pytest.raises(BeliefError, match="costs"):
        minimizing_channel((0.0,) * len(OUTCOMES), ((0, (0.0,)),))


def test_an_unknown_class_is_not_a_spike() -> None:
    """A ground-truth label has to be an outcome."""
    with pytest.raises(BeliefError, match="not an outcome"):
        floored_class("M-99", 0.01)
