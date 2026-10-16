"""The comparison harness.

A full run is `python -m clave.control.order_study`. These tests lock the
two behaviors the report depends on: the harness returns both solvers, and
a colony that ignores the heuristic keeps its old head when an urgent
track appears.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from clave.control.order_study import (
    URGENT_TRACK,
    StudyFactors,
    run_study,
    urgent_arrival,
)
from clave.control.settings import AntColonySettings, ControlSettings
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]


def shipped_colony() -> AntColonySettings:
    """The colony the runtime file names."""
    return ControlSettings.load(
        load(ROOT / "configs" / "runtime" / "control.yml")
    ).selection.ant_colony


def test_pheromone_keeps_the_old_head_when_the_heuristic_is_silent() -> None:
    """With no heuristic, the arrival does not become the head on the first call."""
    colony = replace(
        shipped_colony(),
        ant_count=1,
        iteration_count=1,
        evaporation=0.05,
        pheromone_weight=8.0,
        heuristic_weight=0.0,
        deposit=1.0,
        initial_pheromone=0.01,
        seed=1,
    )
    result = urgent_arrival(colony, exit_weight=1.0, settle_calls=6, follow_calls=3)
    assert result["greedy_head"] == URGENT_TRACK
    assert result["colony_heads"][0] != URGENT_TRACK


def test_the_study_scores_both_solvers() -> None:
    """AC-ORDER-07: the study scores both solvers, and neither beats the reference."""
    report = run_study(
        StudyFactors(
            populations=(3,),
            instances=2,
            exit_weights=(1.0,),
            discounts=(1.0,),
            jitter_count=1,
            stability_populations=(3,),
            static_repeats=2,
            birth_epochs=3,
            shock_iterations=(1,),
            shock_settle=1,
            shock_follow=1,
            seed=2,
        )
    )
    assert report["static"]
    row = report["static"][0]
    assert row["nearest_neighbor"]["mean_travel_gap"] >= -1e-6
    assert row["ant_colony"]["mean_travel_gap"] >= -1e-6
    assert row["nearest_neighbor"]["agrees_greedy"] == 1.0
    assert "median_milliseconds" in row["ant_colony"]
    assert report["shock"][0]["greedy_head"] == URGENT_TRACK
    assert report["line"]
    assert report["stability"]
