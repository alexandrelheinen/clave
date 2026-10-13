"""Where GTSAM may be imported, and what the repository must not contain."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "target", "third_party", ".guidelines", "__pycache__"}
GTSAM_IMPORT = re.compile(r"^\s*(import gtsam\b|from gtsam\b)")
GTBOOK_IMPORT = re.compile(r"^\s*(import gtbook\b|from gtbook\b)")
NOTEBOOK = re.compile(r"S2\d_sorter_.*\.ipynb$")
# Split so this file does not itself contain the chapter sentence.
CHAPTER_SENTENCE = "".join(
    ("For our simple trash sorting robot, ", "the only thing that matters")
)


def _files(root: Path) -> list[Path]:
    """Return the files under `root`, skipping checkouts and build trees."""
    found: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP for part in path.parts):
            continue
        if path.is_file():
            found.append(path)
    return found


def test_ac_sort_19_only_the_posterior_imports_gtsam() -> None:
    """The posterior module is the only place that imports GTSAM or gtbook."""
    offenders: list[str] = []
    for path in _files(ROOT / "src" / "clave"):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT / "src" / "clave").as_posix()
        for line in text.splitlines():
            if GTBOOK_IMPORT.search(line):
                offenders.append(f"{relative} imports gtbook")
            if GTSAM_IMPORT.search(line) and relative != "belief/posterior.py":
                offenders.append(f"{relative} imports gtsam")
    posterior = ROOT / "src" / "clave" / "belief" / "posterior.py"
    assert any(GTSAM_IMPORT.search(line) for line in posterior.read_text().splitlines())
    assert offenders == []


def test_ac_sort_20_the_repository_has_neither_the_notebooks_nor_the_sentence() -> None:
    """The chapter's notebooks and one of its sentences stay out of the tree."""
    notebooks = [
        str(path.relative_to(ROOT))
        for path in _files(ROOT)
        if NOTEBOOK.search(path.name)
    ]
    copies: list[str] = []
    for path in _files(ROOT):
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".rst"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        if CHAPTER_SENTENCE in text:
            copies.append(str(path.relative_to(ROOT)))
    assert notebooks == []
    assert copies == []
