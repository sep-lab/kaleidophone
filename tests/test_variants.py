"""render/variants.py: teaser/thumbnail argv and the aspect-crop filters.

Pure string logic plus monkeypatched ffmpeg calls -- no subprocess, no media.
"""

from __future__ import annotations

import pytest

from kaleidophone.render import variants
from kaleidophone.render.variants import _aspect_crop_filter
from kaleidophone.timeline.schema import TeaserConfig


@pytest.fixture
def calls(monkeypatch):
    recorded: list[list[str]] = []
    monkeypatch.setattr(variants, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(variants, "run", lambda ffmpeg, args: recorded.append(args))
    return recorded


def _arg_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


# --- aspect crop ---------------------------------------------------------


def test_vertical_and_square_crops_are_fixed_social_sizes():
    assert _aspect_crop_filter("9:16") == "crop=ih*9/16:ih,scale=1080:1920"
    assert _aspect_crop_filter("1:1") == "crop=ih:ih,scale=1080:1080"


def test_16_9_teaser_keeps_the_masters_own_resolution():
    """Regression: this hardcoded scale=1280:720, so a brief rendering at 1080p
    got its 16:9 teaser silently downscaled to 720p -- a quality loss with
    nothing to indicate it happened."""
    assert _aspect_crop_filter("16:9", (1920, 1080)) == "scale=1920:1080"
    assert _aspect_crop_filter("16:9", (3840, 2160)) == "scale=3840:2160"


def test_16_9_defaults_to_720p_when_no_resolution_is_supplied():
    assert _aspect_crop_filter("16:9") == "scale=1280:720"


# --- extract_teaser ------------------------------------------------------


def test_extract_teaser_seeks_before_the_input_and_bounds_the_duration(calls, tmp_path):
    teaser = TeaserConfig(name="drop", duration=15.0, aspect="9:16")
    variants.extract_teaser("/tmp/master.mp4", teaser, 42.0, str(tmp_path))

    args = calls[0]
    assert args.index("-ss") < args.index("-i")  # fast seek: before the input
    assert _arg_after(args, "-ss") == "42.000"
    assert _arg_after(args, "-t") == "15.000"
    assert args[-1].endswith("drop.mp4")


def test_extract_teaser_passes_the_master_resolution_into_the_filter(calls, tmp_path):
    teaser = TeaserConfig(name="wide", duration=10.0, aspect="16:9")
    variants.extract_teaser("/tmp/master.mp4", teaser, 0.0, str(tmp_path), (1920, 1080))
    assert _arg_after(calls[0], "-vf") == "scale=1920:1080"


def test_extract_teaser_creates_the_output_directory(calls, tmp_path):
    out = tmp_path / "teasers" / "nested"
    variants.extract_teaser("/tmp/master.mp4", TeaserConfig(name="t"), 0.0, str(out))
    assert out.is_dir()


# --- extract_thumbnail ---------------------------------------------------


def test_extract_thumbnail_grabs_exactly_one_frame(calls, tmp_path):
    out = str(tmp_path / "thumb.jpg")
    variants.extract_thumbnail("/tmp/master.mp4", 12.5, out)

    args = calls[0]
    assert _arg_after(args, "-frames:v") == "1"
    assert _arg_after(args, "-ss") == "12.500"
    assert args[-1] == out
