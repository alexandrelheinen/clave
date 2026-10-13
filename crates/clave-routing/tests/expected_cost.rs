//! Expected cost beside the confidence floor.
#![expect(clippy::unwrap_used, reason = "test assertions")]

use clave_decision::{ChannelId, Confidence, MaterialClass};
use clave_routing::{
    ChannelMap, CostTable, OUTCOME_COUNT, RejectReason, Resolver, Routed, RoutingError,
};

const REJECT: ChannelId = ChannelId::new(0);

fn floor() -> Confidence {
    Confidence::new(0.6).unwrap()
}

fn sitl_map() -> ChannelMap {
    ChannelMap::new(
        [
            (MaterialClass::Pet, ChannelId::new(1)),
            (MaterialClass::Hdpe, ChannelId::new(2)),
            (MaterialClass::Pp, ChannelId::new(3)),
            (MaterialClass::OtherPlastic, ChannelId::new(4)),
            (MaterialClass::Aluminum, ChannelId::new(5)),
            (MaterialClass::Ferrous, ChannelId::new(6)),
            (MaterialClass::Glass, ChannelId::new(7)),
            (MaterialClass::Cardboard, ChannelId::new(8)),
            (MaterialClass::MixedPaper, ChannelId::new(8)),
            (MaterialClass::BeverageCarton, ChannelId::new(8)),
            (MaterialClass::Residue, REJECT),
        ],
        REJECT,
        floor(),
    )
    .unwrap()
}

/// The reasoned default, read from the file the specification names.
fn reasoned_rows() -> Vec<(ChannelId, [f64; OUTCOME_COUNT])> {
    let text = include_str!("../../../configs/routing/expected-cost-default.yml");
    let mut rows = Vec::new();
    let mut channel = None;
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("- channel:") {
            channel = rest.trim().parse().ok();
        } else if let Some(rest) = trimmed.strip_prefix("costs:") {
            let body = rest.trim().trim_start_matches('[').trim_end_matches(']');
            let mut costs = [0.0; OUTCOME_COUNT];
            let mut count = 0;
            for (slot, part) in costs.iter_mut().zip(body.split(',')) {
                *slot = part.trim().parse().unwrap();
                count += 1;
            }
            assert_eq!(count, OUTCOME_COUNT, "a reasoned row has the outcome width");
            let id = channel.take().unwrap();
            rows.push((ChannelId::new(id), costs));
        }
    }
    assert_eq!(
        rows.len(),
        9,
        "the reasoned default prices channels 0 through 8"
    );
    rows
}

fn reasoned() -> Resolver {
    Resolver::with_expected_cost(sitl_map(), reasoned_rows()).unwrap()
}

fn spike(pairs: &[(usize, f64)]) -> [f64; OUTCOME_COUNT] {
    let mut posterior = [0.0; OUTCOME_COUNT];
    for &(index, weight) in pairs {
        posterior[index] = weight;
    }
    posterior
}

/// Hand product of one row, written out so it cannot call the library dot.
fn hand_cost(row: &[f64; OUTCOME_COUNT], posterior: &[f64; OUTCOME_COUNT]) -> f64 {
    let mut total = 0.0;
    for index in (0..OUTCOME_COUNT).rev() {
        total += row[index] * posterior[index];
    }
    total
}

/// AC-SORT-07: the resolver's channel matches an independent product.
#[test]
fn ac_sort_07_the_resolver_argmin_matches_an_independent_multiply() {
    let resolver = reasoned();
    // Mode is M-08, which the map sends to channel 8. The mass on M-06 makes
    // the ferrous channel cheaper than fiber and cheaper than reject.
    let posterior = spike(&[(5, 0.4), (7, 0.6)]);
    let rows = reasoned_rows();

    let mut best = None;
    let mut best_cost = f64::INFINITY;
    for (channel, row) in &rows {
        let cost = hand_cost(row, &posterior);
        if cost < best_cost {
            best_cost = cost;
            best = Some(*channel);
        }
    }

    assert_eq!(best, Some(ChannelId::new(6)));
    assert!((best_cost - 1.8).abs() < 1e-9);
    assert_eq!(
        resolver.map().channel_for(MaterialClass::Cardboard),
        Some(ChannelId::new(8))
    );
    assert_eq!(
        resolver.choose_expected_cost(&posterior),
        Some(Routed::Sorted(ChannelId::new(6)))
    );
}

