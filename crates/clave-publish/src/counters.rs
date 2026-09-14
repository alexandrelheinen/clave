//! What an operator reads to tell a healthy line from an overloaded one.

/// The four counts that describe everything the publisher has done.
///
/// The identity `published == delivered + discarded_overflow +
/// discarded_expired + queued` holds at every moment, where `queued` is
/// [`Publisher::queued_count`]. A frame leaves the ring in exactly one of
/// three ways and each way moves exactly one of these counts.
///
/// A rising `discarded_overflow` is a line running faster than its consumer. A
/// rising `discarded_expired` is a line whose objects pass out of reach before
/// anybody can act on them. The two have different causes and different fixes,
/// which is why they are counted apart.
///
/// [`Publisher::queued_count`]: crate::Publisher::queued_count
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct PublishCounters {
    /// How many decisions were handed to the publisher.
    pub published: u64,
    /// How many decisions the transport took.
    pub delivered: u64,
    /// How many decisions were dropped to make room for a newer one.
    pub discarded_overflow: u64,
    /// How many decisions were dropped because their window had closed.
    pub discarded_expired: u64,
}

/// What one call to publish did, and where the counters stand after it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PublishReport {
    /// Whether the transport took this decision during this call. A decision
    /// that stayed queued may still be delivered by a later call.
    pub delivered: bool,
    /// The counters after this call.
    pub counters: PublishCounters,
}
