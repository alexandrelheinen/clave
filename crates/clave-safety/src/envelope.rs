//! The workspace envelope, and the checks a proposal has to survive.
//!
//! Nothing here is a constant. The arm base, the reach radius, the belt
//! surface and the belt extent all arrive from configuration, because a
//! geometric limit written into Rust is a limit nobody can change when the
//! line changes.

use std::fs;
use std::path::Path;

use clave_decision::{BeltPoint, PickDecision};
use clave_routing::Resolver;
use serde_json::Value;

use crate::error::SafetyError;
use crate::proposal::Proposal;
use crate::verdict::{Check, Verdict};

/// The volume inside which a pick may be attempted.
///
/// The arm is a SCARA, so the volume is an annulus with a wedge missing,
/// extruded over the spline stroke, intersected with the belt extent. Each
/// piece is a real limit of the machine rather than a convenient
/// approximation: the annulus comes from the two link lengths, the missing
/// wedge from the stop on axis 1, and the extrusion from the stroke on axis 3.
///
/// A sphere would be the easy shape and the wrong one. It admits points
/// directly under the shoulder, where axis 2 cannot fold tightly enough to
/// put the tool, and points behind the arm that axis 1 cannot turn to face.
/// Admitting a point the arm cannot reach is how a proposer and a checker come
/// to disagree about the same geometry, which this project has already paid
/// for once.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Envelope {
    shoulder: BeltPoint,
    link_meters: (f64, f64),
    reach_meters: (f64, f64),
    shoulder_limit_radians: f64,
    elbow_limit_radians: f64,
    tool_above_belt_meters: (f64, f64),
    belt_surface_z_meters: f64,
    belt_x_meters: (f64, f64),
    belt_y_meters: (f64, f64),
}

impl Envelope {
    /// Reads an envelope from a JSON configuration file.
    ///
    /// JSON rather than the YAML the rest of CLAVE configures itself with:
    /// this crate gains no parser it does not need, and the Python side writes
    /// the envelope out of the one configuration file before starting the
    /// runtime. `configs/runtime/sitl.yml` remains the file an operator edits.
    ///
    /// # Errors
    ///
    /// Returns [`SafetyError::EnvelopeUnreadable`] when the file cannot be
    /// read, and whatever [`Envelope::from_json`] returns otherwise.
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self, SafetyError> {
        let path = path.as_ref();
        let bytes = fs::read(path).map_err(|error| SafetyError::EnvelopeUnreadable {
            path: path.display().to_string(),
            reason: error.to_string(),
        })?;
        Self::from_json(&bytes)
    }

    /// Reads an envelope from JSON bytes.
    ///
    /// # Errors
    ///
    /// Returns [`SafetyError::MissingEnvelopeKey`] naming the first key that
    /// is absent or of the wrong type, and [`SafetyError::InvalidEnvelope`]
    /// when the values describe no usable volume.
    pub fn from_json(bytes: &[u8]) -> Result<Self, SafetyError> {
        let value: Value =
            serde_json::from_slice(bytes).map_err(|error| SafetyError::Malformed {
                reason: error.to_string(),
            })?;
        let base = triple(&value, "shoulder_meters")?;
        let links = interval(&value, "link_meters")?;
        let envelope = Self {
            shoulder: BeltPoint::new(base[0], base[1], base[2]),
            link_meters: links,
            reach_meters: interval(&value, "reach_meters")?,
            shoulder_limit_radians: number(&value, "shoulder_limit_radians")?,
            elbow_limit_radians: number(&value, "elbow_limit_radians")?,
            tool_above_belt_meters: interval(&value, "tool_above_belt_meters")?,
            belt_surface_z_meters: number(&value, "belt_surface_z_meters")?,
            belt_x_meters: interval(&value, "belt_x_meters")?,
            belt_y_meters: interval(&value, "belt_y_meters")?,
        };
        envelope.validate()?;
        Ok(envelope)
    }

    /// Returns the point axis 1 turns about, in belt frame meters.
    #[must_use]
    pub const fn shoulder(&self) -> BeltPoint {
        self.shoulder
    }

    /// Returns the inner and outer radii of the annulus the tool sweeps.
    #[must_use]
    pub const fn reach_meters(&self) -> (f64, f64) {
        self.reach_meters
    }

    /// Returns the height of the belt surface, in meters.
    #[must_use]
    pub const fn belt_surface_z_meters(&self) -> f64 {
        self.belt_surface_z_meters
    }

    /// Reaches a verdict on one proposal.
    ///
    /// The geometric checks run first and in a fixed order, and the first one
    /// that fails names the verdict. A proposal that survives them is routed
    /// through the operator's policy, so a confidence below the floor becomes
    /// a reject route rather than a safety override: conflating the two would
    /// make the override count meaningless.
    ///
    /// # Errors
    ///
    /// Returns [`SafetyError::Contract`] if the published contract refuses the
    /// decision. Decoding already checked every invariant the contract checks,
    /// so this cannot fire today; it is returned rather than unwrapped because
    /// a panic in the layer that exists to override a model is the one failure
    /// this crate must not have.
    pub fn judge(&self, proposal: &Proposal, resolver: &Resolver) -> Result<Verdict, SafetyError> {
        if let Some(check) = self.failed_check(proposal.pose().point()) {
            return Ok(Verdict::Overridden { check });
        }
        let routed = resolver.resolve(proposal.class(), proposal.confidence());
        let decision = PickDecision::new(
            proposal.object(),
            proposal.class(),
            routed.channel(),
            proposal.pose(),
            proposal.window(),
            proposal.confidence(),
        )?;
        Ok(Verdict::Accepted { decision, routed })
    }

