from __future__ import annotations

import math
from typing import cast

from clave.control.settings import Phase, Profile
from clave.control.trajectory import State

from .task_test import PARK, candidate, machine, queue_of


def test_jaw_abandoned_if_not_reaching_seat_fraction_0_5() -> None:
    task = machine(
        profile=Profile.FULL_VISIT,
        approach_height=0.220,
        dwell_seconds=0.30,
        grasp_seat_fraction=0.70,
    )
    head = candidate(track_id=1, x=0.30, y=0.0)
    queue = queue_of(head)

    goal = task.step(queue, flange=PARK, at_seconds=0.0)
    assert goal is not None
    assert task._plan is not None
    plan = task._plan
    pick_time = plan.pick_at

    sample1 = cast(tuple[Phase, State, float], plan.at(pick_time - 0.01))
    sample2 = cast(tuple[Phase, State, float], plan.at(pick_time))

    task.tick(
        flange=sample1[1].position,
        tool_yaw=0.0,
        object_yaw=math.pi / 2.0,
        jaw_travel=0.0,
        seconds_left=100.0,
        at_seconds=pick_time - 0.01,
    )

    task.tick(
        flange=sample2[1].position,
        tool_yaw=math.pi / 2.0,
        object_yaw=math.pi / 2.0,
        jaw_travel=0.0,
        seconds_left=100.0,
        at_seconds=pick_time,
    )

    task.tick(
        flange=sample2[1].position,
        tool_yaw=math.pi / 2.0,
        object_yaw=math.pi / 2.0,
        jaw_travel=0.0,
        seconds_left=100.0,
        at_seconds=pick_time + 0.15,
    )

    abandon_time = pick_time + 0.31
    final_tick = task.tick(
        flange=sample2[1].position,
        tool_yaw=math.pi / 2.0,
        object_yaw=math.pi / 2.0,
        jaw_travel=0.4,
        seconds_left=100.0,
        at_seconds=abandon_time,
    )

    assert final_tick is None
    abandoned = task.abandoned
    assert len(abandoned) == 1
    assert abandoned[0][0] == 1
    assert abandoned[0][1] == "the fingers did not reach seat fraction 0.5"
