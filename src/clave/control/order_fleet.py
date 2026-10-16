"""Replay a moving field and score how a tour holds together.

The belt study stops where enumeration still fits. This one does not. A
fixed population of points moves inside a square, a fraction of the ids
are replaced every epoch, and other robots delete further ids before the
planner looks. There is no anchor radius: every epoch hands the solver
the raw positions. The depot stays at the center, so the planner's own
choice of head does not fork the world the others are picking from.

The score is open-path length. The exit weight is zero, because a
nonzero weight would ask 2-opt, which only exchanges geometric edges, to
judge a different objective. The reference is 2-opt started from the
greedy walk. It is a local descent, not a proof of the shortest path.

Run it with `python -m clave.control.order_fleet`.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.control.order import (
    FLANGE_ID,
    AntColonySolver,
    NearestNeighborSolver,
    OrderNode,
    OrderRequest,
    tour_cost,
)
from clave.control.settings import AntColonySettings, ControlSettings
from clave.errors import ClaveError
from clave.world.config import load

# Bands on the ratio to the 2-opt path. They are the study's definition of
# "good enough", reported beside the mean ratio rather than tuned.
WITHIN_10 = 1.10
WITHIN_20 = 1.20

# A reversal has to shorten the path by more than float noise.
_IMPROVEMENT_FLOOR = 1e-12

# Below this length a ratio against the reference is not a length.
_LENGTH_FLOOR = 1e-12

# The fleet question is open-path length. 2-opt exchanges geometric edges,
# so a nonzero exit weight would make it the reference for another score.
_EXIT_WEIGHT = 0.0

_POSITION_DISCOUNT = 1.0


@dataclass(frozen=True)
class FleetFactors:
    """How large a moving field to replay.

    Attributes:
        populations: How many points the field holds before other robots
            take some.
        epochs: How many times the field moves, pops, and is stolen from.
        robots: How many robots share the field, including the planner.
            The others each take one point per epoch.
        side_meters: Side of the square the points bounce in.
        speed_meters_per_second: Speed of every point.
        epoch_seconds: Time between solves.
        pop_fraction: Fraction of ids replaced each epoch, before theft.
        iteration_counts: Colony iteration counts to replay.
        evaporations: Colony evaporations to replay.
        seed: Seed of the field and of every colony in the replay.
    """

    populations: tuple[int, ...] = (12, 24, 36)
    epochs: int = 40
    robots: int = 4
    side_meters: float = 4.0
    speed_meters_per_second: float = 0.35
    epoch_seconds: float = 0.25
    pop_fraction: float = 0.08
    iteration_counts: tuple[int, ...] = (5, 20)
    evaporations: tuple[float, ...] = (0.20, 0.50)
    seed: int = 0


@dataclass
class _Point:
    """One moving id. The id is the pheromone key, not the place."""

    node_id: int
    x: float
    y: float
    vx: float
    vy: float


@dataclass(frozen=True)
class _Method:
    """One column of the replay."""

    solver: str
    kind: str
    memory: str
    iteration_count: int | None
    evaporation: float | None
    incumbent: str | None
    settings: AntColonySettings | None


def run_fleet_study(factors: FleetFactors | None = None) -> dict[str, Any]:
    """Replay every solver on one shared sequence per population.

    Args:
        factors: The field and the colony grid. The default is the
            comparison the research note quotes.

    Returns:
        Populations, the colony weights taken from the runtime file, and
        one row per solver.

    Raises:
        ClaveError: If a factor could not generate a field the theft
            rule can share.
    """
    chosen = factors if factors is not None else FleetFactors()
    _require_factors(chosen)
    colony = _colony(chosen)
    origin = np.zeros(3, dtype=np.float64)
    populations: list[dict[str, float | int]] = []
    rows: list[dict[str, Any]] = []
    for population in chosen.populations:
        started = time.perf_counter()
        frames = _frames(chosen, population)
        reference, reference_costs, reference_times = _reference(frames, origin)
        seen = _mean([float(len(frame)) for frame in frames])
        removed = _removed(frames)
        shared = {
            "population": population,
            "seen_mean": seen,
            "mean_removed": removed,
        }
        rows.append(
            _row(
                shared,
                "two_opt",
                "none",
                None,
                None,
                None,
                frames,
                reference,
                reference_times,
                reference_costs,
                origin,
            )
        )
        for method in _methods(chosen, colony):
            orders, times = _replay(method, frames, origin)
            rows.append(
                _row(
                    shared,
                    method.solver,
                    method.memory,
                    method.iteration_count,
                    method.evaporation,
                    method.incumbent,
                    frames,
                    orders,
                    times,
                    reference_costs,
                    origin,
                )
            )
        populations.append(
            {
                "population": population,
                "seen_mean": seen,
                "mean_removed": removed,
                "seconds": time.perf_counter() - started,
            }
        )
    return {
        "seed": chosen.seed,
        "epochs": chosen.epochs,
        "robots": chosen.robots,
        "side_meters": chosen.side_meters,
        "speed_meters_per_second": chosen.speed_meters_per_second,
        "epoch_seconds": chosen.epoch_seconds,
        "pop_fraction": chosen.pop_fraction,
        "exit_weight": _EXIT_WEIGHT,
        "position_discount": _POSITION_DISCOUNT,
        "damping": "none",
        "depot_meters": [0.0, 0.0, 0.0],
        "reference": "two_opt_from_nearest_neighbor",
        "within_10": WITHIN_10,
        "within_20": WITHIN_20,
        "ant_count": colony.ant_count,
        "pheromone_weight": colony.pheromone_weight,
        "heuristic_weight": colony.heuristic_weight,
        "deposit": colony.deposit,
        "initial_pheromone": colony.initial_pheromone,
        "populations": populations,
        "rows": rows,
    }


def repair_order(previous: tuple[int, ...], request: OrderRequest) -> tuple[int, ...]:
    """Keep the surviving order and insert each new id where it costs least.

    Args:
        previous: The order from the epoch before. Empty on the first.
        request: The tracks still here, in the order newcomers are tried.

    Returns:
        A permutation of the request. Survivors keep their relative order.
    """
    live = {node.node_id: node for node in request.nodes}
    kept = [node_id for node_id in previous if node_id in live]
    present = set(kept)
    for node in request.nodes:
        if node.node_id in present:
            continue
        _insert(kept, node, request.origin, live)
        present.add(node.node_id)
    return tuple(kept)


def two_opt(request: OrderRequest, order: tuple[int, ...]) -> tuple[int, ...]:
    """Reverse segments of an open path while the boundary edges shorten.

    Args:
        request: The tracks and the flange the path starts from.
        order: A permutation to descend from.

    Returns:
        A permutation no longer than `order` under Euclidean length.
        Interior edges of a reversed segment cancel because distance is
        symmetric, so each trial is the two boundary edges only.
    """
    if len(order) < 2:
        return order
    by_id = {node.node_id: node for node in request.nodes}
    ids = list(order)
    xs = [float(request.origin[0])]
    ys = [float(request.origin[1])]
    zs = [float(request.origin[2])]
    for node_id in ids:
        position = by_id[node_id].position
        xs.append(float(position[0]))
        ys.append(float(position[1]))
        zs.append(float(position[2]))
    count = len(ids)
    improved = True
    while improved:
        improved = False
        for start in range(count - 1):
            for end in range(start + 1, count):
                if _reversal_helps(xs, ys, zs, start, end):
                    ids[start : end + 1] = reversed(ids[start : end + 1])
                    _reverse_span(xs, start + 1, end + 1)
                    _reverse_span(ys, start + 1, end + 1)
                    _reverse_span(zs, start + 1, end + 1)
                    improved = True
                    break
            if improved:
                break
    return tuple(ids)


def main() -> None:
    """Write the fleet report and print one line per row."""
    report = run_fleet_study()
    destination = Path("runs") / "debug" / "order-solvers"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "fleet.json"
    text = json.dumps(report, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    lines = [_line(row) for row in report["rows"]]
    artifact = Path("/opt/cursor/artifacts")
    if artifact.is_dir():
        (artifact / "order-fleet.json").write_text(text, encoding="utf-8")
        (artifact / "order-fleet-summary.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    print(path)
    for item in report["populations"]:
        print(f"population {item['population']} in {item['seconds']:.1f}s")
    for line in lines:
        print(line)


def _require_factors(factors: FleetFactors) -> None:
    """Refuse a field the theft rule cannot share.

    Args:
        factors: The requested replay.

    Raises:
        ClaveError: If a count, a speed, or a rate could not build one
            sequence for every solver.
    """
    if not factors.populations or any(size < 2 for size in factors.populations):
        raise ClaveError("the fleet study needs populations of at least two")
    if factors.epochs < 1:
        raise ClaveError("the fleet study needs at least one epoch")
    if factors.robots < 2:
        raise ClaveError("the fleet study needs at least two robots")
    if any(factors.robots - 1 >= size for size in factors.populations):
        raise ClaveError("other robots cannot take every point")
    if factors.side_meters <= 0.0 or factors.epoch_seconds <= 0.0:
        raise ClaveError("the field side and the epoch have to be positive")
    if factors.speed_meters_per_second < 0.0:
        raise ClaveError("speed cannot be negative")
    if not 0.0 <= factors.pop_fraction < 1.0:
        raise ClaveError("the pop fraction has to be at least zero and below one")
    if not factors.iteration_counts or any(
        count < 1 for count in factors.iteration_counts
    ):
        raise ClaveError("colony iterations have to be at least one")
    if not factors.evaporations or any(
        not 0.0 < rate <= 1.0 for rate in factors.evaporations
    ):
        raise ClaveError("evaporation has to be above zero and at most one")
    if factors.seed < 0:
        raise ClaveError("the fleet seed has to be a non-negative integer")


def _colony(factors: FleetFactors) -> AntColonySettings:
    """Return the runtime colony, seeded and discounted for path length.

    Args:
        factors: Supplies the seed. Counts and weights stay in the runtime
            file. The position discount is forced to one because the
            reference is an undiscounted length.

    Returns:
        The colony the grid then varies in iterations and evaporation.
    """
    root = Path(__file__).resolve().parents[3]
    shipped = ControlSettings.load(
        load(root / "configs" / "runtime" / "control.yml")
    ).selection.ant_colony
    return replace(shipped, seed=factors.seed, position_discount=_POSITION_DISCOUNT)


def _methods(factors: FleetFactors, colony: AntColonySettings) -> tuple[_Method, ...]:
    """Return the walk, the repair, and the colony grid."""
    methods: list[_Method] = [
        _Method("nearest_neighbor", "walk", "none", None, None, None, None),
        _Method("repair", "repair", "previous_order", None, None, None, None),
    ]
    for iterations in factors.iteration_counts:
        for evaporation in factors.evaporations:
            settings = replace(
                colony, iteration_count=iterations, evaporation=evaporation
            )
            for memory, incumbent in (
                ("cold", "best"),
                ("warm", "best"),
                ("warm", "last"),
            ):
                methods.append(
                    _Method(
                        "ant_colony",
                        "colony",
                        memory,
                        iterations,
                        evaporation,
                        incumbent,
                        settings,
                    )
                )
    return tuple(methods)


def _frames(
    factors: FleetFactors, population: int
) -> tuple[tuple[OrderNode, ...], ...]:
    """Draw one sequence: move, replace ids, then let the other robots take.

    Args:
        factors: Motion, replacement, and how many points are stolen.
        population: How many points exist between thefts.

    Returns:
        One request body per epoch, in id order. The stolen ids are
        absent. Their replacements appear on a later epoch, after they
        have moved with the field.
    """
    rng = np.random.default_rng(factors.seed + population)
    half = factors.side_meters / 2.0
    speed = factors.speed_meters_per_second
    next_id = population
    points = [_spawn(rng, half, speed, index) for index in range(population)]
    stolen = factors.robots - 1
    frames: list[tuple[OrderNode, ...]] = []
    for _epoch in range(factors.epochs):
        for point in points:
            # Velocity already has magnitude `speed`. Advance by the epoch,
            # then fold any wall crossing back into the square.
            point.x, point.vx = _reflect(
                point.x + point.vx * factors.epoch_seconds, point.vx, half
            )
            point.y, point.vy = _reflect(
                point.y + point.vy * factors.epoch_seconds, point.vy, half
            )
        retire = _take(rng, points, _turnover(factors.pop_fraction, population, stolen))
        points = [point for point in points if point.node_id not in retire]
        for _spare in range(len(retire)):
            points.append(_spawn(rng, half, speed, next_id))
            next_id += 1
        taken = _take(rng, points, stolen)
        visible = [point for point in points if point.node_id not in taken]
        frames.append(_nodes(visible))
        points = [point for point in points if point.node_id not in taken]
        for _spare in range(len(taken)):
            points.append(_spawn(rng, half, speed, next_id))
            next_id += 1
    return tuple(frames)


def _spawn(rng: np.random.Generator, half: float, speed: float, node_id: int) -> _Point:
    """Return a new point inside the square, at the field's speed."""
    angle = float(rng.random()) * math.tau
    return _Point(
        node_id=node_id,
        x=float(rng.uniform(-half, half)),
        y=float(rng.uniform(-half, half)),
        vx=speed * math.cos(angle),
        vy=speed * math.sin(angle),
    )


