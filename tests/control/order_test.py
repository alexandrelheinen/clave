"""The queue's order solvers.

`AC-MOVE-01` and `AC-MOVE-02` still describe the shipped walk. These tests
cover the seam that lets a second solver stand beside it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from clave.control.order import (
    AntColonySolver,
    NearestNeighborSolver,
    OrderNode,
    OrderRequest,
    make_solver,
    tour_cost,
)
from clave.control.selection import Selector
from clave.control.settings import AntColonySettings, ControlSettings, OrderSolverKind
from clave.errors import ClaveError
from clave.tracker.markers import GraspMarker, color_for
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
NANOS_PER_SECOND = 1_000_000_000
BELT_SPEED = 0.30


def colony_settings() -> AntColonySettings:
    """The shipped colony, so a test does not invent a second set of numbers."""
    return ControlSettings.load(
        load(ROOT / "configs" / "runtime" / "control.yml")
    ).selection.ant_colony


def request(
    nodes: tuple[OrderNode, ...],
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    exit_weight: float = 1.0,
) -> OrderRequest:
    """One request from plain coordinates."""
    return OrderRequest(
        nodes=nodes,
        origin=np.asarray(origin, dtype=np.float64),
        exit_weight=exit_weight,
    )


def node(node_id: int, along: float, slack: float, across: float = 0.0) -> OrderNode:
    """A track on the x axis."""
    return OrderNode(
        node_id=node_id,
        position=np.asarray((along, across, 0.0), dtype=np.float64),
        distance_before_leaving=slack,
    )


def marker(track_id: int, along: float, leaves_in_seconds: float) -> GraspMarker:
    """A marker whose grasp sits on the x axis, for the selector seam."""
    return GraspMarker(
        track_id=track_id,
        valid_until_nanos=int(leaves_in_seconds * NANOS_PER_SECOND),
        grasp=np.asarray((along, 0.0, 0.945), dtype=np.float64),
        flange=np.asarray((along, 0.0, 1.035), dtype=np.float64),
        pads=(),
        pad_size=np.asarray((0.006, 0.02, 0.025), dtype=np.float64),
        closing_axis=None,
        opening=0.06,
        oriented=False,
        reachable=True,
        extent=0.12,
        color=color_for(track_id),
    )


def test_nearest_neighbor_keeps_the_greedy_order_and_its_tie_break() -> None:
    """AC-ORDER-01: the walk takes the urgent track, and a tie keeps the earlier one."""
    urgent = node(1, along=1.0, slack=0.05)
    idle = node(2, along=0.2, slack=5.0)
    order = NearestNeighborSolver().order(request((idle, urgent), exit_weight=2.0))
    assert order == (1, 2)

    flange = np.asarray((0.0, 0.0, 1.035), dtype=np.float64)
    shipped = ControlSettings.load(
        load(ROOT / "configs" / "runtime" / "control.yml")
    ).selection
    queue = Selector(shipped, lambda _pose: True).update(
        (marker(7, 0.4, 3.0), marker(8, 0.4, 3.0)),
        flange,
        BELT_SPEED,
        0,
    )
    assert queue.head is not None
    assert queue.head.track_id == 7


def test_the_exit_weight_is_a_constant_of_a_complete_tour() -> None:
    """Each exit term is paid once, so the weight cannot reorder the sum."""
    nodes = (node(1, 0.2, 0.4), node(2, 0.5, 1.5), node(3, 0.9, 0.2))
    weighted = request(nodes, exit_weight=3.0)
    bare = request(nodes, exit_weight=0.0)
    constant = 3.0 * (0.4 + 1.5 + 0.2)
    orders = ((1, 2, 3), (1, 3, 2), (2, 1, 3), (2, 3, 1), (3, 1, 2), (3, 2, 1))
    for order in orders:
        assert tour_cost(weighted, order, 1.0) == pytest.approx(
            tour_cost(bare, order, 1.0) + constant
        )


def test_a_discount_below_one_lets_the_first_visit_carry_the_weight() -> None:
    """At discount 1 the short path wins. Below 1 the urgent head can win."""
    nodes = (node(1, 0.2, 5.0), node(2, 1.0, 0.05))
    weighted = request(nodes, exit_weight=2.0)
    # Travel of idle-then-urgent is 0.2 + 0.8. Urgent-then-idle is 1.0 + 0.8.
    assert tour_cost(weighted, (1, 2), 1.0) < tour_cost(weighted, (2, 1), 1.0)
    assert tour_cost(weighted, (2, 1), 0.05) < tour_cost(weighted, (1, 2), 0.05)


def test_the_ant_colony_returns_each_admissible_track_once() -> None:
    """AC-ORDER-03: the colony returns each admissible track once."""
    shipped = ControlSettings.load(
        load(ROOT / "configs" / "runtime" / "control.yml")
    ).selection
    selector = Selector(
        replace(shipped, solver=OrderSolverKind.ANT_COLONY),
        lambda _pose: True,
    )
    flange: NDArray[np.float64] = np.asarray((0.0, 0.0, 1.035), dtype=np.float64)
    queue = selector.update(
        (marker(3, 0.2, 4.0), marker(1, 0.6, 4.0), marker(2, 0.9, 1.0)),
        flange,
        BELT_SPEED,
        0,
    )
    assert sorted(item.track_id for item in queue.order) == [1, 2, 3]
    assert AntColonySolver(colony_settings()).order(request(())) == ()


def test_two_colonies_agree_and_pheromone_outlives_a_call() -> None:
    """AC-ORDER-04: two colonies agree, and pheromone survives the call."""
    settings = replace(
        colony_settings(),
        ant_count=4,
        iteration_count=6,
        seed=3,
    )
    one = AntColonySolver(settings)
    two = AntColonySolver(settings)
    first = request((node(1, 0.2, 1.0), node(2, 0.7, 0.3), node(3, 1.1, 0.8)))
    second = request((node(1, 0.2, 0.4), node(4, 0.5, 0.1)))
    assert one.order(first) == two.order(first)
    # The edge is still stored after the call returns. The next request drops
    # track 3, which is a different contract.
    assert any(edge[1] == 3 for edge in one._pheromone)
    assert one.order(second) == two.order(second)


def test_retiring_a_track_drops_edges_that_name_it() -> None:
    """AC-ORDER-06: retiring a track drops edges that name it."""
    solver = AntColonySolver(replace(colony_settings(), iteration_count=2, ant_count=2))
    solver.order(request((node(1, 0.2, 1.0), node(2, 0.8, 0.5))))
    assert any(1 in edge for edge in solver._pheromone)
    solver.retain(frozenset({2}))
    assert all(1 not in edge for edge in solver._pheromone)
    assert solver.order(request((node(2, 0.8, 0.5),))) == (2,)


def test_a_negative_or_repeated_track_is_refused() -> None:
    """A negative id collides with the flange, and a repeated id is not a tour."""
    with pytest.raises(ClaveError, match="negative"):
        NearestNeighborSolver().order(request((node(-1, 0.2, 1.0),)))
    with pytest.raises(ClaveError, match="twice"):
        NearestNeighborSolver().order(request((node(1, 0.2, 1.0), node(1, 0.4, 1.0))))


def test_make_solver_honors_the_configured_kind() -> None:
    """The factory returns the walk or the colony."""
    settings = colony_settings()
    assert isinstance(
        make_solver(OrderSolverKind.NEAREST_NEIGHBOR, settings), NearestNeighborSolver
    )
    assert isinstance(
        make_solver(OrderSolverKind.ANT_COLONY, settings), AntColonySolver
    )


def test_a_colony_that_cannot_search_is_refused() -> None:
    """A hand-built colony with no ants does not pretend to have returned a tour."""
    with pytest.raises(ClaveError, match="one ant"):
        AntColonySolver(replace(colony_settings(), ant_count=0))


def test_the_last_iteration_is_a_permutation_and_a_bad_incumbent_is_refused() -> None:
    """The final iteration is its own tour, and an unknown choice is refused."""
    settings = replace(colony_settings(), ant_count=2, iteration_count=3, seed=4)
    nodes = (node(1, 0.2, 1.0), node(2, 0.7, 0.4), node(3, 1.1, 0.2))
    last = AntColonySolver(settings).order(request(nodes), incumbent="last")
    assert sorted(last) == [1, 2, 3]
    assert AntColonySolver(settings).order(request(()), incumbent="last") == ()
    with pytest.raises(ClaveError, match="incumbent"):
        AntColonySolver(settings).order(request(nodes), incumbent="sample")
