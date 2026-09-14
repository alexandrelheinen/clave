//! What the safety layer decided, and which check decided it.

use clave_decision::PickDecision;
use clave_routing::Routed;

/// A geometric check a proposed pick point has to survive.
///
/// The name travels with an override so an operator reading a rising override
/// count knows whether the model is reaching too far, aiming into the belt, or
/// picking off it. Those are three different faults.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Check {
    /// The point lies further from the arm base than the effector reaches.
    Reach,
    /// The point lies below the belt surface.
    BeltSurface,
    /// The point lies outside the belt's extent.
    BeltExtent,
}

impl Check {
    /// Returns the stable name of this check, as a report and a counter use it.
    #[must_use]
    pub const fn name(self) -> &'static str {
        match self {
            Self::Reach => "reach",
            Self::BeltSurface => "belt_surface",
            Self::BeltExtent => "belt_extent",
        }
    }
}

/// What the safety layer decided about one proposal.
///
/// Every decoded proposal reaches exactly one of these. There is no third
/// state and no way to leave one undecided, which is what makes "inference
/// proposes, a deterministic layer disposes" a property of the type rather
/// than of a code path.
///
/// The enum is deliberately not `non_exhaustive`: a third state would change
/// what the layer means, so it should break every consumer rather than be
/// absorbed by a wildcard arm.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Verdict {
    /// The geometry passed. The decision is ready to publish.
    Accepted {
        /// The decision, already carrying the channel the policy resolved.
        decision: PickDecision,
        /// How the policy routed it, including why it was rejected if it was.
        routed: Routed,
    },
    /// The geometry failed. Nothing is published.
    Overridden {
        /// The check that failed.
        check: Check,
    },
}

impl Verdict {
    /// Returns the check that failed, or `None` when the proposal was accepted.
    #[must_use]
    pub const fn overridden_check(self) -> Option<Check> {
        match self {
            Self::Accepted { .. } => None,
            Self::Overridden { check } => Some(check),
        }
    }

    /// Returns the decision to publish, or `None` when nothing is published.
    #[must_use]
    pub const fn decision(self) -> Option<PickDecision> {
        match self {
            Self::Accepted { decision, .. } => Some(decision),
            Self::Overridden { .. } => None,
        }
    }
}
