# Where sorted material goes, and what picks it up

Two questions stand between CLAVE and a prototype that completes a pick: what
receives an object once the arm has it, and what the arm holds it with. Both
are settled in industry and both have a simulation cost, and those two
answers do not point the same way for the second question. This document
surveys the field, states what each option costs to simulate, and recommends.

Every claim here carries its source. Where a vendor publishes a figure the
figure is quoted; where a vendor publishes only marketing, that is said
rather than papered over.

## What receives the material

**Chutes into bunkers, not lanes and not free-standing containers.** A
recovery facility puts the robot over the sorting belt and an opening beside
it. The picked object is dropped through that opening into a chute, the
chute feeds a bunker under the sort floor, and the bunker is metered out to a
baler later. The process model for recovery facilities describes recyclables
picked from the conveyor being "dropped into chutes that lead into bunkers
under the sort room", the bunker being "a holding area where the materials
are subsequently metered-from prior to, for example, baling". Vendor
descriptions of robotic cells use the same word: arms "divert targeted
commodities into designated chutes based on facility-specific priorities".

Two things follow for a simulation, and they are what makes the answer
useful rather than trivia.

The drop is a **release above an opening**, not a placement. The arm does not
carry an object to a container and set it down; it moves a short distance to
the side of the belt and opens the effector. That is a much smaller motion
than a place, and it is why published pick rates are per-minute rather than
per-ten-seconds.

The opening is **beside the belt and at belt height or just below**, because
the chute's job is to get out of the arm's way. A container standing on the
floor, which is what CLAVE models today, describes a different machine: it
puts the release point below the belt surface and turns a sideways move into
a reach down.

**What about lanes.** A second conveyor as the destination does exist, but
not as the robot's target: cross-belt and cascade layouts move material
between *stages* of a plant, and the robot inside a stage still drops into a
chute. Making a lane the robot's destination would model a machine the
survey did not find.

**Recommendation.** Replace the free-standing bins with a chute opening per
channel, set into the side of the conveyor structure at belt height, and
define a completed place as the object crossing the opening's plane with the
effector open. This is both the industry shape and by far the cheapest thing
to simulate: an opening is a hole in a wall, and the test for a successful
place is a position predicate rather than a contact sequence.

## What picks it up

The field splits by waste stream, and CLAVE's stream is the one that
complicates the obvious answer.

**Municipal packaging uses suction. Construction and demolition uses
fingers.** A 2025 survey of the field states it directly: studies that
develop sorting systems for municipal solid waste "commonly utilize a vacuum
gripper", while solutions for construction and demolition waste "usually
employ a finger gripper". The vendors line up with that. AMP's Delta
sortation system is suction, and the page giving operator guidance refers to
"replacing a suction cup" as routine maintenance; AMP reports 80 to 120 picks
per minute against about 40 for a human sorter, and up to 140 on a single
robot. ZenRobotics' Heavy Picker, aimed at construction, demolition,
commercial and industrial waste, is a mechanical gripper rated at 40 kg
maximum object weight, 1.5 m maximum object size and up to 2,300 picks per
hour per arm, which is about 38 per minute.

The performance split is documented rather than folkloric. Suction "works
well on flat, lightweight items by targeting the material's centre of mass"
and is "the superior choice for rigid, flat objects like plastic plates and
tin cans". It fails in three specific ways that matter here: it "performed
poorly on deformable items due to sealing failures"; target objects in
recycling "can be dirty, crushed and/or folded, making it difficult for a
suction gripper to create a good seal"; and the ambient dust of a facility
"will be sucked into the suction gripper as it attempts to pick up target
objects". For cylindrical objects such as glass bottles, fingered grippers
outperform suction; for flat objects such as dishes, suction outperforms
fingers. A 3D-printed two-finger gripper for lightweight waste reports grasp
success up to 80 percent on bottles, cups and bags.

**So the maintainer's reasoning is half right and the half that is wrong is
worth knowing.** That waste may be crushed, because it is not a product, is
a real argument and it is an argument *for* a mechanical gripper: the usual
reason to prefer suction, which is not marking the goods, does not apply to
something on its way to a baler. That a waste surface is dirty and unstable
is also supported, and specifically for deformable and folded items. What is
wrong is the implication that suction therefore does not work on this
stream: for rigid packaging under a nadir camera, which is exactly CLAVE's
object set of cans, boxes and bottles, suction is what the industry actually
runs, and it is faster.

