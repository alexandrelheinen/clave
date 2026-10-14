//! The inference boundary and the checks that can override a model.
#![expect(clippy::unwrap_used, reason = "test assertions")]
#![expect(
    clippy::panic,
    reason = "a test that reaches an impossible branch should fail loudly"
)]

use clave_decision::{ChannelId, Confidence, MaterialClass};
use clave_routing::{ChannelMap, OUTCOME_COUNT, RejectReason, Resolver, Routed};
use clave_safety::{Check, Envelope, PROPOSAL_VERSION_POSTERIOR, Proposal, SafetyError, Verdict};

const REJECT: ChannelId = ChannelId::new(0);

/// An envelope matching the shipped world: the arm sits on a pedestal beside
/// the belt at 0.70 m from the centerline, the belt surface is at 0.90 m, and
/// the belt is 3.00 m long by 1.00 m wide.
fn envelope() -> Envelope {
    Envelope::from_json(ENVELOPE_JSON.as_bytes()).unwrap()
}

const ENVELOPE_JSON: &str = r#"{
  "base": [0.0, -0.70, 0.90],
  "reach": [0.25, 1.25],
  "tool_above_base": [-0.05, 0.45],
  "belt_surface_z": 0.90,
  "belt_x": [-1.5, 1.5],
  "belt_y": [-0.5, 0.5]
}"#;

fn resolver() -> Resolver {
    Resolver::new(
        ChannelMap::new(
            [
                (MaterialClass::Pet, ChannelId::new(1)),
                (MaterialClass::Aluminum, ChannelId::new(2)),
            ],
            REJECT,
            Confidence::new(0.60).unwrap(),
        )
        .unwrap(),
    )
}

/// A proposal naming a point, at a confidence, on the wire.
fn wire(x: f64, y: f64, z: f64, confidence: f64) -> String {
    format!(
        r#"{{"version":1,"object_id":7,"material_class":"M-01","confidence":{confidence},
           "x_meters":{x},"y_meters":{y},"z_meters":{z},"yaw_radians":0.0,
           "reference_time_nanos":1000,"window_start_nanos":1000,
           "window_end_nanos":2000}}"#
    )
}

/// A point inside every check: on the belt surface, within reach, on the belt.
fn reachable() -> String {
    // On the belt centerline over the arm, so 0.70 m from the shoulder: clear
    // of the 0.25 m inner radius and inside the 1.25 m outer one. At 0.05 m
    // above the belt surface, inside the trusted vertical band of -0.05 m to
    // +0.45 m about the base.
    wire(0.0, 0.0, 0.95, 0.90)
}

#[test]
fn a_proposal_carries_every_field_across_the_boundary() {
    let proposal = Proposal::decode(reachable().as_bytes()).unwrap();
    assert_eq!(proposal.object().get(), 7);
    assert_eq!(proposal.class(), MaterialClass::Pet);
    assert!((f64::from(proposal.confidence().get()) - 0.90).abs() < 1e-6);
    assert!((proposal.pose().point().z() - 0.95).abs() < 1e-9);
    assert_eq!(proposal.window().earliest().get(), 1000);
}

#[test]
fn an_unrecognized_version_is_refused_by_version() {
    // The version is read before any other field, so a payload
    // whose later fields are nonsense still fails on the version.
    let payload = br#"{"version":99,"object_id":"not a number"}"#;
    let error = Proposal::decode(payload).unwrap_err();
    assert!(matches!(
        error,
        SafetyError::UnsupportedVersion { found: 99 }
    ));
}

#[test]
fn a_malformed_payload_is_reported_rather_than_fatal() {
    for payload in [
        &b"not json at all"[..],
        br#"{"version":1}"#,
        br#"{"version":1,"object_id":7,"material_class":"M-99","confidence":0.9,
             "x_meters":0.0,"y_meters":0.0,"z_meters":0.36,"yaw_radians":0.0,
             "reference_time_nanos":1000,"window_start_nanos":1000,
             "window_end_nanos":2000}"#,
    ] {
        let error = Proposal::decode(payload).unwrap_err();
        assert!(!format!("{error}").is_empty());
    }
}

#[test]
fn a_point_beyond_reach_is_overridden_naming_the_check() {
    // The point is at the belt surface height
    // and inside the trusted vertical band; only the distance from the shoulder
    // disqualifies it, at 2.90 m against an outer radius of 1.25 m.
    let proposal = Proposal::decode(wire(0.0, 2.20, 0.95, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::Reach));
}

#[test]
fn a_point_below_the_belt_surface_is_overridden() {
    let proposal = Proposal::decode(wire(0.0, 0.0, 0.80, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::BeltSurface));
}

