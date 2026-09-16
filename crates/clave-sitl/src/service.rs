//! One proposal in, one outcome out, and the counters a run reports.

use std::num::NonZeroUsize;

use clave_publish::{DecisionSink, Publisher};
use clave_routing::RejectReason;
use clave_safety::{Envelope, Proposal, Verdict};
use serde::Serialize;

use clave_routing::Resolver;

/// How many undelivered decisions the ring holds.
///
/// The runtime publishes at most one decision per captured frame, so the ring
/// exists to absorb a consumer that stalls rather than a burst.
const RING_CAPACITY: NonZeroUsize = match NonZeroUsize::new(64) {
    Some(value) => value,
    None => NonZeroUsize::MIN,
};

/// What a run did, counted rather than estimated.
///
/// The counts are disjoint: every proposal that arrives lands in exactly one
/// of accepted, rejected, overridden or refused, so a reader can add them and
/// get the proposal count back.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize)]
pub struct RunCounters {
    /// Datagrams that arrived, readable or not.
    pub proposals: u64,
    /// Proposals that passed every check and routed to a sorted channel.
    pub accepted: u64,
    /// Proposals that passed every check but fell below the confidence floor.
    pub rejected_low_confidence: u64,
    /// Proposals whose class the operator mapped to no channel.
    pub rejected_unmapped: u64,
    /// Proposals overridden because the point lies beyond the effector's reach.
    pub overridden_reach: u64,
    /// Proposals overridden because the point lies below the belt surface.
    pub overridden_belt_surface: u64,
    /// Proposals overridden because the point lies off the belt.
    pub overridden_belt_extent: u64,
    /// Proposals overridden because the point lies outside the spline stroke,
    /// either too close to the belt to extend to or too high to retract clear.
    pub overridden_stroke: u64,
    /// Datagrams that could not be read as a proposal at all.
    pub refused: u64,
    /// Decisions handed to the publisher.
    pub published: u64,
}

/// What the runtime did with one datagram, as the producer is told.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "verdict", rename_all = "snake_case")]
#[non_exhaustive]
pub enum Outcome {
    /// The geometry passed and a decision was published.
    Accepted {
        /// The object the proposal named.
        object_id: u64,
        /// The channel the routing policy resolved.
        channel: u16,
        /// Why the object was routed to reject, when it was.
        reject_reason: Option<&'static str>,
    },
    /// The geometry failed and nothing was published.
    Overridden {
        /// The check that failed.
        check: &'static str,
    },
    /// The datagram could not be read as a proposal.
    Refused {
        /// What the decoder reported.
        reason: String,
    },
}

/// The decision side of the runtime, with no socket in it.
///
/// Keeping the sockets out is what lets the whole decision path be exercised
/// in one process with no file system and no child process.
#[derive(Debug)]
pub struct Service<S> {
    envelope: Envelope,
    resolver: Resolver,
    publisher: Publisher<S>,
    counters: RunCounters,
}

impl<S: DecisionSink> Service<S> {
    /// Returns a service publishing into `sink`.
    #[must_use]
    pub fn new(envelope: Envelope, resolver: Resolver, sink: S) -> Self {
        Self {
            envelope,
            resolver,
            publisher: Publisher::with_capacity(sink, RING_CAPACITY),
            counters: RunCounters::default(),
        }
    }

    /// Returns what the run has counted so far.
    #[must_use]
    pub const fn counters(&self) -> RunCounters {
        self.counters
    }

    /// Returns the publisher, for a caller reading its delivery counters.
    #[must_use]
    pub const fn publisher(&self) -> &Publisher<S> {
        &self.publisher
    }

    /// Handles one datagram and returns what happened to it.
    ///
    /// Nothing here can fail out of the loop. An unreadable datagram, an
    /// unrecognized version and a transport that refuses a frame all produce
    /// an outcome the producer is told about, because a conveyor that stops on
    /// one bad message is worse than one that reports it.
    pub fn handle(&mut self, payload: &[u8]) -> Outcome {
        self.counters.proposals = self.counters.proposals.saturating_add(1);
        let proposal = match Proposal::decode(payload) {
            Ok(proposal) => proposal,
            Err(error) => {
                self.counters.refused = self.counters.refused.saturating_add(1);
                return Outcome::Refused {
                    reason: error.to_string(),
                };
            }
        };
        match self.envelope.judge(&proposal, &self.resolver) {
            Ok(verdict) => self.record(&proposal, verdict),
            Err(error) => {
                self.counters.refused = self.counters.refused.saturating_add(1);
                Outcome::Refused {
                    reason: error.to_string(),
                }
            }
        }
    }

    /// Counts one verdict and publishes the decision it carries.
    fn record(&mut self, proposal: &Proposal, verdict: Verdict) -> Outcome {
        match verdict {
            Verdict::Overridden { check } => {
                match check {
                    clave_safety::Check::Reach => {
                        self.counters.overridden_reach =
                            self.counters.overridden_reach.saturating_add(1);
                    }
                    clave_safety::Check::BeltSurface => {
                        self.counters.overridden_belt_surface =
                            self.counters.overridden_belt_surface.saturating_add(1);
                    }
                    clave_safety::Check::BeltExtent => {
                        self.counters.overridden_belt_extent =
                            self.counters.overridden_belt_extent.saturating_add(1);
                    }
                    clave_safety::Check::Stroke => {
                        self.counters.overridden_stroke =
                            self.counters.overridden_stroke.saturating_add(1);
                    }
                }
                Outcome::Overridden {
                    check: check.name(),
                }
            }
            Verdict::Accepted { decision, routed } => {
                let reason = match routed.reject_reason() {
                    None => {
                        self.counters.accepted = self.counters.accepted.saturating_add(1);
                        None
                    }
                    Some(RejectReason::BelowThreshold) => {
                        self.counters.rejected_low_confidence =
                            self.counters.rejected_low_confidence.saturating_add(1);
                        Some("below_threshold")
                    }
                    Some(RejectReason::UnmappedClass) => {
                        self.counters.rejected_unmapped =
                            self.counters.rejected_unmapped.saturating_add(1);
                        Some("unmapped_class")
                    }
                };
                // The publisher discards a decision whose window has already
                // closed, and it needs a reading of the same monotonic clock
                // the window came from to tell. That clock belongs to the
                // producer, so the instant the proposal was captured is what
                // is passed rather than a reading taken here under a different
                // epoch.
                let now = proposal.pose().reference_time();
                if self.publisher.publish(&decision, now).is_ok() {
                    self.counters.published = self.counters.published.saturating_add(1);
                }
                Outcome::Accepted {
                    object_id: decision.object().get(),
                    channel: decision.channel().get(),
                    reject_reason: reason,
                }
            }
        }
    }
}
