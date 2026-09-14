"""Ingesting a real corpus.

The mappings below mirror `docs/waste-taxonomy.md`, which is the authority. Most
corpus labels are coarser than the taxonomy, so a mapping loses information, and
the loss is recorded rather than resolved by picking a class.

TrashNet is fetched, digested in `corpora/manifest.toml`, and read through
:class:`CorpusArchive`. What the archive holds and what the mapping costs are
recorded in `docs/research/corpus-ingestion.md`. The other shortlisted corpora
are still unfetched, and declaring a layout for one before its bytes are in hand
would be a guess, so :data:`CORPUS_LAYOUTS` describes only what has been read.

A fetched image is a :class:`CorpusExample` rather than a
:class:`clave.data.examples.Example`. The two are different claims. A simulated
example carries object positions and pixel boxes the world knows by
construction, and one taxonomy class per object. A whole-image corpus label
carries none of that: TrashNet's `plastic` names four classes at once and no
region at all. Forcing it into the simulated type would mean inventing a
position and choosing one of the four, which is exactly the fabrication the
ambiguity record exists to prevent.

Nothing here decodes an image. Ingestion needs the label vocabulary and the
bytes; which library turns a JPEG into pixels is the caller's decision, and
keeping it out means this module runs wherever the standard library does.
"""

from __future__ import annotations

import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

import numpy as np
from numpy.typing import NDArray

from clave.data.examples import Origin
from clave.errors import ClaveError
from clave.taxonomy import MATERIAL_CLASSES

UNMAPPED = "unmapped"

FrameDecoder = Callable[[bytes], NDArray[np.uint8]]
"""Turns one encoded image into a height by width by three array of bytes."""


class CorpusError(ClaveError):
    """A fetched corpus cannot be read the way its declared layout describes."""


CORPUS_MAPPINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "zerowaste": {
        "cardboard": ("M-08", "M-09", "M-10"),
        "soft_plastic": ("M-04",),
        "rigid_plastic": ("M-01", "M-02", "M-03", "M-04"),
        "metal": ("M-05", "M-06"),
    },
    "trashnet": {
        "glass": ("M-07",),
        "paper": ("M-09",),
        "cardboard": ("M-08",),
        "plastic": ("M-01", "M-02", "M-03", "M-04"),
        "metal": ("M-05", "M-06"),
        "trash": ("M-11",),
    },
    "spectralwaste": {
        "film": ("M-04",),
        "basket": ("M-03", "M-04"),
        "video tape": ("M-11",),
        "filaments": ("M-11",),
        "trash bags": ("M-04",),
        "cardboard": ("M-08",),
    },
}


@dataclass(frozen=True)
class MappedLabel:
    """One corpus label resolved against the taxonomy.

    Attributes:
        corpus: Which corpus the label came from.
        source_label: The label as the corpus writes it.
        classes: Taxonomy classes it maps to, empty when unmapped.
        ambiguous: Whether it spans more than one class.
    """

    corpus: str
    source_label: str
    classes: tuple[str, ...]
    ambiguous: bool

    @property
    def mapped(self) -> bool:
        """Whether the label resolved to any taxonomy class."""
        return bool(self.classes)


def map_label(corpus: str, label: str) -> MappedLabel:
    """Resolve one corpus label against the taxonomy.

    A label spanning several classes is recorded as ambiguous rather than
    collapsed onto one. ZeroWaste's `rigid_plastic` covers four classes, and
    choosing one of them would invent a distinction the corpus never made.

    An unrecognized label is recorded as unmapped rather than discarded, so a
    corpus that gains a category does not silently lose examples.

    Args:
        corpus: Corpus identifier, as the manifest names it.
        label: The label as the corpus writes it.

    Returns:
        The resolved label.
    """
    classes = CORPUS_MAPPINGS.get(corpus, {}).get(label, ())
    return MappedLabel(
        corpus=corpus,
        source_label=label,
        classes=classes,
        ambiguous=len(classes) > 1,
    )


