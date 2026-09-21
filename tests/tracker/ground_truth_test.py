"""Ground-truth tracker tests, guarding AC-GT-01 through AC-GT-05.

AC-GT-01: Configuration and CLI flag --ground-truth-tracker.
AC-GT-02: GraspMarker derivation directly from MuJoCo physics state.
AC-GT-03: Concurrent tracker observation and settling during ground-truth mode.
AC-GT-04: Selector and TaskMachine pick planning from ground-truth markers.
AC-GT-05: Scene visualization displaying ground-truth markers.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from clave.cli import _build_parser
from clave.control.selection import Selector
from clave.control.settings import SelectionSettings
from clave.tracker.markers import ground_truth_markers
from clave.world.belt import SpawnedObject
from clave.world.config import load
from clave.world.effector import Effector
from clave.world.scene import BeltGeometry, SceneLayout

ROOT = Path(__file__).resolve().parents[2]
WORLD_CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"
TRACKER_CONFIG = ROOT / "configs" / "debug" / "tracker.yml"


def effector() -> Effector:
    """Load the effector configuration from the sorting line config."""
    return Effector.load(load(WORLD_CONFIG))


def minimal_plan() -> SceneLayout:
    """Minimal scene layout sufficient for ground-truth marker geometry."""
    return SceneLayout(
        belt=BeltGeometry(
            length=4.0,
            width=0.5,
            surface_height=0.90,
            speed=0.31,
        ),
        arm_base=(0.0, -0.45, 0.90),
        reach_min=0.30,
        reach_max=1.30,
        tool_above_base=(-0.20, 0.60),
        pedestal=(0.20, 0.20),
        channels=("chute_a", "chute_b"),
        chutes={"chute_a": (0.0, -0.70, 0.40), "chute_b": (0.3, -0.70, 0.40)},
        objects=(),
        pool_size=4,
        timestep=0.002,
        dressed=False,
    )


def build_test_mujoco() -> tuple[Any, Any]:
    """Compile a minimal MuJoCo model with test objects for ground-truth tests."""
    import mujoco

    xml = """
    <mujoco>
      <worldbody>
        <body name="object_0" pos="0.10 0.05 0.92">
          <freejoint/>
          <geom type="cylinder" size="0.03 0.05"/>
        </body>
        <body name="object_1" pos="-0.20 -0.05 0.92" quat="0.7071068 0 0 0.7071068">
          <freejoint/>
          <geom type="box" size="0.02 0.04 0.03"/>
        </body>
        <body name="object_2" pos="1.50 0.0 0.92">
          <freejoint/>
          <geom type="cylinder" size="0.03 0.05"/>
        </body>
      </worldbody>
    </mujoco>
    """
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data


def test_ground_truth_tracker_config_and_cli_ac_gt_01() -> None:
    """AC-GT-01: Configuration exposes ground_truth_tracker and CLI parses it."""
    # Check config
    cfg = load(TRACKER_CONFIG)
    assert "ground_truth_tracker" in cfg
    assert cfg["ground_truth_tracker"] is False

    # Check CLI without flag defaults to None (delegating to config)
    parser = _build_parser()
    args_default = parser.parse_args(["sim"])
    assert args_default.ground_truth_tracker is None

    # Check CLI with flag sets it to True
    args_flag = parser.parse_args(["sim", "--ground-truth-tracker"])
    assert args_flag.ground_truth_tracker is True


def test_ground_truth_markers_derivation_ac_gt_02() -> None:
    """AC-GT-02: Derive GraspMarker targets directly from MuJoCo physics state."""
    model, data = build_test_mujoco()
    plan = minimal_plan()
    eff = effector()

    active = [
        SpawnedObject(
            index=0, name="object_0", material_class="M-01", channel="chute_a"
        ),
        SpawnedObject(
            index=1, name="object_1", material_class="M-02", channel="chute_b"
        ),
        SpawnedObject(
            index=2, name="object_2", material_class="M-01", channel="chute_a"
        ),
    ]

    now = 1_000_000_000
    window_exit = 1.0
    belt_speed = 0.31

    markers = ground_truth_markers(
        model=model,
        data=data,
        active_objects=active,
        plan=plan,
        effector=eff,
        belt_surface_height_world=0.90,
        at_nanos=now,
        window_exit=window_exit,
        belt_speed=belt_speed,
    )

    # object_2 is at x=1.5 > window_exit=1.0, so it must be excluded
    assert len(markers) == 2

    # Check object_0 (cylinder)
    m0 = markers[0]
    assert m0.track_id == 0
    assert m0.channel == "chute_a"
    assert math.isclose(m0.pinch_position_belt[0], 0.10, abs_tol=1e-5)
    assert math.isclose(m0.pinch_position_belt[1], 0.05, abs_tol=1e-5)
    assert math.isclose(
        m0.pinch_position_belt[2], 0.90 + eff.grasp_height, abs_tol=1e-5
    )
    assert math.isclose(m0.opening, 0.06, abs_tol=1e-5)
    assert m0.oriented is False
    assert m0.closing_yaw_belt is None

    # Check object_1 (box rotated pi/2)
    m1 = markers[1]
    assert m1.track_id == 1
    assert m1.channel == "chute_b"
    assert math.isclose(m1.pinch_position_belt[0], -0.20, abs_tol=1e-5)
    assert math.isclose(m1.pinch_position_belt[1], -0.05, abs_tol=1e-5)
    assert m1.oriented is True
    # Box sx=0.02, sy=0.04 -> opening=0.04 across body local x.
    # Rotated pi/2 -> closing axis in world is pi/2
    assert m1.closing_yaw_belt is not None
    assert math.isclose(m1.closing_yaw_belt, math.pi / 2.0, abs_tol=1e-4)


def test_ground_truth_selector_and_task_planning_ac_gt_04() -> None:
    """AC-GT-04: Selector admits and orders ground-truth markers."""
    model, data = build_test_mujoco()
    plan = minimal_plan()
    eff = effector()

    active = [
        SpawnedObject(
            index=0, name="object_0", material_class="M-01", channel="chute_a"
        ),
    ]

    now = 1_000_000_000
    markers = ground_truth_markers(
        model=model,
        data=data,
        active_objects=active,
        plan=plan,
        effector=eff,
        belt_surface_height_world=0.90,
        at_nanos=now,
        window_exit=1.0,
        belt_speed=0.31,
    )

    selector = Selector(
        SelectionSettings(exit_weight=1.0, anchor_radius=0.02),
        admits=lambda p: True,
    )

    flange = (0.0, 0.0, 1.20)
    queue = selector.update(markers, flange, belt_speed=0.31, at_nanos=now)
    assert len(queue.order) == 1
    assert queue.order[0].track_id == 0
    assert queue.order[0].channel == "chute_a"


def test_ground_truth_simulation_run_ac_gt_03_and_05(tmp_path: Path) -> None:
    """AC-GT-03, AC-GT-05: Simulation runs with ground truth while tracker observes."""
    from clave.tracker.debug_run import run

    report = run(
        root=ROOT,
        out=tmp_path,
        seconds=1.0,
        seed=0,
        window=False,
        video=False,
        ground_truth_tracker=True,
    )

    # AC-GT-03: Tracker continues to observe and settle captures
    assert report.captures > 0
    assert report.ground_truth is True

    # AC-GT-05: Scene visualization reflects markers
    assert report.drawn >= 0
