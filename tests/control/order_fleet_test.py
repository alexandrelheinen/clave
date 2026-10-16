"""The moving-field comparison.

A full run is `python -m clave.control.order_fleet`. These tests lock the
reference and the repair, and that the harness scores the walk, the
repair, and a colony that keeps its pheromone.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from clave.control.order import OrderNode, OrderRequest, tour_cost
from clave.control.order_fleet import (
    FleetFactors,
    repair_order,
    run_fleet_study,
    two_opt,
)
from clave.errors import ClaveError


def _node(node_id: int, x: float, y: float) -> OrderNode:
    """A point in the plane, with no belt left to score."""
    return OrderNode(
        node_id=node_id,
        position=np.asarray((x, y, 0.0), dtype=np.float64),
        distance_before_leaving=0.0,
    )


def _request(nodes: tuple[OrderNode, ...]) -> OrderRequest:
    """A request whose flange is the origin."""
    return OrderRequest(
        nodes=nodes,
        origin=np.zeros(3, dtype=np.float64),
        exit_weight=0.0,
    )


def test_two_opt_shortens_a_crossing() -> None:
    """Reversing the crossed segment beats the path it was handed."""
    nodes = (
        _node(1, 0.0, 1.0),
        _node(2, 1.0, 1.0),
        _node(3, 0.0, 2.0),
        _node(4, 1.0, 2.0),
    )
    request = _request(nodes)
    crossed = (1, 4, 3, 2)
    polished = two_opt(request, crossed)
    assert sorted(polished) == [1, 2, 3, 4]
    assert tour_cost(request, polished, 1.0) < tour_cost(request, crossed, 1.0)


def test_repair_keeps_the_surviving_order() -> None:
    """A stolen id drops out, and the ids that remain stay in their order."""
    nodes = (
        _node(1, 0.0, 0.0),
        _node(3, 0.0, 1.0),
        _node(4, 0.2, 0.4),
    )
    order = repair_order((1, 2, 3), _request(nodes))
    assert set(order) == {1, 3, 4}
    assert order.index(1) < order.index(3)


def test_the_fleet_study_scores_walk_repair_and_colony() -> None:
    """AC-ORDER-08: the fleet study scores the walk, a repair, and the colony."""
    report = run_fleet_study(
        FleetFactors(
            populations=(12,),
            epochs=4,
            robots=2,
            side_meters=0.5,
            speed_meters_per_second=1.5,
            epoch_seconds=0.4,
            pop_fraction=0.08,
            iteration_counts=(1,),
            evaporations=(0.5,),
            seed=1,
        )
    )
    rows = {
        (row["solver"], row["memory"], row["incumbent"]): row for row in report["rows"]
    }
    assert ("nearest_neighbor", "none", None) in rows
    assert ("repair", "previous_order", None) in rows
    assert ("two_opt", "none", None) in rows
    assert ("ant_colony", "cold", "best") in rows
    assert ("ant_colony", "warm", "best") in rows
    assert ("ant_colony", "warm", "last") in rows
    walk = rows[("nearest_neighbor", "none", None)]
    assert walk["mean_quality_ratio"] >= 1.0 - 1e-6
    reference = rows[("two_opt", "none", None)]
    assert reference["mean_quality_ratio"] == pytest.approx(1.0)
    assert report["populations"][0]["seen_mean"] < 12
    for row in report["rows"]:
        assert math.isfinite(row["mean_quality_ratio"])
        assert 0.0 <= row["mean_edge_keep"] <= 1.0
        assert row["median_milliseconds"] >= 0.0


def test_a_fleet_with_one_robot_is_refused() -> None:
    """One robot never steals, so it is not the shared field this study runs."""
    with pytest.raises(ClaveError, match="two robots"):
        run_fleet_study(
            FleetFactors(robots=1, epochs=1, populations=(4,), iteration_counts=(1,))
        )
