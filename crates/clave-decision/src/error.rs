//! The one error type every fallible call in this crate returns.

/// A decision, or a set of bytes claiming to be one, that the contract refuses.
///
/// Variants name the failure rather than the call that produced it, so a
/// caller branches on what went wrong and not on where.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
#[non_exhaustive]
pub enum ContractError {
    /// The window ends before it starts, so it names no reachable interval.
    #[error("pick window runs from {earliest} to {latest}, which ends before it starts")]
    WindowNotOrdered {
        /// The earliest monotonic nanosecond the window named.
        earliest: i64,
        /// The latest monotonic nanosecond the window named.
        latest: i64,
    },

    /// The confidence is not a finite number in the inclusive range 0.0 to 1.0.
    #[error("confidence {value} is not a finite number between 0.0 and 1.0 inclusive")]
    ConfidenceOutOfRange {
        /// The value that was offered as a confidence.
        value: f32,
    },

    /// The pose is timed outside the window, so it does not describe where the
    /// object will be when the effector arrives.
    #[error("pose reference time {reference_time} falls outside the window {earliest} to {latest}")]
    PoseOutsideWindow {
        /// The monotonic nanosecond the pose was estimated for.
        reference_time: i64,
        /// The earliest monotonic nanosecond the window named.
        earliest: i64,
        /// The latest monotonic nanosecond the window named.
        latest: i64,
    },

    /// The message carries a contract version this build does not speak. The
    /// whole message is refused, so no field past the version is read.
    #[error("contract version {found} is not the version {expected} this build speaks")]
    UnknownVersion {
        /// The version the message carried.
        found: u64,
        /// The version this build speaks.
        expected: u16,
    },

    /// The bytes are not a decision at all.
    #[error("the encoded decision is malformed: {reason}")]
    Malformed {
        /// What the decoder expected to find and did not.
        reason: &'static str,
    },

    /// The encoder could not reserve room for the encoded decision.
    #[error("the encoder could not reserve memory for the encoded decision")]
    EncodeBufferExhausted,
}
