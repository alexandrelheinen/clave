//! Delivers encoded pick decisions to one consumer, under a bounded and
//! counted overflow policy.
//!
//! The publisher encodes a decision, queues it in a ring sized at
//! construction, and hands it to a sink. It never blocks, on any path. When
//! the line runs faster than the consumer the oldest undelivered decision is
//! discarded to make room for the newest, and every discard moves a counter an
//! operator can read.
//!
//! This crate performs input and output and holds no estimation and no routing
//! policy. It depends on `clave-decision` for the message and on nothing else
//! in the workspace.
//!
//! # The latency budget
//!
//! Publication, meaning the span from handing a decision to
//! [`Publisher::publish`] until the transport has taken it, owns
//! 5 milliseconds at the 99th percentile.
//!
//! That budget is one share of the
//! 100 millisecond capture-to-delivery budget the whole path is measured
//! against. Capture, inference, and tracking own the rest, and none of them
//! is in this crate. The two budgets are [`PUBLICATION_BUDGET`] and
//! [`CAPTURE_TO_DELIVERY_BUDGET`], and `benches/publish.rs` measures against
//! the first and fails above it.
//!
//! No published source reports a 99th percentile for local delivery of a small
//! message, so the budget is held by measurement rather than by citation.
//! Nothing here has been measured on a target board: a green benchmark on a
//! development machine is evidence about that machine.
//!
//! # The transport
//!
//! [`UnixDatagramSink`] carries one encoded decision per datagram on an
//! `AF_UNIX` socket, which takes record boundaries from the kernel and
//! delivers them in order. The design calls for `SOCK_SEQPACKET`, and the
//! standard library exposes no way to open one without foreign function calls,
//! so this crate uses the datagram mode `std::os::unix::net` does expose. An
//! `AF_UNIX` datagram socket is reliable, ordered, and record oriented on
//! Linux, which is every property the choice rested on. The departure is
//! recorded in `docs/decisions.md`.
//!
//! # Hardened lint tier
//!
//! This crate sits on the capture-to-decision path, so it carries the hardened
//! lint tier from `standards/guidelines/languages/rs.md`. Cargo refuses to
//! merge an inherited lint table with a local one, so the crate manifest
//! repeats the workspace baseline beside the hardened tier.
//!
//! # Examples
//!
//! ```
//! use std::num::NonZeroUsize;
//!
//! use clave_decision::{
//!     BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
//!     PickPose, PickWindow,
//! };
//! use clave_publish::{DecisionSink, Publisher, SendOutcome};
//!
//! /// A consumer implements the seam itself when it needs a transport this
//! /// crate does not ship.
//! #[derive(Debug, Default)]
//! struct CountingSink {
//!     record_count: usize,
//! }
//!
//! impl DecisionSink for CountingSink {
//!     type Error = std::convert::Infallible;
//!
//!     fn try_send(&mut self, frame: &[u8]) -> Result<SendOutcome, Self::Error> {
//!         self.record_count += 1;
//!         let _ = frame;
//!         Ok(SendOutcome::Sent)
//!     }
//! }
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let window = PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(250_000_000))?;
//! let decision = PickDecision::new(
//!     ObjectId::new(1),
//!     MaterialClass::Pet,
//!     ChannelId::new(3),
//!     PickPose::new(BeltPoint::new(0.4, -0.1, 0.0), 0.0, MonotonicNanos::new(0)),
//!     window,
//!     Confidence::new(0.9)?,
//! )?;
//!
//! let mut publisher = Publisher::with_capacity(
//!     CountingSink::default(),
//!     NonZeroUsize::new(8).expect("eight is not zero"),
//! );
//! let report = publisher.publish(&decision, MonotonicNanos::new(0))?;
//!
//! assert!(report.delivered);
//! assert_eq!(report.counters.delivered, 1);
//! assert_eq!(publisher.sink().record_count, 1);
//! # Ok(())
//! # }
//! ```
#![forbid(unsafe_code)]

mod counters;
mod error;
#[cfg(feature = "test-support")]
mod fake;
mod latency;
mod publisher;
mod sink;
mod uds;

pub use crate::counters::{PublishCounters, PublishReport};
pub use crate::error::{PublishError, TransportError};
#[cfg(feature = "test-support")]
pub use crate::fake::{InMemorySink, SinkFault};
pub use crate::latency::{CAPTURE_TO_DELIVERY_BUDGET, LatencyReport, PUBLICATION_BUDGET};
pub use crate::publisher::Publisher;
pub use crate::sink::{DecisionSink, SendOutcome};
pub use crate::uds::UnixDatagramSink;
