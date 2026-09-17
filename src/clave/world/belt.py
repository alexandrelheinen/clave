"""The conveyor: spawning, carrying, and reachability.

MuJoCo has no conveyor primitive. Objects are free bodies whose horizontal
velocity is driven to the belt speed while they rest on the belt, leaving
vertical motion, rotation and contact to physics. This is a driven constraint
rather than a friction model, which is the honest description: objects do not
slip, and a real line's slip is a disturbance this world does not reproduce.

An object that passes the reachable window is left alone. A real line does not
stop, so an unpicked object is a throughput loss rather than a fault.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from clave.world import arm
from clave.world.config import Range
from clave.world.scene import PARKED_X, PARKED_Z, SceneLayout


@dataclass(frozen=True)
class ReachReport:
    """What the geometry implies about whether a pick is possible at all.

    Attributes:
        reach_min: Inner radius of the annulus the arm is trusted over.
        reach_max: Outer radius of that annulus, in meters.
        belt_offset: Lateral distance from the shoulder to the belt centerline.
        window_length: Belt length a centerline object spends inside the
            annulus, in meters, with the dead zone already deducted.
        window_edges: Where along the belt the window opens and closes, in
            world meters. Both are zero when the belt never enters reach.
        belt_speed: Belt speed in meters per second.
        time_budget: Seconds an object spends inside the window.
    """

    reach_min: float
    reach_max: float
    belt_offset: float
    window_length: float
    window_edges: tuple[float, float]
    belt_speed: float
    time_budget: float

    @property
    def reachable(self) -> bool:
        """Whether the belt passes within the manipulator's reach at all."""
        return self.window_length > 0.0


def within_reach(position: tuple[float, float, float], plan: SceneLayout) -> bool:
    """Whether the tool can reach a point.

    The arm is trusted over an annulus about its base, within a vertical band,
    both measured by sweeping the compiled model with the tool held vertical.
    The region is smaller than what the arm can actually serve, on purpose: a
    caller that trusts it is never surprised.

    The inner radius is not a defect to work around. An object inside it is
    carried out of it by the belt, so the dead zone costs pick time rather than
    coverage.

    Args:
        position: The object's position, in world meters.
        plan: The resolved scene layout, carrying the arm base and the
            workspace.

    Returns:
        Whether the tool can be placed on the object.
    """
    lowest, highest = plan.tool_above_base
    above = position[2] - plan.arm_base[2]
    if not lowest <= above <= highest:
        return False
    return arm.reaches((plan.arm_base[0], plan.arm_base[1]), position[0], position[1])


def reach_report(plan: SceneLayout) -> ReachReport:
    """Compute the reachable window and the per-object time budget.

    The window is the chord the reachable sphere cuts through the belt
    centerline. The budget is that chord divided by belt speed, and it is the
    number every perception latency has to fit inside.

    Args:
        plan: The resolved scene layout.

    Returns:
        The report. `window_length` is zero when the belt never enters reach.
    """
    offset = abs(plan.arm_base[1])
    # Swept rather than solved, so the window is measured through exactly the
    # test the safety layer applies. A closed-form chord would be correct for
    # this arm's annulus, and was wrong for the last one; measuring costs
    # milliseconds once and cannot drift.
    #
    # AC-REACH-07: the sweep spans the belt's own extent. Objects ride from
    # -length/2 to +length/2, so a sweep starting at the origin measures the
    # downstream half and reports a window half the size of the one the arm
    # actually has.
    step = 0.002
    hits = 0
    first = last = 0.0
    seen = False
    x = -plan.belt.length / 2.0
    while x <= plan.belt.length / 2.0:
        # The belt centerline is y = 0; `offset` is how far the shoulder sits
        # from it, which the sweep sees through the shoulder position rather
        # than by being passed as a coordinate.
        if arm.reaches((plan.arm_base[0], plan.arm_base[1]), x, 0.0):
            hits += 1
            last = x
            if not seen:
                first = x
                seen = True
        x += step
    window = hits * step
    return ReachReport(
        reach_min=plan.reach_min,
        reach_max=plan.reach_max,
        belt_offset=offset,
        window_length=window,
        window_edges=(first, last),
        belt_speed=plan.belt.speed,
        time_budget=window / plan.belt.speed if plan.belt.speed else 0.0,
    )


def window_exit(plan: SceneLayout) -> float | None:
    """Return the belt coordinate at which the reachable window closes.

    The scripted expert ranks objects by how little time they have left, which
    is their distance to this coordinate, so a wrong value here teaches picks
    that cannot be made.

    It is the swept downstream edge rather than half the window's length. Those
    two agree only while the arm stands at the belt centre: move the arm and the
    window moves with it, leaving half the length naming a coordinate the arm
    cannot reach.

    Args:
        plan: The resolved scene layout.

    Returns:
        The downstream edge in world meters, or None when the belt never enters
        reach and there is no edge to name.
    """
    report = reach_report(plan)
    return report.window_edges[1] if report.reachable else None


