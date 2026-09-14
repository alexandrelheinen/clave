"""Tests for the research document table checker."""

from pathlib import Path

import pytest

from clave.errors import TableCheckError
from clave.research.tables import (
    DOCUMENTS,
    TableSchema,
    check_all,
    check_document,
    raise_for_problems,
)

SCHEMA = TableSchema(
    label="demo",
    header=("Name", "License", "Verdict"),
    verdict_column="Verdict",
    vocabulary=frozenset({"Advance", "Reject"}),
)

GOOD = """# Demo

| Name | License | Verdict |
| --- | --- | --- |
| alpha | MIT | Advance |
| beta | AGPL-3.0 | Reject |
"""


def write(tmp_path: Path, body: str) -> Path:
    """Write a document body and return its path."""
    path = tmp_path / "doc.md"
    path.write_text(body)
    return path


def test_a_conforming_document_reports_no_problems(tmp_path: Path) -> None:
    """AC-CHECK-01: the happy path is silent."""
    assert check_document(write(tmp_path, GOOD), (SCHEMA,)) == []


def test_header_drift_is_reported_naming_document_and_table(tmp_path: Path) -> None:
    """AC-CHECK-01: a renamed column fails, and says which table."""
    drifted = GOOD.replace(
        "| Name | License | Verdict |", "| Name | Licence | Verdict |"
    )
    problems = check_document(write(tmp_path, drifted), (SCHEMA,))
    assert len(problems) == 1
    assert "demo" in problems[0]
    assert "doc.md" in problems[0]


def test_empty_cell_is_reported_naming_row_and_column(tmp_path: Path) -> None:
    """AC-CHECK-02: this is the defect the checker exists for."""
    holed = GOOD.replace("| alpha | MIT | Advance |", "| alpha |  | Advance |")
    problems = check_document(write(tmp_path, holed), (SCHEMA,))
    assert len(problems) == 1
    assert "alpha" in problems[0]
    assert "License" in problems[0]


def test_verdict_outside_the_vocabulary_is_reported(tmp_path: Path) -> None:
    """AC-CHECK-03: the vocabulary is closed."""
    invented = GOOD.replace("Advance |", "Probably |")
    problems = check_document(write(tmp_path, invented), (SCHEMA,))
    assert any("Probably" in problem for problem in problems)


def test_wrong_cell_count_is_reported(tmp_path: Path) -> None:
    """AC-CHECK-02: a dropped separator is a structural failure."""
    short = GOOD.replace("| beta | AGPL-3.0 | Reject |", "| beta | AGPL-3.0 |")
    problems = check_document(write(tmp_path, short), (SCHEMA,))
    assert any("expected 3" in problem for problem in problems)


def test_table_with_no_rows_is_reported(tmp_path: Path) -> None:
    """A declared table that is present but empty is a failure, not a pass."""
    empty = "# Demo\n\n| Name | License | Verdict |\n| --- | --- | --- |\n"
    assert check_document(write(tmp_path, empty), (SCHEMA,)) == [
        f"{tmp_path / 'doc.md'}: demo has no rows"
    ]


def test_absent_document_is_skipped_not_failed(tmp_path: Path) -> None:
    """AC-CHECK-04: the gate stays green before the document exists."""
    assert check_document(tmp_path / "nothing.md", (SCHEMA,)) == []


def test_raise_for_problems_is_silent_when_there_are_none() -> None:
    """The caller can raise unconditionally."""
    raise_for_problems([])


def test_raise_for_problems_carries_every_problem() -> None:
    """A reviewer should see all failures at once, not the first."""
    with pytest.raises(TableCheckError, match="second"):
        raise_for_problems(["first", "second"])


def test_the_delivered_v0_1_0_review_passes_its_own_schema() -> None:
    """The checker is worthless if it only passes against fixtures."""
    root = Path(__file__).resolve().parents[2]
    assert check_all(root) == []
    assert "docs/research/training-infrastructure-review.md" in DOCUMENTS
