"""Holding the line at a feed rate by trimming belt speed.

Against a synthetic plant rather than the simulator. The loop's claim is
that it settles a rate onto a setpoint and respects its limits, and neither
of those needs a conveyor to prove: a plant that delivers `speed / spacing`
objects a second is the whole of what the controller sees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clave.world.config import WorldConfigError, load, require_range
from clave.world.feed import (
    FeedScenario,
    FeedSettings,
    RateController,
    apply_pool,
    apply_scenario,
)

LOW, HIGH = 0.25, 0.35
TIMESTEP = 0.002


def settings(**overrides: float) -> FeedSettings:
    """Feed settings with gains brisk enough to settle inside a test."""
    fields: dict[str, float] = {
        "rate": 0.25,
        "window_seconds": 60.0,
        "proportional_gain": 0.40,
        "integral_gain": 0.01,
    }
    fields.update(overrides)
    return FeedSettings(**fields)


def run(
    controller: RateController,
    spacing: float,
    seconds: float,
    since: float = 0.0,
) -> tuple[RateController, float]:
    """Drive a plant that delivers one object every `spacing` metres.

    Args:
        controller: The loop under test.
        spacing: Metres of belt travel between objects.
        seconds: How long to run.
        since: Where the clock already stands, so a test that changes the
            plant mid-run carries it forward. The controller prunes its
            window against a monotonic clock, and restarting one behind the
            arrivals it already holds counts them all over again.

    Returns:
        The controller and the clock it reached.
    """
    travelled, at = 0.0, since
    until = since + seconds
    while at < until:
        at += TIMESTEP
        travelled += controller.speed * TIMESTEP
        while travelled >= spacing:
            travelled -= spacing
            controller.arrived(at)
        controller.update(at, TIMESTEP)
    return controller, at


def controller(**overrides: float) -> RateController:
    """A controller starting at the middle of the drive's range."""
    return RateController(
        settings=settings(**overrides), lowest=LOW, highest=HIGH, speed=0.30
    )


def test_a_reachable_setpoint_is_settled_onto() -> None:
    """AC-RATE-07: a reachable setpoint is settled onto.

    At 1.20 m of spacing the setpoint needs 0.300 m/s, which is the middle
    of the drive's range, so the loop has room on both sides.
    """
    loop, _ = run(controller(), spacing=1.20, seconds=1200.0)
    assert loop.measured == pytest.approx(0.25, abs=0.01)
    assert loop.speed == pytest.approx(0.30, abs=0.01)


def test_the_loop_corrects_a_spacing_it_was_not_tuned_for() -> None:
    """AC-RATE-07: the loop corrects a spacing it was not tuned for.

    The non-vacuous half. Settling at the speed it started from proves
    nothing, so this feeds the plant wider and checks the belt speeds up to
    hold the same rate.
    """
    loop, _ = run(controller(), spacing=1.32, seconds=1200.0)
    assert loop.measured == pytest.approx(0.25, abs=0.01)
    assert loop.speed > 0.31


def test_the_commanded_speed_never_leaves_the_drive_range() -> None:
    """AC-RATE-05: the commanded speed never leaves the drive range."""
    for spacing in (0.40, 1.20, 4.00):
        loop = controller()
        travelled, at = 0.0, 0.0
        while at < 400.0:
            at += TIMESTEP
            travelled += loop.speed * TIMESTEP
            while travelled >= spacing:
                travelled -= spacing
                loop.arrived(at)
            assert LOW <= loop.update(at, TIMESTEP) <= HIGH


def test_an_unreachable_setpoint_saturates_rather_than_fails() -> None:
    """AC-RATE-08: an unreachable setpoint saturates rather than fails.

    Four metres of spacing delivers 0.088 objects a second even at the top
    of the drive's range, so the setpoint cannot be met and the honest
    behaviour is to run flat out and report the shortfall.
    """
    loop, _ = run(controller(), spacing=4.00, seconds=600.0)
    assert loop.speed == pytest.approx(HIGH)
    assert loop.saturated
    assert loop.measured < loop.settings.rate


def test_saturating_does_not_wind_the_integrator_up() -> None:
    """AC-RATE-06: saturating does not wind the integrator up.

    A loop pinned to a limit for ten minutes and then given a plant it can
    actually hold has to come back to the setpoint, not overshoot past it
    for as long as it spent accumulating.
    """
    loop, at = run(controller(), spacing=4.00, seconds=600.0)
    assert loop.speed == pytest.approx(HIGH)
    loop, _ = run(loop, spacing=1.20, seconds=1200.0, since=at)
    assert loop.measured == pytest.approx(0.25, abs=0.015)


def test_a_rate_at_or_below_zero_is_refused() -> None:
    """AC-RATE-02: a rate at or below zero is refused."""
    raw = {
        "feed": {
            "rate_objects_per_second": 0.0,
            "window_seconds": 60.0,
            "proportional_gain": 0.40,
            "integral_gain": 0.01,
        }
    }
    with pytest.raises(WorldConfigError, match="not a line"):
        FeedSettings.load(raw)


def test_the_shipped_configuration_loads() -> None:
    """AC-RATE-02: the shipped configuration loads."""
    from pathlib import Path

    from clave.world.config import load

    root = Path(__file__).resolve().parents[2]
    shipped = FeedSettings.load(load(root / "configs" / "world" / "sorting_line.yml"))
    assert shipped.rate > 0.0
    assert shipped.window_seconds > 0.0


