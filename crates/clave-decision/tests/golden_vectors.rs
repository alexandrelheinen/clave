//! The published schema and the golden vectors a consumer implements against.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use clave_decision::{ChannelId, ContractError, MaterialClass, MonotonicNanos, ObjectId, codec};

const SCHEMA: &str = include_str!("../contract/pick-decision.cddl");
const VECTOR_INDEX: &str = include_str!("../contract/vectors/v1/README.md");
const NOMINAL: &str = include_str!("../contract/vectors/v1/nominal.hex");
const REJECTED: &str = include_str!("../contract/vectors/v1/rejected.hex");
const UNKNOWN_VERSION: &str = include_str!("../contract/vectors/v1/unknown-version.hex");

fn bytes_of(vector: &str) -> Vec<u8> {
    let digits: String = vector
        .lines()
        .filter(|line| !line.trim_start().starts_with('#'))
        .flat_map(str::chars)
        .filter(char::is_ascii_hexdigit)
        .collect();
    digits
        .as_bytes()
        .chunks(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).unwrap();
            u8::from_str_radix(text, 16).unwrap()
        })
        .collect()
}

/// The published worked example decodes to the values the index
/// documents, and re-encodes to the same bytes.
#[test]
fn the_nominal_vector_decodes_to_its_documented_values() {
    let bytes = bytes_of(NOMINAL);
    let decision = codec::decode(&bytes).unwrap();

    assert_eq!(decision.version(), 1);
    assert_eq!(decision.object(), ObjectId::new(4_815_162_342));
    assert_eq!(decision.class(), MaterialClass::Pet);
    assert_eq!(decision.channel(), ChannelId::new(3));
    assert_eq!(
        decision.pose().point().x_meters().to_bits(),
        0.412_f64.to_bits()
    );
    assert_eq!(
        decision.pose().point().y_meters().to_bits(),
        (-0.085_f64).to_bits()
    );
    assert_eq!(
        decision.pose().point().z_meters().to_bits(),
        0.031_f64.to_bits()
    );
    assert_eq!(decision.pose().yaw_radians().to_bits(), 1.047_f64.to_bits());
    assert_eq!(
        decision.pose().reference_time(),
        MonotonicNanos::new(9_100_000_000)
    );
    assert_eq!(
        decision.window().earliest(),
        MonotonicNanos::new(9_000_000_000)
    );
    assert_eq!(
        decision.window().latest(),
        MonotonicNanos::new(9_250_000_000)
    );
    assert_eq!(decision.confidence().get().to_bits(), 0.94_f32.to_bits());
    assert_eq!(codec::encode(&decision).unwrap(), bytes);
}

/// The reject vector shows a consumer what an object sent to the
/// reject channel looks like, which is an ordinary decision.
#[test]
fn the_reject_vector_is_an_ordinary_decision() {
    let bytes = bytes_of(REJECTED);
    let decision = codec::decode(&bytes).unwrap();

    assert_eq!(decision.class(), MaterialClass::Residue);
    assert_eq!(decision.channel(), ChannelId::new(0));
    assert_eq!(codec::encode(&decision).unwrap(), bytes);
}

/// The vector directory carries a message a
/// consumer can point its own rejection path at.
#[test]
fn the_unknown_version_vector_is_rejected_whole() {
    let bytes = bytes_of(UNKNOWN_VERSION);

    assert!(matches!(
        codec::decode(&bytes),
        Err(ContractError::UnknownVersion { found: 2, .. })
    ));
}

/// The schema states the unit, the coordinate frame, and the
/// time reference of every field a consumer has to interpret.
#[test]
fn the_schema_states_the_unit_the_frame_and_the_time_reference() {
    for statement in [
        "meters",
        "radians",
        "monotonic",
        "belt frame",
        "nanoseconds",
        "0.0 to 1.0",
    ] {
        assert!(
            SCHEMA.contains(statement),
            "the schema does not state {statement}"
        );
    }
}

/// The schema names every field of a decision and every class in
/// the fixed set, so a consumer never has to read this crate's source.
#[test]
fn the_schema_names_every_field_and_every_class() {
    for field in [
        "version",
        "object",
        "class",
        "channel",
        "pose",
        "window",
        "confidence",
        "reference_time",
        "earliest",
        "latest",
        "x_meters",
        "y_meters",
        "z_meters",
        "yaw_radians",
    ] {
        assert!(SCHEMA.contains(field), "the schema does not name {field}");
    }
    for class in MaterialClass::ALL {
        assert!(
            SCHEMA.contains(class.taxonomy_id()),
            "the schema does not name {}",
            class.taxonomy_id()
        );
    }
}

/// The schema tells a consumer what to do with a version it does
/// not recognize, so nobody writes a tolerant reader out of habit.
#[test]
fn the_schema_states_what_an_unrecognized_version_means_for_a_consumer() {
    assert!(SCHEMA.contains("reject"));
    assert!(SCHEMA.contains("version"));
    assert!(VECTOR_INDEX.contains("unknown-version.hex"));
}
