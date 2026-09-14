//! The operator-supplied mapping from a material class to a channel.

use std::collections::BTreeMap;

use clave_decision::{ChannelId, Confidence, MaterialClass};

use crate::error::RoutingError;

/// The mapping a line operator supplies, validated once when it is loaded.
///
/// The class count is a property of the material stream and the channel count
/// is a property of the installed effector, so the two are bound here by
/// configuration rather than in the taxonomy. A channel may serve several
/// classes, which is how a deployment with fewer channels than classes is
/// expressed, and a class the operator names no channel for is routed to the
/// reject channel.
#[derive(Debug, Clone)]
pub struct ChannelMap {
    channels: BTreeMap<MaterialClass, ChannelId>,
    reject: ChannelId,
    threshold: Confidence,
}

impl ChannelMap {
    /// Loads and validates an operator mapping.
    ///
    /// `threshold` is the confidence floor below which an object goes to the
    /// reject channel whatever its class. It is a measured quantity that
    /// depends on a trained model, so it is configuration here rather than a
    /// constant.
    ///
    /// # Errors
    ///
    /// Returns [`RoutingError::DuplicateClass`] when one class is mapped more
    /// than once, and [`RoutingError::ResidueNotRejected`] when residue is
    /// mapped anywhere other than the reject channel.
    pub fn new(
        entries: impl IntoIterator<Item = (MaterialClass, ChannelId)>,
        reject: ChannelId,
        threshold: Confidence,
    ) -> Result<Self, RoutingError> {
        let mut channels = BTreeMap::new();
        for (class, channel) in entries {
            if channels.insert(class, channel).is_some() {
                return Err(RoutingError::DuplicateClass { class });
            }
            if class == MaterialClass::Residue && channel != reject {
                return Err(RoutingError::ResidueNotRejected {
                    channel: channel.get(),
                    reject: reject.get(),
                });
            }
        }
        Ok(Self {
            channels,
            reject,
            threshold,
        })
    }

    /// Returns the channel the operator mapped this class to, if any.
    #[must_use]
    pub fn channel_for(&self, class: MaterialClass) -> Option<ChannelId> {
        self.channels.get(&class).copied()
    }

    /// Returns the channel that receives everything the line cannot route.
    #[must_use]
    pub const fn reject_channel(&self) -> ChannelId {
        self.reject
    }

    /// Returns the confidence floor for a sorted channel.
    #[must_use]
    pub const fn threshold(&self) -> Confidence {
        self.threshold
    }
}
