"""The chapter's arithmetic, on the pinned GTSAM.

The numbers are the published fixture from chapter 2. They are not the
line's costs, and they are not a configuration CLAVE loads.
"""

from __future__ import annotations

import math

import pytest

gtsam = pytest.importorskip("gtsam")

CATEGORY = (0, 5)
CONDUCTIVITY = (1, 2)
DETECTOR = (2, 3)
PRIOR_SPEC = "200/300/250/200/50"
CONDUCTIVITY_SPEC = "99/1 99/1 10/90 15/85 95/5"
DETECTOR_SPEC = "2/88/10 2/20/78 33/33/34 33/33/34 95/2/3"
# Means and standard deviations, in grams, in category order.
WEIGHT_MODEL = ((20.0, 10.0), (5.0, 5.0), (15.0, 5.0), (150.0, 100.0), (300.0, 200.0))
COST = (
    (2.0, 2.0, 4.0, 6.0, 0.0),
    (1.0, 1.0, 0.0, 0.0, 2.0),
    (0.0, 0.0, 5.0, 10.0, 3.0),
    (1.0, 1.0, 1.0, 1.0, 1.0),
)
METAL_BIN = 1
NOP = 3


def _expected(
    costs: tuple[tuple[float, ...], ...], belief: tuple[float, ...]
) -> list[float]:
    """Return one expected cost per action."""
    totals: list[float] = []
    for row in costs:
        totals.append(
            math.fsum(cost * weight for cost, weight in zip(row, belief, strict=True))
        )
    return totals


def _density(mass: float, mean: float, deviation: float) -> float:
    """Return one Gaussian density."""
    coefficient = (mass - mean) / deviation
    normalizer = deviation * math.sqrt(2.0 * math.pi)
    return math.exp(-0.5 * coefficient * coefficient) / normalizer


def test_ac_sort_10_prior_cost_and_conductivity_match_the_chapter() -> None:
    """The prior, the costs, and a false conductivity reading match the chapter."""
    prior = gtsam.DiscreteDistribution(CATEGORY, PRIOR_SPEC)
    pmf = tuple(float(value) for value in prior.pmf())
    assert pmf == pytest.approx((0.20, 0.30, 0.25, 0.20, 0.05))

    costs = _expected(COST, pmf)
    assert costs == pytest.approx((3.2, 0.6, 3.4, 1.0))
    assert min(range(len(costs)), key=lambda index: costs[index]) == METAL_BIN

    conditional = gtsam.DiscreteConditional(CONDUCTIVITY, [CATEGORY], CONDUCTIVITY_SPEC)
    observed = gtsam.DiscreteValues()
    observed[CONDUCTIVITY[0]] = 0
    posterior = gtsam.DiscreteDistribution(conditional.likelihood(observed) * prior)
    rounded = [round(float(value), 3) for value in posterior.pmf()]
    assert rounded == [0.331, 0.497, 0.042, 0.050, 0.079]


def test_ac_sort_11_the_given_posterior_selects_nop() -> None:
    """The chapter's posterior minimizes at the action that does nothing."""
    belief = (0.2, 0.3, 0.1, 0.1, 0.3)
    costs = _expected(COST, belief)
    assert costs == pytest.approx((2.0, 1.1, 2.4, 1.0))
    assert min(range(len(costs)), key=lambda index: costs[index]) == NOP


def test_ac_sort_10_three_sensors_peak_on_cardboard_and_scrap() -> None:
    """Weight, conductivity, and a cardboard detection peak where the chapter does."""
    prior = gtsam.DiscreteDistribution(CATEGORY, PRIOR_SPEC)
    conductivity = gtsam.DiscreteConditional(
        CONDUCTIVITY, [CATEGORY], CONDUCTIVITY_SPEC
    )
    detector = gtsam.DiscreteConditional(DETECTOR, [CATEGORY], DETECTOR_SPEC)
    false_reading = gtsam.DiscreteValues()
    false_reading[CONDUCTIVITY[0]] = 0
    cardboard = gtsam.DiscreteValues()
    cardboard[DETECTOR[0]] = 1
    densities = [_density(50.0, mean, deviation) for mean, deviation in WEIGHT_MODEL]
    weight = gtsam.DecisionTreeFactor(CATEGORY, densities)
    posterior = gtsam.DiscreteDistribution(
        weight
        * detector.likelihood(cardboard)
        * conductivity.likelihood(false_reading)
        * prior
    )
    pmf = tuple(float(value) for value in posterior.pmf())
    assert pmf[0] == pytest.approx(0.757, abs=1e-3)
    assert pmf[3] == pytest.approx(0.235, abs=1e-3)
    assert pmf[1] < 1e-8
    assert pmf[2] < 1e-8
