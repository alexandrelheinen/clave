"""Tests for manipulator actuation."""

import math
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


def test_the_arm_is_found_with_its_four_axes() -> None:
    """The controller drives the four axes a SCARA has, and a tool site."""
    pytest.importorskip("mujoco")
    _, _, indices = built()
    assert len(indices.joint_ids) == 4
    assert len(indices.actuator_ids) == 4
    assert indices.tool_site >= 0


def test_joint_limits_are_read_from_the_model() -> None:
    """Limits come from the model, never from a number written here."""
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
    # Inside the annulus and inside the spline stroke, offset from the shoulder
    # so it clears the dead zone underneath it.
    base = indices.base_position
    target = np.array([base[0] - 0.45, base[1] + 0.20, base[2] + indices.tool_offset])
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


def test_the_solver_places_the_tool_exactly() -> None:
    """Closed-form inverse kinematics has no residual to converge away."""
    pytest.importorskip("mujoco")
    import mujoco

    model, data, indices = built()
    base = indices.base_position
    target = np.array([base[0] - 0.45, base[1] + 0.20, base[2] + indices.tool_offset])
    solved = armmod.solve(indices, target, yaw=0.4)
    for joint, value in zip(indices.joint_ids, solved, strict=True):
        data.qpos[model.jnt_qposadr[joint]] = value
    mujoco.mj_forward(model, data)
    reached = armmod.end_effector_position(data, indices)
    assert np.linalg.norm(reached - target) < 1e-9


def test_the_solver_orients_the_tool_independently_of_position() -> None:
    """Axis 4 is the reason a SCARA replaced the previous arm."""
    pytest.importorskip("mujoco")
    _, _, indices = built()
    base = indices.base_position
    target = np.array([base[0] - 0.45, base[1] + 0.20, base[2] + indices.tool_offset])
    for wanted in (-1.0, 0.0, 0.8):
        solved = armmod.solve(indices, target, yaw=wanted)
        # Yaw is an angle, so the sum matches modulo a full turn.
        error = (solved[0] + solved[1] + solved[3]) - wanted
        assert abs(math.atan2(math.sin(error), math.cos(error))) < 1e-9


def test_a_target_under_the_shoulder_is_refused() -> None:
    """The dead zone is a real property of the arm, not an approximation."""
    pytest.importorskip("mujoco")
    _, _, indices = built()
    base = indices.base_position
    under = np.array([base[0], base[1], base[2] + indices.tool_offset])
    with pytest.raises(armmod.ReachError):
        armmod.solve(indices, under)
    assert not armmod.reachable(indices, under)


def test_a_target_past_the_shoulder_stop_is_refused_not_clipped() -> None:
    """Clipping to a joint limit returns joints whose tool is somewhere else."""
    pytest.importorskip("mujoco")
    _, _, indices = built()
    base = indices.base_position
    height = base[2] + indices.tool_offset
    refused = [
        np.array([base[0] + dx, base[1] + dy, height])
        for dx in np.arange(-0.65, 0.66, 0.05)
        for dy in np.arange(-0.65, 0.66, 0.05)
        if not armmod.reachable(indices, np.array([base[0] + dx, base[1] + dy, height]))
    ]
    assert refused, "the sweep should find points the stops exclude"
    for target in refused:
        with pytest.raises(armmod.ReachError):
            armmod.solve(indices, target)
