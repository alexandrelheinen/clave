//! Resolves a material class and a classifier confidence to a sorting channel.
//!
//! This crate is policy and nothing else. It reads no input, writes no output,
//! and estimates nothing. It depends on `clave-decision` for the value types
//! and on nothing else in the workspace.
//!
//! The line operator supplies the mapping from a material class to a physical
//! channel, including which channel is the reject channel and the confidence
//! floor below which an object is rejected whatever its class. The mapping is
//! validated once when it is loaded rather than once per object, because a
//! line that starts and then misroutes is worse than a line that refuses to
//! start.
//!
//! Two routes end at the reject channel and they are told apart by their
//! reason: an object the classifier was not sure enough about, and an object
//! whose class the operator mapped no channel for.
//!
//! # Examples
//!
//! ```
//! use clave_decision::{ChannelId, Confidence, MaterialClass};
//! use clave_routing::{ChannelMap, RejectReason, Resolver, Routed};
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let reject = ChannelId::new(0);
//! let map = ChannelMap::new(
//!     [(MaterialClass::Pet, ChannelId::new(1))],
//!     reject,
//!     Confidence::new(0.6)?,
//! )?;
//! let resolver = Resolver::new(map);
//!
//! assert_eq!(
//!     resolver.resolve(MaterialClass::Pet, Confidence::new(0.9)?),
//!     Routed::Sorted(ChannelId::new(1))
//! );
//! assert_eq!(
//!     resolver
//!         .resolve(MaterialClass::Pet, Confidence::new(0.1)?)
//!         .reject_reason(),
//!     Some(RejectReason::BelowThreshold)
//! );
//! # Ok(())
//! # }
//! ```
#![forbid(unsafe_code)]

mod channel_map;
mod error;
mod resolver;

pub use crate::channel_map::ChannelMap;
pub use crate::error::RoutingError;
pub use crate::resolver::{RejectReason, Resolver, Routed};
