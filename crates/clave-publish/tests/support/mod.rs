//! Shared fixtures for the delivery tests.

use clave_decision::{
    BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
    PickPose, PickWindow,
};

/// Returns a decision for `object`, reachable from `earliest` for 250 ms.
#[must_use]
pub(crate) fn decision_for(object: u64, earliest: i64) -> PickDecision {
    let latest = earliest.saturating_add(250_000_000);
    let window = PickWindow::new(MonotonicNanos::new(earliest), MonotonicNanos::new(latest))
        .unwrap_or_else(|error| unreachable!("{error}"));
    PickDecision::new(
        ObjectId::new(object),
        MaterialClass::Pet,
        ChannelId::new(3),
        PickPose::new(
            BeltPoint::new(0.4, -0.1, 0.03),
            1.0,
            MonotonicNanos::new(earliest),
        ),
        window,
        Confidence::new(0.9).unwrap_or_else(|error| unreachable!("{error}")),
    )
    .unwrap_or_else(|error| unreachable!("{error}"))
}
