//! The one place that turns a class and a confidence into a channel.

use clave_decision::{ChannelId, Confidence, MaterialClass};

use crate::channel_map::ChannelMap;

/// Why an object went to the reject channel.
///
/// The reason is what separates a line that is unsure from a line that is
/// configured for a different material stream, and an operator reading a
/// rising count of one rather than the other has two different problems.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum RejectReason {
    /// The classifier confidence fell below the operator's threshold.
    BelowThreshold,
    /// The operator's mapping names no channel for this class.
    UnmappedClass,
}

/// Where one object goes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Routed {
    /// The object goes to a sorted channel.
    Sorted(ChannelId),
    /// The object goes to the reject channel, for the stated reason.
    Rejected {
        /// The reject channel.
        channel: ChannelId,
        /// Why the object was not sorted.
        reason: RejectReason,
    },
}

impl Routed {
    /// Returns the channel this object goes to, sorted or rejected.
    ///
    /// Every route ends at a channel, which is what lets a caller publish a
    /// decision without branching on the reason first.
    #[must_use]
    pub const fn channel(self) -> ChannelId {
        match self {
            Self::Sorted(channel) | Self::Rejected { channel, .. } => channel,
        }
    }

    /// Returns why the object was rejected, or `None` when it was sorted.
    #[must_use]
    pub const fn reject_reason(self) -> Option<RejectReason> {
        match self {
            Self::Sorted(_) => None,
            Self::Rejected { reason, .. } => Some(reason),
        }
    }
}

/// Holds the routing policy and nothing else.
///
/// The contract crate carries no policy and the publisher carries no policy,
/// so this is the only place a class becomes a channel.
#[derive(Debug, Clone)]
pub struct Resolver {
    map: ChannelMap,
}

impl Resolver {
    /// Returns a resolver over a loaded mapping.
    #[must_use]
    pub const fn new(map: ChannelMap) -> Self {
        Self { map }
    }

    /// Returns the mapping this resolver was built with.
    #[must_use]
    pub const fn map(&self) -> &ChannelMap {
        &self.map
    }

    /// Resolves one object to a channel.
    ///
    /// The confidence is tested against the threshold before the class is
    /// looked up, so a low-confidence object never reaches a sorted channel
    /// even when its class is mapped. The call is total: every class and every
    /// confidence produces a channel, which is what makes "no decision before
    /// a channel exists" a property of the type rather than of a code path.
    #[must_use]
    pub fn resolve(&self, class: MaterialClass, confidence: Confidence) -> Routed {
        if confidence < self.map.threshold() {
            return Routed::Rejected {
                channel: self.map.reject_channel(),
                reason: RejectReason::BelowThreshold,
            };
        }
        match self.map.channel_for(class) {
            Some(channel) => Routed::Sorted(channel),
            None => Routed::Rejected {
                channel: self.map.reject_channel(),
                reason: RejectReason::UnmappedClass,
            },
        }
    }
}
