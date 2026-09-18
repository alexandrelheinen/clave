"""Where the reachable window ends, and why half its length is not that.



`clave.runtime.loop` and `clave.data.recorder` both computed the exit as
`window_length / 2.0`. That is only the exit coordinate because the arm happens
to stand at the origin, so the two agree today and would stop agreeing the
moment anybody moved it. The exit is a measured edge, and it is read as one.
"""

from __future__ import annotations

import pytest

from clave.world import arm as armmod
from clave.world import belt
from clave.world.scene import BeltGeometry, SceneLayout


def layout(arm_x: float) -> SceneLayout:
    """A layout for reachability arithmetic, needing no physics.

    The reach bounds come from the arm model rather than from numbers a test
    picks, which is what keeps this describing the manipulator the world has.
    """
    return SceneLayout(
        belt=BeltGeometry(length=3.0, width=1.0, surface_height=0.90, speed=0.31),
        arm_base=(arm_x, -0.70, 0.90),
        reach_min=armmod.REACH_MIN_METERS,
        reach_max=armmod.REACH_MAX_METERS,
        tool_above_base=(-0.05, 0.45),
        pedestal=(0.30, 0.30),
        channels=("CH-PET",),
        objects=(),
        pool_size=0,
        timestep=0.002,
    )


def test_the_window_exit_is_the_measured_downstream_edge() -> None:
    """The exit is swept, never derived from the length."""
    plan = layout(arm_x=0.0)
    assert belt.window_exit(plan) == pytest.approx(
        belt.reach_report(plan).window_edges[1]
    )


def test_the_shipped_line_puts_the_exit_at_the_swept_edge() -> None:
    """The shipped line puts the exit at the swept edge.

    docs/measurements.md records the window as 2.071 m running -1.034 m to
    +1.034 m. Half the length is 1.035 m, which is the sweep step away from the
    edge and is not the same quantity.
    """
    plan = layout(arm_x=0.0)
    assert belt.window_exit(plan) == pytest.approx(1.034, abs=1e-3)


def test_half_the_window_length_stops_being_the_exit_when_the_arm_moves() -> None:
    """Half the window length stops being the exit when the arm moves.

    This is the latent defect the criterion exists to close. With the arm
    downstream of the belt centre the window shifts with it, so half the length
    names a coordinate the arm cannot reach while the swept edge still does.
    """
    plan = layout(arm_x=0.40)
    report = belt.reach_report(plan)
    exit_coordinate = belt.window_exit(plan)

    assert exit_coordinate == pytest.approx(report.window_edges[1])
    assert exit_coordinate != pytest.approx(report.window_length / 2.0, abs=1e-3)
    # The shifted window still opens and closes downstream of where it did.
    assert report.window_edges[0] > layout(arm_x=0.0).belt.length / -2.0


def test_a_belt_that_never_enters_reach_reports_no_exit() -> None:
    """A window of zero length has no edge to name."""
    plan = layout(arm_x=40.0)
    assert belt.reach_report(plan).window_length == 0.0
    assert belt.window_exit(plan) is None
