"""One belief per object, and the only record a consumer reads.

`Tracker` is the one mutable thing in this package. Everything it calls is a
pure function, so what changes between two observations is visible in one class
rather than spread across the modules it drives.

`Tracker.observe` passes every reading through the intake. That is what makes
the `GroundTruth` refusal a property of the system rather than a habit: there is
no second way in, and a test counts the doors.

`WasteObject` carries no channel. The contract lists one and calls it resolved
by the routing policy rather than by perception, which means perception could
only ever write a null there, and a field that is always absent is worse than an
absent field.

It does carry `simulated`, naming the fields that came from the simulator rather
than from a sensor. No per-instance classifier exists in this repository, so a
material folded from `GroundTruth` is the simulator's label. A record that does
not say so launders a supplied value into a perceived one, which is the failure
this spec exists to end.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from clave.tracker.association import Associator, Cue, TrackSummary
from clave.tracker.belt_frame import Footprint, elapsed_seconds, propagate
from clave.tracker.evidence import Code, Detection, Evidence, GroundTruth, Height, Role
from clave.tracker.fusion import FusionSettings, Posterior, Resolver, fold, mass_band
from clave.tracker.intake import Intake
from clave.world.config import Range

NANOS_PER_SECOND = 1_000_000_000
"""Nanoseconds in a second, for the monotonic instants an observation carries."""


@dataclass
class Track:
    """What the tracker believes about one object on the belt.

    Attributes:
        track_id: Stable for the object's life on the belt, and never reused.
        footprint: Where it was last seen, at `observed_at_nanos`.
        observed_at_nanos: The instant the footprint describes.
        posterior: What it is believed to be made of.
        height: Its estimated height above the belt, or None.
        codes: Every symbol associated to it, in the order they arrived.
        contributors: Which sources have been folded in, for auditing.
        evidence: Which roles have contributed.
        simulated: Which record fields derive from the simulator's label.
        label: The simulator's object id, when one was folded in.
        first_seen_nanos: When it opened.
        last_updated_nanos: When it last took evidence.
    """

    track_id: int
    footprint: Footprint
    observed_at_nanos: int
    posterior: Posterior
    first_seen_nanos: int
    last_updated_nanos: int
    height: float | None = None
    codes: tuple[str, ...] = ()
    contributors: frozenset[str] = frozenset()
    evidence: frozenset[Role] = frozenset()
    simulated: frozenset[str] = frozenset()
    label: int | None = None

    def at(self, at_nanos: int, belt_speed: float) -> Footprint:
        """Return where this track is at a later instant.

        Args:
            at_nanos: The instant wanted.
            belt_speed: Belt speed in meters per second.

        Returns:
            The footprint, carried along belt travel.
        """
        return propagate(self.footprint, belt_speed, self.observed_at_nanos, at_nanos)

    def summarize(self, at_nanos: int, belt_speed: float) -> TrackSummary:
        """Return this track as an associator is allowed to see it.

        Args:
            at_nanos: The instant to propagate to.
            belt_speed: Belt speed in meters per second.

        Returns:
            The summary.
        """
        return TrackSummary(
            track_id=self.track_id,
            footprint=self.at(at_nanos, belt_speed),
            height=self.height,
            digits=self.codes,
            label=self.label,
            last_updated_nanos=self.last_updated_nanos,
        )


@dataclass(frozen=True)
class WasteObject:
    """The only record a consumer reads.

    No field names a sensor: `evidence` names roles, so a consumer can report
    that a decision used a code without knowing which of three cameras read it.

    Attributes:
        track_id: The identity the tracker assigned.
        observed_at_nanos: When this description was settled.
        valid_until_nanos: When belt travel invalidates the pose, which is the
            instant the object reaches the measured window exit.
        footprint: Where it is, propagated to `observed_at_nanos`.
        height: Its estimated height above the belt, or None.
        material: Taxonomy identifier, or `reject`.
        material_confidence: How much of the belief that class holds.
        density: The bulk density band its class implies, or None when nothing
            in the world carries that class.
        mass: What it might weigh, as a band, or None.
        codes: Every symbol associated to it.
        evidence: Which roles contributed.
        simulated: Which of these fields came from the simulator rather than
            from a sensor.
    """

    track_id: int
    observed_at_nanos: int
    valid_until_nanos: int
    footprint: Footprint
    height: float | None
    material: str
    material_confidence: float
    density: Range | None
    mass: Range | None
    codes: tuple[str, ...]
    evidence: frozenset[Role]
    simulated: frozenset[str]

    @property
    def grasp_point(self) -> tuple[float, float, float]:
        """Where the end effector should meet the object.

        Computed rather than stored: a stored grasp point can disagree with the
        footprint it came from and a computed one cannot.
        """
        return self.footprint.center

    @property
    def grasp_axis(self) -> float:
        """The footprint's minor axis, as a rotation about the belt normal."""
        return self.footprint.yaw + 1.5707963267948966

    @property
    def grasp_width(self) -> float:
        """What a jaw would have to open to. A suction cup ignores it."""
        return self.footprint.minor_extent

    @property
    def surface_normal(self) -> tuple[float, float, float]:
        """Where a suction cup should point.

        Vertical, because objects travel in a single layer on a flat belt and
        nothing here measures a surface orientation. Stating it as vertical is
        honest; deriving a tilt from a footprint would not be.
        """
        return (0.0, 0.0, 1.0)


