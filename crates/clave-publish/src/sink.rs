//! The transport seam: one narrow trait, non-blocking by contract.

/// What a sink did with one frame.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SendOutcome {
    /// The transport took the whole record.
    Sent,
    /// The transport took nothing and the caller still owns the frame. A
    /// consumer that is slow, absent, or gone reports this rather than an
    /// error, so the discard policy decides what happens next.
    WouldBlock,
}

/// Somewhere one encoded decision can go.
///
/// The trait takes an encoded frame rather than a decision, so the schema
/// stays on the contract side of the seam and changing the transport never
/// touches the message type.
///
/// A sink must not block. A sink that waits converts backpressure into a
/// pipeline stall, which is the failure the overflow policy exists to
/// prevent. This is a clause of the trait rather than an accident of one
/// implementation.
pub trait DecisionSink {
    /// What this transport fails with, outside the refusals it absorbs.
    type Error: std::error::Error + Send + Sync + 'static;

    /// Offers one complete encoded decision to the transport.
    ///
    /// Returns [`SendOutcome::Sent`] when the transport took the whole record
    /// and [`SendOutcome::WouldBlock`] when it took nothing. A partial record
    /// is never delivered.
    ///
    /// # Errors
    ///
    /// Returns [`Self::Error`] when the transport failed in a way retrying
    /// cannot fix. A slow, absent, or departed consumer is not an error.
    fn try_send(&mut self, frame: &[u8]) -> Result<SendOutcome, Self::Error>;
}
