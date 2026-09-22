"""Every tunable the arm controller reads.

Four blocks, one per module, plus the calibration offset between the pose a
marker stands at and the pose the flange is commanded to. Nothing here carries
a default: a gain buried in Python is a gain nobody reviews, and a missing key
fails at load naming itself rather than producing a run that quietly did
something else.

The workspace the arm is trusted over is deliberately absent. It comes from
`configs/world/sorting_line.yml` through `clave.world.arm`, so the region the
controller aims inside cannot drift from the region the safety layer enforces.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from clave.world.config import WorldConfigError, require

DRIFT_HORIZON = 0.30
"""How long an object's drift across the belt is carried, in seconds.

An object is driven along the belt and not across it. The drift comes from a
parcel turning or being nudged, and measured on the shipped line the
autocorrelation of the cross-belt velocity is +0.04 after 0.2 s and -0.02
after 0.8 s: it decays within a fraction of a second, so carrying it over a
four second visit is not a prediction. The p90 lateral speed on this belt is
0.261 m/s, which over four seconds is 900 mm of aim error -- and measured, two
visits in nine commanded a pose 208 and 346 mm from any object, outside the
region the arm is trusted over, with the arm falling 50 to 80 mm behind the
command while the jaws closed on nothing. 0.30 s is one and a half times the
measured decorrelation time. Configured as `task.drift_horizon_seconds`.
"""

Point = tuple[float, float, float]
"""A position in belt frame meters, which is MuJoCo world."""


class Phase(enum.Enum):
    """Where the arm is in one visit.

    The names and the shape of the transition are FRET's `PickPlaceState`
    with the grasp, placement and release states removed, so adding them
    later is filling in gaps rather than rewriting.
    """

    STANDBY = "standby"
    """Nothing to serve, and the arm is already at park."""

    TRACK = "track"
    """Following a marker at approach height."""

    DESCEND = "descend"
    """Dropping to the grasp plane. Full visit only."""

    HOLD = "hold"
    """Holding station at the grasp plane. Full visit only."""

    RETREAT = "retreat"
    """Lifting clear of the object. Full visit only."""

    DELIVER = "deliver"
    """Carrying the object to its channel's chute. Full visit only.

    The one arc of a visit no interception constrains: the object is in the
    jaw, so where it has to be and when are both the arm's to choose.
    """

    PARK = "park"
    """On the way back to rest."""

    FAULT = "fault"
    """The solver or the envelope refused the pose a phase asked for."""


class Profile(enum.Enum):
    """Which phases of a visit a run puts the arm through.

    The two profiles do not differ only in how many phases they run. They are
    driven differently: a motion-only visit is stepped toward a goal and ends
    when the flange gets there, while a full visit is planned as timed arcs
    and ends when the clock says so. A pick needs the second, because a jaw
    has to arrive at a known instant moving with the object.
    """

    MOTION_ONLY = "motion_only"
    """Standby, tracking, parking and fault, and nothing else.

    What tuning arm speed against belt speed needs: the arm goes to each
    marker in turn and moves on, with no descent in the way.
    """

    FULL_VISIT = "full_visit"
    """Adds descent, grasp, retreat and delivery, planned as one sequence."""


@dataclass(frozen=True)
class SelectionSettings:
    """How the queue is ordered and how still it is held.

    Attributes:
        exit_weight: Weights urgency against travel in the ordering cost.
            Dimensionless, because both terms of that cost are meters.
        anchor_radius: How far the tracker's estimate moves before the anchor
            the ordering scores follows it, in meters.
    """

    exit_weight: float
    anchor_radius: float


@dataclass(frozen=True)
class TaskSettings:
    """The phases of a visit, and where the arm waits between them.

    Attributes:
        profile: Which phases run.
        approach_height: Where the flange rides while following an object,
            above the belt surface, in meters.
        arrival_tolerance: How close the flange has to be to a pose before it
            counts as arrived, in meters.
        dwell_seconds: How long the flange holds station before a visit counts
            as served. Under a full visit this is also how long the jaw is
            given to close, because the two are the same wait.
        grasp_clearance: How far above the object a planned approach ends, in
            meters, and how far the retreat lifts it. Full visit only.
        approach_speed: How fast the flange is descending when it reaches
            that clearance, in meters per second. Full visit only.
        interception_limit: The longest interception a pick will plan for, in
            seconds. Beyond it the object is refused rather than chased.
        interception_margin: How much longer than the soonest feasible
            interception to take, as a multiple, so the arc has room to be
            re-aimed later.
        park_position_world: Where the arm rests with nothing to serve.
        park_marker_color: What the park pose is drawn in, as red, green and
            blue in the unit range.
        safe_clearance: Flange clearance above the belt surface for crossing
            the belt border, in meters. If None, defaults to approach_height.
        aim_tolerance: How far the freshest estimate of the object's grasp
            pose may stand from the pose a plan in flight is aiming at before
            the visit is re-solved, in meters. Past it, a plan that cannot be
            corrected is abandoned rather than flown.
        drift_horizon: How long an object's drift across the belt is carried
            forward, in seconds. The travel along the belt is carried for the
            whole interception; the drift across it decays within a fraction
            of a second and is carried for this long.
    """

    profile: Profile
    approach_height: float
    arrival_tolerance: float
    dwell_seconds: float
    grasp_clearance: float
    approach_speed: float
    interception_limit: float
    interception_margin: float
    park_position_world: Point
    park_marker_color: Point
    safe_clearance: float = 0.300
    aim_tolerance: float = 0.030
    drift_horizon: float = DRIFT_HORIZON

    def __init__(
        self,
        profile: Profile,
        approach_height: float,
        arrival_tolerance: float,
        dwell_seconds: float,
        grasp_clearance: float,
        approach_speed: float,
        interception_limit: float,
        interception_margin: float,
        park_position_world: Point | None = None,
        park_marker_color: Point = (0.0, 0.0, 0.0),
        safe_clearance: float | None = None,
        aim_tolerance: float = 0.030,
        drift_horizon: float = DRIFT_HORIZON,
        *,
        park_position: Point | None = None,
    ) -> None:
        pos = park_position_world if park_position_world is not None else park_position
        if pos is None:
            raise TypeError(
                "TaskSettings requires park_position_world or park_position"
            )
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "approach_height", approach_height)
        object.__setattr__(self, "arrival_tolerance", arrival_tolerance)
        object.__setattr__(self, "dwell_seconds", dwell_seconds)
        object.__setattr__(self, "grasp_clearance", grasp_clearance)
        object.__setattr__(self, "approach_speed", approach_speed)
        object.__setattr__(self, "interception_limit", interception_limit)
        object.__setattr__(self, "interception_margin", interception_margin)
        object.__setattr__(self, "park_position_world", pos)
        object.__setattr__(self, "park_marker_color", park_marker_color)
        object.__setattr__(
            self,
            "safe_clearance",
            safe_clearance if safe_clearance is not None else approach_height,
        )
        object.__setattr__(self, "aim_tolerance", aim_tolerance)
        object.__setattr__(self, "drift_horizon", drift_horizon)

    @property
    def park_position(self) -> Point:
        """Backwards compatibility alias for park_position_world."""
        return self.park_position_world


@dataclass(frozen=True)
class GuidanceSettings:
    """What bounds the path between two poses.

    Attributes:
        max_speed: Flange speed ceiling in task space, in meters per second.
        max_acceleration: Flange acceleration ceiling, in meters per second
            squared.
    """

    max_speed: float
    max_acceleration: float


@dataclass(frozen=True)
class ServoSettings:
    """What the joint step is allowed to do.

    Attributes:
        gain: Fraction of each solved step commanded.
        max_joint_speed: The bound a wrist singularity is judged against, in
            radians per second.
        lead_seconds: How far ahead of the commanded pose to aim, cancelling
            the lag a position loop has against a moving command.
    """

    gain: float
    max_joint_speed: float
    lead_seconds: float


@dataclass(frozen=True)
class CalibrationSettings:
    """Where the flange sits relative to the pose a marker stands at.

    Attributes:
        flange_offset: The offset, in meters.
    """

    flange_offset: Point


@dataclass(frozen=True)
class ControlSettings:
    """Everything the four control modules read.

    Attributes:
        selection: How the queue is ordered.
        task: The phases and the park pose.
        guidance: The bounds on the path.
        servo: The joint step.
        calibration: The flange offset.
    """

    selection: SelectionSettings
    task: TaskSettings
    guidance: GuidanceSettings
    servo: ServoSettings
    calibration: CalibrationSettings

    @classmethod
    def load(cls, raw: dict[str, Any]) -> ControlSettings:
        """Read the controller's configuration.

        Args:
            raw: The parsed control configuration.

        Returns:
            The settings it describes.

        Raises:
            WorldConfigError: If a block or a key is absent, if a bound is not
                positive, if a point is not three numbers, or if the profile
                names something that does not exist.
        """
        selection = require(raw, "selection")
        task = require(raw, "task")
        guidance = require(raw, "guidance")
        servo = require(raw, "servo")
        calibration = require(raw, "calibration")

        return cls(
            selection=SelectionSettings(
                exit_weight=float(require(selection, "exit_weight", "selection")),
                anchor_radius=_positive(selection, "anchor_radius_meters", "selection"),
            ),
            task=TaskSettings(
                profile=_profile(task),
                approach_height=_positive(task, "approach_height_meters", "task"),
                arrival_tolerance=_positive(task, "arrival_tolerance_meters", "task"),
                dwell_seconds=float(require(task, "dwell_seconds", "task")),
                grasp_clearance=_positive(task, "grasp_clearance_meters", "task"),
                approach_speed=_positive(
                    task, "approach_speed_meters_per_second", "task"
                ),
                interception_limit=_positive(
                    task, "interception_limit_seconds", "task"
                ),
                interception_margin=_positive(task, "interception_margin", "task"),
                park_position_world=_point(task, "park_position_meters", "task"),
                park_marker_color=_point(task, "park_marker_color", "task"),
                safe_clearance=(
                    _positive(task, "safe_clearance_meters", "task")
                    if "safe_clearance_meters" in task
                    else None
                ),
                aim_tolerance=_positive(task, "aim_tolerance_meters", "task"),
                drift_horizon=_positive(task, "drift_horizon_seconds", "task"),
            ),
            guidance=GuidanceSettings(
                max_speed=_positive(
                    guidance, "max_speed_meters_per_second", "guidance"
                ),
                max_acceleration=_positive(
                    guidance,
                    "max_acceleration_meters_per_second_squared",
                    "guidance",
                ),
            ),
            servo=ServoSettings(
                gain=float(require(servo, "gain", "servo")),
                max_joint_speed=_positive(
                    servo, "max_joint_speed_radians_per_second", "servo"
                ),
                lead_seconds=float(require(servo, "lead_seconds", "servo")),
            ),
            calibration=CalibrationSettings(
                flange_offset=_point(
                    calibration, "flange_offset_meters", "calibration"
                ),
            ),
        )


def _profile(block: dict[str, Any]) -> Profile:
    """Read the task profile, naming the alternatives when it is wrong.

    Args:
        block: The `task` block.

    Returns:
        The profile.

    Raises:
        WorldConfigError: If the key is absent or names no profile. A typo
            here is a run that silently did something else, so the message
            lists what it could have been.
    """
    name = str(require(block, "profile", "task"))
    try:
        return Profile(name)
    except ValueError:
        known = ", ".join(sorted(member.value for member in Profile))
        raise WorldConfigError(
            f"task.profile is {name!r}, which is no profile. Known: {known}"
        ) from None


def _positive(block: dict[str, Any], key: str, path: str) -> float:
    """Read a bound, refusing one that stops the arm before it starts.

    Args:
        block: The block to read from.
        key: The key required.
        path: Dotted path of the block, for the message.

    Returns:
        The value.

    Raises:
        WorldConfigError: If the key is absent or the value is not above zero.
    """
    value = float(require(block, key, path))
    if not value > 0.0:
        raise WorldConfigError(
            f"{path}.{key} is {value}, and a bound at or below zero describes "
            f"an arm that never moves"
        )
    return value


def _point(block: dict[str, Any], key: str, path: str) -> Point:
    """Read three numbers.

    Args:
        block: The block to read from.
        key: The key required.
        path: Dotted path of the block, for the message.

    Returns:
        The point.

    Raises:
        WorldConfigError: If the key is absent or does not hold three numbers.
    """
    values = [float(value) for value in require(block, key, path)]
    if len(values) != 3:
        raise WorldConfigError(
            f"{path}.{key} holds {len(values)} numbers, and this is three"
        )
    return values[0], values[1], values[2]
