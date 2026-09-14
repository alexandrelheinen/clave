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
}