def coverage(corpus: str) -> dict[str, tuple[str, ...]]:
    """Return every mapping a corpus declares.

    Args:
        corpus: Corpus identifier.

    Returns:
        Label to taxonomy classes. Empty when the corpus is unknown, which is
        itself informative: it means no mapping has been recorded for it.
    """
    return dict(CORPUS_MAPPINGS.get(corpus, {}))


@dataclass(frozen=True)
class ArchiveLayout:
    """How one corpus archive encodes a label in each member path.

    Attributes:
        root: Top-level directory every image sits under. A member outside it
            is packaging rather than corpus content.
        label_depth: Which path component holds the label, counting the root as
            zero.
        suffixes: Lowercase file suffixes that hold imagery.
    """

    root: str
    label_depth: int
    suffixes: frozenset[str]


CORPUS_LAYOUTS: dict[str, ArchiveLayout] = {
    "trashnet": ArchiveLayout(
        root="dataset-resized", label_depth=1, suffixes=frozenset({".jpg"})
    ),
}


@dataclass(frozen=True)
class CorpusExample:
    """One image of a fetched corpus, with its label resolved.

    Attributes:
        corpus: Corpus identifier, as the manifest names it.
        member: Path of the image inside the archive.
        label: The corpus label resolved against the taxonomy, carrying the
            ambiguity when the label spans several classes.
        origin: Always real. It is carried rather than assumed so a held-out
            set of photographs can be excluded from training by filtering on
            the same field a simulated example carries.
    """

    corpus: str
    member: str
    label: MappedLabel
    origin: Origin = Origin.REAL

    @property
    def source_label(self) -> str:
        """The label as the corpus writes it."""
        return self.label.source_label


class CorpusArchive:
    """A fetched corpus archive, opened and read in place.

    The archive is read rather than unpacked, so the bytes an example comes
    from are the bytes the manifest digested. Unpacking would put a second,
    undigested copy on disk and leave no way to tell the two apart.

    Use it as a context manager, or call [CorpusArchive.close] when done.
    """

    def __init__(self, path: Path, corpus: str) -> None:
        """Open an archive and resolve every label it holds.

        Args:
            path: The fetched archive.
            corpus: Corpus identifier, as the manifest names it.

        Raises:
            CorpusError: If the corpus declares no layout, the file is not a
                readable archive, or the archive holds no imagery where the
                layout says imagery lives. An empty read is reported as a
                failure, because a corpus that reads as empty and a corpus that
                is empty are not the same thing.
        """
        layout = CORPUS_LAYOUTS.get(corpus)
        if layout is None:
            known = ", ".join(sorted(CORPUS_LAYOUTS)) or "none"
            raise CorpusError(
                f"corpus {corpus!r} declares no archive layout; declared: {known}"
            )
        try:
            self._archive = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise CorpusError(f"{path} is not a readable archive: {exc}") from exc
        self._corpus = corpus
        self._layout = layout
        self._examples = tuple(self._scan())
        if not self._examples:
            self._archive.close()
            raise CorpusError(
                f"{path} holds no {corpus!r} imagery under {layout.root!r}"
            )

    def __enter__(self) -> CorpusArchive:
        """Return the opened archive."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the archive."""
        self.close()

    def close(self) -> None:
        """Release the underlying file handle."""
        self._archive.close()

    @property
    def examples(self) -> tuple[CorpusExample, ...]:
        """Every labeled image the archive holds, in member order."""
        return self._examples

    def read_bytes(self, example: CorpusExample) -> bytes:
        """Return one image's encoded bytes, straight from the archive.

        Args:
            example: An example this archive produced.

        Returns:
            The member's bytes, still encoded.
        """
        return self._archive.read(example.member)

    def read_frame(
        self, example: CorpusExample, decode: FrameDecoder
    ) -> NDArray[np.uint8]:
        """Decode one image through a decoder the caller supplies.

        The decoder is a parameter rather than a dependency. CLAVE's training
        step already brings an image library, and ingestion has no business
        choosing a second one.

        Args:
            example: An example this archive produced.
            decode: Turns encoded bytes into pixels.

        Returns:
            Whatever the decoder returned.
        """
        return decode(self.read_bytes(example))

    def _scan(self) -> Iterator[CorpusExample]:
        """Yield one example per image member, in member order."""
        for member in sorted(self._archive.namelist()):
            label = self._label_of(member)
            if label is None:
                continue
            yield CorpusExample(
                corpus=self._corpus,
                member=member,
                label=map_label(self._corpus, label),
            )

    def _label_of(self, member: str) -> str | None:
        """Return the label a member path carries, or None when it carries none.

        A member is imagery when it sits under the declared root, at least one
        directory below the component holding the label, carries a declared
        suffix, and hides no dot-prefixed component. That last rule is what
        excludes the `__MACOSX` resource forks and `.DS_Store` entries a macOS
        zip carries: they look like files of the right name and are not images.
        """
        parts = member.split("/")
        if parts[0] != self._layout.root:
            return None
        if self._layout.label_depth >= len(parts) - 1:
            return None
        if any(part.startswith(".") for part in parts):
            return None
        if Path(member).suffix.lower() not in self._layout.suffixes:
            return None
        return parts[self._layout.label_depth]


