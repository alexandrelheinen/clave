# Dressing the scene, and what is still missing

> Roadmap steps: v1.0.2 and v1.0.3, patches to the world of v0.5.0 · Spec:
> [.kiro/specs/sorting-world/](../../.kiro/specs/sorting-world/)

The simulation was a belt and an arm floating over a gray plane. Everything it
measured was sound and none of it looked like equipment, which matters when the
recording is meant to show somebody what the project does.

This step stands the equipment on supports, widens the belt past what one arm
covers, halves the belt speed, and dresses the room with the warehouse
collection FRET already uses. It also records what that collection does not
have, because two of the things CLAVE would most like from it are absent.

## What was added

| Change | Value |
| --- | --- |
| Belt width | 0.16 m to **0.32 m**, doubled |
| Belt speed | 0.04 to 0.10 m/s, halved to **0.02 to 0.05 m/s** |
| Arm offset from the centerline | 0.14 m to **0.22 m** |
| Belt support | A frame on four legs |
| Arm support | A pedestal on a bolted foot |
| Room | Floor texture, shelving, a pallet jack, a trash can, a bucket |

**The belt is wider than one arm can cover, on purpose.** The workspace reaches
to 0.03 m past the centerline, so 41 percent of the width is outside it. A real
line is sized by throughput rather than by one manipulator's reach, and covering
the far side is a second arm's job. The safety layer already refuses a pick
outside the workspace, so the uncovered strip costs throughput and nothing else.

**Widening the belt moved the arm.** At 0.14 m the arm base sat inside the
belt's own footprint once the belt reached 0.16 m half width, which left the new
pedestal passing through the conveyor. The base is now 0.22 m out, where the
mounting plate clears the belt edge by 5 mm, and the centerline is still inside
the 0.266 m the workspace sweep in [world-scale.md](world-scale.md) measured.

**Nothing here changes what the simulation measures.** Every support and every
prop is static geometry standing clear of the belt and the workspace, the props
carry no collision geometry at all, and the overhead camera the models see looks
straight down at the belt. The belt surface, the arm base and the object set
keep the heights and sizes v1.0.1 set.

## The warehouse collection

`third_party/aws-robomaker-small-warehouse-world`, MIT-0, added as a submodule.
It is the same collection FRET pins, which is why it was the first place to
look.

MuJoCo reads STL, OBJ and MSH, and the upstream assets are COLLADA, so
`scripts/import_warehouse_assets.py` converts what CLAVE uses, scales it from
centimeters to meters, and puts the origin at the footprint center. The output
under `assets/warehouse/` is generated rather than committed, for the same
reason a dataset is: it is derived from bytes the submodule already pins.

A world built without it keeps the plain floor and reports `dressed = False`
rather than failing.

| Asset | Size | Used as |
| --- | --- | --- |
| `ShelfD_01`, `ShelfE_01` | 3.92 x 0.88 x 2.61 m | Shelving behind the line |
| `PalletJackB_01` | 1.15 x 0.53 x 0.96 m | A prop beside the line |
| `TrashCanC_01` | 1.45 x 0.89 x 1.27 m | A prop beside the line |
| `Bucket_01` | 0.94 x 1.22 x 1.40 m | A prop beside the line |
| `GroundB_01`, `WallB_01` | Textures | The floor |

## What the collection does not have

**No conveyor.** The fourteen models are shelving, clutter piles, a desk, a
lamp, a pallet jack, a trash can, a bucket, and the floor, wall and roof of the
building. The belt stays what it was, which is a box with side guides and now a
frame and legs. Searching further found no maintained MuJoCo conveyor
collection at all: the eight repositories that match are individual projects,
most without a license and none with more than three stars. A conveyor is a box,
so what a mesh would add is a rubber-and-roller texture rather than geometry.

**No small household containers.** The nearest thing is a clutter pile 2.7 m
across. Nothing in the collection is an object a person throws away.

## What was added at v1.0.3

Two of the collections below were adopted after the measurements in this
section were taken. What follows the table is the list as it stood when the
decision was made, kept because it is the reasoning that produced the choice.

