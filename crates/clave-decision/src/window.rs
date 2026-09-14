//! The time reference and the window during which an object is reachable.

use crate::error::ContractError;

/// A point on the system monotonic clock, in nanoseconds.
///
/// The reference is the Linux system monotonic clock, shared between processes
/// on one machine and meaningful within one boot. A reading cannot jump
/// backward when the wall clock is corrected. A consumer on another machine
/// cannot interpret one of these, which is why moving a consumer off the
/// machine is a contract question rather than a deployment detail.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct MonotonicNanos(i64);

impl MonotonicNanos {
    /// Returns the instant at this many nanoseconds on the monotonic clock.
    #[must_use]
    pub const fn new(value: i64) -> Self {
        Self(value)
    }

    /// Returns the reading in nanoseconds.
    #[must_use]
    pub const fn get(self) -> i64 {
        self.0
    }
}

/// The interval during which an object is reachable by the effector.
///
/// The window is bounded by belt speed and effector reach. An object not
/// picked before the window closes continues down the belt, which is a
/// throughput loss rather than a misroute.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PickWindow {
    earliest: MonotonicNanos,
    latest: MonotonicNanos,
}

impl PickWindow {
    /// Returns the window running from `earliest` to `latest`, both inclusive.
    ///
    /// # Errors
    ///
    /// Returns [`ContractError::WindowNotOrdered`] when `latest` falls before
    /// `earliest`, which names no reachable interval.
    pub fn new(earliest: MonotonicNanos, latest: MonotonicNanos) -> Result<Self, ContractError> {
        if latest < earliest {
            return Err(ContractError::WindowNotOrdered {
                earliest: earliest.get(),
                latest: latest.get(),
            });
        }
        Ok(Self { earliest, latest })
    }

    /// Returns the earliest instant at which the object is reachable.
    #[must_use]
    pub const fn earliest(self) -> MonotonicNanos {
        self.earliest
    }

    /// Returns the latest instant at which the object is reachable.
    #[must_use]
    pub const fn latest(self) -> MonotonicNanos {
        self.latest
    }

    /// Returns whether `instant` falls inside the window, both edges included.
    #[must_use]
    pub fn contains(self, instant: MonotonicNanos) -> bool {
        (self.earliest..=self.latest).contains(&instant)
    }

    /// Returns whether the window has already closed at `now`.
    ///
    /// A decision whose window has closed is one no consumer can act on, so
    /// the publisher discards it rather than delivering it.
    #[must_use]
    pub fn has_closed_by(self, now: MonotonicNanos) -> bool {
        self.latest < now
    }
}
