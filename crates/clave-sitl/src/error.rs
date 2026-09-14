//! The one error type this crate returns.

/// Something the runtime could not do before it started deciding.
///
/// Nothing in this enum describes a bad proposal. A proposal nobody can read
/// is reported as an outcome and the loop continues, because one unreadable
/// datagram is not a reason to stop a conveyor.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum RuntimeError {
    /// A file the runtime needs could not be read.
    #[error("{path} could not be read: {reason}")]
    Unreadable {
        /// The path that was tried.
        path: String,
        /// What the operating system reported.
        reason: String,
    },

    /// The configuration does not describe a runnable line.
    #[error("the runtime configuration is unusable: {reason}")]
    Config {
        /// What is wrong with it.
        reason: String,
    },

    /// A socket could not be bound, connected, or read.
    #[error("the {role} socket failed: {reason}")]
    Socket {
        /// Which socket, in the words the command line uses.
        role: &'static str,
        /// What the operating system reported.
        reason: String,
    },

    /// The envelope or a proposal was refused by the safety layer.
    #[error("the safety layer refused the configuration")]
    Safety(#[from] clave_safety::SafetyError),
}
