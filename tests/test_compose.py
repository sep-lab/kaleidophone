"""timeline/compose.py: cut-boundary math, conditional effects, and the
determinism the whole "cheap re-render" workflow depends on.

See docs/decisions/0001-version-the-brief-not-the-render.md: compose() must
be a pure function of (brief, analysis, station_assets) -- same inputs, same
seed, same edit, every time.
"""

from __future__ import annotations

import random
import typing

import pytest
from factories import make_analysis, make_brief, make_media_asset, make_section, make_station

from mvideo.audio.analysis import EnergyJump
from mvideo.timeline.compose import (
    _BEAT_DIVISORS,
    _compose_section,
    _cut_boundaries,
    _effects_for_cut,
    compose,
)
from mvideo.timeline.schema import CutDensity


def test_beat_divisors_cover_every_cut_density_the_schema_allows():
    for density in typing.get_args(CutDensity):
        assert density in _BEAT_DIVISORS


# --- _cut_boundaries -------------------------------------------------------


def test_cut_boundaries_every_beat_uses_every_beat():
    analysis = make_analysis(duration=10.0, beat_times=tuple(float(i) for i in range(11)))  # 0..10
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")
    assert _cut_boundaries(section, analysis) == [float(i) for i in range(11)]


def test_cut_boundaries_every_2_beats_skips_every_other_beat():
    analysis = make_analysis(duration=10.0, beat_times=tuple(float(i) for i in range(11)))
    section = make_section(start=0.0, end=10.0, cut_density="every_2_beats")
    assert _cut_boundaries(section, analysis) == [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]


def test_cut_boundaries_static_is_one_cut_spanning_the_whole_section():
    analysis = make_analysis(duration=10.0, beat_times=tuple(float(i) for i in range(11)))
    section = make_section(start=2.0, end=8.0, cut_density="static")
    assert _cut_boundaries(section, analysis) == [2.0, 8.0]


def test_cut_boundaries_pads_to_section_edges_when_no_beat_lands_exactly_on_them():
    beats = tuple(0.5 + i for i in range(10))  # 0.5 .. 9.5, never touching 0 or 10
    analysis = make_analysis(duration=10.0, beat_times=beats)
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")
    boundaries = _cut_boundaries(section, analysis)
    assert boundaries[0] == 0.0
    assert boundaries[-1] == 10.0


def test_cut_boundaries_never_drops_the_sections_true_end():
    """Regression test: a beat-derived boundary 0.01s before the section end
    is inside one 24fps frame (~0.0417s) of the previous kept boundary. The
    near-duplicate collapse must snap onto the section's true end rather
    than silently truncating it -- see CHANGELOG.md's Fixed entry."""
    beats = (0.0, 5.0, 9.99, 10.0)
    analysis = make_analysis(duration=10.0, beat_times=beats)
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")
    boundaries = _cut_boundaries(section, analysis)
    assert boundaries[0] == 0.0
    assert boundaries[-1] == 10.0
    assert 9.99 not in boundaries


# --- _effects_for_cut --------------------------------------------------


def test_kaleidoscope_only_fires_every_7th_cut_after_the_first():
    analysis = make_analysis(duration=20.0)
    section = make_section(effects=["kaleidoscope"])
    assert _effects_for_cut(section, 0, analysis, 0.0, 1.0) == []  # cut 0 is exempt even though 0 % 7 == 0
    assert _effects_for_cut(section, 3, analysis, 3.0, 4.0) == []
    assert _effects_for_cut(section, 7, analysis, 7.0, 8.0) == ["kaleidoscope"]
    assert _effects_for_cut(section, 14, analysis, 14.0, 15.0) == ["kaleidoscope"]


def test_freeze_on_peak_only_fires_on_cuts_containing_an_energy_jump():
    analysis = make_analysis(
        duration=20.0, energy_jumps=(EnergyJump(time=5.0, onset_strength=1.0, z_score=3.0),)
    )
    section = make_section(effects=["freeze_on_peak"])
    assert _effects_for_cut(section, 0, analysis, 4.0, 6.0) == ["freeze_on_peak"]
    assert _effects_for_cut(section, 0, analysis, 6.0, 8.0) == []