| Source | License | Size | What it supplies |
| --- | --- | --- | --- |
| [vikashplus/YCB_sim](https://github.com/vikashplus/YCB_sim), submodule | Apache-2.0 | 24 MB checked out | Four scanned packages the gripper can close on |
| `Open-RMF/conveyor_block` on [Gazebo Fuel](https://app.gazebosim.org/Open-RMF/fuel/models/conveyor_block), downloaded | CC BY 4.0 | 1.1 MB archive | The conveyor module the belt is drawn from |

**The YCB objects are read natively.** MuJoCo loads the `.msh` files and their
PNG textures with no conversion at all, which is why this collection beat the
one gigabyte of Scanned Objects on more than size.

| Object | Narrowest horizontal axis | Taxonomy class |
| --- | --- | --- |
| `009_gelatin_box` | 30.1 mm | `M-09` paperboard |
| `007_tuna_fish_can` | 33.5 mm | `M-06` ferrous metal |
| `008_pudding_box` | 38.9 mm | `M-09` paperboard |
| `004_sugar_box` | 45.2 mm | `M-09` paperboard |

Adding them moved the world from eight of eleven classes to nine: `M-09` had no
object before, because no primitive in the set was paperboard.

**The bound moved with the measurement.** `max_grasp_width_meters` was 45 mm
while every object was a primitive whose size this project chose. The sugar box
compiles to 45.2 mm, which the real 55.7 mm gripper closes on comfortably, so
the bound is now 50 mm. The five YCB objects left out are 60.1 mm and wider and
are still refused, and the check that refuses them reads the compiled vertices
rather than a number in a file.

**The conveyor comes from Fuel, which is not a git host.** It is downloaded and
checked against a sha256 recorded in `scripts/import_scene_assets.py`, exactly
as a corpus is, and a download that does not match is refused rather than used.
The module is published at 0.500 by 0.504 by 0.502 m with its belt surface on
top, and each axis is scaled independently to the belt the world configures.
The README tabulates the factors. The modules carry no collision geometry: an
object still rests on the box the belt has always been, so drawing them moves
nothing that was ever measured.

## Collections worth considering, none added

The list as it stood before the two above were adopted. **Nothing below is in
the repository.**

| Collection | License | Size | What it has | What it costs |
| --- | --- | --- | --- | --- |
| [kevinzakka/mujoco_scanned_objects](https://github.com/kevinzakka/mujoco_scanned_objects) | MIT | 1.0 GB, 1,030 models | Google Scanned Objects converted to MJCF, with textures and V-HACD collision meshes. 127 of the names are household containers: soda can multipacks, candy boxes, mugs, jars, plant pots | A gigabyte of submodule, and the objects are scanned at real size |
| [google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) | Per model, mostly Apache-2.0 or BSD | 575 MB | The reference collection of robot models, already the source of the arm CLAVE uses through the ROBOTIS fork | Robots rather than objects. Nothing to sort |
| [robocasa/robocasa](https://github.com/robocasa/robocasa) | Not declared at the repository root | 47 MB of code, assets fetched separately | Thousands of kitchen objects across 150 categories in MJCF, sourced from Objaverse | The license is undeclared where it matters, and the assets download separately rather than pinning by submodule |
| [ARISE-Initiative/robosuite](https://github.com/ARISE-Initiative/robosuite) | Not declared at the repository root | 630 MB | A simulation framework whose object set includes cans, bottles and cereal boxes | Rejected at v0.1.2 on `S2`, since CLAVE reuses FRET's MuJoCo rather than a second framework. Its assets could still be used alone |

### The measurement that decided it, and the one that corrected it

The first measurement taken was the wrong one. The `Diet Pepsi 12 oz Cans`
model from Scanned Objects measures 0.406 x 0.129 x 0.139 m, narrowest
horizontal dimension **129 mm** against the gripper's **55.7 mm**, and the
conclusion drawn from it was that no realistic object fits and that a wider
gripper is a precondition. That model is a twelve pack rather than an item
somebody throws away, and generalizing from it was a mistake.

Measuring the nine YCB packages individually gives a different answer: **four
fit today**, listed above, and a fifth misses by 4.4 mm. What is true is
narrower than the original claim.

| Gripper opening | Objects it adds | Classes reached |
| --- | --- | --- |
| 55.7 mm, today | gelatin box, tuna can, pudding box, sugar box | `M-06`, `M-09` |
| about 62 mm | potted meat can | the same |
| about 72 mm | mustard bottle, tomato soup can, cracker box | adds `M-02` |
| about 105 mm | master chef can | the same |

So a wider gripper is worth having and is not a precondition. Four scanned
packages ship at the current opening, and the classes a wider one would add are
written down rather than guessed at.

## What this does not change

**No measurement moved because of the dressing.** The belt geometry and speed
did move, so the dataset was re-recorded, the candidates retrained and the
benchmark rerun, exactly as v1.0.1 did.

**The room is not lit like a room.** One overhead light and a dark horizon. A
scene built for a camera would need more, and none of it would change a number.

**Nothing grasps.** A wider belt and a prettier room do not move the pick any
closer.
