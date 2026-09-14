//! The wire encoding of a decision, and the version that gates every decode.
//!
//! A decision travels as CBOR, defined by
//! [RFC 8949](https://www.rfc-editor.org/rfc/rfc8949.html), with named fields,
//! fixed width floats, and class variants carried as their names. The schema a
//! consumer implements against is `contract/pick-decision.cddl`, and the
//! golden vectors under `contract/vectors/` are what prove this encoder still
//! produces it.
//!
//! The version is the first field, so refusing a message a consumer does not
//! understand costs one field read and never reaches the class field. Tolerant
//! reading through serde `default`, `alias`, or `other` is deliberately absent:
//! it converts a contract break into a silent default.

use serde::{Deserialize, Serialize};

use crate::CONTRACT_VERSION;
use crate::decision::PickDecision;
use crate::error::ContractError;
use crate::ids::{ChannelId, Confidence, ObjectId};
use crate::material::MaterialClass;
use crate::pose::{BeltPoint, PickPose};
use crate::window::{MonotonicNanos, PickWindow};

/// The lowest CBOR head byte for a definite length map.
const MAP_HEAD_MIN: u8 = 0xa0;
/// The highest CBOR head byte for a definite length map whose size fits in the
/// head byte itself, which every decision does.
const MAP_HEAD_MAX: u8 = 0xb7;
/// The first key of an encoded decision: a seven character text string.
const VERSION_KEY: &[u8] = b"\x67version";
/// The offset of the version value, immediately past the map head and the key.
const VERSION_VALUE_AT: usize = 9;

/// A point in the belt frame as it travels.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
#[expect(
    clippy::struct_field_names,
    reason = "the field names are the published wire names and cannot be shortened here"
)]
struct WirePoint {
    x_meters: f64,
    y_meters: f64,
    z_meters: f64,
}

/// A predicted pose as it travels.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct WirePose {
    point: WirePoint,
    yaw_radians: f64,
    reference_time: i64,
}

/// A reachability window as it travels.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct WireWindow {
    earliest: i64,
    latest: i64,
}

/// A decision as it travels.
///
/// This is the only definition of the wire shape. The domain types carry no
/// serde derives, so nothing can deserialize straight into a decision and skip
/// the validating constructor.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct WireDecision {
    version: u16,
    object: u64,
    class: MaterialClass,
    channel: u16,
    pose: WirePose,
    window: WireWindow,
    confidence: f32,
}

impl From<&PickDecision> for WireDecision {
    fn from(decision: &PickDecision) -> Self {
        let point = decision.pose().point();
        Self {
            version: decision.version(),
            object: decision.object().get(),
            class: decision.class(),
            channel: decision.channel().get(),
            pose: WirePose {
                point: WirePoint {
                    x_meters: point.x_meters(),
                    y_meters: point.y_meters(),
                    z_meters: point.z_meters(),
                },
                yaw_radians: decision.pose().yaw_radians(),
                reference_time: decision.pose().reference_time().get(),
            },
            window: WireWindow {
                earliest: decision.window().earliest().get(),
                latest: decision.window().latest().get(),
            },
            confidence: decision.confidence().get(),
        }
    }
}

/// Encodes a decision into a new buffer.
///
/// # Errors
///
/// Returns [`ContractError::EncodeBufferExhausted`] when the buffer cannot be
/// grown to hold the encoded decision.
///
/// # Examples
///
/// ```
/// use clave_decision::{
///     codec, BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId,
///     PickDecision, PickPose, PickWindow,
/// };
///
/// # fn main() -> Result<(), clave_decision::ContractError> {
/// let window = PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(250_000_000))?;
/// let decision = PickDecision::new(
///     ObjectId::new(1),
///     MaterialClass::Pet,
///     ChannelId::new(3),
///     PickPose::new(BeltPoint::new(0.4, -0.1, 0.0), 0.0, MonotonicNanos::new(100_000_000)),
///     window,
///     Confidence::new(0.9)?,
/// )?;
///
/// let encoded = codec::encode(&decision)?;
/// assert_eq!(codec::decode(&encoded)?.class(), MaterialClass::Pet);
/// # Ok(())
/// # }
/// ```
pub fn encode(decision: &PickDecision) -> Result<Vec<u8>, ContractError> {
    encode_into(Vec::new(), decision)
}

