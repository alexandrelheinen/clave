"""The pose to command this tick, on a path the arm can follow.

A phase says where it wants the flange. It does not say how to get there, and
commanding the goal outright is how a controller asks for a jump the actuators
answer with a lunge. Guidance is the layer in between: a straight line in task
space, which is what an industrial linear move is, stepped at no more than the
configured speed.

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

Two things this does not do yet, both scheduled. The acceleration bound is
read from the settings and not yet applied, so the first tick of a traverse
asks for full speed from a standstill. And there is no interception: the pose
commanded is where the marker is, not where it will be when the arm arrives,
so the flange trails a moving object by whatever the traverse took. Both are
deliberate for now. The lag is visible in a rollout, and measuring it is what
sizes the interception rather than guessing at it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from clave.control.settings import GuidanceSettings, Point
from clave.control.task import Goal


@dataclass(frozen=True)
class Command:
    """The pose to command this tick.

    Attributes:
        position: Where the flange should be by the end of the tick.
        yaw: What the tool should be turned to about the belt normal, or None
            to hold the rotation the arm already has.
    """

    position: Point
    yaw: float | None


def toward(
    reference: Point,
    goal: Goal,
    timestep: float,
    limits: GuidanceSettings,
    keep_inside: Callable[[Point], Point] | None = None,
) -> Command:
    """Return the pose to command one tick along the way to a goal.

    Args:
        reference: The pose commanded last tick, which is what this advances.
            Seed it from the flange once, at the start of a motion, and feed
            this function's own output back into it afterwards. Passing the
            measured flange every tick makes the reference chase the plant
            instead of leading it.
        goal: Where the phase wants it, and what rotation it asked for.
        timestep: How long this tick lasts, in seconds.
        limits: The speed and acceleration ceilings.
        keep_inside: Pushes a pose back into the region the arm is trusted
            over, or None to step without that constraint. Supplied rather
            than computed here, so the region is the one `clave.world.arm`
            enforces and cannot drift from it.

    Returns:
        The command. Its position is the goal itself once the goal is within
        one tick's travel, because stepping a fixed distance past a near goal
        is what makes a reference buzz around a target it has already met.
    """
    inside = keep_inside if keep_inside is not None else _unchanged
    remaining = math.dist(reference, goal.position)
    reach = limits.max_speed * timestep
    if remaining <= reach or remaining == 0.0:
        return Command(position=inside(goal.position), yaw=goal.yaw)

    fraction = reach / remaining
    stepped = tuple(
        place + (wanted - place) * fraction
        for place, wanted in zip(reference, goal.position, strict=True)
    )
    return Command(position=inside((stepped[0], stepped[1], stepped[2])), yaw=goal.yaw)


def _unchanged(pose: Point) -> Point:
    """Return the pose as given, for a caller that supplied no constraint.

    Args:
        pose: The pose.

    Returns:
        The same pose.
    """
    return pose
