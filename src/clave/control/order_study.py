"""Compare the greedy walk with the ant colony on the queue's own cost.

The study is the evidence behind
`docs/research/object-order-solvers.md`. It is not on the control path.
A call draws scenes inside the reachable window, orders them with both
solvers, and scores the orders against every permutation of the same
scene. The reference is exact at the populations this function draws.
Past eight tracks it refuses rather than guessing.

Run it with `python -m clave.control.order_study`.
"""

from __future__ import annotations

import itertools
import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.control.order import (
    AntColonySolver,
    NearestNeighborSolver,
    OrderNode,
    OrderRequest,
    tour_cost,
)
from clave.control.settings import AntColonySettings, ControlSettings
from clave.control.trajectory import distance
from clave.errors import ClaveError
from clave.world.config import load

# The reachable window along the belt, from docs/measurements.md: 2.071 m,
# from -1.034 m to +1.034 m. The study draws inside that interval. The belt
# is longer; the arm is not.
WINDOW_HALF_LENGTH_METERS = 1.034

# Grasp height the selection tests command. Objects share it, so the
# vertical gap to the park pose is part of every travel.
OBJECT_Z_METERS = 0.945

# Denser than the feeder, so about five objects sit in the window at once,
# near the measured peak of six. The line case uses the feeder spacing.
DENSE_SPACING_METERS = 0.45

URGENT_TRACK = 99
"""Track inserted once the colony has settled, in the scripted arrival."""

_PERMUTATION_LIMIT = 8
_OPTIMAL_GAP = 1e-8
_GAP_FLOOR = 1e-12


@dataclass(frozen=True)
class StudyFactors:
    """How large a comparison to run.

    Attributes:
        populations: How many tracks a static scene holds.
        instances: Scenes drawn at each population, before the cap at six
            and eight tracks.
        exit_weights: Weights the static scenes are scored at.
        discounts: Position discounts the colony is scored at.
        jitter_count: Perturbed copies of each stability scene.
        jitter_sigma_meters: Standard deviation of the planar perturbation.
        stability_populations: Populations the repeated-call section uses.
        static_repeats: Calls in a row on one frozen scene.
        birth_epochs: Steps of the rolling belt.
        shock_iterations: Colony iteration counts on the scripted arrival.
        shock_settle: Calls on the settled scene before the arrival.
        shock_follow: Calls after the arrival, pheromone carried through.
        seed: Seed of the scene generator. Colony seeds stay in their settings.
    """

    populations: tuple[int, ...] = (2, 3, 4, 5, 6, 8)
    instances: int = 20
    exit_weights: tuple[float, ...] = (0.0, 1.0)
    discounts: tuple[float, ...] = (1.0, 0.5)
    jitter_count: int = 6
    jitter_sigma_meters: float = 0.030
    stability_populations: tuple[int, ...] = (3, 6)
    static_repeats: int = 8
    birth_epochs: int = 40
    shock_iterations: tuple[int, ...] = (1, 5, 20, 50)
    shock_settle: int = 8
    shock_follow: int = 12
    seed: int = 0


def urgent_arrival(
    colony: AntColonySettings,
    *,
    exit_weight: float,
    settle_calls: int,
    follow_calls: int,
) -> dict[str, Any]:
    """Settle a colony, then insert one urgent track and keep sampling.

    The settled tracks share a slack. The arrival has almost none, and it
    stands further along the same line, so the greedy walk takes it first
    whenever the exit weight is positive. The colony keeps the pheromone
    from the settled calls.

    Args:
        colony: The colony under test, including how many iterations a call runs.
        exit_weight: Dimensionless weight on belt left.
        settle_calls: Calls before the arrival.
        follow_calls: Calls after it.

    Returns:
        The greedy head after the arrival, the colony's heads on the
        following calls, and the first following call whose head matches
        the greedy head, or None if none does.
    """
    origin = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    settled = OrderRequest(
        nodes=_shock_nodes(urgent=False), origin=origin, exit_weight=exit_weight
    )
    arrived = OrderRequest(
        nodes=_shock_nodes(urgent=True), origin=origin, exit_weight=exit_weight
    )
    colony_solver = AntColonySolver(colony)
    for _call in range(settle_calls):
        colony_solver.order(settled)
    greedy_head = NearestNeighborSolver().order(arrived)[0]
    heads: list[int] = []
    matched: int | None = None
    for index in range(follow_calls):
        head = colony_solver.order(arrived)[0]
        heads.append(head)
        if matched is None and head == greedy_head:
            matched = index
    return {
        "greedy_head": greedy_head,
        "colony_heads": heads,
        "calls_until_greedy_head": matched,
    }


