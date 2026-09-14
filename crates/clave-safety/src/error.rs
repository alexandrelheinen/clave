//! The one error type every fallible call in this crate returns.

/// A proposal, an envelope, or a file claiming to be one, that this crate
/// refuses.
///
/// Variants name the failure rather than the call that produced it, so a
/// caller branches on what went wrong and not on where.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum SafetyError {
    /// The proposal declares a wire version this build does not implement.
    ///
    /// The version is read before any other field, so nothing past it is
    /// interpreted. A producer running ahead of its consumer stops visibly
    /// rather than having its fields read under the wrong meaning.
    #[error("proposal declares version {found}, which this build does not implement")]
    UnsupportedVersion {
        /// The version the payload carried.
        found: u64,
    },

    /// The payload is not a proposal this crate can read.
    #[error("the proposal is malformed: {reason}")]
    Malformed {
        /// What the decoder expected to find and did not.
        reason: String,
    },

    /// The proposal names a material class the taxonomy does not define.
    #[error("material class {id} is not in the taxonomy")]
    UnknownClass {
        /// The identifier the payload carried.
        id: String,
    },

    /// A value the decision contract validates was refused.
    #[error("the decision contract refused the proposal")]
    Contract(#[from] clave_decision::ContractError),

    /// The envelope configuration does not carry a key the checks need.
    #[error("the workspace envelope is missing the key {key}")]
    MissingEnvelopeKey {
        /// The key that was absent.
        key: String,
    },

    /// The envelope values describe no usable volume.
    #[error("the workspace envelope is unusable: {reason}")]
    InvalidEnvelope {
        /// What is wrong with it.
        reason: String,
    },

    /// The envelope file could not be read.
    #[error("the workspace envelope at {path} could not be read: {reason}")]
    EnvelopeUnreadable {
        /// The path that was tried.
        path: String,
        /// What the operating system reported.
        reason: String,
    },
}
