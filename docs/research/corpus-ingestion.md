# Ingesting a real corpus

> Extends the v0.6.0 data pipeline · Spec:
> [.kiro/specs/data-pipeline/](../../.kiro/specs/data-pipeline/), requirement 6
> · Corpora fetched at v0.6.3 and v0.9.1

The ingestion path applies the taxonomy's corpus mappings, records ambiguity
where a label spans several classes, and keeps a label the mapping does not
recognize. Every one of those behaviors was first proven against a fixture
written to match a table in a document. Two of the four shortlisted corpora
have since been fetched, digested, read and measured: TrashNet, which is the
cheapest, and ZeroWaste, which the v0.1.0 review ranks first.

Every number below comes from running CLAVE's reader over the archive whose
sha256 `corpora/manifest.toml` records. None of them is copied from a corpus
paper, from the v0.1.0 review, or from the taxonomy document.

## TrashNet, fetched at v0.6.3

The smallest corpus on the shortlist and the only one under a license that
asks nothing of a downstream repository. It advanced at v0.1.0 as a
`Baseline` rather than as training data, because it carries whole-image
labels and no localization, and nothing below changes that verdict.

### What was fetched

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

#### Thirteen members that are not images

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

### How the archive is read

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

#### A fetched image is not a simulated example

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

### Measured composition

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

### What the mapping loses

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

### Scene difference

Every image decodes to 384 by 512 pixels across three channels, and that is the
only property of the imagery this step measured. The v0.1.0 review describes the
capture conditions as one object on a plain background under controlled indoor
lighting; nothing here checked that description. CLAVE's target scene is a
moving belt carrying overlapping objects under a fixed camera, and fetching the
corpus narrows that gap by nothing at all.

### Acceptance criteria

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

### Reproducing this

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

## ZeroWaste, added at v0.9.1

TrashNet proved the path and is a poor corpus to train on. ZeroWaste is the one
the v0.1.0 review ranks first, and the difference is not volume: it is an
operating recovery-facility conveyor, photographed from a fixed overhead camera,
with every object localized. That is CLAVE's scene rather than a picture of one
object on a white background.

### What was fetched

