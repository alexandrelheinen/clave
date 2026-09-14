//! The publication budget and the shape of a measurement against it.

use std::fmt;
use std::time::Duration;

/// The budget for publication, measured at the 99th percentile.
///
/// Publication is the span from handing a decision to the publisher until the
/// transport has taken it. It is one share of
/// [`CAPTURE_TO_DELIVERY_BUDGET`].
pub const PUBLICATION_BUDGET: Duration = Duration::from_millis(5);

/// The budget for the whole path from capture to delivery, measured at the
/// 99th percentile.
///
/// Publication owns 5 milliseconds of this 100 millisecond budget. The rest
/// belongs to capture, inference, and tracking, which this crate does not
/// touch.
pub const CAPTURE_TO_DELIVERY_BUDGET: Duration = Duration::from_millis(100);

/// What a run of publication measurements says about the budget.
///
/// A system that averages well and misses one publication in a hundred still
/// drops that object on the floor, so the number the budget is stated at is a
/// percentile and never a mean.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LatencyReport {
    sample_count: usize,
    median: Duration,
    p99: Duration,
    worst: Duration,
}

impl LatencyReport {
    /// Summarizes a run of measurements, sorting `samples` in place.
    ///
    /// Returns `None` for an empty run, because no measurement is not a
    /// passing measurement.
    #[must_use]
    pub fn from_samples(samples: &mut [Duration]) -> Option<Self> {
        if samples.is_empty() {
            return None;
        }
        samples.sort_unstable();
        let last = samples.len().saturating_sub(1);
        let median_at = last.checked_div(2).unwrap_or(0);
        let p99_at = nearest_rank(samples.len(), 99).min(last);

        Some(Self {
            sample_count: samples.len(),
            median: *samples.get(median_at)?,
            p99: *samples.get(p99_at)?,
            worst: *samples.get(last)?,
        })
    }

    /// Returns how many measurements this report covers.
    #[must_use]
    pub const fn sample_count(self) -> usize {
        self.sample_count
    }

    /// Returns the median measurement.
    #[must_use]
    pub const fn median(self) -> Duration {
        self.median
    }

    /// Returns the 99th percentile measurement, by nearest rank.
    #[must_use]
    pub const fn p99(self) -> Duration {
        self.p99
    }

    /// Returns the slowest measurement in the run.
    #[must_use]
    pub const fn worst(self) -> Duration {
        self.worst
    }

    /// Returns whether the 99th percentile sits inside
    /// [`PUBLICATION_BUDGET`], which is the condition a benchmark fails on.
    #[must_use]
    pub const fn within_budget(self) -> bool {
        self.p99.as_nanos() <= PUBLICATION_BUDGET.as_nanos()
    }
}

impl fmt::Display for LatencyReport {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} samples, median {:?}, p99 {:?}, worst {:?}, budget {:?}",
            self.sample_count, self.median, self.p99, self.worst, PUBLICATION_BUDGET
        )
    }
}

/// Returns the zero-based index of the nearest-rank percentile.
///
/// The nearest rank of percentile `p` over `sample_count` samples is
/// `ceil(p * sample_count / 100)`, counted from one, so the index is one less.
fn nearest_rank(sample_count: usize, percentile: usize) -> usize {
    sample_count
        .saturating_mul(percentile)
        .saturating_add(99)
        .checked_div(100)
        .unwrap_or(0)
        .saturating_sub(1)
}