@dataclass
class Tracker:
    """Holds one belief per object and folds evidence into it.

    Attributes:
        intake: The one door every reading crosses.
        associator: The rule deciding which track a reading joins.
        settings: The fusion floor, half life and density bands.
        belt_speed: Belt speed in meters per second.
        window_exit: Where the reachable window closes, in belt frame meters.
        unmeasured_extent: How wide to assume a track is before anything has
            measured it, in meters. A reading that carries no geometry, which
            `GroundTruth` does not, still opens a track somewhere, and the
            association gate scales with the track's own extent. Left at zero
            that gate is nothing and no later detection can ever join, so the
            two would run as separate tracks over one object. The caller passes
            the widest object the line handles, which
            `arm.max_grasp_width_meters` already states.
        resolve: Turns a decoded symbol into packaging components.
    """

    intake: Intake
    associator: Associator
    settings: FusionSettings
    belt_speed: float
    window_exit: float
    unmeasured_extent: float = 0.0
    resolve: Resolver | None = None
    _tracks: dict[int, Track] = field(default_factory=dict)
    _next_id: int = 1

    def observe(self, evidence: Evidence, at_nanos: int) -> None:
        """Fold one reading into whichever track it belongs to.

        Args:
            evidence: What an adapter produced.
            at_nanos: The instant to fold it at.

        Raises:
            IntakeError: If the boundary refuses the reading. Every reading
                crosses it, which is what makes the refusal a property of the
                system rather than a habit of its callers.
        """
        admitted = self.intake.accept(evidence)
        cue = _cue_of(admitted, self._extent())
        summaries = tuple(
            track.summarize(cue.observed_at_nanos, self.belt_speed)
            for track in self._tracks.values()
        )
        placed = self.associator.associate(cue, summaries)
        track = (
            self._tracks.get(placed.track_id) if placed.track_id is not None else None
        )
        if track is None:
            track = self._open(cue, at_nanos)
        self._fold(track, admitted, at_nanos)

    def settle(self, at_nanos: int) -> tuple[WasteObject, ...]:
        """Describe every open track as of one instant.

        Args:
            at_nanos: The instant to describe them at.

        Returns:
            One record per track, in the order the tracks opened.
        """
        return tuple(
            self._settle(track, at_nanos)
            for track in sorted(self._tracks.values(), key=lambda t: t.track_id)
        )

    def _extent(self) -> float:
        """Return the width to assume before anything has measured one."""
        return max(self.unmeasured_extent, 1e-6)

    def _unmeasured(self) -> Footprint:
        """Return the footprint a track carries before anything measures it.

        The extent is what the association gate scales with, so a sentinel of
        nothing means nothing can ever join. The line's widest handled object is
        the honest assumption: it over-reaches rather than under-reaches, and a
        real detection replaces it the moment one arrives.
        """
        extent = self._extent()
        return Footprint(
            center=(0.0, 0.0, 0.0), major_extent=extent, minor_extent=extent, yaw=0.0
        )

    def _open(self, cue: Cue, at_nanos: int) -> Track:
        """Start a new track from one cue.

        A `track_id` is minted here and never reused, so two objects can never
        share one and a retired identity never comes back.
        """
        track_id = self._next_id
        self._next_id += 1
        track = Track(
            track_id=track_id,
            footprint=cue.footprint or self._unmeasured(),
            observed_at_nanos=cue.observed_at_nanos,
            posterior=Posterior.uniform(),
            first_seen_nanos=at_nanos,
            last_updated_nanos=at_nanos,
        )
        self._tracks[track_id] = track
        return track

    def _fold(self, track: Track, evidence: Evidence, at_nanos: int) -> None:
        """Fold one admitted reading into one track."""
        resolver = self.resolve
        result = (
            fold(track.posterior, evidence, at_nanos, self.settings, resolver)
            if resolver is not None
            else fold(track.posterior, evidence, at_nanos, self.settings)
        )
        track.posterior = result.posterior
        track.contributors |= {evidence.source_id}
        track.evidence |= {evidence.role}
        track.last_updated_nanos = at_nanos

        payload = evidence.payload
        if isinstance(payload, Detection):
            track.footprint = payload.footprint
            track.observed_at_nanos = evidence.observed_at_nanos
            if payload.height is not None:
                track.height = payload.height
        elif isinstance(payload, Height):
            track.height = payload.top_surface - track.footprint.center[2]
        elif isinstance(payload, Code):
            if payload.digits not in track.codes:
                track.codes = (*track.codes, payload.digits)
        elif isinstance(payload, GroundTruth):
            track.label = payload.object_id
            track.simulated |= {"material"}
            if track.footprint.center == self._unmeasured().center:
                track.footprint = replace(track.footprint, center=payload.position)
                track.observed_at_nanos = evidence.observed_at_nanos

    def _settle(self, track: Track, at_nanos: int) -> WasteObject:
        """Turn one track into the record a consumer reads."""
        carried = track.at(at_nanos, self.belt_speed)
        material, confidence = track.posterior.most_likely
        density = self.settings.densities.get(material)
        volume = (
            carried.major_extent * carried.minor_extent * track.height
            if track.height is not None
            else 0.0
        )
        remaining = max(0.0, (self.window_exit - carried.center[0]))
        expires = (
            at_nanos + int(remaining / self.belt_speed * NANOS_PER_SECOND)
            if self.belt_speed > 0.0
            else at_nanos
        )
        return WasteObject(
            track_id=track.track_id,
            observed_at_nanos=at_nanos,
            valid_until_nanos=expires,
            footprint=carried,
            height=track.height,
            material=material,
            material_confidence=confidence,
            density=density,
            mass=mass_band(material, volume, self.settings),
            codes=track.codes,
            evidence=frozenset(track.evidence),
            simulated=frozenset(track.simulated),
        )


