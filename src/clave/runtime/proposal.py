"""The Python half of the inference boundary.

The format is stated once, in `crates/clave-safety/contract/proposal.md`. This
module encodes it and refuses to send a proposal it already knows the runtime
will refuse, because a producer that ships garbage and reads the complaint back
has learned nothing the check here could not have told it.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.errors import ClaveError
from clave.taxonomy import BY_ID
from clave.tracker.fusion import OUTCOMES

PROPOSAL_VERSION = 1
"""The wire version a confidence-floor runtime implements.

A runtime that meets a version it does not implement refuses the whole message
rather than reading fields under the wrong meaning.
"""

PROPOSAL_VERSION_POSTERIOR = 2
"""The wire version that carries a posterior.

An expected-cost runtime implements this version and refuses version 1.
"""

POSTERIOR_SUM_TOLERANCE = 1e-6
"""Absolute tolerance on a posterior summing to one.

The proposal contract states this bound. It is a numerical limit of the wire,
not a routing parameter.
"""

CONFIDENCE_AGREEMENT_TOLERANCE = 1e-5
"""Absolute tolerance between confidence and the leading class weight.

Confidence is the f32 the decision carries, and the posterior weight is wider,
so the two copies of one probability disagree in the last bits. The proposal
contract states this bound.
"""

_CLASS_COUNT = len(OUTCOMES) - 1

STOP = b""
"""The stop signal: a datagram with no version and no fields."""


class ProposalError(ClaveError):
    """A proposal the runtime would refuse, caught before it is sent."""


@dataclass(frozen=True)
class Proposal:
    """One pick inference proposes, before any check has run.

    Attributes:
        object_id: Identity of the object, carried unchanged into the decision.
        material_class: Taxonomy identifier of the form `M-NN`.
        confidence: Classifier confidence, 0.0 to 1.0 inclusive.
        point: Proposed pick point in belt frame meters.
        yaw_radians: Proposed rotation about the belt normal.
        reference_time_nanos: Instant the pose is predicted for.
        window_start_nanos: Earliest instant the object is reachable.
        window_end_nanos: Latest instant the object is reachable.
        posterior: Outcome weights, in `OUTCOMES` order, when the proposal
            speaks version 2. Absent on a confidence-floor proposal.
    """

    object_id: int
    material_class: str
    confidence: float
    point: NDArray[np.float64]
    yaw_radians: float
    reference_time_nanos: int
    window_start_nanos: int
    window_end_nanos: int
    posterior: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        """Refuse a proposal the runtime would refuse, and coerce the point.

        Raises:
            ProposalError: Naming the field that is wrong.
        """
        object.__setattr__(self, "point", np.asarray(self.point, dtype=np.float64))
        if self.material_class not in BY_ID:
            raise ProposalError(
                f"material class {self.material_class!r} is not in the taxonomy"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ProposalError(
                f"confidence {self.confidence} is outside 0.0 to 1.0 inclusive"
            )
        if self.window_end_nanos < self.window_start_nanos:
            raise ProposalError(
                f"window {self.window_start_nanos} to {self.window_end_nanos} "
                "ends before it starts"
            )
        if not (
            self.window_start_nanos
            <= self.reference_time_nanos
            <= self.window_end_nanos
        ):
            raise ProposalError(
                f"reference time {self.reference_time_nanos} falls outside the window"
            )
        if self.posterior is not None:
            _check_posterior(self.material_class, self.confidence, self.posterior)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Proposal):
            return NotImplemented
        return (
            self.object_id == other.object_id
            and self.material_class == other.material_class
            and self.confidence == other.confidence
            and bool(np.allclose(self.point, other.point, rtol=0.0, atol=1e-12))
            and self.yaw_radians == other.yaw_radians
            and self.reference_time_nanos == other.reference_time_nanos
            and self.window_start_nanos == other.window_start_nanos
            and self.window_end_nanos == other.window_end_nanos
            and self.posterior == other.posterior
        )

    def encode(self) -> bytes:
        """Render as one datagram.

        Returns:
            The UTF-8 JSON the runtime reads.
        """
        x, y, z = (float(self.point[0]), float(self.point[1]), float(self.point[2]))
        version = (
            PROPOSAL_VERSION_POSTERIOR
            if self.posterior is not None
            else PROPOSAL_VERSION
        )
        payload: dict[str, Any] = {
            "version": version,
            "object_id": self.object_id,
            "material_class": self.material_class,
            "confidence": self.confidence,
            "x_meters": x,
            "y_meters": y,
            "z_meters": z,
            "yaw_radians": self.yaw_radians,
            "reference_time_nanos": self.reference_time_nanos,
            "window_start_nanos": self.window_start_nanos,
            "window_end_nanos": self.window_end_nanos,
        }
        if self.posterior is not None:
            payload["posterior"] = [float(weight) for weight in self.posterior]
        return json.dumps(payload, sort_keys=True).encode("utf-8")


def _check_posterior(
    material_class: str, confidence: float, posterior: tuple[float, ...]
) -> None:
    """Refuse a posterior the version 2 runtime would refuse.

    Args:
        material_class: The class the proposal reports.
        confidence: The confidence the proposal reports.
        posterior: Outcome weights, in `OUTCOMES` order.

    Raises:
        ProposalError: Naming the disagreement.
    """
    if len(posterior) != len(OUTCOMES):
        raise ProposalError(
            f"posterior has {len(posterior)} weights and the contract has "
            f"{len(OUTCOMES)}"
        )
    if any(not math.isfinite(weight) or weight < 0.0 for weight in posterior):
        raise ProposalError("posterior holds a weight that is negative or not finite")
    if abs(math.fsum(posterior) - 1.0) > POSTERIOR_SUM_TOLERANCE:
        raise ProposalError("posterior does not sum to 1 within the contract tolerance")
    leading, weight = _leading_class(posterior)
    if leading != material_class:
        raise ProposalError(
            f"material_class {material_class} disagrees with the leading "
            f"class {leading}"
        )
    if abs(weight - confidence) > CONFIDENCE_AGREEMENT_TOLERANCE:
        raise ProposalError("confidence disagrees with the leading class weight")


def _leading_class(posterior: tuple[float, ...]) -> tuple[str, float]:
    """Return the first maximum among the taxonomy classes.

    The reject outcome is the last weight and is not a class.

    Args:
        posterior: Outcome weights, in `OUTCOMES` order.

    Returns:
        The taxonomy identifier and its weight.
    """
    best = max(range(_CLASS_COUNT), key=lambda index: posterior[index])
    return OUTCOMES[best], posterior[best]


@dataclass(frozen=True)
class Outcome:
    """What the runtime did with one proposal.

    Attributes:
        verdict: One of `accepted`, `overridden` or `refused`.
        object_id: The object, when one was read.
        channel: The channel the policy resolved, when one was.
        reject_reason: Why it was routed to reject, when it was.
        check: The geometric check that failed, when one did.
        reason: What the decoder reported, when the proposal was refused.
    """

    verdict: str
    object_id: int | None = None
    channel: int | None = None
    reject_reason: str | None = None
    check: str | None = None
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        """Whether a decision was published for this proposal."""
        return self.verdict == "accepted"

    @property
    def overridden(self) -> bool:
        """Whether the safety layer refused the proposed point."""
        return self.verdict == "overridden"

    @classmethod
    def decode(cls, payload: bytes) -> Outcome:
        """Read one outcome datagram.

        Args:
            payload: The JSON the runtime sent.

        Returns:
            The outcome.

        Raises:
            ProposalError: If the payload is not an outcome.
        """
        try:
            read: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ProposalError(
                f"the runtime sent something unreadable: {error}"
            ) from (error)
        verdict = read.get("verdict")
        if verdict not in {"accepted", "overridden", "refused"}:
            raise ProposalError(f"the runtime reported an unknown verdict {verdict!r}")
        return cls(
            verdict=verdict,
            object_id=read.get("object_id"),
            channel=read.get("channel"),
            reject_reason=read.get("reject_reason"),
            check=read.get("check"),
            reason=read.get("reason"),
        )
