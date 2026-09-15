# Dressing the scene, and what is still missing

> Roadmap step: v1.0.2, a patch to the world of v0.5.0 · Spec:
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

## Collections worth considering, none added

Listed for a decision rather than adopted. **Nothing below is in the repository.**

| Collection | License | Size | What it has | What it costs |
| --- | --- | --- | --- | --- |
| [kevinzakka/mujoco_scanned_objects](https://github.com/kevinzakka/mujoco_scanned_objects) | MIT | 1.0 GB, 1,030 models | Google Scanned Objects converted to MJCF, with textures and V-HACD collision meshes. 127 of the names are household containers: soda can multipacks, candy boxes, mugs, jars, plant pots | A gigabyte of submodule, and the objects are scanned at real size |
| [google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) | Per model, mostly Apache-2.0 or BSD | 575 MB | The reference collection of robot models, already the source of the arm CLAVE uses through the ROBOTIS fork | Robots rather than objects. Nothing to sort |
| [robocasa/robocasa](https://github.com/robocasa/robocasa) | Not declared at the repository root | 47 MB of code, assets fetched separately | Thousands of kitchen objects across 150 categories in MJCF, sourced from Objaverse | The license is undeclared where it matters, and the assets download separately rather than pinning by submodule |
| [ARISE-Initiative/robosuite](https://github.com/ARISE-Initiative/robosuite) | Not declared at the repository root | 630 MB | A simulation framework whose object set includes cans, bottles and cereal boxes | Rejected at v0.1.2 on `S2`, since CLAVE reuses FRET's MuJoCo rather than a second framework. Its assets could still be used alone |

### The measurement that decides this

A scanned household object does not fit the gripper. The `Diet Pepsi 12 oz
Cans` model measures 0.406 x 0.129 x 0.139 m, and its smallest horizontal
dimension is **129 mm** against the gripper's **55.7 mm** clear opening. It is a
twelve pack rather than a can, and even a single soda can is about 66 mm across,
still above the opening.

So adopting a realistic object collection is not an asset decision. Every object
worth sorting needs a gripper roughly two to three times wider than the
OpenMANIPULATOR-X has, which is a different arm. The choice is between a scale
model that the current gripper can hold, which is what ships, and a realistic
object set that needs new hardware in the simulation first.

That is worth knowing before a gigabyte of meshes is pinned to find it out.

## What this does not change

**No measurement moved because of the dressing.** The belt geometry and speed
did move, so the dataset was re-recorded, the candidates retrained and the
benchmark rerun, exactly as v1.0.1 did.

**The room is not lit like a room.** One overhead light and a dark horizon. A
scene built for a camera would need more, and none of it would change a number.

**Nothing grasps.** A wider belt and a prettier room do not move the pick any
closer.