def _reflect(position: float, velocity: float, limit: float) -> tuple[float, float]:
    """Fold one coordinate back into the closed interval.

    Args:
        position: The coordinate after the step.
        velocity: The component along that axis. A crossing negates it.
        limit: Half the side of the square.

    Returns:
        The folded coordinate and the velocity after the reflections.
    """
    for _fold in range(16):
        if position > limit:
            position = (2.0 * limit) - position
            velocity = -velocity
        elif position < -limit:
            position = (-2.0 * limit) - position
            velocity = -velocity
        else:
            return position, velocity
    if position > limit:
        return limit, -abs(velocity)
    if position < -limit:
        return -limit, abs(velocity)
    return position, velocity


def _turnover(fraction: float, population: int, reserve: int) -> int:
    """How many ids to replace without leaving the thieves nothing.

    Args:
        fraction: Requested share of the population.
        population: Points present before replacement.
        reserve: Points that have to remain so the other robots can take
            theirs after the replacement.

    Returns:
        A count that leaves at least `reserve` points.
    """
    if fraction <= 0.0 or population <= reserve:
        return 0
    raw = int(round(fraction * population))
    raw = max(raw, 1)
    return min(raw, population - reserve)


def _take(rng: np.random.Generator, points: list[_Point], count: int) -> set[int]:
    """Draw ids without replacement.

    The candidates are sorted first, so the order of `points` cannot
    change which ids the same seed draws.
    """
    if count <= 0:
        return set()
    ids = np.asarray(sorted(point.node_id for point in points), dtype=np.int64)
    picked = np.asarray(rng.choice(ids, size=count, replace=False)).reshape(-1)
    return {int(item) for item in picked}


