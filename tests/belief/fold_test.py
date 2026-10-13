"""Folding evidence once a category model is attached.

The confidence-floor line never attaches one, and the tests in
`tests/tracker` keep that path. These cover the path the model opens.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from clave.belief.model import BeliefModel
from clave.tracker.association import Association, Cue, TrackSummary
from clave.tracker.belt_frame import Footprint
from clave.tracker.evidence import (
    Code,
    Detection,
    Evidence,
    GroundTruth,
    Material,
    PixelMask,
    Role,
)
from clave.tracker.fusion import OUTCOMES, FusionSettings, Posterior, fold
from clave.tracker.intake import Deployment, Intake
from clave.tracker.sensors import load_sensors
from clave.tracker.track import Tracker
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
WIDTH = len(OUTCOMES)
SECOND = 1_000_000_000


class _JoinFirst:
    """Joins every cue to the first open track."""

    @property
    def name(self) -> str:
        """What decided the association."""
        return "stub"

    def associate(self, cue: Cue, tracks: tuple[TrackSummary, ...]) -> Association:
        """Join the first open track, or open one."""
        del cue
        return Association(track_id=tracks[0].track_id if tracks else None)


def _settings() -> FusionSettings:
    """The shipped fusion settings."""
    return FusionSettings.load(
        ROOT / "configs" / "perception" / "fusion.yml",
        ROOT / "configs" / "world" / "sorting_line.yml",
    )


def _table(column: int, winner: int) -> tuple[tuple[float, ...], ...]:
    """Return a conditional table whose one interesting column peaks on `winner`."""
    rows: list[tuple[float, ...]] = []
    for outcome in range(WIDTH):
        counts = [1.0] * WIDTH
        counts[column] = 100.0 if outcome == winner else 1.0
        rows.append(tuple(counts))
    return tuple(rows)


def _model(
    table: tuple[tuple[float, ...], ...], prior: tuple[float, ...] | None = None
) -> BeliefModel:
    """A model with one material table and a flat cost, enough to fold."""
    return BeliefModel(
        prior_counts=prior if prior is not None else tuple(1.0 for _ in range(WIDTH)),
        sensors={"material": table},
        cost_channels=(0,),
        cost_rows=(tuple(1.0 for _ in range(WIDTH)),),
    )


def _soft(class_id: str) -> tuple[float, ...]:
    """A distribution whose mode is `class_id` and whose mass is not a likelihood."""
    spread = 0.2 / (WIDTH - 1)
    return tuple(0.8 if name == class_id else spread for name in OUTCOMES)


def _material(belief: tuple[float, ...]) -> Evidence:
    """One material reading."""
    return Evidence(
        source_id="gate_wide",
        role=Role.SPECTRAL,
        observed_at_nanos=SECOND,
        confidence=1.0,
        payload=Material(belief),
    )


def test_ac_sort_02_the_soft_vector_is_not_the_likelihood() -> None:
    """The argmax selects the table column, and the column selects the outcome."""
    reading = OUTCOMES.index("M-02")
    winner = OUTCOMES.index("M-06")
    configured = replace(_settings(), belief=_model(_table(reading, winner)))
    updated = fold(Posterior.uniform(), _material(_soft("M-02")), SECOND, configured)
    assert updated.recognized
    assert updated.posterior.most_likely[0] == "M-06"
    old = Posterior.uniform().fold(
        _soft("M-02"), weight=1.0, floor=configured.posterior_floor
    )
    assert old.most_likely[0] == "M-02"


def test_ac_sort_05_geometry_does_not_enter_the_product() -> None:
    """A detection leaves the category belief where the prior put it."""
    prior = tuple(50.0 if name == "M-06" else 1.0 for name in OUTCOMES)
    model = _model(_table(0, 0), prior)
    configured = replace(_settings(), belief=model)
    detection = Evidence(
        source_id="gate_wide",
        role=Role.DETECTION,
        observed_at_nanos=SECOND,
        confidence=1.0,
        payload=Detection(
            footprint=Footprint(
                center=np.asarray((-1.0, 0.0, 0.93), dtype=np.float64),
                major_extent=0.10,
                minor_extent=0.06,
                yaw=0.0,
            ),
            mask=PixelMask(width=8, height=8, runs=((0, 1, 1),)),
            height=0.06,
        ),
    )
    opening = Posterior(weights=model.opening_weights(configured.posterior_floor))
    updated = fold(opening, detection, SECOND, configured)
    assert updated.posterior.weights == opening.weights


def test_ground_truth_keeps_the_spike_when_a_model_is_attached() -> None:
    """The simulator label does not consult the material table."""
    reading = OUTCOMES.index("M-03")
    configured = replace(
        _settings(), belief=_model(_table(reading, OUTCOMES.index("M-06")))
    )
    evidence = Evidence(
        source_id="simulator",
        role=Role.GROUND_TRUTH,
        observed_at_nanos=SECOND,
        confidence=1.0,
        payload=GroundTruth(
            object_id=1,
            material_class="M-03",
            position=np.asarray((-1.0, 0.0, 0.93), dtype=np.float64),
        ),
    )
    updated = fold(Posterior.uniform(), evidence, SECOND, configured)
    assert updated.posterior.most_likely[0] == "M-03"


def test_a_new_track_opens_on_the_floored_prior() -> None:
    """A configured model replaces the uniform opening belief."""
    prior = tuple(50.0 if name == "M-06" else 1.0 for name in OUTCOMES)
    model = _model(_table(0, 0), prior)
    configured = replace(_settings(), belief=model)
    held = Tracker(
        intake=Intake(
            Deployment.SIMULATED,
            load_sensors(load(ROOT / "configs" / "world" / "sorting_line.yml")),
        ),
        associator=_JoinFirst(),
        settings=configured,
        belt_speed=0.31,
        window_exit=1.034,
        unmeasured_extent=0.12,
    )
    detection = Evidence(
        source_id="gate_wide",
        role=Role.DETECTION,
        observed_at_nanos=SECOND,
        confidence=1.0,
        payload=Detection(
            footprint=Footprint(
                center=np.asarray((-1.0, 0.0, 0.93), dtype=np.float64),
                major_extent=0.10,
                minor_extent=0.06,
                yaw=0.0,
            ),
            mask=PixelMask(width=8, height=8, runs=((0, 1, 1),)),
            height=0.06,
        ),
    )
    held.observe(detection, SECOND)
    opened = next(iter(held._tracks.values()))
    expected = model.opening_weights(configured.posterior_floor)
    assert opened.posterior.weights == expected
    assert opened.posterior.most_likely[0] == "M-06"
    assert opened.posterior.weights != Posterior.uniform().weights


def test_a_sharp_belief_moves_less_under_the_same_code() -> None:
    """The code down-weight leaves a sharp belief closer to where it started."""
    configured = replace(_settings(), belief=_model(_table(0, 0)))
    code = Evidence(
        source_id="gate_code_left",
        role=Role.CODE,
        observed_at_nanos=SECOND,
        confidence=1.0,
        payload=Code(symbology="UPC_A", digits="037600138727"),
    )
    sharp = _peaked("M-06", 0.95)
    flat = Posterior.uniform()

    def shift(start: Posterior) -> float:
        after = fold(start, code, SECOND, configured, resolve=lambda _: ("M-07",))
        return sum(
            abs(left - right)
            for left, right in zip(after.posterior.weights, start.weights, strict=True)
        )

    assert shift(sharp) < shift(flat)


def _peaked(class_id: str, mass: float) -> Posterior:
    """A belief that already holds `mass` on one class."""
    spread = (1.0 - mass) / (WIDTH - 1)
    return Posterior(
        weights=tuple(mass if name == class_id else spread for name in OUTCOMES)
    )
