"""audio/wavemap.py: the PIL-only wave-map render. Fast enough to run for
real rather than mock -- no ffmpeg, no audio decode."""

from __future__ import annotations

from factories import make_analysis
from PIL import Image

from kaleidophone.audio.wavemap import render_wavemap


def test_render_wavemap_writes_an_image_of_the_requested_size(tmp_path):
    analysis = make_analysis(
        duration=10.0,
        beat_times=tuple(float(i) for i in range(11)),
        rms_db=tuple(float(-40 + i) for i in range(20)),
        rms_times=tuple(i * 0.5 for i in range(20)),
    )
    out = tmp_path / "wavemap.png"

    render_wavemap(analysis, str(out), width=200, height=60)

    with Image.open(out) as img:
        assert img.size == (200, 60)


def test_render_wavemap_handles_a_zero_duration_analysis_without_crashing(tmp_path):
    analysis = make_analysis(duration=0.0, beat_times=(), rms_db=(), rms_times=())
    out = tmp_path / "wavemap.png"

    render_wavemap(analysis, str(out), width=100, height=40)

    with Image.open(out) as img:
        assert img.size == (100, 40)


def test_render_wavemap_draws_section_markers_without_crashing(tmp_path):
    analysis = make_analysis(
        duration=10.0, beat_times=(0.0, 1.0, 2.0), rms_db=(-20.0, -10.0), rms_times=(0.0, 5.0)
    )
    out = tmp_path / "wavemap.png"

    render_wavemap(analysis, str(out), section_markers=[(2.0, "INTRO"), (6.0, "DROP")])

    with Image.open(out) as img:
        assert img.size == (1600, 360)  # the documented defaults
