"""What a run records, so its numbers can be traced and audited.

AC-MOVE-51, AC-MOVE-52 and AC-MOVE-53. These are the figures a run of
2026-09-21 could not answer: which tree flew it, and how close the jaws came to
the belt. Every number in that run's telemetry that described the state it
reached survived the replay; the ones that described the control path did not,
because nothing recorded the tree.
"""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from clave.control.guidance import Command
from clave.control.settings import Phase
from clave.tracker.debug_run import (
    _jaw_collision_geoms,
    _jaw_state,
    _park_the_arm,
    _run_metadata,
    _TelemetryWriter,
)
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "configs" / "world" / "sorting_line.yml"
CONTROL = ROOT / "configs" / "runtime" / "control.yml"


@pytest.fixture(scope="module")
def world() -> Any:
    """The shipped world, compiled once for the module."""
    numpy = pytest.importorskip("numpy")
    mujoco = pytest.importorskip("mujoco")
    from clave.world import arm as armmod
    from clave.world import scene

    model, data, plan = scene.build(load(WORLD), numpy.random.default_rng(0), ROOT)
    mujoco.mj_forward(model, data)
    return mujoco, model, data, plan, armmod.locate(model)


def test_the_run_records_the_revision_and_the_configuration_digests() -> None:
    """AC-MOVE-52: a run records the revision and the configuration digests."""
    record = _run_metadata(ROOT, {"world": WORLD, "control": CONTROL})
    revision = record["revision"]
    assert revision is None or (len(revision) == 40 and int(revision, 16) >= 0)
    assert record["dirty"] is None or isinstance(record["dirty"], bool)
    digests = record["config_digests"]
    assert set(digests) == {"world", "control"}
    for digest in digests.values():
        assert len(digest) == 64 and int(digest, 16) >= 0
    assert digests["world"] != digests["control"], "two configs hashed as one"


def test_a_telemetry_row_carries_the_command_and_the_jaw(
    world: Any, tmp_path: Path
) -> None:
    """AC-MOVE-53: a row carries the command and the jaw's own clearance.

    A pose is the flange, the jaw hangs 173.5 mm below it, and nothing in the
    old row said which of the two was anywhere near the belt.
    """
    mujoco, model, data, plan, arm = world
    _park_the_arm(mujoco, model, data, arm, (0.72, -0.42, 1.20))
    geoms = _jaw_collision_geoms(model, arm)
    belt = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "belt"))
    surface = plan.belt.surface_height
    state = _jaw_state(mujoco, model, data, arm, geoms, belt, surface)
    path = tmp_path / "telemetry.csv"
    writer = _TelemetryWriter(path, model, plan.pool_size, 100.0)
    command = Command(
        position=(0.50, 0.10, 1.20),
        yaw=0.25,
        speed=0.0,
        velocity=(0.0, 0.0, 0.0),
        aim=(0.50, 0.10, 1.20),
    )
    writer.write(
        model,
        data,
        arm,
        SimpleNamespace(active=()),
        0.31,
        Phase.STANDBY,
        False,
        state,
        command,
    )
    writer.close()

    with path.open() as handle:
        header = next(csv.reader(handle))
        row = next(csv.reader(handle))
    record = dict(zip(header, row, strict=True))
    for column in (
        "commanded_x",
        "commanded_y",
        "commanded_z",
        "commanded_yaw",
        "jaw_lowest_z",
        "jaw_clearance",
        "belt_contact",
        "tool_tilt_degrees",
    ):
        assert column in record, f"{column} is not in the telemetry"
    assert float(record["commanded_x"]) == pytest.approx(0.50)
    assert float(record["commanded_yaw"]) == pytest.approx(0.25)
    assert float(record["jaw_lowest_z"]) == pytest.approx(state.lowest_z)
    assert float(record["jaw_clearance"]) == pytest.approx(state.clearance)
    assert record["belt_contact"] == "0"
    # Parked at 1.20 m with the jaw 173.5 mm below the flange, the pads stand
    # clear of a belt at 0.90 m by a hand's width.
    assert state.clearance > 0.05
    assert state.tilt_degrees < 1.0


def test_the_jaw_state_reports_a_jaw_inside_the_belt(world: Any) -> None:
    """AC-MOVE-53: the clearance is measured from the jaw's own geometry.

    There is no pose in this repository that answers how close the pads came to
    the belt, because every pose is the flange and the jaw hangs below it. This
    drives the jaw into the belt on purpose and reads the answer.
    """
    numpy = pytest.importorskip("numpy")
    mujoco, model, data, plan, arm = world
    surface = plan.belt.surface_height
    geoms = _jaw_collision_geoms(model, arm)
    belt = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "belt"))

    _park_the_arm(mujoco, model, data, arm, (0.72, -0.42, 1.20))
    parked = _jaw_state(mujoco, model, data, arm, geoms, belt, surface)
    assert parked.clearance > 0.0
    assert parked.contact is False

    from clave.world import arm as armmod

    angles = armmod.solve(model, data, arm, numpy.array([0.30, 0.0, surface + 0.15]))
    for slot, joint in enumerate(arm.joint_ids):
        data.qpos[model.jnt_qposadr[joint]] = angles[slot]
        data.ctrl[arm.actuator_ids[slot]] = angles[slot]
    mujoco.mj_forward(model, data)
    inside = _jaw_state(mujoco, model, data, arm, geoms, belt, surface)
    assert inside.clearance < 0.0, "the pads are not reporting the belt they are in"

    # Checked over the first ticks rather than only at the end: the contact is
    # stiff enough to push the jaw back out of the belt within a few of them,
    # and a run reports the contact rather than how long it lasted.
    touching = False
    for _ in range(200):
        mujoco.mj_step(model, data)
        if _jaw_state(mujoco, model, data, arm, geoms, belt, surface).contact:
            touching = True
            break
    assert touching, "the jaws are inside the belt and no contact is recorded"


def test_a_plan_reports_each_leg_for_its_own_duration() -> None:
    """AC-MOVE-38: the phase a tick carries is the leg the tick is in.

    Sampled here rather than in a run, because the run's phase column is what a
    reader trusts when a figure does not reproduce: a `DESCEND` column spanning
    twice the leg the configuration asks for is a reporting fault or a planning
    one, and this says which.
    """
    from clave.control.pick import plan_pick
    from clave.control.trajectory import State

    plan = plan_pick(
        flange=State.at_rest((0.45, -1.00, 1.20)),
        track_id=1,
        object_position=(0.30, 0.0, 1.035),
        belt_velocity=(0.314, 0.0, 0.0),
        z_offset=0.050,
        approach_speed=0.25,
        dwell_seconds=0.30,
        max_speed=1.00,
        max_acceleration=2.50,
        latest=4.00,
        at_seconds=0.0,
        margin=1.0,
    )
    assert plan is not None
    tick = 0.001
    spans: list[tuple[Phase, float]] = []
    at = plan.started_at
    while at < plan.started_at + plan.duration:
        sampled = plan.at(at)
        if sampled is None:
            break
        phase = sampled[0]
        if not spans or spans[-1][0] is not phase:
            spans.append((phase, 0.0))
        spans[-1] = (phase, spans[-1][1] + tick)
        at += tick
    assert [phase for phase, _ in spans] == [leg.phase for leg in plan.legs]
    for (_, measured), leg in zip(spans, plan.legs, strict=True):
        assert measured == pytest.approx(leg.segment.duration, abs=2 * tick)
    assert all(duration > 0.0 for _, duration in spans), "a leg was sampled for no time"
    assert sum(duration for _, duration in spans) == pytest.approx(
        plan.duration, abs=2 * tick
    )