/// Encodes a decision into `buffer`, clearing whatever it held.
///
/// The publisher recycles buffers through this call so that a steady state
/// publication allocates nothing.
///
/// # Errors
///
/// Returns [`ContractError::EncodeBufferExhausted`] when the buffer cannot be
/// grown to hold the encoded decision.
pub fn encode_into(mut buffer: Vec<u8>, decision: &PickDecision) -> Result<Vec<u8>, ContractError> {
    buffer.clear();
    let wire = WireDecision::from(decision);
    cbor4ii::serde::to_vec(buffer, &wire).map_err(|_| ContractError::EncodeBufferExhausted)
}

/// Decodes a decision, refusing anything this build cannot vouch for.
///
/// The version is read first. A message carrying a version this build does not
/// speak is refused whole, so no field past the version is read and an
/// unrecognized class cannot appear in an accepted message. What survives the
/// version check goes back through [`PickDecision::new`], so hostile bytes
/// cannot produce a decision that breaks an invariant.
///
/// # Errors
///
/// Returns [`ContractError::UnknownVersion`] for a version this build does not
/// speak, [`ContractError::Malformed`] for bytes that are not a decision, and
/// the construction errors of [`PickDecision::new`], [`PickWindow::new`] and
/// [`Confidence::new`] for a well formed message that breaks an invariant.
pub fn decode(bytes: &[u8]) -> Result<PickDecision, ContractError> {
    let version = read_version(bytes)?;
    if version != u64::from(CONTRACT_VERSION) {
        return Err(ContractError::UnknownVersion {
            found: version,
            expected: CONTRACT_VERSION,
        });
    }

    let wire: WireDecision =
        cbor4ii::serde::from_slice(bytes).map_err(|_| ContractError::Malformed {
            reason: "the body is not a decision of this contract version",
        })?;

    PickDecision::new(
        ObjectId::new(wire.object),
        wire.class,
        ChannelId::new(wire.channel),
        PickPose::new(
            BeltPoint::new(
                wire.pose.point.x_meters,
                wire.pose.point.y_meters,
                wire.pose.point.z_meters,
            ),
            wire.pose.yaw_radians,
            MonotonicNanos::new(wire.pose.reference_time),
        ),
        PickWindow::new(
            MonotonicNanos::new(wire.window.earliest),
            MonotonicNanos::new(wire.window.latest),
        )?,
        Confidence::new(wire.confidence)?,
    )
}

/// Reads the contract version of an encoded decision without decoding the rest.
///
/// A consumer that speaks several contract versions reads this first and
/// dispatches on it. A consumer that speaks one version compares it and
/// discards the message when it does not match.
///
/// # Errors
///
/// Returns [`ContractError::Malformed`] when the bytes do not open a decision
/// whose first field is an unsigned version.
pub fn read_version(bytes: &[u8]) -> Result<u64, ContractError> {
    let map_head = *bytes.first().ok_or(ContractError::Malformed {
        reason: "the message is empty",
    })?;
    if !(MAP_HEAD_MIN..=MAP_HEAD_MAX).contains(&map_head) {
        return Err(ContractError::Malformed {
            reason: "the message does not open a definite length map",
        });
    }
    if bytes.get(1..VERSION_VALUE_AT) != Some(VERSION_KEY) {
        return Err(ContractError::Malformed {
            reason: "the first field of the message is not the version",
        });
    }

    let value_head = *bytes
        .get(VERSION_VALUE_AT)
        .ok_or(ContractError::Malformed {
            reason: "the version field has no value",
        })?;
    let payload_at = VERSION_VALUE_AT.saturating_add(1);
    match value_head {
        0x00..=0x17 => Ok(u64::from(value_head)),
        0x18 => read_big_endian::<1>(bytes, payload_at),
        0x19 => read_big_endian::<2>(bytes, payload_at),
        0x1a => read_big_endian::<4>(bytes, payload_at),
        0x1b => read_big_endian::<8>(bytes, payload_at),
        _ => Err(ContractError::Malformed {
            reason: "the version field is not an unsigned integer",
        }),
    }
}

/// Reads `WIDTH` big endian bytes at `at` as an unsigned integer.
fn read_big_endian<const WIDTH: usize>(bytes: &[u8], at: usize) -> Result<u64, ContractError> {
    const fn truncated() -> ContractError {
        ContractError::Malformed {
            reason: "the version field is truncated",
        }
    }

    let end = at.checked_add(WIDTH).ok_or_else(truncated)?;
    let payload = bytes.get(at..end).ok_or_else(truncated)?;
    let mut buffer = [0_u8; 8];
    let start = buffer.len().checked_sub(WIDTH).ok_or_else(truncated)?;
    buffer
        .get_mut(start..)
        .ok_or_else(truncated)?
        .copy_from_slice(payload);
    Ok(u64::from_be_bytes(buffer))
}
