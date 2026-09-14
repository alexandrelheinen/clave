"""The recorded outcome and the placeholder reader.

Covers `AC-OUTCOME-01`, `AC-OUTCOME-03`, `AC-OUTCOME-04`, `AC-OUTCOME-05`, and
`AC-OUTCOME-06`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clave.validation.outcomes import (
    ObjectOutcome,
    OutcomeError,
    OutcomeSet,
    load_outcomes,
)


def _record(**overrides: object) -> ObjectOutcome:
    """Build a valid record, overriding named fields.

    Args:
        overrides: Fields to replace.

    Returns:
        The record.
    """
    fields: dict[str, object] = {
        "object_id": "obj-1",
        "true_class": "M-01",
        "predicted_class": "M-01",
        "picked": True,
        "routed_channel": "CH-PET",
        "seen_instance": True,
        "decision_latency_seconds": 0.05,
        "cycle_time_seconds": 0.9,
    }
    fields.update(overrides)
    return ObjectOutcome(**fields)  # type: ignore[arg-type]


def test_valid_records_construct_a_set() -> None:
    """AC-OUTCOME-01: a set of valid records is accepted and kept in order."""
    first = _record(object_id="obj-1")
    second = _record(object_id="obj-2")
    outcomes = OutcomeSet("fixture", [first, second])
    assert outcomes.outcomes == (first, second)
    assert len(outcomes) == 2


def test_set_carries_its_provenance() -> None:
    """AC-OUTCOME-06: the set names where its records came from."""
    assert OutcomeSet("synthetic fixture", []).provenance == "synthetic fixture"


def test_record_marks_whether_the_instance_was_seen() -> None:
    """AC-OUTCOME-04: seen and unseen instances are distinguishable."""
    assert _record(seen_instance=False).seen_instance is False


def test_unknown_true_class_is_refused_by_name() -> None:
    """AC-OUTCOME-03: a class outside the taxonomy is named, not counted."""
    with pytest.raises(OutcomeError, match="M-99"):
        OutcomeSet("fixture", [_record(true_class="M-99")])


def test_unknown_predicted_class_is_refused_by_name() -> None:
    """AC-OUTCOME-03: the rule applies to the predicted class too."""
    with pytest.raises(OutcomeError, match="M-42"):
        OutcomeSet("fixture", [_record(predicted_class="M-42")])


def test_absent_prediction_is_accepted() -> None:
    """AC-OUTCOME-01: no prediction is a state, not an error."""
    outcomes = OutcomeSet("fixture", [_record(predicted_class=None)])
    assert outcomes.outcomes[0].predicted_class is None


def test_unpicked_record_carrying_a_channel_is_refused() -> None:
    """AC-OUTCOME-01: an object that was not picked landed nowhere."""
    with pytest.raises(OutcomeError, match="obj-1"):
        OutcomeSet("fixture", [_record(picked=False, routed_channel="CH-PET")])


def test_picked_record_without_a_channel_is_refused() -> None:
    """AC-OUTCOME-01: an object that was picked landed somewhere."""
    with pytest.raises(OutcomeError, match="obj-1"):
        OutcomeSet("fixture", [_record(picked=True, routed_channel=None)])


def test_negative_duration_is_refused() -> None:
    """AC-OUTCOME-01: a negative duration is not a time anything took."""
    with pytest.raises(OutcomeError, match="decision_latency_seconds"):
        OutcomeSet("fixture", [_record(decision_latency_seconds=-0.01)])


def test_negative_cycle_time_is_refused() -> None:
    """AC-OUTCOME-01: the rule applies to cycle time too."""
    with pytest.raises(OutcomeError, match="cycle_time_seconds"):
        OutcomeSet("fixture", [_record(cycle_time_seconds=-1.0)])


def test_records_file_round_trips(tmp_path: Path) -> None:
    """AC-OUTCOME-05, AC-OUTCOME-06: a file reads back to an equal set."""
    path = tmp_path / "outcomes.json"
    path.write_text(
        json.dumps(
            {
                "provenance": "synthetic fixture, not a measurement",
                "outcomes": [
                    {
                        "object_id": "obj-1",
                        "true_class": "M-05",
                        "predicted_class": "M-06",
                        "picked": True,
                        "routed_channel": "CH-FERROUS",
                        "seen_instance": False,
                        "decision_latency_seconds": 0.4,
                        "cycle_time_seconds": 1.0,
                    }
                ],
            }
        )
    )
    loaded = load_outcomes(path)
    assert loaded.provenance == "synthetic fixture, not a measurement"
    assert loaded.outcomes == (
        ObjectOutcome(
            object_id="obj-1",
            true_class="M-05",
            predicted_class="M-06",
            picked=True,
            routed_channel="CH-FERROUS",
            seen_instance=False,
            decision_latency_seconds=0.4,
            cycle_time_seconds=1.0,
        ),
    )


def test_records_file_missing_a_field_fails_naming_it(tmp_path: Path) -> None:
    """AC-OUTCOME-05: an incomplete record names what it is missing."""
    path = tmp_path / "outcomes.json"
    path.write_text(
        json.dumps({"provenance": "fixture", "outcomes": [{"object_id": "obj-1"}]})
    )
    with pytest.raises(OutcomeError, match="true_class"):
        load_outcomes(path)


def test_records_file_without_provenance_is_refused(tmp_path: Path) -> None:
    """AC-OUTCOME-06: an unlabeled records file cannot be scored."""
    path = tmp_path / "outcomes.json"
    path.write_text(json.dumps({"outcomes": []}))
    with pytest.raises(OutcomeError, match="provenance"):
        load_outcomes(path)


def test_records_file_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    """AC-OUTCOME-05: a bare list carries no provenance, so it is refused."""
    path = tmp_path / "outcomes.json"
    path.write_text("[]")
    with pytest.raises(OutcomeError, match="does not contain an object"):
        load_outcomes(path)