def _nodes(points: list[_Point]) -> tuple[OrderNode, ...]:
    """Return the request body, sorted by id so a tie breaks the same way every time."""
    ordered = sorted(points, key=lambda point: point.node_id)
    return tuple(
        OrderNode(
            node_id=point.node_id,
            position=np.asarray((point.x, point.y, 0.0), dtype=np.float64),
            distance_before_leaving=0.0,
        )
        for point in ordered
    )


def _reference(
    frames: tuple[tuple[OrderNode, ...], ...], origin: NDArray[np.float64]
) -> tuple[list[tuple[int, ...]], list[float], list[float]]:
    """Descend from the greedy walk and time that descent.

    Returns:
        The polished orders, their lengths, and the milliseconds each
        descent took, including the walk it started from.
    """
    walk = NearestNeighborSolver()
    orders: list[tuple[int, ...]] = []
    costs: list[float] = []
    times: list[float] = []
    for nodes in frames:
        request = OrderRequest(nodes, origin, _EXIT_WEIGHT)
        started = time.perf_counter()
        polished = two_opt(request, walk.order(request))
        times.append((time.perf_counter() - started) * 1e3)
        orders.append(polished)
        costs.append(tour_cost(request, polished, _POSITION_DISCOUNT))
    return orders, costs, times


