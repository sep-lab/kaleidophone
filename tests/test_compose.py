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

from kaleidophone.audio.analysis import EnergyJump
from kaleidophone.timeline.compose import (
    _BEAT_DIVISORS,
    _compose_section,
    _cut_boundaries,
    _effects_for_cut,
    compose,
)
from kaleidophone.timeline.schema import CutDensity


def test_beat_divisors_cover_every_cut_density_the_schema_allows():
    for density in typing.get_args(CutDensity):
        assert density in _BEAT_DIVISORS


# --- _cut_boundaries -------------------------------------------------------


def test_cut_boundaries_every_beat_uses_every_beat():
    analysis = make_analysis(duration=10.0, beat_times=tuple(float(i) for i in range(11)))  # 0..10
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")
    assert _cut_boundaries(section, analysis, 24) == [float(i) for i in range(11)]


def test_cut_boundaries_every_2_beats_skips_every_other_beat():
    analysis = make_analysis(duration=10.0, beat_times=tuple(float(i) for i in range(11)))
    section = make_section(start=0.0, end=10.0, cut_density="every_2_beats")
    assert _cut_boundaries(section, analysis, 24) == [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]


def test_cut_boundaries_static_is_one_cut_spanning_the_whole_section():
    analysis = make_analysis(duration=10.0, beat_times=tuple(float(i) for i in range(11)))
    section = make_section(start=2.0, end=8.0, cut_density="static")
    assert _cut_boundaries(section, analysis, 24) == [2.0, 8.0]


def test_cut_boundaries_pads_to_section_edges_when_no_beat_lands_exactly_on_them():
    beats = tuple(0.5 + i for i in range(10))  # 0.5 .. 9.5, never touching 0 or 10
    analysis = make_analysis(duration=10.0, beat_times=beats)
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")
    boundaries = _cut_boundaries(section, analysis, 24)
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
    boundaries = _cut_boundaries(section, analysis, 24)
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
        _compose_section(section, analysis, [], start_index=0, fps=24)