    /// Returns the first check this point fails, or `None` when it passes all.
    ///
    /// A coordinate large enough to overflow the squared distance yields
    /// infinity, which is greater than any radius, so the reach check refuses
    /// it. Overflow here cannot produce an accepted verdict.
    #[must_use]
    fn failed_check(&self, point: BeltPoint) -> Option<Check> {
        if !self.within_reach(point) {
            return Some(Check::Reach);
        }
        if point.z_meters() < self.belt_surface_z_meters {
            return Some(Check::BeltSurface);
        }
        let above = point.z_meters() - self.belt_surface_z_meters;
        if above < self.tool_above_belt_meters.0 || above > self.tool_above_belt_meters.1 {
            return Some(Check::Stroke);
        }
        if !on_belt(point.x_meters(), self.belt_x_meters)
            || !on_belt(point.y_meters(), self.belt_y_meters)
        {
            return Some(Check::BeltExtent);
        }
        None
    }

    /// Returns whether the point lies within the effector's reach.
    ///
    /// Every coordinate was checked finite at decode, and a coordinate large
    /// enough to overflow the squared distance yields infinity, which is
    /// greater than any radius. The arithmetic here cannot produce an
    /// acceptance it should not.
    fn within_reach(&self, point: BeltPoint) -> bool {
        let dx = point.x_meters() - self.shoulder.x_meters();
        let dy = point.y_meters() - self.shoulder.y_meters();
        let radius = dx.hypot(dy);
        let (inner, outer) = self.reach_meters;
        if !(radius >= inner && radius <= outer) {
            return false;
        }
        let (first, second) = self.link_meters;
        // Law of cosines on the planar two-link chain, the same arithmetic
        // `clave.world.arm.reaches` performs. The clamp absorbs the rounding
        // that puts a target exactly at the reach limit a hair outside the
        // domain of acos, which would otherwise yield NaN and compare false.
        let cosine = (radius.mul_add(radius, -first.mul_add(first, second * second)))
            / (2.0 * first * second);
        let magnitude = cosine.clamp(-1.0, 1.0).acos();
        let bearing = dy.atan2(dx);
        // One elbow configuration often clears the stop on axis 1 where the
        // mirror does not, so both are tried before the point is refused.
        [magnitude, -magnitude].into_iter().any(|elbow| {
            if elbow.abs() > self.elbow_limit_radians {
                return false;
            }
            let carried = (second * elbow.sin()).atan2(first + second * elbow.cos());
            let shoulder = bearing - carried;
            let wrapped = shoulder.sin().atan2(shoulder.cos());
            wrapped.abs() <= self.shoulder_limit_radians
        })
    }

    /// Refuses an envelope that describes no usable volume.
    fn validate(&self) -> Result<(), SafetyError> {
        for (key, value) in [
            ("shoulder_limit_radians", self.shoulder_limit_radians),
            ("elbow_limit_radians", self.elbow_limit_radians),
        ] {
            if !(value.is_finite() && value > 0.0) {
                return Err(SafetyError::InvalidEnvelope {
                    reason: format!("{key} is not a positive finite number"),
                });
            }
        }
        // The two link lengths are a pair rather than an ordered interval:
        // arm 1 is longer than arm 2, so an ordering test would refuse the
        // real machine. Both must simply be positive.
        let (first, second) = self.link_meters;
        if !(first.is_finite() && second.is_finite() && first > 0.0 && second > 0.0) {
            return Err(SafetyError::InvalidEnvelope {
                reason: "link_meters does not name two positive lengths".to_owned(),
            });
        }
        for (key, (low, high)) in [
            ("reach_meters", self.reach_meters),
            ("tool_above_belt_meters", self.tool_above_belt_meters),
            ("belt_x_meters", self.belt_x_meters),
            ("belt_y_meters", self.belt_y_meters),
        ] {
            if !(low.is_finite() && high.is_finite() && low <= high) {
                return Err(SafetyError::InvalidEnvelope {
                    reason: format!("{key} does not name an interval"),
                });
            }
        }
        Ok(())
    }
}

/// Returns whether a coordinate falls inside an inclusive interval.
fn on_belt(coordinate: f64, extent: (f64, f64)) -> bool {
    coordinate >= extent.0 && coordinate <= extent.1
}

/// Reads a number, naming the key when it is absent or not a number.
fn number(value: &Value, key: &str) -> Result<f64, SafetyError> {
    value
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| SafetyError::MissingEnvelopeKey {
            key: key.to_owned(),
        })
}

/// Reads a fixed-length array of numbers, naming the key when it is wrong.
fn numbers<const N: usize>(value: &Value, key: &str) -> Result<[f64; N], SafetyError> {
    let missing = || SafetyError::MissingEnvelopeKey {
        key: key.to_owned(),
    };
    let array = value
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(missing)?;
    let mut read = [0.0; N];
    if array.len() != N {
        return Err(missing());
    }
    for (slot, entry) in read.iter_mut().zip(array) {
        *slot = entry.as_f64().ok_or_else(missing)?;
    }
    Ok(read)
}

/// Reads a three-element point.
fn triple(value: &Value, key: &str) -> Result<[f64; 3], SafetyError> {
    numbers::<3>(value, key)
}

/// Reads a two-element interval as a low and a high bound.
fn interval(value: &Value, key: &str) -> Result<(f64, f64), SafetyError> {
    let read = numbers::<2>(value, key)?;
    Ok((read[0], read[1]))
}
