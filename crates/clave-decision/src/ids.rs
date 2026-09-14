//! The identities and the confidence a decision carries.

use crate::error::ContractError;

/// A physical sorting channel on the line.
///
/// The line operator supplies the mapping from a material class to a channel,
/// including which channel is the reject channel, so this type carries no
/// meaning of its own beyond being the channel the resolver named.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ChannelId(u16);

impl ChannelId {
    /// Returns the channel with this number.
    #[must_use]
    pub const fn new(value: u16) -> Self {
        Self(value)
    }

    /// Returns the channel number.
    #[must_use]
    pub const fn get(self) -> u16 {
        self.0
    }
}

/// The identity the tracker assigned to one object on the belt.
///
/// A decision carries the identity it was given. CLAVE never mints one here
/// and never rewrites one, so every decision published for one tracked object
/// carries the same identity.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ObjectId(u64);

impl ObjectId {
    /// Returns the identity with this number.
    #[must_use]
    pub const fn new(value: u64) -> Self {
        Self(value)
    }

    /// Returns the identity number.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }
}

/// The classifier confidence behind the material class of a decision.
///
/// A confidence is a finite number in the inclusive range 0.0 to 1.0. The type
/// holds no ordering against a threshold of its own: the routing policy owns
/// the threshold and the comparison.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]
pub struct Confidence(f32);

impl Confidence {
    /// Returns the confidence for this value.
    ///
    /// # Errors
    ///
    /// Returns [`ContractError::ConfidenceOutOfRange`] when the value is not
    /// finite or falls outside the inclusive range 0.0 to 1.0.
    pub fn new(value: f32) -> Result<Self, ContractError> {
        if value.is_finite() && (0.0..=1.0).contains(&value) {
            Ok(Self(value))
        } else {
            Err(ContractError::ConfidenceOutOfRange { value })
        }
    }

    /// Returns the confidence value.
    #[must_use]
    pub const fn get(self) -> f32 {
        self.0
    }
}