| Property | Measured value |
| --- | --- |
| Artifact | `zerowaste-f-final.zip` from [Zenodo record 6412647](https://zenodo.org/records/6412647) |
| Bytes | 7,518,242,799 |
| sha256 | `9ce00fe12e0e4163d94f83e167e7d358211702d58fd6b82b9b9021615a80f117` |
| md5 published by Zenodo | `e26e31a58080bca6782dca0e56074c5d`, checked against the bytes |
| Archive members | 9,019 |
| Images | 4,503, split 3,002 train, 572 validation, 929 test |
| Annotated regions | 26,766 |
| Image size | 1920 by 1080, for all 4,503 |

Checking the publisher's own md5 as well as recording our sha256 ties the
artifact to its source rather than only to this machine. A digest we compute
proves two runs saw the same bytes; a digest the publisher computed proves those
bytes are the ones published.

The split counts match the three the corpus paper states, which is the check
that says the reader agrees with the corpus rather than merely parses it.

#### The license is recorded twice and the two disagree

The Zenodo record states CC BY 4.0. The project page at `ai.bu.edu/zerowaste`
states CC BY-NC 4.0. Nothing here depends on resolving it, because CLAVE is
personal research and satisfies the stricter of the two, and the narrower term
is the one [the v0.1.0 review](training-infrastructure-review.md) carries. A
project intending to use this corpus commercially would have to resolve it with
the authors first, and the disagreement is recorded in `corpora/manifest.toml`
so nobody has to rediscover it.

### Why a second reader exists

TrashNet writes one label per image in a directory name. ZeroWaste annotates
regions inside an image, roughly six per frame and often of different materials,
in a COCO annotation file per split.

Reading ZeroWaste through the TrashNet reader would mean choosing one label per
frame, which would discard the localization that is the whole reason the corpus
outranks the others, and would invent a whole-image label the corpus never
wrote. So `LocalizedExample` is a separate type from `CorpusExample` for the
same reason `CorpusExample` is separate from the simulated `Example`: the three
make different claims and the type system should not let one pass for another.

A box arrives from COCO as an origin and a size and is carried as corners, which
is the convention the rest of this project already uses, so the conversion
happens once at ingestion rather than at every consumer.

Both readers share the property that matters: the archive is read in place and
never unpacked, so what a manifest verifies and what a training run consumes
stay the same bytes. A 7.5 GB corpus makes that less of a nicety than it was at
2,527 images.

### Measured composition

| Split | Images | Regions | Regions per image |
| --- | --- | --- | --- |
| train | 3,002 | 18,002 | 6.00 |
| validation | 572 | 3,687 | 6.45 |
| test | 929 | 5,077 | 5.47 |
| **Total** | **4,503** | **26,766** | **5.94** |

The busiest frame holds 19 annotated objects. **86 images carry no annotation at
all**, which is a photograph of a belt holding nothing the annotators marked
rather than a missing label, and the reader keeps them rather than dropping
them.

By corpus label, counting regions:

| Corpus label | Regions | Share | Maps to |
| --- | --- | --- | --- |
| cardboard | 17,751 | 66.3% | `M-08`, `M-09`, `M-10` |
| soft_plastic | 6,864 | 25.6% | `M-04` |
| rigid_plastic | 1,769 | 6.6% | `M-01`, `M-02`, `M-03`, `M-04` |
| metal | 382 | 1.4% | `M-05`, `M-06` |

**The imbalance is severe.** Cardboard outnumbers metal 46 to 1. TrashNet's
worst ratio was 4.3 to 1, so a model trained on ZeroWaste without reweighting
learns "predict cardboard" as a strategy that is right two thirds of the time.
Metal is the rarest label and it is also the one CLAVE most wants, because a
metal object is the one a magnet and an eddy current separator can actually act
on.

Against CLAVE's eleven classes. The second column counts every region whose
label spans the class, so one `cardboard` region appears in three rows; the
third counts only regions whose label names that class and no other.

| Class | Name | Regions a label spans it | Regions resolved to it |
| --- | --- | --- | --- |
| `M-01` | PET | 1,769 | 0 |
| `M-02` | HDPE | 1,769 | 0 |
| `M-03` | PP | 1,769 | 0 |
| `M-04` | Other plastic | 8,633 | 6,864 |
| `M-05` | Aluminum | 382 | 0 |
| `M-06` | Ferrous metal | 382 | 0 |
| `M-07` | Glass | 0 | 0 |
| `M-08` | Corrugated cardboard | 17,751 | 0 |
| `M-09` | Mixed paper | 17,751 | 0 |
| `M-10` | Beverage carton | 17,751 | 0 |
| `M-11` | Residue | 0 | 0 |

One class is supplied outright, `M-04`, by the 6,864 `soft_plastic` regions.
Two classes receive nothing at all: `M-07` glass is not among the annotated
foreground types and `M-11` residue is unlabeled background. The other eight are
reachable only through a label that spans several of them.

### What the mapping loses

Of 26,766 regions, **6,864 determine a taxonomy class and 19,902 do not**, which
is 74.4 percent. Averaged over the corpus, a ZeroWaste label leaves **1.198
bits** of the class identity undetermined, assuming each class inside a label's
span is equally likely.

That figure is worth holding against TrashNet's 0.54 bits. ZeroWaste is more
than twice as ambiguous per annotation, and the reason is its largest label:
`cardboard` is two thirds of the corpus and spans three fiber classes. The
corpus is better than TrashNet on scene, on volume and on localization, and
worse on label precision.

**The channel mapping recovers most of it, and only for fiber.** `CH-FIBER`
carries `M-08`, `M-09` and `M-10` together, so every `cardboard` region is
unambiguous at the channel level even though it is three-way ambiguous at the
class level. At the channel level only `rigid_plastic` and `metal` stay
undetermined, which is 2,151 regions, or 8.0 percent rather than 74.4 percent.

That is the first place in this project where the channel mapping does real
work, and it argues for something the taxonomy document already lists as open:
training a channel head on ZeroWaste and a class head where a corpus separates
classes, rather than one head on the finest labels available.

### The published splits share source sequences

Every image is named for the video it came from and the frame number inside it,
so the splits can be checked against the sequences rather than trusted.

| Comparison | Shared sequences |
| --- | --- |
| train and validation | 6 of 11 and 6 of 6 |
| train and test | 4 of 11 and 4 of 5 |
| validation and test | 2 |

**All 572 validation images and 714 of the 929 test images, 76.9 percent, come
from a sequence that also appears in train.** Anyone reporting a number on these
splits is reporting performance on the same conveyor, the same session and the
same lighting the model trained on.

How close the frames actually sit is a separate question, and the answer is
mostly reassuring:

| Nearest training frame, in frame numbers | Test images |
| --- | --- |
| 0 to 100 | 11 |
| 101 to 1,000 | 101 |
| More than 1,000 | 602 |

The median test frame is 27,900 frames from the nearest training frame, so this
is not adjacent-frame leakage. It is domain overlap, which is a weaker problem
and still one a reader should know about before quoting a test figure.

**Three file names appear in two splits each and name different images.**
`01_frame_049000.PNG` and `03_frame_049000.PNG` appear in both validation and
test; `09_frame_003000.PNG` appears in both train and test. In all three cases
the bytes differ. A pipeline that flattens the three splits into one directory
keyed by file name would silently lose three images and mislabel nothing, which
is the kind of defect that never surfaces as an error. A test locks this so it
cannot be forgotten.

### Scene difference, and why this corpus is different

TrashNet narrowed the gap to CLAVE's target scene by nothing at all. ZeroWaste
narrows it substantially, and the reasons are measurable rather than editorial:
roughly six objects per frame against TrashNet's one, a fixed overhead camera
over a moving belt, and a median annotated object covering 1.93 percent of the
frame, meaning the objects are small, cluttered and overlapping.

The simulated world CLAVE records is the same kind of picture: an overhead
camera, a belt, several objects at once. What the simulation does not have is
appearance, because its objects are parametric primitives. This corpus is the
first thing in the project that could supply it.

Two things still stand between the corpus and a trained detector. Its labels are
four where CLAVE has eleven, and 1920 by 1080 frames at 26,766 boxes is a
training run this machine cannot afford: [v0.7.0](training-application.md)
measured Faster R-CNN at 136.9 seconds per epoch over 160 frames of 320 by 240,
and scaling by images alone puts one epoch over this corpus near 43 minutes
before accounting for the 27 times larger frame.

### Acceptance criteria

Continuing the append-only `AC-INGEST` series.

| Id | Criterion | Guarded by |
| --- | --- | --- |
| `AC-INGEST-12` | When a corpus annotates regions rather than whole images, the reader shall carry one region per annotation with its pixel bounds and its mapped label | `test_a_localized_corpus_reads_regions_with_boxes_and_mapped_labels` |
| `AC-INGEST-13` | When an annotated image carries no region, the reader shall keep it and report it rather than dropping it | `test_an_image_with_no_annotation_is_kept_and_reported` |
| `AC-INGEST-14` | If an annotation names a category its file never declares, then the reader shall refuse the archive rather than skip the annotation | `test_an_annotation_naming_an_undeclared_category_is_refused` |
| `AC-INGEST-15` | If the annotations describe an image the archive does not hold, then the reader shall refuse the archive | `test_an_annotated_image_missing_from_the_archive_is_refused` |
| `AC-INGEST-16` | The reader shall report a localized corpus's composition counted in regions, separating classes it resolves from classes it only spans | `test_a_localized_composition_counts_regions_rather_than_images` |

Three further tests lock the measurements above against the real artifact:
`test_the_fetched_zerowaste_archive_matches_its_manifest_digest`,
`test_the_fetched_zerowaste_archive_holds_its_recorded_composition`, and
`test_a_zerowaste_file_name_does_not_identify_an_image_across_splits`. All three
skip when the archive is absent, which is the normal state of a clone and of CI.

### Reproducing this

```bash
mkdir -p datasets/corpora/zerowaste
curl -L -o datasets/corpora/zerowaste/zerowaste-f-final.zip \
  "https://zenodo.org/records/6412647/files/zerowaste-f-final.zip?download=1"
md5sum datasets/corpora/zerowaste/zerowaste-f-final.zip
python -m clave.cli record-digest zerowaste datasets/corpora/zerowaste/zerowaste-f-final.zip
```

The md5 must equal `e26e31a58080bca6782dca0e56074c5d` and the sha256 must equal
the one in `corpora/manifest.toml`. The download is 7.5 GB and took about seven
minutes here. With the archive in place, the three skipped tests run and check
every count in this section. An operator keeping the archive somewhere else
points `CLAVE_ZEROWASTE_ARCHIVE` at it.

### What ZeroWaste does not settle

**Nothing was trained on it.** No accuracy, no loss curve and no comparison
against synthetic data appears here. The only numbers are counts, digests, byte
sizes and one entropy figure derived from the counts.

**No image was decoded.** The sizes above come from the annotation file, which
records a width and a height per image, not from decoding pixels. Ingestion
deliberately needs no image library, and the gate installs none.

**No label was checked by eye.** Nothing here says an annotation is correct,
tight, or complete. The reader checks that the corpus is internally consistent,
which is a different claim.

**The segmentation masks are not read.** Each split carries a `sem_seg`
directory the reader ignores, because CLAVE's decision needs a box and a class
rather than a mask, and reading masks nobody consumes would mean digesting and
documenting data that no part of this project uses.

## What is still unproven

**Two of the four shortlisted corpora remain unfetched.** SpectralWaste and
TACO still carry no digest. ZeroWaste, which the v0.1.0 review ranks first, was
fetched at v0.9.1 and is measured above.

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
