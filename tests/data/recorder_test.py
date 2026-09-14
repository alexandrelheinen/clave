"""Tests for the rollout recorder.

These need MuJoCo and the pinned menagerie submodule, and skip when either is
absent, as the world tests do.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from clave.data.examples import Rollout

ROOT = Path(__file__).resolve().parents[2]


def record_short(seed: int, rollout_id: str = "r0") -> Rollout:
    """Record a short rollout for testing."""
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    from clave.data.recorder import record

    return record(
        root=ROOT,
        seed=seed,
        seconds=4.0,
        capture_interval_seconds=1.0,
        height=48,
        width=64,
        rollout_id=rollout_id,
    )


def test_a_rollout_captures_labeled_frames() -> None:
    """AC-RECORD-01 and AC-RECORD-02."""
    pytest.importorskip("mujoco")
    rollout = record_short(0)
    assert rollout.examples
    example = rollout.examples[-1]
    assert example.frame.shape == (48, 64, 3)
    assert example.frame.dtype == np.uint8
    for label in example.labels:
        assert label.material_class.startswith("M-")
        assert label.channel.startswith("CH-")


def test_every_example_carries_seed_time_and_config_digest() -> None:
    """AC-RECORD-03: a dataset must say what produced it."""
    pytest.importorskip("mujoco")
    rollout = record_short(2)
    for example in rollout.examples:
        assert example.seed == 2
        assert example.simulated_time >= 0.0
        assert len(example.config_digest) == 64


def test_one_seed_twice_records_identical_examples() -> None:
    """AC-RECORD-04: two runs must be comparable."""
    pytest.importorskip("mujoco")
    first, second = record_short(7), record_short(7)
    assert len(first.examples) == len(second.examples)
    assert np.array_equal(first.examples[-1].frame, second.examples[-1].frame)
    assert first.examples[-1].material_classes == second.examples[-1].material_classes


def test_two_seeds_record_different_examples() -> None:
    """The guard above would pass for a constant renderer."""
    pytest.importorskip("mujoco")
    first, second = record_short(7), record_short(8)
    assert not np.array_equal(first.examples[-1].frame, second.examples[-1].frame)
