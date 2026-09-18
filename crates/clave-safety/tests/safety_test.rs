//! The inference boundary and the checks that can override a model.
#![expect(clippy::unwrap_used, reason = "test assertions")]
#![expect(
    clippy::panic,
    reason = "a test that reaches an impossible branch should fail loudly"
)]

use clave_decision::{ChannelId, Confidence, MaterialClass};
use clave_routing::{ChannelMap, RejectReason, Resolver};
use clave_safety::{Check, Envelope, Proposal, SafetyError, Verdict};

const REJECT: ChannelId = ChannelId::new(0);

/// An envelope matching the shipped world: the arm sits on a pedestal beside
/// the belt at 0.70 m from the centerline, the belt surface is at 0.90 m, and
/// the belt is 3.00 m long by 1.00 m wide.
fn envelope() -> Envelope {
    Envelope::from_json(ENVELOPE_JSON.as_bytes()).unwrap()
}

const ENVELOPE_JSON: &str = r#"{
  "base_meters": [0.0, -0.70, 0.90],
  "reach_meters": [0.25, 1.25],
  "tool_above_base_meters": [-0.05, 0.45],
  "belt_surface_z_meters": 0.90,
  "belt_x_meters": [-1.5, 1.5],
  "belt_y_meters": [-0.5, 0.5]
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
    assert!((proposal.pose().point().z_meters() - 0.95).abs() < 1e-9);
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
    let error = Envelope::from_json(br#"{"base_meters": [0.0, -0.70, 0.90]}"#).unwrap_err();
    assert!(
        format!("{error}").contains("reach_meters"),
        "the error does not name the missing key: {error}"
    );
}

#[test]
fn the_envelope_loads_from_a_file() {
    let path = std::env::temp_dir().join("clave-safety-envelope-test.json");
    std::fs::write(&path, ENVELOPE_JSON).unwrap();
    let loaded = Envelope::load(&path).unwrap();
    std::fs::remove_file(&path).unwrap();
    assert!((loaded.reach_meters().1 - 1.25).abs() < 1e-12);
}

#[test]
fn the_crate_links_no_machine_learning_framework() {
    // The property that lets this crate override a model is that
    // it shares no code with one, and a manifest is where that is checkable.
    let manifest = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml"))
        .unwrap()
        .to_lowercase();
    for framework in ["ort", "tch", "torch", "onnx", "candle", "burn", "tract"] {
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