def test_the_feed_loop_reads_no_perception() -> None:
    """AC-RATE-10: the feed loop reads no perception.

    The tracker's estimate is unusable downstream of the sensing gate, so a
    loop built on it would regulate the tracker's opinion rather than the
    line. Asserted against the module's imports rather than argued in a
    comment, because a comment does not fail when somebody adds one.
    """
    source = (
        Path(__file__).resolve().parents[2] / "src" / "clave" / "world" / "feed.py"
    ).read_text()
    assert "clave.tracker" not in source
    assert "import" in source, "the check is worthless if the file is empty"


def test_the_high_flow_file_keeps_the_belt_inside_the_shipped_drive() -> None:
    """AC-RATE-13: the high-flow file keeps the belt inside the shipped drive.

    Closing the spacing raises the arrival rate while the belt stays at
    the drive floor. The shipped world file keeps its own rate, its own
    spacing and its own range.
    """
    root = Path(__file__).resolve().parents[2]
    world = load(root / "configs" / "world" / "sorting_line.yml")
    shipped = FeedSettings.load(world)
    drive = require_range(world["belt"], "speed_meters_per_second", "belt")
    shipped_spacing = require_range(world["spawn"], "spacing_meters", "spawn")
    scenario = FeedScenario.load(root / "configs" / "debug" / "high-flow.yml")

    assert scenario.rate == shipped.rate
    assert drive.low <= scenario.belt_speed <= drive.high
    assert scenario.spacing.high < shipped_spacing.low
    assert scenario.belt_speed == drive.low
    carried = scenario.belt_speed / scenario.spacing.midpoint
    assert carried > shipped.rate


def test_a_feed_file_refuses_a_rate_that_is_not_positive(tmp_path: Path) -> None:
    """AC-RATE-12: a feed file refuses a rate that is not positive."""
    path = tmp_path / "feed.yml"
    path.write_text("rate_objects_per_second: 0\nbelt_speed_meters_per_second: 1.0\n")
    with pytest.raises(WorldConfigError, match="not a line"):
        FeedScenario.load(path)


def test_a_feed_file_refuses_a_missing_spacing(tmp_path: Path) -> None:
    """AC-RATE-13: a feed file refuses a missing spacing."""
    path = tmp_path / "feed.yml"
    path.write_text(
        "rate_objects_per_second: 0.125\nbelt_speed_meters_per_second: 0.25\n"
    )
    with pytest.raises(WorldConfigError, match="spacing_meters"):
        FeedScenario.load(path)


def test_a_feed_file_without_a_pool_keeps_the_shipped_one(tmp_path: Path) -> None:
    """AC-RATE-15: a feed file that names no pool keeps the shipped one."""
    path = tmp_path / "feed.yml"
    path.write_text(
        "rate_objects_per_second: 0.125\n"
        "belt_speed_meters_per_second: 0.25\n"
        "spacing_meters: [0.125, 0.125]\n"
    )
    scenario = FeedScenario.load(path)
    assert scenario.pool_size is None
    root = Path(__file__).resolve().parents[2]
    raw = load(root / "configs" / "world" / "sorting_line.yml")
    shipped = raw["spawn"]["pool_size"]
    apply_pool(raw, scenario)
    assert raw["spawn"]["pool_size"] == shipped


def test_the_high_flow_pool_is_applied_in_memory_only() -> None:
    """AC-RATE-15: the high-flow pool replaces the shipped one for the run."""
    root = Path(__file__).resolve().parents[2]
    scenario = FeedScenario.load(root / "configs" / "debug" / "high-flow.yml")
    raw = load(root / "configs" / "world" / "sorting_line.yml")
    shipped = int(raw["spawn"]["pool_size"])
    assert scenario.pool_size is not None
    assert scenario.pool_size > shipped
    apply_pool(raw, scenario)
    assert raw["spawn"]["pool_size"] == scenario.pool_size
    again = load(root / "configs" / "world" / "sorting_line.yml")
    assert int(again["spawn"]["pool_size"]) == shipped


def test_a_feed_file_refuses_a_pool_that_is_not_a_count(tmp_path: Path) -> None:
    """AC-RATE-15: a feed file refuses a pool that is not a count."""
    path = tmp_path / "feed.yml"
    path.write_text(
        "rate_objects_per_second: 0.125\n"
        "belt_speed_meters_per_second: 0.25\n"
        "spacing_meters: [0.125, 0.125]\n"
        "pool_size: 0\n"
    )
    with pytest.raises(WorldConfigError, match="pool_size"):
        FeedScenario.load(path)


def test_an_operator_belt_speed_wins_over_the_feed_file() -> None:
    """AC-RATE-12: an operator belt speed wins over the feed file."""
    root = Path(__file__).resolve().parents[2]
    shipped = FeedSettings.load(load(root / "configs" / "world" / "sorting_line.yml"))
    scenario = FeedScenario.load(root / "configs" / "debug" / "high-flow.yml")
    raised, speed = apply_scenario(shipped, scenario, None)
    assert raised.rate == scenario.rate
    assert speed == scenario.belt_speed
    assert raised.window_seconds == shipped.window_seconds
    overridden, chosen = apply_scenario(shipped, scenario, 0.30)
    assert overridden.rate == scenario.rate
    assert chosen == 0.30
