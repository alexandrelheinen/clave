from clave.control.settings import Phase, Profile

from .task_test import PARK, candidate, machine, queue_of


def test_jaw_seat_abandon() -> None:
    """If the jaws never seat, abandon the pick."""
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
    finished: str | None = "not none"
    for _ in range(80):  # Trigger dwell expiry
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


def test_jaw_stopped_on_object_seats_after_dwell() -> None:
    """If the jaws travel enough but do not reach seat fraction, seat after dwell."""
    arm = machine(
        profile=Profile.FULL_VISIT,
        grasp_seat_fraction=0.70,
        dwell_seconds=0.15,
        grasp_contact_fraction=0.25,
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

    # Keep passing jaw_travel=0.5 (above contact, below seat) past dwell expiry
    finished: str | None = "not none"
    for _ in range(20):
        at_seconds += 0.01
        flown = arm.tick(at_seconds, PARK, jaw_travel=0.5, seconds_left=30.0)
        if flown is None:
            finished = None
            break

    # Tick should return HOLD/lift pose, not None
    assert finished == "not none"
    assert flown is not None
    assert flown.phase in (Phase.HOLD, Phase.RETREAT)
    # The pick is not abandoned
    assert len(arm.abandoned) == 0