@dataclass
class SpawnedObject:
    """One object riding the belt.

    Attributes:
        index: Pool slot, which is also the body index into the model.
        name: Body name in the model.
        material_class: Taxonomy identifier, recorded at spawn so a consumer
            never has to infer it.
        channel: Default channel for that class.
        entered_window: Whether it has been seen inside the reachable window.
    """

    index: int
    name: str
    material_class: str
    channel: str
    entered_window: bool = False


@dataclass
class Conveyor:
    """Drives the belt, spawns objects, and tracks reachability.

    Attributes:
        plan: The resolved scene layout.
        rng: Generator used for spawn timing and placement.
        interval: Range the next spawn delay is drawn from.
        lateral: Range the lateral placement is drawn from.
        drop: Range the drop height above the belt is drawn from.
    """

    plan: SceneLayout
    rng: np.random.Generator
    interval: Range
    lateral: Range
    drop: Range
    entry_margin: float = 0.0
    active: list[SpawnedObject] = field(default_factory=list)
    _next_free: int = 0
    _next_spawn: float = 0.0

    @property
    def report(self) -> ReachReport:
        """The reachability report for this layout."""
        return reach_report(self.plan)

    def _place(self, model: Any, data: Any, slot: int) -> SpawnedObject:
        """Put one pooled object at the belt entrance."""
        import mujoco

        template = self.plan.objects[slot % len(self.plan.objects)]
        name = f"object_{slot}"
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        address = model.jnt_qposadr[model.body_jntadr[body]]
        data.qpos[address : address + 3] = [
            -self.plan.belt.length / 2.0 + self.entry_margin,
            self.lateral.sample(self.rng),
            self.plan.belt.surface_height + self.drop.sample(self.rng),
        ]
        data.qpos[address + 3 : address + 7] = [1.0, 0.0, 0.0, 0.0]
        velocity = model.jnt_dofadr[model.body_jntadr[body]]
        data.qvel[velocity : velocity + 6] = 0.0
        spawned = SpawnedObject(
            index=slot,
            name=name,
            material_class=template.material_class,
            channel=template.channel,
        )
        self.active.append(spawned)
        return spawned

    def _hold_parked(self, model: Any, data: Any) -> None:
        """Pin every unspawned pool slot in place.

        Parked slots rest on the floor clear of the belt, so the scene is
        stable without this. Pinning them anyway keeps a recorded rollout
        identical from one run to the next, since a body settling under gravity
        is one more thing that would have to converge the same way twice.
        """
        import mujoco

        for slot in range(self._next_free, self.plan.pool_size):
            body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f"object_{slot}")
            address = model.jnt_qposadr[model.body_jntadr[body]]
            velocity = model.jnt_dofadr[model.body_jntadr[body]]
            data.qpos[address : address + 3] = [
                PARKED_X + 0.3 * slot,
                PARKED_X,
                PARKED_Z,
            ]
            data.qpos[address + 3 : address + 7] = [1.0, 0.0, 0.0, 0.0]
            data.qvel[velocity : velocity + 6] = 0.0

    def step(self, model: Any, data: Any) -> None:
        """Advance spawning and belt drive by one simulation step.

        Args:
            model: The compiled model.
            data: Its state, already stepped by the caller.
        """
        import mujoco

        self._hold_parked(model, data)

        if data.time >= self._next_spawn and self._next_free < self.plan.pool_size:
            self._place(model, data, self._next_free)
            self._next_free += 1
            self._next_spawn = data.time + self.interval.sample(self.rng)

        for item in self.active:
            body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, item.name)
            address = model.jnt_qposadr[model.body_jntadr[body]]
            velocity = model.jnt_dofadr[model.body_jntadr[body]]
            position = data.qpos[address : address + 3]
            on_belt = (
                abs(position[0]) <= self.plan.belt.length / 2.0
                and abs(position[1]) <= self.plan.belt.width / 2.0
                and position[2] > self.plan.belt.surface_height - 0.05
            )
            if on_belt:
                # Drive travel only. Vertical motion and rotation stay with
                # physics, so contacts with bins and the arm remain real.
                data.qvel[velocity] = self.plan.belt.speed
            if on_belt and within_reach(
                (float(position[0]), float(position[1]), float(position[2])), self.plan
            ):
                item.entered_window = True

    def entered_window(self) -> list[SpawnedObject]:
        """List the objects that have been inside the reachable window."""
        return [item for item in self.active if item.entered_window]
