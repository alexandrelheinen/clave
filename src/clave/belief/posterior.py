"""The category product, computed with GTSAM's discrete types.

Callers pass counts and likelihoods. The integer key GTSAM uses for the
category variable is allocated here and discarded with the factor.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import gtsam

from clave.belief.errors import BeliefError
from clave.belief.floor import reserve_floor


def multiply(
    prior: Sequence[float], factors: Sequence[Sequence[float]]
) -> tuple[float, ...]:
    """Return the normalized product of a prior and zero or more likelihoods.

    Args:
        prior: One unnormalized weight per outcome. GTSAM normalizes it.
        factors: Likelihoods, each one weight per outcome. A likelihood does
            not have to sum to one.

    Returns:
        One probability per outcome, summing to one.

    Raises:
        BeliefError: If a factor has a different length, or the product is
            zero everywhere.
    """
    count = len(prior)
    if count == 0:
        raise BeliefError("a category product needs at least one outcome")
    if any(not math.isfinite(value) or value < 0.0 for value in prior):
        raise BeliefError("a prior weight is negative or not finite")
    key = (0, count)
    distribution = gtsam.DiscreteDistribution(key, _spec(prior))
    for factor in factors:
        if len(factor) != count:
            raise BeliefError(
                f"a likelihood spans {count} outcomes and this one spans {len(factor)}"
            )
        if any(not math.isfinite(value) or value < 0.0 for value in factor):
            raise BeliefError("a likelihood weight is negative or not finite")
        tree = gtsam.DecisionTreeFactor(key, [float(value) for value in factor])
        distribution = gtsam.DiscreteDistribution(tree * distribution)
    weights = tuple(float(value) for value in distribution.pmf())
    if not math.isfinite(math.fsum(weights)) or math.fsum(weights) <= 0.0:
        raise BeliefError("the product leaves no probability anywhere")
    return weights


def scale(likelihood: Sequence[float], weight: float) -> tuple[float, ...]:
    """Raise a likelihood to `weight` so a weak reading moves the belief less.

    Args:
        likelihood: One value per outcome.
        weight: How much the reading counts. Zero leaves the belief unchanged
            when the result is multiplied in, because every entry becomes one.

    Returns:
        The scaled likelihood.

    Raises:
        BeliefError: If `weight` is negative or a likelihood entry is not a
            finite non-negative number.
    """
    if not math.isfinite(weight) or weight < 0.0:
        raise BeliefError(f"a likelihood weight of {weight} is not usable")
    if weight == 0.0:
        return tuple(1.0 for _ in likelihood)
    scaled: list[float] = []
    for value in likelihood:
        if not math.isfinite(value) or value < 0.0:
            raise BeliefError("a likelihood weight is negative or not finite")
        scaled.append(value**weight)
    return tuple(scaled)


def with_floor(weights: Sequence[float], floor: float) -> tuple[float, ...]:
    """Apply the category floor after a product has been normalized.

    Args:
        weights: A normalized distribution.
        floor: The smallest weight any outcome may hold.

    Returns:
        The floored distribution.
    """
    return reserve_floor(weights, floor)


def gaussian_likelihood(
    mass: float, means: Sequence[float], deviations: Sequence[float]
) -> tuple[float, ...]:
    """Score each outcome by a Gaussian density at one mass.

    Args:
        mass: The measured mass.
        means: One mean per outcome, in the same units as `mass`.
        deviations: One standard deviation per outcome, in those units.

    Returns:
        One density per outcome. The values are a likelihood, not a
        distribution.

    Raises:
        BeliefError: If the arguments disagree in length or a deviation is
            not positive.
    """
    if len(means) != len(deviations):
        raise BeliefError(
            f"a mass model has {len(means)} means and {len(deviations)} deviations"
        )
    if not math.isfinite(mass):
        raise BeliefError(f"a mass of {mass} is not a reading")
    densities: list[float] = []
    for mean, deviation in zip(means, deviations, strict=True):
        if not math.isfinite(mean) or not math.isfinite(deviation) or deviation <= 0.0:
            raise BeliefError(
                f"a mass model entry ({mean}, {deviation}) is not a Gaussian"
            )
        coefficient = (mass - mean) / deviation
        coefficient = -0.5 * coefficient * coefficient
        normalizer = deviation * math.sqrt(2.0 * math.pi)
        densities.append(math.exp(coefficient) / normalizer)
    return tuple(densities)


def observation_factors(
    discrete: Sequence[Sequence[float]],
    *,
    mass: float | None,
    mass_means: Sequence[float] | None,
    mass_deviations: Sequence[float] | None,
) -> tuple[tuple[float, ...], ...]:
    """Assemble the likelihoods for one update.

    A missing mass omits the weight factor. Geometry never enters here.

    Args:
        discrete: Likelihoods already in hand, one per discrete sensor.
        mass: A measured mass, or none when no scale reported.
        mass_means: One mean per outcome, required when `mass` is present.
        mass_deviations: One standard deviation per outcome, required alongside
            the means.

    Returns:
        The factors to multiply, discrete ones first.

    Raises:
        BeliefError: If a mass is present without its Gaussian parameters.
    """
    factors = [tuple(factor) for factor in discrete]
    if mass is None:
        return tuple(factors)
    if mass_means is None or mass_deviations is None:
        raise BeliefError("a mass reading needs a mean and a deviation per outcome")
    factors.append(gaussian_likelihood(mass, mass_means, mass_deviations))
    return tuple(factors)


def _spec(weights: Sequence[float]) -> str:
    """Render unnormalized weights in the form GTSAM's constructor parses."""
    return "/".join(str(float(value)) for value in weights)
