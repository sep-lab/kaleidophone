"""cover/generate.py: station-picking logic plus one end-to-end smoke test.

See the mvideo-cover-art skill and docs/decisions/0002 for why this is a
procedural render (no AI call, no network) -- pick_cover_station() is pure
logic and generate_cover() is cheap enough to run for real at a tiny size.
"""

from __future__ import annotations

from factories import make_analysis, make_brief, make_section, make_station
from PIL import Image

from mvideo.cover.generate import generate_cover, pick_cover_station
from mvideo.timeline.schema import OutputConfig


def test_pick_cover_station_uses_the_section_containing_the_loudest_instant():
    quiet, loud = make_station(name="quiet"), make_station(name="loud")
    sections = [
        make_section(name="A", start=0.0, end=5.0, station="quiet"),
        make_section(name="B", start=5.0, end=10.0, station="loud"),
    ]
    brief = make_brief(stations=[quiet, loud], sections=sections)
    analysis = make_analysis(duration=10.0, rms_times=(1.0, 7.0), rms_db=(-30.0, -5.0))

    assert pick_cover_station(brief, analysis).name == "loud"


def test_pick_cover_station_respects_an_explicit_override():
    quiet, loud = make_station(name="quiet"), make_station(name="loud")
    sections = [
        make_section(name="A", start=0.0, end=5.0, station="quiet"),
        make_section(name="B", start=5.0, end=10.0, station="loud"),
    ]
    brief = make_brief(stations=[quiet, loud], sections=sections, output=OutputConfig(cover_station="quiet"))
    analysis = make_analysis(duration=10.0, rms_times=(7.0,), rms_db=(-5.0,))  # loudest instant is in "loud"

    assert pick_cover_station(brief, analysis).name == "quiet"


def test_pick_cover_station_falls_back_to_the_first_section_with_no_rms_data():
    station = make_station(name="only")
    brief = make_brief(stations=[station], sections=[make_section(station="only")])
    analysis = make_analysis(duration=10.0, rms_db=(), rms_times=())

    assert pick_cover_station(brief, analysis).name == "only"


def test_generate_cover_writes_a_square_image_of_the_requested_size(tmp_path):
    analysis = make_analysis(
        duration=10.0,
        rms_db=tuple(float(-40 + i) for i in range(20)),
        rms_times=tuple(i * 0.5 for i in range(20)),
    )
    station = make_station(duotone=("#1a0f06", "#f2b25c"))
    out = tmp_path / "cover.jpg"

    generate_cover(analysis, station, str(out), size=64, bands=8, seed=0)

    with Image.open(out) as img:
        assert img.size == (64, 64)
