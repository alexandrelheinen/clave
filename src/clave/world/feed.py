"""Holding the line at a feed rate by trimming belt speed.

A line whose throughput is whatever the spawn timer happened to produce
cannot be reasoned about. This gives it a setpoint in objects per second, a
measurement of what it is achieving, and a proportional-integral controller
between the two. `docs/requirements/line-throughput.md` carries the spec.

**Belt speed only regulates a rate if the feed is by distance.** With
objects released every `T` seconds the arrival rate is `1/T` whatever the
belt does: speeding up spreads the same objects over more metres. With
objects released every `s` metres of belt travel, which is what a metering
feeder does on a real line, the rate is `v / s` and speed is the throughput
knob directly. That is why [clave.world.belt] feeds by spacing.

The loop is not trivial even so, because `s` is drawn per object from a
range. The realised rate wanders around `v` over the mean spacing, and this
trims `v` to hold it.

**The measurement reads the simulator.** Counting arrivals is ground truth
and says so here rather than quietly: the tracker's own estimate is
unusable downstream of the sensing gate, so a loop built on it would
regulate the tracker's opinion rather than the line.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from clave.world.config import Range, WorldConfigError, load, require, require_range


@dataclass(frozen=True)
class FeedSettings:
    """What the feed controller reads.

    Attributes:
        rate: Objects per second the line is asked to carry.
        window_seconds: How long a span the measured rate is counted over.
        proportional_gain: Meters per second of belt speed per object per
            second of error. A positional gain: the term is added to the
            speed the run started at, not to the speed commanded last tick.
        integral_gain: Meters per second per object, since it multiplies an
            error integrated over time.
    """

    rate: float
    window_seconds: float
    proportional_gain: float
    integral_gain: float

    @classmethod
    def load(cls, raw: dict[str, Any]) -> FeedSettings:
        """Read the feed block of a world configuration.

        Args:
            raw: The parsed world configuration.

        Returns:
            The settings it describes.

        Raises:
            WorldConfigError: If the block or a key is absent, or if the rate
                or the window is not above zero. A rate at or below zero
                describes a line that carries nothing.
        """
        block = require(raw, "feed")
        return cls(
            rate=_positive(block, "rate_objects_per_second"),
            window_seconds=_positive(block, "window_seconds"),
            proportional_gain=float(require(block, "proportional_gain", "feed")),
            integral_gain=float(require(block, "integral_gain", "feed")),
        )


@dataclass(frozen=True)
class FeedScenario:
    """A rate, a belt speed and a spacing for one run, not the shipped line.

    Attributes:
        rate: Objects per second this run is asked to carry. The controller
            trims belt speed toward it, inside the shipped drive.
        belt_speed: Meters per second the belt starts at.
        spacing: Metres of belt travel between objects, centre to centre.
        pool_size: How many object bodies to compile for this run, or None
            to keep the shipped pool. A dense spacing puts more packages
            on the belt at once than the shipped pool can hold.
    """

    rate: float
    belt_speed: float
    spacing: Range
    pool_size: int | None = None

    @classmethod
    def load(cls, path: Path) -> FeedScenario:
        """Read a debug feed file.

        Args:
            path: Path to the YAML file.

        Returns:
            The scenario it names.

        Raises:
            WorldConfigError: If a key is absent, or if the rate or the
                speed is not above zero.
        """
        raw = load(path)
        pool = raw.get("pool_size")
        return cls(
            rate=_positive(raw, "rate_objects_per_second", where=""),
            belt_speed=_positive(raw, "belt_speed", where=""),
            spacing=require_range(raw, "spacing"),
            pool_size=None if pool is None else _pool_size(pool),
        )


def apply_scenario(
    settings: FeedSettings,
    scenario: FeedScenario,
    belt_speed: float | None,
) -> tuple[FeedSettings, float]:
    """Apply a debug feed file to one run.

    Args:
        settings: The shipped feed settings.
        scenario: The file's rate and speed.
        belt_speed: An operator belt speed, or None. When set, it wins over
            the speed in the file. The file's rate still applies.

    Returns:
        The settings with the file's rate, and the belt speed this run starts
        at.
    """
    speed = scenario.belt_speed if belt_speed is None else belt_speed
    return replace(settings, rate=scenario.rate), speed


def apply_pool(raw: dict[str, Any], scenario: FeedScenario) -> None:
    """Copy the file's pool into the world dict for this run.

    The scene is compiled from that dict, so this runs before the build.
    A file that names no pool leaves the shipped pool alone. The file on
    disk is not what this writes.

    Args:
        raw: The parsed world configuration, modified in place.
        scenario: The debug feed file.
    """
    if scenario.pool_size is None:
        return
    spawn = require(raw, "spawn")
    spawn["pool_size"] = scenario.pool_size


@dataclass
class RateController:
    """Trims belt speed to hold the line at its feed rate.

    Attributes:
        settings: The setpoint, the window and the gains.
        lowest: Slowest the belt drive runs, in meters per second.
        highest: Fastest it runs.
        speed: What the belt is commanded to now. Seeded with the speed the
            run drew, which also becomes the operating point the
            proportional term is measured from.
    """

    settings: FeedSettings
    lowest: float
    highest: float
    speed: float
    _base: float | None = None
    _arrivals: deque[float] = field(default_factory=deque)
    _accumulated: float = 0.0
    _measured: float = 0.0

    @property
    def measured(self) -> float:
        """The rate the line is achieving, in objects per second."""
        return self._measured

    @property
    def saturated(self) -> bool:
        """Whether the commanded speed is sitting on one of its limits."""
        return self.speed <= self.lowest or self.speed >= self.highest

    def arrived(self, at_seconds: float) -> None:
        """Record one object entering the line.

        Args:
            at_seconds: When it entered.
        """
        self._arrivals.append(at_seconds)

    def update(self, at_seconds: float, timestep: float) -> float:
        """Advance the loop one tick and return the speed to command.

        Args:
            at_seconds: Simulated time.
            timestep: How long this tick lasts, in seconds.

        Returns:
            The commanded belt speed, inside the configured range.
        """
        opened = at_seconds - self.settings.window_seconds
        while self._arrivals and self._arrivals[0] < opened:
            self._arrivals.popleft()
        # Divided by the window rather than by how long the run has lasted,
        # so the figure is a rate the line is achieving now and not an
        # average over a start-up transient it has long left behind. Early in
        # a run the window is not yet full, which reads as a low rate and is
        # the truth: the line has not yet delivered that many objects.
        filled = min(at_seconds, self.settings.window_seconds)
        self._measured = len(self._arrivals) / filled if filled > 0.0 else 0.0

        # Positional form, around the speed the run started at. The velocity
        # form, adding the terms to the current command each tick, makes the
        # proportional term an integrator of its own: at the physics rate it
        # accumulates five hundred times a second, and the loop slams to a
        # drive limit on any error at all and sits there.
        if self._base is None:
            self._base = self.speed
        error = self.settings.rate - self._measured
        wanted = (
            self._base
            + self.settings.proportional_gain * error
            + self.settings.integral_gain * self._accumulated
        )
        bounded = min(max(wanted, self.lowest), self.highest)
        # Anti-windup by conditional integration. Accumulating while the
        # command is pinned to a limit buys nothing, because the extra term
        # cannot reach the plant, and it costs an overshoot on the way back
        # when the condition clears.
        pinned_high = bounded >= self.highest and error > 0.0
        pinned_low = bounded <= self.lowest and error < 0.0
        if not (pinned_high or pinned_low):
            self._accumulated += error * timestep
        self.speed = bounded
        return bounded


def _pool_size(value: Any) -> int:
    """Read a pool size, which has to be a whole number above zero.

    Args:
        value: The parsed YAML value.

    Returns:
        The size.

    Raises:
        WorldConfigError: If the value is not a positive integer. A pool of
            zero compiles a line with nothing on it.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorldConfigError(
            f"pool_size is {value}, and a pool has to be a whole number above zero"
        )
    return value


def _positive(block: dict[str, Any], key: str, where: str = "feed") -> float:
    """Read a value that has to be above zero.

    Args:
        block: The mapping to read from.
        key: The key required.
        where: Dotted path of the parent, used in the error message. Empty
            when the key sits at the top of a debug feed file.

    Returns:
        The value.

    Raises:
        WorldConfigError: If the key is absent or the value is not positive.
    """
    value = float(require(block, key, where))
    name = f"{where}.{key}" if where else key
    if not value > 0.0:
        raise WorldConfigError(
            f"{name} is {value}, and a line carrying nothing is not a line"
        )
    return value
