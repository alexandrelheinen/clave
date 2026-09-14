"""Tests for reading a fetched corpus archive into labeled examples."""

import os
import zipfile
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from clave.corpus.artifacts import digest_of
from clave.corpus.manifest import Manifest
from clave.data.examples import Origin
from clave.data.ingest import (
    CORPUS_LAYOUTS,
    CorpusArchive,
    CorpusError,
    compose_corpus,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRASHNET = ROOT / "datasets" / "corpora" / "trashnet" / "dataset-resized.zip"

FIXTURE_MEMBERS = {
    "dataset-resized/": b"",
    "dataset-resized/.DS_Store": b"editor metadata",
    "dataset-resized/glass/": b"",
    "dataset-resized/glass/.DS_Store": b"editor metadata inside a label",
    "dataset-resized/glass/notes.txt": b"a label directory may hold prose",
    "dataset-resized/glass/glass1.jpg": b"glass pixels",
    "dataset-resized/glass/glass2.jpg": b"more glass pixels",
    "dataset-resized/plastic/plastic1.jpg": b"plastic pixels",
    "dataset-resized/unicorn/unicorn1.jpg": b"unmapped pixels",
    "dataset-resized/stray.jpg": b"outside any label directory",
    "__MACOSX/dataset-resized/glass/._glass1.jpg": b"resource fork",
}


def trashnet_archive() -> Path | None:
    """Return the fetched TrashNet archive, or None when it is absent.

    An operator fetches the corpus; the gate does not. Everything below that
    needs the real bytes asks here and skips when the answer is None.
    """
    override = os.environ.get("CLAVE_TRASHNET_ARCHIVE")
    path = Path(override) if override else DEFAULT_TRASHNET
    return path if path.is_file() else None


def build_archive(path: Path, members: dict[str, bytes]) -> Path:
    """Write a zip holding the given members, and return its path."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path


@pytest.fixture
def fixture_archive(tmp_path: Path) -> Path:
    """A small archive laid out the way TrashNet lays out its own."""
    return build_archive(tmp_path / "trashnet.zip", FIXTURE_MEMBERS)


def test_a_fetched_archive_reads_into_labeled_examples(fixture_archive: Path) -> None:
    """AC-INGEST-06: imagery is read from the archive without extracting it."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        members = [example.member for example in archive.examples]
    assert members == [
        "dataset-resized/glass/glass1.jpg",
        "dataset-resized/glass/glass2.jpg",
        "dataset-resized/plastic/plastic1.jpg",
        "dataset-resized/unicorn/unicorn1.jpg",
    ]


def test_every_fetched_example_carries_the_real_origin(fixture_archive: Path) -> None:
    """AC-INGEST-07 and AC-INGEST-04: real examples stay separable."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        origins = {example.origin for example in archive.examples}
    assert origins == {Origin.REAL}


def test_a_label_spanning_several_classes_is_read_as_ambiguous(
    fixture_archive: Path,
) -> None:
    """AC-INGEST-02: TrashNet's plastic covers four classes."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        plastic = next(
            example for example in archive.examples if example.source_label == "plastic"
        )
    assert plastic.label.ambiguous
    assert plastic.label.classes == ("M-01", "M-02", "M-03", "M-04")


