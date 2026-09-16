"""Tests for the still capture.

A still is presentation, so what these guard is that it stays presentation:
the lighting reaches the world as an argument and never as a change to the
configuration every dataset, training run and benchmark reads.
"""

import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from clave.demo.still import StillError, StillScenario, write_png

ROOT = Path(__file__).resolve().parents[2]
STILLS = ROOT / "configs" / "stills"


def test_every_shipped_still_loads() -> None:
    """A still is named and nothing else has to be supplied."""
    files = sorted(STILLS.glob("*.yml"))
    assert files, "no still ships with the project"
    for path in files:
        scenario = StillScenario.load(path)
        assert scenario.cameras
        assert scenario.width > 0 and scenario.height > 0


def test_the_thumbnail_is_sixteen_by_nine() -> None:
    """The card plate crops anything else."""
    scenario = StillScenario.load(STILLS / "thumbnail.yml")
    assert scenario.width * 9 == scenario.height * 16


def test_every_camera_sits_inside_the_stated_ranges() -> None:
    """The ranges are what keep the arm readable rather than a dark smudge."""
    scenario = StillScenario.load(STILLS / "thumbnail.yml")
    assert len(scenario.cameras) >= 3
    for camera in scenario.cameras:
        assert 0.8 <= camera.distance <= 1.8, camera.name
        assert -35.0 <= camera.elevation <= -10.0, camera.name
        assert 20.0 <= camera.fovy <= 60.0, camera.name
    # Three points of view rather than one frame rendered three times.
    assert len({camera.azimuth for camera in scenario.cameras}) == len(scenario.cameras)


def test_a_missing_key_fails_naming_itself(tmp_path: Path) -> None:
    """A still carries no default, as no configuration here does."""
    raw = yaml.safe_load((STILLS / "thumbnail.yml").read_text())
    del raw["still"]["seed"]
    path = tmp_path / "broken.yml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(StillError, match="still.seed"):
        StillScenario.load(path)


def test_the_lighting_never_reaches_the_shared_world() -> None:
    """The world every measurement reads must not carry presentation values.

    This is the constraint the whole feature is built around: a frame that
    shifts the benchmark's world is worth less than no frame.
    """
    world = yaml.safe_load(
        (ROOT / "configs" / "world" / "sorting_line.yml").read_text()
    )
    scenario = StillScenario.load(STILLS / "thumbnail.yml")
    assert scenario.lighting, "the still declares no lighting of its own"
    for key in ("headlight", "background", "lights"):
        assert key not in world, f"{key} leaked into the shared world"
    # The world's own lighting section is the one it always had.
    assert set(world["lighting"]) == {"diffuse"}


def test_a_world_built_without_a_still_is_unchanged() -> None:
    """The presentation argument defaults to adding nothing."""
    pytest.importorskip("mujoco")
    import mujoco

    from clave.world import config, scene

    raw = config.load(ROOT / "configs" / "world" / "sorting_line.yml")
    plain, _, _ = scene.build(raw, np.random.default_rng(0), ROOT)
    lit, _, _ = scene.build(
        raw,
        np.random.default_rng(0),
        ROOT,
        presentation=StillScenario.load(STILLS / "thumbnail.yml").lighting,
    )
    assert plain.nlight == 1, "the shared world gained a light"
    assert lit.nlight > plain.nlight, "the still added none"
    # Nothing but lighting differs: same bodies, same geoms, same degrees of
    # freedom, so no trajectory can depend on which one was built.
    assert (plain.nbody, plain.nq, plain.nv) == (lit.nbody, lit.nq, lit.nv)
    names = [
        mujoco.mj_id2name(plain, mujoco.mjtObj.mjOBJ_LIGHT, i)
        for i in range(plain.nlight)
    ]
    assert not any(n and n.startswith("presentation_") for n in names)


@pytest.mark.skipif(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
    reason="ffmpeg is not installed here",
)
def test_a_written_still_is_the_pixels_it_was_given(tmp_path: Path) -> None:
    """Nothing is drawn on a frame after the renderer made it.

    One flat gray frame in, one flat gray frame out. PNG is lossless, so an
    overlay, a caption or a watermark would show up exactly.
    """
    path = tmp_path / "flat.png"
    write_png(np.full((48, 64, 3), 137, dtype=np.uint8), path, 64, 48)
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    pixels = np.frombuffer(decoded, dtype=np.uint8)
    assert pixels.size == 48 * 64 * 3
    assert int(pixels.min()) == 137
    assert int(pixels.max()) == 137


def _rendering_available() -> bool:
    """Whether offscreen rendering works here.

    MuJoCo aborts the process when no GL backend is present, so the probe runs
    in a subprocess where an abort kills the child rather than the session.
    """
    import sys

    model = '<mujoco><worldbody><geom type="box" size=".1 .1 .1"/></worldbody></mujoco>'
    probe = (
        "import os;os.environ.setdefault('MUJOCO_GL','osmesa');"
        "import mujoco;"
        f"m=mujoco.MjModel.from_xml_string({model!r});"
        "mujoco.Renderer(m,height=8,width=8)"
    )
    try:
        return (
            subprocess.run(
                [sys.executable, "-c", probe], capture_output=True, timeout=60
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def test_a_capture_writes_one_frame_per_camera(tmp_path: Path) -> None:
    """The command produces a file for every point of view it declares."""
    pytest.importorskip("mujoco")
    if not _rendering_available():
        pytest.skip("no offscreen GL backend here")
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        pytest.skip("ffmpeg is not installed here")

    from clave.demo.still import capture

    # A short, small version of the shipped still, because what this proves is
    # that the path works rather than what the frame looks like.
    raw = yaml.safe_load((STILLS / "thumbnail.yml").read_text())
    raw["still"]["capture_at_seconds"] = 1.5
    raw["still"]["width"] = 160
    raw["still"]["height"] = 90
    path = tmp_path / "short.yml"
    path.write_text(yaml.safe_dump(raw))

    scenario = StillScenario.load(path)
    written = capture(ROOT, scenario, tmp_path)

    assert len(written) == len(scenario.cameras)
    for file in written:
        assert file.is_file() and file.stat().st_size > 0
        size = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(file),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert size == "160,90"
    # Three cameras, three different pictures.
    assert len({file.read_bytes() for file in written}) == len(written)


def test_a_still_naming_no_camera_is_refused(tmp_path: Path) -> None:
    """A still with no point of view renders nothing."""
    raw = yaml.safe_load((STILLS / "thumbnail.yml").read_text())
    raw["cameras"] = []
    path = tmp_path / "blind.yml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(StillError, match="no camera"):
        StillScenario.load(path)


def test_a_camera_needs_three_numbers_to_look_at(tmp_path: Path) -> None:
    """Two coordinates name no point in a scene."""
    raw = yaml.safe_load((STILLS / "thumbnail.yml").read_text())
    raw["cameras"][0]["lookat_meters"] = [0.0, 0.0]
    path = tmp_path / "flat.yml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(StillError, match="three numbers"):
        StillScenario.load(path)
