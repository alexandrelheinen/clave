//! The one error type the routing policy returns.

use clave_decision::MaterialClass;

/// An operator-supplied channel mapping the resolver refuses to load.
///
/// Every variant here is a misconfiguration caught when the mapping is loaded
/// rather than when the first object arrives, because a line that starts and
/// then misroutes is worse than a line that refuses to start.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[non_exhaustive]
pub enum RoutingError {
    /// The same material class is mapped more than once, so which channel the
    /// operator meant cannot be recovered.
    #[error("material class {} is mapped more than once", .class.taxonomy_id())]
    DuplicateClass {
        /// The class that appears more than once.
        class: MaterialClass,
    },

    /// The residue class is mapped somewhere other than the reject channel.
    /// The taxonomy fixes residue to the reject channel, and the reject rule
    /// depends on exactly one reject channel existing.
    #[error(
        "the residue class is mapped to channel {channel} rather than to the reject channel \
         {reject}"
    )]
    ResidueNotRejected {
        /// The channel the mapping named for residue.
        channel: u16,
        /// The reject channel the mapping was built with.
        reject: u16,
    },

    /// The same channel is priced more than once, so which row the operator
    /// meant cannot be recovered.
    #[error("channel {channel} is priced more than once")]
    DuplicateChannel {
        /// The channel that appears more than once.
        channel: u16,
    },

    /// A channel the map names has no cost row.
    #[error("the cost table has no row for channel {channel}")]
    MissingCostRow {
        /// The channel that is missing.
        channel: u16,
    },

    /// A cost row names a channel the map does not.
    #[error("the cost table prices channel {channel}, which the channel map does not name")]
    UnknownCostChannel {
        /// The channel that is not in the map.
        channel: u16,
    },

    /// A cost is negative or not finite.
    #[error("channel {channel} holds a cost that is negative or not finite")]
    InvalidCost {
        /// The channel whose row is unusable.
        channel: u16,
    },

    /// A sorted channel prices residue below the reject channel, so expected
    /// cost could route residue off the reject channel the taxonomy fixes.
    #[error("channel {channel} prices residue cheaper than the reject channel {reject}")]
    ResidueCheaperThanReject {
        /// The sorted channel that undercuts reject.
        channel: u16,
        /// The reject channel the table was built with.
        reject: u16,
    },
}
