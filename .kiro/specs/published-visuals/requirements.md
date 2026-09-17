# Published visuals

## Intent

Produce the images and the videos that present CLAVE outside the repository,
from the world the repository actually simulates today, so that a reader who
arrives through the project page sees the machine, the line and the reachable
window the code measures rather than the ones it measured before the
manipulator changed.

Three figures and two recordings are published. Every one of them was rendered
from a world with a 0.22 m manipulator over a 1.20 m belt, and none of that
world survives: the arm is a UR10e on a pedestal beside a 3.00 m line. A figure
that shows a different machine from the one the text describes is worse than no
figure, because a reader cannot tell which of the two is out of date.

The figures also carry the argument the text makes, which the current capture
path cannot express. A still of the line shows a belt and an arm; it does not
show where the arm can reach, where the reachable window begins and ends, or
which material class the policy assigned to each package. The published figures
showed all three, drawn as geometry standing in the scene.

## Scope

**In.** A capture that can place annotation geometry in the scene; a still
scenario producing the three published figures under their published names; the
two demonstration recordings; the sweep that establishes the reachable window,
which the figures draw and which is currently measured over half the belt.

**Out.** The page text, which the author rewrites separately. The website and
its asset bucket, which this repository does not own. The thumbnail candidates
in `configs/stills/thumbnail.yml`, which serve a different purpose and stay.
The policy, the object set and the end effector, unchanged by any of this.

## Constraints

- **Annotation is geometry, never an overlay.** `standards`, No fabricated
  evidence. A shape that explains the scene is placed in the scene and rendered
  by the renderer. Nothing is drawn on a frame after the renderer produced it,
  and the test that proves it stays.
- **Annotation is presentation.** It reaches the world the same way lighting
  does, as an argument whose default adds nothing, so
  `configs/world/sorting_line.yml` stays byte-identical and no dataset,
  training run or benchmark can see a marker.
- **Every annotated quantity is read, never authored.** The reach ring takes
  its radii from the resolved layout, the window edges take their positions
  from the same sweep the safety layer consults, and a class marker takes its
  color from the taxonomy channel of the object it stands over.
- **The frame is a rollout.** As today: a seed, an instant, the scripted expert
  driving, and whatever the renderer produced at that moment.

## Acceptance criteria

### Annotation

`AC-VIS-01`: When a still scenario declares annotations, the system shall add
the annotation geometry to the scene before it is compiled, so the renderer
produces it and nothing is composited afterwards.

`AC-VIS-02`: When a world is built without annotations, the system shall add no
annotation geometry, and the bodies, coordinates and degrees of freedom shall
match a world built with them, so no trajectory can depend on which was built.

`AC-VIS-03`: When the reach ring is drawn, the system shall take its radii from
the resolved layout rather than from the scenario file.

`AC-VIS-04`: When a window edge is drawn, the system shall place it at the
position the reachability sweep reports, so the figure and the safety layer
cannot disagree.

`AC-VIS-05`: When a class marker is drawn, the system shall color it by the
taxonomy channel of the object it stands over, and shall give it no mass, so an
annotated object falls exactly as an unannotated one does.

### Published assets

`AC-VIS-06`: The system shall produce the three published figures under the
names the project page already uses, from one scenario, in one command.

`AC-VIS-07`: When the figures are produced, the manipulator shall be the one
the repository simulates, established by the model the scene loads rather than
by inspection.

`AC-VIS-08`: The system shall produce both demonstration recordings from the
same world, framed so the arm, its pedestal and the line are all in shot.

### Reachable window

`AC-REACH-07`: When the reachable window is measured, the sweep shall cover the
belt's full extent, because the belt is centered on the origin and a sweep that
starts at the origin measures half of it.

## Traceability

Ids are append-only. `AC-REACH-01` through `AC-REACH-06` belong to earlier
specs and are not reused.

## Design notes

`AC-REACH-07` is a defect rather than a new requirement, and it is recorded
here because the figures draw the quantity it corrupts. The sweep runs `x` from
zero to the belt length while objects ride from `-length/2` to `+length/2`, so
it counts only the downstream half of the window: 1.036 m against the 2.071 m
the same test admits when asked about the upstream half. The scripted expert
divides that figure by two to obtain the downstream edge, which is correct
arithmetic on a symmetric window and gives 0.518 m today, half a metre inside
the point where an object actually leaves reach. Fixing the sweep leaves that
division correct and doubles the reported time budget.

Annotation geometry attaches to the worldbody, or to an existing object body,
and never introduces a body of its own, which is what keeps `AC-VIS-02`
satisfiable by construction rather than by inspection. A marker carries zero
density so it contributes no inertia, and no contact so it cannot push anything.

The ring is drawn as a run of short boxes rather than as one curved primitive,
because MuJoCo has no torus and a cylinder would read as a disc from the
overhead camera the figures need.
