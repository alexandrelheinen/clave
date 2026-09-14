//! What the runtime reads before it binds a socket.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use clave_decision::{ChannelId, Confidence, MaterialClass};
use clave_routing::{ChannelMap, Resolver};
use clave_safety::Envelope;

use crate::error::RuntimeError;

/// The envelope and the routing policy, read from one file.
///
/// The file is JSON, written by the Python side out of
/// `configs/runtime/sitl.yml` before the runtime starts. An operator edits the
/// YAML; this crate reads the translation, which is what keeps a YAML parser
/// out of the process that decides whether an effector moves.
#[derive(Debug, Clone)]
pub struct RuntimeConfig {
    envelope: Envelope,
    resolver: Resolver,
}

impl RuntimeConfig {
    /// Reads the configuration from a file.
    ///
    /// # Errors
    ///
    /// Returns [`RuntimeError::Unreadable`] when the file cannot be read,
    /// [`RuntimeError::Safety`] when the envelope is missing a key, and
    /// [`RuntimeError::Config`] when the routing policy names a class outside
    /// the taxonomy or a channel the mapping refuses.
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self, RuntimeError> {
        let path = path.as_ref();
        let bytes = fs::read(path).map_err(|error| RuntimeError::Unreadable {
            path: path.display().to_string(),
            reason: error.to_string(),
        })?;
        Self::from_json(&bytes)
    }

    /// Reads the configuration from JSON bytes.
    ///
    /// # Errors
    ///
    /// As [`RuntimeConfig::load`], less the file read.
    pub fn from_json(bytes: &[u8]) -> Result<Self, RuntimeError> {
        let wire: Wire = serde_json::from_slice(bytes).map_err(|error| RuntimeError::Config {
            reason: error.to_string(),
        })?;
        let mut entries = Vec::new();
        for (id, channel) in &wire.channels {
            entries.push((class_for(id)?, ChannelId::new(*channel)));
        }
        let threshold =
            Confidence::new(wire.confidence_floor).map_err(|error| RuntimeError::Config {
                reason: error.to_string(),
            })?;
        let map = ChannelMap::new(entries, ChannelId::new(wire.reject_channel), threshold)
            .map_err(|error| RuntimeError::Config {
                reason: error.to_string(),
            })?;
        Ok(Self {
            envelope: Envelope::from_json(bytes)?,
            resolver: Resolver::new(map),
        })
    }

    /// Returns the workspace envelope the checks run against.
    #[must_use]
    pub const fn envelope(&self) -> &Envelope {
        &self.envelope
    }

    /// Returns the routing policy a surviving proposal is resolved through.
    #[must_use]
    pub const fn resolver(&self) -> &Resolver {
        &self.resolver
    }
}

/// The routing half of the file. The envelope half is read by `clave-safety`.
#[derive(Debug, serde::Deserialize)]
struct Wire {
    channels: BTreeMap<String, u16>,
    reject_channel: u16,
    confidence_floor: f32,
}

/// Returns the class with this taxonomy identifier.
fn class_for(id: &str) -> Result<MaterialClass, RuntimeError> {
    MaterialClass::ALL
        .into_iter()
        .find(|class| class.taxonomy_id() == id)
        .ok_or_else(|| RuntimeError::Config {
            reason: format!("channel map names material class {id}, which is not in the taxonomy"),
        })
}
