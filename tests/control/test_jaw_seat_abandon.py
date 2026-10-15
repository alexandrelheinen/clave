import math
import numpy as np

from clave.control.selection import Candidate
from clave.control.task import Phase
from .task_test import machine, PARK, queue_of, candidate, Profile

def test_jaw_seat_abandon() -> None:
    """If the jaws never seat, abandon the pick; do not treat close-dwell expiry as a successful seat."""
    arm = machine(
        profile=Profile.FULL_VISIT,
        grasp_seat_fraction=0.70,
        dwell_seconds=0.15,
    )
    aimed_at = candidate()
    arm.step(queue_of(aimed_at), PARK, 0.0)

    at_seconds = 0.0
    # Tick into HOLD with grip commanded shut
    while at_seconds < 12.0:
        at_seconds += 0.01
        flown = arm.tick(at_seconds, PARK, jaw_travel=0.0, seconds_left=30.0)
        if flown is not None and flown.phase is Phase.HOLD and flown.grip >= 0.5:
            break

    # Keep passing jaw_travel=0.2 (below seat) until tick returns None
    finished = "not none"
    for _ in range(80):  # More than enough to trigger dwell expiry (0.15s / 0.01s = 15 ticks)
        at_seconds += 0.01
        flown = arm.tick(at_seconds, PARK, jaw_travel=0.2, seconds_left=30.0)
        if flown is None:
            finished = None
            break

    assert finished is None
    assert arm.served == ()
    assert arm.last_visit_closed is False
    assert len(arm.abandoned) > 0

    reason = arm.abandoned[0][1]
    assert "seat" in reason or "fingers" in reason
