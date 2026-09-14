//! What the wire encoding costs, which feeds the publication budget.
#![expect(
    clippy::expect_used,
    reason = "a benchmark that cannot build its fixture has nothing to measure"
)]

use clave_decision::{
    BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
    PickPose, PickWindow, codec,
};
use criterion::{Criterion, criterion_group, criterion_main};

fn sample_decision() -> PickDecision {
    let window = PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(250_000_000))
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

fn codec_costs(criterion: &mut Criterion) {
    let decision = sample_decision();
    let encoded = codec::encode(&decision).expect("the decision encodes");

    criterion.bench_function("encode_one_decision", |bencher| {
        bencher.iter(|| codec::encode(std::hint::black_box(&decision)));
    });
    criterion.bench_function("decode_one_decision", |bencher| {
        bencher.iter(|| codec::decode(std::hint::black_box(&encoded)));
    });
    criterion.bench_function("read_version_only", |bencher| {
        bencher.iter(|| codec::read_version(std::hint::black_box(&encoded)));
    });
}

criterion_group!(benches, codec_costs);
criterion_main!(benches);
