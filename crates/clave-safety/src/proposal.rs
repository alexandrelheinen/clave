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
use clave_routing::OUTCOME_COUNT;
use serde::Deserialize;

use crate::error::SafetyError;

/// The wire version of a confidence-floor proposal.
///
/// A runtime that loaded no cost table implements this version. A payload
/// carrying any other version is refused rather than interpreted.
pub const PROPOSAL_VERSION: u64 = 1;

/// The wire version of a proposal that carries a posterior.
///
/// A runtime that loaded a cost table implements this version and refuses
/// version 1 before it reads any later field.
pub const PROPOSAL_VERSION_POSTERIOR: u64 = 2;

/// Absolute tolerance on a posterior summing to one.
///
/// A producer rounds each weight, so the sum is not exact. The proposal
/// contract states this bound. It is a numerical limit of the wire, not a
/// routing parameter.
const POSTERIOR_SUM_ABS: f64 = 1e-6;

/// Absolute tolerance between `confidence` and the leading class weight.
///
/// `confidence` is an f32 and the posterior weights are f64, so the two
/// copies of one probability disagree in the last bits. The proposal
/// contract states this bound.
const CONFIDENCE_ABS: f64 = 1e-5;

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

/// Version 2 of the payload, which adds the posterior.
#[derive(Debug, Deserialize)]
struct WirePosterior {
    object_id: u64,
    material_class: String,
    confidence: f32,
    posterior: Vec<f64>,
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
    posterior: Option<[f64; OUTCOME_COUNT]>,
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
        Self::decode_as(bytes, PROPOSAL_VERSION)
    }

    /// Decodes a proposal that must carry `expected`.
    ///
    /// The version is read first. A mismatch is refused before the remaining
    /// fields are interpreted, including when those fields would not parse.
    ///
    /// # Errors
    ///
    /// Returns [`SafetyError::UnsupportedVersion`] when the payload's version
    /// is not `expected`, and the errors of [`Proposal::decode`] for a payload
    /// whose version matches and whose body does not.
    pub fn decode_as(bytes: &[u8], expected: u64) -> Result<Self, SafetyError> {
        let versioned: Versioned =
            serde_json::from_slice(bytes).map_err(|error| SafetyError::Malformed {
                reason: error.to_string(),
            })?;
        if versioned.version != expected {
            return Err(SafetyError::UnsupportedVersion {
                found: versioned.version,
            });
        }
        match expected {
            PROPOSAL_VERSION => decode_floor(bytes),
            PROPOSAL_VERSION_POSTERIOR => decode_posterior(bytes),
            _ => Err(SafetyError::UnsupportedVersion { found: expected }),
        }
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

    /// Returns the posterior, in outcome order, when the payload carried one.
    #[must_use]
    pub const fn posterior(&self) -> Option<&[f64; OUTCOME_COUNT]> {
        self.posterior.as_ref()
    }
}

/// The fields both wire versions share.
struct Body<'a> {
    object_id: u64,
    material_class: &'a str,
    confidence: f32,
    x_meters: f64,
    y_meters: f64,
    z_meters: f64,
    yaw_radians: f64,
    reference_time_nanos: i64,
    window_start_nanos: i64,
    window_end_nanos: i64,
}

/// Decodes a version 1 body.
fn decode_floor(bytes: &[u8]) -> Result<Proposal, SafetyError> {
    let wire: Wire = serde_json::from_slice(bytes).map_err(|error| SafetyError::Malformed {
        reason: error.to_string(),
    })?;
    assemble(&body_from_floor(&wire), None)
}

/// Decodes a version 2 body, including the posterior agreement checks.
fn decode_posterior(bytes: &[u8]) -> Result<Proposal, SafetyError> {
    let wire: WirePosterior =
        serde_json::from_slice(bytes).map_err(|error| SafetyError::Malformed {
            reason: error.to_string(),
        })?;
    let posterior = posterior_array(&wire.posterior)?;
    check_posterior(&posterior, &wire.material_class, wire.confidence)?;
    assemble(&body_from_posterior(&wire), Some(posterior))
}

/// Copies the shared fields out of a version 1 payload.
fn body_from_floor(wire: &Wire) -> Body<'_> {
    Body {
        object_id: wire.object_id,
        material_class: &wire.material_class,
        confidence: wire.confidence,
        x_meters: wire.x_meters,
        y_meters: wire.y_meters,
        z_meters: wire.z_meters,
        yaw_radians: wire.yaw_radians,
        reference_time_nanos: wire.reference_time_nanos,
        window_start_nanos: wire.window_start_nanos,
        window_end_nanos: wire.window_end_nanos,
    }
}

