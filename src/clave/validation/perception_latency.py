"""Perception forward-pass latency gate (issue #117 AC-DET-18).

A strong mIoU does not clear a candidate whose forward pass eats the decision
budget. Runtime detection refuses such a candidate.
"""

from __future__ import annotations

from clave.errors import ClaveError
from clave.validation.gates import GateThresholds


class PerceptionLatencyError(ClaveError):
    """A perception candidate is too slow for runtime detection."""


def clears_perception_latency(
    observed_seconds: float, ceiling_seconds: float
) -> bool:
    """Return whether a measured forward pass fits the perception budget.

    Args:
        observed_seconds: Median or p99 forward-pass latency in seconds.
        ceiling_seconds: `max_perception_latency_p99_seconds` from the gates.

    Returns:
        True when the observation is at or under the ceiling.
    """
    return observed_seconds <= ceiling_seconds


def require_perception_latency(
    candidate: str,
    observed_seconds: float,
    thresholds: GateThresholds,
) -> None:
    """Refuse a candidate whose forward pass exceeds the perception gate.

    Args:
        candidate: Registry name, named in the error.
        observed_seconds: Measured forward-pass latency in seconds.
        thresholds: Loaded gate thresholds.

    Raises:
        PerceptionLatencyError: When the observation is over budget.
    """
    ceiling = thresholds.max_perception_latency_p99_seconds
    if clears_perception_latency(observed_seconds, ceiling):
        return
    raise PerceptionLatencyError(
        f"{candidate} forward pass is {observed_seconds:.4f} s, which exceeds "
        f"max_perception_latency_p99_seconds={ceiling:.4f} s (AC-DET-18); "
        "it cannot be used for runtime detection even if mIoU passes"
    )
