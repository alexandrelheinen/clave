//! The contract version travels with every decision and gates every decode.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use clave_decision::{
    BeltPoint, CONTRACT_VERSION, ChannelId, Confidence, ContractError, MaterialClass,
    MonotonicNanos, ObjectId, PickDecision, PickPose, PickWindow, codec,
};

fn sample() -> PickDecision {
    PickDecision::new(
        ObjectId::new(11),
        MaterialClass::Hdpe,
        ChannelId::new(2),
        PickPose::new(BeltPoint::new(0.4, 0.1, 0.0), 0.0, MonotonicNanos::new(50)),
        PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(100)).unwrap(),
        Confidence::new(0.99).unwrap(),
    )
    .unwrap()
}

/// The version is in the decision and it is the first field on
/// the wire, so rejecting a message costs one field read.
#[test]
fn the_version_is_the_first_field_of_every_encoded_decision() {
    let encoded = codec::encode(&sample()).unwrap();

    assert_eq!(sample().version(), CONTRACT_VERSION);
    assert_eq!(encoded.get(1..9), Some(b"\x67version".as_slice()));
    assert_eq!(
        codec::read_version(&encoded).unwrap(),
        u64::from(CONTRACT_VERSION)
    );
}

/// A decision carrying a version this build does not know is
/// rejected whole, and no field past the version is read.
#[test]
fn a_message_with_an_unknown_version_is_rejected_before_any_other_field() {
    let mut message = Vec::new();
    message.push(0xa7);
    message.extend_from_slice(b"\x67version");
    message.extend_from_slice(&[0x18, 99]);
    message.extend_from_slice(b"this is not CBOR at all");

    let error = codec::decode(&message).unwrap_err();

    assert!(matches!(
        error,
        ContractError::UnknownVersion { found: 99, expected } if expected == CONTRACT_VERSION
    ));
}

/// A version too large for the contract's own version type is
/// an unknown version rather than a malformed message.
#[test]
fn a_version_wider_than_the_contract_version_type_is_an_unknown_version() {
    let mut message = Vec::new();
    message.push(0xa7);
    message.extend_from_slice(b"\x67version");
    message.push(0x1b);
    message.extend_from_slice(&u64::MAX.to_be_bytes());

    let error = codec::decode(&message).unwrap_err();

    assert!(matches!(error, ContractError::UnknownVersion { found, .. } if found == u64::MAX));
}

/// Every width of CBOR unsigned integer is read as a version,
/// so a producer that encodes the number differently is still understood.
#[test]
fn a_version_is_read_at_every_encoded_width() {
    let widths: [(&[u8], u64); 5] = [
        (&[0x0a], 10),
        (&[0x18, 0x2a], 42),
        (&[0x19, 0x01, 0x00], 256),
        (&[0x1a, 0x00, 0x01, 0x00, 0x00], 65_536),
        (&[0x1b, 0, 0, 0, 1, 0, 0, 0, 0], 4_294_967_296),
    ];

    for (encoded_version, expected) in widths {
        let mut message = Vec::new();
        message.push(0xa7);
        message.extend_from_slice(b"\x67version");
        message.extend_from_slice(encoded_version);

        assert_eq!(codec::read_version(&message).unwrap(), expected);
    }
}

/// Bytes that are not a decision are refused rather than
/// decoded into a default.
#[test]
fn bytes_that_are_not_a_decision_are_refused() {
    let malformed: [&[u8]; 5] = [
        &[],
        &[0x82, 0x01, 0x02],
        &[0xa7],
        &[0xa7, 0x67],
        &[0xa7, 0x64, b'n', b'o', b'p', b'e'],
    ];

    for bytes in malformed {
        assert!(matches!(
            codec::decode(bytes),
            Err(ContractError::Malformed { .. })
        ));
    }
}

/// A version field that is not an unsigned integer is a
/// malformed message rather than an unknown version.
#[test]
fn a_version_field_that_is_not_an_unsigned_integer_is_malformed() {
    let mut message = Vec::new();
    message.push(0xa7);
    message.extend_from_slice(b"\x67version");
    message.push(0x20);

    assert!(matches!(
        codec::decode(&message),
        Err(ContractError::Malformed { .. })
    ));
}

/// A decoded message runs back through the validating
/// constructor, so bytes carrying a known version but a broken invariant are
/// refused rather than accepted as a decision.
#[test]
fn a_well_versioned_message_carrying_a_broken_invariant_is_refused() {
    let decision = PickDecision::new(
        ObjectId::new(11),
        MaterialClass::Hdpe,
        ChannelId::new(2),
        PickPose::new(BeltPoint::new(0.4, 0.1, 0.0), 0.0, MonotonicNanos::new(15)),
        PickWindow::new(MonotonicNanos::new(10), MonotonicNanos::new(20)).unwrap(),
        Confidence::new(0.99).unwrap(),
    )
    .unwrap();
    let mut encoded = codec::encode(&decision).unwrap();
    let key_at = encoded
        .windows(7)
        .position(|window| window == b"\x66latest")
        .unwrap();
    let value_at = key_at.saturating_add(7);
    // The latest time was 20, encoded in one byte. Rewrite it to 0, which puts
    // the window's end before its start.
    assert_eq!(encoded.get(value_at).copied(), Some(0x14));
    if let Some(slot) = encoded.get_mut(value_at) {
        *slot = 0x00;
    }

    let error = codec::decode(&encoded).unwrap_err();

    assert!(matches!(error, ContractError::WindowNotOrdered { .. }));
}

/// The contract version this build speaks is the one the crate
/// publishes, so raising it in one place raises it everywhere.
#[test]
fn the_build_speaks_exactly_one_contract_version() {
    let encoded = codec::encode(&sample()).unwrap();

    assert_eq!(CONTRACT_VERSION, 1);
    assert_eq!(codec::decode(&encoded).unwrap().version(), CONTRACT_VERSION);
}
