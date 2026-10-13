//! The channel of minimum expected cost.
//!
//! The confidence floor in [`crate::Resolver::resolve`] stays. A configuration
//! picks one rule. This module is the other one: a dot product of a cost row
//! with a posterior, and the lowest channel id when two rows tie.

use std::collections::BTreeMap;
use std::collections::BTreeSet;

use clave_decision::{ChannelId, MaterialClass};

use crate::error::RoutingError;

/// Weights in one posterior: one per taxonomy class, then the reject outcome.
///
/// The reject outcome is a cost column. It is not a [`MaterialClass`], and the
/// decision reports the leading taxonomy class beside it.
pub const OUTCOME_COUNT: usize = MaterialClass::ALL.len() + 1;

/// Column of `M-11` in that vector.
///
/// Taxonomy order is the column order, and residue is the last class, so its
/// column sits one slot before the reject outcome.
fn residue_column() -> usize {
    let mut index = 0;
    while index < MaterialClass::ALL.len() {
        if matches!(MaterialClass::ALL[index], MaterialClass::Residue) {
            return index;
        }
        index += 1;
    }
    index
}

/// One finite, nonnegative cost per outcome, for every channel the map names.
#[derive(Debug, Clone, PartialEq)]
pub struct CostTable<const N: usize> {
    rows: BTreeMap<ChannelId, [f64; N]>,
    reject: ChannelId,
}

impl<const N: usize> CostTable<N> {
    /// Loads rows, requiring the reject channel and refusing a bad cost.
    ///
    /// # Errors
    ///
    /// Returns [`RoutingError::DuplicateChannel`] when one channel is priced
    /// twice, [`RoutingError::MissingCostRow`] when the reject channel has no
    /// row, and [`RoutingError::InvalidCost`] when a cost is negative or not
    /// finite.
    pub fn from_rows(
        entries: impl IntoIterator<Item = (ChannelId, [f64; N])>,
        reject: ChannelId,
    ) -> Result<Self, RoutingError> {
        let mut rows = BTreeMap::new();
        for (channel, costs) in entries {
            if rows.insert(channel, costs).is_some() {
                return Err(RoutingError::DuplicateChannel {
                    channel: channel.get(),
                });
            }
            if costs.iter().any(|cost| !cost.is_finite() || *cost < 0.0) {
                return Err(RoutingError::InvalidCost {
                    channel: channel.get(),
                });
            }
        }
        if !rows.contains_key(&reject) {
            return Err(RoutingError::MissingCostRow {
                channel: reject.get(),
            });
        }
        Ok(Self { rows, reject })
    }

    /// Returns the channel of minimum expected cost, and that cost.
    ///
    /// Rows are visited in channel-id order. A tie keeps the earlier row, so
    /// the lowest channel id wins, and the reject channel wins a tie when it
    /// is the lowest id.
    #[must_use]
    pub fn minimizing_channel(&self, posterior: &[f64; N]) -> (ChannelId, f64) {
        let mut best_channel = self.reject;
        let mut best_cost = f64::INFINITY;
        let mut seen = false;
        for (channel, row) in &self.rows {
            let cost = dot(row, posterior);
            if !seen || cost < best_cost {
                seen = true;
                best_cost = cost;
                best_channel = *channel;
            }
        }
        (best_channel, best_cost)
    }
}

impl CostTable<OUTCOME_COUNT> {
    /// Loads the rows the channel map names, and refuses a residue bypass.
    ///
    /// # Errors
    ///
    /// Returns the errors of [`CostTable::from_rows`], [`RoutingError::UnknownCostChannel`]
    /// or [`RoutingError::MissingCostRow`] when the row set is not the map's
    /// channel set, and [`RoutingError::ResidueCheaperThanReject`] when a
    /// sorted channel prices `M-11` strictly below the reject channel.
    pub fn for_channels(
        known: &BTreeSet<ChannelId>,
        reject: ChannelId,
        entries: impl IntoIterator<Item = (ChannelId, [f64; OUTCOME_COUNT])>,
    ) -> Result<Self, RoutingError> {
        let table = Self::from_rows(entries, reject)?;
        table.exact_channels(known)?;
        table.refuse_cheap_residue()
    }

    /// Refuses a row set that is not exactly `known`.
    fn exact_channels(&self, known: &BTreeSet<ChannelId>) -> Result<(), RoutingError> {
        for channel in self.rows.keys() {
            if !known.contains(channel) {
                return Err(RoutingError::UnknownCostChannel {
                    channel: channel.get(),
                });
            }
        }
        for channel in known {
            if !self.rows.contains_key(channel) {
                return Err(RoutingError::MissingCostRow {
                    channel: channel.get(),
                });
            }
        }
        Ok(())
    }

    /// Refuses a sorted channel that undercuts reject on residue.
    fn refuse_cheap_residue(self) -> Result<Self, RoutingError> {
        let column = residue_column();
        let Some(reject_cost) = self.rows.get(&self.reject).and_then(|row| row.get(column)) else {
            return Err(RoutingError::MissingCostRow {
                channel: self.reject.get(),
            });
        };
        let reject_cost = *reject_cost;
        for (channel, row) in &self.rows {
            if *channel == self.reject {
                continue;
            }
            let Some(cost) = row.get(column) else {
                return Err(RoutingError::InvalidCost {
                    channel: channel.get(),
                });
            };
            if *cost < reject_cost {
                return Err(RoutingError::ResidueCheaperThanReject {
                    channel: channel.get(),
                    reject: self.reject.get(),
                });
            }
        }
        Ok(self)
    }
}

/// The sum of `cost * weight` across one row.
fn dot<const N: usize>(row: &[f64; N], posterior: &[f64; N]) -> f64 {
    let mut total = 0.0;
    for (cost, weight) in row.iter().zip(posterior.iter()) {
        total += cost * weight;
    }
    total
}
