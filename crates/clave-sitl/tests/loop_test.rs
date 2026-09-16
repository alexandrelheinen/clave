//! The loop over real sockets, end to end in one test process.
//!
//! Covers `AC-LOOP-01`, `AC-LOOP-03` and `AC-LOOP-04`.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use std::os::unix::net::UnixDatagram;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use clave_decision::{MaterialClass, codec};
use clave_sitl::{ServeConfig, serve};

const CONFIG: &str = r#"{
  "shoulder_meters": [1.5, 0.0, 1.408],
  "link_meters": [0.400, 0.250],
  "reach_meters": [0.222, 0.650],
  "shoulder_limit_radians": 2.443461,
  "elbow_limit_radians": 2.617994,
  "tool_above_belt_meters": [0.030, 0.210],
  "belt_surface_z_meters": 0.90,
  "belt_x_meters": [0.0, 3.0],
  "belt_y_meters": [-0.5, 0.5],
  "channels": {"M-01": 1, "M-05": 2},
  "reject_channel": 0,
  "confidence_floor": 0.6
}"#;

/// A proposal naming a point, at a confidence, on the wire.
fn wire(x: f64, y: f64, z: f64, confidence: f64) -> String {
    format!(
        r#"{{"version":1,"object_id":7,"material_class":"M-01","confidence":{confidence},
           "x_meters":{x},"y_meters":{y},"z_meters":{z},"yaw_radians":0.0,
           "reference_time_nanos":1000,"window_start_nanos":1000,
           "window_end_nanos":9223372036854775807}}"#
    )
}

/// A directory nothing else in this run writes to.
fn scratch(name: &str) -> PathBuf {
    let directory = std::env::temp_dir().join(format!("clave-sitl-{name}-{}", std::process::id()));
    std::fs::create_dir_all(&directory).unwrap();
    directory
}

/// Waits for the runtime to bind, so the first proposal is not sent into a void.
fn await_bind(path: &Path) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while !path.exists() {
        assert!(
            Instant::now() < deadline,
            "the runtime never bound {}",
            path.display()
        );
        std::thread::sleep(Duration::from_millis(5));
    }
}

/// Reads one datagram, failing rather than hanging when none arrives.
fn receive(socket: &UnixDatagram) -> Vec<u8> {
    socket
        .set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap();
    let mut buffer = vec![0_u8; 65_536];
    let read = socket.recv(&mut buffer).unwrap();
    buffer.truncate(read);
    buffer
}

#[test]
fn the_runtime_decides_publishes_and_counts_over_real_sockets() {
    let directory = scratch("loop");
    let config = directory.join("config.json");
    std::fs::write(&config, CONFIG).unwrap();
    let paths = ServeConfig {
        config,
        listen: directory.join("proposals.sock"),
        decisions: directory.join("decisions.sock"),
        outcomes: directory.join("outcomes.sock"),
    };

    // The producer binds its own sockets first, as the documented order says.
    let _removed = std::fs::remove_file(&paths.decisions);
    let _also_removed = std::fs::remove_file(&paths.outcomes);
    let decisions = UnixDatagram::bind(&paths.decisions).unwrap();
    let outcomes = UnixDatagram::bind(&paths.outcomes).unwrap();

    let listen = paths.listen.clone();
    let runtime = std::thread::spawn(move || serve(&paths).unwrap());
    await_bind(&listen);

    let sender = UnixDatagram::unbound().unwrap();
    sender.connect(&listen).unwrap();
    for payload in [
        wire(1.85, 0.0, 1.00, 0.90), // accepted and sorted
        wire(2.70, 0.0, 1.00, 0.90), // beyond reach
        "{ not json".to_owned(),     // refused
        wire(1.85, 0.0, 1.00, 0.20), // routed to reject on confidence
    ] {
        sender.send(payload.as_bytes()).unwrap();
    }

    let read = |socket: &UnixDatagram| -> serde_json::Value {
        serde_json::from_slice(&receive(socket)).unwrap()
    };
    let first = read(&outcomes);
    assert_eq!(first["verdict"], "accepted");
    assert_eq!(first["channel"], 1);
    assert_eq!(read(&outcomes)["check"], "reach");
    assert_eq!(read(&outcomes)["verdict"], "refused");
    let fourth = read(&outcomes);
    assert_eq!(fourth["channel"], 0);
    assert_eq!(fourth["reject_reason"], "below_threshold");

    // Two decisions were published: the sorted one and the rejected one. An
    // overridden proposal publishes nothing, which is the point of the layer.
    for expected_channel in [1_u16, 0] {
        let decision = codec::decode(&receive(&decisions)).unwrap();
        assert_eq!(decision.class(), MaterialClass::Pet);
        assert_eq!(decision.channel().get(), expected_channel);
    }

    sender.send(b"").unwrap();
    let counters = runtime.join().unwrap();
    assert_eq!(counters.proposals, 4);
    assert_eq!(counters.accepted, 1);
    assert_eq!(counters.overridden_reach, 1);
    assert_eq!(counters.refused, 1);
    assert_eq!(counters.rejected_low_confidence, 1);
    assert_eq!(counters.published, 2);
    std::fs::remove_dir_all(&directory).unwrap();
}

#[test]
fn a_configuration_naming_an_unknown_class_is_refused_before_any_socket_is_bound() {
    let directory = scratch("badconfig");
    let config = directory.join("config.json");
    std::fs::write(&config, CONFIG.replace("\"M-01\": 1", "\"M-99\": 1")).unwrap();
    let paths = ServeConfig {
        config,
        listen: directory.join("proposals.sock"),
        decisions: directory.join("decisions.sock"),
        outcomes: directory.join("outcomes.sock"),
    };
    let error = serve(&paths).unwrap_err();
    assert!(format!("{error}").contains("unusable"), "{error}");
    assert!(!paths.listen.exists(), "a socket was bound anyway");
    std::fs::remove_dir_all(&directory).unwrap();
}

#[test]
fn every_path_the_runtime_needs_is_required_on_the_command_line() {
    let complete = [
        "--config",
        "c.json",
        "--listen",
        "p.sock",
        "--decisions",
        "d.sock",
        "--outcomes",
        "o.sock",
    ]
    .map(str::to_owned);
    let parsed = ServeConfig::from_arguments(complete.clone()).unwrap();
    assert_eq!(parsed.listen, PathBuf::from("p.sock"));

    let without_outcomes = complete.iter().take(6).cloned().collect::<Vec<_>>();
    let error = ServeConfig::from_arguments(without_outcomes).unwrap_err();
    assert!(format!("{error}").contains("--outcomes"), "{error}");

    let unknown = ["--sink".to_owned(), "x".to_owned()];
    let error = ServeConfig::from_arguments(unknown).unwrap_err();
    assert!(format!("{error}").contains("--sink"), "{error}");
}
