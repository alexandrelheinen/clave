//! The publication budget and the measurement that holds it.
//!
//! Covers `AC-LATENCY-01`, `AC-LATENCY-02`, `AC-LATENCY-03` and
//! `AC-LATENCY-04`.
//!
//! Every number this file produces is a development machine number. There is
//! no camera, no belt, and no target board here, so a green run is evidence
//! about this machine and about nothing else.
#![expect(clippy::unwrap_used, reason = "test assertions")]

mod support;

use std::num::NonZeroUsize;
use std::time::{Duration, Instant};

use clave_decision::MonotonicNanos;
use clave_publish::{
    CAPTURE_TO_DELIVERY_BUDGET, LatencyReport, PUBLICATION_BUDGET, Publisher, UnixDatagramSink,
};

use crate::support::decision_for;

const CRATE_DOCS: &str = include_str!("../src/lib.rs");

/// AC-LATENCY-02: the publication budget is documented as a share of the
/// capture-to-delivery budget it belongs to, rather than as a number on its
/// own.
#[test]
fn the_publication_budget_is_a_share_of_the_capture_to_delivery_budget() {
    assert_eq!(PUBLICATION_BUDGET, Duration::from_millis(5));
    assert_eq!(CAPTURE_TO_DELIVERY_BUDGET, Duration::from_millis(100));
    assert!(PUBLICATION_BUDGET < CAPTURE_TO_DELIVERY_BUDGET);
    assert!(CRATE_DOCS.contains("5 millisecond"));
    assert!(CRATE_DOCS.contains("100 millisecond"));
}

/// AC-LATENCY-03: the report names the 99th percentile by nearest rank, which
/// is the number the budget is stated at.
#[test]
fn the_report_names_the_ninety_ninth_percentile_by_nearest_rank() {
    let mut samples: Vec<Duration> = (1_u64..=100).map(Duration::from_micros).collect();

    let report = LatencyReport::from_samples(&mut samples).unwrap();

    assert_eq!(report.sample_count(), 100);
    assert_eq!(report.p99(), Duration::from_micros(99));
    assert_eq!(report.worst(), Duration::from_micros(100));
    assert_eq!(report.median(), Duration::from_micros(50));
}

/// AC-LATENCY-03: the report sorts what it is given, so a caller may hand it
/// samples in the order they were measured.
#[test]
fn the_report_does_not_depend_on_the_order_samples_arrive_in() {
    let mut ascending: Vec<Duration> = (1_u64..=1_000).map(Duration::from_nanos).collect();
    let mut descending: Vec<Duration> = (1_u64..=1_000).rev().map(Duration::from_nanos).collect();

    let from_ascending = LatencyReport::from_samples(&mut ascending).unwrap();
    let from_descending = LatencyReport::from_samples(&mut descending).unwrap();

    assert_eq!(from_ascending, from_descending);
    assert_eq!(from_ascending.p99(), Duration::from_nanos(990));
}

/// AC-LATENCY-03: a single sample is still a distribution, and an empty run is
/// no measurement at all rather than a passing one.
#[test]
fn one_sample_reports_itself_and_no_sample_reports_nothing() {
    let mut one = vec![Duration::from_millis(1)];
    let report = LatencyReport::from_samples(&mut one).unwrap();

    assert_eq!(report.p99(), Duration::from_millis(1));
    assert_eq!(report.sample_count(), 1);
    assert!(LatencyReport::from_samples(&mut []).is_none());
}

/// AC-LATENCY-04: a measurement above the budget is over budget, so a
/// benchmark that reports it fails instead of printing a number and passing.
#[test]
fn a_measurement_above_the_budget_is_over_budget() {
    let mut fast = vec![Duration::from_micros(10); 100];
    let mut slow = vec![Duration::from_micros(10); 90];
    slow.resize(
        100,
        PUBLICATION_BUDGET.saturating_add(Duration::from_nanos(1)),
    );

    assert!(
        LatencyReport::from_samples(&mut fast)
            .unwrap()
            .within_budget()
    );
    assert!(
        !LatencyReport::from_samples(&mut slow)
            .unwrap()
            .within_budget()
    );
}

/// AC-LATENCY-04: a measurement exactly at the budget is inside it, so the
/// budget is a ceiling rather than a strict bound.
#[test]
fn a_measurement_exactly_at_the_budget_is_inside_it() {
    let mut samples = vec![PUBLICATION_BUDGET; 10];

    assert!(
        LatencyReport::from_samples(&mut samples)
            .unwrap()
            .within_budget()
    );
}

/// AC-LATENCY-01: publication to a connected consumer stays inside the 5
/// millisecond budget at the 99th percentile on this machine.
#[test]
fn publication_to_a_connected_consumer_stays_inside_the_budget() {
    let (sink, consumer) = UnixDatagramSink::pair().unwrap();
    consumer.set_nonblocking(true).unwrap();
    let mut publisher = Publisher::with_capacity(sink, NonZeroUsize::new(16).unwrap());
    let mut samples = Vec::with_capacity(2_000);
    let mut buffer = vec![0_u8; 8192];

    for object in 0_u64..2_000 {
        let decision = decision_for(object, 0);
        let started = Instant::now();
        let report = publisher
            .publish(&decision, MonotonicNanos::new(0))
            .unwrap();
        samples.push(started.elapsed());
        assert!(report.delivered);
        while consumer.recv(&mut buffer).is_ok() {}
    }

    let report = LatencyReport::from_samples(&mut samples).unwrap();
    println!("publication latency on this machine: {report}");
    assert!(
        report.within_budget(),
        "publication p99 {:?} exceeds the {:?} budget",
        report.p99(),
        PUBLICATION_BUDGET
    );
}
