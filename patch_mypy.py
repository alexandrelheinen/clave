import re

with open("tests/control/task_test.py", "r") as f:
    content = f.read()

# Fix 1: `arm.plan` could be None according to mypy. We need to `assert arm.plan is not None` before accessing `arm.plan.target_yaw`.
new_test = """
def test_waiting_visit_measures_arrival_error_against_shifted_command() -> None:
    \"\"\"AC-MOVE-12: a clock wait measures arrival against the shifted command.\"\"\"
    arm = machine(
        profile=Profile.FULL_VISIT,
        grasp_yaw_tolerance=0.20,
        grasp_align_limit_seconds=1.0,
    )
    arm.step(queue_of(candidate(1, x=0.30)), PARK, 0.0)
    assert arm.plan is not None

    off = (arm.plan.target_yaw or 0.0) + 0.8
    at_seconds = 0.0
    waiting = None
    while at_seconds < 8.0:
        at_seconds += 0.01
        flown = arm.tick(at_seconds, PARK, tool_yaw=off)
        if flown is not None and flown.phase is Phase.HOLD:
            waiting = flown
            break

    assert waiting is not None

    for _ in range(10):
        at_seconds += 0.01
        arm.tick(at_seconds, PARK, tool_yaw=off)

    at_seconds += 0.01

    waited = arm._align_lag + arm._seat_lag
    shifted_pos = waiting.position.copy()
    shifted_pos[0] += BELT_SPEED * waited

    # Tick with the flange AT the shifted_pos and the right yaw
    flown = arm.tick(at_seconds, shifted_pos, tool_yaw=waiting.yaw)

    # Run out the plan to finish
    while at_seconds < 8.0:
        at_seconds += 0.01
        arm.tick(at_seconds, shifted_pos, tool_yaw=waiting.yaw)
        if arm.served:
            break

    assert len(arm.arrivals) == 1
    assert arm.arrivals[0] < 0.01
"""

pattern = re.compile(r"def test_waiting_visit_measures_arrival_error_against_shifted_command\(\) -> None:.*?(?=def test_a_far_object_is_not_an_attempt)", re.DOTALL)
new_content = pattern.sub(new_test.strip() + "\n\n\n", content)

with open("tests/control/task_test.py", "w") as f:
    f.write(new_content)
