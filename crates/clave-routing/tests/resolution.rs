//! Resolving a material class and a confidence to a channel.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use clave_decision::{
    BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
    PickPose, PickWindow,
};
use clave_routing::{ChannelMap, RejectReason, Resolver, Routed, RoutingError};

const REJECT: ChannelId = ChannelId::new(0);

fn operator_map() -> ChannelMap {
    ChannelMap::new(
        [
            (MaterialClass::Pet, ChannelId::new(1)),
            (MaterialClass::Hdpe, ChannelId::new(2)),
            (MaterialClass::Aluminum, ChannelId::new(3)),
            (MaterialClass::Cardboard, ChannelId::new(4)),
            (MaterialClass::MixedPaper, ChannelId::new(4)),
            (MaterialClass::BeverageCarton, ChannelId::new(4)),
            (MaterialClass::Residue, REJECT),
        ],
        REJECT,
        Confidence::new(0.6).unwrap(),
    )
    .unwrap()
}

/// The channel comes from the operator-supplied mapping and
/// from nowhere else.
#[test]
fn a_mapped_class_above_the_threshold_resolves_to_its_operator_channel() {
    let resolver = Resolver::new(operator_map());

    let routed = resolver.resolve(MaterialClass::Pet, Confidence::new(0.95).unwrap());

    assert_eq!(routed, Routed::Sorted(ChannelId::new(1)));
    assert_eq!(routed.channel(), ChannelId::new(1));
    assert_eq!(routed.reject_reason(), None);
}

/// Several classes may share one channel, which is how a
/// deployment with fewer channels than classes is expressed.
#[test]
fn several_classes_may_share_one_channel() {
    let resolver = Resolver::new(operator_map());
    let fiber = ChannelId::new(4);

    for class in [
        MaterialClass::Cardboard,
        MaterialClass::MixedPaper,
        MaterialClass::BeverageCarton,
    ] {
        assert_eq!(
            resolver.resolve(class, Confidence::new(0.9).unwrap()),
            Routed::Sorted(fiber)
        );
    }
}

/// An object the classifier was not sure enough about goes to
/// the reject channel even though its class is mapped.
#[test]
fn a_confidence_below_the_threshold_sends_a_mapped_class_to_the_reject_channel() {
    let resolver = Resolver::new(operator_map());

    let routed = resolver.resolve(MaterialClass::Pet, Confidence::new(0.59).unwrap());

    assert_eq!(
        routed,
        Routed::Rejected {
            channel: REJECT,
            reason: RejectReason::BelowThreshold
        }
    );
    assert_eq!(routed.channel(), REJECT);
}

/// The threshold is a floor rather than a strict bound, so a
/// confidence exactly at it is sorted.
#[test]
fn a_confidence_exactly_at_the_threshold_is_sorted() {
    let resolver = Resolver::new(operator_map());

    assert_eq!(
        resolver.resolve(MaterialClass::Pet, Confidence::new(0.6).unwrap()),
        Routed::Sorted(ChannelId::new(1))
    );
}

/// A rejected object is published as an ordinary decision,
/// carrying its predicted class rather than a placeholder.
#[test]
fn a_rejected_object_becomes_an_ordinary_decision_carrying_its_class() {
    let resolver = Resolver::new(operator_map());
    let confidence = Confidence::new(0.2).unwrap();
    let routed = resolver.resolve(MaterialClass::Glass, confidence);

    let decision = PickDecision::new(
        ObjectId::new(5),
        MaterialClass::Glass,
        routed.channel(),
        PickPose::new(BeltPoint::new(0.2, 0.0, 0.0), 0.0, MonotonicNanos::new(5)),
        PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(10)).unwrap(),
        confidence,
    )
    .unwrap();

    assert_eq!(decision.channel(), REJECT);
    assert_eq!(decision.class(), MaterialClass::Glass);
}

/// A class the operator mapped to nothing goes to the reject
/// channel, and the reason separates it from the low-confidence route.
#[test]
fn an_unmapped_class_goes_to_the_reject_channel_with_its_own_reason() {
    let resolver = Resolver::new(operator_map());

    let routed = resolver.resolve(MaterialClass::Glass, Confidence::new(1.0).unwrap());

    assert_eq!(
        routed,
        Routed::Rejected {
            channel: REJECT,
            reason: RejectReason::UnmappedClass
        }
    );
    assert_eq!(routed.reject_reason(), Some(RejectReason::UnmappedClass));
}

/// Confidence is tested before the class is looked up, so a
/// low-confidence unmapped object reports the confidence as the reason.
#[test]
fn confidence_is_tested_before_the_class_is_looked_up() {
    let resolver = Resolver::new(operator_map());

    let routed = resolver.resolve(MaterialClass::Glass, Confidence::new(0.1).unwrap());

    assert_eq!(routed.reject_reason(), Some(RejectReason::BelowThreshold));
}

/// Resolution is total. Every class and every confidence
/// produces a channel, so no object is left without one and no decision is
/// published before a channel exists.
#[test]
fn every_class_and_every_confidence_resolves_to_a_channel() {
    let resolver = Resolver::new(operator_map());

    for class in MaterialClass::ALL {
        for step in 0_u8..=100 {
            let confidence = Confidence::new(f32::from(step) / 100.0).unwrap();
            let routed = resolver.resolve(class, confidence);
            assert!(matches!(
                routed,
                Routed::Sorted(_) | Routed::Rejected { .. }
            ));
        }
    }
}

/// A mapping that sends residue anywhere but the reject
/// channel is refused when it is loaded, not when the first object arrives.
#[test]
fn a_map_that_sends_residue_away_from_the_reject_channel_is_refused_at_load() {
    let error = ChannelMap::new(
        [(MaterialClass::Residue, ChannelId::new(7))],
        REJECT,
        Confidence::new(0.5).unwrap(),
    )
    .unwrap_err();

    assert!(matches!(error, RoutingError::ResidueNotRejected { .. }));
}

/// A mapping that names one class twice is ambiguous about
/// the operator's intent and is refused when it is loaded.
#[test]
fn a_map_that_names_one_class_twice_is_refused_at_load() {
    let error = ChannelMap::new(
        [
            (MaterialClass::Pet, ChannelId::new(1)),
            (MaterialClass::Pet, ChannelId::new(2)),
        ],
        REJECT,
        Confidence::new(0.5).unwrap(),
    )
    .unwrap_err();

    assert!(matches!(error, RoutingError::DuplicateClass { .. }));
}

/// An empty mapping is legal, and it sends everything to the
/// reject channel rather than failing.
#[test]
fn an_empty_map_sends_everything_to_the_reject_channel() {
    let map = ChannelMap::new([], REJECT, Confidence::new(0.5).unwrap()).unwrap();
    let resolver = Resolver::new(map);

    for class in MaterialClass::ALL {
        assert_eq!(
            resolver.resolve(class, Confidence::new(1.0).unwrap()),
            Routed::Rejected {
                channel: REJECT,
                reason: RejectReason::UnmappedClass
            }
        );
    }
}

/// The map reports the channel it holds for a class and the
/// reject channel it was built with, so an operator can read back what was
/// loaded.
#[test]
fn the_map_reports_what_the_operator_loaded() {
    let map = operator_map();

    assert_eq!(
        map.channel_for(MaterialClass::Hdpe),
        Some(ChannelId::new(2))
    );
    assert_eq!(map.channel_for(MaterialClass::Glass), None);
    assert_eq!(map.reject_channel(), REJECT);
    assert_eq!(map.threshold().get().to_bits(), 0.6_f32.to_bits());
}