def test_compose_section_is_deterministic_and_matches_the_documented_seed_contract():
    """docs/decisions/0001 and the kaleidophone-timeline-compose skill both claim
    'same seed, same shuffle, same edit, every time' -- pin that against the
    actual random.Random(seed) contract, not just against itself twice."""
    analysis = make_analysis(duration=6.0, beat_times=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    assets = [make_media_asset(f"/media/{i}.jpg") for i in range(4)]
    section = make_section(start=0.0, end=6.0, cut_density="every_beat", seed=7)

    expected_pool = assets.copy()
    random.Random(7).shuffle(expected_pool)

    cuts = _compose_section(section, analysis, assets, start_index=0, fps=24)
    assert [c.source_path for c in cuts] == [
        expected_pool[i % len(expected_pool)].path for i in range(len(cuts))
    ]

    cuts_again = _compose_section(section, analysis, assets, start_index=0, fps=24)
    assert [c.source_path for c in cuts_again] == [c.source_path for c in cuts]


def test_compose_section_different_seeds_reorder_the_pool():
    analysis = make_analysis(duration=6.0, beat_times=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    assets = [make_media_asset(f"/media/{i}.jpg") for i in range(6)]
    section_a = make_section(start=0.0, end=6.0, cut_density="every_beat", seed=1)
    section_b = make_section(start=0.0, end=6.0, cut_density="every_beat", seed=2)

    cuts_a = _compose_section(section_a, analysis, assets, start_index=0, fps=24)
    cuts_b = _compose_section(section_b, analysis, assets, start_index=0, fps=24)
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


# --- the frame grid ------------------------------------------------------
#
# These pin the fix for the drift documented in docs/ARCHITECTURE.md,
# "Frame-accurate cuts": before boundaries were snapped, a 300s/640-cut render
# finished 3.25s short of its own audio, because every cut lost the fraction
# of a frame ffmpeg couldn't emit -- always in the same direction.


def _off_grid_beats(fps: int, count: int) -> tuple[float, ...]:
    """A beat grid deliberately landing between frames: 129 BPM at 24fps gives
    0.4651s per beat, which is 11.16 frames -- never a whole one."""
    interval = 60.0 / 129.0
    return tuple(round(i * interval, 6) for i in range(count))


@pytest.mark.parametrize("fps", [24, 25, 30, 60])
def test_every_cut_boundary_lands_on_a_whole_frame(fps):
    beats = _off_grid_beats(fps, 40)
    analysis = make_analysis(duration=20.0, beat_times=beats)
    section = make_section(start=0.0, end=18.0, cut_density="every_beat")

    for b in _cut_boundaries(section, analysis, fps):
        frames = b * fps
        assert frames == pytest.approx(round(frames), abs=1e-9), f"{b} is not a whole frame at {fps}fps"


def test_cut_durations_are_whole_frame_counts_so_concatenation_cannot_drift():
    """The actual property that keeps audio in sync: render_silent()
    concatenates segments, so if every duration is an exact frame count the
    running total is exact too."""
    fps = 24
    analysis = make_analysis(duration=60.0, beat_times=_off_grid_beats(fps, 130))
    station = make_station(name="s")
    section = make_section(name="A", start=0.0, end=55.0, station="s", cut_density="every_beat")
    brief = make_brief(stations=[station], sections=[section])
    edl = compose(brief, analysis, {"s": [make_media_asset("/media/0.jpg")]})

    assert len(edl.cuts) > 100  # enough cuts that any per-cut error would show
    for cut in edl.cuts:
        frames = cut.duration * fps
        assert frames == pytest.approx(round(frames), abs=1e-9)

    total = sum(round(c.duration * fps) for c in edl.cuts)
    assert total / fps == pytest.approx(edl.cuts[-1].end, abs=1e-9)


def test_the_frame_grid_follows_output_fps_and_is_not_hardcoded_to_24():
    """Regression: the near-duplicate collapse used a literal 1/24 regardless
    of the brief's own output.fps, so a 60fps brief silently kept boundaries
    that 60fps can actually resolve, and a 12fps one kept ones it can't."""
    # 0.01s past the top: inside half a frame at 24fps (so it snaps back onto
    # 0.0 and collapses), but a resolvable instant at 60fps.
    beats = (0.0, 0.01, 5.0, 10.0)
    analysis = make_analysis(duration=10.0, beat_times=beats)
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")

    at_24 = _cut_boundaries(section, analysis, 24)
    at_60 = _cut_boundaries(section, analysis, 60)

    assert at_24 == [0.0, 5.0, 10.0]  # the 0.01 beat collapsed onto 0.0
    assert at_60 == [0.0, 1 / 60, 5.0, 10.0]  # 60fps keeps it, on its own frame

    # And the grid itself scales: a beat that is not a whole frame at either
    # rate snaps to a different instant depending on output.fps.
    off = make_analysis(duration=10.0, beat_times=(0.0, 0.3, 10.0))
    assert _cut_boundaries(section, off, 24)[1] == pytest.approx(7 / 24)
    assert _cut_boundaries(section, off, 60)[1] == pytest.approx(18 / 60)


def test_a_section_with_no_detected_beats_falls_back_to_the_tempo_grid(capsys):
    """Regression: librosa returns no beats at all for a quiet passage -- it
    finds none in the first 11s of this repo's own demo song. A section asking
    for every_2_beats used to silently become ONE cut spanning the whole
    section, contradicting cut_density's documented meaning with nothing said.
    """
    analysis = make_analysis(duration=20.0, bpm=120.0, beat_times=(12.0, 12.5, 13.0, 13.5))
    section = make_section(name="QUIET", start=0.0, end=8.0, cut_density="every_2_beats")

    boundaries = _cut_boundaries(section, analysis, 24)

    # 120 BPM over 8s is 16 beats; every_2_beats halves that.
    assert len(boundaries) == 9, boundaries
    assert boundaries[0] == 0.0
    assert boundaries[-1] == 8.0
    assert "no beats detected" in capsys.readouterr().err


def test_the_tempo_grid_fallback_still_lands_on_the_frame_grid():
    analysis = make_analysis(duration=20.0, bpm=129.0, beat_times=(15.0,))
    section = make_section(start=0.0, end=10.0, cut_density="every_beat")
    for b in _cut_boundaries(section, analysis, 24):
        assert b * 24 == pytest.approx(round(b * 24), abs=1e-9)


def test_a_section_shorter_than_one_frame_is_refused_rather_than_rendered_empty():
    analysis = make_analysis(duration=10.0)
    section = make_section(start=1.0, end=1.01, cut_density="every_beat")  # 0.01s < 1/24
    with pytest.raises(ValueError, match="shorter than one frame"):
        _cut_boundaries(section, analysis, 24)
