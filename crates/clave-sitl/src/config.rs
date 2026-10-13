//! What the runtime reads before it binds a socket.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use clave_decision::{ChannelId, Confidence, MaterialClass};
use clave_routing::{ChannelMap, OUTCOME_COUNT, Resolver};
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
        let probe: RuleProbe =
            serde_json::from_slice(bytes).map_err(|error| RuntimeError::Config {
                reason: error.to_string(),
            })?;
        let rule = probe.rule.as_deref().unwrap_or(CONFIDENCE_FLOOR);
        match rule {
            CONFIDENCE_FLOOR => Self::from_floor(bytes),
            EXPECTED_COST => Self::from_expected_cost(bytes),
            other => Err(RuntimeError::Config {
                reason: format!("rule {other} is not a known routing rule"),
            }),
        }
    }

    /// Loads a confidence-floor runtime, ignoring any cost table in the file.
    fn from_floor(bytes: &[u8]) -> Result<Self, RuntimeError> {
        let wire: Wire = serde_json::from_slice(bytes).map_err(|error| RuntimeError::Config {
            reason: error.to_string(),
        })?;
        let map = channel_map(&wire)?;
        Ok(Self {
            envelope: Envelope::from_json(bytes)?,
            resolver: Resolver::new(map),
        })
    }

    /// Loads an expected-cost runtime, requiring a cost row per channel.
    fn from_expected_cost(bytes: &[u8]) -> Result<Self, RuntimeError> {
        let wire: ExpectedWire =
            serde_json::from_slice(bytes).map_err(|error| RuntimeError::Config {
                reason: error.to_string(),
            })?;
        let Some(raw_rows) = wire.cost else {
            return Err(RuntimeError::Config {
                reason: "required configuration key 'cost' is missing".to_owned(),
            });
        };
        let map = channel_map(&wire.floor)?;
        let mut rows = Vec::new();
        for row in raw_rows {
            rows.push(cost_row(row)?);
        }
        let resolver =
            Resolver::with_expected_cost(map, rows).map_err(|error| RuntimeError::Config {
                reason: error.to_string(),
            })?;
        Ok(Self {
            envelope: Envelope::from_json(bytes)?,
            resolver,
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

/// The rule a missing `rule` key selects.
const CONFIDENCE_FLOOR: &str = "confidence_floor";

/// The rule that loads a cost table and speaks proposal version 2.
const EXPECTED_COST: &str = "expected_cost";

/// Enough of the file to read the rule, ignoring every other field.
///
/// A confidence-floor file may carry a garbage `cost` value. That value is
/// not read, which is why this probe names only `rule`.
#[derive(Debug, serde::Deserialize)]
struct RuleProbe {
    #[serde(default)]
    rule: Option<String>,
}

/// The routing half of a confidence-floor file.
#[derive(Debug, serde::Deserialize)]
struct Wire {
    channels: BTreeMap<String, u16>,
    reject_channel: u16,
    confidence_floor: f32,
}

/// An expected-cost file: the floor fields, plus the cost rows.
#[derive(Debug, serde::Deserialize)]
struct ExpectedWire {
    #[serde(flatten)]
    floor: Wire,
    cost: Option<Vec<CostRow>>,
}

/// One channel's costs, in outcome order.
#[derive(Debug, serde::Deserialize)]
struct CostRow {
    channel: u16,
    costs: Vec<f64>,
}

/// Builds the channel map the floor and the cost rule share.
fn channel_map(wire: &Wire) -> Result<ChannelMap, RuntimeError> {
    let mut entries = Vec::new();
    for (id, channel) in &wire.channels {
        entries.push((class_for(id)?, ChannelId::new(*channel)));
    }
    let threshold =
        Confidence::new(wire.confidence_floor).map_err(|error| RuntimeError::Config {
            reason: error.to_string(),
        })?;
    ChannelMap::new(entries, ChannelId::new(wire.reject_channel), threshold).map_err(|error| {
        RuntimeError::Config {
            reason: error.to_string(),
        }
    })
}

/// Copies one cost row into the fixed outcome width.
fn cost_row(row: CostRow) -> Result<(ChannelId, [f64; OUTCOME_COUNT]), RuntimeError> {
    if row.costs.len() != OUTCOME_COUNT {
        return Err(RuntimeError::Config {
            reason: format!("cost channel {} needs {OUTCOME_COUNT} costs", row.channel),
        });
    }
    let mut costs = [0.0; OUTCOME_COUNT];
    for (slot, value) in costs.iter_mut().zip(row.costs) {
        *slot = value;
    }
    Ok((ChannelId::new(row.channel), costs))
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