**What decides it here is not the stream but the simulator.** MuJoCo
Menagerie carries a Robotiq 2F-85 parallel-jaw gripper, from the same
collection the UR10e already comes from, with published specifications: 85 mm
stroke, 5 kg payload, grip force programmable from 20 to 235 N, 0.05 mm
repeatability, 1.3 kg, and an ISO 9409-1-50-4-M6 flange, which is the
standard the UR10e wrist presents. It carries no suction or vacuum end
effector, and MuJoCo has no vacuum primitive: a suction pick is simulated by
creating a weld or equality constraint between the tool and the object when
some scripted condition holds, and releasing it later.

That difference is the whole decision. A parallel jaw closing on an object is
contact physics the simulator solves, so a grasp that fails because the
object squirted out of the fingers is a result. A weld that appears when the
tool is near enough is a scripted success: it proves the plumbing runs and
nothing about whether a pick would hold. CLAVE's constitution forbids
presenting the second as the first, and `D-13` already set the precedent that
a validated open model outranks one authored here.

**Recommendation.** Adopt the Robotiq 2F-85 from Menagerie, vendored the way
the UR10e was. Record that this is a departure from what a municipal
packaging line would install, that the departure is made for simulation
fidelity rather than for process realism, and that it costs throughput
against the suction systems the survey describes. A suction effector remains
the honest thing to add later *if* a vacuum model arrives that is more than a
conditional weld.

**What adopting it costs.** The jaw opens 85 mm and the world currently
admits objects up to `arm.max_grasp_width_meters` of 180 mm.
`docs/measurements.md` records the object set at two earlier bounds: at a
55.7 mm jaw, 14 objects and 4 of 11 classes; at a 180 mm stroke, 18 objects
and the same 4 classes. Eighty-five millimetres lands between them, so the
set shrinks and the class coverage probably does not move, since it did not
move across that whole range. The number has to be re-swept rather than
interpolated.

## What this does not settle

Whether a grasp succeeds. Nothing in this document, and nothing in the
simulator until the gripper lands, says how often a closing jaw holds a
tumbling package on a moving belt. That is the first thing the effector makes
measurable and it is the reason to build it.

## Sources

- [Description of the Material Recovery Facilities Process Model](https://mswdst.rti.org/docs/MRF_Model_OCR.pdf), RTI, on chutes, bunkers and metering.
- [Autonomous data collection and system control for material recovery facilities](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11801535), on robotic sorters over the belt and ejection into bunkers.
- [Vacuum extraction for material sorting applications](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12234128), on releasing suction to direct an item into a collection bunker.
- [Systems and methods for robotic suction grippers](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11059075), on sealing failures against dirty, crushed and folded objects and on ingested dust.
- [5 questions about robotic sorting in C&D recycling](https://www.cdrecycler.com/article/5-questions-about-robotic-sorting-in-cd-recycling/), Construction & Demolition Recycling.
- [Heavy Picker](https://www.terex.com/zenrobotics/robots/heavy-picker), ZenRobotics/Terex: 40 kg maximum object weight, 1.5 m maximum object size, up to 2,300 picks per hour per arm.
- [ZenRobotics Heavy Picker](https://www.recyclingproductnews.com/product/5345/zenrobotics-heavy-picker), Recycling Product News, on the 50 to 500 mm gripper opening.
- [Delta robotic sortation system](https://ampsortation.com/technologies/delta), AMP, referring to suction cup replacement as routine service.
- [AMP Robotics achieves data milestones and recycling automation breakthrough](https://ampsortation.com/articles/amp-robotics-achieves-data-milestones-and-recycling-automation-breakthrough), on 120 to 140 picks per minute.
- [Samurai sorting robot](https://www.machinexrecycling.com/sorting/equipment/samurai-sorting-robot/), Machinex: up to 70 picks per minute against 30 to 40 for a human sorter.
- [System Layout and Grasp Efficiency Optimization for a Multirobot Waste Sorting System](https://doi.org/10.3390/robotics14030022), Robotics 2025, on vacuum grippers for municipal waste and finger grippers for construction and demolition.
- [Design and Experimental Validation of a 3D-Printed Two-Finger Gripper with a V-Shaped Profile for Lightweight Waste Collection](https://doi.org/10.3390/robotics14070087), Robotics 2025, reporting grasp success up to 80 percent.
- [Enhancing recycling efficiency: a rapid glass bottle sorting gripper](https://www.sciencedirect.com/science/article/abs/pii/S0921889024000307), Robotics and Autonomous Systems 2024, on combining suction and two-finger operation.
- [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie), Google DeepMind, for the Robotiq 2F-85 and the absence of any suction model.
- [Robotiq 2F-85](https://www.roboticscenter.ai/en/hardware/robotiq-2f-85), for 85 mm stroke, 5 kg payload, 20 to 235 N grip force, 0.05 mm repeatability.
