"""Encoding what the simulator rendered.

Frames go to `ffmpeg` on standard input as raw `rgb24`. That needs no imaging
library in the wheel and no new dependency, and it keeps the encoder a tool the
operator already has rather than one this project pins.

A machine without `ffmpeg` runs the scenario anyway. A missing encoder means no
video, not a failed demonstration.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

ENCODER = "ffmpeg"
"""The tool that turns raw frames into a file."""


@dataclass(frozen=True)
class VideoSettings:
    """How to record, all of it from the scenario file.

    Attributes:
        path: Where the video goes.
        width: Frame width in pixels.
        height: Frame height in pixels.
        frames_per_second: Playback rate.
        interval_seconds: Simulated seconds between rendered frames. The loop
            decides every half simulated second, which is far too sparse to
            watch, so the video renders on its own cadence.
        azimuth: Camera azimuth in degrees.
        elevation: Camera elevation in degrees.
        distance: Camera distance from its target, in meters.
        lookat: What the camera points at, in world meters.
    """

    path: Path
    width: int
    height: int
    frames_per_second: int
    interval_seconds: float
    azimuth: float
    elevation: float
    distance: float
    lookat: tuple[float, float, float]

    @property
    def speed(self) -> float:
        """How fast the recording plays against simulated time."""
        return self.frames_per_second * self.interval_seconds


class VideoRecorder:
    """An open encoder, taking one frame at a time."""

    def __init__(self, settings: VideoSettings) -> None:
        """Start the encoder.

        Args:
            settings: Where and how to record.

        Raises:
            FileNotFoundError: If the encoder is not installed.
        """
        settings.path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.frames = 0
        """How many frames were written."""
        self._process = subprocess.Popen(
            [
                ENCODER,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{settings.width}x{settings.height}",
                "-r",
                str(settings.frames_per_second),
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                # Chroma subsampling every player understands. Without it the
                # file plays in ffplay and in almost nothing else.
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                str(settings.path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def write(self, frame: NDArray[np.uint8]) -> None:
        """Write one rendered frame.

        Args:
            frame: Height by width by three bytes, as the renderer produced it.
                Nothing is drawn on it and nothing is composited into it.
        """
        if self._process.stdin is None:
            return
        self._process.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
        self.frames += 1

    def close(self) -> None:
        """Finish the file and wait for the encoder."""
        if self._process.stdin is not None:
            self._process.stdin.close()
        self._process.wait(timeout=120)


def available() -> bool:
    """Whether an encoder is installed here."""
    return shutil.which(ENCODER) is not None


def open_recorder(settings: VideoSettings) -> VideoRecorder | None:
    """Start recording, or say there is no encoder.

    Args:
        settings: Where and how to record.

    Returns:
        The recorder, or None when `ffmpeg` is absent. A caller that gets None
        runs the scenario and reports that no video was recorded.
    """
    if not available():
        return None
    return VideoRecorder(settings)
