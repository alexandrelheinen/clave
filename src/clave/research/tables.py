"""Enforce the research document table schemas.

v0.1.0 specified its registers to be mechanically checkable and deferred the
checker to this step, because writing one there would have settled the whole
Python toolchain as a side effect of a documentation step. This is that checker.

What it defends is narrow and worth defending: a candidate advancing with an
empty license cell. A reviewer misses that; a parser does not.

A document that does not exist is skipped rather than failed, so the gate stays
green on a clone that has not reached the step which produces it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from clave.errors import TableCheckError


@dataclass(frozen=True)
class TableSchema:
    """One table a document must contain, and the rules it must satisfy.

    Attributes:
        label: Human name used in error messages.
        header: The exact header cells, in order.
        verdict_column: Name of the column constrained to a closed vocabulary,
            or None when the table has no such column.
        vocabulary: The permitted values of that column.
    """

    label: str
    header: tuple[str, ...]
    verdict_column: str | None = None
    vocabulary: frozenset[str] = field(default_factory=frozenset)


_REVIEW_VERDICTS = frozenset(
    {"Advance", "Advance (provisional)", "Reject", "Unavailable", "Baseline"}
)

_CANDIDATE_OUTCOMES = frozenset({"Confirmed", "Contradicted", "Unmeasured"})

DOCUMENTS: dict[str, tuple[TableSchema, ...]] = {
    "docs/research/model-candidates.md": (
        TableSchema(
            label="measurements",
            header=(
                "Candidate",
                "Stage",
                "Parameters",
                "Median latency",
                "Spread",
                "Repetitions",
                "v0.1.2 estimate",
                "Outcome",
            ),
            verdict_column="Outcome",
            vocabulary=_CANDIDATE_OUTCOMES,
        ),
    ),
    "docs/research/training-infrastructure-review.md": (
        TableSchema(
            label="corpus register",
            header=(
                "Corpus",
                "License",
                "Size",
                "Annotation type",
                "Capture conditions",
                "Difference from CLAVE scene",
                "Constraint failed",
                "Verdict",
                "Source",
            ),
            verdict_column="Verdict",
            vocabulary=_REVIEW_VERDICTS,
        ),
        TableSchema(
            label="architecture register",
            header=(
                "Architecture",
                "Stage",
                "License",
                "Weights license",
                "Last release",
                "Training signal",
                "Estimated training cost",
                "Published result",
                "Measured on",
                "Constraint failed",
                "Verdict",
                "Source",
            ),
            verdict_column="Verdict",
            vocabulary=_REVIEW_VERDICTS,
        ),
        TableSchema(
            label="infrastructure register",
            header=(
                "Option",
                "Purpose",
                "License",
                "Runs on FRET MuJoCo unforked",
                "Reproducibility requirements",
                "Tradeoff against",
                "Constraint failed",
                "Verdict",
                "Source",
            ),
            verdict_column="Verdict",
            vocabulary=_REVIEW_VERDICTS,
        ),
    ),
}


def _cells(line: str) -> list[str]:
    """Split one markdown table row into stripped cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _rows_under(lines: list[str], start: int) -> list[list[str]]:
    """Collect the body rows following a header at ``start``."""
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(_cells(line))
    return rows


def check_document(path: Path, schemas: tuple[TableSchema, ...]) -> list[str]:
    """Check every declared table in one document.

    Args:
        path: The document to check.
        schemas: The tables it must contain.

    Returns:
        A list of human-readable problems. Empty means the document passes. An
        absent document returns an empty list, since skipping is the specified
        behavior rather than a pass.

    Raises:
        TableCheckError: Never raised directly; problems are returned so the
            caller can report all of them at once rather than the first.
    """
    if not path.is_file():
        return []
    lines = path.read_text().splitlines()
    problems: list[str] = []

    for schema in schemas:
        header_line = "| " + " | ".join(schema.header) + " |"
        if header_line not in lines:
            problems.append(
                f"{path}: {schema.label} header does not match the declared schema"
            )
            continue
        index = lines.index(header_line)
        rows = _rows_under(lines, index)
        if not rows:
            problems.append(f"{path}: {schema.label} has no rows")
            continue
        for row in rows:
            name = row[0] if row else "<empty row>"
            if len(row) != len(schema.header):
                problems.append(
                    f"{path}: {schema.label} row {name!r} has {len(row)} cells, "
                    f"expected {len(schema.header)}"
                )
                continue
            for column, cell in zip(schema.header, row, strict=True):
                if not cell:
                    problems.append(
                        f"{path}: {schema.label} row {name!r} has an empty "
                        f"{column!r} cell"
                    )
            if schema.verdict_column is not None:
                verdict = row[schema.header.index(schema.verdict_column)]
                if verdict not in schema.vocabulary:
                    problems.append(
                        f"{path}: {schema.label} row {name!r} has verdict "
                        f"{verdict!r}, which is outside the declared vocabulary"
                    )
    return problems


def check_all(root: Path) -> list[str]:
    """Check every declared document under a repository root.

    Args:
        root: Repository root.

    Returns:
        Every problem found, across all declared documents.
    """
    problems: list[str] = []
    for relative, schemas in DOCUMENTS.items():
        problems.extend(check_document(root / relative, schemas))
    return problems


def raise_for_problems(problems: list[str]) -> None:
    """Raise when any problem was found.

    Args:
        problems: Problems returned by a check.

    Raises:
        TableCheckError: If the list is not empty, carrying every problem.
    """
    if problems:
        raise TableCheckError("\n".join(problems))
