# Ingesting a real corpus

> Extends the v0.6.0 data pipeline · Spec:
> [.kiro/specs/data-pipeline/](../../.kiro/specs/data-pipeline/), requirement 6

The ingestion path applies the taxonomy's corpus mappings, records ambiguity
where a label spans several classes, and keeps a label the mapping does not
recognize. Every one of those behaviors was proven against a fixture written to
match a table in a document, and none of them against a photograph. This step
fetches TrashNet, records its digest, reads it, and reports what it holds.

Every number below comes from running CLAVE's reader over the archive whose
sha256 `corpora/manifest.toml` records. None of them is copied from the corpus
paper, from the v0.1.0 review, or from the taxonomy document.

## What was fetched

TrashNet is the smallest corpus on the v0.1.0 shortlist and the only one under
a license that asks nothing of a downstream repository. It advanced there as a
`Baseline` rather than as training data, because it carries whole-image labels
and no localization, and nothing below changes that verdict.

| Property | Measured value |
| --- | --- |
| Artifact | `data/dataset-resized.zip` in [github.com/garythung/trashnet](https://github.com/garythung/trashnet) |
| Bytes | 42,834,870 |
| sha256 | `0bf472790f8b20e5c950d5b5012a9d38af0d3392efd65f8ce171334fc16b07c2` |
| License | MIT, read from the repository's `LICENSE` file on 2026-09-14 |
| Archive members | 2,540 |
| Members that are corpus imagery | 2,527 |
| Members excluded as packaging or editor metadata | 13 |
| Uncompressed bytes across all file members | 43,288,847 |
| Decoded frame shape | 384 by 512 by 3, for all 2,527 images |

The archive is never committed. It lands under `datasets/`, which
`.gitignore` already excludes, and the manifest entry points at the URL the
bytes came from so the digest and the source describe the same object.

### Thirteen members that are not images

A macOS zip carries its own bookkeeping, and this one carries thirteen members
that look like corpus content to a naive reader: ten directory entries, two
`.DS_Store` files, and one AppleDouble resource fork named
`__MACOSX/dataset-resized/cardboard/._cardboard9.jpg`. That last one is the
interesting case. It ends in `.jpg`, so a filter that reads suffixes would
ingest it as a 2,528th image, and it is 177 bytes of Finder metadata that no
decoder can open. Pillow refuses it with `UnidentifiedImageError`.

Four rules do the excluding, and each catches something different. A member
outside the declared root directory goes first, which is what removes the whole
`__MACOSX` subtree and the resource fork inside it. A member sitting directly
under the root rather than inside a label directory goes next, which removes
`dataset-resized/.DS_Store` and would also remove a stray image nobody had
filed under a label. A member carrying a dot-prefixed path component goes
third, catching a `.DS_Store` written inside a label directory. Last comes the
suffix, which removes the ten directory entries and anything else a label
directory might hold.

Only the third rule finds nothing in this archive, so a fixture exercises it
rather than the corpus.

The published figure of 2,527 images is recovered exactly, which is the check
that says the filter is right rather than merely plausible.

## How the archive is read

`clave.data.ingest.CorpusArchive` opens the zip and reads members in place. It
does not unpack, because unpacking would put a second copy on disk that no
digest describes, and a later reader would have no way to tell which copy it
was looking at. What a manifest verifies and what a training run consumes stay
the same bytes.

A corpus declares an `ArchiveLayout` saying which directory its imagery sits
under, which path component holds the label, and which suffixes are images.
Only TrashNet declares one. Writing a layout for ZeroWaste or TACO before
their bytes are in hand would be a guess dressed as configuration, and the
reader refuses an undeclared corpus rather than inferring a structure from
whatever it finds.

**Nothing in the module decodes an image.** `read_bytes` returns the encoded
member and `read_frame` hands those bytes to a decoder the caller supplies.
That keeps ingestion runnable wherever the standard library runs, which is also
where CLAVE's quality gate runs: the gate installs no image library, so the
default environment has no decoder and the reader still works. Training already
brings one, and it is the right place to choose it.

### A fetched image is not a simulated example

`CorpusExample` is a separate type from `clave.data.examples.Example`, and the
separation is deliberate. A simulated example carries a world position, a pixel
box, and exactly one taxonomy class per object, all of which the world knows by
construction. A TrashNet image carries a directory name. Its `plastic` label
names four classes at once and no region at all.

Reusing the simulated type would mean supplying a position that does not exist
and choosing one of four classes that the corpus never distinguished. The
existing type does have a way to say "no box", and it means "this object is not
visible in the frame", which is false of a TrashNet image where the object fills
the frame and is merely not localized. Overloading that field would corrupt the
one signal detection training depends on.

Both types carry `Origin`, so a held-out set of photographs stays separable
from synthetic data by filtering the same field either way.

## Measured composition

The archive holds 2,527 images under six labels, and the taxonomy maps every
one of them, so no image was read as unmapped.

| Corpus label | Images | Share | Uncompressed bytes |
| --- | --- | --- | --- |
| paper | 594 | 23.5% | 12,843,767 |
| glass | 501 | 19.8% | 6,675,059 |
| plastic | 482 | 19.1% | 6,945,927 |
| metal | 410 | 16.2% | 7,273,130 |
| cardboard | 403 | 15.9% | 7,605,360 |
| trash | 137 | 5.4% | 1,939,159 |

The rarest label holds 137 images against the most common label's 594, a ratio
of 4.3, so anything trained on this without reweighting learns the prior along
with the task.

Against CLAVE's eleven material classes, the same images look like this. The
second column counts every image whose label spans the class, so one `plastic`
image appears in four rows. The third counts only images whose label names that
class and no other.

| Class | Name | Images a label spans it | Images resolved to it |
| --- | --- | --- | --- |
| `M-01` | PET | 482 | 0 |
| `M-02` | HDPE | 482 | 0 |
| `M-03` | PP | 482 | 0 |
| `M-04` | Other plastic | 482 | 0 |
| `M-05` | Aluminum | 410 | 0 |
| `M-06` | Ferrous metal | 410 | 0 |
| `M-07` | Glass | 501 | 501 |
| `M-08` | Corrugated cardboard | 403 | 403 |
| `M-09` | Mixed paper | 594 | 594 |
| `M-10` | Beverage carton | 0 | 0 |
| `M-11` | Residue | 137 | 137 |

Four classes are supplied outright: glass, corrugated cardboard, mixed paper,
and residue, covering 1,635 images. Six classes are reachable only through a
label that spans several of them, covering 892 images. One class, `M-10`
beverage carton, receives nothing at all, because TrashNet has no label that
touches liquid packaging board.

## What the mapping loses

Of 2,527 images, **1,635 determine a taxonomy class and 892 do not**, which is
35.3 percent of the corpus. The undetermined images are exactly the two coarse
labels: `plastic` stands where `M-01` through `M-04` belong, and `metal` stands
where `M-05` and `M-06` belong.

Averaged over the whole corpus, a TrashNet label leaves 0.54 bits of the class
identity undetermined, assuming each class inside a label's span is equally
likely. Uniform is the assumption that maximizes that figure, so any better
prior over resins lowers it, and 0.54 bits is a ceiling rather than an
estimate.

**The default channel mapping recovers none of it.** `CH-FIBER` carries `M-08`,
`M-09` and `M-10` together, so a reader might expect the fiber merge to hide
part of the coarseness. It does not, because `cardboard` and `paper` each
already pin a class, and the two labels that do not pin one span classes routed
to four channels and to two channels respectively. Every image undetermined at
the class level is undetermined at the channel level too.

**No image carries a region.** All 2,527 labels are whole-image, so the
localization signal is zero, and the corpus supports a classifier sanity check
rather than the detector v0.4.0 shortlisted. This is what `C-CORPUS-3` failed
on in the v0.1.0 review, now confirmed by reading the artifact rather than its
description.

**Three images carry contradictory labels.** Digesting each member found 2,524
distinct images among 2,527, and every one of the three repeats crosses a label
boundary, appearing once under `glass` and once under another label.

| Same bytes at | And at |
| --- | --- |
| `glass/glass115.jpg` | `metal/metal91.jpg` |
| `glass/glass176.jpg` | `plastic/plastic152.jpg` |
| `glass/glass389.jpg` | `plastic/plastic332.jpg` |

Six images out of 2,527 is a rounding error in any accuracy figure. What they
do move is a split, because partitioning by image puts identical pixels with
opposing labels on both sides of the train and test boundary. Anything
splitting this corpus should partition by image digest.

What the mapping loses is a property of the annotation rather than of the
imagery. The taxonomy lists distinguishing properties that separate a
transparent PET bottle from an opaque HDPE jug by appearance, so a relabeling
pass might recover part of the resin split. Nothing here tested that, and the
corpus as published records none of it.

## Scene difference

Every image decodes to 384 by 512 pixels across three channels, and that is the
only property of the imagery this step measured. The v0.1.0 review describes the
capture conditions as one object on a plain background under controlled indoor
lighting; nothing here checked that description. CLAVE's target scene is a
moving belt carrying overlapping objects under a fixed camera, and fetching the
corpus narrows that gap by nothing at all.

## Acceptance criteria

`AC-INGEST-01` through `AC-INGEST-04` were met at v0.6.0 and still hold.
`AC-INGEST-05` said the pipeline shall state that no corpus has been fetched;
it is superseded by this document and keeps its identifier, since identifiers
are append-only.

| Id | Criterion | Guarded by |
| --- | --- | --- |
| `AC-INGEST-06` | When an operator supplies a fetched corpus archive, the reader shall read it into labeled examples without unpacking it | `test_a_fetched_archive_reads_into_labeled_examples` |
| `AC-INGEST-07` | The reader shall mark every example read from a fetched corpus with the real origin | `test_every_fetched_example_carries_the_real_origin` |
| `AC-INGEST-08` | When an archive member is packaging or editor metadata, the reader shall exclude it | `test_editor_metadata_is_not_read_as_imagery` |
| `AC-INGEST-09` | The reader shall report a fetched corpus's measured composition, naming both the classes it cannot supply and the classes it supplies only ambiguously | `test_composition_counts_every_class_a_label_may_be`, `test_composition_separates_resolved_classes_from_ambiguous_ones`, `test_composition_names_the_classes_a_corpus_cannot_supply` |
| `AC-INGEST-10` | If a corpus declares no archive layout, then the reader shall refuse it rather than infer one | `test_a_corpus_with_no_declared_layout_is_refused` |
| `AC-INGEST-11` | The reader shall decode a frame only through a caller-supplied decoder, so ingestion requires no image library | `test_a_frame_decodes_through_the_caller_supplied_decoder` |

Two further tests lock the measurements above against the real artifact:
`test_the_fetched_trashnet_archive_matches_its_manifest_digest` and
`test_the_fetched_trashnet_archive_holds_its_recorded_composition`. Both skip
when the archive is absent, which is the normal state of a clone and of CI.

## Reproducing this

```bash
mkdir -p datasets/corpora/trashnet
curl -L -o datasets/corpora/trashnet/dataset-resized.zip \
  https://raw.githubusercontent.com/garythung/trashnet/master/data/dataset-resized.zip
python -m clave.cli record-digest trashnet datasets/corpora/trashnet/dataset-resized.zip
```

The digest printed must equal the one in `corpora/manifest.toml`. With the
archive in place, the two skipped tests run and check every count in this
document. An operator keeping the archive somewhere else points
`CLAVE_TRASHNET_ARCHIVE` at it.

## What is still unproven

**Three of the four shortlisted corpora remain unfetched.** SpectralWaste,
TACO and ZeroWaste still carry no digest, and ZeroWaste is the one the v0.1.0
review ranks first. TrashNet was fetched because it is small, permissively
licensed, and already mapped, which makes it the cheapest way to prove the path
end to end while leaving it a poor choice to train on.

**Nothing was trained on it.** No accuracy, no loss curve, and no comparison
against synthetic data appears anywhere in this document. The only numbers are
counts, byte sizes, and digests.

**No held-out set of real imagery exists yet.** Building one means deciding what
to do about the 892 images whose class the label does not determine, and that
decision belongs with the one the taxonomy document already lists as open:
whether CLAVE trains a coarse head and refines it, trains only on the classes a
corpus separates, or relabels a subset.

**The end-to-end decode is exercised only where an image library is installed.**
The reader's own tests use a stub decoder and need nothing. Decoding all 2,527
images through Pillow was run once, by hand, to produce the frame shape recorded
above; the gate does not repeat it, because the gate installs no image library.

**The images were not inspected by eye.** No claim is made here about image
quality, framing, or whether any individual label is correct, beyond the three
byte-identical pairs the digests found.
