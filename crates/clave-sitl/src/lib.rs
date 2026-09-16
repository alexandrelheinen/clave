//! The Rust half of the software-in-the-loop runtime.
//!
//! Python steps the world, runs inference and proposes a pick. This crate
//! receives the proposal, hands it to the safety layer in `clave-safety`,
//! routes what survives through `clave-routing`, and publishes the decision
//! through `clave-publish`. It loads no model and links no machine learning
//! framework, which is the whole reason it is a separate process.
//!
//! The decision path is in [`Service`], which owns no socket. The socket loop
//! is in [`serve`]. Splitting them is what lets every verdict, every counter
//! and every outcome be exercised without a file system or a child process.
//!
//! # Examples
//!
//! ```
//! use clave_decision::{ChannelId, Confidence, MaterialClass};
//! use clave_publish::InMemorySink;
//! use clave_routing::{ChannelMap, Resolver};
//! use clave_safety::Envelope;
//! use clave_sitl::{Outcome, Service};
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let envelope = Envelope::from_json(
//!     br#"{"shoulder_meters": [0.0, 0.0, 1.408], "link_meters": [0.4, 0.25],
//!          "reach_meters": [0.222, 0.65], "shoulder_limit_radians": 2.443461,
//!          "elbow_limit_radians": 2.617994,
//!          "tool_above_belt_meters": [0.03, 0.21],
//!          "belt_surface_z_meters": 0.9, "belt_x_meters": [-1.5, 1.5],
//!          "belt_y_meters": [-0.5, 0.5]}"#,
//! )?;
//! let resolver = Resolver::new(ChannelMap::new(
//!     [(MaterialClass::Pet, ChannelId::new(1))],
//!     ChannelId::new(0),
//!     Confidence::new(0.6)?,
//! )?);
//! let mut service = Service::new(envelope, resolver, InMemorySink::new());
//!
//! let outcome = service.handle(b"this is not a proposal");
//! assert!(matches!(outcome, Outcome::Refused { .. }));
//! assert_eq!(service.counters().refused, 1);
//! # Ok(())
//! # }
//! ```
#![forbid(unsafe_code)]

mod config;
mod error;
mod serve;
mod service;

pub use crate::config::RuntimeConfig;
pub use crate::error::RuntimeError;
pub use crate::serve::{ServeConfig, serve};
pub use crate::service::{Outcome, RunCounters, Service};
