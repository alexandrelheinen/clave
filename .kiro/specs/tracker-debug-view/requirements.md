# Tracker debug view

## Intent

Make the tracker auditable by eye. Today the only way to see what it decided is
to read a table of `WasteObject` values beside a video of a belt, and hold the
correspondence in your head. That is how an integration defect survived 134
passing tests: the tracker ran one object as two tracks, one carrying the
material and the other the geometry, and nothing showed it until somebody
printed the records and counted.

This spec builds the view that would have shown it in one frame. Every property
the tracker holds is drawn where the object is, so a reader can follow the
algorithm part by part rather than infer it.

The audience is whoever is debugging the tracker, which today is the maintainer.
It is not a published figure and it must never become one.

## Scope

**In.** A debug renderer that annotates a rendered frame with every field of the
records the tracker settled at that instant. A live window for watching a run as
it happens, and a written artifact for reading afterwards. One command. The
decision recording why an overlay is permitted here.

**Out.** The rest of the pipeline. Perception and policy models, the safety
layer, the publisher, the benchmark: this view shows the tracker and says so, so
a frame it produces cannot be read as evidence about anything else. Training of
any kind. Wiring the tracker into `clave.runtime.loop`, which is `AC-TRACK-41`
in `learned-tracker`.

## Constraints

- **This is the one place an overlay is allowed, and it is quarantined.**
  `agents/claude.md` forbids post-processed overlays on captured output, and
  `D-15` records that a published figure may carry geometry and never an
  overlay. Those hold. The debug view is a diagnostic rather than evidence, it
  writes to its own directory through its own encoder, and nothing it produces
  may reach the published path. `D-17` records the distinction.
- **Every annotation is read from a record, never computed for display.** A
  value drawn on a frame that no `WasteObject` carries would be a drawing of
  something the system does not know, which is the failure the overlay rule
  exists to prevent.
- **Nothing is hidden.** A view that shows the fields somebody thought were
  interesting is a view that hides the field the defect is in.
- **The published path stays provably untouched.** The flat-gray tests that
  guard `demo` and `still` keep passing, unchanged.
- **The tracker is not wired into the runtime.** This view drives the tracker
  directly, and the frame says so, so nobody reads it as the loop's output.

## Acceptance criteria

### The view

`AC-DEBUG-01`: When the tracker settles records for an instant, the system shall
draw each record's footprint at the belt position it describes, projected back
through the same optics the adapter used.

`AC-DEBUG-02`: The system shall render every field of `WasteObject`, including
the ones computed from it, and a test shall fail when a field is added to the
record and not to the view.

`AC-DEBUG-03`: When a record is drawn, the system shall give it a colour derived
from its `track_id`, and use that colour for both its footprint and its entry in
the property listing, so the two correspond without a reader counting.

`AC-DEBUG-04`: When a track carries a field derived from the simulator rather
than from a sensor, the view shall mark that field, because a reader auditing
perception has to see which values were supplied.

`AC-DEBUG-05`: When a footprint declines to state a yaw, the view shall draw it
as unoriented rather than drawing a yaw of zero, because a box drawn square is a
claim the record did not make.

### Provenance

`AC-DEBUG-06`: The system shall draw no value that is absent from the record it
annotates, proved by a test that compares every drawn string against the
record's own fields.

`AC-DEBUG-07`: Every frame the view produces shall state that it is a debug
render of the tracker alone, so no frame of it can be mistaken for the loop's
output or for a published figure.

`AC-DEBUG-08`: The system shall write debug output to its own directory, and no
debug frame shall be written through the encoder the published figures use.

`AC-DEBUG-09`: When the published still and video paths are exercised, they
shall remain free of any drawing, proved by the existing flat-gray tests
continuing to pass unchanged.

### Running it

`AC-DEBUG-10`: The system shall offer one command that drives the tracker over a
rollout and produces the annotated output.

`AC-DEBUG-11`: When a display is available, the command shall be able to show
the run as it happens; when none is, it shall write the artifact and say why it
did not open a window, rather than failing.

`AC-DEBUG-12`: The command shall report, per frame, how many tracks were open
and how many records it drew, so a frame that drew nothing is distinguishable
from a frame the view failed on.

## Traceability

Ids are append-only. `AC-DEBUG` is a new prefix; nothing in the repository used
it. Tests name the id they guard.

## Design notes

**Why an overlay is the right answer here and the wrong answer everywhere
else.** A published figure argues something to a reader who cannot run the code,
so anything drawn on it is a claim they cannot check, which is why `D-15` puts
the geometry into the scene instead. A debug view argues nothing: it is read by
somebody who has the records open beside it, and its whole purpose is to show
the correspondence between a number and a place. The rule that protects the
first case would make the second impossible. `D-17` records that, and
`AC-DEBUG-08` and `AC-DEBUG-09` keep the two paths apart mechanically rather
than by convention.

**Why every field, rather than the useful ones.** The defect that motivated this
was two tracks over one object, visible only in the `evidence` set. A view
showing footprint and material would have shown two plausible boxes and hidden
the thing that mattered. Choosing what to display is choosing what to miss, so
`AC-DEBUG-02` makes the record's own shape the contract and fails when the two
drift.

**Why the projection runs backwards through the adapter's optics.** The record
is in belt metres and the frame is in pixels. Drawing the box requires the
inverse of the conversion `AC-TRACK-02` specifies, and using the same
`NadirOptics` the adapter used means a wrong scale factor shows up as boxes that
do not sit on their objects, rather than as a quietly consistent lie.
