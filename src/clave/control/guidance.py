"""The pose to command this tick, on a path the arm can follow.

A phase says where it wants the flange. It does not say how to get there, and
commanding the goal outright is how a controller asks for a jump the actuators
answer with a lunge. Guidance is the layer in between: a straight line in task
space, which is what an industrial linear move is, walked under a speed and an
acceleration the machine actually has.

**The first argument is the reference, not the measurement.** Guidance
integrates its own previous output, seeded once from where the flange stood.
Stepping from the measured flange instead looks equivalent and is not: the
reference then never runs ahead of the plant, so every tick it restarts from
wherever the arm lagged to and the effective speed becomes the tracking error
divided by the tick rather than the configured ceiling. Measured on the
shipped world, that mistake moved the flange 0.11 m in three seconds where
the ceiling allows 0.71 m in less than one.

**The path is kept inside a region that is not convex.** The arm is trusted
over an annulus, so a straight line between two poses it admits can still
pass through the hole around the base. That is not a tuning problem and no
choice of park pose removes it, because the base sits between the arm's
resting place and part of the belt. Each stepped pose is therefore handed to
a projection that pushes it back out of the hole, which makes the path run
straight, slide around the hole, and run straight again.

**A goal that rides the belt is aimed ahead of itself.** That lag was
measured at 102 mm against a 10 mm arrival tolerance before this existed, and
it has two parts that are easy to confuse. The arm travels while the object
moves, and the goal itself is stale: it is decided once per capture and held
for half a second, during which the belt carries the object 157 mm.

Compensating only the traverse fixes nothing once the arm has caught up,
because the traverse is then zero and the aim collapses onto a pose that is
still half a second old. So the goal carries the instant it was seen, and the
intercept is carried from there to now plus however long the traverse takes.
The traverse is the fixed point of a short iteration: guess it, carry the
object that far, and re-measure to where it landed. Belt speed is known here
rather than estimated, so all of this is arithmetic and introduces no state.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from clave.control.settings import GuidanceSettings, Point
from clave.control.task import Goal
from clave.tracker.belt_frame import carry

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the belt travel the intercept carries."""

INTERCEPT_PASSES = 3
"""How many times the intercept is re-measured before it is used.

The iteration converges geometrically while the belt runs slower than the
arm, which it does by a factor of three on this line, so three passes put the
remaining error well under the arrival tolerance. Iterating to a tolerance
instead would put an unbounded loop on the control path to buy an accuracy
nothing downstream can measure.
"""


@dataclass(frozen=True)
class Motion:
    """Where the reference stands and how fast it is going.

    Attributes:
        position: The pose commanded last tick.
        speed: How fast the reference was moving, in meters per second. Held
            across ticks because an acceleration bound is a statement about
            the change in this, and a caller that forgets it asks for a step
            in velocity every time it starts.
    """

    position: Point
    speed: float


@dataclass(frozen=True)
class Command:
    """The pose to command this tick.

    Attributes:
        position: Where the flange should be by the end of the tick.
        speed: How fast the reference is now moving, to be fed back next
            tick.
        velocity: Which way it is moving and how fast, as a vector. The
            servo needs the direction as well as the magnitude, because it
            leads the plant by a time rather than by a distance.
        yaw: What the tool should be turned to about the belt normal, or None
            to hold the rotation the arm already has.
        aim: The pose the step was aimed at, which is the goal itself unless
            the goal rides the belt. Reported so a run can show where the arm
            expected to meet an object rather than only where it went. None
            when the command was built directly rather than by [toward],
            which is how a caller asks for one pose and nothing else.
    """

    position: Point
    yaw: float | None
    speed: float = 0.0
    velocity: Point = (0.0, 0.0, 0.0)
    aim: Point | None = None