def _replay(
    method: _Method,
    frames: tuple[tuple[OrderNode, ...], ...],
    origin: NDArray[np.float64],
) -> tuple[list[tuple[int, ...]], list[float]]:
    """Run one solver across the frames.

    A cold colony is a new solver every epoch, so its pheromone and its
    sampler both restart. A warm colony is one solver, and `order` already
    drops edges that name a track the frame no longer holds.
    """
    orders: list[tuple[int, ...]] = []
    times: list[float] = []
    previous: tuple[int, ...] = ()
    walk = NearestNeighborSolver()
    warm: AntColonySolver | None = None
    if method.memory == "warm":
        if method.settings is None or method.incumbent is None:
            raise ClaveError("a warm colony needs its settings")
        warm = AntColonySolver(method.settings)
    for nodes in frames:
        request = OrderRequest(nodes, origin, _EXIT_WEIGHT)
        started = time.perf_counter()
        if method.kind == "repair":
            order = repair_order(previous, request)
        elif method.memory == "cold":
            if method.settings is None or method.incumbent is None:
                raise ClaveError("a cold colony needs its settings")
            order = AntColonySolver(method.settings).order(
                request, incumbent=method.incumbent
            )
        elif warm is not None and method.incumbent is not None:
            order = warm.order(request, incumbent=method.incumbent)
        else:
            order = walk.order(request)
        times.append((time.perf_counter() - started) * 1e3)
        orders.append(order)
        previous = order
    return orders, times


