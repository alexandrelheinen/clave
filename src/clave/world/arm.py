"""Actuating the manipulator.

v0.5.0 placed the ROBOTIS arm in the scene and never moved it. Nothing wrote
`data.ctrl`, so there was no action to take and no reward to earn, which is why
v0.7.0 could not train a reinforcement candidate at all and why every policy
there was vision-only: the dataset had no proprioception to record because the
arm had no state worth recording.

This drives the four revolute joints toward a Cartesian target by damped least
squares on the position Jacobian. It is deliberately a reaching controller
rather than a pick-and-place state machine: FRET already owns a robot-agnostic
`PickPlaceFSM`, and duplicating it here would put two of them in the family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

ARM_JOINTS = ("arm_Joint1", "arm_Joint2", "arm_Joint3", "arm_Joint4")
GRIPPER_JOINT = "arm_Gripper"
END_EFFECTOR = "arm_link5"

DAMPING = 0.08
"""Damping for the least squares solve.

Undamped inverse kinematics diverges near a singular configuration, which for a
four degree of freedom arm reaching across a belt is not an edge case.
"""


@dataclass(frozen=True)
class ArmIndices:
    """Where the arm lives inside the model's arrays.

    The scene holds a pool of free-floating objects as well as the arm, so the
    arm's degrees of freedom are a slice of a much larger state vector and every
    Jacobian column outside it has to be discarded.

    Attributes:
        joint_ids: Model joint ids of the revolute joints, in order.
        dof_indices: Velocity-space indices of those joints.
        actuator_ids: Actuator ids driving them, in the same order.
        gripper_actuator: Actuator id of the gripper.
        end_effector: Body id whose position is controlled.
        lower: Lower joint limits.
        upper: Upper joint limits.
    """

    joint_ids: tuple[int, ...]
    dof_indices: tuple[int, ...]
    actuator_ids: tuple[int, ...]
    gripper_actuator: int
    end_effector: int
    lower: NDArray[np.float64]
    upper: NDArray[np.float64]


def locate(model: Any) -> ArmIndices:
    """Find the arm's joints, actuators and end effector in a compiled model.

    Args:
        model: The compiled model.

    Returns:
        The indices.

    Raises:
        KeyError: If the arm is not present under the expected names, which
            means the menagerie submodule moved or the attachment prefix
            changed.
    """
    import mujoco

    def joint(name: str) -> int:
        found = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if found < 0:
            raise KeyError(f"joint {name!r} is not in the model")
        return int(found)

    def actuator(name: str) -> int:
        found = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        if found < 0:
            raise KeyError(f"actuator {name!r} is not in the model")
        return int(found)

    joint_ids = tuple(joint(name) for name in ARM_JOINTS)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, END_EFFECTOR)
    if body < 0:
        raise KeyError(f"body {END_EFFECTOR!r} is not in the model")
    return ArmIndices(
        joint_ids=joint_ids,
        dof_indices=tuple(int(model.jnt_dofadr[j]) for j in joint_ids),
        actuator_ids=tuple(actuator(name) for name in ARM_JOINTS),
        gripper_actuator=actuator(GRIPPER_JOINT),
        end_effector=int(body),
        lower=np.array([model.jnt_range[j][0] for j in joint_ids]),
        upper=np.array([model.jnt_range[j][1] for j in joint_ids]),
    )


def joint_positions(model: Any, data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Read the arm's joint angles.

    This is the proprioception the dataset lacked. A policy that cannot see
    where its own arm is cannot account for it.

    Args:
        model: The compiled model.
        data: Its state.
        arm: The arm indices.

    Returns:
        Joint angles in radians, in joint order.
    """
    return np.array([float(data.qpos[model.jnt_qposadr[j]]) for j in arm.joint_ids])


def end_effector_position(data: Any, arm: ArmIndices) -> NDArray[np.float64]:
    """Read where the end effector currently is, in world coordinates."""
    return np.array(data.xpos[arm.end_effector], dtype=np.float64)


def step_toward(
    model: Any,
    data: Any,
    arm: ArmIndices,
    target: NDArray[np.float64],
    gain: float,
) -> NDArray[np.float64]:
    """Move the commanded joint angles one step toward a Cartesian target.

    Solves the damped least squares problem for a joint delta that reduces the
    end effector's distance to the target, then writes the result into the
    position actuators, clipped to the joint limits.

    Args:
        model: The compiled model.
        data: Its state, with forward kinematics already current.
        arm: The arm indices.
        target: Desired end effector position in world coordinates.
        gain: Fraction of the solved delta to apply per step.

    Returns:
        The commanded joint angles after the step.
    """
    import mujoco

    jacp = np.zeros((3, model.nv))
    mujoco.mj_jacBody(model, data, jacp, None, arm.end_effector)
    reduced = jacp[:, list(arm.dof_indices)]

    error = target - end_effector_position(data, arm)
    # Damped least squares: the undamped pseudo-inverse blows up near a
    # singularity, and a four degree of freedom arm reaching across a belt sits
    # near one routinely.
    square = reduced @ reduced.T + (DAMPING**2) * np.eye(3)
    delta = reduced.T @ np.linalg.solve(square, error)

    commanded = joint_positions(model, data, arm) + gain * delta
    clipped: NDArray[np.float64] = np.clip(commanded, arm.lower, arm.upper)
    for slot, actuator_id in enumerate(arm.actuator_ids):
        data.ctrl[actuator_id] = clipped[slot]
    return clipped


def set_gripper(data: Any, arm: ArmIndices, opening: float) -> None:
    """Command the gripper.

    Args:
        data: Simulation state.
        arm: The arm indices.
        opening: Commanded opening, clipped by the actuator's own range.
    """
    data.ctrl[arm.gripper_actuator] = opening
