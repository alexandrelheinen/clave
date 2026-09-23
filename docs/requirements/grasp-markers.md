# Grasp markers in the world

## Intent

Show where the effector would go. The tracker settles a `WasteObject` for
every object on the belt, carrying a grasp point, a closing axis and a jaw
opening, and today none of that is visible. The only way to check it is to
read a table of numbers beside a video and hold the correspondence in your
head.

This spec draws the grasp pose as geometry inside the MuJoCo scene, one marker
per open track, coloured to match the track. A reader watching the simulation
sees which object the tracker believes it has, where a jaw would close on it,
and which way that jaw is turned.

The audience is whoever is debugging the tracker or the pick geometry, which
today is the maintainer.

## Scope

**In.** An effector description in configuration. A grasp pose computed from a
`WasteObject` and that description. Marker geometry pushed into the rendered
scene, one set per open track, in the track's colour. A 3D viewpoint for the
debug run, so the markers read as solids rather than as a plan view. Removal
of the two-dimensional overlay the debug view drew on captured frames.

**Out.** Grasping. Nothing in CLAVE closes a jaw, and a marker is not a plan.
Reference planning and approach trajectories, which stay in ARCO and FRET. The
runtime loop, which publishes decisions and does not render markers. Any
change to what the tracker computes: this spec reads `WasteObject` and writes
nothing back to it.

## Constraints

- **Markers are scene geometry, never an overlay.** They are pushed into
  `mjvScene` and drawn by MuJoCo's own renderer, so what a reader sees is the
  simulator drawing a solid in the world rather than a post-process painting
  on a photograph. `agents/claude.md` forbids the second and permits the
  first.
- **No marker reaches perception.** A marker exists so a person can see where
  a pick is planned. One landing in the detection render would feed the
  perception stage an object that is not on the belt, so the markers go into
  the scene of the renderer a person watches and never into the scene of the
  camera the tracker reads. The model is untouched, which is what makes that
  true by construction rather than by discipline.
- **Nothing measures the effector.** CLAVE has no gripper, in the model or on
  a bench. Every effector dimension is a stated assumption living in
  configuration, and the marker documents itself as showing an assumed
  standoff rather than a measured one.
- **The gate estimates no height.** The nadir cameras produce no depth and the
  `Height` role is refused at intake, so `WasteObject.height` is always
  absent on this line. The vertical placement of a marker is therefore
  configured, while its horizontal position, closing axis and opening are
  derived from the record.
- **No numeric default in Python.** Every dimension comes from
  `configs/world/sorting_line.yml`, and a missing key fails at load naming
  itself.
- **`clave.tracker` imports MuJoCo inside a function**, so the package still
  imports on a machine with no simulator.

## Acceptance criteria

Ids continue at `AC-MARK-01`. They are append-only and never reused.

`AC-MARK-01`: The system shall read the effector's finger length, pad
dimensions and grasp height from configuration, and shall fail at load naming
any key that is absent.

`AC-MARK-02`: The system shall place a marker's pads at the record's
horizontal grasp point, so the marker moves with the track rather than with
the object the simulator knows about.

`AC-MARK-03`: When a record's footprint is oriented, the system shall turn the
jaw so that it closes across the footprint's minor extent.

`AC-MARK-04`: When a record's footprint is not oriented, the system shall
draw no jaw axis and shall ring the pose instead, because a circular footprint
has no minor axis, a confident angle on one is worse than an absent one, and a
filled shape of the same radius hides the object the marker is checked
against.

`AC-MARK-05`: The system shall separate the two pads by the record's grasp
width, so the marker shows how far the jaw opens for that object.

`AC-MARK-06`: The system shall offset the marker's flange above the pads by
the effector's finger length, so the pose shown is where the tool mounts
rather than where the object sits.

`AC-MARK-07`: When a record's grasp width exceeds the effector's opening, the
system shall mark the pose as unreachable rather than drawing a jaw wider than
the machine has.

`AC-MARK-08`: The system shall colour a marker by the same rule the tracker
debug colours a track, so a marker and a record correspond without a reader
counting.

`AC-MARK-09`: When a track opens, the system shall draw its marker on the next
rendered frame, and when a track retires, the system shall stop drawing it.

`AC-MARK-10`: The system shall add marker geometry to a renderer's own scene
without changing the model, so that a render of the detection camera taken
while markers stand in another renderer's scene is identical, pixel for pixel,
to one taken with no marker drawn anywhere.

`AC-MARK-11`: When the scene has no room left for a geom, the system shall
stop adding markers rather than write past the buffer.

`AC-MARK-12`: The system shall render the debug run from a configured
three-dimensional viewpoint, so a marker reads as a solid in the world.

`AC-MARK-13`: The system shall draw nothing onto a captured frame after the
renderer has produced it.

`AC-MARK-14`: The system shall leave no marker in a scene that `update_scene`
has rebuilt, so markers cannot accumulate across frames and a run that stops
drawing them stops showing them.

`AC-MARK-15`: The system shall place a marker's pads from the compiled
gripper's own collision geometry, so a pad drawn or assumed is the pad the
model closes.

`AC-MARK-16`: The system shall define the grasp plane's clearance from the belt
surface to the lowest gripper collision geometry, not to the pinch point, which
sits below the pads and would grant a clearance the jaw does not have.

`AC-MARK-17`: The system shall set the grasp plane's floor from the open jaw's
lowest geometry, because the hold rises by the extra hang of the shut jaw
while the fingers close. A centre below that floor is lifted to it. A centre
above it is taken as it stands, up to the height an object on the belt still
has.

## Design notes

**Why the clearance is measured to the pads and not to the pinch point.** The
pinch site is where the jaw closes, which is the pose an arm is commanded to,
and on the compiled gripper it is **not the lowest part of the jaw**: the pads
hang **4.5 mm below it with the jaw open and 17.7 mm below it with the jaw
shut**, measured from the model at both ends of the linkage's travel. A
clearance quoted at the pinch point is therefore 4.5 to 17.7 mm more generous
than the jaw's own, and the marker's old floor of 12.2 mm put the pads **5.5 mm
inside the belt** while its own plane said they were clear of the surface. The
marker keeps standing at the pinch point and derives the plane it may descend to
from the effector's geometry, so the pose a caller reads and the clearance the
world enforces cannot disagree. The floor is the open jaw's, plus the
millimetre the rise needs so it leads the hang. The shut hang is 13.2 mm
further, and the hold climbs that while the jaw closes, which is what keeps
the shut clearance equal to the clearance the arrival granted.

**Why the pose is only partly derived.** The record supplies the horizontal
grasp point, the closing axis and the opening, and all three come from the
segmentation footprint. It supplies no height, because no sensor on this line
estimates one. Rather than invent a top face, the grasp height is a configured
plane above the belt and the marker's own documentation says so. A depth
sensor would replace that constant with a reading and change nothing else.

**Why the flange is offset by the finger length.** The pads close on the
object; the tool mounts a finger length above them. Showing the flange is what
makes the marker a pose the arm could be commanded to rather than a point on
an object.

**Why an unoriented footprint draws differently.** `Footprint.oriented` is
false when second moments find no major axis, which happens for anything
circular in plan. Drawing a jaw at the yaw that fell out of the arithmetic
would show a reader a decision the tracker did not make.