@dataclass(frozen=True)
class CorpusComposition:
    """What a fetched corpus holds, measured against the taxonomy.

    Two class counts are reported because a coarse label is not evidence about
    one class. `class_counts` answers what an image might be, and
    `resolved_class_counts` answers what it is known to be. The gap between
    them is the information the mapping loses.

    Attributes:
        corpus: Corpus identifier.
        example_count: Images read.
        source_counts: Corpus label to image count, as the corpus writes it.
        class_counts: Taxonomy class to the number of images whose label spans
            it, so one ambiguous image is counted under every class it may be.
        resolved_class_counts: Taxonomy class to the number of images whose
            label names that class and no other.
        ambiguous_count: Images whose label spans more than one class.
        unmapped_count: Images whose label maps to no class at all.
        absent_classes: Taxonomy classes no label reaches, even ambiguously.
        unresolved_classes: Taxonomy classes reachable only through an
            ambiguous label, so the corpus supplies no image known to be one.
    """

    corpus: str
    example_count: int
    source_counts: dict[str, int]
    class_counts: dict[str, int]
    resolved_class_counts: dict[str, int]
    ambiguous_count: int
    unmapped_count: int
    absent_classes: tuple[str, ...]
    unresolved_classes: tuple[str, ...]


def compose_corpus(
    corpus: str, examples: tuple[CorpusExample, ...]
) -> CorpusComposition:
    """Measure what a fetched corpus supplies for each taxonomy class.

    Counts come from the examples read, never from the mapping table or from a
    published description of the corpus.

    Args:
        corpus: Corpus identifier.
        examples: The examples read from the archive.

    Returns:
        The measured composition, naming both the classes the corpus cannot
        supply and the classes it supplies only ambiguously.
    """
    sources: Counter[str] = Counter()
    spanned: Counter[str] = Counter()
    resolved: Counter[str] = Counter()
    ambiguous = 0
    unmapped = 0
    for example in examples:
        sources[example.source_label] += 1
        spanned.update(example.label.classes)
        if example.label.ambiguous:
            ambiguous += 1
        elif example.label.mapped:
            resolved[example.label.classes[0]] += 1
        else:
            unmapped += 1
    return CorpusComposition(
        corpus=corpus,
        example_count=len(examples),
        source_counts=dict(sorted(sources.items())),
        class_counts=dict(sorted(spanned.items())),
        resolved_class_counts=dict(sorted(resolved.items())),
        ambiguous_count=ambiguous,
        unmapped_count=unmapped,
        absent_classes=tuple(
            entry.id for entry in MATERIAL_CLASSES if spanned.get(entry.id, 0) == 0
        ),
        unresolved_classes=tuple(
            entry.id
            for entry in MATERIAL_CLASSES
            if spanned.get(entry.id, 0) > 0 and resolved.get(entry.id, 0) == 0
        ),
    )
