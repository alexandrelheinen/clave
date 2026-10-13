"""The category product, against a hand calculation and the floor."""

from __future__ import annotations

import math

import pytest

from clave.belief.errors import BeliefError
from clave.belief.floor import reserve_floor
from clave.belief.posterior import (
    gaussian_likelihood,
    multiply,
    observation_factors,
    scale,
    with_floor,
)
from clave.tracker.fusion import OUTCOMES

pytest.importorskip("gtsam")

WIDTH = len(OUTCOMES)


def test_ac_sort_01_two_likelihoods_match_a_hand_product() -> None:
    """Two categorical likelihoods match the product written out by hand."""
    prior = (1.0,) * WIDTH
    first = (2.0, 1.0) + (1.0,) * (WIDTH - 2)
    second = (1.0, 3.0) + (1.0,) * (WIDTH - 2)
    product = multiply(prior, (first, second))
    expected = (2.0, 3.0) + (1.0,) * (WIDTH - 2)
    total = math.fsum(expected)
    assert product == pytest.approx(tuple(value / total for value in expected))


def test_ac_sort_04_a_gaussian_matches_the_density_at_a_fixed_mass() -> None:
    """A mass of 50 against mean 150 and deviation 100 is that Gaussian."""
    density = gaussian_likelihood(50.0, (150.0,), (100.0,))
    coefficient = (50.0 - 150.0) / 100.0
    expected = math.exp(-0.5 * coefficient * coefficient) / (
        100.0 * math.sqrt(2.0 * math.pi)
    )
    assert density == pytest.approx((expected,))
    assert density[0] == pytest.approx(0.0024197, abs=1e-7)


def test_ac_sort_05_a_missing_mass_omits_the_weight_factor() -> None:
    """No scale reading means no weight factor in the product."""
    discrete = ((1.0, 2.0),)
    factors = observation_factors(
        discrete, mass=None, mass_means=None, mass_deviations=None
    )
    assert factors == ((1.0, 2.0),)
    with pytest.raises(BeliefError, match="mass reading"):
        observation_factors(
            discrete, mass=50.0, mass_means=None, mass_deviations=(1.0, 1.0)
        )


def test_ac_sort_22_the_book_weight_underflow_is_lifted_to_the_floor() -> None:
    """A 50 g Gaussian underflows two categories, and the floor lifts them."""
    means = (20.0, 5.0, 15.0, 150.0, 300.0)
    deviations = (10.0, 5.0, 5.0, 100.0, 200.0)
    densities = gaussian_likelihood(50.0, means, deviations)
    assert densities[1] < 1e-12
    assert densities[2] < 1e-8
    raw = multiply((0.2, 0.3, 0.25, 0.2, 0.05), (densities,))
    assert raw[1] < 1e-12
    lifted = with_floor(raw, 0.0005)
    assert min(lifted) >= 0.0005
    assert lifted[1] == pytest.approx(0.0005, abs=1e-9)
    assert reserve_floor(raw, 0.0005) == lifted


def test_a_zero_weight_likelihood_does_not_move_the_prior() -> None:
    """A weight of zero is a factor of ones."""
    prior = multiply((1.0, 2.0, 3.0), ())
    assert multiply(prior, (scale((9.0, 0.1, 4.0), 0.0),)) == pytest.approx(prior)


def test_a_negative_likelihood_weight_is_refused() -> None:
    """A negative exponent would invert the reading."""
    with pytest.raises(BeliefError, match="likelihood weight"):
        scale((1.0, 1.0), -0.1)
