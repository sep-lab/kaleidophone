"""Shared ffmpeg subprocess helpers for render.ffmpeg_pipeline and render.variants."""

from __future__ import annotations

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
