"""Tests for the conveyor drive and reachability."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from clave.world import arm as armmod
from clave.world import belt, config, scene
from clave.world.scene import BeltGeometry, SceneLayout, TakeawayDrive

ROOT = Path(__file__).resolve().parents[2]
_ARM = config.load(ROOT / "configs" / "world" / "sorting_line.yml")["arm"]
_REACH_MIN = float(_ARM["reach_min"])
_REACH_MAX = float(_ARM["reach_max"])
_TOOL_ABOVE = (
    float(_ARM["tool_above_base"][0]),
    float(_ARM["tool_above_base"][1]),
)
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def layout(speed: float, offset: float) -> SceneLayout:
    """A minimal layout for reachability arithmetic, needing no physics.

    The reach bounds are the arm's own and are not parameters here: they come
    from the model rather than from a number a test picks, which is what keeps
    this arithmetic describing the manipulator the world actually has.
    """

    return SceneLayout(
        belt=BeltGeometry(
            length=3.0,
            width=1.0,
            surface_height=0.90,
            speed=speed,
            height_tolerance=0.05,
            speed_limit=1.0,
        ),
        arm_base=np.asarray((0.0, offset, 0.90), dtype=np.float64),
        reach_min=_REACH_MIN,
        reach_max=_REACH_MAX,
        tool_above_base=_TOOL_ABOVE,
        pedestal=(0.30, 0.30),
        channels=("CH-PET",),
        objects=(),
        pool_size=0,
        timestep=0.002,
        takeaway=TakeawayDrive(
            speed=0.20,
            height_min=0.25,
            height_max=0.45,
            mouth_half_width=0.15,
            past_mouth=1.50,
            toward_mouth=0.10,
        ),
    )


def test_the_report_states_the_annulus_window_and_budget() -> None:
    """The report states the annulus window and budget."""
    report = belt.reach_report(layout(speed=0.2, offset=-0.34))
    assert report.reach_min == _REACH_MIN
    assert report.reach_max == _REACH_MAX
    assert report.belt_offset == pytest.approx(0.34)
    assert report.window_length > 0
    assert report.time_budget == pytest.approx(report.window_length / 0.2)
    assert report.reachable


def test_a_belt_outside_reach_yields_no_window() -> None:
    """A world where the arm cannot touch the belt must say so.

    The offset has to clear the outer radius now. A UR10e reaches 1.25 m, so
    the 0.9 m that stranded the previous arm leaves this one comfortably on
    the belt.
    """
    report = belt.reach_report(layout(speed=0.2, offset=-(_REACH_MAX + 0.5)))
    assert report.window_length == 0.0
    assert not report.reachable


def test_a_faster_belt_shortens_the_budget() -> None:
    """The budget is what every perception latency fits inside."""
    slow = belt.reach_report(layout(speed=0.1, offset=-0.34))
    fast = belt.reach_report(layout(speed=0.4, offset=-0.34))
    assert fast.time_budget < slow.time_budget


def built(
    seed: int,
) -> tuple[dict[str, Any], np.random.Generator, Any, Any, SceneLayout]:
    """Build the shipped world at one seed, with a conveyor ready to drive.

    Args:
        seed: The seed.

    Returns:
        The configuration, the generator, the model, its state and the plan.
    """
    raw = config.load(CONFIG)
    rng = np.random.default_rng(seed)
    model, data, plan = scene.build(raw, rng, ROOT)
    return raw, rng, model, data, plan


def conveyor_for(
    raw: dict[str, Any], rng: np.random.Generator, plan: SceneLayout
) -> belt.Conveyor:
    """A conveyor built from the shipped spawn configuration.

    Args:
        raw: The configuration.
        rng: The generator.
        plan: The resolved layout.

    Returns:
        The conveyor.
    """
    spawn = raw["spawn"]
    return belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "spacing", "spawn"),
        config.require_range(spawn, "lateral_offset", "spawn"),
        config.require_range(spawn, "drop_height", "spawn"),
        belt.flat_tilt(spawn),
        entry_margin=float(spawn["entry_margin"]),
    )


def test_objects_reach_belt_speed_and_enter_the_window() -> None:
    """Objects reach belt speed and enter the window."""
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    rng = np.random.default_rng(7)
    model, data, plan = scene.build(raw, rng, ROOT)
    spawn = raw["spawn"]
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "spacing", "spawn"),
        config.require_range(spawn, "lateral_offset", "spawn"),
        config.require_range(spawn, "drop_height", "spawn"),
        belt.flat_tilt(spawn),
        entry_margin=float(spawn["entry_margin"]),
    )
    for _ in range(12000):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert conveyor.active, "nothing spawned"
    assert conveyor.entered_window(), "no object reached the arm"
    for item in conveyor.active:
        assert item.material_class.startswith("M-")
        assert item.channel.startswith("CH-")


def test_a_lifted_object_is_not_driven_by_the_belt() -> None:
    """A grasped object keeps its motion after it leaves the belt.

    AC-RATE-14. The height that counts is the bottom of the geometry.
    A point with no extent uses its own z, which is what a lifted origin
    was tested as before the bottom was available.
    """
    plan = layout(speed=0.3, offset=-0.34)
    assert belt._on_belt((0.0, 0.0, 0.90), plan)
    assert not belt._on_belt((0.0, 0.0, 0.951), plan)
    assert belt._on_belt((0.0, 0.0, 0.979), plan, bottom=0.90)
    assert not belt._on_belt((0.0, 0.0, 0.979), plan, bottom=0.96)


def test_an_unpicked_object_is_not_removed() -> None:
    """A real line does not stop for a missed pick.

    The object leaves the belt when the belt carries it off the end, and for
    no other reason. Counting what is on the belt is not enough to say that:
    the feed doses by distance, so an object can reach the end and retire in
    the same window in which nothing new is due, and the count dips for a
    reason that has nothing to do with the line removing anything. This reads
    where each object was when it went instead.
    """
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    rng = np.random.default_rng(2)
    model, data, plan = scene.build(raw, rng, ROOT)
    spawn = raw["spawn"]
    conveyor = belt.Conveyor(
        plan,
        rng,
        config.require_range(spawn, "spacing", "spawn"),
        config.require_range(spawn, "lateral_offset", "spawn"),
        config.require_range(spawn, "drop_height", "spawn"),
        belt.flat_tilt(spawn),
        entry_margin=float(spawn["entry_margin"]),
    )
    seen: dict[str, float] = {}
    left_from: dict[str, float] = {}
    end = plan.belt.length / 2.0
    for _ in range(13000):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        riding = {item.index for item in conveyor.active}
        assert not (riding & set(conveyor._free)), (
            "a pool slot with an object on the belt was handed back as free"
        )
        for item in conveyor.active:
            body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
            address = model.jnt_qposadr[model.body_jntadr[body]]
            seen[item.name] = float(data.qpos[address])
        for gone in set(seen) - {item.name for item in conveyor.active}:
            left_from[gone] = seen[gone]
    assert left_from, "no object ever left the belt, so nothing was tested"
    for name, where in left_from.items():
        assert abs(where) > end - 0.05, (
            f"{name} left the belt from x={where:.3f}, in the middle of it"
        )


def test_the_window_covers_both_halves_of_the_belt() -> None:
    """The belt is centered on the origin, so the sweep must be.

    A sweep that starts at the origin sees only the downstream half, which the
    expert then halves again to obtain the edge an object leaves reach at. The
    two ends are found here by asking the same test the safety layer asks,
    rather than by a radius this test computes for itself.
    """
    plan = layout(speed=0.2, offset=-0.70)
    step = 0.002
    reachable = [
        x * step
        for x in range(
            int(-plan.belt.length / 2.0 / step), int(plan.belt.length / 2.0 / step) + 1
        )
        if armmod.reaches(
            (plan.arm_base[0], plan.arm_base[1]),
            x * step,
            0.0,
            armmod.ReachBounds(_REACH_MIN, _REACH_MAX, _TOOL_ABOVE),
        )
    ]
    assert min(reachable) < 0.0, "nothing upstream of the arm is reachable"
    span = max(reachable) - min(reachable)
    report = belt.reach_report(plan)
    assert report.window_length == pytest.approx(span, abs=2 * step)
    # The edges a figure draws are the ones the sweep found.
    assert report.window_edges[0] == pytest.approx(min(reachable), abs=2 * step)
    assert report.window_edges[1] == pytest.approx(max(reachable), abs=2 * step)


def test_the_feed_is_by_distance_rather_than_by_elapsed_time() -> None:
    """AC-RATE-01: the feed is by distance rather than by elapsed time.

    The property the whole loop rests on. Halving the belt speed has to
    halve the number of objects released in a given span of time; a feed by
    time would release the same number and only spread them further apart.
    """
    pytest.importorskip("mujoco")
    import mujoco

    released = {}
    for speed in (0.30, 0.15):
        raw, rng, model, data, plan = built(0)
        conveyor = conveyor_for(raw, rng, plan)
        conveyor.speed = speed
        for _ in range(int(40.0 / plan.timestep)):
            mujoco.mj_step(model, data)
            conveyor.step(model, data)
        released[speed] = len(conveyor.arrivals)
    assert released[0.30] >= 6, "too few objects for the ratio to mean anything"
    assert released[0.15] == pytest.approx(released[0.30] / 2, abs=1)


def test_a_recycled_slot_is_a_new_identity_ac_gt_06() -> None:
    """AC-GT-06: a respawned object is a new identity, not the slot it reuses.

    The regression this exists for: ground-truth markers were identified by
    pool slot, and a slot is reused as soon as the object in it leaves the
    belt. The task machine remembers which identities it has already served,
    so on the shipped line it served each of the pool's slots once and then
    sat idle for the rest of the run -- four visits in sixty seconds, with the
    remaining forty seconds spent parked while objects went past.
    """
    pytest.importorskip("mujoco")
    import mujoco

    raw = config.load(CONFIG)
    raw["spawn"]["pool_size"] = 2
    rng = np.random.default_rng(0)
    model, data, plan = scene.build(raw, rng, ROOT)
    conveyor = conveyor_for(raw, rng, plan)
    conveyor.speed = 0.35
    seen: dict[int, set[int]] = {}
    for _ in range(int(40.0 / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        for item in conveyor.active:
            seen.setdefault(item.index, set()).add(item.serial)
    assert len(conveyor.arrivals) > plan.pool_size, "the pool was never spent"
    reused = {slot: serials for slot, serials in seen.items() if len(serials) > 1}
    assert reused, "no slot was ever reused, so nothing was tested"
    for slot, serials in reused.items():
        assert len(serials) > 1, f"slot {slot} reported one identity twice"


def test_a_resting_package_does_not_move_relative_to_the_belt_ac_rate_16() -> None:
    """AC-RATE-16: a resting package travels with the belt and does not turn.

    The spin is cleared after each step while the arm is not touching the
    package. Keeping that pin after the arm has made contact is the failure
    AC-RATE-11 records, and it is not what this test asks for.
    """
    pytest.importorskip("mujoco")
    import mujoco

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    conveyor.speed = 0.35
    for _ in range(int(12.0 / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert conveyor.active, "nothing was on the belt to test"
    item = conveyor.active[0]
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
    address = model.jnt_qposadr[model.body_jntadr[body]]
    dof = model.jnt_dofadr[model.body_jntadr[body]]
    start_x = float(data.qpos[address])
    start_y = float(data.qpos[address + 1])
    data.qvel[dof + 5] = 5.0
    data.qvel[dof + 1] = 0.4
    elapsed = 0.5
    for _ in range(int(elapsed / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert abs(float(data.qvel[dof + 5])) < 1e-6
    assert abs(float(data.qvel[dof + 1])) < 1e-6
    assert float(data.qvel[dof]) == pytest.approx(0.35)
    assert float(data.qpos[address]) == pytest.approx(
        start_x + 0.35 * elapsed, abs=0.01
    )
    assert float(data.qpos[address + 1]) == pytest.approx(start_y, abs=0.01)
    quat = data.qpos[address + 3 : address + 7]
    sine = float(np.linalg.norm(quat[1:]))
    lean = 2.0 * float(np.arctan2(sine, float(quat[0])))
    assert lean <= float(raw["spawn"]["rest_tilt_radians"])
    # Past the configured lean, and still inside the belt's height band.
    # A right angle swings the mesh through the belt, so the drive no
    # longer sees a package resting on it.
    data.qpos[address + 3 : address + 7] = [0.99500417, 0.09983342, 0.0, 0.0]
    conveyor.step(model, data)
    assert float(data.qpos[address + 3]) == pytest.approx(1.0)
    assert data.qpos[address + 4 : address + 7] == pytest.approx((0.0, 0.0, 0.0))


def test_packages_lie_flat_and_stay_graspable_ac_rate_16() -> None:
    """AC-RATE-16: a package lies flat, and one horizontal side still fits the jaw."""
    pytest.importorskip("mujoco")
    import mujoco

    raw, _rng, model, data, plan = built(0)
    height = float(raw["spawn"]["crushed_height"])
    minimum = float(raw["spawn"]["minimum_rest_height"])
    opening = float(raw["arm"]["max_grasp_width"])
    mujoco.mj_forward(model, data)
    seen = 0
    for index, spec in enumerate(plan.objects):
        geom = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_GEOM, f"object_{index}_geom"
        )
        mesh = int(model.geom_dataid[geom])
        start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
        local = np.asarray(model.mesh_vert[start : start + count], dtype=np.float64)
        rotation = np.asarray(data.geom_xmat[geom], dtype=np.float64).reshape(3, 3)
        origin = np.asarray(data.geom_xpos[geom], dtype=np.float64)
        world = local @ rotation.T + origin
        extents = world.max(axis=0) - world.min(axis=0)
        standing = float(extents[2])
        assert minimum - 1e-3 <= standing <= height + 1e-3, spec.name
        assert min(float(extents[0]), float(extents[1])) < opening, spec.name
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"object_{index}")
        place = np.asarray(data.xpos[body], dtype=np.float64)
        centre = (world.min(axis=0) + world.max(axis=0)) / 2.0
        assert centre[0] == pytest.approx(float(place[0]), abs=0.002), spec.name
        assert centre[1] == pytest.approx(float(place[1]), abs=0.002), spec.name
        assert float(world[:, 2].min()) == pytest.approx(float(place[2]), abs=0.002), (
            spec.name
        )
        seen += 1
    assert seen == len(plan.objects)


def test_an_arm_contact_releases_the_rest_constraint_ac_rate_16() -> None:
    """AC-RATE-16: a package the arm is touching keeps the velocity it has.

    The rest write stops at that contact. Continuing it is the pin that
    tips the package under the jaw.
    """
    pytest.importorskip("mujoco")
    import mujoco

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    for _ in range(int(8.0 / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        if conveyor.active:
            break
    assert conveyor.active, "nothing spawned to put under the jaw"
    item = conveyor.active[0]
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
    pad = None
    for geom in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom) or ""
        if name.endswith("pad1"):
            pad = geom
            break
    assert pad is not None
    mujoco.mj_forward(model, data)
    address = model.jnt_qposadr[model.body_jntadr[body]]
    data.qpos[address : address + 3] = data.geom_xpos[pad]
    data.qpos[address + 3 : address + 7] = [1.0, 0.0, 0.0, 0.0]
    velocity = model.jnt_dofadr[model.body_jntadr[body]]
    data.qvel[velocity : velocity + 6] = 0.0
    mujoco.mj_step(model, data)
    assert body in belt._packages_touching_arm(mujoco, model, data)
    # The contact is the one the step just resolved. Move the package onto
    # the belt before the drive runs, without another dynamics step, so the
    # drive sees a resting package that the arm is already touching.
    data.qpos[address : address + 3] = [0.0, 0.0, plan.belt.surface_height]
    data.qvel[velocity] = 0.1
    data.qvel[velocity + 5] = 1.5
    data.qpos[address + 3 : address + 7] = [0.70710678, 0.70710678, 0.0, 0.0]
    conveyor.step(model, data)
    assert float(data.qvel[velocity + 5]) == pytest.approx(1.5)
    assert float(data.qvel[velocity]) == pytest.approx(0.1)
    assert data.qpos[address + 3 : address + 7] == pytest.approx(
        (0.70710678, 0.70710678, 0.0, 0.0)
    )


def _rest_on_surface(
    mujoco: Any, model: Any, data: Any, slot: int, plan: SceneLayout
) -> float:
    """Put one pooled body upright with its bottom on the belt.

    Args:
        mujoco: The imported module.
        model: The compiled model.
        data: Its state, modified in place.
        slot: Pool slot.
        plan: The resolved layout.

    Returns:
        How far the origin sits above the bottom. Above the height tolerance
        means the origin test would have left this package undriven.
    """
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"object_{slot}")
    address = model.jnt_qposadr[model.body_jntadr[body]]
    surface = plan.belt.surface_height
    data.qpos[address : address + 7] = [0.0, 0.0, surface, 1.0, 0.0, 0.0, 0.0]
    velocity = model.jnt_dofadr[model.body_jntadr[body]]
    data.qvel[velocity : velocity + 6] = 0.0
    mujoco.mj_kinematics(model, data)
    bottom = belt._body_bottom(model, data, body)
    rise = surface - bottom
    data.qpos[address + 2] = surface + rise
    mujoco.mj_kinematics(model, data)
    return rise


def test_a_package_resting_on_its_bottom_is_driven_ac_rate_14() -> None:
    """AC-RATE-14: a package is driven from its bottom, not its origin.

    A crushed package can sit with its origin inside the height tolerance.
    The drive still has to follow the bottom: an origin above the tolerance
    whose bottom is on the surface is on the belt, and a package placed that
    way is carried at belt speed.
    """
    mujoco = pytest.importorskip("mujoco")

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    conveyor.speed = 0.25
    surface = plan.belt.surface_height
    tolerance = plan.belt.height_tolerance
    assert belt._on_belt((0.0, 0.0, surface + tolerance + 0.02), plan, bottom=surface)
    for _ in range(int(8.0 / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        if conveyor.active:
            break
    assert conveyor.active, "nothing spawned to rest on the belt"
    item = conveyor.active[0]
    _rest_on_surface(mujoco, model, data, item.index, plan)
    mujoco.mj_step(model, data)
    conveyor.step(model, data)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
    velocity = model.jnt_dofadr[model.body_jntadr[body]]
    assert float(data.qvel[velocity]) == pytest.approx(0.25)


def test_a_package_past_the_side_guide_returns_to_the_pool_ac_rate_15() -> None:
    """AC-RATE-15: a package past the side guide, still at belt height, returns."""
    mujoco = pytest.importorskip("mujoco")

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    slot = 0
    _rest_on_surface(mujoco, model, data, slot, plan)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"object_{slot}")
    address = model.jnt_qposadr[model.body_jntadr[body]]
    data.qpos[address + 1] = plan.belt.width / 2.0 + 0.05
    mujoco.mj_kinematics(model, data)
    conveyor._next_free = 1
    conveyor.active.append(
        belt.SpawnedObject(
            index=slot,
            name=f"object_{slot}",
            material_class="M-01",
            channel="CH-PET",
            serial=1,
        )
    )
    conveyor.step(model, data)
    assert conveyor.active == []
    assert slot in conveyor._free
    assert conveyor.retired == 1


def test_a_package_over_a_chute_stays_until_it_falls() -> None:
    """AC-RATE-15: a package over a chute mouth is not returned to the pool.

    The release lowers the package back through belt height beside the
    belt. Recycling it there removes the place before the mouth can count it.
    """
    mujoco = pytest.importorskip("mujoco")

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    slot = 0
    _rest_on_surface(mujoco, model, data, slot, plan)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"object_{slot}")
    address = model.jnt_qposadr[model.body_jntadr[body]]
    mouth = next(iter(plan.chutes.values()))
    data.qpos[address] = float(mouth[0])
    data.qpos[address + 1] = float(mouth[1])
    mujoco.mj_kinematics(model, data)
    assert belt._beside_chute(float(mouth[0]), float(mouth[1]), plan)
    conveyor._next_free = 1
    item = belt.SpawnedObject(
        index=slot,
        name=f"object_{slot}",
        material_class="M-01",
        channel="CH-PET",
        serial=1,
    )
    conveyor.active.append(item)
    conveyor.step(model, data)
    assert conveyor.active == [item]


def test_a_lifted_package_past_the_belt_stays_with_the_arm() -> None:
    """AC-RATE-15: a lifted package past the belt edge is not recycled."""
    mujoco = pytest.importorskip("mujoco")

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    slot = 0
    rise = _rest_on_surface(mujoco, model, data, slot, plan)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"object_{slot}")
    address = model.jnt_qposadr[model.body_jntadr[body]]
    data.qpos[address + 1] = -(plan.belt.width / 2.0 + 0.05)
    data.qpos[address + 2] = (
        float(data.qpos[address + 2]) + plan.belt.height_tolerance + 0.02
    )
    mujoco.mj_kinematics(model, data)
    bottom = belt._body_bottom(model, data, body)
    assert bottom > plan.belt.surface_height + plan.belt.height_tolerance
    conveyor._next_free = 1
    item = belt.SpawnedObject(
        index=slot,
        name=f"object_{slot}",
        material_class="M-01",
        channel="CH-PET",
        serial=1,
    )
    conveyor.active.append(item)
    conveyor.step(model, data)
    assert conveyor.active == [item]
    assert rise > 0.0


def test_close_centers_keep_moving_ac_rate_14() -> None:
    """AC-RATE-14: packages at 0.125 m centers stay on the belt speed.

    This is the gap that used to stall a tall package and overflow the step.
    """
    mujoco = pytest.importorskip("mujoco")

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    conveyor.spacing = config.Range(0.125, 0.125)
    conveyor.speed = 0.25
    steps = int(8.0 / plan.timestep)
    for _ in range(steps):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise AssertionError("the belt state left the finite range")
        for item in conveyor.active:
            body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
            dof = model.jnt_dofadr[model.body_jntadr[body]]
            for axis in range(3):
                assert abs(float(data.qvel[dof + axis])) <= plan.belt.speed_limit
    on_belt = 0
    speeds: list[float] = []
    for item in conveyor.active:
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
        address = model.jnt_qposadr[model.body_jntadr[body]]
        velocity = model.jnt_dofadr[model.body_jntadr[body]]
        position = data.qpos[address : address + 3]
        assert abs(float(position[0])) < plan.belt.length
        assert abs(float(position[1])) < 1.0
        assert float(position[2]) < 2.0
        bottom = belt._body_bottom(model, data, body)
        if not belt._on_belt(position, plan, bottom):
            continue
        speeds.append(float(data.qvel[velocity]))
        on_belt += 1
    assert on_belt >= 8, "packages left the belt instead of riding it"
    assert len(conveyor.arrivals) >= 10
    assert float(np.median(speeds)) == pytest.approx(conveyor.running, abs=0.05)


def test_a_slot_returns_to_the_pool_once_its_object_leaves() -> None:
    """AC-RATE-01: a slot returns to the pool once its object leaves.

    A compiled model cannot gain bodies at run time, so a line that never
    gives a slot back stops feeding after `pool_size` objects. A rate held
    for ninety seconds is a different claim from a rate held.
    """
    pytest.importorskip("mujoco")
    import mujoco

    raw, rng, model, data, plan = built(0)
    conveyor = conveyor_for(raw, rng, plan)
    conveyor.speed = 0.35
    for _ in range(int(240.0 / plan.timestep)):
        mujoco.mj_step(model, data)
        conveyor.step(model, data)
    assert conveyor.retired > 0, "nothing ever left the belt"
    assert len(conveyor.arrivals) > plan.pool_size, (
        "the line stopped feeding once the pool was spent"
    )
