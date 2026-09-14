//! One delivery contract, proved against every sink behind the seam.
//!
//! Covers `AC-PUBLISH-01`, `AC-PUBLISH-02`, `AC-PUBLISH-05` and
//! `AC-PUBLISH-06`. The suite is generic over [`DecisionSink`], so ordering
//! and the counter identity are proved per backend rather than assumed from
//! the one the unit tests happened to use.
#![expect(clippy::unwrap_used, reason = "test assertions")]

mod support;

use std::num::NonZeroUsize;
use std::os::unix::net::UnixDatagram;

use clave_decision::{MonotonicNanos, codec};
use clave_publish::{DecisionSink, InMemorySink, Publisher, UnixDatagramSink};

use crate::support::decision_for;

/// A sink plus whatever it takes to read back what the consumer received.
trait Backend: Sized {
    /// The sink under test.
    type Sink: DecisionSink;

    /// Returns the backend and the sink the publisher will own.
    fn create() -> (Self, Self::Sink);

    /// Reads whatever the consumer can read right now, so a test that
    /// publishes many decisions does not depend on the size of a kernel queue.
    fn pump(&mut self) {}

    /// Returns every frame the consumer has received so far, in order.
    fn delivered(&mut self, publisher: &Publisher<Self::Sink>) -> Vec<Vec<u8>>;
}

struct InMemoryBackend;

impl Backend for InMemoryBackend {
    type Sink = InMemorySink;

    fn create() -> (Self, Self::Sink) {
        (Self, InMemorySink::new())
    }

    fn delivered(&mut self, publisher: &Publisher<Self::Sink>) -> Vec<Vec<u8>> {
        publisher.sink().frames().to_vec()
    }
}

struct SocketBackend {
    consumer: UnixDatagram,
    frames: Vec<Vec<u8>>,
}

impl SocketBackend {
    fn drain_socket(&mut self) {
        let mut buffer = vec![0_u8; 8192];
        while let Ok(length) = self.consumer.recv(&mut buffer) {
            self.frames.push(buffer.get(..length).unwrap().to_vec());
        }
    }
}

impl Backend for SocketBackend {
    type Sink = UnixDatagramSink;

    fn pump(&mut self) {
        self.drain_socket();
    }

    fn create() -> (Self, Self::Sink) {
        let (sink, consumer) = UnixDatagramSink::pair().unwrap();
        consumer.set_nonblocking(true).unwrap();
        (
            Self {
                consumer,
                frames: Vec::new(),
            },
            sink,
        )
    }

    fn delivered(&mut self, _publisher: &Publisher<Self::Sink>) -> Vec<Vec<u8>> {
        self.drain_socket();
        self.frames.clone()
    }
}

/// AC-PUBLISH-01 and AC-PUBLISH-02: a consumer that keeps up receives every
/// decision once, in the order it was published.
fn each_decision_arrives_once_and_in_order<B: Backend>() {
    let (mut backend, sink) = B::create();
    let mut publisher = Publisher::with_capacity(sink, NonZeroUsize::new(8).unwrap());

    for object in 0_u64..64 {
        let report = publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap();
        assert!(report.delivered);
        backend.pump();
    }

    let frames = backend.delivered(&publisher);
    assert_eq!(frames.len(), 64);
    assert_eq!(publisher.counters().delivered, 64);
    assert_eq!(publisher.counters().published, 64);
    assert_eq!(publisher.queued_count(), 0);

    let objects: Vec<u64> = frames
        .iter()
        .map(|frame| codec::decode(frame).unwrap().object().get())
        .collect();
    assert_eq!(objects, (0_u64..64).collect::<Vec<_>>());
}