def toward(
    motion: Motion,
    goal: Goal,
    timestep: float,
    limits: GuidanceSettings,
    belt_speed: float,
    at_nanos: int,
    keep_inside: Callable[[Point], Point] | None = None,
) -> Command:
    """Return the pose to command one tick along the way to a goal.

    Args:
        motion: Where the reference stands and how fast it is going. Seed it
            from the flange at rest once, at the start of a motion, and feed
            this function's own output back into it afterwards. Passing the
            measured flange every tick makes the reference chase the plant
            instead of leading it.
        goal: Where the phase wants it, what rotation it asked for, and
            whether it rides the belt.
        timestep: How long this tick lasts, in seconds.
        limits: The speed and acceleration ceilings.
        belt_speed: How fast the belt runs, in meters per second, used to aim
            ahead of a goal that rides it.
        at_nanos: Now, against which the goal's own instant says how stale
            the pose it carries has become.
        keep_inside: Pushes a pose back into the region the arm is trusted
            over, or None to step without that constraint. Supplied rather
            than computed here, so the region is the one `clave.world.arm`
            enforces and cannot drift from it.

    Returns:
        The command.
    """
    inside = keep_inside if keep_inside is not None else _unchanged
    aim = _intercept(motion.position, goal, limits.max_speed, belt_speed, at_nanos)

    remaining = math.dist(motion.position, aim)
    speed = _speed(motion.speed, remaining, timestep, limits)
    reach = speed * timestep
    if remaining <= reach or remaining == 0.0:
        # Arriving does not licence an instant stop. Bleeding the last of the
        # speed off at the same rate everything else changes is what keeps
        # the bound true on the tick that matters most, which is the last
        # one.
        settling = max(0.0, motion.speed - limits.max_acceleration * timestep)
        return Command(position=inside(aim), speed=settling, yaw=goal.yaw, aim=aim)

    fraction = reach / remaining
    stepped = tuple(
        place + (wanted - place) * fraction
        for place, wanted in zip(motion.position, aim, strict=True)
    )
    heading = tuple(
        (wanted - place) / remaining
        for place, wanted in zip(motion.position, aim, strict=True)
    )
    return Command(
        position=inside((stepped[0], stepped[1], stepped[2])),
        speed=speed,
        velocity=(heading[0] * speed, heading[1] * speed, heading[2] * speed),
        yaw=goal.yaw,
        aim=aim,
    )


def _intercept(
    reference: Point,
    goal: Goal,
    max_speed: float,
    belt_speed: float,
    at_nanos: int,
) -> Point:
    """Return where to aim, ahead of a goal the belt is carrying.

    Args:
        reference: Where the reference stands.
        goal: The goal, which says whether it rides the belt and when its
            pose was seen.
        max_speed: The reference's speed ceiling, in meters per second.
        belt_speed: How fast the belt runs, in meters per second.
        at_nanos: Now.

    Returns:
        The goal itself when it stands still, and otherwise where the object
        will be at the instant the reference could get there, carried from
        when it was seen rather than from now.
    """
    if not goal.rides_belt or belt_speed <= 0.0 or max_speed <= 0.0:
        return goal.position
    aim = carry(goal.position, belt_speed, goal.observed_at_nanos, at_nanos)
    for _ in range(INTERCEPT_PASSES):
        seconds = math.dist(reference, aim) / max_speed
        aim = carry(
            goal.position,
            belt_speed,
            goal.observed_at_nanos,
            at_nanos + int(seconds * NANOS_PER_SECOND),
        )
    return aim


def _speed(
    speed: float, remaining: float, timestep: float, limits: GuidanceSettings
) -> float:
    """Return how fast the reference may move this tick.

    A trapezoidal profile: climb toward the ceiling while there is room to
    stop, and give the speed back once there is not. Arriving at speed is not
    arriving, because the reference overshoots and comes back, which reads on
    a plot as an arm that cannot settle.

    Args:
        speed: How fast the reference was going.
        remaining: How far it still has to go, in meters.
        timestep: How long this tick lasts, in seconds.
        limits: The speed and acceleration ceilings.

    Returns:
        The speed for this tick, never negative and never above the ceiling.
    """
    step = limits.max_acceleration * timestep
    # The stopping curve is read where the tick will end rather than where it
    # began. Reading it at the start samples a continuous curve one tick late,
    # and the profile then enters the braking leg with a drop of 0.0072 m/s
    # against a bound of 0.0050. Looking ahead cuts that to 1.8e-6 m/s.
    ahead = max(0.0, remaining - speed * timestep)
    stoppable = math.sqrt(max(0.0, 2.0 * limits.max_acceleration * ahead))
    wanted = max(0.0, min(limits.max_speed, speed + step, stoppable))
    # What is left of that residual is clamped away. On its own this floor is
    # harmful: without the look-ahead it holds the speed above the stopping
    # curve, the error compounds over the braking leg, and the profile arrives
    # fast and stops dead. With the look-ahead it binds only on the last
    # fraction of a percent, and the bound then holds exactly.
    return max(wanted, max(0.0, speed - step))


def _unchanged(pose: Point) -> Point:
    """Return the pose as given, for a caller that supplied no constraint.

    Args:
        pose: The pose.

    Returns:
        The same pose.
    """
    return pose
