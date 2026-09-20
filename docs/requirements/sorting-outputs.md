# Where the sorted material goes

## Intent

Give the arm somewhere to put an object. The world has eleven material
classes, a routing policy that resolves each to a channel, and a decision
that carries that channel on the wire, and none of it reaches anything
physical: the destination is eleven boxes 0.14 m on a side standing on the
floor 0.75 m from the belt, which nothing is ever placed in and which no
test reads.

This spec replaces them with what a recovery facility actually puts there,
and makes a completed place a measurable event rather than a gap in the
report.

## Scope

**In.** A chute opening per channel, set into the conveyor structure. The
geometry that decides where the arm releases. A place recorded when an
object crosses an opening, and the channel it crossed. Misroute counted
against the channel routing already resolved. The arm's release pose per
channel.

**Out.** The effector that lets go, which is `end-effector.md` and lands
first. What happens below the opening: bunkers, metering and baling are
plant downstream of anything CLAVE measures. Ejection by air jet or paddle,
which is a different machine. Any claim about throughput on a real line.

## Why a chute and not a container or a lane

Settled by [the survey](../research/sorting-outputs-and-effectors.md) rather
than by preference, and worth stating because two plausible answers were
rejected.

A recovery facility drops a picked object through an opening beside the
belt, into a chute that feeds a bunker under the sort floor, which is
metered out to a baler later. The robot's part of that is a short sideways
move and a release. It is not a place: nothing is carried to a container and
set down, which is why published pick rates are per minute rather than per
ten seconds.

**Free-standing containers**, which is what the world models today, describe
a different machine. Standing on the floor puts the release point below the
belt surface and turns a sideways move into a reach down, which costs the
cycle time the whole layout exists to protect.

**A second conveyor** exists in plants but not as a robot's destination:
cross-belt and cascade layouts move material between stages, and the robot
inside a stage still drops into a chute. Making a lane the target would
model a machine the survey did not find.

That leaves what sits under the chute, and a take-away conveyor per channel
is one of the things a plant actually puts there, alongside a bunker. It is
modelled here because a funnel ending in nothing reads as unfinished
geometry rather than as equipment, and because a reader watching a run
should be able to see where a channel goes. It is scenery in the strict
sense: the place is still the plane crossing at the opening, nothing below
it is measured, and the take-away leads off the end of the world.

## Constraints

- **The opening is beside the belt and at belt height, on the arm's own
  side.** Its job is to be out of the arm's way, which is what makes the
  release a sideways move. Putting the bank across the belt would make
  every release a reach over the line, which is a longer move and passes
  the effector over objects it is not picking.
- **Every dimension is configuration.** Opening size, spacing, height and
  the standoff from the belt edge are YAML keys that fail at load when
  absent, like every other tunable in the world.
- **The openings live inside the region the arm is trusted over.** A chute
  the arm cannot reach is a channel that can never be served, and that is a
  configuration error to catch at load rather than a fault to count at run
  time.
- **A place is a position predicate, not a contact sequence.** The object
  crossing the opening's plane with the effector open is the event. Nothing
  models the chute's interior, because nothing downstream of the opening is
  in scope.
- **Channels come from the routing policy already in place.** This spec adds
  no mapping and renames no channel.

## Acceptance criteria

Ids begin at `AC-DROP-01`. They are append-only and never reused.

`AC-DROP-01`: The system shall build one chute opening per channel the
routing policy resolves to, and shall fail at load when a channel has no
opening.

`AC-DROP-02`: The system shall place every opening inside the region the arm
is trusted over, and shall fail at load naming any that is not.

`AC-DROP-03`: The system shall read every opening dimension, spacing, height
and standoff from configuration, and shall fail at load naming any that is
absent.

`AC-DROP-04`: The system shall set the openings into the side of the
conveyor structure at belt height, so reaching one is a sideways move rather
than a reach below the belt surface.

`AC-DROP-05`: When an object crosses the plane of an opening, the system
shall record a place naming the object, the channel and the instant.

`AC-DROP-06`: When the channel an object was placed in differs from the
channel its material class resolves to, the system shall count a misroute
rather than a place.

`AC-DROP-07`: The system shall report placements and misroutes per channel,
and shall report the objects that reached the end of the belt unplaced
separately from both, because a throughput loss is not a contaminated bale.

`AC-DROP-08`: The system shall leave an object's physics alone at the
opening, so an object that does not fall through is reported as not placed
rather than removed from the world.

`AC-DROP-09`: The system shall draw each opening in the debug view in the
colour of its channel, so a reader can check a placement by looking.

`AC-DROP-10`: The system shall build the openings as funnels narrowing from
a mouth at belt height to a throat, rather than as holes, so an object
released near an edge is guided in rather than stranded on a lip.

`AC-DROP-11`: The system shall build one take-away conveyor per channel
below its funnel throat, carrying material away from the line. It is plant
downstream of the opening and nothing measures it, so it has no collision
with anything the arm can reach and no test reads its state.

`AC-DROP-12`: The system shall place the openings clear of the arm
pedestal's footprint in the belt travel axis, so a take-away conveyor
running out from under a funnel does not intersect the structure carrying
the arm.

## Design notes

**Why the place is a plane crossing.** Modelling the chute's interior would
add contact geometry nothing measures, and modelling a container would add
the question of whether an object bounced out. The opening's plane is where
the system's responsibility ends and the plant's begins, which is also
where the survey puts it.

**Why misroutes are counted here and not in validation.** The validation
harness already carries a `max_misroute_rate` gate with no way to produce
the number. This is the event that produces it.

**What stays unmeasurable until the effector lands.** Every criterion above
that involves an object leaving the arm needs an effector that can let go.
Until `end-effector.md` lands, the openings can be built, reached and
reported as reachable, and nothing can be placed in them.