/// AC-PUBLISH-06: a decision whose window closed before the send is discarded
/// rather than delivered to a consumer that cannot act on it.
fn an_expired_decision_is_discarded_rather_than_delivered<B: Backend>() {
    let (mut backend, sink) = B::create();
    let mut publisher = Publisher::with_capacity(sink, NonZeroUsize::new(4).unwrap());

    let report = publisher
        .publish(&decision_for(1, 0), MonotonicNanos::new(250_000_001))
        .unwrap();

    assert!(!report.delivered);
    assert_eq!(report.counters.discarded_expired, 1);
    assert_eq!(report.counters.delivered, 0);
    assert!(backend.delivered(&publisher).is_empty());
}

/// AC-PUBLISH-05: the counter identity holds at every moment, whichever sink
/// is behind the seam.
fn the_counter_identity_holds_for_this_backend<B: Backend>() {
    let (mut backend, sink) = B::create();
    let mut publisher = Publisher::with_capacity(sink, NonZeroUsize::new(2).unwrap());

    for object in 0_u64..32 {
        let counters = publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap()
            .counters;
        let accounted = counters
            .delivered
            .saturating_add(counters.discarded_overflow)
            .saturating_add(counters.discarded_expired)
            .saturating_add(u64::try_from(publisher.queued_count()).unwrap());
        assert_eq!(counters.published, accounted);
        backend.pump();
    }
}

#[test]
fn the_in_memory_sink_delivers_each_decision_once_and_in_order() {
    each_decision_arrives_once_and_in_order::<InMemoryBackend>();
}

#[test]
fn the_socket_sink_delivers_each_decision_once_and_in_order() {
    each_decision_arrives_once_and_in_order::<SocketBackend>();
}

#[test]
fn the_in_memory_sink_never_sees_an_expired_decision() {
    an_expired_decision_is_discarded_rather_than_delivered::<InMemoryBackend>();
}

#[test]
fn the_socket_sink_never_sees_an_expired_decision() {
    an_expired_decision_is_discarded_rather_than_delivered::<SocketBackend>();
}

#[test]
fn the_in_memory_sink_keeps_the_counter_identity() {
    the_counter_identity_holds_for_this_backend::<InMemoryBackend>();
}

#[test]
fn the_socket_sink_keeps_the_counter_identity() {
    the_counter_identity_holds_for_this_backend::<SocketBackend>();
}

/// AC-PUBLISH-02: a socket in seqpacket-like datagram mode takes record
/// boundaries from the kernel, so a consumer reads one decision per read and
/// never has to reassemble a frame.
#[test]
fn one_read_returns_exactly_one_decision() {
    let (mut backend, sink) = SocketBackend::create();
    let mut publisher = Publisher::with_capacity(sink, NonZeroUsize::new(4).unwrap());

    publisher
        .publish(&decision_for(7, 0), MonotonicNanos::new(0))
        .unwrap();

    let frames = backend.delivered(&publisher);
    assert_eq!(frames.len(), 1);
    let frame = frames.first().unwrap();
    assert_eq!(codec::decode(frame).unwrap().object().get(), 7);
    assert_eq!(
        frame.len(),
        codec::encode(&decision_for(7, 0)).unwrap().len()
    );
}

/// AC-PUBLISH-05: a consumer that disconnects partway leaves the publisher
/// running, and the pipeline keeps producing rather than stalling.
#[test]
fn a_consumer_that_disconnects_does_not_stall_the_publisher() {
    let (sink, consumer) = UnixDatagramSink::pair().unwrap();
    let mut publisher = Publisher::with_capacity(sink, NonZeroUsize::new(2).unwrap());

    publisher
        .publish(&decision_for(1, 0), MonotonicNanos::new(0))
        .unwrap();
    drop(consumer);

    for object in 2_u64..32 {
        let report = publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap();
        assert!(!report.delivered);
    }

    let counters = publisher.counters();
    assert_eq!(counters.published, 31);
    assert_eq!(counters.delivered, 1);
    assert_eq!(counters.discarded_overflow, 28);
    assert_eq!(publisher.queued_count(), 2);
}
