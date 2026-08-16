"""Shared ffmpeg subprocess helpers, used across the package.

Everything here shells out to the system ffmpeg/ffprobe binaries rather than
depending on a Python video library -- see
docs/decisions/0002-deterministic-edit-engine.md. Helpers that are merely
*useful* (probe_duration, first_frame_png) degrade to None when the binary
isn't there; only the render path itself calls require_ffmpeg() and hard-fails.
"""

from __future__ import annotations

import os
import shutil
import subprocess


class FfmpegNotFound(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegNotFound(
            "ffmpeg was not found on PATH. kaleidophone renders through the system ffmpeg "
            "binary rather than a Python dependency -- install it (e.g. `brew install "
            "ffmpeg` or `apt install ffmpeg`) and try again."
        )
    return path


def run(ffmpeg: str, args: list[str]) -> None:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (args tail: {' '.join(args[-6:])}):\n{proc.stderr[-2000:]}")


def first_frame_png(path: str) -> bytes | None:
    """The first decodable frame of a video, as PNG bytes, or None.

    Used by asset curation and the contact-sheet preview to look at a clip
    without pulling in a second video-decoding stack -- ffmpeg is already a
    hard requirement of the render path, so a ~90MB OpenCV wheel to read one
    frame was the more expensive of the two options. Returns None (rather than
    raising) when ffmpeg is absent or the file won't decode: both callers have
    a "couldn't read this one" path already, and neither should abort a scan
    of several hundred files over one bad clip.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    proc = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-i", os.path.abspath(path),
            "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def probe_duration(path: str) -> float | None:
    """Duration of a media file in seconds, or None if it can't be determined.

    Best-effort on purpose: ffprobe normally ships alongside ffmpeg but isn't
    guaranteed to, and nothing in the render path should hard-fail because a
    *diagnostic* couldn't run.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None
