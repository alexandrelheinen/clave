"""Solvers that turn a set of tracks into the order the arm should try.

The selector used to own the walk. It now asks a solver, so the walk and
an ant colony can be exchanged from configuration without the queue's
anchoring, or the task machine, knowing which one ran.

The step cost both solvers share is

    distance(standing, anchor) + exit_weight * distance_before_leaving

with both distances in meters. Summed over a complete permutation at a
position discount of one, the exit terms are a constant: every admissible
object is visited once, so they cannot change which permutation is
shortest. The greedy walk does not minimize that sum. It minimizes the
next step, which is the rule that lets a dying object outrank a nearer
one. The colony minimizes the discounted sum, and only a discount below
one lets that sum care about the same thing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from clave.control.settings import AntColonySettings, OrderSolverKind
from clave.control.trajectory import distance
from clave.errors import ClaveError

FLANGE_ID = -1
"""Edge source for the flange. Track ids are non-negative, so this cannot collide."""

COST_FLOOR = 1e-12
"""Meters. Keeps a reciprocal finite when a node sits on the standing position."""


@dataclass(frozen=True)
class OrderNode:
    """One admissible track, at the pose the ordering scores.

    Attributes:
        node_id: The track. Non-negative, and unique inside a request.
        position: Where the track is scored, in the same frame the flange
            is passed in.
        distance_before_leaving: Belt left before the window closes, in
            meters.
    """

    node_id: int
    position: NDArray[np.float64]
    distance_before_leaving: float


@dataclass(frozen=True)
class OrderRequest:
    """What a solver needs and nothing the queue already decided.

    Attributes:
        nodes: The admissible tracks, in the order the caller listed them.
            A tie in the greedy walk keeps the earlier node.
        origin: Where the flange stands.
        exit_weight: The dimensionless weight on belt left.
    """

    nodes: tuple[OrderNode, ...]
    origin: NDArray[np.float64]
    exit_weight: float


class OrderSolver(Protocol):
    """A permutation of one request, plus whatever memory the method keeps."""

    def order(self, request: OrderRequest) -> tuple[int, ...]:
        """Return the track ids, first visit first.

        Args:
            request: The admissible tracks and the flange.

        Returns:
            A permutation of the request's track ids, or empty when the
            request is empty.
        """

    def retain(self, node_ids: frozenset[int]) -> None:
        """Forget memory about tracks outside this set.

        Args:
            node_ids: The tracks still admissible. The flange id is not a
                member, and edges from the flange to a retained track stay.
        """


def step_cost(
    standing: NDArray[np.float64], node: OrderNode, exit_weight: float
) -> float:
    """Return the cost of taking this track next, in meters.

    Args:
        standing: Where the flange is, or will be.
        node: The track scored.
        exit_weight: Dimensionless weight on belt left.

    Returns:
        Travel plus the weighted belt left.
    """
    return (
        distance(standing, node.position) + exit_weight * node.distance_before_leaving
    )


def tour_cost(request: OrderRequest, order: tuple[int, ...], discount: float) -> float:
    """Return the discounted sum of step costs along one permutation.

    Args:
        request: The tracks and the flange the permutation starts from.
        order: Track ids, first visit first. Every id has to name a node
            of the request.
        discount: Multiplier applied to the step cost once per visit
            already taken. One scores the plain sum.

    Returns:
        The discounted sum, in meters.
    """
    by_id = {node.node_id: node for node in request.nodes}
    standing = request.origin
    total = 0.0
    place = 1.0
    for node_id in order:
        node = by_id[node_id]
        total += place * step_cost(standing, node, request.exit_weight)
        standing = node.position
        place *= discount
    return total


def make_solver(kind: OrderSolverKind, colony: AntColonySettings) -> OrderSolver:
    """Build the solver a configuration named.

    Args:
        kind: Which construction to run.
        colony: The colony's parameters. Ignored by the greedy walk, and
            still required so a renamed solver does not discover its
            numbers missing at the first rebuild.

    Returns:
        The solver.

    Raises:
        ClaveError: If the kind is not one this module builds.
    """
    if kind is OrderSolverKind.NEAREST_NEIGHBOR:
        return NearestNeighborSolver()
    if kind is OrderSolverKind.ANT_COLONY:
        return AntColonySolver(colony)
    raise ClaveError(f"no order solver named {kind!r}")


class NearestNeighborSolver:
    """The greedy walk: each next track is the cheapest step from here.

    Ties keep the earlier node in the request. The walk has no memory, so
    retaining a set does nothing.
    """

    def retain(self, node_ids: frozenset[int]) -> None:
        """Ignore the retained set. This solver stores nothing.

        Args:
            node_ids: Unused. Present so the selector can treat solvers alike.
        """
        del node_ids

    def order(self, request: OrderRequest) -> tuple[int, ...]:
        """Walk the tracks, cheapest step first.

        Args:
            request: The admissible tracks and the flange.

        Returns:
            The track ids in visit order.
        """
        _require_request(request)
        remaining = list(request.nodes)
        standing = request.origin
        chosen: list[int] = []
        while remaining:
            # `min` is stable, so an equal cost keeps the earlier node.
            best = min(
                remaining,
                key=lambda node: step_cost(standing, node, request.exit_weight),
            )
            remaining.remove(best)
            chosen.append(best.node_id)
            standing = best.position
        return tuple(chosen)


class AntColonySolver:
    """Ant system on the open path, with pheromone that outlives the call.

    Each call runs a fixed number of iterations. Every ant builds one
    permutation from the flange. Stored edges evaporate, then each ant
    deposits on the edges it used. The permutation returned is the lowest
    discounted score seen during the call, unless the caller asks for the
    last iteration's best. Edges that have never been deposited stay at
    the initial pheromone and do not evaporate, which is how a track that
    just appeared stays a stranger until some ant takes it.
    """

    def __init__(self, settings: AntColonySettings) -> None:
        """Store the parameters and an empty pheromone table.

        Args:
            settings: Counts, weights, discount, evaporation, deposit, and
                the seed.

        Raises:
            ClaveError: If a parameter would make the search vacuous or
                the score unbounded.
        """
        _require_colony(settings)
        self._settings = settings
        self._rng = np.random.default_rng(settings.seed)
        self._pheromone: dict[tuple[int, int], float] = {}

    def retain(self, node_ids: frozenset[int]) -> None:
        """Drop edges that name a track outside the live set.

        Args:
            node_ids: Tracks still admissible. An edge from the flange is
                kept when its destination is in the set.
        """
        self._pheromone = {
            edge: tau
            for edge, tau in self._pheromone.items()
            if _edge_alive(edge, node_ids)
        }

    def order(
        self, request: OrderRequest, *, incumbent: str = "best"
    ) -> tuple[int, ...]:
        """Run the colony and return one permutation of this call.

        Args:
            request: The admissible tracks and the flange.
            incumbent: `best` is the lowest score seen in the call. `last`
                is the lowest score of the final iteration, the tour the
                pheromone has just been pulled toward.

        Returns:
            Track ids, first visit first. Empty when the request is empty.

        Raises:
            ClaveError: If `incumbent` is neither `best` nor `last`.
        """
        if incumbent not in ("best", "last"):
            raise ClaveError("the incumbent is 'best' or 'last'")
        _require_request(request)
        self.retain(frozenset(node.node_id for node in request.nodes))
        if not request.nodes:
            return ()

        best_order: tuple[int, ...] | None = None
        best_cost = math.inf
        last_order: tuple[int, ...] | None = None
        built: list[tuple[tuple[int, ...], float]] = []
        for _iteration in range(self._settings.iteration_count):
            built.clear()
            last_order = None
            last_cost = math.inf
            for _ant in range(self._settings.ant_count):
                path = self._walk(request)
                cost = tour_cost(request, path, self._settings.position_discount)
                built.append((path, cost))
                if cost < best_cost:
                    best_cost = cost
                    best_order = path
                if cost < last_cost:
                    last_cost = cost
                    last_order = path
            self._evaporate()
            for path, cost in built:
                self._deposit(path, self._settings.deposit / max(cost, COST_FLOOR))
        chosen = last_order if incumbent == "last" else best_order
        if chosen is None:
            raise ClaveError("the colony produced no tour")
        return chosen

    def _walk(self, request: OrderRequest) -> tuple[int, ...]:
        """Sample one permutation from the current pheromone.

        Args:
            request: The tracks still to visit.

        Returns:
            One permutation.
        """
        remaining = list(request.nodes)
        standing_id = FLANGE_ID
        standing = request.origin
        chosen: list[int] = []
        while remaining:
            weights = [
                self._weight(standing_id, standing, node, request.exit_weight)
                for node in remaining
            ]
            node = remaining.pop(self._draw(weights))
            chosen.append(node.node_id)
            standing_id = node.node_id
            standing = node.position
        return tuple(chosen)

    def _weight(
        self,
        standing_id: int,
        standing: NDArray[np.float64],
        node: OrderNode,
        exit_weight: float,
    ) -> float:
        """Return the unnormalized probability of stepping to this node.

        Args:
            standing_id: The id pheromone is keyed by, or the flange id.
            standing: The position the step starts at.
            node: The candidate step.
            exit_weight: Dimensionless weight on belt left.

        Returns:
            Pheromone and heuristic, combined. Zero only when a stored
            edge has evaporated away.
        """
        tau = self._pheromone.get(
            (standing_id, node.node_id), self._settings.initial_pheromone
        )
        eta = 1.0 / max(step_cost(standing, node, exit_weight), COST_FLOOR)
        # `**` is typed as Any because a negative base can be complex. Both
        # bases here are non-negative, and math.pow stays a float.
        return math.pow(tau, self._settings.pheromone_weight) * math.pow(
            eta, self._settings.heuristic_weight
        )

    def _draw(self, weights: list[float]) -> int:
        """Draw an index with probability proportional to its weight.

        Args:
            weights: One positive entry per remaining node.

        Returns:
            The chosen index. A non-positive total falls back to a uniform
            draw, which is the table after a full evaporation.
        """
        total = 0.0
        for weight in weights:
            total += weight
        if not total > 0.0:
            return int(self._rng.integers(len(weights)))
        draw = float(self._rng.random()) * total
        cursor = 0.0
        for index, weight in enumerate(weights):
            cursor += weight
            if draw <= cursor:
                return index
        return len(weights) - 1

    def _evaporate(self) -> None:
        """Shrink every stored edge. Edges never stored stay at the initial value."""
        kept = 1.0 - self._settings.evaporation
        for edge in self._pheromone:
            self._pheromone[edge] *= kept

    def _deposit(self, path: tuple[int, ...], amount: float) -> None:
        """Add pheromone along one permutation, starting from the flange.

        Args:
            path: Track ids in visit order.
            amount: What each edge of this path gains.
        """
        standing_id = FLANGE_ID
        for node_id in path:
            edge = (standing_id, node_id)
            current = self._pheromone.get(edge, self._settings.initial_pheromone)
            self._pheromone[edge] = current + amount
            standing_id = node_id


def _edge_alive(edge: tuple[int, int], node_ids: frozenset[int]) -> bool:
    """Return whether both ends of an edge are still in play.

    Args:
        edge: Source and destination. The source may be the flange.
        node_ids: Tracks still admissible.

    Returns:
        Whether the edge may stay in the table.
    """
    source, destination = edge
    if destination not in node_ids:
        return False
    return source == FLANGE_ID or source in node_ids


def _require_request(request: OrderRequest) -> None:
    """Refuse a request whose ids the pheromone table could not key.

    Args:
        request: The request about to be ordered.

    Raises:
        ClaveError: If an id is negative or repeated. Negative ids would
            collide with the flange.
    """
    seen: set[int] = set()
    for node in request.nodes:
        if node.node_id < 0:
            raise ClaveError(
                f"track {node.node_id} is negative, and negative ids are reserved "
                "for the flange"
            )
        if node.node_id in seen:
            raise ClaveError(f"track {node.node_id} is in the order request twice")
        seen.add(node.node_id)


def _require_colony(settings: AntColonySettings) -> None:
    """Refuse a colony that would not search or could not score.

    Args:
        settings: The parameters the caller built. The loader checks the
            same bounds and names the configuration key; this names the
            field, because a study can build the object directly.

    Raises:
        ClaveError: If a bound is outside the range the loader accepts.
    """
    if settings.ant_count < 1 or settings.iteration_count < 1:
        raise ClaveError("the colony needs at least one ant and one iteration")
    if not 0.0 < settings.evaporation <= 1.0:
        raise ClaveError("evaporation has to be above zero and at most one")
    if settings.heuristic_weight < 0.0:
        raise ClaveError("the heuristic weight cannot be negative")
    if not settings.pheromone_weight > 0.0:
        raise ClaveError("the pheromone weight has to be positive")
    if not settings.deposit > 0.0 or not settings.initial_pheromone > 0.0:
        raise ClaveError("deposit and the initial pheromone have to be positive")
    if not 0.0 < settings.position_discount <= 1.0:
        raise ClaveError("the position discount has to be above zero and at most one")
