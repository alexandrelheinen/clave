"""The debug narrative: one sentence per decision, and a watch that edges.

AC-STORY-01 through AC-STORY-09. The sentences are what an operator reads
while a run is going wrong. They are specified in
docs/requirements/simulation-narrative.md.
"""

from __future__ import annotations

import logging
import math

import pytest

from clave.control.story import (
    ACCELERATION_WATCH,
    PINCH_MISS_METERS,
    TRACKING_WATCH,
    AnomalyWatch,
    StoryLog,
    material_phrase,
)


def _lines() -> tuple[StoryLog, list[str]]:
    """A log that keeps every sentence, and the list it keeps them in."""
    kept: list[str] = []
    return StoryLog(sink=kept.append), kept


def test_the_narrative_is_silent_above_debug(caplog: pytest.LogCaptureFixture) -> None:
    """AC-STORY-01: above DEBUG the narrative emits nothing."""
    caplog.set_level(logging.INFO, logger="clave.control.story")
    StoryLog().tell(1.25, "the queue is empty", "not start a visit", "pending")
    assert caplog.records == []


def test_a_debug_line_is_the_sentence(caplog: pytest.LogCaptureFixture) -> None:
    """AC-STORY-02: time, because, I will, and an outcome token."""
    caplog.set_level(logging.DEBUG, logger="clave.control.story")
    story = StoryLog()
    story.note(12, "M-01", "CH-PET")
    story.tell(
        1.25,
        "the queue offered this object",
        f"fly a visit to fetch {story.refer(12)}",
        "pending",
        channel="CH-PET",
    )
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
    message = caplog.records[0].getMessage()
    assert message == (
        "t=   1.250s because the queue offered this object, "
        "I will fly a visit to fetch object 12 (PET, M-01), chute CH-PET: pending"
    )


def test_an_outcome_outside_the_three_tokens_is_refused() -> None:
    """AC-STORY-02: the outcome token is exactly success, fail, or pending."""
    story, _ = _lines()
    with pytest.raises(ValueError, match="outcome"):
        story.tell(0.0, "a cause", "do something", "maybe")


def test_material_is_the_taxonomy_name_or_unknown() -> None:
    """AC-STORY-08: a known class is its name and id; an absent one is unknown."""
    assert material_phrase("M-01") == "PET, M-01"
    assert material_phrase("") == "unknown material"
    assert material_phrase("M-99") == "M-99"
    story, _ = _lines()
    assert story.refer(4) == "object 4 (unknown material)"
    story.note(4, "M-07", "CH-GLASS")
    assert story.refer(4) == "object 4 (Glass, M-07)"
    assert story.channel_of(4) == "CH-GLASS"


def test_a_queue_rebuild_says_whether_the_head_changed() -> None:
    """AC-STORY-09: a rebuild names its trigger and what happened to the head."""
    story, lines = _lines()
    story.note(7, "M-02", "CH-HDPE")
    story.note(8, "M-03", "CH-PP")
    story.queue(0.5, frozenset({"appeared"}), 7, None, False)
    story.queue(1.0, frozenset({"anchor", "retired"}), 7, 7, True)
    story.queue(1.5, frozenset({"appeared"}), 8, 7, True)
    story.queue(2.0, frozenset(), None, 8, False)
    assert "serve object 7 (HDPE, M-02) next" in lines[0]
    assert "appeared" in lines[0]
    assert lines[0].endswith(": pending")
    assert "the head did not change" in lines[1]
    assert "anchor, retired" in lines[1]
    assert "while object 7 (HDPE, M-02) was still waiting" in lines[2]
    assert "leave it and serve object 8 (PP, M-03) instead" in lines[2]
    assert "it has no head" in lines[3]
    assert "I will not start a visit" in lines[3]