/// Copies the shared fields out of a version 2 payload.
fn body_from_posterior(wire: &WirePosterior) -> Body<'_> {
    Body {
        object_id: wire.object_id,
        material_class: &wire.material_class,
        confidence: wire.confidence,
        x_meters: wire.x_meters,
        y_meters: wire.y_meters,
        z_meters: wire.z_meters,
        yaw_radians: wire.yaw_radians,
        reference_time_nanos: wire.reference_time_nanos,
        window_start_nanos: wire.window_start_nanos,
        window_end_nanos: wire.window_end_nanos,
    }
}

/// Copies a posterior into the fixed width, naming a short or long vector.
fn posterior_array(weights: &[f64]) -> Result<[f64; OUTCOME_COUNT], SafetyError> {
    if weights.len() != OUTCOME_COUNT {
        return Err(SafetyError::Malformed {
            reason: format!(
                "posterior has {} weights and the contract has {OUTCOME_COUNT}",
                weights.len()
            ),
        });
    }
    let mut posterior = [0.0; OUTCOME_COUNT];
    for (slot, weight) in posterior.iter_mut().zip(weights.iter().copied()) {
        if !weight.is_finite() || weight < 0.0 {
            return Err(SafetyError::Malformed {
                reason: "posterior holds a weight that is negative or not finite".to_owned(),
            });
        }
        *slot = weight;
    }
    let sum = posterior.iter().fold(0.0, |total, weight| total + weight);
    if (sum - 1.0).abs() > POSTERIOR_SUM_ABS {
        return Err(SafetyError::Malformed {
            reason: "posterior does not sum to 1 within the contract tolerance".to_owned(),
        });
    }
    Ok(posterior)
}

/// Refuses a class or a confidence that is not the leading taxonomy weight.
///
/// The leading class is the first maximum among the taxonomy classes. The
/// reject outcome is the last weight and is not a class, so a posterior that
/// peaks there still reports the best taxonomy class.
fn check_posterior(
    posterior: &[f64; OUTCOME_COUNT],
    material_class: &str,
    confidence: f32,
) -> Result<(), SafetyError> {
    let (best_class, best_weight) = leading_class(posterior);
    if best_class.taxonomy_id() != material_class {
        return Err(SafetyError::Malformed {
            reason: format!(
                "material_class {material_class} disagrees with the leading class {}",
                best_class.taxonomy_id()
            ),
        });
    }
    let stated = f64::from(confidence);
    if (stated - best_weight).abs() > CONFIDENCE_ABS {
        return Err(SafetyError::Malformed {
            reason: "confidence disagrees with the leading class weight".to_owned(),
        });
    }
    Ok(())
}

/// The first maximum among the taxonomy classes, and its weight.
fn leading_class(posterior: &[f64; OUTCOME_COUNT]) -> (MaterialClass, f64) {
    let mut best_class = MaterialClass::Pet;
    let mut best_weight = f64::NEG_INFINITY;
    for (class, weight) in MaterialClass::ALL
        .iter()
        .copied()
        .zip(posterior.iter().copied())
    {
        if weight > best_weight {
            best_class = class;
            best_weight = weight;
        }
    }
    (best_class, best_weight)
}

/// Builds a proposal once the version-specific fields have been checked.
fn assemble(
    body: &Body<'_>,
    posterior: Option<[f64; OUTCOME_COUNT]>,
) -> Result<Proposal, SafetyError> {
    let class = from_taxonomy_id(body.material_class)?;
    for (name, value) in [
        ("x_meters", body.x_meters),
        ("y_meters", body.y_meters),
        ("z_meters", body.z_meters),
        ("yaw_radians", body.yaw_radians),
    ] {
        if !value.is_finite() {
            return Err(SafetyError::Malformed {
                reason: format!("{name} is not a finite number"),
            });
        }
    }

    let window = PickWindow::new(
        MonotonicNanos::new(body.window_start_nanos),
        MonotonicNanos::new(body.window_end_nanos),
    )?;
    let reference = MonotonicNanos::new(body.reference_time_nanos);
    if !window.contains(reference) {
        return Err(SafetyError::Malformed {
            reason: format!(
                "reference_time_nanos {} falls outside the proposed window",
                body.reference_time_nanos
            ),
        });
    }

    Ok(Proposal {
        object: ObjectId::new(body.object_id),
        class,
        confidence: Confidence::new(body.confidence)?,
        pose: PickPose::new(
            BeltPoint::new(body.x_meters, body.y_meters, body.z_meters),
            body.yaw_radians,
            reference,
        ),
        window,
        posterior,
    })
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
