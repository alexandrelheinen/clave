//! The decision itself, and the constructor that refuses an invalid one.

use crate::CONTRACT_VERSION;
use crate::error::ContractError;
use crate::ids::{ChannelId, Confidence, ObjectId};
use crate::material::MaterialClass;
use crate::pose::PickPose;
use crate::window::{MonotonicNanos, PickWindow};

/// One decision about one object: what it is, where it goes, where it will be,
/// when it is reachable, how sure the classifier was, and which object it is.
///
/// A constructed decision stays valid. No field is publicly mutable and every
/// accessor returns a copy, so the invariants checked in [`PickDecision::new`]
/// hold for the life of the value.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PickDecision {
    version: u16,
    object: ObjectId,
    class: MaterialClass,
    channel: ChannelId,
    pose: PickPose,
    window: PickWindow,
    confidence: Confidence,
}

impl PickDecision {
    /// Returns the decision, or refuses the combination.
    ///
    /// The constructor validates rather than trusting its caller. The window
    /// and the confidence validated themselves when they were built, so what
    /// is left to check here is the one invariant that binds two fields
    /// together: the pose has to be predicted for an instant inside the
    /// window, which is what makes "the pose the object will hold when the
    /// effector arrives" a checked property rather than a comment.
    ///
    /// The object identity is carried, never minted and never rewritten.
    ///
    /// # Errors
    ///
    /// Returns [`ContractError::PoseOutsideWindow`] when the pose reference
    /// time falls outside the pick window.
    pub fn new(
        object: ObjectId,
        class: MaterialClass,
        channel: ChannelId,
        pose: PickPose,
        window: PickWindow,
        confidence: Confidence,
    ) -> Result<Self, ContractError> {
        if !window.contains(pose.reference_time()) {
            return Err(ContractError::PoseOutsideWindow {
                reference_time: pose.reference_time().get(),
                earliest: window.earliest().get(),
                latest: window.latest().get(),
            });
        }
        Ok(Self {
            version: CONTRACT_VERSION,
            object,
            class,
            channel,
            pose,
            window,
            confidence,
        })
    }

    /// Returns the contract version this decision was built under.
    #[must_use]
    pub const fn version(self) -> u16 {
        self.version
    }

    /// Returns the identity the tracker assigned to the object.
    #[must_use]
    pub const fn object(self) -> ObjectId {
        self.object
    }

    /// Returns the material class the classifier assigned.
    #[must_use]
    pub const fn class(self) -> MaterialClass {
        self.class
    }

    /// Returns the channel the routing policy resolved.
    #[must_use]
    pub const fn channel(self) -> ChannelId {
        self.channel
    }

    /// Returns the pose the object is predicted to hold.
    #[must_use]
    pub const fn pose(self) -> PickPose {
        self.pose
    }

    /// Returns the window during which the object is reachable.
    #[must_use]
    pub const fn window(self) -> PickWindow {
        self.window
    }

    /// Returns the classifier confidence behind the material class.
    #[must_use]
    pub const fn confidence(self) -> Confidence {
        self.confidence
    }

    /// Returns whether this decision can still be acted on at `now`.
    #[must_use]
    pub fn is_reachable_at(self, now: MonotonicNanos) -> bool {
        !self.window.has_closed_by(now)
    }
}
