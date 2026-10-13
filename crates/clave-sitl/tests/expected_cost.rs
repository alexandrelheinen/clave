//! Loading expected cost, and counting the reject it produces.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use clave_decision::{ChannelId, MaterialClass, codec};
use clave_publish::InMemorySink;
use clave_sitl::{Outcome, RuntimeConfig, Service};

const ENVELOPE: &str = r#"
  "base_meters": [0.0, -0.70, 0.90],
  "reach_meters": [0.25, 1.25],
  "tool_above_base_meters": [-0.05, 0.45],
  "belt_surface_z_meters": 0.90,
  "belt_x_meters": [-1.5, 1.5],
  "belt_y_meters": [-0.5, 0.5],
  "channels": {"M-08": 8, "M-06": 6, "M-05": 5},
  "reject_channel": 0,
  "confidence_floor": 0.6
"#;

fn config(extra: &str) -> String {
    format!("{{{ENVELOPE},{extra}}}")
}

fn row(channel: u16, costs: [f64; 12]) -> String {
    let body = costs
        .iter()
        .map(|cost| format!("{cost}"))
        .collect::<Vec<_>>()
        .join(",");
    format!(r#"{{"channel":{channel},"costs":[{body}]}}"#)
}

fn divert_costs() -> String {
    let mut reject = [2.0; 12];
    let mut ferrous = [3.0; 12];
    let mut fiber = [4.0; 12];
    let mut aluminum = [3.0; 12];
    reject[10] = 0.0;
    reject[11] = 0.0;
    ferrous[4] = 5.0;
    ferrous[5] = 0.0;
    ferrous[7] = 3.0;
    ferrous[10] = 10.0;
    fiber[5] = 10.0;
    fiber[7] = 0.0;
    fiber[10] = 10.0;
    aluminum[4] = 0.0;
    aluminum[5] = 8.0;
    aluminum[10] = 10.0;
    format!(
        "[{},{},{},{}]",
        row(0, reject),
        row(5, aluminum),
        row(6, ferrous),
        row(8, fiber)
    )
}

fn proposal(version: u64, class: &str, confidence: f64, posterior: &str) -> String {
    format!(
        r#"{{"version":{version},"object_id":7,"material_class":"{class}",
            "confidence":{confidence},"posterior":[{posterior}],
            "x_meters":0.0,"y_meters":0.0,"z_meters":0.95,"yaw_radians":0.0,
            "reference_time_nanos":1000,"window_start_nanos":1000,
            "window_end_nanos":2000}}"#
    )
}

/// AC-SORT-21: a floor runtime does not read `cost`, even when the value
/// would not parse as a table.
#[test]
fn ac_sort_21_a_confidence_floor_runtime_ignores_a_garbage_cost() {
    for rule in [
        r#""rule":"confidence_floor","cost":"nope""#,
        r#""cost":"nope""#,
    ] {
        let loaded = RuntimeConfig::from_json(config(rule).as_bytes()).unwrap();
        assert!(!loaded.resolver().uses_expected_cost());
    }
}

#[test]
fn an_unknown_rule_is_refused() {
    let error =
        RuntimeConfig::from_json(config(r#""rule":"cheapest_label""#).as_bytes()).unwrap_err();
    assert!(
        format!("{error}").contains("cheapest_label"),
        "the error does not name the rule: {error}"
    );
}

#[test]
fn expected_cost_names_a_missing_cost_key() {
    let error =
        RuntimeConfig::from_json(config(r#""rule":"expected_cost""#).as_bytes()).unwrap_err();
    assert!(
        format!("{error}").contains("cost"),
        "the error does not name the missing key: {error}"
    );
}

/// AC-SORT-09: the runtime refuses the table at load.
#[test]
fn ac_sort_09_a_runtime_refuses_residue_cheaper_than_reject() {
    let mut reject = [1.0; 12];
    let mut sorted = [1.0; 12];
    reject[10] = 5.0;
    sorted[10] = 4.0;
    let document = format!(
        r#"{{
            "base_meters": [0.0, -0.70, 0.90],
            "reach_meters": [0.25, 1.25],
            "tool_above_base_meters": [-0.05, 0.45],
            "belt_surface_z_meters": 0.90,
            "belt_x_meters": [-1.5, 1.5],
            "belt_y_meters": [-0.5, 0.5],
            "channels": {{"M-08": 8}},
            "reject_channel": 0,
            "confidence_floor": 0.6,
            "rule": "expected_cost",
            "cost": [{}, {}]
        }}"#,
        row(0, reject),
        row(8, sorted)
    );
    let error = RuntimeConfig::from_json(document.as_bytes()).unwrap_err();
    assert!(
        format!("{error}").contains("residue"),
        "the error does not name residue: {error}"
    );
}

#[test]
fn a_version_2_runtime_diverts_and_counts_an_expected_cost_reject() {
    let document = format!(
        r#"{{
            {ENVELOPE},
            "rule": "expected_cost",
            "cost": {}
        }}"#,
        divert_costs()
    );
    let loaded = RuntimeConfig::from_json(document.as_bytes()).unwrap();
    assert!(loaded.resolver().uses_expected_cost());
    let mut service = Service::new(
        *loaded.envelope(),
        loaded.resolver().clone(),
        InMemorySink::new(),
    );

    let version_1 = proposal(1, "M-08", 0.6, "0,0,0,0,0,0.4,0,0.6,0,0,0,0");
    let refused = service.handle(version_1.as_bytes());
    assert!(matches!(refused, Outcome::Refused { .. }));
    assert_eq!(service.counters().refused, 1);

    let divert = proposal(2, "M-08", 0.6, "0,0,0,0,0,0.4,0,0.6,0,0,0,0");
    let diverted = service.handle(divert.as_bytes());
    assert_eq!(
        diverted,
        Outcome::Accepted {
            object_id: 7,
            channel: 6,
            reject_reason: None,
        }
    );

    let reject = proposal(2, "M-05", 0.5, "0,0,0,0,0.5,0.5,0,0,0,0,0,0");
    let rejected = service.handle(reject.as_bytes());
    assert_eq!(
        rejected,
        Outcome::Accepted {
            object_id: 7,
            channel: 0,
            reject_reason: Some("expected_cost"),
        }
    );
    assert_eq!(service.counters().rejected_expected_cost, 1);
    assert_eq!(service.counters().accepted, 1);

    let frames = service.publisher().sink().frames();
    assert_eq!(frames.len(), 2);
    let decision = codec::decode(&frames[0]).unwrap();
    assert_eq!(decision.class(), MaterialClass::Cardboard);
    assert_eq!(decision.channel(), ChannelId::new(6));
    let kept = codec::decode(&frames[1]).unwrap();
    assert_eq!(kept.class(), MaterialClass::Aluminum);
    assert_eq!(kept.channel(), ChannelId::new(0));
}
