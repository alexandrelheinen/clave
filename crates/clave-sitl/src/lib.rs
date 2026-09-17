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
//!     br#"{"base_meters": [0.0, -0.7, 0.9], "reach_meters": [0.25, 1.25],
//!          "tool_above_base_meters": [-0.05, 0.45],
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
