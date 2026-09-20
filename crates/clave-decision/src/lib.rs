//! The pick decision CLAVE publishes, its wire encoding, and its version.
//!
//! A decision names the material class the classifier assigned, the channel
//! CLAVE resolved from that class, the pose the object is predicted to hold
//! during its pick window, the window itself, the classifier confidence, and
//! the identity the tracker assigned. Everything a consumer needs in order to
//! reach for one object is in the decision, so nothing CLAVE already estimated
//! has to be estimated a second time downstream.
//!
//! This crate holds data and no policy. It resolves no channel, sends nothing,
//! and reads nothing from its environment. The routing policy lives in
//! `clave-routing` and delivery lives in `clave-publish`.
//!
//! # The published contract
//!
//! A consumer implements against `contract/pick-decision.cddl` and the golden
//! vectors under `contract/vectors/`, not against this source. The schema
//! states the unit, the coordinate frame, and the time reference of every
//! field, and states what a consumer does with a version it does not
//! recognize.
//!
//! [`CONTRACT_VERSION`] moves whenever the fields of a decision or the set of
//! material classes changes. A new version ships a new vector directory and
//! leaves the existing ones untouched, because a vector that changes is a
//! vector that proves nothing.
//!
//! # Hardened lint tier
//!
//! This crate sits on the capture-to-decision path, so it carries the hardened
//! lint tier from `.guidelines/languages/rs.md`: an unchecked index,
//! a silent cast, or an unnamed arithmetic overflow is a fault in this domain
//! rather than a style question. Cargo refuses to merge an inherited lint
//! table with a local one, so the crate manifest repeats the workspace
//! baseline beside the hardened tier.
//!
//! # Examples
//!
//! ```
//! use clave_decision::{
//!     BeltPoint, ChannelId, Confidence, MaterialClass, MonotonicNanos, ObjectId, PickDecision,
//!     PickPose, PickWindow,
//! };
//!
//! # fn main() -> Result<(), clave_decision::ContractError> {
//! let window = PickWindow::new(MonotonicNanos::new(0), MonotonicNanos::new(250_000_000))?;
//! let decision = PickDecision::new(
//!     ObjectId::new(4_815_162_342),
//!     MaterialClass::Pet,
//!     ChannelId::new(3),
//!     PickPose::new(BeltPoint::new(0.412, -0.085, 0.031), 1.047, MonotonicNanos::new(100_000_000)),
//!     window,
//!     Confidence::new(0.94)?,
//! )?;
//!
//! assert_eq!(decision.class().taxonomy_id(), "M-01");
//! assert!(decision.is_reachable_at(MonotonicNanos::new(200_000_000)));
//! # Ok(())
//! # }
//! ```
#![forbid(unsafe_code)]

pub mod codec;
mod decision;
mod error;
mod ids;
mod material;
mod pose;
mod window;

pub use crate::decision::PickDecision;
pub use crate::error::ContractError;
pub use crate::ids::{ChannelId, Confidence, ObjectId};
pub use crate::material::MaterialClass;
pub use crate::pose::{BeltPoint, PickPose};
pub use crate::window::{MonotonicNanos, PickWindow};

/// The contract version every published decision carries.
///
/// The version is the first field on the wire. A consumer that reads a version
/// it does not recognize refuses the whole message rather than reading on,
/// which is what keeps a producer running ahead of its consumer from becoming
/// a silent default rather than a visible stop.
pub const CONTRACT_VERSION: u16 = 1;
