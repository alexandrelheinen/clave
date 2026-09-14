//! The publication budget, measured rather than assumed.
//!
//! The benchmark records one duration per publication over a real socket,
//! reports the 99th percentile beside the median, and ends the run non-zero
//! when the 99th percentile sits above the budget. Reporting the number and
//! passing anyway would make the budget decorative.
//!
//! Every number this benchmark prints is a development machine number. There
//! is no camera, no belt, and no target board here, so a green run is evidence
//! about this machine and about nothing else. Requirement 4 is not met until
//! the same measurement is taken on the board the line runs.
#![expect(
    clippy::expect_used,
    reason = "a benchmark that cannot build its fixture has nothing to measure"
)]

use std::num::NonZeroUsize;
use std::time::{Duration, Instant};

use clave_decision::{
    BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
    PickPose, PickWindow,
};
use clave_publish::{LatencyReport, PUBLICATION_BUDGET, Publisher, UnixDatagramSink};
use criterion::{Criterion, criterion_group, criterion_main};

fn sample_decision() -> PickDecision {
    let window = PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(i64::MAX))
        .expect("the window is ordered");
    PickDecision::new(
        ObjectId::new(4_815_162_342),
        MaterialClass::Pet,
        ChannelId::new(3),
        PickPose::new(
            BeltPoint::new(0.412, -0.085, 0.031),
            1.047,
            MonotonicNanos::new(100_000_000),
        ),
        window,
        Confidence::new(0.94).expect("the confidence is in range"),
    )
    .expect("the pose is timed inside the window")
}

fn publication_latency(criterion: &mut Criterion) {
    let (sink, consumer) = UnixDatagramSink::pair().expect("the socket pair opens");
    consumer
        .set_nonblocking(true)
        .expect("the consumer goes non-blocking");
    let mut publisher =
        Publisher::with_capacity(sink, NonZeroUsize::new(16).expect("sixteen is not zero"));
    let decision = sample_decision();
    let now = MonotonicNanos::new(0);
    let mut samples: Vec<Duration> = Vec::with_capacity(100_000);
    let mut buffer = vec![0_u8; 8192];

    criterion.bench_function("publish_one_decision_over_a_socket", |bencher| {
        bencher.iter_custom(|iterations| {
            let mut total = Duration::ZERO;
            for _ in 0..iterations {
                let started = Instant::now();
                let report = publisher
                    .publish(&decision, now)
                    .expect("the publication succeeds");
                let elapsed = started.elapsed();
                assert!(report.delivered, "the consumer kept up");
                total = total.saturating_add(elapsed);
                samples.push(elapsed);
                while consumer.recv(&mut buffer).is_ok() {}
            }
            total
        });
    });

    let report =
        LatencyReport::from_samples(&mut samples).expect("the benchmark took measurements");
    println!("publication latency on this machine: {report}");
    assert!(
        report.within_budget(),
        "publication p99 {:?} exceeds the {PUBLICATION_BUDGET:?} budget",
        report.p99()
    );
}

criterion_group!(benches, publication_latency);
criterion_main!(benches);