def _row(
    shared: dict[str, float | int],
    solver: str,
    memory: str,
    iteration_count: int | None,
    evaporation: float | None,
    incumbent: str | None,
    frames: tuple[tuple[OrderNode, ...], ...],
    orders: list[tuple[int, ...]],
    times: list[float],
    reference_costs: list[float],
    origin: NDArray[np.float64],
) -> dict[str, Any]:
    """Score one replay against the 2-opt lengths."""
    from clave.control.order_study import kendall_fraction

    ratios: list[float] = []
    within_10: list[float] = []
    within_20: list[float] = []
    shorter: list[float] = []
    paths: list[float] = []
    keeps: list[float] = []
    kendalls: list[float] = []
    flips: list[float] = []
    for index, nodes in enumerate(frames):
        request = OrderRequest(nodes, origin, _EXIT_WEIGHT)
        order = orders[index]
        cost = tour_cost(request, order, _POSITION_DISCOUNT)
        reference = reference_costs[index]
        ratio = cost / reference if reference > _LENGTH_FLOOR else 1.0
        ratios.append(ratio)
        within_10.append(1.0 if ratio <= WITHIN_10 else 0.0)
        within_20.append(1.0 if ratio <= WITHIN_20 else 0.0)
        shorter.append(1.0 if ratio < 1.0 - 1e-9 else 0.0)
        paths.append(cost)
        if index == 0:
            continue
        live = {node.node_id for node in nodes}
        previous = orders[index - 1]
        kept = _edge_keep(previous, order, live)
        if kept is not None:
            keeps.append(kept)
        if sum(1 for node_id in previous if node_id in live) >= 2:
            kendalls.append(kendall_fraction(previous, order))
        if previous and previous[0] in live:
            same = bool(order) and order[0] == previous[0]
            flips.append(0.0 if same else 1.0)
    return {
        **shared,
        "solver": solver,
        "memory": memory,
        "iteration_count": iteration_count,
        "evaporation": evaporation,
        "incumbent": incumbent,
        "mean_quality_ratio": _mean(ratios),
        "fraction_within_10": _mean(within_10),
        "fraction_within_20": _mean(within_20),
        "fraction_shorter": _mean(shorter),
        "mean_edge_keep": _mean(keeps),
        "mean_kendall": _mean(kendalls),
        "head_flip": _mean(flips),
        "median_milliseconds": _median(times),
        "mean_path_meters": _mean(paths),
        "mean_reference_meters": _mean(reference_costs),
        "edge_epochs": len(keeps),
        "kendall_epochs": len(kendalls),
        "flip_epochs": len(flips),
    }


def _edge_keep(
    previous: tuple[int, ...], order: tuple[int, ...], live: set[int]
) -> float | None:
    """Return the fraction of still-live successive edges the new order keeps.

    The flange is always live. An edge whose track was stolen or replaced
    is not a failure to keep it, so it stays out of the fraction. None
    means nothing survived to keep.
    """
    surviving = [
        edge
        for edge in _edges(previous)
        if edge[1] in live and (edge[0] == FLANGE_ID or edge[0] in live)
    ]
    if not surviving:
        return None
    current = set(_edges(order))
    held = sum(1 for edge in surviving if edge in current)
    return held / len(surviving)


