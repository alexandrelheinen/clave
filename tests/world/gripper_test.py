"""The jaw on the flange, and whether it holds anything.

This is the first thing in CLAVE that can fail for a physical reason rather
than a logical one. A pose outside the envelope is refused by arithmetic; a
jaw that closes on a package and comes away empty is the simulator
disagreeing with the plan.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "configs" / "world" / "sorting_line.yml"


@pytest.fixture(scope="module")
def world() -> Any:
    """The shipped world, compiled once for the module."""
    numpy = pytest.importorskip("numpy")
    mujoco = pytest.importorskip("mujoco")
    from clave.world import arm as armmod
    from clave.world import scene

    model, data, plan = scene.build(load(WORLD), numpy.random.default_rng(0), ROOT)
    mujoco.mj_forward(model, data)
    return model, data, plan, armmod.locate(model)


def test_the_gripper_is_on_the_flange(world: Any) -> None:
    """AC-GRIP-01: the gripper is on the flange."""
    from clave.world import arm as armmod

    model, data, _, arm = world
    del model
    assert arm.gripper_actuator >= 0
    assert arm.pinch_site >= 0
    flange = armmod.end_effector_position(data, arm)
    pinch = armmod.pinch_position(data, arm)
    assert math.dist(flange, pinch) > 0.10


def test_the_configured_finger_length_is_the_compiled_one(world: Any) -> None:
    """AC-GRIP-01: the configured finger length is the compiled one.

    The offset between the flange and the pinch point is a property of the
    vendored model, and the controller reads it from configuration. This is
    what stops the two drifting when the model is re-copied.
    """
    from clave.world import arm as armmod
    from clave.world.effector import Effector

    model, data, _, arm = world
    del model
    effector = Effector.load(load(WORLD))
    measured = math.dist(
        armmod.end_effector_position(data, arm), armmod.pinch_position(data, arm)
    )
    assert effector.finger_length == pytest.approx(measured, abs=0.001)
    assert effector.opening == pytest.approx(0.085)


def test_the_tool_site_every_pose_is_expressed_against_still_moves(
    world: Any,
) -> None:
    """AC-GRIP-01: the tool site every pose is expressed against still moves.

    The gripper hangs off the flange rather than displacing it, which is why
    the trusted reach bounds did not have to be re-swept. This fails if a
    future mounting moves the site instead.
    """
    mujoco = pytest.importorskip("mujoco")
    numpy = pytest.importorskip("numpy")
    from clave.world import arm as armmod

    model, data, _, arm = world
    before = armmod.end_effector_position(data, arm).copy()
    target = numpy.array([0.20, -0.30, 1.15])
    for _ in range(900):
        armmod.step_toward(model, data, arm, target, gain=1.0)
        mujoco.mj_step(model, data)
    after = armmod.end_effector_position(data, arm)
    assert math.dist(before, after) > 0.05
    assert math.dist(after, target) < 0.05


def test_the_jaw_opens_and_closes(world: Any) -> None:
    """AC-GRIP-05: the jaw opens and closes."""
    mujoco = pytest.importorskip("mujoco")
    from clave.world import arm as armmod

    model, data, _, arm = world

    def separation() -> float:
        left = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "arm_grip_left_pad")
        right = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "arm_grip_right_pad")
        return float(math.dist(data.xpos[left], data.xpos[right]))

    armmod.hold(data, arm, closed=0.0)
    for _ in range(1500):
        mujoco.mj_step(model, data)
    wide = separation()

    armmod.hold(data, arm, closed=1.0)
    for _ in range(1500):
        mujoco.mj_step(model, data)
    shut = separation()

    assert wide > shut + 0.05, f"open {wide * 1000:.1f} mm, shut {shut * 1000:.1f} mm"


def test_no_object_in_the_set_is_wider_than_the_jaw() -> None:
    """AC-GRIP-03: no object in the set is wider than the jaw.

    Enforced at load by the scene, which is why building the world is the
    test. This states the property so a reader finds it here rather than
    inferring it from a build that happened not to fail.
    """
    raw = load(WORLD)
    assert float(raw["arm"]["max_grasp_width_meters"]) == pytest.approx(0.085)
    assert not [
        entry for entry in raw["objects"] if entry.get("name") == "master_chef_can"
    ], "an object the jaw cannot close on is back in the set"