#[test]
fn a_point_above_the_trusted_vertical_band_is_overridden() {
    // Reachable at 0.70 m from the shoulder and above the belt
    // surface, so only the height disqualifies it: 1.40 m is 0.50 m above a
    // base at 0.90 m, against a trusted ceiling of 0.45 m.
    //
    // Only the ceiling is reachable through this check. The band's floor sits
    // at 0.85 m and the belt surface at 0.90 m, so any point low enough to fail
    // the floor fails `BeltSurface` first, which runs before it.
    let proposal = Proposal::decode(wire(0.0, 0.0, 1.40, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::ToolHeight));
}

#[test]
fn a_point_off_the_belt_is_overridden() {
    // Reachable, and 0.55 m across against a belt half width of 0.50 m, so the
    // extent check is what refuses it rather than the reach check.
    let proposal = Proposal::decode(wire(0.0, 0.55, 0.95, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::BeltExtent));
}

#[test]
fn a_point_inside_the_envelope_is_accepted_with_a_publishable_decision() {
    let proposal = Proposal::decode(reachable().as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    let Verdict::Accepted { decision, routed } = verdict else {
        panic!("an in-envelope proposal was overridden: {verdict:?}");
    };
    assert_eq!(decision.class(), MaterialClass::Pet);
    assert_eq!(decision.channel(), ChannelId::new(1));
    assert_eq!(routed.reject_reason(), None);
}

#[test]
fn every_point_in_a_swept_grid_reaches_exactly_one_verdict() {
    // A verdict is one of two variants, so what this proves is
    // that no input leaves the layer undecided or panicking.
    let envelope = envelope();
    let resolver = resolver();
    let mut accepted = 0_u32;
    let mut overridden = 0_u32;
    for xi in -12_i32..=12 {
        for yi in -6_i32..=6 {
            for zi in -2_i32..=4 {
                let x = f64::from(xi) * 0.1;
                let y = f64::from(yi) * 0.1;
                let z = 0.90 + f64::from(zi) * 0.05;
                let proposal = Proposal::decode(wire(x, y, z, 0.90).as_bytes()).unwrap();
                match envelope.judge(&proposal, &resolver).unwrap() {
                    Verdict::Accepted { .. } => accepted += 1,
                    Verdict::Overridden { .. } => overridden += 1,
                }
            }
        }
    }
    assert_eq!(accepted + overridden, 25 * 13 * 7);
    assert!(accepted > 0, "the grid never reached an acceptable point");
    assert!(overridden > 0, "the grid never reached a refused point");
}

#[test]
fn a_low_confidence_proposal_is_rejected_rather_than_overridden() {
    // The point is inside the envelope, so the safety layer has
    // nothing to say; the routing policy sends it to the reject channel.
    let proposal = Proposal::decode(wire(0.0, 0.0, 0.95, 0.20).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    let Verdict::Accepted { decision, routed } = verdict else {
        panic!("a low confidence proposal was counted as a safety override");
    };
    assert_eq!(decision.channel(), REJECT);
    assert_eq!(routed.reject_reason(), Some(RejectReason::BelowThreshold));
}

#[test]
fn the_envelope_names_a_missing_configuration_key() {
    // No geometric constant lives in this crate, so a key that
    // is absent has to fail rather than fall back.
    let error = Envelope::from_json(br#"{"base": [0.0, -0.70, 0.90]}"#).unwrap_err();
    assert!(
        format!("{error}").contains("reach"),
        "the error does not name the missing key: {error}"
    );
}

#[test]
fn the_envelope_loads_from_a_file() {
    let path = std::env::temp_dir().join("clave-safety-envelope-test.json");
    std::fs::write(&path, ENVELOPE_JSON).unwrap();
    let loaded = Envelope::load(&path).unwrap();
    std::fs::remove_file(&path).unwrap();
    assert!((loaded.reach().1 - 1.25).abs() < 1e-12);
}

#[test]
fn the_crate_links_no_machine_learning_framework() {
    // The property that lets this crate override a model is that
    // it shares no code with one, and a manifest is where that is checkable.
    let manifest = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml"))
        .unwrap()
        .to_lowercase();
    for framework in [
        "ort", "tch", "torch", "onnx", "candle", "burn", "tract", "gtsam",
    ] {
        assert!(
            !manifest.contains(&format!("\n{framework}")),
            "the safety crate declares {framework}"
        );
    }
}

#[test]
fn each_check_carries_a_stable_name_a_counter_can_use() {
    // An operator reading a rising override count needs to know
    // whether the model reaches too far, aims into the belt, or picks off it.
    assert_eq!(Check::Reach.name(), "reach");
    assert_eq!(Check::ToolHeight.name(), "tool_height");
    assert_eq!(Check::BeltSurface.name(), "belt_surface");
    assert_eq!(Check::BeltExtent.name(), "belt_extent");
}

#[test]
fn an_overridden_proposal_carries_no_decision_to_publish() {
    // Nothing reaches the publisher when a check fails.
    let envelope = envelope();
    let resolver = resolver();
    let refused = Proposal::decode(wire(0.9, 0.0, 0.36, 0.90).as_bytes()).unwrap();
    assert!(
        envelope
            .judge(&refused, &resolver)
            .unwrap()
            .decision()
            .is_none()
    );
    let allowed = Proposal::decode(reachable().as_bytes()).unwrap();
    let verdict = envelope.judge(&allowed, &resolver).unwrap();
    assert_eq!(
        verdict.decision().map(|decision| decision.object().get()),
        Some(7)
    );
    assert_eq!(verdict.overridden_check(), None);
}

fn set(row: &mut [f64; OUTCOME_COUNT], index: usize, value: f64) {
    if let Some(slot) = row.get_mut(index) {
        *slot = value;
    }
}

fn weights(pairs: &[(usize, f64)]) -> [f64; OUTCOME_COUNT] {
    let mut posterior = [0.0; OUTCOME_COUNT];
    for &(index, weight) in pairs {
        set(&mut posterior, index, weight);
    }
    posterior
}

fn weights_json(pairs: &[(usize, f64)]) -> String {
    weights(pairs)
        .iter()
        .map(|weight| format!("{weight}"))
        .collect::<Vec<_>>()
        .join(",")
}

fn wire_v2(class: &str, confidence: f64, pairs: &[(usize, f64)]) -> String {
    let posterior = weights_json(pairs);
    format!(
        r#"{{"version":2,"object_id":7,"material_class":"{class}","confidence":{confidence},
            "posterior":[{posterior}],
            "x_meters":0.0,"y_meters":0.0,"z_meters":0.95,"yaw_radians":0.0,
            "reference_time_nanos":1000,"window_start_nanos":1000,
            "window_end_nanos":2000}}"#
    )
}

fn cost_resolver(
    classes: &[(MaterialClass, u16)],
    rows: &[(u16, [f64; OUTCOME_COUNT])],
) -> Resolver {
    let entries = classes
        .iter()
        .map(|(class, channel)| (*class, ChannelId::new(*channel)));
    let map = ChannelMap::new(entries, REJECT, Confidence::new(0.6).unwrap()).unwrap();
    let cost_rows = rows
        .iter()
        .map(|(channel, costs)| (ChannelId::new(*channel), *costs));
    Resolver::with_expected_cost(map, cost_rows).unwrap()
}

/// AC-SORT-16: the safety manifest does not name GTSAM.
#[test]
fn ac_sort_16_the_safety_manifest_does_not_name_gtsam() {
    let manifest = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml"))
        .unwrap()
        .to_lowercase();
    assert!(
        !manifest.contains("gtsam"),
        "the safety crate declares gtsam"
    );
}

/// AC-SORT-17: a version 2 runtime refuses version 1 before the broken field.
#[test]
fn ac_sort_17_a_version_2_runtime_refuses_version_1_before_other_fields() {
    let payload = br#"{"version":1,"material_class":99}"#;
    let error = Proposal::decode_as(payload, PROPOSAL_VERSION_POSTERIOR).unwrap_err();
    assert!(matches!(
        error,
        SafetyError::UnsupportedVersion { found: 1 }
    ));
}

/// AC-SORT-18: class and confidence have to match the posterior.
#[test]
fn ac_sort_18_a_class_or_confidence_that_disagrees_with_the_posterior_is_refused() {
    let peaked = &[(7, 0.6), (5, 0.4)];
    let wrong_class = wire_v2("M-01", 0.6, peaked);
    let class_error =
        Proposal::decode_as(wrong_class.as_bytes(), PROPOSAL_VERSION_POSTERIOR).unwrap_err();
    assert!(
        format!("{class_error}").contains("M-08"),
        "the error does not name the leading class: {class_error}"
    );

    let wrong_confidence = wire_v2("M-08", 0.9, peaked);
    let confidence_error =
        Proposal::decode_as(wrong_confidence.as_bytes(), PROPOSAL_VERSION_POSTERIOR).unwrap_err();
    assert!(
        format!("{confidence_error}").contains("confidence"),
        "the error does not name confidence: {confidence_error}"
    );
}

/// AC-SORT-07: a version 2 proposal takes the minimum expected-cost channel,
/// which is not the channel the leading class maps to.
#[test]
fn ac_sort_07_a_version_2_proposal_takes_the_minimum_expected_cost_channel() {
    let mut reject_row = [2.0; OUTCOME_COUNT];
    let mut ferrous = [3.0; OUTCOME_COUNT];
    let mut fiber = [4.0; OUTCOME_COUNT];
    set(&mut reject_row, 10, 0.0);
    set(&mut reject_row, 11, 0.0);
    set(&mut ferrous, 5, 0.0);
    set(&mut ferrous, 7, 3.0);
    set(&mut ferrous, 10, 10.0);
    set(&mut fiber, 5, 10.0);
    set(&mut fiber, 7, 0.0);
    set(&mut fiber, 10, 10.0);
    let resolver = cost_resolver(
        &[(MaterialClass::Cardboard, 8), (MaterialClass::Ferrous, 6)],
        &[(0, reject_row), (6, ferrous), (8, fiber)],
    );
    let payload = wire_v2("M-08", 0.6, &[(7, 0.6), (5, 0.4)]);
    let proposal = Proposal::decode_as(payload.as_bytes(), PROPOSAL_VERSION_POSTERIOR).unwrap();
    let verdict = envelope().judge(&proposal, &resolver).unwrap();
    let decision = verdict.decision().unwrap();

    assert_eq!(decision.class(), MaterialClass::Cardboard);
    assert_eq!(decision.channel(), ChannelId::new(6));
    assert!(matches!(
        verdict,
        Verdict::Accepted {
            routed: Routed::Sorted(channel),
            ..
        } if channel == ChannelId::new(6)
    ));
}

/// AC-SORT-08: when reject minimizes expected cost, the decision keeps the
/// leading class and publishes the reject channel.
#[test]
fn ac_sort_08_reject_wins_and_the_leading_class_stays_on_the_decision() {
    let mut reject_row = [2.0; OUTCOME_COUNT];
    let mut aluminum = [3.0; OUTCOME_COUNT];
    let mut ferrous = [3.0; OUTCOME_COUNT];
    set(&mut reject_row, 10, 0.0);
    set(&mut reject_row, 11, 0.0);
    set(&mut aluminum, 4, 0.0);
    set(&mut aluminum, 5, 8.0);
    set(&mut aluminum, 10, 10.0);
    set(&mut ferrous, 4, 5.0);
    set(&mut ferrous, 5, 0.0);
    set(&mut ferrous, 10, 10.0);
    let resolver = cost_resolver(
        &[(MaterialClass::Aluminum, 5), (MaterialClass::Ferrous, 6)],
        &[(0, reject_row), (5, aluminum), (6, ferrous)],
    );
    let payload = wire_v2("M-05", 0.5, &[(4, 0.5), (5, 0.5)]);
    let proposal = Proposal::decode_as(payload.as_bytes(), PROPOSAL_VERSION_POSTERIOR).unwrap();
    let verdict = envelope().judge(&proposal, &resolver).unwrap();
    let decision = verdict.decision().unwrap();

    assert_eq!(decision.class(), MaterialClass::Aluminum);
    assert_eq!(decision.channel(), REJECT);
    assert!(matches!(
        verdict,
        Verdict::Accepted {
            routed: Routed::Rejected {
                channel: REJECT,
                reason: RejectReason::ExpectedCost,
            },
            ..
        }
    ));
}

/// Expected cost still sorts when the leading weight is below the floor.
#[test]
fn expected_cost_sorts_below_the_confidence_floor() {
    let mut reject_row = [2.0; OUTCOME_COUNT];
    let mut pet = [3.0; OUTCOME_COUNT];
    let mut hdpe = [3.0; OUTCOME_COUNT];
    set(&mut reject_row, 10, 0.0);
    set(&mut pet, 0, 0.0);
    set(&mut pet, 1, 3.0);
    set(&mut pet, 10, 10.0);
    set(&mut hdpe, 0, 3.0);
    set(&mut hdpe, 1, 0.0);
    set(&mut hdpe, 10, 10.0);
    let resolver = cost_resolver(
        &[(MaterialClass::Pet, 1), (MaterialClass::Hdpe, 2)],
        &[(0, reject_row), (1, pet), (2, hdpe)],
    );
    let payload = wire_v2("M-01", 0.55, &[(0, 0.55), (1, 0.45)]);
    let proposal = Proposal::decode_as(payload.as_bytes(), PROPOSAL_VERSION_POSTERIOR).unwrap();
    let decision = envelope()
        .judge(&proposal, &resolver)
        .unwrap()
        .decision()
        .unwrap();

    assert_eq!(decision.channel(), ChannelId::new(1));
    assert!((f64::from(decision.confidence().get()) - 0.55).abs() < 1e-6);
}
