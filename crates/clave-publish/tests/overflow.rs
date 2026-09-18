//! What the publisher does when the line runs faster than the consumer.
#![expect(clippy::unwrap_used, reason = "test assertions")]

mod support;

use std::num::NonZeroUsize;

use clave_decision::{MonotonicNanos, codec};
use clave_publish::{InMemorySink, PublishError, Publisher};
use proptest::prelude::*;

use crate::support::decision_for;

fn capacity(value: usize) -> NonZeroUsize {
    NonZeroUsize::new(value).unwrap()
}

/// A full queue loses its oldest undelivered decision to make
/// room, because the newest decision is the one still worth acting on.
#[test]
fn a_full_queue_discards_its_oldest_undelivered_decision() {
    let mut publisher = Publisher::with_capacity(InMemorySink::refusing(), capacity(2));

    for object in 1_u64..=3 {
        publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap();
    }
    publisher.sink_mut().accept();
    publisher.flush(MonotonicNanos::new(0)).unwrap();

    let objects: Vec<u64> = publisher
        .sink()
        .frames()
        .iter()
        .map(|frame| codec::decode(frame).unwrap().object().get())
        .collect();
    assert_eq!(objects, vec![2, 3]);
}

/// Every discard moves a counter an operator can read, and a
/// rising overflow count is a line running faster than its consumer.
#[test]
fn a_discarded_decision_is_counted_where_an_operator_can_read_it() {
    let mut publisher = Publisher::with_capacity(InMemorySink::refusing(), capacity(4));

    for object in 1_u64..=10 {
        publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap();
    }

    let counters = publisher.counters();
    assert_eq!(counters.published, 10);
    assert_eq!(counters.discarded_overflow, 6);
    assert_eq!(counters.discarded_expired, 0);
    assert_eq!(counters.delivered, 0);
    assert_eq!(publisher.queued_count(), 4);
}

/// An expired decision moves its own counter, so an operator
/// can tell a line that is overloaded from a line that is too slow to reach.
#[test]
fn an_expired_decision_is_counted_apart_from_an_overflowed_one() {
    let mut publisher = Publisher::with_capacity(InMemorySink::new(), capacity(4));

    let report = publisher
        .publish(&decision_for(1, 0), MonotonicNanos::new(250_000_001))
        .unwrap();

    assert!(!report.delivered);
    assert_eq!(report.counters.discarded_expired, 1);
    assert_eq!(report.counters.discarded_overflow, 0);
    assert!(publisher.sink().frames().is_empty());
}

/// A decision that waited in the queue until its window closed
/// is discarded at the moment it would have been sent, not on a timer.
#[test]
fn a_queued_decision_whose_window_closes_while_it_waits_is_discarded() {
    let mut publisher = Publisher::with_capacity(InMemorySink::refusing(), capacity(4));

    publisher
        .publish(&decision_for(1, 0), MonotonicNanos::new(0))
        .unwrap();
    publisher.sink_mut().accept();
    let flushed = publisher.flush(MonotonicNanos::new(250_000_001)).unwrap();

    assert_eq!(flushed, 0);
    assert_eq!(publisher.counters().discarded_expired, 1);
    assert!(publisher.sink().frames().is_empty());
}

/// With no consumer reachable the publisher keeps producing and
/// discarding under the same policy, and no call blocks.
#[test]
fn no_reachable_consumer_does_not_stall_the_pipeline() {
    let mut publisher = Publisher::with_capacity(InMemorySink::refusing(), capacity(3));

    for object in 1_u64..=1_000 {
        let report = publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap();
        assert!(!report.delivered);
    }

    let counters = publisher.counters();
    assert_eq!(counters.published, 1_000);
    assert_eq!(counters.discarded_overflow, 997);
    assert_eq!(publisher.queued_count(), 3);
}

/// A consumer that starts reading again drains the queue, and
/// what it gets is the newest decisions rather than the stalest ones.
#[test]
fn a_consumer_that_resumes_reading_gets_the_newest_decisions() {
    let mut publisher = Publisher::with_capacity(InMemorySink::refusing(), capacity(3));

    for object in 1_u64..=10 {
        publisher
            .publish(&decision_for(object, 0), MonotonicNanos::new(0))
            .unwrap();
    }
    publisher.sink_mut().accept();
    let flushed = publisher.flush(MonotonicNanos::new(0)).unwrap();

    assert_eq!(flushed, 3);
    let objects: Vec<u64> = publisher
        .sink()
        .frames()
        .iter()
        .map(|frame| codec::decode(frame).unwrap().object().get())
        .collect();
    assert_eq!(objects, vec![8, 9, 10]);
    assert_eq!(publisher.queued_count(), 0);
}

/// Backpressure is not an error, but a transport broken in a
/// way a retry cannot fix is, and it reaches the caller without stalling.
#[test]
fn a_broken_transport_reaches_the_caller_as_an_error() {
    let mut publisher = Publisher::with_capacity(InMemorySink::faulting(), capacity(2));

    let error = publisher
        .publish(&decision_for(1, 0), MonotonicNanos::new(0))
        .unwrap_err();

    assert!(matches!(error, PublishError::Transport(_)));
    assert_eq!(publisher.counters().published, 1);
    assert_eq!(publisher.queued_count(), 1);
}

/// A queue of one still discards the oldest rather than
/// refusing the newest, which is the smallest case of the same policy.
#[test]
fn a_queue_of_one_still_discards_the_oldest() {
    let mut publisher = Publisher::with_capacity(InMemorySink::refusing(), capacity(1));

    publisher
        .publish(&decision_for(1, 0), MonotonicNanos::new(0))
        .unwrap();
    publisher
        .publish(&decision_for(2, 0), MonotonicNanos::new(0))
        .unwrap();
    publisher.sink_mut().accept();
    publisher.flush(MonotonicNanos::new(0)).unwrap();

    let objects: Vec<u64> = publisher
        .sink()
        .frames()
        .iter()
        .map(|frame| codec::decode(frame).unwrap().object().get())
        .collect();
    assert_eq!(objects, vec![2]);
}

proptest! {
    /// Across an arbitrary sequence of
    /// publications and consumer stalls, what was published equals what was
    /// delivered plus what was discarded either way plus what is still queued.
    #[test]
    fn the_counter_identity_holds_over_an_arbitrary_publish_sequence(
        ring_capacity in 1_usize..8,
        steps in prop::collection::vec((0_u64..4, 0_i64..500_000_000), 1..64),
    ) {
        let mut publisher =
            Publisher::with_capacity(InMemorySink::new(), NonZeroUsize::new(ring_capacity).unwrap());

        for (index, (action, now)) in steps.into_iter().enumerate() {
            match action {
                0 => publisher.sink_mut().refuse(),
                1 => publisher.sink_mut().accept(),
                _ => {}
            }
            let object = u64::try_from(index).unwrap();
            let counters = publisher
                .publish(&decision_for(object, 0), MonotonicNanos::new(now))
                .unwrap()
                .counters;

            let accounted = counters
                .delivered
                .saturating_add(counters.discarded_overflow)
                .saturating_add(counters.discarded_expired)
                .saturating_add(u64::try_from(publisher.queued_count()).unwrap());
            prop_assert_eq!(counters.published, accounted);
            prop_assert!(publisher.queued_count() <= ring_capacity);
        }
    }
}