def test_a_label_outside_the_mapping_is_read_as_unmapped(
    fixture_archive: Path,
) -> None:
    """AC-INGEST-03: an unrecognized directory does not lose its images."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        unicorn = next(
            example for example in archive.examples if example.source_label == "unicorn"
        )
    assert not unicorn.label.mapped
    assert unicorn.label.classes == ()


def test_editor_metadata_is_not_read_as_imagery(fixture_archive: Path) -> None:
    """AC-INGEST-08: AppleDouble forks and .DS_Store files are not images.

    Three separate rules exclude them, so the fixture carries one member for
    each: outside the declared root, directly under the root, and hidden inside
    a label directory.
    """
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        members = [example.member for example in archive.examples]
    assert not [member for member in members if "__MACOSX" in member]
    assert not [member for member in members if "/." in member]
    assert "dataset-resized/glass/.DS_Store" not in members


def test_a_file_outside_a_label_directory_is_not_read(
    fixture_archive: Path,
) -> None:
    """A member at the archive root carries no label, so it is not an example.

    Nor does a directory entry or a file whose suffix the layout does not
    declare, both of which sit in the right place and hold no imagery.
    """
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        members = [example.member for example in archive.examples]
    assert "dataset-resized/stray.jpg" not in members
    assert "dataset-resized/glass/" not in members
    assert "dataset-resized/glass/notes.txt" not in members


def test_a_corpus_with_no_declared_layout_is_refused(fixture_archive: Path) -> None:
    """AC-INGEST-10: guessing a layout would invent a label vocabulary."""
    with pytest.raises(CorpusError, match="taco"):
        CorpusArchive(fixture_archive, "taco")


def test_an_archive_holding_no_imagery_is_refused(tmp_path: Path) -> None:
    """AC-INGEST-10: an empty read is a failure, not an empty corpus."""
    empty = build_archive(tmp_path / "empty.zip", {"readme.txt": b"nothing here"})
    with pytest.raises(CorpusError, match="dataset-resized"):
        CorpusArchive(empty, "trashnet")


def test_a_file_that_is_not_an_archive_is_refused(tmp_path: Path) -> None:
    """A truncated download must fail loudly rather than read as empty."""
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip at all")
    with pytest.raises(CorpusError, match="readable archive"):
        CorpusArchive(broken, "trashnet")


def test_a_frame_decodes_through_the_caller_supplied_decoder(
    fixture_archive: Path,
) -> None:
    """AC-INGEST-11: ingestion needs no image library of its own."""
    seen: list[bytes] = []

    def decode(payload: bytes) -> NDArray[np.uint8]:
        seen.append(payload)
        return np.zeros((2, 2, 3), dtype=np.uint8)

    with CorpusArchive(fixture_archive, "trashnet") as archive:
        first = archive.examples[0]
        assert archive.read_bytes(first) == b"glass pixels"
        frame = archive.read_frame(first, decode)
    assert seen == [b"glass pixels"]
    assert frame.shape == (2, 2, 3)


def test_composition_counts_every_class_a_label_may_be(
    fixture_archive: Path,
) -> None:
    """AC-INGEST-09: an ambiguous label counts toward each class it spans."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        measured = compose_corpus("trashnet", archive.examples)
    assert measured.example_count == 4
    assert measured.source_counts == {"glass": 2, "plastic": 1, "unicorn": 1}
    assert measured.class_counts["M-07"] == 2
    assert measured.class_counts["M-01"] == 1
    assert measured.class_counts["M-04"] == 1
    assert measured.ambiguous_count == 1
    assert measured.unmapped_count == 1


def test_composition_separates_resolved_classes_from_ambiguous_ones(
    fixture_archive: Path,
) -> None:
    """AC-INGEST-09: only a label pinning one class resolves that class."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        measured = compose_corpus("trashnet", archive.examples)
    assert measured.resolved_class_counts == {"M-07": 2}
    assert measured.unresolved_classes == ("M-01", "M-02", "M-03", "M-04")


def test_composition_names_the_classes_a_corpus_cannot_supply(
    fixture_archive: Path,
) -> None:
    """AC-INGEST-09: an absent class is an absence in the data."""
    with CorpusArchive(fixture_archive, "trashnet") as archive:
        measured = compose_corpus("trashnet", archive.examples)
    assert "M-10" in measured.absent_classes
    assert "M-07" not in measured.absent_classes


def test_trashnet_declares_an_archive_layout() -> None:
    """The fetched corpus is the one whose layout the module describes."""
    assert CORPUS_LAYOUTS["trashnet"].root == "dataset-resized"


@pytest.mark.skipif(
    trashnet_archive() is None, reason="TrashNet has not been fetched locally"
)
def test_the_fetched_trashnet_archive_matches_its_manifest_digest() -> None:
    """The committed digest describes the bytes this machine holds."""
    path = trashnet_archive()
    assert path is not None
    recorded = Manifest.load(ROOT / "corpora" / "manifest.toml")["trashnet"]
    assert digest_of(path) == recorded.sha256


@pytest.mark.skipif(
    trashnet_archive() is None, reason="TrashNet has not been fetched locally"
)
def test_the_fetched_trashnet_archive_holds_its_recorded_composition() -> None:
    """The counts in docs/research/corpus-ingestion.md come from these bytes."""
    path = trashnet_archive()
    assert path is not None
    with CorpusArchive(path, "trashnet") as archive:
        measured = compose_corpus("trashnet", archive.examples)
    assert measured.example_count == 2527
    assert measured.source_counts == {
        "cardboard": 403,
        "glass": 501,
        "metal": 410,
        "paper": 594,
        "plastic": 482,
        "trash": 137,
    }
    assert measured.unmapped_count == 0
    assert measured.absent_classes == ("M-10",)
    assert measured.unresolved_classes == (
        "M-01",
        "M-02",
        "M-03",
        "M-04",
        "M-05",
        "M-06",
    )