/// AC-SORT-08: reject wins, and the route still names a reason rather than
/// dropping the class. The class stays on the decision the caller builds.
#[test]
fn ac_sort_08_reject_wins_and_the_route_names_expected_cost() {
    let resolver = reasoned();
    // Half aluminum and half ferrous. Aluminum's row costs 4, ferrous costs
    // 2.5, reject costs 2, so reject is the minimum.
    let posterior = spike(&[(4, 0.5), (5, 0.5)]);
    let routed = resolver.choose_expected_cost(&posterior).unwrap();

    assert_eq!(
        routed,
        Routed::Rejected {
            channel: REJECT,
            reason: RejectReason::ExpectedCost,
        }
    );
    assert_eq!(routed.channel(), REJECT);
}

/// AC-SORT-09: a nonnegative residue cost below reject's residue cost fails
/// at load, before any posterior is scored.
#[test]
fn ac_sort_09_residue_cheaper_on_a_sorted_channel_fails_load() {
    let mut reject_row = [1.0; OUTCOME_COUNT];
    let mut sorted_row = [1.0; OUTCOME_COUNT];
    reject_row[10] = 5.0;
    sorted_row[10] = 4.0;
    let map = ChannelMap::new([(MaterialClass::Pet, ChannelId::new(1))], REJECT, floor()).unwrap();

    let error =
        Resolver::with_expected_cost(map, [(REJECT, reject_row), (ChannelId::new(1), sorted_row)])
            .unwrap_err();

    assert!(matches!(
        error,
        RoutingError::ResidueCheaperThanReject {
            channel: 1,
            reject: 0,
        }
    ));
}

/// AC-SORT-11: the book's posterior selects nop, and the prior selects metal.
#[test]
fn ac_sort_11_the_book_posterior_selects_the_nop() {
    // Columns are cardboard, paper, can, scrap metal, bottle.
    let glass = [2.0, 2.0, 4.0, 6.0, 0.0];
    let metal = [1.0, 1.0, 0.0, 0.0, 2.0];
    let paper = [0.0, 0.0, 5.0, 10.0, 3.0];
    let nop = [1.0, 1.0, 1.0, 1.0, 1.0];
    let table = CostTable::from_rows(
        [
            (ChannelId::new(0), glass),
            (ChannelId::new(1), metal),
            (ChannelId::new(2), paper),
            (ChannelId::new(3), nop),
        ],
        ChannelId::new(3),
    )
    .unwrap();

    let prior = [0.2, 0.3, 0.25, 0.2, 0.05];
    let (prior_channel, prior_cost) = table.minimizing_channel(&prior);
    assert_eq!(prior_channel, ChannelId::new(1));
    assert!((prior_cost - 0.6).abs() < 1e-9);
    let prior_glass = 2.0 * 0.2 + 2.0 * 0.3 + 4.0 * 0.25 + 6.0 * 0.2;
    assert!((prior_glass - 3.2_f64).abs() < 1e-9);

    let posterior = [0.2, 0.3, 0.1, 0.1, 0.3];
    let (channel, cost) = table.minimizing_channel(&posterior);
    assert_eq!(channel, ChannelId::new(3));
    assert!((cost - 1.0).abs() < 1e-9);
    let metal_cost = 1.0 * 0.2 + 1.0 * 0.3 + 2.0 * 0.3;
    assert!((metal_cost - 1.1_f64).abs() < 1e-9);
}

