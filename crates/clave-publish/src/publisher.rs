//! The bounded ring, the discard policy, the expiry check, and the counters.

use std::collections::VecDeque;
use std::num::NonZeroUsize;

use clave_decision::{MonotonicNanos, PickDecision, codec};

use crate::counters::{PublishCounters, PublishReport};
use crate::error::PublishError;
use crate::sink::{DecisionSink, SendOutcome};

/// How much room a recycled frame buffer keeps.
///
/// An encoded decision at contract version 1 is 215 bytes. The extra room
/// means a version that grows a field still fits without the buffer having to
/// reallocate on a hot path.
const FRAME_CAPACITY: usize = 512;

/// How the frame at the front of the ring leaves it, or fails to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FrameExit {
    /// Its window closed before it could be sent.
    Expired,
    /// The transport took it.
    Sent,
    /// The transport refused it, so it stays where it is.
    Blocked,
}

/// One encoded decision waiting for the transport.
#[derive(Debug)]
struct Frame {
    bytes: Vec<u8>,
    latest: MonotonicNanos,
    sequence: u64,
}

/// Queues encoded decisions and hands them to a sink, never blocking.
///
/// A frame leaves the ring in exactly one of three ways: the transport takes
/// it, a newer decision displaces it, or its window closes before it is sent.
/// Each way moves exactly one counter, so the identity in
/// [`PublishCounters`] holds at every moment.
///
/// The expiry check happens immediately before a send rather than on a timer,
/// so no clock thread exists and the check costs one comparison.
///
/// # Concurrency
///
/// A publisher is owned by one stage. Every call that moves a counter takes
/// `&mut self`, so the compiler rejects the shared mutation that would make
/// the counters disagree with what was actually sent.
///
/// # Allocation
///
/// The ring and its buffers are allocated once at construction. A frame that
/// leaves the ring returns its buffer to a pool and the next publication
/// encodes into it, so a steady state publication allocates nothing.
#[derive(Debug)]
pub struct Publisher<S> {
    sink: S,
    ring: VecDeque<Frame>,
    spares: Vec<Vec<u8>>,
    capacity: NonZeroUsize,
    counters: PublishCounters,
    next_sequence: u64,
}

impl<S: DecisionSink> Publisher<S> {
    /// Returns a publisher holding at most `capacity` undelivered decisions.
    ///
    /// The capacity cannot be zero, which the type enforces rather than a
    /// runtime check.
    #[must_use]
    pub fn with_capacity(sink: S, capacity: NonZeroUsize) -> Self {
        let room = capacity.get();
        let mut spares = Vec::with_capacity(room);
        for _ in 0..room {
            spares.push(Vec::with_capacity(FRAME_CAPACITY));
        }
        Self {
            sink,
            ring: VecDeque::with_capacity(room),
            spares,
            capacity,
            counters: PublishCounters::default(),
            next_sequence: 0,
        }
    }

    /// Publishes one decision and delivers whatever the transport will take.
    ///
    /// The decision is encoded and queued. When the ring is already full, the
    /// oldest undelivered decision is discarded to make room, because the
    /// newest decision is the one still worth acting on. The queue is then
    /// drained toward the sink until the sink refuses, and a decision whose
    /// window has already closed at `now` is discarded instead of sent.
    ///
    /// The call never blocks, whatever the consumer is doing.
    ///
    /// # Errors
    ///
    /// Returns [`PublishError::Encoding`] when the decision cannot be encoded,
    /// and [`PublishError::Transport`] when the sink fails in a way retrying
    /// cannot fix. A slow, absent, or departed consumer is neither.
    pub fn publish(
        &mut self,
        decision: &PickDecision,
        now: MonotonicNanos,
    ) -> Result<PublishReport, PublishError<S::Error>> {
        let buffer = self
            .spares
            .pop()
            .unwrap_or_else(|| Vec::with_capacity(FRAME_CAPACITY));
        let bytes = codec::encode_into(buffer, decision)?;

        let sequence = self.next_sequence;
        self.next_sequence = self.next_sequence.saturating_add(1);
        self.counters.published = self.counters.published.saturating_add(1);

        if self.ring.len() >= self.capacity.get()
            && let Some(oldest) = self.ring.pop_front()
        {
            self.counters.discarded_overflow = self.counters.discarded_overflow.saturating_add(1);
            self.recycle(oldest);
        }
        self.ring.push_back(Frame {
            bytes,
            latest: decision.window().latest(),
            sequence,
        });

        let delivered = self.drain(now, Some(sequence))?;
        Ok(PublishReport {
            delivered,
            counters: self.counters,
        })
    }

    /// Drains whatever the transport will take, without publishing anything.
    ///
    /// Returns how many decisions the transport took during this call.
    ///
    /// # Errors
    ///
    /// Returns [`PublishError::Transport`] when the sink fails in a way
    /// retrying cannot fix.
    pub fn flush(&mut self, now: MonotonicNanos) -> Result<usize, PublishError<S::Error>> {
        let before = self.counters.delivered;
        self.drain(now, None)?;
        let sent = self.counters.delivered.saturating_sub(before);
        Ok(usize::try_from(sent).unwrap_or(usize::MAX))
    }

    /// Returns the counters an operator reads.
    #[must_use]
    pub const fn counters(&self) -> PublishCounters {
        self.counters
    }

    /// Returns how many decisions are queued and undelivered.
    #[must_use]
    pub fn queued_count(&self) -> usize {
        self.ring.len()
    }

    /// Returns how many decisions the ring holds when it is full.
    #[must_use]
    pub const fn capacity(&self) -> NonZeroUsize {
        self.capacity
    }

    /// Returns the sink underneath.
    #[must_use]
    pub const fn sink(&self) -> &S {
        &self.sink
    }

    /// Returns the sink underneath, for a caller that has to reconfigure it.
    pub const fn sink_mut(&mut self) -> &mut S {
        &mut self.sink
    }

    /// Sends queued frames until the sink refuses or the ring empties.
    ///
    /// Returns whether the frame carrying `target` was sent during this call.
    fn drain(
        &mut self,
        now: MonotonicNanos,
        target: Option<u64>,
    ) -> Result<bool, PublishError<S::Error>> {
        let mut delivered_target = false;
        while let Some(front) = self.ring.front() {
            let sequence = front.sequence;
            let exit = if front.latest < now {
                FrameExit::Expired
            } else {
                match self.sink.try_send(&front.bytes) {
                    Ok(SendOutcome::Sent) => FrameExit::Sent,
                    Ok(SendOutcome::WouldBlock) => FrameExit::Blocked,
                    Err(error) => return Err(PublishError::Transport(error)),
                }
            };

            match exit {
                FrameExit::Expired => {
                    if let Some(expired) = self.ring.pop_front() {
                        self.counters.discarded_expired =
                            self.counters.discarded_expired.saturating_add(1);
                        self.recycle(expired);
                    }
                }
                FrameExit::Sent => {
                    if let Some(sent) = self.ring.pop_front() {
                        self.counters.delivered = self.counters.delivered.saturating_add(1);
                        self.recycle(sent);
                    }
                    if target == Some(sequence) {
                        delivered_target = true;
                    }
                }
                FrameExit::Blocked => break,
            }
        }
        Ok(delivered_target)
    }

    /// Returns a frame's buffer to the pool so the next encode reuses it.
    fn recycle(&mut self, frame: Frame) {
        let mut bytes = frame.bytes;
        bytes.clear();
        if self.spares.len() < self.capacity.get() {
            self.spares.push(bytes);
        }
    }
}
