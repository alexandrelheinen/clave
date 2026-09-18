"""The boundary every reading crosses before it can reach a track.

Covers `AC-TRACK-08` and `AC-TRACK-48`.

`GroundTruth` is deliberately in the same union as real evidence, so simulation
supplies labels through the path real sensors use. The price of that is a gate:
a runtime configured for hardware has to refuse it, and the refusal has to sit
where nothing can go round it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clave.tracker.belt_frame import Footprint
from clave.tracker.evidence import (
    Code,
    Detection,
    Evidence,
    GroundTruth,
    PixelMask,
    Role,
)
from clave.tracker.intake import Deployment, Intake, IntakeError
from clave.tracker.sensors import SensorSpec, load_sensors
from clave.world.config import load

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "world" / "sorting_line.yml"


def sensors() -> tuple[SensorSpec, ...]:
    """The sensors the shipped line declares."""
    return load_sensors(load(CONFIG))


def a_detection(source: str = "gate_wide") -> Evidence:
    """A reading the wide camera could have produced."""
    return Evidence(
        source_id=source,
        role=Role.DETECTION,
        observed_at_nanos=1_000,
        confidence=0.9,
        payload=Detection(
            footprint=Footprint(
                center=(-1.0, 0.0, 0.93),
                major_extent=0.10,
                minor_extent=0.06,
                yaw=0.0,
            ),
            mask=PixelMask(width=64, height=64, runs=((10, 20, 10),)),
        ),
    )


def a_label(source: str = "simulator") -> Evidence:
    """What the simulator offers through the sensor path."""
    return Evidence(
        source_id=source,
        role=Role.GROUND_TRUTH,
        observed_at_nanos=1_000,
        confidence=1.0,
        payload=GroundTruth(
            object_id=3, material_class="M-06", position=(-1.0, 0.0, 0.93)
        ),
    )


def test_simulation_admits_the_simulator_label() -> None:
    """AC-TRACK-08. This is the whole reason GroundTruth is in the union."""
    intake = Intake(Deployment.SIMULATED, sensors())
    admitted = intake.accept(a_label()).payload
    assert isinstance(admitted, GroundTruth)
    assert admitted.object_id == 3


def test_hardware_refuses_the_simulator_label_naming_the_source() -> None:
    """AC-TRACK-08.

    Naming the source matters: on a real line the interesting question is which
    process is still offering simulated labels, not that one did.
    """
    intake = Intake(Deployment.HARDWARE, sensors())
    with pytest.raises(IntakeError, match="replay-harness"):
        intake.accept(a_label(source="replay-harness"))


def test_hardware_admits_everything_a_real_sensor_could_have_produced() -> None:
    """AC-TRACK-08. The gate refuses one variant, not the deployment."""
    intake = Intake(Deployment.HARDWARE, sensors())
    assert intake.accept(a_detection()).role is Role.DETECTION


def test_a_reading_from_an_undeclared_sensor_is_refused() -> None:
    """AC-TRACK-25.

    Provenance that names nothing the line declares is provenance nobody can
    audit, and it is usually a camera that was removed from configuration and
    left running.
    """
    intake = Intake(Deployment.SIMULATED, sensors())
    with pytest.raises(IntakeError, match="gate_removed"):
        intake.accept(a_detection(source="gate_removed"))


def test_a_reading_whose_role_its_sensor_does_not_produce_is_refused() -> None:
    """AC-TRACK-25. A code read attributed to the detection camera is a fault.

    The wide camera is nearly three times coarser than a barcode module needs,
    so evidence like this cannot have come from where it says it did.
    """
    intake = Intake(Deployment.SIMULATED, sensors())
    misattributed = Evidence(
        source_id="gate_wide",
        role=Role.CODE,
        observed_at_nanos=1_000,
        confidence=0.9,
        payload=Code(symbology="UPC_A", digits="037600138727"),
    )
    with pytest.raises(IntakeError, match="gate_wide"):
        intake.accept(misattributed)


def test_the_simulator_is_not_required_to_be_a_declared_camera() -> None:
    """AC-TRACK-08.

    Ground truth comes from the world rather than from an installation, so it
    has no entry in `cameras` and could not have one. That exemption is exactly
    what the hardware gate exists to close.
    """
    intake = Intake(Deployment.SIMULATED, sensors())
    assert intake.accept(a_label(source="anything-at-all")).role is Role.GROUND_TRUTH


def test_a_deployment_is_stated_rather_than_inferred() -> None:
    """AC-TRACK-08.

    There is no default. A runtime that guessed would guess SIMULATED, which is
    the permissive answer, and the one time it mattered it would be wrong.
    """
    with pytest.raises(TypeError):
        Intake()  # type: ignore[call-arg]


def test_nothing_reaches_a_track_without_crossing_the_gate() -> None:
    """AC-TRACK-48.

    The refusal is worth nothing if a caller can construct evidence and hand it
    straight to fusion. `Intake.accept` is the only function in the package
    that returns an admitted reading, so this asserts the bypass does not
    exist by counting the ways in.

    The full property lands with `Tracker`, which takes an `Intake` rather than
    raw evidence. Until then this holds the boundary to being the only door.
    """
    package = ROOT / "src" / "clave" / "tracker"
    admitting = [
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if "def accept(" in path.read_text()
    ]
    assert admitting == ["intake.py"]
