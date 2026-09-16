//! The layer that can override a model it shares no code with.
//!
//! CLAVE's constitution says inference proposes and a deterministic layer
//! disposes. This crate is that layer. It receives a proposed pick across a
//! versioned boundary, checks the point against a workspace envelope read from
//! configuration, and either produces a decision ready to publish or overrides
//! the proposal and names the check that refused it.
//!
//! # Why this links no machine learning framework
//!
//! The whole value of the layer is that it cannot be wrong in the same way the
//! model is wrong. A crate that loaded the model would share its version of a
//! tensor library, its export step, and its failure modes. So Python runs
//! inference, this crate never loads a model, and the two meet only at the
//! JSON proposal in [`Proposal`]. The manifest is where that claim is
//! checkable, and a test checks it.
//!
//! The cost is a process boundary and the latency it adds, which is measured
//! rather than assumed. `docs/measurements.md` reports the figure.
//!
//! # Hardened lint tier
//!
//! This crate decides whether an effector moves, so it carries the hardened
//! lint tier from `standards/guidelines/languages/rs.md`. Cargo refuses to
//! merge an inherited lint table with a local one, so the crate manifest
//! repeats the workspace baseline beside it.
//!
//! # Examples
//!
//! ```
//! use clave_decision::{ChannelId, Confidence, MaterialClass};
//! use clave_routing::{ChannelMap, Resolver};
//! use clave_safety::{Check, Envelope, Proposal};
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let envelope = Envelope::from_json(
//!     br#"{"arm_base_meters": [0.0, 0.34, 0.35], "reach_radius_meters": 0.38,
//!          "belt_surface_z_meters": 0.35, "belt_x_meters": [-1.0, 1.0],
//!          "belt_y_meters": [-0.25, 0.25]}"#,
//! )?;
//! let resolver = Resolver::new(ChannelMap::new(
//!     [(MaterialClass::Pet, ChannelId::new(1))],
//!     ChannelId::new(0),
//!     Confidence::new(0.6)?,
//! )?);
//!
//! // A point two thirds of a meter down the belt is beyond the arm's reach.
//! let proposal = Proposal::decode(
//!     br#"{"version": 1, "object_id": 7, "material_class": "M-01",
//!          "confidence": 0.91, "x_meters": 0.66, "y_meters": 0.0,
//!          "z_meters": 0.36, "yaw_radians": 0.0, "reference_time_nanos": 1000,
//!          "window_start_nanos": 1000, "window_end_nanos": 2000}"#,
//! )?;
//! let verdict = envelope.judge(&proposal, &resolver)?;
//! assert_eq!(verdict.overridden_check(), Some(Check::Reach));
//! assert!(verdict.decision().is_none());
//! # Ok(())
//! # }
//! ```
#![forbid(unsafe_code)]

mod envelope;
mod error;
mod proposal;
mod verdict;

pub use crate::envelope::Envelope;
pub use crate::error::SafetyError;
pub use crate::proposal::{PROPOSAL_VERSION, Proposal};
pub use crate::verdict::{Check, Verdict};
