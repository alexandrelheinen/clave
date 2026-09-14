//! The round trip through the codec reproduces every field.
//!
//! Covers `AC-SCHEMA-02`.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use clave_decision::{
    BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
    PickPose, PickWindow, codec,
};
use proptest::prelude::*;

fn decision_with(class: MaterialClass, point: BeltPoint, yaw_radians: f64) -> PickDecision {
    PickDecision::new(
        ObjectId::new(u64::MAX),
        class,
        ChannelId::new(u16::MAX),
        PickPose::new(point, yaw_radians, MonotonicNanos::new(i64::MIN)),
        PickWindow::new(MonotonicNanos::new(i64::MIN), MonotonicNanos::new(i64::MAX)).unwrap(),
        Confidence::new(1.0).unwrap(),
    )
    .unwrap()
}

fn assert_round_trips(decision: &PickDecision) {
    let encoded = codec::encode(decision).unwrap();
    let decoded = codec::decode(&encoded).unwrap();

    assert_eq!(decoded.version(), decision.version());
    assert_eq!(decoded.object(), decision.object());
    assert_eq!(decoded.class(), decision.class());
    assert_eq!(decoded.channel(), decision.channel());
    assert_eq!(decoded.window(), decision.window());
    assert_eq!(
        decoded.confidence().get().to_bits(),
        decision.confidence().get().to_bits()
    );
    assert_eq!(
        decoded.pose().reference_time(),
        decision.pose().reference_time()
    );
    assert_eq!(
        decoded.pose().yaw_radians().to_bits(),
        decision.pose().yaw_radians().to_bits()
    );
    assert_eq!(
        decoded.pose().point().x_meters().to_bits(),
        decision.pose().point().x_meters().to_bits()
    );
    assert_eq!(
        decoded.pose().point().y_meters().to_bits(),
        decision.pose().point().y_meters().to_bits()
    );
    assert_eq!(
        decoded.pose().point().z_meters().to_bits(),
        decision.pose().point().z_meters().to_bits()
    );
    assert_eq!(codec::encode(&decoded).unwrap(), encoded);
}

/// AC-SCHEMA-02: every class in the fixed set survives the round trip.
#[test]
fn every_material_class_survives_the_round_trip() {
    for class in MaterialClass::ALL {
        assert_round_trips(&decision_with(class, BeltPoint::new(0.1, 0.2, 0.3), 1.0));
    }
}

/// AC-SCHEMA-02: the edge floats a belt coordinate can hold survive the round
/// trip with their bits intact, which is the property JSON could not keep.
#[test]
fn edge_floats_survive_the_round_trip_bit_for_bit() {
    let edges = [
        f64::NAN,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::MIN_POSITIVE,
        -0.0,
        0.0,
        f64::MAX,
        f64::MIN,
        5e-324,
        0.1,
    ];

    for value in edges {
        assert_round_trips(&decision_with(
            MaterialClass::Residue,
            BeltPoint::new(value, -value, value),
            value,
        ));
    }
}

/// AC-SCHEMA-02: the precision of a confidence survives the round trip, which
/// is where a text format loses a unit in the last place.
#[test]
fn confidence_precision_survives_the_round_trip() {
    for bits in 0_u32..64 {
        let value = f32::from_bits(0x3f00_0000_u32.wrapping_add(bits));
        if !(0.0..=1.0).contains(&value) {
            continue;
        }
        let decision = PickDecision::new(
            ObjectId::new(1),
            MaterialClass::Pp,
            ChannelId::new(1),
            PickPose::new(BeltPoint::new(0.0, 0.0, 0.0), 0.0, MonotonicNanos::new(0)),
            PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(1)).unwrap(),
            Confidence::new(value).unwrap(),
        )
        .unwrap();
        assert_round_trips(&decision);
    }
}

proptest! {
    /// AC-SCHEMA-02: the round trip holds over generated decisions, where the
    /// input space is larger than the examples anyone would think to write.
    #[test]
    fn an_arbitrary_decision_survives_the_round_trip(
        object in any::<u64>(),
        class_index in 0_usize..11,
        channel in any::<u16>(),
        x_meters in any::<f64>(),
        y_meters in any::<f64>(),
        z_meters in any::<f64>(),
        yaw_radians in any::<f64>(),
        earliest in any::<i64>(),
        span in 0_i64..1_000_000,
        offset in 0_i64..1_000_000,
        confidence in 0.0_f32..=1.0,
    ) {
        let latest = earliest.saturating_add(span);
        let reference_time = earliest.saturating_add(offset.min(span));
        let class = MaterialClass::ALL.get(class_index).copied().unwrap();
        let decision = PickDecision::new(
            ObjectId::new(object),
            class,
            ChannelId::new(channel),
            PickPose::new(
                BeltPoint::new(x_meters, y_meters, z_meters),
                yaw_radians,
                MonotonicNanos::new(reference_time),
            ),
            PickWindow::new(MonotonicNanos::new(earliest), MonotonicNanos::new(latest)).unwrap(),
            Confidence::new(confidence).unwrap(),
        )
        .unwrap();

        assert_round_trips(&decision);
    }
}
