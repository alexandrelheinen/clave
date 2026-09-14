//! The error types delivery returns.

use clave_decision::ContractError;

/// A publication that failed for a reason the policy cannot absorb.
///
/// Backpressure is deliberately absent from this enumeration. A slow, absent,
/// or departed consumer is reported as [`SendOutcome::WouldBlock`] and handled
/// by the discard policy, because treating a slow consumer as a failure is
/// what stalls a pipeline.
///
/// [`SendOutcome::WouldBlock`]: crate::SendOutcome::WouldBlock
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum PublishError<E>
where
    E: std::error::Error + Send + Sync + 'static,
{
    /// The decision could not be encoded, so nothing was queued.
    #[error("the decision could not be encoded for the wire")]
    Encoding(#[from] ContractError),

    /// The transport failed in a way retrying cannot fix. The frame stays
    /// queued and the counters stay consistent.
    #[error("the transport failed in a way a retry cannot fix")]
    Transport(#[source] E),
}

/// A Unix socket that failed outside the cases the discard policy absorbs.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum TransportError {
    /// The kernel took part of a record. A datagram socket should never do
    /// this, and a consumer reading a truncated decision would act on garbage.
    #[error("the socket accepted {written} bytes of a {expected} byte record")]
    PartialRecord {
        /// How many bytes the kernel took.
        written: usize,
        /// How many bytes the record holds.
        expected: usize,
    },

    /// The socket failed for a reason that is not a refusal.
    #[error("the socket rejected a complete record")]
    Socket(#[from] std::io::Error),
}
