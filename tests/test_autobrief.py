"""timeline/autobrief.py: default-mode section proposal and the
empty-station-avoidance fix documented in
docs/decisions/0004-default-mode-and-auto-curation.md.

analyze()/scan_media()/suggest_stations() are monkeypatched throughout so
this suite never decodes real audio or touches a real filesystem of media --
build_default_brief()'s own *logic* is what's under test, not librosa or
OpenCV.
"""

from __future__ import annotations

import pytest
from factories import make_analysis, make_media_asset

from kaleidophone.timeline import autobrief
from kaleidophone.timeline.autobrief import (
    DEFAULT_STATION_CYCLE,
    MAX_SECTIONS,
    MIN_SECTIONS,
    _drop_short_gaps,
    _guess_title,
    _propose_section_boundaries,
    _section_loudness,
    build_default_brief,
)


def test_guess_title_cleans_up_a_filename():
    assert _guess_title("/x/y/my_favorite-song.mp3") == "My Favorite Song"


def test_guess_title_falls_back_to_untitled_for_an_empty_stem():
    # os.path.splitext treats a leading dot as part of the name (dotfile
    # convention), not an extension separator -- ".mp3" alone splits to
    # stem=".mp3", not "". An actually-empty stem needs no filename at all.
    assert _guess_title("/x/y/") == "Untitled"


def test_section_loudness_is_normalized_0_to_1_against_the_songs_own_range():
    analysis = make_analysis(
        duration=10.0,
        rms_times=(0.0, 2.0, 4.0, 6.0, 8.0),
        rms_db=(-40.0, -40.0, -10.0, -10.0, -10.0),
    )
    quiet = _section_loudness(analysis, 0.0, 4.0)
    loud = _section_loudness(analysis, 4.0, 10.0)
    assert quiet == pytest.approx(0.0)
    assert loud == pytest.approx(1.0)


def test_section_loudness_defaults_to_the_midpoint_with_no_rms_data():
    analysis = make_analysis(duration=10.0, rms_db=(), rms_times=())
    assert _section_loudness(analysis, 0.0, 10.0) == 0.5


def test_drop_short_gaps_merges_close_candidates_but_keeps_the_true_end():
    boundaries = [0.0, 1.0, 1.5, 20.0]
    cleaned = _drop_short_gaps(boundaries, min_gap=4.0)
    assert cleaned[0] == 0.0
    assert cleaned[-1] == 20.0
    assert 1.5 not in cleaned


def test_propose_section_boundaries_falls_back_to_even_slicing_for_a_dynamically_flat_song():
    analysis = make_analysis(duration=120.0, quiet_passages=(), energy_jumps=())
    boundaries = _propose_section_boundaries(analysis)
    n_sections = len(boundaries) - 1
    assert MIN_SECTIONS <= n_sections <= MAX_SECTIONS
    assert boundaries[0] == 0.0
    assert boundaries[-1] == pytest.approx(120.0)


def test_build_default_brief_drops_stations_that_received_no_assets(monkeypatch):
    """Regression test for the exact bug documented in ADR-0004: when
    curation starves a candidate station down to zero assets,
    build_default_brief must never assign it a section (compose() would
    otherwise crash on it) -- it should drop the station entirely and cycle
    only through the ones that actually got something."""
    analysis = make_analysis(duration=40.0, quiet_passages=(), energy_jumps=())
    monkeypatch.setattr(autobrief, "analyze", lambda path, **kw: analysis)
    monkeypatch.setattr(
        autobrief, "scan_media", lambda directory: [make_media_asset(f"/m/{i}.jpg") for i in range(8)]
    )

    def starve_all_but_the_first(assets, stations):
        buckets = {s.name: [] for s in stations}
        buckets[stations[0].name] = list(assets)
        return buckets

    monkeypatch.setattr(autobrief, "suggest_stations", starve_all_but_the_first)

    brief, station_assets = build_default_brief("song.wav", "photos/")

    assert {s.station for s in brief.sections} == {DEFAULT_STATION_CYCLE[0]}
    assert set(station_assets) == {DEFAULT_STATION_CYCLE[0]}
    assert len(brief.stations) == 1  # the starved candidates never made it into the brief


def test_build_default_brief_keeps_every_station_that_received_assets(monkeypatch):
    analysis = make_analysis(duration=40.0, quiet_passages=(), energy_jumps=())
    monkeypatch.setattr(autobrief, "analyze", lambda path, **kw: analysis)
    assets = [make_media_asset(f"/m/{i}.jpg") for i in range(9)]
    monkeypatch.setattr(autobrief, "scan_media", lambda directory: assets)

    def split_evenly(assets, stations):
        buckets = {s.name: [] for s in stations}
        for i, a in enumerate(assets):
            buckets[stations[i % len(stations)].name].append(a)
        return buckets

    monkeypatch.setattr(autobrief, "suggest_stations", split_evenly)

    brief, station_assets = build_default_brief("song.wav", "photos/")

    assert len(brief.stations) == len(station_assets)
    assert all(station_assets[s.name] for s in brief.stations)
    assert {sec.station for sec in brief.sections} <= {s.name for s in brief.stations}


def test_build_default_brief_raises_a_clear_error_for_an_empty_media_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(autobrief, "analyze", lambda path, **kw: make_analysis(duration=40.0))
    monkeypatch.setattr(autobrief, "scan_media", lambda directory: [])

    with pytest.raises(ValueError, match="no photos or clips"):
        build_default_brief("song.wav", str(tmp_path))
