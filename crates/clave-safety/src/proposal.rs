//! The inference boundary.
//!
//! A proposal is what Python sends and Rust receives. It is the only place the
//! two languages meet, and nothing machine-learned crosses it.
//!
//! The wire format is JSON, one object per datagram, and it differs on purpose
//! from the CBOR a published decision uses. A proposal is internal, crossed at
//! most tens of times a second, and is the thing an engineer reads while
//! debugging; a decision is the contract another project compiles against.
//! Readability wins on one side and stability on the other.
//!
//! `contract/proposal.md`, beside this crate, states the fields, their units and the version rule,
//! so a consumer implements against that rather than against this source.

use clave_decision::{
    BeltPoint, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickPose, PickWindow,
};
use serde::Deserialize;

use crate::error::SafetyError;

/// The wire version this build implements.
///
/// A proposal carrying any other version is refused rather than interpreted.
/// The version moves whenever a field is added, removed, or changes meaning.
pub const PROPOSAL_VERSION: u64 = 1;

/// Enough of the payload to read the version, ignoring every other field.
///
/// Decoding happens in two passes so that an unrecognized version is refused
/// on the version alone. A single pass would fail on whichever field the new
/// version changed, reporting a type error where the truthful answer is that
/// the producer is speaking a language this build does not.
#[derive(Debug, Deserialize)]
struct Versioned {
    version: u64,
}

/// The payload as it appears on the wire.
#[derive(Debug, Deserialize)]
struct Wire {
    object_id: u64,
    material_class: String,
    confidence: f32,
    x_meters: f64,
    y_meters: f64,
    z_meters: f64,
    yaw_radians: f64,
    reference_time_nanos: i64,
    window_start_nanos: i64,
    window_end_nanos: i64,
}

/// One pick proposed by inference, before any check has run.
///
/// Every field a decision needs is carried, so the safety layer estimates
/// nothing the model already estimated and invents nothing the model did not.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Proposal {
    object: ObjectId,
    class: MaterialClass,
    confidence: Confidence,
    pose: PickPose,
    window: PickWindow,
}

impl Proposal {
    /// Decodes a proposal from one datagram.
    ///
    /// The version is read first, so an unrecognized one is refused before any
    /// other field is interpreted. Every coordinate is checked to be finite
    /// here, which is what lets the geometric checks be plain arithmetic.
    ///
    /// # Errors
    ///
    /// Returns [`SafetyError::UnsupportedVersion`] when the payload names a
    /// version this build does not implement, [`SafetyError::Malformed`] when
    /// a field is missing, of the wrong type, or not finite,
    /// [`SafetyError::UnknownClass`] when the material class is outside the
    /// taxonomy, and [`SafetyError::Contract`] when the window, the confidence
    /// or the pose reference time is one the published contract refuses.
    ///
    /// Every one of those is returned to the caller. A datagram nobody can
    /// read is not a reason to stop a conveyor.
    pub fn decode(bytes: &[u8]) -> Result<Self, SafetyError> {
        let versioned: Versioned =
            serde_json::from_slice(bytes).map_err(|error| SafetyError::Malformed {
                reason: error.to_string(),
            })?;
        if versioned.version != PROPOSAL_VERSION {
            return Err(SafetyError::UnsupportedVersion {
                found: versioned.version,
            });
        }

        let wire: Wire = serde_json::from_slice(bytes).map_err(|error| SafetyError::Malformed {
            reason: error.to_string(),
        })?;
        let class = from_taxonomy_id(&wire.material_class)?;
        for (name, value) in [
            ("x_meters", wire.x_meters),
            ("y_meters", wire.y_meters),
            ("z_meters", wire.z_meters),
            ("yaw_radians", wire.yaw_radians),
        ] {
            if !value.is_finite() {
                return Err(SafetyError::Malformed {
                    reason: format!("{name} is not a finite number"),
                });
            }
        }

        let window = PickWindow::new(
            MonotonicNanos::new(wire.window_start_nanos),
            MonotonicNanos::new(wire.window_end_nanos),
        )?;
        let reference = MonotonicNanos::new(wire.reference_time_nanos);
        if !window.contains(reference) {
            return Err(SafetyError::Malformed {
                reason: format!(
                    "reference_time_nanos {} falls outside the proposed window",
                    wire.reference_time_nanos
                ),
            });
        }

        Ok(Self {
            object: ObjectId::new(wire.object_id),
            class,
            confidence: Confidence::new(wire.confidence)?,
            pose: PickPose::new(
                BeltPoint::new(wire.x_meters, wire.y_meters, wire.z_meters),
                wire.yaw_radians,
                reference,
            ),
            window,
        })
    }

    /// Returns the identity the tracker assigned to the object.
    #[must_use]
    pub const fn object(self) -> ObjectId {
        self.object
    }

    /// Returns the material class inference assigned.
    #[must_use]
    pub const fn class(self) -> MaterialClass {
        self.class
    }

    /// Returns the confidence behind that class.
    #[must_use]
    pub const fn confidence(self) -> Confidence {
        self.confidence
    }

    /// Returns the pose inference proposes to pick at.
    #[must_use]
    pub const fn pose(self) -> PickPose {
        self.pose
    }

    /// Returns the window inference believes the object is reachable in.
    #[must_use]
    pub const fn window(self) -> PickWindow {
        self.window
    }
}

/// Returns the class with this taxonomy identifier.
///
/// The identifier is matched rather than the variant name, because the
/// identifier is what `docs/waste-taxonomy.md` marks append-only and what the
/// Python side of the boundary already carries.
fn from_taxonomy_id(id: &str) -> Result<MaterialClass, SafetyError> {
    MaterialClass::ALL
        .into_iter()
        .find(|class| class.taxonomy_id() == id)
        .ok_or_else(|| SafetyError::UnknownClass { id: id.to_owned() })
}