def run_study(factors: StudyFactors | None = None) -> dict[str, Any]:
    """Run the comparison and return a JSON-ready report.

    Args:
        factors: Sample sizes. The shipped colony parameters and the park
            pose come from the runtime configuration either way.

    Returns:
        Scene constants, static aggregates, stability, the scripted
        arrival, and the rolling belt.
    """
    chosen = factors or StudyFactors()
    scene = _scene()
    colony = scene["colony"]
    origin = scene["origin"]
    arm_speed = scene["arm_speed"]
    belt_speed = scene["belt_speed"]
    rng = np.random.default_rng(chosen.seed)

    drawn = {
        population: [
            _draw_nodes(
                rng,
                population,
                scene["entry"],
                scene["exit"],
                scene["lateral"],
            )
            for _index in range(_instance_count(population, chosen.instances))
        ]
        for population in chosen.populations
    }

    static: list[dict[str, Any]] = []
    for population, scenes in drawn.items():
        for exit_weight in chosen.exit_weights:
            references = [
                _reference(
                    OrderRequest(nodes=nodes, origin=origin, exit_weight=exit_weight),
                    chosen.discounts,
                    arm_speed,
                    belt_speed,
                )
                for nodes in scenes
            ]
            for discount in chosen.discounts:
                tuned = replace(colony, position_discount=discount)
                greedy_rows: list[dict[str, float]] = []
                colony_rows: list[dict[str, float]] = []
                for nodes, reference in zip(scenes, references, strict=True):
                    request = OrderRequest(
                        nodes=nodes, origin=origin, exit_weight=exit_weight
                    )
                    greedy = _evaluate(
                        NearestNeighborSolver(),
                        request,
                        reference,
                        discount,
                        arm_speed,
                        belt_speed,
                    )
                    greedy["agrees_greedy"] = 1.0
                    colony_row = _evaluate(
                        AntColonySolver(tuned),
                        request,
                        reference,
                        discount,
                        arm_speed,
                        belt_speed,
                    )
                    colony_row["agrees_greedy"] = _same_head(colony_row, greedy)
                    greedy_rows.append(greedy)
                    colony_rows.append(colony_row)
                static.append(
                    {
                        "population": population,
                        "exit_weight": exit_weight,
                        "position_discount": discount,
                        "instances": len(scenes),
                        "nearest_neighbor": _aggregate(greedy_rows),
                        "ant_colony": _aggregate(colony_rows),
                    }
                )

    stability = _stability(chosen, scene, drawn, rng)
    shock = [
        {
            "iteration_count": iterations,
            **urgent_arrival(
                replace(colony, iteration_count=iterations),
                exit_weight=1.0,
                settle_calls=chosen.shock_settle,
                follow_calls=chosen.shock_follow,
            ),
        }
        for iterations in chosen.shock_iterations
    ]
    line = [
        _rolling(
            colony=colony,
            origin=origin,
            exit_weight=1.0,
            spacing=spacing,
            entry=scene["entry"],
            exit_x=scene["exit"],
            belt_speed=belt_speed,
            arm_speed=arm_speed,
            epochs=chosen.birth_epochs,
            lateral=scene["lateral"],
        )
        for spacing in (scene["spacing"], DENSE_SPACING_METERS)
    ]
    return {
        "scene": _public_scene(scene),
        "factors": {
            "instances": chosen.instances,
            "exit_weights": list(chosen.exit_weights),
            "discounts": list(chosen.discounts),
            "jitter_sigma_meters": chosen.jitter_sigma_meters,
            "static_repeats": chosen.static_repeats,
            "birth_epochs": chosen.birth_epochs,
            "shock_settle": chosen.shock_settle,
            "shock_follow": chosen.shock_follow,
            "seed": chosen.seed,
        },
        "static": static,
        "stability": stability,
        "shock": shock,
        "line": line,
    }


