"""Turning a commanded pose into joint angles, against the compiled model."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from clave.control.guidance import Command
from clave.control.servo import follow
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
GAIN = 1.0


@pytest.fixture(scope="module")
def world() -> Any:
    """The shipped world, compiled once for the whole module."""
    numpy = pytest.importorskip("numpy")
    mujoco = pytest.importorskip("mujoco")
    from clave.world import arm as armmod
    from clave.world import scene

    raw = load(ROOT / "configs" / "world" / "sorting_line.yml")
    model, data, _ = scene.build(raw, numpy.random.default_rng(0), ROOT)
    mujoco.mj_forward(model, data)
    return model, data, armmod.locate(model)


def flange_of(world: Any) -> tuple[float, float, float]:
    """Where the flange stands right now."""
    from clave.world import arm as armmod

    model, data, arm = world
    del model
    place = armmod.end_effector_position(data, arm)
    return float(place[0]), float(place[1]), float(place[2])


def settle(world: Any, command: Command, steps: int = 400) -> Any:
    """Command one pose repeatedly and let the physics catch up."""
    mujoco = pytest.importorskip("mujoco")
    model, data, arm = world
    step = None
    for _ in range(steps):
        step = follow(model, data, arm, command, GAIN)
        mujoco.mj_step(model, data)
    return step


def test_a_reachable_pose_moves_the_flange_toward_it(world: Any) -> None:
    """AC-MOVE-04: a reachable pose moves the flange toward it."""
    target = (0.30, -0.20, 1.12)
    before = math.dist(flange_of(world), target)
    settle(world, Command(position=target, yaw=0.0))
    assert math.dist(flange_of(world), target) < before


def test_the_flange_arrives_inside_the_tolerance_the_task_layer_uses(
    world: Any,
) -> None:
    """AC-MOVE-12: the flange arrives inside the tolerance the task layer uses.

    Ten millimetres is what `task.arrival_tolerance_meters` calls arrived. A
    servo that cannot get inside it makes every visit hang, so the number and
    the mechanism are checked against each other here rather than separately.
    """
    from clave.control.settings import ControlSettings

    settings = ControlSettings.load(load(ROOT / "configs" / "runtime" / "control.yml"))
    target = (0.20, -0.30, 1.15)
    settle(world, Command(position=target, yaw=0.0), steps=1200)
    assert math.dist(flange_of(world), target) <= settings.task.arrival_tolerance


def test_a_pose_outside_the_annulus_is_refused_and_named(world: Any) -> None:
    """AC-MOVE-05: a pose outside the annulus is refused and named."""
    model, data, arm = world
    step = follow(model, data, arm, Command(position=(3.0, 0.0, 1.10), yaw=0.0), GAIN)
    assert step.refusal is not None
    assert "annulus" in step.refusal


def test_a_pose_outside_the_vertical_band_is_refused_and_named(world: Any) -> None:
    """AC-MOVE-05: a pose outside the vertical band is refused and named."""
    model, data, arm = world
    step = follow(
        model, data, arm, Command(position=(0.30, -0.30, 2.40), yaw=0.0), GAIN
    )
    assert step.refusal is not None
    assert "band" in step.refusal


def test_a_refused_pose_commands_a_hold_rather_than_the_pose(world: Any) -> None:
    """AC-MOVE-05: a refused pose commands a hold rather than the pose.

    Writing nothing looks safer and is not. An uncommanded arm sags under
    gravity, the sag puts the flange outside the trusted vertical band, and
    from there every pose is refused for a reason the controller caused. That
    deadlock is what this pins down: the command written is where the arm
    already is, derived from the arm and not from the pose that was refused.
    """
    from clave.world import arm as armmod

    model, data, arm = world
    step = follow(model, data, arm, Command(position=(3.0, 0.0, 1.10), yaw=0.0), GAIN)
    assert step.refusal is not None
    held = armmod.joint_positions(model, data, arm)
    for slot, actuator in enumerate(arm.actuator_ids):
        assert float(data.ctrl[actuator]) == pytest.approx(held[slot])


def test_an_arm_left_refusing_does_not_sag_out_of_its_own_workspace(
    world: Any,
) -> None:
    """An arm left refusing does not sag out of its own workspace.

    The regression behind the hold. Two hundred ticks of refusal used to drop
    the flange below the trusted band, after which nothing the controller
    asked for could ever be accepted again.
    """
    mujoco = pytest.importorskip("mujoco")
    from clave.world import arm as armmod

    model, data, arm = world
    settle(world, Command(position=(0.30, -0.30, 1.15), yaw=0.0), steps=900)
    for _ in range(200):
        follow(model, data, arm, Command(position=(3.0, 0.0, 1.10), yaw=0.0), GAIN)
        mujoco.mj_step(model, data)
    import numpy

    assert armmod.reachable(arm, numpy.array(flange_of(world)))


def test_a_command_with_no_yaw_holds_the_rotation_the_arm_has(world: Any) -> None:
    """AC-MOVE-08: a command with no yaw holds the rotation the arm has.

    An unoriented footprint claims no angle, so the arm keeps the one it is
    already turned to rather than snapping to zero.
    """
    from clave.world import arm as armmod

    model, data, arm = world
    settle(world, Command(position=(0.30, -0.25, 1.15), yaw=1.0), steps=900)
    held = armmod.tool_yaw(data, arm)
    settle(world, Command(position=(0.32, -0.25, 1.15), yaw=None), steps=300)
    assert armmod.tool_yaw(data, arm) == pytest.approx(held, abs=0.15)


def test_the_commanded_joints_stay_inside_their_limits(world: Any) -> None:
    """The commanded joints stay inside their limits."""
    model, data, arm = world
    step = follow(
        model, data, arm, Command(position=(0.40, -0.40, 1.05), yaw=0.3), GAIN
    )
    assert step.refusal is None
    for angle, low, high in zip(step.joints, arm.lower, arm.upper, strict=True):
        assert low <= angle <= high


def test_the_arm_keeps_up_with_a_pose_moving_at_the_speed_ceiling(
    world: Any,
) -> None:
    """AC-MOVE-09: the arm keeps up with a pose moving at the speed ceiling.

    This is the question etapa A exists to answer. The belt moves a target
    0.5 mm per physics step and the solver's warm start was sized for that;
    a flange traversing at the configured 1 m/s moves 2 mm per step, three to
    four times further. If the descent stops converging there, the answer is
    to slow the belt rather than to raise the ceiling, and this is what would
    say so.
    """
    mujoco = pytest.importorskip("mujoco")
    from clave.control.guidance import toward
    from clave.control.settings import ControlSettings, Phase
    from clave.control.task import Goal

    settings = ControlSettings.load(load(ROOT / "configs" / "runtime" / "control.yml"))
    model, data, arm = world
    settle(world, Command(position=(0.30, -0.30, 1.15), yaw=0.0), steps=900)

    goal = Goal(phase=Phase.TRACK, position=(-0.40, -0.20, 1.15), yaw=0.0, track_id=1)
    reference = flange_of(world)
    lag = 0.0
    for _ in range(1500):
        command = toward(reference, goal, 0.002, settings.guidance)
        reference = command.position
        step = follow(model, data, arm, command, settings.servo.gain)
        assert step.refusal is None
        mujoco.mj_step(model, data)
        lag = max(lag, math.dist(flange_of(world), command.position))
    assert math.dist(flange_of(world), goal.position) <= settings.task.arrival_tolerance
    # Recorded rather than bounded tightly: what matters here is that the
    # solver kept converging and the flange arrived, not the exact tracking
    # error of a position-controlled arm under its own actuator dynamics.
    assert lag < 0.30


def test_stepping_guidance_from_the_measurement_crawls(world: Any) -> None:
    """Stepping guidance from the measurement crawls.

    The defect this pins down is easy to write and hard to see: feeding the
    measured flange back into guidance makes the reference restart from
    wherever the arm lagged to, so it never leads the plant and the traverse
    runs at the tracking error rather than at the ceiling. Keeping the test
    keeps somebody from simplifying the reference away again.
    """
    mujoco = pytest.importorskip("mujoco")
    from clave.control.guidance import toward
    from clave.control.settings import ControlSettings, Phase
    from clave.control.task import Goal

    settings = ControlSettings.load(load(ROOT / "configs" / "runtime" / "control.yml"))
    model, data, arm = world
    settle(world, Command(position=(0.30, -0.30, 1.15), yaw=0.0), steps=900)

    goal = Goal(phase=Phase.TRACK, position=(-0.40, -0.20, 1.15), yaw=0.0, track_id=1)
    start = flange_of(world)
    for _ in range(500):
        command = toward(flange_of(world), goal, 0.002, settings.guidance)
        follow(model, data, arm, command, settings.servo.gain)
        mujoco.mj_step(model, data)
    chasing = math.dist(start, flange_of(world))

    # One second of ticks at the ceiling covers a metre. Chasing the plant
    # covers a fraction of that, and this is the fraction that matters.
    assert chasing < 0.5 * settings.guidance.max_speed * 500 * 0.002
