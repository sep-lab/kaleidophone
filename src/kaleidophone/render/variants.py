"""
Derive 9:16 teaser cutdowns and thumbnails from a rendered master.

Works on the rendered MP4 (not the EDL) via ffmpeg crop/trim -- simple,
robust, and consistent with treating the render as a cache: if a teaser
doesn't work, changing TeaserConfig and re-running costs seconds, not a
re-edit. See docs/decisions/0001-version-the-brief-not-the-render.md.
"""

from __future__ import annotations

import os

from kaleidophone.render._ffmpeg_util import require_ffmpeg, run
from kaleidophone.timeline.schema import TeaserConfig


def extract_teaser(master_path: str, teaser: TeaserConfig, start: float, out_dir: str) -> str:
    ffmpeg = require_ffmpeg()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{teaser.name}.mp4")

    run(
        ffmpeg,
        [
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            master_path,
            "-t",
            f"{teaser.duration:.3f}",
            "-vf",
            _aspect_crop_filter(teaser.aspect),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            out_path,
        ],
    )
    return out_path


def extract_thumbnail(master_path: str, timestamp: float, out_path: str) -> str:
    ffmpeg = require_ffmpeg()
    run(ffmpeg, ["-y", "-ss", f"{timestamp:.3f}", "-i", master_path, "-frames:v", "1", out_path])
    return out_path


def _aspect_crop_filter(aspect: str) -> str:
    if aspect == "9:16":
        return "crop=ih*9/16:ih,scale=1080:1920"
    if aspect == "1:1":
        return "crop=ih:ih,scale=1080:1080"
    return "scale=1280:720"  # 16:9 -- already the default brief's master aspect
