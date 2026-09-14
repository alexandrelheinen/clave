"""Ingesting a real corpus.

The mappings below mirror `docs/waste-taxonomy.md`, which is the authority. Most
corpus labels are coarser than the taxonomy, so a mapping loses information, and
the loss is recorded rather than resolved by picking a class.

No corpus has been fetched. This path is exercised against a fixture, and its
first real test comes when an operator downloads one and records its digest
through the manifest.
"""

from __future__ import annotations

from dataclasses import dataclass

UNMAPPED = "unmapped"

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
