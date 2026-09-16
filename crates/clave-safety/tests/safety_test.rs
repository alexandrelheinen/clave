//! The inference boundary and the checks that can override a model.
//!
//! Covers `AC-BRIDGE-01` through `AC-BRIDGE-04`, `AC-SAFETY-01` through
//! `AC-SAFETY-07`.
#![expect(clippy::unwrap_used, reason = "test assertions")]
#![expect(
    clippy::panic,
    reason = "a test that reaches an impossible branch should fail loudly"
)]

use clave_decision::{ChannelId, Confidence, MaterialClass};
use clave_routing::{ChannelMap, RejectReason, Resolver};
use clave_safety::{Check, Envelope, Proposal, SafetyError, Verdict};

const REJECT: ChannelId = ChannelId::new(0);

/// An envelope roughly matching the shipped world: the arm sits beside the
/// belt, the belt surface is at 0.35 m, and the working area is two meters long.
fn envelope() -> Envelope {
    Envelope::from_json(ENVELOPE_JSON.as_bytes()).unwrap()
}

const ENVELOPE_JSON: &str = r#"{
  "shoulder_meters": [1.5, 0.0, 1.408],
  "link_meters": [0.400, 0.250],
  "reach_meters": [0.222, 0.650],
  "shoulder_limit_radians": 2.443461,
  "elbow_limit_radians": 2.617994,
  "tool_above_belt_meters": [0.030, 0.210],
  "belt_surface_z_meters": 0.90,
  "belt_x_meters": [0.0, 3.0],
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
    // 0.35 m in front of the shoulder at (1.5, 0), clear of the 0.222 m dead
    // zone, inside the 0.650 m outer radius, and inside the wedge axis 1 can
    // turn to. At 0.10 m above the belt, which the spline stroke covers.
    wire(1.85, 0.0, 1.00, 0.90)
}

#[test]
fn a_proposal_carries_every_field_across_the_boundary() {
    // AC-BRIDGE-01.
    let proposal = Proposal::decode(reachable().as_bytes()).unwrap();
    assert_eq!(proposal.object().get(), 7);
    assert_eq!(proposal.class(), MaterialClass::Pet);
    assert!((f64::from(proposal.confidence().get()) - 0.90).abs() < 1e-6);
    assert!((proposal.pose().point().z_meters() - 1.00).abs() < 1e-9);
    assert_eq!(proposal.window().earliest().get(), 1000);
}

#[test]
fn an_unrecognized_version_is_refused_by_version() {
    // AC-BRIDGE-03. The version is read before any other field, so a payload
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
    // AC-BRIDGE-04.
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
    // AC-SAFETY-01 and AC-SAFETY-04. The point is on the belt and inside the
    // stroke; only the distance from the shoulder disqualifies it, at 1.2 m
    // against an outer radius of 0.650 m.
    let proposal = Proposal::decode(wire(2.7, 0.0, 1.00, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::Reach));
}

#[test]
fn a_point_below_the_belt_surface_is_overridden() {
    // AC-SAFETY-02.
    let proposal = Proposal::decode(wire(1.85, 0.0, 0.80, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::BeltSurface));
}

#[test]
fn a_point_off_the_belt_is_overridden() {
    // AC-SAFETY-03.
    // Reachable, and 0.55 m across against a belt half width of 0.50 m, so the
    // extent check is what refuses it rather than the reach check.
    let proposal = Proposal::decode(wire(1.50, 0.55, 1.00, 0.90).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    assert_eq!(verdict.overridden_check(), Some(Check::BeltExtent));
}

#[test]
fn a_point_inside_the_envelope_is_accepted_with_a_publishable_decision() {
    // AC-SAFETY-06.
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
    // AC-SAFETY-06. A verdict is one of two variants, so what this proves is
    // that no input leaves the layer undecided or panicking.
    let envelope = envelope();
    let resolver = resolver();
    let mut accepted = 0_u32;
    let mut overridden = 0_u32;
    for xi in -12_i32..=12 {
        for yi in -6_i32..=6 {
            for zi in -2_i32..=4 {
                let x = 1.5 + f64::from(xi) * 0.1;
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
    // AC-SAFETY-07. The point is inside the envelope, so the safety layer has
    // nothing to say; the routing policy sends it to the reject channel.
    let proposal = Proposal::decode(wire(1.85, 0.0, 1.00, 0.20).as_bytes()).unwrap();
    let verdict = envelope().judge(&proposal, &resolver()).unwrap();
    let Verdict::Accepted { decision, routed } = verdict else {
        panic!("a low confidence proposal was counted as a safety override");
    };
    assert_eq!(decision.channel(), REJECT);
    assert_eq!(routed.reject_reason(), Some(RejectReason::BelowThreshold));
}

#[test]
fn the_envelope_names_a_missing_configuration_key() {
    // AC-SAFETY-05. No geometric constant lives in this crate, so a key that
    // is absent has to fail rather than fall back.
    let error = Envelope::from_json(br#"{"shoulder_meters": [1.5, 0.0, 1.408]}"#).unwrap_err();
    assert!(
        format!("{error}").contains("link_meters"),
        "the error does not name the missing key: {error}"
    );
}

#[test]
fn the_envelope_loads_from_a_file() {
    // AC-SAFETY-05.
    let path = std::env::temp_dir().join("clave-safety-envelope-test.json");
    std::fs::write(&path, ENVELOPE_JSON).unwrap();
    let loaded = Envelope::load(&path).unwrap();
    std::fs::remove_file(&path).unwrap();
    assert!((loaded.reach_meters().1 - 0.650).abs() < 1e-12);
}

#[test]
fn the_crate_links_no_machine_learning_framework() {
    // AC-BRIDGE-02. The property that lets this crate override a model is that
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
    // AC-SAFETY-04. An operator reading a rising override count needs to know
    // whether the model reaches too far, aims into the belt, or picks off it.
    assert_eq!(Check::Reach.name(), "reach");
    assert_eq!(Check::BeltSurface.name(), "belt_surface");
    assert_eq!(Check::BeltExtent.name(), "belt_extent");
}

#[test]
fn an_overridden_proposal_carries_no_decision_to_publish() {
    // AC-SAFETY-01. Nothing reaches the publisher when a check fails.
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
