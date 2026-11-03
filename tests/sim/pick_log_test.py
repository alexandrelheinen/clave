"""A visit records the fingers, the pad force, and where the pinch sat."""

from pathlib import Path

import mujoco
import numpy as np

from clave.sim.pick_log import PickLog

_MODEL = """
<mujoco>
  <worldbody>
    <body name="object_0" pos="0 0 0.90">
      <freejoint/>
      <geom type="box" size="0.03 0.03 0.02"/>
    </body>
    <body name="arm_right_pad" pos="0.01 0 0.95">
      <joint name="arm_grip_right_driver_joint" type="hinge" axis="0 1 0"
        range="0 0.8"/>
      <geom name="pad_right" type="box" size="0.01 0.004 0.01"/>
    </body>
    <body name="arm_left_pad" pos="-0.01 0 0.95">
      <joint name="arm_grip_left_driver_joint" type="hinge" axis="0 1 0"
        range="0 0.8"/>
      <geom type="box" size="0.01 0.004 0.01"/>
    </body>
  </worldbody>
</mujoco>
"""


def test_a_visit_records_the_fingers_the_force_and_the_offset(tmp_path: Path) -> None:
    """AC-BEHAVE-07: a visit records the fingers, the force, and the offset."""
    model = mujoco.MjModel.from_xml_string(_MODEL)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "object_0")
    path = tmp_path / "pick-evidence.csv"
    log = PickLog(path, model)
    centre = data.xipos[body]
    log.record(
        model,
        data,
        track=3,
        phase="descend",
        grip=0.0,
        pinch=(float(centre[0]) + 0.01, float(centre[1]), float(centre[2])),
        object_xyz=(float(centre[0]), float(centre[1]), float(centre[2])),
        object_body=int(body),
        jaw_lowest_z=0.93,
        object_top_z=0.92,
    )
    log.record(
        model,
        data,
        track=None,
        phase="standby",
        grip=0.0,
        pinch=(0.0, 0.0, 0.0),
        object_xyz=(0.0, 0.0, 0.0),
        object_body=int(body),
        jaw_lowest_z=0.0,
        object_top_z=0.0,
    )
    log.close()
    rows = path.read_text().strip().splitlines()
    assert len(rows) == 2
    header = rows[0].split(",")
    assert "driver_right_rad" in header
    assert "pad_force_n" in header
    assert "dx_m" in header
    fields = dict(zip(header, rows[1].split(","), strict=True))
    assert fields["track"] == "3"
    assert fields["phase"] == "descend"
    assert float(fields["dx_m"]) == np.float64(0.01)
    assert float(fields["dy_m"]) == np.float64(0.0)
    assert float(fields["pad_force_n"]) == np.float64(0.0)
    assert fields["driver_right_rad"] != ""
