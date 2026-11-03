"""Per-visit record of the fingers, the contact, and where the pinch sat.

A close command is not a grasp. The log is the driver joints, the force
the pads exchange with the package, and the pinch's place relative to that
package while the jaw is coming down (`AC-BEHAVE-07`). Nothing here welds
a package to the gripper or writes its pose.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

_PERIOD_SECONDS = 0.01
"""How often a visit is sampled, in seconds."""


class PickLog:
    """Append one row per sample of an active visit."""

    def __init__(self, path: Path, model: Any) -> None:
        self.path = path
        self._pads = _pad_bodies(model)
        self._right = _joint_address(model, "arm_grip_right_driver_joint")
        self._left = _joint_address(model, "arm_grip_left_driver_joint")
        self._low, self._span = _driver_range(model)
        self._file = path.open("w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(
            [
                "time",
                "track",
                "phase",
                "grip",
                "driver_right_rad",
                "driver_left_rad",
                "driver_fraction",
                "pinch_x",
                "pinch_y",
                "pinch_z",
                "object_x",
                "object_y",
                "object_z",
                "dx_m",
                "dy_m",
                "jaw_lowest_z",
                "object_top_z",
                "pad_force_n",
                "pad_contacts",
            ]
        )
        self._next = 0.0
        self._force = np.zeros(6, dtype=np.float64)

    def record(
        self,
        model: Any,
        data: Any,
        *,
        track: int | None,
        phase: str,
        grip: float,
        pinch: tuple[float, float, float],
        object_xyz: tuple[float, float, float],
        object_body: int,
        jaw_lowest_z: float,
        object_top_z: float,
    ) -> None:
        """Write one sample when a visit is active and the period is due.

        Args:
            model: The compiled model.
            data: Its state, after the dynamics step.
            track: The visit's target, or None when the arm is not on one.
            phase: The phase the tick commanded.
            grip: The jaw command, from 0 open to 1 shut.
            pinch: Where the jaw closes, in world meters.
            object_xyz: The package centre, in world meters.
            object_body: The package's body id, for the contact search.
            jaw_lowest_z: The lowest collision point of the jaw, in meters.
            object_top_z: The highest point of the package, in meters.
        """
        if track is None:
            return
        now = float(data.time)
        if now + 1e-12 < self._next:
            return
        force, contacts = self._pad_force(model, data, object_body)
        right = _qpos(data, self._right)
        left = _qpos(data, self._left)
        fraction = (
            0.0
            if self._span <= 0.0 or right is None
            else (right - self._low) / self._span
        )
        self._writer.writerow(
            [
                now,
                track,
                phase,
                grip,
                "" if right is None else right,
                "" if left is None else left,
                fraction,
                pinch[0],
                pinch[1],
                pinch[2],
                object_xyz[0],
                object_xyz[1],
                object_xyz[2],
                pinch[0] - object_xyz[0],
                pinch[1] - object_xyz[1],
                jaw_lowest_z,
                object_top_z,
                force,
                contacts,
            ]
        )
        self._file.flush()
        self._next += _PERIOD_SECONDS

    def close(self) -> None:
        """Flush and close the file."""
        self._file.close()

    def _pad_force(self, model: Any, data: Any, object_body: int) -> tuple[float, int]:
        """Return the normal force and the contact count of pads on one body.

        Args:
            model: The compiled model.
            data: Its state.
            object_body: The package.

        Returns:
            The summed normal force in newtons, and how many contacts added
            to it. Both are zero when nothing is touching.
        """
        import mujoco

        total = 0.0
        count = 0
        if object_body < 0 or not self._pads:
            return total, count
        for index in range(int(data.ncon)):
            contact = data.contact[index]
            first = int(model.geom_bodyid[int(contact.geom1)])
            second = int(model.geom_bodyid[int(contact.geom2)])
            pads_here = first in self._pads or second in self._pads
            if object_body not in (first, second) or not pads_here:
                continue
            mujoco.mj_contactForce(model, data, index, self._force)
            total += float(self._force[0])
            count += 1
        return total, count


def _pad_bodies(model: Any) -> frozenset[int]:
    """Return body ids whose name marks a finger pad."""
    import mujoco

    found: set[int] = set()
    for body in range(int(model.nbody)):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body) or ""
        if "pad" in name:
            found.add(body)
    return frozenset(found)


def _joint_address(model: Any, name: str) -> int | None:
    """Return a joint's qpos address, or None when the model has no such joint."""
    import mujoco

    joint = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name))
    if joint < 0:
        return None
    return int(model.jnt_qposadr[joint])


def _driver_range(model: Any) -> tuple[float, float]:
    """Return the right driver joint's lower stop and its span, in radians."""
    import mujoco

    joint = int(
        mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, "arm_grip_right_driver_joint"
        )
    )
    if joint < 0:
        return 0.0, 0.0
    low, high = model.jnt_range[joint]
    return float(low), float(high - low)


def _qpos(data: Any, address: int | None) -> float | None:
    """Return one joint position, or None when the address is absent."""
    if address is None:
        return None
    return float(data.qpos[address])
