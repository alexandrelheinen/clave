//! Construction invariants of a pick decision.
#![expect(clippy::unwrap_used, reason = "test assertions")]
#![expect(
    clippy::as_conversions,
    reason = "the test reads a declared discriminant"
)]

use clave_decision::{
    BeltPoint, CONTRACT_VERSION, ChannelId, Confidence, ContractError, MaterialClass,
    MonotonicNanos, ObjectId, PickDecision, PickPose, PickWindow,
};

fn window(earliest: i64, latest: i64) -> PickWindow {
    PickWindow::new(MonotonicNanos::new(earliest), MonotonicNanos::new(latest)).unwrap()
}

fn pose(reference_time: i64) -> PickPose {
    PickPose::new(
        BeltPoint::new(0.25, -0.10, 0.04),
        0.5,
        MonotonicNanos::new(reference_time),
    )
}

/// A decision carries the class, the channel, the pose, the
/// window, the confidence, and the object identity.
#[test]
fn a_decision_carries_everything_a_consumer_needs_to_reach_for_one_object() {
    let decision = PickDecision::new(
        ObjectId::new(7),
        MaterialClass::Pet,
        ChannelId::new(3),
        pose(1_500),
        window(1_000, 2_000),
        Confidence::new(0.91).unwrap(),
    )
    .unwrap();

    assert_eq!(decision.object(), ObjectId::new(7));
    assert_eq!(decision.class(), MaterialClass::Pet);
    assert_eq!(decision.channel(), ChannelId::new(3));
    assert_eq!(decision.pose().reference_time(), MonotonicNanos::new(1_500));
    assert_eq!(decision.window(), window(1_000, 2_000));
    assert_eq!(decision.confidence().get().to_bits(), 0.91_f32.to_bits());
    assert_eq!(decision.version(), CONTRACT_VERSION);
}

/// The class of a decision comes from the fixed set named in
/// the contract, which is the taxonomy in `docs/waste-taxonomy.md`.
#[test]
fn the_class_set_matches_the_taxonomy_identifier_for_identifier() {
    let expected = [
        (MaterialClass::Pet, "M-01", 1_u16),
        (MaterialClass::Hdpe, "M-02", 2),
        (MaterialClass::Pp, "M-03", 3),
        (MaterialClass::OtherPlastic, "M-04", 4),
        (MaterialClass::Aluminum, "M-05", 5),
        (MaterialClass::Ferrous, "M-06", 6),
        (MaterialClass::Glass, "M-07", 7),
        (MaterialClass::Cardboard, "M-08", 8),
        (MaterialClass::MixedPaper, "M-09", 9),
        (MaterialClass::BeverageCarton, "M-10", 10),
        (MaterialClass::Residue, "M-11", 11),
    ];

    assert_eq!(MaterialClass::ALL.len(), expected.len());
    for (index, (class, taxonomy_id, discriminant)) in expected.into_iter().enumerate() {
        assert_eq!(MaterialClass::ALL.get(index).copied(), Some(class));
        assert_eq!(class.taxonomy_id(), taxonomy_id);
        assert_eq!(class as u16, discriminant);
        assert_eq!(u16::from(class), discriminant);
    }
}

/// The pose is the one the object is predicted to hold during
/// the window, which the constructor checks by refusing a reference time
/// outside it.
#[test]
fn a_pose_timed_outside_the_window_is_refused() {
    let error = PickDecision::new(
        ObjectId::new(1),
        MaterialClass::Glass,
        ChannelId::new(1),
        pose(2_001),
        window(1_000, 2_000),
        Confidence::new(0.8).unwrap(),
    )
    .unwrap_err();

    assert!(matches!(error, ContractError::PoseOutsideWindow { .. }));
}

/// A pose timed inside the window is accepted at both edges.
#[test]
fn a_pose_timed_on_either_edge_of_the_window_is_accepted() {
    for reference_time in [1_000, 2_000] {
        assert!(
            PickDecision::new(
                ObjectId::new(1),
                MaterialClass::Glass,
                ChannelId::new(1),
                pose(reference_time),
                window(1_000, 2_000),
                Confidence::new(0.8).unwrap(),
            )
            .is_ok()
        );
    }
}

/// The window is an earliest and a latest time, and one that
/// ends before it starts is not a window.
#[test]
fn a_window_that_ends_before_it_starts_is_refused() {
    let error =
        PickWindow::new(MonotonicNanos::new(2_000), MonotonicNanos::new(1_999)).unwrap_err();

    assert!(matches!(error, ContractError::WindowNotOrdered { .. }));
}

/// A window reports the two times it was built from.
#[test]
fn a_window_reports_its_earliest_and_its_latest_time() {
    let reachable = window(1_000, 2_000);

    assert_eq!(reachable.earliest(), MonotonicNanos::new(1_000));
    assert_eq!(reachable.latest(), MonotonicNanos::new(2_000));
    assert!(reachable.contains(MonotonicNanos::new(1_500)));
    assert!(!reachable.contains(MonotonicNanos::new(2_001)));
    assert!(reachable.has_closed_by(MonotonicNanos::new(2_001)));
    assert!(!reachable.has_closed_by(MonotonicNanos::new(2_000)));
}

/// The decision carries the object identity it was given, so
/// two decisions for one tracked object carry one identity.
#[test]
fn two_decisions_for_one_tracked_object_carry_the_same_identity() {
    let first = PickDecision::new(
        ObjectId::new(42),
        MaterialClass::Aluminum,
        ChannelId::new(2),
        pose(1_200),
        window(1_000, 2_000),
        Confidence::new(0.7).unwrap(),
    )
    .unwrap();
    let second = PickDecision::new(
        first.object(),
        MaterialClass::Aluminum,
        ChannelId::new(2),
        pose(1_800),
        window(1_400, 2_400),
        Confidence::new(0.75).unwrap(),
    )
    .unwrap();

    assert_eq!(first.object(), second.object());
    assert_eq!(second.object(), ObjectId::new(42));
}

/// A confidence outside the inclusive unit range, or one that
/// is not finite, is not a confidence.
#[test]
fn a_confidence_outside_the_unit_range_is_refused() {
    for value in [-0.001_f32, 1.001, f32::NAN, f32::INFINITY] {
        let error = Confidence::new(value).unwrap_err();
        assert!(matches!(error, ContractError::ConfidenceOutOfRange { .. }));
    }
    assert!(Confidence::new(0.0).is_ok());
    assert!(Confidence::new(1.0).is_ok());
}
