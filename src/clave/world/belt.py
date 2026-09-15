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

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from clave.world.config import Range
from clave.world.scene import PARKED_X, PARKED_Z, SceneLayout


@dataclass(frozen=True)
class ReachReport:
    """What the geometry implies about whether a pick is possible at all.

    Attributes:
        reach_radius: The manipulator's reachable radius, in meters.
        belt_offset: Lateral distance from the arm base to the belt centerline.
        window_length: Belt length inside the reachable radius, in meters.
        belt_speed: Belt speed in meters per second.
        time_budget: Seconds an object spends inside the window.
    """

    reach_radius: float
    belt_offset: float
    window_length: float
    belt_speed: float
    time_budget: float

    @property
    def reachable(self) -> bool:
        """Whether the belt passes within the manipulator's reach at all."""
        return self.window_length > 0.0


def within_reach(position: tuple[float, float, float], plan: SceneLayout) -> bool:
    """Whether the effector can reach a point, in three dimensions.

    The reachable window is the chord the reachable sphere cuts through the
    belt centerline, and an object is rarely on the centerline. Testing only
    the coordinate along belt travel calls an object reachable when it sits at
    the window's edge and off to the far side, where the effector cannot go.
    That is what the safety layer kept overriding, and the demonstrations
    recorded from it taught picks that could not be executed.

    Args:
        position: The object's position, in world meters.
        plan: The resolved scene layout, carrying the arm base and its reach.

    Returns:
        Whether the point lies inside the reachable sphere.
    """
    return math.dist(position, plan.arm_base) <= plan.reach_radius


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
    radius = plan.reach_radius
    if radius <= offset:
        return ReachReport(radius, offset, 0.0, plan.belt.speed, 0.0)
    half_chord = math.sqrt(radius * radius - offset * offset)
    window = 2.0 * half_chord
    return ReachReport(
        reach_radius=radius,
        belt_offset=offset,
        window_length=window,
        belt_speed=plan.belt.speed,
        time_budget=window / plan.belt.speed,
    )


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