def _cue_of(evidence: Evidence, unmeasured_extent: float) -> Cue:
    """Return what an associator is allowed to see of one reading.

    Every field an implementation may read is filled here and nowhere else, so
    widening what a tracker exposes to the seam is one function to review.

    Args:
        evidence: An admitted reading.
        unmeasured_extent: How wide to call a reading that carries a position
            but no extent, which `GroundTruth` does. The association gate
            scales with it, so a sentinel here means nothing can ever join.

    Returns:
        The cue.
    """
    payload = evidence.payload
    if isinstance(payload, Detection):
        return Cue(
            observed_at_nanos=evidence.observed_at_nanos,
            footprint=payload.footprint,
            height=payload.height,
        )
    if isinstance(payload, Code):
        return Cue(observed_at_nanos=evidence.observed_at_nanos, digits=payload.digits)
    if isinstance(payload, Height):
        return Cue(
            observed_at_nanos=evidence.observed_at_nanos, height=payload.top_surface
        )
    if isinstance(payload, GroundTruth):
        return Cue(
            observed_at_nanos=evidence.observed_at_nanos,
            footprint=Footprint(
                center=payload.position,
                major_extent=unmeasured_extent,
                minor_extent=unmeasured_extent,
                yaw=0.0,
            ),
            label=payload.object_id,
        )
    return Cue(observed_at_nanos=evidence.observed_at_nanos)


def elapsed(earlier_nanos: int, later_nanos: int) -> float:
    """Return the seconds between two instants, for a caller that has both."""
    return elapsed_seconds(earlier_nanos, later_nanos)
