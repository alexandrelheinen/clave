"""Ordering the markers into a queue.

Etapa A holds the metric and the head. Anchors, the hysteresis that damps
them, and recomputing on change arrive with etapa B, so nothing here asserts
stability yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clave.control.selection import Selector
from clave.control.settings import ControlSettings, Point, SelectionSettings
from clave.tracker.markers import GraspMarker, color_for
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
NANOS_PER_SECOND = 1_000_000_000
BELT_SPEED = 0.30


def everywhere(_: Point) -> bool:
    """An arm trusted over the whole world, for tests about ordering."""
    return True


def selector(exit_weight: float = 1.0, admits: object = None) -> Selector:
    """A selector with the weight under test."""
    return Selector(settings(exit_weight), admits or everywhere)  # type: ignore[arg-type]


def settings(exit_weight: float = 1.0) -> SelectionSettings:
    """Selection settings with the weight under test."""
    shipped = ControlSettings.load(load(ROOT / "configs" / "runtime" / "control.yml"))
    return SelectionSettings(
        exit_weight=exit_weight, anchor_radius=shipped.selection.anchor_radius
    )


def marker(
    track_id: int,
    x: float,
    y: float = 0.0,
    leaves_in_seconds: float = 5.0,
    oriented: bool = True,
    reachable: bool = True,
) -> GraspMarker:
    """One marker, with only the fields selection reads set."""
    return GraspMarker(
        track_id=track_id,
        valid_until_nanos=int(leaves_in_seconds * NANOS_PER_SECOND),
        grasp=(x, y, 0.945),
        flange=(x, y, 1.035),
        pads=((x, y - 0.03, 0.945), (x, y + 0.03, 0.945)) if oriented else (),
        pad_size=(0.006, 0.02, 0.025),
        closing_axis=1.5708 if oriented else None,
        opening=0.06,
        oriented=oriented,
        reachable=reachable,
        extent=0.12,
        color=color_for(track_id),
    )


def test_an_empty_belt_produces_an_empty_queue() -> None:
    """An empty belt produces an empty queue."""
    queue = selector().update((), (0.0, 0.0, 1.2), BELT_SPEED, 0)
    assert queue.order == ()
    assert queue.head is None


def test_the_nearer_of_two_equally_urgent_markers_comes_first() -> None:
    """AC-MOVE-01: the nearer of two equally urgent markers comes first."""
    near = marker(1, x=0.10, leaves_in_seconds=5.0)
    far = marker(2, x=0.80, leaves_in_seconds=5.0)
    queue = selector().update((far, near), (0.0, 0.0, 1.035), BELT_SPEED, 0)
    assert queue.head is not None
    assert queue.head.track_id == 1


def test_the_more_urgent_of_two_equally_near_markers_comes_first() -> None:
    """AC-MOVE-01: the more urgent of two equally near markers comes first.

    Equally near in the sense that matters: both the same distance from the
    flange, one about to run out of belt.
    """
    leaving = marker(1, x=0.30, y=0.20, leaves_in_seconds=0.5)
    staying = marker(2, x=0.30, y=-0.20, leaves_in_seconds=6.0)
    queue = selector().update((staying, leaving), (0.30, 0.0, 1.035), BELT_SPEED, 0)
    assert queue.head is not None
    assert queue.head.track_id == 1


def test_urgency_can_outrank_distance_and_the_weight_says_by_how_much() -> None:
    """AC-MOVE-01: urgency can outrank distance, and the weight says by how much.

    The same pair orders one way at a weight that ignores the deadline and the
    other way at a weight that respects it, which is what makes the weight the
    knob rather than a decoration.
    """
    urgent_and_far = marker(1, x=0.90, leaves_in_seconds=0.2)
    idle_and_near = marker(2, x=0.10, leaves_in_seconds=8.0)
    pair = (urgent_and_far, idle_and_near)
    flange = (0.0, 0.0, 1.035)

    ignoring = selector(exit_weight=0.0).update(pair, flange, BELT_SPEED, 0)
    assert ignoring.head is not None
    assert ignoring.head.track_id == 2

    respecting = selector(exit_weight=2.0).update(pair, flange, BELT_SPEED, 0)
    assert respecting.head is not None
    assert respecting.head.track_id == 1


def test_the_order_is_built_from_where_the_flange_will_be() -> None:
    """AC-MOVE-02: the order is built from where the flange will be.

    Scoring every candidate from where the flange stands now would put the
    two near the origin first and the far one last. Scoring each next
    candidate from the previous one walks the chain instead, which is what
    nearest-neighbour construction means.
    """
    chain = (
        marker(1, x=0.20, leaves_in_seconds=9.0),
        marker(3, x=1.00, leaves_in_seconds=9.0),
        marker(2, x=0.60, leaves_in_seconds=9.0),
    )
    queue = selector(exit_weight=0.0).update(chain, (0.0, 0.0, 1.035), BELT_SPEED, 0)
    assert tuple(item.track_id for item in queue.order) == (1, 2, 3)


def test_a_marker_the_effector_cannot_open_to_is_left_out() -> None:
    """A marker the effector cannot open to is left out.

    An unreachable pose is not a candidate. Ordering it and then refusing it
    at the servo wastes a visit the arm could have spent on something it can
    take.
    """
    wide = marker(1, x=0.10, reachable=False)
    queue = selector().update((wide,), (0.0, 0.0, 1.035), BELT_SPEED, 0)
    assert queue.order == ()


def test_a_marker_already_past_the_window_is_left_out() -> None:
    """A marker already past the window is left out.

    Its pose expired, so there is no belt left to reach it over and no
    ordering that helps.
    """
    gone = marker(1, x=0.10, leaves_in_seconds=1.0)
    queue = selector().update(
        (gone,), (0.0, 0.0, 1.035), BELT_SPEED, at_nanos=2 * NANOS_PER_SECOND
    )
    assert queue.order == ()


def test_a_candidate_carries_what_the_task_layer_needs() -> None:
    """A candidate carries what the task layer needs.

    The flange pose and the closing axis travel with the candidate, so the
    task machine never has to go back to the marker list to find them.
    """
    queue = selector().update(
        (marker(4, x=0.25, y=0.10),), (0.0, 0.0, 1.035), BELT_SPEED, 0
    )
    head = queue.head
    assert head is not None
    assert head.track_id == 4
    assert head.flange == (0.25, 0.10, 1.035)
    assert head.closing_axis == pytest.approx(1.5708)
    assert head.distance_before_leaving == pytest.approx(5.0 * BELT_SPEED)


def test_an_unoriented_marker_carries_no_closing_axis() -> None:
    """AC-MOVE-08: an unoriented marker carries no closing axis."""
    queue = selector().update(
        (marker(1, x=0.25, oriented=False),), (0.0, 0.0, 1.035), BELT_SPEED, 0
    )
    assert queue.head is not None
    assert queue.head.closing_axis is None


def test_a_stopped_belt_leaves_nothing_urgent() -> None:
    """A stopped belt leaves nothing urgent.

    With no belt speed no object is running out of belt, so the deadline term
    vanishes and the ordering is by travel alone. This is the degenerate case
    the metric has to survive rather than divide by.
    """
    pair = (
        marker(1, x=0.90, leaves_in_seconds=0.2),
        marker(2, x=0.10, leaves_in_seconds=8.0),
    )
    queue = selector().update(pair, (0.0, 0.0, 1.035), 0.0, 0)
    assert queue.head is not None
    assert queue.head.track_id == 2


def test_a_pose_the_arm_is_not_trusted_over_is_left_out() -> None:
    """AC-MOVE-01: a pose the arm is not trusted over is left out.

    Different from a jaw that does not open wide enough, and conflating the
    two fed the controller markers a metre outside the annulus and faulted
    every visit. The region comes from the arm rather than from a constant
    here, so the two cannot drift.
    """
    upstream = marker(1, x=-1.00)
    near = marker(2, x=0.30)

    def inside_the_annulus(pose: Point) -> bool:
        return abs(pose[0]) <= 0.80

    queue = selector(admits=inside_the_annulus).update(
        (upstream, near), (0.0, 0.0, 1.035), BELT_SPEED, 0
    )
    assert tuple(item.track_id for item in queue.order) == (2,)
