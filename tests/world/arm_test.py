"""Tests for manipulator actuation."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from clave.world import arm as armmod
from clave.world import config, scene

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def built() -> tuple[Any, Any, armmod.ArmIndices]:
    """Build the shipped world and locate the arm in it."""
    import mujoco

    raw = config.load(CONFIG)
    model, data, _ = scene.build(raw, np.random.default_rng(0), ROOT)
    indices = armmod.locate(model)
    mujoco.mj_forward(model, data)
    return model, data, indices


def test_the_arm_is_found_with_four_revolute_joints() -> None:
    """The controller drives the four joints the OpenMANIPULATOR-X has."""
    pytest.importorskip("mujoco")
    _, _, indices = built()
    assert len(indices.joint_ids) == 4
    assert len(indices.actuator_ids) == 4
    assert indices.gripper_actuator >= 0


def test_joint_limits_are_read_from_the_model() -> None:
    """Limits come from the menagerie, never from a number written here."""
    pytest.importorskip("mujoco")
    _, _, indices = built()
    assert np.all(indices.lower < indices.upper)


def test_proprioception_reports_the_arm_joint_angles() -> None:
    """The dataset had none of this, which is why policies were vision only."""
    pytest.importorskip("mujoco")
    model, data, indices = built()
    angles = armmod.joint_positions(model, data, indices)
    assert angles.shape == (4,)
    assert np.all(np.isfinite(angles))


def test_commanding_a_target_moves_the_end_effector_toward_it() -> None:
    """The point of the whole module: something now writes data.ctrl."""
    pytest.importorskip("mujoco")
    import mujoco

    model, data, indices = built()
    target = np.array([0.05, -0.05, 0.42])
    before = np.linalg.norm(target - armmod.end_effector_position(data, indices))
    for _ in range(2000):
        armmod.step_toward(model, data, indices, target, gain=0.5)
        mujoco.mj_step(model, data)
    after = np.linalg.norm(target - armmod.end_effector_position(data, indices))
    assert after < before / 2.0


def test_commanded_angles_stay_inside_the_joint_limits() -> None:
    """A target outside the workspace must not drive a joint past its stop."""
    pytest.importorskip("mujoco")
    import mujoco

    model, data, indices = built()
    unreachable = np.array([5.0, 5.0, 5.0])
    for _ in range(500):
        commanded = armmod.step_toward(model, data, indices, unreachable, gain=1.0)
        mujoco.mj_step(model, data)
        assert np.all(commanded >= indices.lower - 1e-9)
        assert np.all(commanded <= indices.upper + 1e-9)


def test_the_scene_is_stable_without_a_conveyor_stepping_it() -> None:
    """v0.6.0 left the world stable only while a conveyor pinned parked slots."""
    pytest.importorskip("mujoco")
    import mujoco

    model, data, indices = built()
    target = np.array([0.05, -0.05, 0.42])
    for _ in range(3000):
        armmod.step_toward(model, data, indices, target, gain=0.5)
        mujoco.mj_step(model, data)
    assert np.all(np.isfinite(data.qpos))
    assert np.all(np.isfinite(data.qvel))


def test_a_missing_arm_is_reported_by_name() -> None:
    """A moved submodule or a changed prefix should fail legibly."""
    pytest.importorskip("mujoco")
    import mujoco

    empty = mujoco.MjModel.from_xml_string("<mujoco><worldbody/></mujoco>")
    with pytest.raises(KeyError, match="arm_Joint1"):
        armmod.locate(empty)
