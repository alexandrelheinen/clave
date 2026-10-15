"""The approach figures, without a simulator under them."""

from __future__ import annotations

import math

import pytest

from clave.sim.grasp_path import MISALIGN_METERS, GraspPathWatch, turn_radians


def _flat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


def _yaw(radians: float) -> tuple[float, float, float, float]:
    return (math.cos(radians / 2.0), 0.0, 0.0, math.sin(radians / 2.0))


def test_a_package_that_rides_the_belt_does_not_count_as_shoved() -> None:
    """AC-BEHAVE-07: belt travel is not a slide, and no turn is no turn."""
    watch = GraspPathWatch()
    speed = 0.25
    for step in range(20):
        time = step * 0.01
        along = -0.20 + speed * time
        watch.observe(
            track=3,
            time=time,
            pinch_xy=(along, 0.0),
            lowest_z=1.00,
            object_xy=(along, 0.0),
            object_top_z=0.955,
            object_quat=_flat(),
            belt_speed=speed,
            contacting=step >= 5,
            jaw_shut=step == 19,
        )
    assert watch.slides == [0.0]
    assert watch.turns == [0.0]


def test_a_shove_before_the_jaw_shuts_is_the_slide_and_the_turn() -> None:
    """AC-BEHAVE-07: motion relative to the belt, from the touch until the close."""
    watch = GraspPathWatch()
    speed = 0.25
    for step in range(11):
        time = step * 0.02
        # The belt would carry it 5 mm a tick. From the touch at step 2 the
        # package instead lags, 2 mm a tick, and yaws.
        lag = 0.0 if step < 2 else (step - 2) * 0.002
        yaw = 0.0 if step < 2 else (step - 2) * 0.02
        along = -0.10 + speed * time - lag
        watch.observe(
            track=4,
            time=time,
            pinch_xy=(along, 0.01),
            lowest_z=0.94,
            object_xy=(along, 0.0),
            object_top_z=0.955,
            object_quat=_yaw(yaw),
            belt_speed=speed,
            contacting=step >= 2,
            jaw_shut=step == 10,
        )
    assert watch.slides[0] == pytest.approx(8 * 0.002)
    assert watch.turns[0] == pytest.approx(8 * 0.02)
    # Ten millimetres off, and the jaw is below the top: that sample counts.
    assert watch.above[0] < 0.0


def test_a_miss_inside_five_millimetres_does_not_lower_the_height() -> None:
    """AC-BEHAVE-07: once the jaw is over the package, height is the descent."""
    watch = GraspPathWatch()
    watch.observe(
        track=1,
        time=0.0,
        pinch_xy=(0.0, 0.0),
        lowest_z=1.10,
        object_xy=(0.0, 0.020),
        object_top_z=0.955,
        object_quat=_flat(),
        belt_speed=0.25,
        contacting=False,
        jaw_shut=False,
    )
    watch.observe(
        track=1,
        time=0.01,
        pinch_xy=(0.0, 0.0),
        lowest_z=0.90,
        object_xy=(0.0, 0.004),
        object_top_z=0.955,
        object_quat=_flat(),
        belt_speed=0.25,
        contacting=True,
        jaw_shut=True,
    )
    assert watch.above[0] == pytest.approx(1.10 - 0.955)
    assert MISALIGN_METERS > 0.004
    assert watch.slides == [0.0]


def test_a_visit_that_never_shuts_the_jaw_has_no_slide() -> None:
    """A touch without a close is not the interval the slide is measured over."""
    watch = GraspPathWatch()
    watch.observe(
        track=2,
        time=0.0,
        pinch_xy=(0.0, 0.1),
        lowest_z=1.0,
        object_xy=(0.0, 0.0),
        object_top_z=0.95,
        object_quat=_flat(),
        belt_speed=0.25,
        contacting=True,
        jaw_shut=False,
    )
    watch.finish()
    assert watch.slides == []
    assert watch.above[0] == pytest.approx(1.0 - 0.95)


def test_a_gap_in_the_plan_does_not_split_one_visit() -> None:
    """AC-BEHAVE-07: one visit reports one worst height, gap or no gap.

    A tick with no plan used to seal the visit. The next tick opened
    another, so one descent was reported as a hundred heights and the
    worst of them was buried in the list.
    """
    watch = GraspPathWatch()
    for step, lowest in enumerate((1.05, 1.02, 0.99)):
        watch.observe(
            track=None if step == 1 else 5,
            time=step * 0.01,
            pinch_xy=(0.0, 0.02),
            lowest_z=lowest,
            object_xy=(0.0, 0.0),
            object_top_z=0.95,
            object_quat=_flat(),
            belt_speed=0.25,
            contacting=False,
            jaw_shut=False,
        )
    watch.finish()
    assert watch.above == pytest.approx([0.99 - 0.95])


def test_turn_radians_ignores_the_sign_of_a_quaternion() -> None:
    """The same rotation written with either sign is no turn."""
    assert turn_radians(_flat(), (1.0, 0.0, 0.0, 0.0)) == 0.0
    assert turn_radians(_flat(), (-1.0, 0.0, 0.0, 0.0)) == 0.0