def _edges(order: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    """Return successive pairs, starting at the flange."""
    pairs: list[tuple[int, int]] = []
    source = FLANGE_ID
    for node_id in order:
        pairs.append((source, node_id))
        source = node_id
    return tuple(pairs)


def _removed(frames: tuple[tuple[OrderNode, ...], ...]) -> float:
    """Return the mean number of ids that do not survive into the next epoch."""
    lost: list[float] = []
    for previous, current in zip(frames, frames[1:], strict=False):
        before = {node.node_id for node in previous}
        after = {node.node_id for node in current}
        lost.append(float(len(before - after)))
    return _mean(lost)


def _insert(
    kept: list[int],
    node: OrderNode,
    origin: NDArray[np.float64],
    live: dict[int, OrderNode],
) -> None:
    """Put `node` where the extra length is smallest. An earlier slot wins a tie."""
    best_slot = 0
    best_extra = math.inf
    for slot in range(len(kept) + 1):
        pred = origin if slot == 0 else live[kept[slot - 1]].position
        extra = _span(pred, node.position)
        if slot < len(kept):
            succ = live[kept[slot]].position
            extra += _span(node.position, succ) - _span(pred, succ)
        if extra < best_extra:
            best_extra = extra
            best_slot = slot
    kept.insert(best_slot, node.node_id)


def _reversal_helps(
    xs: list[float], ys: list[float], zs: list[float], start: int, end: int
) -> bool:
    """Return whether reversing the path segment shortens the two boundary edges.

    `start` and `end` index the path, not the coordinate list. Coordinate
    0 is the flange.
    """
    pred_x, pred_y, pred_z = xs[start], ys[start], zs[start]
    head_x, head_y, head_z = xs[start + 1], ys[start + 1], zs[start + 1]
    tail_x, tail_y, tail_z = xs[end + 1], ys[end + 1], zs[end + 1]
    old = _hypot(pred_x, pred_y, pred_z, head_x, head_y, head_z)
    new = _hypot(pred_x, pred_y, pred_z, tail_x, tail_y, tail_z)
    if end + 2 < len(xs):
        succ_x, succ_y, succ_z = xs[end + 2], ys[end + 2], zs[end + 2]
        old += _hypot(tail_x, tail_y, tail_z, succ_x, succ_y, succ_z)
        new += _hypot(head_x, head_y, head_z, succ_x, succ_y, succ_z)
    return new + _IMPROVEMENT_FLOOR < old


def _reverse_span(values: list[float], start: int, end: int) -> None:
    """Reverse a coordinate span, inclusive."""
    values[start : end + 1] = reversed(values[start : end + 1])


def _hypot(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> float:
    """Return the distance between two explicit coordinates."""
    return math.hypot(ax - bx, ay - by, az - bz)


def _span(one: NDArray[np.float64], other: NDArray[np.float64]) -> float:
    """Return the distance between two stored positions."""
    return _hypot(
        float(one[0]),
        float(one[1]),
        float(one[2]),
        float(other[0]),
        float(other[1]),
        float(other[2]),
    )


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean. An empty column is zero."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    """Return the median. An empty column is zero."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _line(row: dict[str, Any]) -> str:
    """Return one terminal row."""
    iteration = row["iteration_count"]
    evaporation = row["evaporation"]
    incumbent = row["incumbent"]
    iteration_text = "-" if iteration is None else str(iteration)
    evaporation_text = "-" if evaporation is None else f"{evaporation:.2f}"
    incumbent_text = "-" if incumbent is None else str(incumbent)
    return (
        f"n={row['population']} seen={row['seen_mean']:.1f} "
        f"{row['solver']} {row['memory']} {incumbent_text} "
        f"i={iteration_text} e={evaporation_text} "
        f"ratio={row['mean_quality_ratio']:.3f} "
        f"within10={row['fraction_within_10']:.2f} "
        f"within20={row['fraction_within_20']:.2f} "
        f"keep={row['mean_edge_keep']:.3f} "
        f"kendall={row['mean_kendall']:.3f} "
        f"flip={row['head_flip']:.3f} "
        f"{row['median_milliseconds']:.2f}ms"
    )


if __name__ == "__main__":
    main()