def test_a_close_past_the_watch_is_remembered_as_a_miss() -> None:
    """AC-STORY-04: a wide gap is a fail, and a later delivery can see it."""
    story, lines = _lines()
    story.note(3, "M-05", "CH-ALU")
    story.grasp_reading(1.0, 3, PINCH_MISS_METERS + 0.010)
    assert story.missed_the_grasp(3)
    assert lines[0].endswith(": fail")
    assert "past the 40 mm watch" in lines[0]
    story.grasp_reading(2.0, 3, math.inf)
    assert "nothing is in reach of the pinch" in lines[1]
    story.grasp_reading(3.0, 9, 0.008)
    assert not story.missed_the_grasp(9)
    assert lines[2].endswith(": pending")
    assert "8 mm from the pinch" in lines[2]


def test_the_lift_is_the_grasp_verdict() -> None:
    """AC-STORY-04: the visit ends success only when the caller says it held."""
    story, lines = _lines()
    story.note(3, "M-05", "CH-ALU")
    story.visit_ended(4.0, 3, 0.024, held=True)
    story.visit_ended(5.0, 3, 0.001, held=False)
    assert "rose 24 mm" in lines[0]
    assert lines[0].endswith(": success")
    assert lines[1].endswith(": fail")


def test_a_place_names_the_chute_and_a_misroute_names_both() -> None:
    """AC-STORY-05: the material's own chute is success; any other is fail."""
    story, lines = _lines()
    story.placed(6.0, "object_3", "M-01", "CH-PET", "CH-PET", serial=12)
    story.placed(6.5, "object_4", "M-01", "CH-ALU", "CH-PET", serial=13)
    assert "body object_3, object 12 (PET, M-01)" in lines[0]
    assert "count a place in chute CH-PET" in lines[0]
    assert lines[0].endswith(", chute CH-PET: success")
    assert "crossed chute CH-ALU, which is not CH-PET" in lines[1]
    assert lines[1].endswith(": fail")


def test_the_watch_reports_each_condition_once_until_it_clears() -> None:
    """AC-STORY-06: contact, acceleration, lag, and a refusal are edge-triggered."""
    story, lines = _lines()
    story.note(2, "M-07", "CH-GLASS")
    watch = AnomalyWatch(story)

    def see(
        at: float,
        *,
        contact: bool = False,
        clearance: float = 0.020,
        vertical_acceleration: float = 0.0,
        tracking_error: float | None = 0.001,
        refusal: str | None = None,
    ) -> None:
        watch.observe(
            at,
            contact=contact,
            clearance=clearance,
            vertical_acceleration=vertical_acceleration,
            tracking_error=tracking_error,
            refusal=refusal,
            track_id=2,
        )

    see(0.0)
    see(0.002, contact=True, clearance=-0.0014)
    see(0.004, contact=True, clearance=-0.0014)
    see(0.006)
    see(0.008, contact=True, clearance=-0.0005)
    collisions = [line for line in lines if "report a collision" in line]
    assert len(collisions) == 2
    assert "clearance -1.4 mm" in collisions[0]
    assert collisions[0].endswith(": fail")
    assert "object 2 (Glass, M-07)" in collisions[0]

    see(0.010, vertical_acceleration=ACCELERATION_WATCH + 1)
    see(0.012, vertical_acceleration=ACCELERATION_WATCH + 5)
    see(0.014, vertical_acceleration=ACCELERATION_WATCH / 2 - 1.0)
    see(0.016, vertical_acceleration=ACCELERATION_WATCH + 1)
    spikes = [line for line in lines if "acceleration spike" in line]
    assert len(spikes) == 2
    assert "m/s^2" in spikes[0]

    see(0.020, tracking_error=TRACKING_WATCH + 0.010)
    see(0.022, tracking_error=TRACKING_WATCH + 0.020)
    see(0.024, tracking_error=TRACKING_WATCH / 2 - 0.001)
    see(0.026, tracking_error=TRACKING_WATCH + 0.010)
    lags = [line for line in lines if "from the pose it was commanded" in line]
    assert len(lags) == 2

    see(0.030, refusal="outside the annulus")
    see(0.032, refusal="outside the annulus")
    see(0.034)
    see(0.036, refusal="joint limit")
    refusals = [line for line in lines if "the servo refused" in line]
    assert len(refusals) == 2
    assert "outside the annulus" in refusals[0]
    assert "joint limit" in refusals[1]
    assert all("report a loss of control" in line for line in (*lags, *refusals))