def main() -> None:
    """Write the report next to other debug runs and print the path."""
    report = run_study()
    destination = Path("runs") / "debug" / "order-solvers"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "study.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    artifact = Path("/opt/cursor/artifacts")
    if artifact.is_dir():
        (artifact / "order-study.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    print(path)
    for row in report["static"]:
        if row["exit_weight"] != 1.0 or row["position_discount"] != 1.0:
            continue
        greedy = row["nearest_neighbor"]
        colony = row["ant_colony"]
        print(
            f"n={row['population']} "
            f"greedy {greedy['median_milliseconds']:.3f} ms "
            f"gap {greedy['mean_travel_gap']:.4f} "
            f"colony {colony['median_milliseconds']:.3f} ms "
            f"gap {colony['mean_travel_gap']:.4f} "
            f"head {colony['agrees_greedy']:.2f}"
        )
    # The fleet replay is a second report. Imported here so loading the belt
    # study does not load that module.
    from clave.control.order_fleet import main as fleet_main

    fleet_main()


@dataclass(frozen=True)
class _Reference:
    """Exact scores of one request, for every discount under test."""

    best_travel: float
    best_tardiness: float
    tardiness_head: int | None
    discounted: dict[float, tuple[float, int | None]]


def _scene() -> dict[str, Any]:
    """Load the geometry and the colony the study is not allowed to invent."""
    root = Path(__file__).resolve().parents[3]
    control = ControlSettings.load(load(root / "configs" / "runtime" / "control.yml"))
    world = load(root / "configs" / "world" / "sorting_line.yml")
    belt = world["belt"]
    spawn = world["spawn"]
    lateral = spawn["lateral_offset_meters"]
    return {
        "origin": np.asarray(control.task.park_position_world, dtype=np.float64),
        "arm_speed": control.motion.max_speed,
        "belt_speed": _midpoint(belt["speed_meters_per_second"]),
        "spacing": _midpoint(spawn["spacing_meters"]),
        "entry": -WINDOW_HALF_LENGTH_METERS,
        "exit": WINDOW_HALF_LENGTH_METERS,
        "lateral": (float(lateral[0]), float(lateral[1])),
        "colony": control.selection.ant_colony,
        "anchor_radius": control.selection.anchor_radius,
    }


def _public_scene(scene: dict[str, Any]) -> dict[str, Any]:
    """Drop arrays the JSON encoder cannot hold."""
    colony: AntColonySettings = scene["colony"]
    return {
        "window_meters": [scene["entry"], scene["exit"]],
        "lateral_meters": list(scene["lateral"]),
        "object_z_meters": OBJECT_Z_METERS,
        "park_meters": [float(value) for value in scene["origin"]],
        "arm_speed_meters_per_second": scene["arm_speed"],
        "belt_speed_meters_per_second": scene["belt_speed"],
        "feeder_spacing_meters": scene["spacing"],
        "dense_spacing_meters": DENSE_SPACING_METERS,
        "anchor_radius_meters": scene["anchor_radius"],
        "ant_colony": {
            "ant_count": colony.ant_count,
            "iteration_count": colony.iteration_count,
            "evaporation": colony.evaporation,
            "pheromone_weight": colony.pheromone_weight,
            "heuristic_weight": colony.heuristic_weight,
            "deposit": colony.deposit,
            "initial_pheromone": colony.initial_pheromone,
            "position_discount": colony.position_discount,
            "seed": colony.seed,
        },
    }


def _stability(
    factors: StudyFactors,
    scene: dict[str, Any],
    drawn: dict[int, list[tuple[OrderNode, ...]]],
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Repeat a frozen scene, then nudge it by more than an anchor radius."""
    rows: list[dict[str, Any]] = []
    for population in factors.stability_populations:
        scenes = drawn.get(population)
        if scenes is None:
            scenes = [
                _draw_nodes(
                    rng,
                    population,
                    scene["entry"],
                    scene["exit"],
                    scene["lateral"],
                )
                for _index in range(min(4, factors.instances))
            ]
        for exit_weight in factors.exit_weights:
            greedy_flips: list[float] = []
            colony_flips: list[float] = []
            colony_kendall: list[float] = []
            greedy_jitter: list[float] = []
            colony_jitter: list[float] = []
            for nodes in scenes:
                request = OrderRequest(
                    nodes=nodes, origin=scene["origin"], exit_weight=exit_weight
                )
                greedy_order = NearestNeighborSolver().order(request)
                greedy_again = NearestNeighborSolver().order(request)
                greedy_flips.append(_flipped(greedy_order, greedy_again))
                colony = AntColonySolver(scene["colony"])
                previous = colony.order(request)
                flips = 0
                kendall = 0.0
                for _repeat in range(factors.static_repeats - 1):
                    current = colony.order(request)
                    flips += int(_flipped(previous, current))
                    kendall += kendall_fraction(previous, current)
                    previous = current
                colony_flips.append(flips / max(1, factors.static_repeats - 1))
                colony_kendall.append(kendall / max(1, factors.static_repeats - 1))
                jitter_flips_g = 0
                jitter_flips_c = 0
                for _jitter in range(factors.jitter_count):
                    nudged = _nudge(nodes, rng, factors.jitter_sigma_meters)
                    nudged_request = OrderRequest(
                        nodes=nudged,
                        origin=scene["origin"],
                        exit_weight=exit_weight,
                    )
                    jitter_flips_g += int(
                        _flipped(
                            greedy_order, NearestNeighborSolver().order(nudged_request)
                        )
                    )
                    jitter_flips_c += int(
                        _flipped(previous, colony.order(nudged_request))
                    )
                if factors.jitter_count:
                    greedy_jitter.append(jitter_flips_g / factors.jitter_count)
                    colony_jitter.append(jitter_flips_c / factors.jitter_count)
            rows.append(
                {
                    "population": population,
                    "exit_weight": exit_weight,
                    "scenes": len(scenes),
                    "nearest_neighbor_repeat_head_flip_rate": _mean(greedy_flips),
                    "ant_colony_repeat_head_flip_rate": _mean(colony_flips),
                    "ant_colony_repeat_kendall": _mean(colony_kendall),
                    "nearest_neighbor_jitter_head_flip_rate": _mean(greedy_jitter),
                    "ant_colony_jitter_head_flip_rate": _mean(colony_jitter),
                }
            )
    return rows


def _rolling(
    *,
    colony: AntColonySettings,
    origin: NDArray[np.float64],
    exit_weight: float,
    spacing: float,
    entry: float,
    exit_x: float,
    belt_speed: float,
    arm_speed: float,
    epochs: int,
    lateral: tuple[float, float],
) -> dict[str, Any]:
    """Advance a belt, spawning upstream and retiring at the window exit."""
    bodies = _seed_belt(entry, exit_x, spacing, lateral)
    next_id = max((body[0] for body in bodies), default=0) + 1
    epoch_seconds = spacing / (5.0 * belt_speed)
    greedy = NearestNeighborSolver()
    colony_solver = AntColonySolver(colony)
    agree = 0
    populations: list[float] = []
    greedy_late: list[float] = []
    colony_late: list[float] = []
    greedy_ms: list[float] = []
    colony_ms: list[float] = []
    for _epoch in range(epochs):
        nodes = _bodies_to_nodes(bodies)
        request = OrderRequest(nodes=nodes, origin=origin, exit_weight=exit_weight)
        greedy_order, greedy_time = _timed(greedy, request)
        colony_order, colony_time = _timed(colony_solver, request)
        greedy_ms.append(greedy_time)
        colony_ms.append(colony_time)
        populations.append(float(len(nodes)))
        if _heads_agree(greedy_order, colony_order):
            agree += 1
        if greedy_order:
            greedy_late.append(
                _tardiness(request, greedy_order, arm_speed, belt_speed)[0]
            )
        if colony_order:
            colony_late.append(
                _tardiness(request, colony_order, arm_speed, belt_speed)[0]
            )
        bodies = _advance(bodies, belt_speed * epoch_seconds, exit_x)
        if not bodies or min(body[1] for body in bodies) > entry + spacing:
            y_index = next_id % 2
            span = lateral[1] - lateral[0]
            y = lateral[0] + (0.25 if y_index == 0 else 0.75) * span
            bodies.append((next_id, entry, y, exit_x - entry))
            next_id += 1
    return {
        "spacing_meters": spacing,
        "epochs": epochs,
        "epoch_seconds": epoch_seconds,
        "mean_population": _mean(populations),
        "head_agreement": agree / epochs if epochs else 0.0,
        "mean_greedy_tardiness_seconds": _mean(greedy_late),
        "mean_colony_tardiness_seconds": _mean(colony_late),
        "median_greedy_milliseconds": _percentile(greedy_ms, 0.5),
        "median_colony_milliseconds": _percentile(colony_ms, 0.5),
    }


def _seed_belt(
    entry: float, exit_x: float, spacing: float, lateral: tuple[float, float]
) -> list[tuple[int, float, float, float]]:
    """Place tracks from the window entry, one feeder gap apart."""
    bodies: list[tuple[int, float, float, float]] = []
    x = entry
    node_id = 1
    span = lateral[1] - lateral[0]
    while x < exit_x - 0.05:
        y = lateral[0] + (0.25 if node_id % 2 else 0.75) * span
        bodies.append((node_id, x, y, exit_x - x))
        node_id += 1
        x += spacing
    return bodies


def _advance(
    bodies: list[tuple[int, float, float, float]], travel: float, exit_x: float
) -> list[tuple[int, float, float, float]]:
    """Carry every track downstream and drop whatever has left the window."""
    carried: list[tuple[int, float, float, float]] = []
    for node_id, x, y, slack in bodies:
        moved = x + travel
        left = slack - travel
        if left > 0.0 and moved < exit_x:
            carried.append((node_id, moved, y, left))
    return carried


def _bodies_to_nodes(
    bodies: list[tuple[int, float, float, float]],
) -> tuple[OrderNode, ...]:
    """Turn belt coordinates into the nodes a solver scores."""
    return tuple(
        OrderNode(
            node_id=node_id,
            position=np.asarray((x, y, OBJECT_Z_METERS), dtype=np.float64),
            distance_before_leaving=slack,
        )
        for node_id, x, y, slack in bodies
    )


def _draw_nodes(
    rng: np.random.Generator,
    count: int,
    entry: float,
    exit_x: float,
    lateral: tuple[float, float],
) -> tuple[OrderNode, ...]:
    """Draw tracks uniformly in the window, some of them nearly out of belt."""
    nodes: list[OrderNode] = []
    for index in range(count):
        x = float(rng.uniform(entry, exit_x))
        y = float(rng.uniform(lateral[0], lateral[1]))
        remaining = max(0.06, exit_x - x)
        slack = float(rng.uniform(0.05, remaining))
        nodes.append(
            OrderNode(
                node_id=index + 1,
                position=np.asarray((x, y, OBJECT_Z_METERS), dtype=np.float64),
                distance_before_leaving=slack,
            )
        )
    return tuple(nodes)


def _nudge(
    nodes: tuple[OrderNode, ...], rng: np.random.Generator, sigma: float
) -> tuple[OrderNode, ...]:
    """Move each anchor in the belt plane. Slack stays, so only geometry changes."""
    nudged: list[OrderNode] = []
    for node in nodes:
        position = np.asarray(node.position, dtype=np.float64).copy()
        position[0] += float(rng.normal(0.0, sigma))
        position[1] += float(rng.normal(0.0, sigma))
        nudged.append(
            OrderNode(
                node_id=node.node_id,
                position=position,
                distance_before_leaving=node.distance_before_leaving,
            )
        )
    return tuple(nudged)


def _reference(
    request: OrderRequest,
    discounts: tuple[float, ...],
    arm_speed: float,
    belt_speed: float,
) -> _Reference:
    """Minimize travel, tardiness, and each discounted score by enumeration."""
    ids = [node.node_id for node in request.nodes]
    if len(ids) > _PERMUTATION_LIMIT:
        raise ClaveError(
            f"a reference over {len(ids)} tracks is past the enumeration limit"
        )
    best_travel = math.inf
    best_tardiness = math.inf
    tardiness_head: int | None = ids[0] if ids else None
    best_discounted = {discount: math.inf for discount in discounts}
    discounted_head: dict[float, int | None] = {
        discount: ids[0] if ids else None for discount in discounts
    }
    if not ids:
        return _Reference(
            0.0, 0.0, None, {discount: (0.0, None) for discount in discounts}
        )
    for perm in itertools.permutations(ids):
        order = tuple(perm)
        travel, tardiness, _misses = _tardiness(request, order, arm_speed, belt_speed)
        if travel < best_travel:
            best_travel = travel
        if tardiness < best_tardiness:
            best_tardiness = tardiness
            tardiness_head = order[0]
        for discount in discounts:
            scored = tour_cost(request, order, discount)
            if scored < best_discounted[discount]:
                best_discounted[discount] = scored
                discounted_head[discount] = order[0]
    return _Reference(
        best_travel=best_travel,
        best_tardiness=best_tardiness,
        tardiness_head=tardiness_head,
        discounted={
            discount: (best_discounted[discount], discounted_head[discount])
            for discount in discounts
        },
    )


def _evaluate(
    solver: NearestNeighborSolver | AntColonySolver,
    request: OrderRequest,
    reference: _Reference,
    discount: float,
    arm_speed: float,
    belt_speed: float,
) -> dict[str, float]:
    """Time one call and score it against the exhaustive reference."""
    started = time.perf_counter()
    order = solver.order(request)
    elapsed = (time.perf_counter() - started) * 1e3
    travel, tardiness, misses = (
        _tardiness(request, order, arm_speed, belt_speed) if order else (0.0, 0.0, 0)
    )
    discounted = tour_cost(request, order, discount) if order else 0.0
    best_discounted, discounted_head = reference.discounted[discount]
    head = order[0] if order else None
    return {
        "milliseconds": elapsed,
        "travel_gap": _gap(travel, reference.best_travel),
        "discounted_gap": _gap(discounted, best_discounted),
        "tardiness_gap": _gap(tardiness, reference.best_tardiness),
        "tardiness_seconds": tardiness,
        "misses": float(misses),
        "agrees_discounted": 1.0 if head == discounted_head else 0.0,
        "agrees_tardiness": 1.0 if head == reference.tardiness_head else 0.0,
        "head": float(head) if head is not None else -1.0,
    }


def _tardiness(
    request: OrderRequest,
    order: tuple[int, ...],
    arm_speed: float,
    belt_speed: float,
) -> tuple[float, float, int]:
    """Return path length, total lateness, and how many tracks arrive late.

    Lateness uses distance over the configured speed bound as a travel
    time, and belt left over belt speed as the allowance. The bound is
    faster than a real visit, so the lateness is a comparison between
    orders and not a prediction of missed picks.

    Args:
        request: The tracks and the flange.
        order: Visit order.
        arm_speed: Speed bound, in meters per second.
        belt_speed: Belt speed, in meters per second.

    Returns:
        Travel in meters, lateness in seconds, and the count of late tracks.
    """
    by_id = {node.node_id: node for node in request.nodes}
    standing = request.origin
    travel = 0.0
    elapsed = 0.0
    late = 0.0
    misses = 0
    for node_id in order:
        node = by_id[node_id]
        step = distance(standing, node.position)
        travel += step
        elapsed += step / arm_speed
        allowance = node.distance_before_leaving / belt_speed
        if elapsed > allowance:
            late += elapsed - allowance
            misses += 1
        standing = node.position
    return travel, late, misses


def _aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    """Mean the rates and take the median of the times."""

    def column(name: str) -> list[float]:
        return [row[name] for row in rows]

    return {
        "median_milliseconds": _percentile(column("milliseconds"), 0.5),
        "p99_milliseconds": _percentile(column("milliseconds"), 0.99),
        "mean_travel_gap": _mean(column("travel_gap")),
        "optimal_travel_rate": _mean(
            [1.0 if gap <= _OPTIMAL_GAP else 0.0 for gap in column("travel_gap")]
        ),
        "mean_discounted_gap": _mean(column("discounted_gap")),
        "optimal_discounted_rate": _mean(
            [1.0 if gap <= _OPTIMAL_GAP else 0.0 for gap in column("discounted_gap")]
        ),
        "agrees_greedy": _mean(column("agrees_greedy")),
        "agrees_discounted_head": _mean(column("agrees_discounted")),
        "agrees_tardiness_head": _mean(column("agrees_tardiness")),
        "mean_tardiness_seconds": _mean(column("tardiness_seconds")),
        "mean_misses": _mean(column("misses")),
    }


def _shock_nodes(urgent: bool) -> tuple[OrderNode, ...]:
    """Three equally slack tracks, and optionally one that is about to leave."""

    def node(node_id: int, along: float, slack: float) -> OrderNode:
        return OrderNode(
            node_id=node_id,
            position=np.asarray((along, 0.0, 0.0), dtype=np.float64),
            distance_before_leaving=slack,
        )

    nodes = (node(1, 0.30, 1.20), node(2, 0.60, 1.20), node(3, 0.90, 1.20))
    if urgent:
        return nodes + (node(URGENT_TRACK, 1.10, 0.04),)
    return nodes


def _timed(
    solver: NearestNeighborSolver | AntColonySolver, request: OrderRequest
) -> tuple[tuple[int, ...], float]:
    """Return an order and the milliseconds it took."""
    started = time.perf_counter()
    order = solver.order(request)
    return order, (time.perf_counter() - started) * 1e3


def _same_head(left: dict[str, float], right: dict[str, float]) -> float:
    """Return 1 when two scored orders share a head."""
    if left["head"] < 0 and right["head"] < 0:
        return 1.0
    return 1.0 if left["head"] == right["head"] else 0.0


def _heads_agree(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    """Return whether two orders name the same first track, including both empty."""
    if not left and not right:
        return True
    if not left or not right:
        return False
    return left[0] == right[0]


def _flipped(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    """Return 1 when the first track changed."""
    return 0.0 if _heads_agree(left, right) else 1.0


def kendall_fraction(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    """Return the fraction of shared pairs whose relative order disagrees.

    Args:
        left: One visit order.
        right: Another.

    Returns:
        Zero when the shared order agrees, one when every pair is reversed.
    """
    rank = {node: index for index, node in enumerate(right)}
    common = [node for node in left if node in rank]
    pairs = 0
    disagree = 0
    for earlier in range(len(common)):
        for later in range(earlier + 1, len(common)):
            pairs += 1
            if rank[common[earlier]] > rank[common[later]]:
                disagree += 1
    if pairs == 0:
        return 0.0
    return disagree / pairs


def _gap(value: float, best: float) -> float:
    """Return how far a score sits above the reference, as a fraction."""
    if best > _GAP_FLOOR:
        return (value - best) / best
    return value - best


def _instance_count(population: int, base: int) -> int:
    """Cap the scenes whose reference is a large factorial."""
    if population >= 8:
        return min(base, 8)
    if population >= 6:
        return min(base, 12)
    return base


def _percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile. An empty column is zero."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round(fraction * (len(ordered) - 1)))
    return ordered[index]


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean. An empty column is zero."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _midpoint(value: object) -> float:
    """Return a scalar, or the midpoint of a two-element range.

    Args:
        value: A number, or a two-element range as loaded from YAML.

    Returns:
        The number, or the midpoint.

    Raises:
        ClaveError: If the value is not a number or a pair of numbers.
    """
    if isinstance(value, list):
        return 0.5 * (_as_float(value[0]) + _as_float(value[1]))
    return _as_float(value)


def _as_float(value: object) -> float:
    """Return a YAML number as a float.

    Args:
        value: A candidate number. Booleans are refused because they are
            integers in Python and not magnitudes anyone wrote on purpose.

    Returns:
        The value as a float.

    Raises:
        ClaveError: If the value is not a number.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ClaveError(f"{value!r} is not a number")
    return float(value)


if __name__ == "__main__":
    main()