def test_strobe_only_fires_on_cuts_containing_an_onset():
    analysis = make_analysis(duration=20.0, onset_times=(5.0,))
    section = make_section(effects=["strobe"])
    assert _effects_for_cut(section, 0, analysis, 4.0, 6.0) == ["strobe"]
    assert _effects_for_cut(section, 0, analysis, 6.0, 8.0) == []


def test_section_wide_effects_apply_to_every_cut_regardless_of_index_or_timing():
    analysis = make_analysis(duration=20.0)
    section = make_section(effects=["grain", "vignette", "halation"])
    assert _effects_for_cut(section, 0, analysis, 0.0, 1.0) == ["grain", "vignette", "halation"]
    assert _effects_for_cut(section, 99, analysis, 999.0, 1000.0) == ["grain", "vignette", "halation"]


# --- _compose_section / compose -----------------------------------------


def test_compose_section_raises_a_clear_error_when_no_assets_were_curated():
    analysis = make_analysis(duration=10.0)
    section = make_section(start=0.0, end=10.0, station="empty-station")
    with pytest.raises(ValueError, match="empty-station"):
        _compose_section(section, analysis, [], start_index=0)


def test_compose_section_is_deterministic_and_matches_the_documented_seed_contract():
    """docs/decisions/0001 and the mvideo-timeline-compose skill both claim
    'same seed, same shuffle, same edit, every time' -- pin that against the
    actual random.Random(seed) contract, not just against itself twice."""
    analysis = make_analysis(duration=6.0, beat_times=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    assets = [make_media_asset(f"/media/{i}.jpg") for i in range(4)]
    section = make_section(start=0.0, end=6.0, cut_density="every_beat", seed=7)

    expected_pool = assets.copy()
    random.Random(7).shuffle(expected_pool)

    cuts = _compose_section(section, analysis, assets, start_index=0)
    assert [c.source_path for c in cuts] == [
        expected_pool[i % len(expected_pool)].path for i in range(len(cuts))
    ]

    cuts_again = _compose_section(section, analysis, assets, start_index=0)
    assert [c.source_path for c in cuts_again] == [c.source_path for c in cuts]


def test_compose_section_different_seeds_reorder_the_pool():
    analysis = make_analysis(duration=6.0, beat_times=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    assets = [make_media_asset(f"/media/{i}.jpg") for i in range(6)]
    section_a = make_section(start=0.0, end=6.0, cut_density="every_beat", seed=1)
    section_b = make_section(start=0.0, end=6.0, cut_density="every_beat", seed=2)

    cuts_a = _compose_section(section_a, analysis, assets, start_index=0)
    cuts_b = _compose_section(section_b, analysis, assets, start_index=0)
    assert [c.source_path for c in cuts_a] != [c.source_path for c in cuts_b]


def test_compose_indexes_cuts_continuously_across_sections_with_no_gaps():
    beat_times = tuple(float(i) for i in range(21))  # 0..20, one beat/sec
    analysis = make_analysis(duration=20.0, beat_times=beat_times)
    station = make_station(name="only-station")
    sections = [
        make_section(name="A", start=0.0, end=10.0, station="only-station", cut_density="every_beat"),
        make_section(name="B", start=10.0, end=20.0, station="only-station", cut_density="every_2_beats"),
    ]
    brief = make_brief(stations=[station], sections=sections)
    assets = [make_media_asset(f"/media/{i}.jpg") for i in range(3)]

    edl = compose(brief, analysis, {"only-station": assets})

    assert [c.index for c in edl.cuts] == list(range(len(edl.cuts)))
    assert edl.cuts[0].section == "A"
    assert edl.cuts[-1].section == "B"
    assert all(c.station == "only-station" for c in edl.cuts)
    # EDL.__post_init__ already raises on any overlap -- reaching this line
    # is itself proof compose() produced a non-overlapping timeline.


def test_compose_raises_when_a_section_points_at_a_station_missing_from_station_assets():
    analysis = make_analysis(duration=10.0)
    station = make_station(name="only-station")
    section = make_section(station="only-station", start=0.0, end=10.0)
    brief = make_brief(stations=[station], sections=[section])
    with pytest.raises(ValueError, match="only-station"):
        compose(brief, analysis, {})  # station_assets missing the key entirely
