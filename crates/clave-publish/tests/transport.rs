//! The socket sink itself, apart from the policy in front of it.
//!
//! Covers `AC-PUBLISH-01`, `AC-PUBLISH-02` and `AC-PUBLISH-05`.
#![expect(clippy::unwrap_used, reason = "test assertions")]

mod support;

use std::os::unix::net::UnixDatagram;
use std::path::PathBuf;
use std::process;

use clave_decision::codec;
use clave_publish::{DecisionSink, SendOutcome, UnixDatagramSink};

use crate::support::decision_for;

/// Returns a path in the temporary directory that no other test uses.
fn socket_path(name: &str) -> PathBuf {
    let mut path = std::env::temp_dir();
    path.push(format!("clave-{}-{name}.sock", process::id()));
    let _removed = std::fs::remove_file(&path);
    path
}

/// AC-PUBLISH-01: a consumer bound to a path receives what the sink sends to
/// that path, which is how the two processes meet outside a test.
#[test]
fn a_sink_connected_to_a_path_reaches_the_consumer_bound_to_it() {
    let path = socket_path("connected");
    let consumer = UnixDatagram::bind(&path).unwrap();
    let mut sink = UnixDatagramSink::connect(&path).unwrap();
    let frame = codec::encode(&decision_for(11, 0)).unwrap();

    assert_eq!(sink.try_send(&frame).unwrap(), SendOutcome::Sent);

    let mut buffer = vec![0_u8; 8192];
    let length = consumer.recv(&mut buffer).unwrap();
    assert_eq!(buffer.get(..length).unwrap(), frame.as_slice());
    assert!(sink.socket().peer_addr().is_ok());
    std::fs::remove_file(&path).unwrap();
}

/// AC-PUBLISH-05: a consumer that stops reading fills the kernel queue, and
/// the sink reports a refusal rather than waiting for room.
#[test]
fn a_full_kernel_queue_is_a_refusal_rather_than_a_wait() {
    let (mut sink, consumer) = UnixDatagramSink::pair().unwrap();
    let frame = codec::encode(&decision_for(1, 0)).unwrap();

    let mut refused = false;
    for _ in 0_u32..100_000 {
        if sink.try_send(&frame).unwrap() == SendOutcome::WouldBlock {
            refused = true;
            break;
        }
    }

    assert!(refused, "the sink never reported a full queue");
    drop(consumer);
}

/// AC-PUBLISH-05: a consumer that has gone is a refusal too, so a dead
/// consumer never reaches the caller as an error.
#[test]
fn a_departed_consumer_is_a_refusal_rather_than_an_error() {
    let (mut sink, consumer) = UnixDatagramSink::pair().unwrap();
    drop(consumer);
    let frame = codec::encode(&decision_for(1, 0)).unwrap();

    assert_eq!(sink.try_send(&frame).unwrap(), SendOutcome::WouldBlock);
}

/// AC-PUBLISH-02: one record in, one record out. The kernel keeps the
/// boundary, so a consumer never reassembles a frame or splits two.
#[test]
fn every_record_arrives_whole_and_on_its_own() {
    let (mut sink, consumer) = UnixDatagramSink::pair().unwrap();
    consumer.set_nonblocking(true).unwrap();
    let frames: Vec<Vec<u8>> = (1_u64..=4)
        .map(|object| codec::encode(&decision_for(object, 0)).unwrap())
        .collect();

    for frame in &frames {
        assert_eq!(sink.try_send(frame).unwrap(), SendOutcome::Sent);
    }

    let mut buffer = vec![0_u8; 8192];
    for frame in &frames {
        let length = consumer.recv(&mut buffer).unwrap();
        assert_eq!(buffer.get(..length).unwrap(), frame.as_slice());
    }
    assert!(consumer.recv(&mut buffer).is_err());
}
