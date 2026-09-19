"""One commanded pose, turned into joint angles and written to the actuators.

The only module in the control path that compiles a model, and the only one
with no decisions in it. It takes the pose guidance produced, asks
`clave.world.arm` for joint angles that put the flange there with the tool
vertical, and writes them.

It reports a refusal rather than swallowing one. `arm.step_toward` leaves the
command untouched for a target outside the trusted region, which is correct
for a controller and useless for a report: an arm that quietly stops moving
looks identical to an arm that arrived. So the reach is checked here and the
refusal travels back, which is what lets the task machine fault the track and
the run count it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from clave.control.guidance import Command
from clave.world import arm as armmod


@dataclass(frozen=True)
class Step:
    """What one servo tick did.

    Attributes:
        joints: The joint angles commanded, in joint order.
        refusal: Why the pose was refused, or None when it was taken.
    """

    joints: NDArray[np.float64]
    refusal: str | None


def follow(
    model: Any, data: Any, arm: armmod.ArmIndices, command: Command, gain: float
) -> Step:
    """Command one pose and report whether the arm could take it.

    Args:
        model: The compiled model.
        data: Its state, with forward kinematics already current.
        arm: The arm indices.
        command: The pose to command.
        gain: Fraction of the solved step to command.

    Returns:
        The step. A refused pose writes no actuator command, so the arm holds
        whatever it was last told.
    """
    target = np.array(command.position, dtype=np.float64)
    if not armmod.reachable(arm, target):
        # Hold, rather than write nothing. An uncommanded arm sags under
        # gravity, the sag puts the flange outside the trusted band, and from
        # there every pose is refused for a reason the controller caused. The
        # command written is where the arm already is, which is derived from
        # the arm and not from the pose that was refused.
        holding = armmod.joint_positions(model, data, arm)
        for slot, actuator in enumerate(arm.actuator_ids):
            data.ctrl[actuator] = holding[slot]
        return Step(joints=holding, refusal=_why(arm, target))

    # A goal that asked for no rotation gets the one the tool already holds,
    # which is how an unoriented footprint reaches the actuators without
    # anybody inventing an angle for it.
    yaw = command.yaw if command.yaw is not None else armmod.tool_yaw(data, arm)
    return Step(
        joints=armmod.step_toward(model, data, arm, target, gain=gain, yaw=yaw),
        refusal=None,
    )


def _why(arm: armmod.ArmIndices, target: NDArray[np.float64]) -> str:
    """Return why a pose is outside the region the arm is trusted over.

    Args:
        arm: The arm indices.
        target: The pose that was refused.

    Returns:
        A sentence naming which bound it broke, so a fault says something a
        reader can act on rather than that something went wrong.
    """
    import math

    radius = math.hypot(
        float(target[0]) - float(arm.base_position[0]),
        float(target[1]) - float(arm.base_position[1]),
    )
    if not armmod.REACH_MIN_METERS <= radius <= armmod.REACH_MAX_METERS:
        return (
            f"{radius:.3f} m from the base, outside the "
            f"{armmod.REACH_MIN_METERS:.2f} m to "
            f"{armmod.REACH_MAX_METERS:.2f} m annulus"
        )
    lowest, highest = armmod.TOOL_ABOVE_BASE_METERS
    above = float(target[2]) - float(arm.base_position[2])
    return (
        f"{above:+.3f} m from the base, outside the trusted "
        f"{lowest:+.2f} m to {highest:+.2f} m band"
    )