/// AC-SORT-21: `resolve` keeps the floor even after a cost table is loaded.
#[test]
fn ac_sort_21_resolve_keeps_the_confidence_floor_beside_a_cost_table() {
    let resolver = reasoned();
    let routed = resolver.resolve(MaterialClass::Pet, Confidence::new(0.1).unwrap());

    assert_eq!(
        routed,
        Routed::Rejected {
            channel: REJECT,
            reason: RejectReason::BelowThreshold,
        }
    );
    assert!(resolver.choose_expected_cost(&spike(&[])).is_some());
}

/// A posterior whose leading weight sits below the floor still sorts when
/// that sorted channel is the minimum. The two rules do not blend.
#[test]
fn expected_cost_does_not_apply_the_confidence_floor() {
    let resolver = reasoned();
    let posterior = spike(&[(0, 0.55), (1, 0.45)]);
    let routed = resolver.choose_expected_cost(&posterior).unwrap();

    assert_eq!(routed, Routed::Sorted(ChannelId::new(1)));
}

/// Equal expected cost keeps the lowest channel id, which is reject here.
#[test]
fn a_tie_keeps_the_lowest_channel_id() {
    let mut reject_row = [2.0; OUTCOME_COUNT];
    let mut sorted_row = [2.0; OUTCOME_COUNT];
    reject_row[10] = 0.0;
    sorted_row[10] = 0.0;
    let map = ChannelMap::new([(MaterialClass::Pet, ChannelId::new(1))], REJECT, floor()).unwrap();
    let resolver =
        Resolver::with_expected_cost(map, [(REJECT, reject_row), (ChannelId::new(1), sorted_row)])
            .unwrap();

    let routed = resolver.choose_expected_cost(&spike(&[(0, 1.0)])).unwrap();
    assert_eq!(
        routed,
        Routed::Rejected {
            channel: REJECT,
            reason: RejectReason::ExpectedCost,
        }
    );
}

/// Residue priced the same on a sorted channel as on reject is a tie, not a
/// bypass, so the table loads.
#[test]
fn residue_priced_equal_to_reject_loads() {
    let mut reject_row = [1.0; OUTCOME_COUNT];
    let mut sorted_row = [1.0; OUTCOME_COUNT];
    reject_row[10] = 5.0;
    sorted_row[10] = 5.0;
    let map = ChannelMap::new([(MaterialClass::Pet, ChannelId::new(1))], REJECT, floor()).unwrap();

    assert!(
        Resolver::with_expected_cost(map, [(REJECT, reject_row), (ChannelId::new(1), sorted_row)],)
            .is_ok()
    );
}

#[test]
fn a_negative_cost_is_refused_at_load() {
    let mut reject_row = [1.0; OUTCOME_COUNT];
    let mut sorted_row = [1.0; OUTCOME_COUNT];
    reject_row[10] = 0.0;
    sorted_row[0] = -1.0;
    let map = ChannelMap::new([(MaterialClass::Pet, ChannelId::new(1))], REJECT, floor()).unwrap();
    let error =
        Resolver::with_expected_cost(map, [(REJECT, reject_row), (ChannelId::new(1), sorted_row)])
            .unwrap_err();

    assert!(matches!(error, RoutingError::InvalidCost { channel: 1 }));
}

#[test]
fn a_missing_mapped_channel_is_named() {
    let mut reject_row = [1.0; OUTCOME_COUNT];
    reject_row[10] = 0.0;
    let map = ChannelMap::new([(MaterialClass::Pet, ChannelId::new(1))], REJECT, floor()).unwrap();
    let error = Resolver::with_expected_cost(map, [(REJECT, reject_row)]).unwrap_err();

    assert!(matches!(error, RoutingError::MissingCostRow { channel: 1 }));
}

#[test]
fn residue_column_is_the_taxonomy_slot_for_m11() {
    assert_eq!(MaterialClass::ALL[10], MaterialClass::Residue);
    assert_eq!(OUTCOME_COUNT, MaterialClass::ALL.len() + 1);
}
