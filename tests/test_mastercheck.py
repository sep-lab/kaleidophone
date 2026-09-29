"""audio/mastercheck.py: is a new master a drop-in for the picture?

Two synthetic "masters" per test -- a groove, a bass line that changes every
bar, and a harmonic "voice" in some bars, all procedural -- run through
compare_signals(). Then each stage on its own, against hand-built envelopes
and hand-built lag windows, so the verdict logic is pinned directly rather
than only through whatever a synthetic song happens to produce.

Nothing is decoded; master_check()'s ffmpeg decode is stubbed. The cases are
the ones the technique was built for -- an identical grid (remux), a bar
where something new sounds (rerender that bar), a master that is only louder
(still remux), a tempo change, the loop that lines up with itself a whole
number of beats away -- and the ones the 0.3 review added: a head trimmed or
padded (offset, with the silent_start to use), a shift inside half a frame
(remux), an insertion at the head (new grid), a varispeed (the same material
faster), every hi-hat removed (a piece reading the highs would sparkle to
nothing: rerender), a vocal moved a bar on an unchanged beat, and an added
outro that must not read as a different take.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from kaleidophone.audio import mastercheck as mc

SR = 48000
BPM = 120.0
BAR = 4 * 60.0 / BPM
FIRST = 0.5  # the synthetic songs' first downbeat
GIVEN = {"bpm": BPM, "downbeat": FIRST}


# --------------------------------------------------------------------------
# synthetic masters
# --------------------------------------------------------------------------
def _add(x: np.ndarray, sound: np.ndarray, t: float, gain: float) -> None:
    i = round(t * SR)
    n = min(len(sound), len(x) - i)
    if n > 0:
        x[i : i + n] += gain * sound[:n]


def song(
    dur: float = 40.0, vocal_bars=(2, 3, 4, 5, 10, 11, 12, 13), seed: int = 3, hats: bool = True
) -> np.ndarray:
    """Kick/snare/hats at 120 BPM from 0.5 s, a random bass note per bar and a
    vibrato 'voice' (random pitch per beat) in `vocal_bars` (0-based). The
    random draws happen in the same order whatever `vocal_bars` and `hats`
    are, so two songs with one seed differ only where asked."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(dur * SR))
    beat = 60.0 / BPM
    t = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t / 0.025)) / SR) * np.exp(-t / 0.12)
    for k, b in enumerate(np.arange(FIRST, dur - 0.5, beat)):
        if k % 2 == 0:
            _add(x, kick, b, 0.7)
        else:
            _add(x, rng.standard_normal(int(0.1 * SR)) * np.exp(-np.arange(int(0.1 * SR)) / 2400), b, 0.4)
        for half in (0.0, beat / 2):
            hat = rng.standard_normal(int(0.03 * SR)) * np.exp(-np.arange(int(0.03 * SR)) / 500)
            if hats:
                _add(x, hat, b + half, 0.08)
    for k in range(int(dur / BAR)):
        f = rng.choice([41.2, 49.0, 55.0, 61.7, 65.4])
        tt = np.arange(int(BAR * SR)) / SR
        _add(x, np.sin(2 * np.pi * f * tt) * np.minimum(1, tt / 0.01), FIRST + k * BAR, 0.25)
    for k in vocal_bars:
        for j in range(4):
            f0 = rng.choice([220, 247, 262, 294, 330, 392])
            tt = np.arange(int(beat * 0.9 * SR)) / SR
            phase = 2 * np.pi * np.cumsum(f0 * (1 + 0.01 * np.sin(2 * np.pi * 5 * tt))) / SR
            voice = sum(np.sin(h * phase) / h for h in range(1, 6)) * np.minimum(1, tt / 0.03)
            _add(x, voice * np.minimum(1, (tt[-1] - tt) / 0.05), FIRST + k * BAR + j * beat, 0.15)
    return x.astype(np.float32)


@pytest.fixture(scope="module")
def old():
    return song()


def burst(dur: float, start: float, length: float, freq: float = 800.0) -> np.ndarray:
    """A smooth-edged tone in the vocal band -- something new that sounds."""
    x = np.zeros(int(dur * SR), dtype=np.float32)
    tt = np.arange(int(length * SR)) / SR
    edges = np.minimum(1, tt / 0.02) * np.minimum(1, (tt[-1] - tt) / 0.02)
    _add(x, 0.2 * np.sin(2 * np.pi * freq * tt) * edges, start, 1.0)
    return x


def delayed(x: np.ndarray, seconds: float) -> np.ndarray:
    """`x` starting `seconds` later (silence in front), or earlier (head cut)."""
    n = round(abs(seconds) * SR)
    return np.concatenate([np.zeros(n, dtype=np.float32), x]) if seconds >= 0 else x[n:].copy()


def faster(x: np.ndarray, ratio: float) -> np.ndarray:
    """Played `ratio` times as fast, pitch and all -- a varispeed."""
    return np.interp(np.arange(0, len(x) - 1, ratio), np.arange(len(x)), x).astype(np.float32)


def limited(x: np.ndarray, drive_db: float = 6.0, ceiling: float = 0.9) -> np.ndarray:
    """A plain look-ahead limiter: `drive_db` louder, the gain held down for
    50 ms around every peak that would cross `ceiling`, smoothed over 10 ms."""
    from scipy.ndimage import maximum_filter1d

    y = x.astype(np.float64) / np.max(np.abs(x)) * 0.89 * 10 ** (drive_db / 20)
    held = maximum_filter1d(np.abs(y), size=int(0.05 * SR))
    target = np.minimum(1.0, ceiling / np.maximum(held, 1e-9))
    gain = np.convolve(target, np.ones(int(0.01 * SR)) / int(0.01 * SR), mode="same")
    return (y * np.minimum(gain, target)).astype(np.float32)


def _texture(n: int = 3000, seed: int = 0) -> np.ndarray:
    """A level envelope with detail but no long memory -- unlike a random
    walk, two of these are unrelated at any lag."""
    noise = np.random.default_rng(seed).standard_normal(n)
    return -40.0 + 10.0 * np.convolve(noise, np.ones(5) / 5, mode="same")


@pytest.fixture(scope="module")
def identical(old):
    return mc.compare_signals(old, old.copy(), SR)


# --------------------------------------------------------------------------
# the verdicts, end to end
# --------------------------------------------------------------------------
def test_an_identical_master_is_a_remux(identical):
    check = identical
    assert check.verdict == "remux"
    assert check.exit_code == mc.EXIT_REMUX == 0
    assert all(w.lag == 0.0 for w in check.windows if w.lag is not None)
    assert check.offset == 0.0 and check.new_silent_start == 0.0
    assert not any(b.changed for b in check.bars)
    assert all(s.vocal_r == pytest.approx(1.0) for s in check.sections if s.vocal_r is not None)
    assert check.detail == "remux: same grid, no bar changed"


def test_the_exit_codes_are_distinct_and_leave_1_and_2_to_the_cli():
    codes = [mc.EXIT_REMUX, mc.EXIT_RERENDER, mc.EXIT_NEW_GRID, mc.EXIT_OFFSET]
    assert codes == [0, 3, 4, 5]


def test_the_grid_is_estimated_from_the_old_master(identical):
    grid = identical.grid
    assert grid.bpm == pytest.approx(BPM, abs=0.05)
    assert grid.downbeat == pytest.approx(FIRST, abs=0.02)
    assert grid.source == "estimated from the old master"
    assert grid.confidence is not None


def test_a_master_padded_by_half_a_second_is_an_offset_with_its_silent_start(old):
    """A new head of silence moves nothing but where the song starts in the
    file: the delivery sheet's silent_start absorbs it, no render needed."""
    check = mc.compare_signals(old, delayed(old, 0.5), SR)
    assert check.verdict == "offset"
    assert check.exit_code == mc.EXIT_OFFSET == 5
    assert check.offset == pytest.approx(0.5, abs=0.001)
    assert check.new_silent_start == pytest.approx(0.5, abs=0.001)
    assert "silent_start to 0.5 (was 0)" in check.detail
    assert check.bars and not any(b.changed for b in check.bars)  # compared after aligning


def test_a_trimmed_head_is_a_negative_offset_added_to_the_current_silent_start(old):
    check = mc.compare_signals(old, delayed(old, -0.3), SR, silent_start=1.0, **GIVEN)
    assert check.verdict == "offset"
    assert check.offset == pytest.approx(-0.3, abs=0.001)
    assert check.new_silent_start == pytest.approx(0.7, abs=0.001)
    assert "sits 0.300 s earlier" in check.detail and "(was 1)" in check.detail


def test_an_offset_is_measured_to_the_sample_not_the_envelope_frame(old):
    check = mc.compare_signals(old, delayed(old, 0.2345), SR, **GIVEN)
    assert check.offset == pytest.approx(0.2345, abs=0.0005)


def test_a_shift_inside_half_a_frame_is_the_same_grid_and_the_tolerance_is_settable(old):
    """15 ms is inside half a frame at 24 fps: the picture is on the right
    frame. The report still says how to make it exact."""
    new = delayed(old, 0.015)[: len(old)]
    check = mc.compare_signals(old, new, SR, **GIVEN)
    assert check.verdict == "remux"
    assert check.offset == pytest.approx(0.015, abs=0.001)
    assert "inside the +-0.021 s tolerance" in check.detail
    strict = mc.compare_signals(old, new, SR, tolerance=0.010, **GIVEN)
    assert strict.verdict == "offset" and strict.exit_code == 5


def test_new_material_before_the_first_note_is_an_insertion_not_an_offset(old):
    """Two bars of something new in front: everything after it moved by two
    bars, but the head is music, not silence -- the picture needs a new start."""
    intro = song(dur=2 * BAR, vocal_bars=(), seed=11)
    check = mc.compare_signals(old, np.concatenate([intro, old]), SR, **GIVEN)
    assert check.verdict == "new grid" and check.exit_code == 4
    assert check.offset == pytest.approx(2 * BAR, abs=0.02)
    assert "insertion at the head" in check.detail and "+4.00 s" in check.detail
    assert check.bars == ()  # bars can't be compared across a moved grid


def test_music_cut_from_the_head_is_a_new_grid(old):
    check = mc.compare_signals(old, delayed(old, -2.0), SR, **GIVEN)
    assert check.verdict == "new grid"
    assert "cut at the head" in check.detail


def test_a_new_tone_in_one_bar_flags_that_bar_and_no_other(old):
    bar = 8  # 1-based: bar 1 starts at the downbeat
    start = FIRST + (bar - 1) * BAR
    check = mc.compare_signals(old, old + burst(40.0, start, BAR), SR, **GIVEN)
    assert check.verdict == "rerender"
    assert check.exit_code == mc.EXIT_RERENDER == 3
    assert check.changed_ranges == [(bar, bar)]
    assert check.detail.startswith("rerender bar 8 (00:14.50-00:16.50): ")
    flagged = next(b for b in check.bars if b.changed)
    assert flagged.new_voice > mc.NEW_VOICE_THRESHOLD
    assert flagged.start == pytest.approx(start, abs=0.01)
    assert "mid" in flagged.envelopes


def test_a_new_vocal_line_across_bars_is_one_range(old):
    new = song(vocal_bars=(2, 3, 4, 5, 10, 11, 12, 13, 15, 16, 17))
    check = mc.compare_signals(old, new, SR, **GIVEN)
    assert check.verdict == "rerender"
    assert check.changed_ranges == [(16, 18)]


def test_a_master_that_is_only_louder_and_harder_limited_is_still_a_remux(old):
    """6 dB hotter through a peak limiter: every band sits somewhere else on
    its own scale, and the comparison on the old master's scale sees through it."""
    normal = (old / np.max(np.abs(old)) * 0.89).astype(np.float32)
    check = mc.compare_signals(normal, limited(normal), SR, **GIVEN)
    assert check.verdict == "remux", check.detail


def test_removing_every_hat_is_a_rerender_for_a_piece_that_reads_the_highs(old):
    """The review's case: nothing a vocal-band check hears, but a piece driven
    by air or hflux would sparkle to hats that are gone."""
    check = mc.compare_signals(old, song(hats=False), SR, **GIVEN)
    assert check.verdict == "rerender"
    assert len(check.changed_ranges) == 1 and check.changed_ranges[0][1] - check.changed_ranges[0][0] >= 15
    changed = {key for b in check.bars for key in b.envelopes}
    assert {"air", "hflux"} & changed
    assert not {"voc", "bass", "bflux"} & changed


def test_envelopes_narrows_the_check_to_what_the_piece_reads(old):
    check = mc.compare_signals(old, song(hats=False), SR, envelopes=("bass", "mid", "rms"), **GIVEN)
    assert check.verdict == "remux"
    assert set(check.bars[3].detail) == {"bass", "mid", "rms"}


def test_a_vocal_moved_on_an_unchanged_beat_says_so_instead_of_a_different_take(old):
    moved = song(vocal_bars=(4, 5, 6, 7, 12, 13, 14, 15))  # every vocal bar two bars (4 s) later
    check = mc.compare_signals(old, moved, SR, **GIVEN)
    assert check.offset == pytest.approx(0.0, abs=0.01)  # the beat didn't move
    assert check.vocal_lag == pytest.approx(4.0, abs=0.02) and check.vocal_r >= 0.8
    assert any(note.startswith("vocal moved +4.00 s (r ") for note in check.notes)
    assert not any("different take" in note for note in check.notes)


def test_an_added_outro_is_new_picture_past_the_end_not_a_different_take(old):
    check = mc.compare_signals(old, np.concatenate([old, old[-8 * SR :]]), SR, **GIVEN)
    assert check.verdict == "rerender"
    assert check.changed_ranges[0][0] >= 19 and check.changed_ranges[-1][1] >= 23
    assert any("past the old one's end" in note for note in check.notes)
    assert not any("take" in note for note in check.notes)


def test_a_tempo_change_reads_as_the_same_material_faster():
    """The speed is found to about 0.01% (a stretched alignment of the level
    envelope); on this 40 s loop 1% reads 1.0101."""
    base = song(dur=40.0)
    check = mc.compare_signals(base, faster(base, 1.01), SR, **GIVEN)
    assert check.verdict == "new grid"
    assert check.tempo_ratio == pytest.approx(1.01, abs=0.0003)
    assert "% faster, 121.2" in check.diagnosis and "BPM against 120.00" in check.diagnosis
    assert "% faster, 121.2" in check.detail


def test_a_varispeed_of_a_loop_is_the_same_material_faster_not_one_shift(old):
    """6% faster: past the windows' reach within half a minute, and a loop's
    level envelope lines up with itself anyway. The onsets don't -- and the
    stretch that brings them back is the answer."""
    check = mc.compare_signals(old, faster(old, 1.06), SR, **GIVEN)
    assert check.verdict == "new grid"
    assert check.tempo_ratio == pytest.approx(1.06, abs=0.002)
    assert "% faster" in check.detail and "BPM against 120.00" in check.detail


def test_changed_bars_on_a_shifted_master_are_a_rerender_that_still_gives_the_silent_start(old):
    start = FIRST + 7 * BAR
    check = mc.compare_signals(old, delayed(old + burst(40.0, start, BAR), 0.3), SR, **GIVEN)
    assert check.verdict == "rerender" and check.changed_ranges == [(8, 8)]
    assert check.detail.endswith("set the delivery sheet's silent_start to 0.3 (was 0)")


def test_a_shift_the_onsets_do_not_confirm_is_kept_but_flagged(old, monkeypatch):
    """No stretch explains onsets that don't meet: the shift stands, and the
    report says the rhythm itself changed or the shift is wrong."""
    monkeypatch.setattr(mc, "onset_alignment", lambda *a, **k: 0.1)
    monkeypatch.setattr(mc, "tempo_change", lambda *a, **k: None)
    check = mc.compare_signals(old, old.copy(), SR, **GIVEN)
    assert check.verdict == "remux"
    assert any(note.startswith("the onsets correlate only r 0.10 at this shift") for note in check.notes)


def test_a_whole_bar_of_new_intro_on_a_loop_is_caught_song_wide(old):
    """Two bars earlier is 8 beats: every 8 s window can line the loop up with
    itself. The song as a whole can't -- and the head is new music."""
    intro = old[round(FIRST * SR) : round((FIRST + 2 * BAR) * SR)]
    check = mc.compare_signals(old, np.concatenate([intro, old]), SR, **GIVEN)
    assert check.verdict == "new grid"
    assert check.offset == pytest.approx(2 * BAR, abs=0.02)
    assert "insertion at the head" in check.detail


def test_given_bpm_and_downbeat_are_used_exactly(old):
    check = mc.compare_signals(old, old, SR, bpm=119.991, downbeat=0.5)
    assert (check.grid.bpm, check.grid.downbeat, check.grid.source) == (119.991, 0.5, "given")
    assert check.grid.confidence is None and check.grid.octave is None


def test_a_given_bpm_alone_gets_its_downbeat_estimated(old):
    check = mc.compare_signals(old, old, SR, bpm=120.0)
    assert check.grid.bpm == 120.0
    assert check.grid.downbeat == pytest.approx(FIRST, abs=0.02)
    assert "downbeat estimated" in check.grid.source


def test_a_given_downbeat_alone_gets_its_tempo_estimated(old):
    check = mc.compare_signals(old, old, SR, downbeat=2.5)
    assert check.grid.downbeat == 2.5
    assert check.grid.bpm == pytest.approx(BPM, abs=0.05)
    assert "tempo estimated" in check.grid.source
    assert check.bars[0].bar <= 0  # bars before bar 1 are numbered down, not renumbered


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"bpm": 0.0}, "--bpm"),
        ({"downbeat": -1.0}, "--downbeat"),
        ({"beats_per_bar": 0}, "--beats-per-bar"),
        ({"tolerance": -0.001}, "--tolerance-ms"),
        ({"envelopes": ("bass", "sparkle")}, "--envelopes"),
        ({"envelopes": ()}, "--envelopes"),
    ],
)
def test_nonsense_arguments_are_refused(old, kwargs, match):
    with pytest.raises(ValueError, match=match):
        mc.compare_signals(old, old, SR, **kwargs)


# --------------------------------------------------------------------------
# 1. lags, on hand-built envelopes
# --------------------------------------------------------------------------
def _envelope(n: int = 3000, seed: int = 0) -> np.ndarray:
    """A log-RMS-like envelope: a random walk, so no stretch repeats."""
    return np.cumsum(np.random.default_rng(seed).standard_normal(n)) - 60.0


def test_local_lags_find_a_shift_in_every_window():
    a = _envelope()
    b = np.concatenate([np.full(37, -90.0), a])[: len(a)]
    windows = mc.local_lags(a, b)
    assert len(windows) == (3000 - 800) // 400 + 1
    assert all(w.lag == pytest.approx(0.37) for w in windows)


def test_local_lags_skip_a_flat_window_instead_of_guessing():
    a = np.concatenate([np.full(1200, -100.0), _envelope(1800)])
    windows = mc.local_lags(a, a)
    assert windows[0].lag is None and windows[0].r is None
    assert windows[-1].lag == 0.0


def test_local_lags_report_no_match_when_nothing_in_reach_correlates():
    a = _envelope(seed=1)
    b = _envelope(seed=2)
    windows = mc.local_lags(a, b)
    assert any(w.lag is None and w.r is not None for w in windows)


def test_a_small_real_shift_is_not_rounded_to_zero_by_the_tie_break():
    """Regression: near-ties were once taken from *every* lag, and on a smooth
    envelope the neighbours of the true peak always tie -- a 0.02 s shift
    read as 0.00, i.e. "same grid". Only separate peaks may tie."""
    a = _envelope()
    b = np.concatenate([np.full(2, -90.0), a])[: len(a)]
    assert all(w.lag == pytest.approx(0.02) for w in mc.local_lags(a, b))


def test_a_periodic_tie_goes_to_the_smallest_shift():
    """A loop correlates perfectly with itself a period away; 'nothing moved'
    is the explanation to prefer."""
    period = np.sin(np.linspace(0, 2 * np.pi, 50, endpoint=False)) * 10 - 50
    a = np.tile(period, 60)
    assert all(w.lag == 0.0 for w in mc.local_lags(a, a))


def test_local_lags_handle_a_song_shorter_than_one_window():
    a = _envelope(500)
    windows = mc.local_lags(a, a)
    assert len(windows) == 1 and windows[0].lag == 0.0


def test_global_offset_ignores_alignments_that_only_overlap_silence():
    a = np.concatenate([np.full(2000, -100.0), _envelope(2000)])
    lag, r = mc.global_offset(a, a)
    assert (lag, r) == (0.0, pytest.approx(1.0))


def test_global_offset_aligns_the_whole_song_beyond_the_window_search():
    a = _envelope(4000)
    b = np.concatenate([_envelope(400, seed=9), a])
    assert mc.global_offset(a, b) == (4.0, pytest.approx(1.0))


# --------------------------------------------------------------------------
# refining the shift, and telling a shift from a tempo change
# --------------------------------------------------------------------------
def _bursts(dur: float = 12.0, seed: int = 5) -> np.ndarray:
    """Noise bursts at random times: a sharp, unrepeating waveform."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(dur * SR))
    for t in np.sort(rng.uniform(0.2, dur - 0.5, 40)):
        _add(x, rng.standard_normal(int(0.08 * SR)) * np.exp(-np.arange(int(0.08 * SR)) / 800), t, 0.5)
    return x


def test_refine_lag_finds_the_shift_to_the_sample():
    x = _bursts()
    y = np.concatenate([np.zeros(123), x])  # 2.56 ms: a quarter of an envelope frame
    ex = mc.raw_envelopes(x.astype(np.float32), SR)["rms"]
    ey = mc.raw_envelopes(y.astype(np.float32), SR)["rms"]
    coarse, _ = mc.global_offset(ex, ey)
    assert mc.refine_lag(x, y, SR, ex, ey, coarse) == pytest.approx(123 / SR, abs=1e-4)


def test_refine_lag_keeps_the_envelope_answer_when_the_audio_does_not_match():
    """The same envelope with a scrambled waveform -- what a pitch shifter's
    output looks like to a waveform: no clear peak, so the envelope's answer
    stands."""
    x = _bursts(seed=5)
    shifted = np.concatenate([np.zeros(480), x])  # 10 ms later
    y = np.abs(shifted) * np.sign(np.random.default_rng(1).standard_normal(len(shifted)))
    ex = mc.raw_envelopes(x.astype(np.float32), SR)["rms"]
    ey = mc.raw_envelopes(y.astype(np.float32), SR)["rms"]
    coarse, _ = mc.global_offset(ex, ey)
    assert mc.refine_lag(x, y, SR, ex, ey, coarse) == pytest.approx(0.01, abs=0.006)


def test_refine_lag_keeps_the_envelope_answer_for_audio_too_short_to_refine():
    x = np.random.default_rng(0).standard_normal(2000)  # 42 ms: under two 1024-sample segments
    e = mc.raw_envelopes(x.astype(np.float32), SR)["rms"]
    assert mc.refine_lag(x, x, SR, e, e, 0.0) == 0.0


def test_onset_alignment_of_a_flat_envelope_is_zero():
    assert mc.onset_alignment(np.zeros(500), np.ones(500), 0.0) == 0.0


def test_phase_peak_needs_something_to_correlate():
    assert mc._phase_peak(np.zeros(2048), np.zeros(2248), 100) is None


def test_onset_alignment_is_high_only_where_the_onsets_meet():
    flux = np.zeros(2000)
    flux[np.arange(50, 2000, 50)] = 1.0
    shifted = np.concatenate([np.zeros(7), flux])[:2000]
    assert mc.onset_alignment(flux, shifted, 0.07) == pytest.approx(1.0)
    assert mc.onset_alignment(flux, shifted, 0.0) < 0.1
    assert mc.onset_alignment(flux, flux, 100.0) == 0.0  # nothing overlaps


def test_tempo_change_needs_a_guess_and_a_real_improvement():
    env = {"rms": _texture(3000), "flux": np.abs(np.random.default_rng(3).standard_normal(3000))}
    assert mc.tempo_change(env, env, [], (0.0, 30.0), (0.0, 0.0)) is None  # no length, no windows: no guess
    assert mc.tempo_change(env, env, [], (0.0, 30.0), (0.0, 30.0)) is None  # ratio 1 isn't a tempo change
    other = {"rms": _texture(3000, seed=4), "flux": env["flux"]}
    assert mc.tempo_change(env, other, [], (0.0, 30.0), (0.0, 28.0)) is None  # nothing lines up


def test_tempo_change_finds_a_stretched_envelope():
    a = _texture(3000)
    stretched = np.interp(np.arange(0, 2999, 1.05), np.arange(3000), a)  # 5% faster
    found = mc.tempo_change({"rms": a}, {"rms": stretched}, [], (0.0, 30.0), (0.0, 30.0 / 1.05))
    assert found is not None and found[0] == pytest.approx(1.05, abs=0.001)


def _loop(n: int = 3000, stretch: float = 1.0) -> np.ndarray:
    """A level envelope that repeats every second: it lines up with itself
    stretched a little, the way a looped groove does."""
    return -40.0 + 10.0 * np.sin(2 * np.pi * np.arange(0, n, stretch) / 100.0)


def test_a_loop_stretched_a_little_needs_its_onsets_to_call_it_a_tempo_change():
    """The levels of a loop line up nearly as well unstretched, so the
    stretch must be what brings the onsets into line -- and without onsets,
    or with onsets it doesn't align, it isn't called."""
    old, new = {"rms": _loop()}, {"rms": _loop(stretch=1.003)}
    audible = ((0.0, 30.0), (0.0, 30.0 / 1.003))
    assert mc.tempo_change(old, new, [], *audible) is None  # no onsets to decide with
    noise = np.abs(np.random.default_rng(2).standard_normal(3000))
    unrelated = {**new, "flux": np.abs(np.random.default_rng(3).standard_normal(3000))}
    assert mc.tempo_change({**old, "flux": noise}, unrelated, [], *audible) is None


def test_vocal_shift_stays_quiet_when_the_vocal_band_lines_up_with_the_mix():
    a = _texture(3000)
    assert mc.vocal_shift(a, a, 0.0) == (None, None)
    moved = np.concatenate([np.full(300, -100.0), a])
    lag, r = mc.vocal_shift(a, moved, 0.0)
    assert lag == pytest.approx(3.0) and r == pytest.approx(1.0)


# --------------------------------------------------------------------------
# classify_lags, on hand-built windows
# --------------------------------------------------------------------------
def _windows(lags) -> list[mc.LagWindow]:
    return [
        mc.LagWindow(start=4.0 * i, lag=lag, r=None if lag is None else 0.9) for i, lag in enumerate(lags)
    ]


def test_all_zero_and_no_song_wide_offset_is_one_shift():
    kind, why = mc.classify_lags(_windows([0.0, 0.01, None, 0.0]), 0.0)
    assert kind == "shift"
    assert "3/4 windows" in why and "1 without a confident match" in why


def test_no_confident_window_means_the_grid_cannot_be_confirmed():
    kind, why = mc.classify_lags(_windows([None, None]), 0.0)
    assert kind == "unconfirmed" and "can't be confirmed" in why


def test_one_matching_window_out_of_many_confirms_nothing():
    windows = _windows([0.0]) + [mc.LagWindow(start=4.0 * i, lag=None, r=0.1) for i in range(1, 12)]
    kind, why = mc.classify_lags(windows, 0.0, 0.5)
    assert kind == "unconfirmed" and "only 1 of 12 windows" in why


def test_zero_windows_under_a_song_wide_offset_are_a_whole_beat_offset():
    kind, why = mc.classify_lags(_windows([0.0] * 5), 2.0, 0.95)
    assert kind == "shift" and "whole beats" in why


def test_windows_agreeing_on_one_shift_are_a_whole_song_shift():
    kind, why = mc.classify_lags(_windows([0.5] * 9 + [-0.5]), 0.5, 0.99)
    assert kind == "shift" and "whole new master sits +0.50 s" in why


def test_steadily_growing_lags_are_a_tempo_change():
    lags = [round(-0.002 * 4.0 * i, 2) for i in range(10)] + [1.3]  # one window on the wrong beat
    kind, why = mc.classify_lags(_windows(lags), 0.0, 0.9, bpm=120.0)
    assert kind == "tempo"
    assert "tempo differs" in why and "faster" in why and "BPM against 120.00" in why


def test_lags_that_jump_partway_are_material_that_moved():
    kind, why = mc.classify_lags(_windows([0.0] * 5 + [1.0, -0.5, 1.0, 0.5]), 0.0, 0.7)
    assert kind == "moved"
    assert why.startswith("material moved inside the song from 20 s on")


# --------------------------------------------------------------------------
# 2. bars and sections, on hand-built envelopes
# --------------------------------------------------------------------------
GRID = mc.Grid(bpm=120.0, downbeat=0.0, beats_per_bar=4, source="given")


def _env(n: int, **levels) -> dict:
    """An envelope dict the way raw_envelopes() makes one: every key a piece
    reads, quiet unless given, plus the `vocal` band."""
    quiet = np.full(n, -60.0)
    out = {key: quiet.copy() for key in ("bass", "lowmid", "mid", "high", "air", "rms", "vocal")}
    out.update({key: np.zeros(n) for key in ("flux", "bflux", "hflux")})
    out["cent"] = np.full(n, 1000.0)
    for key, values in levels.items():
        out[key] = np.asarray(values, dtype=np.float64)
    return out


def test_bar_changes_measure_delta_and_new_voice_per_bar():
    vocal = np.full(1000, -60.0)
    vocal[::10] = -10.0  # something everywhere, so the percentiles have a range
    new_vocal = vocal.copy()
    new_vocal[400:600] = -10.0  # bar 3 (4-6 s): new sound where the old was quiet
    old, new = _env(1000, vocal=vocal, mid=vocal), _env(1000, vocal=new_vocal, mid=new_vocal)
    bars = mc.bar_changes(old, new, GRID)
    assert [b.bar for b in bars] == [1, 2, 3, 4, 5]
    assert [b.changed for b in bars] == [False, False, True, False, False]
    assert bars[2].new_voice == pytest.approx(0.9)
    assert bars[2].delta > mc.DELTA_THRESHOLD and bars[2].envelopes == ("mid",)
    assert bars[2].detail["mid"]["delta"] == bars[2].delta


def test_a_louder_master_is_the_same_on_the_old_masters_scale():
    rng = np.random.default_rng(0)
    mid = -40.0 + 10.0 * rng.standard_normal(1000)
    bars = mc.bar_changes(_env(1000, mid=mid), _env(1000, mid=mid + 6.0), GRID)
    assert not any(b.changed for b in bars)
    assert max(b.detail["mid"]["delta"] for b in bars) < 1e-9


def test_a_level_change_inside_the_tolerance_slide_is_not_a_change():
    rng = np.random.default_rng(2)
    mid = np.convolve(-40.0 + 10.0 * rng.standard_normal(1000), np.ones(5) / 5, mode="same")
    bars = mc.bar_changes(_env(1000, mid=mid), _env(1000, mid=np.roll(mid, 2)), GRID)
    assert max(b.detail["mid"]["delta"] for b in bars[1:-1]) < 0.02


def test_a_bar_whose_shape_changes_is_flagged_by_r_even_at_the_same_level():
    t = np.arange(1000)
    old_mid = -40.0 + 10.0 * np.sin(2 * np.pi * t / 50.0)
    new_mid = old_mid.copy()
    new_mid[200:400] = -40.0 + 10.0 * np.sin(2 * np.pi * t[200:400] / 50.0 + np.pi)  # bar 2, flipped
    bars = mc.bar_changes(_env(1000, mid=old_mid), _env(1000, mid=new_mid), GRID, max_delta=0.9)
    assert [b.bar for b in bars if b.changed] == [2]
    assert bars[1].detail["mid"]["r"] < mc.SHAPE_THRESHOLD


def test_rhythm_changes_are_read_per_sixteenth_and_silence_is_not_a_rhythm():
    old_flux = np.zeros(1000)
    old_flux[0:1000:25] = 1.0  # every 16th at 120 BPM
    new_flux = old_flux.copy()
    new_flux[200:400] = 0.0
    new_flux[200:400:50] = 1.0  # bar 2: 8ths instead of 16ths
    new_flux[600:800] = 0.0  # bar 4: silent in the new master only
    both_quiet = _env(1000)
    bars = mc.bar_changes(_env(1000, hflux=old_flux), _env(1000, hflux=new_flux), GRID)
    assert [b.bar for b in bars if b.changed] == [2, 4]
    assert bars[3].detail["hflux"]["r"] == 0.0
    assert bars[0].detail["hflux"]["r"] == pytest.approx(1.0)
    quiet = mc.bar_changes(both_quiet, both_quiet, GRID)
    assert all(b.detail["hflux"]["r"] is None for b in quiet)


def test_bar_changes_treat_a_longer_new_master_as_new_sound_past_the_old_end():
    vocal = np.tile([-60.0, -10.0], 300)
    new_vocal = np.tile([-60.0, -10.0], 500)
    bars = mc.bar_changes(_env(600, vocal=vocal, rms=vocal), _env(1000, vocal=new_vocal, rms=new_vocal), GRID)
    assert bars[-1].bar == 5 and bars[-1].changed
    assert not bars[0].changed


def test_thresholds_are_the_callers_to_tune():
    mid = np.tile([-60.0, -10.0], 500)
    new_mid = mid.copy()
    new_mid[200:400] += 3.0
    strict = mc.bar_changes(_env(1000, mid=mid), _env(1000, mid=new_mid), GRID, max_delta=0.01)
    loose = mc.bar_changes(
        _env(1000, mid=mid), _env(1000, mid=new_mid), GRID, max_delta=0.9, max_new_voice=0.9
    )
    assert any(b.changed for b in strict)
    assert not any(b.changed for b in loose)


def test_a_perfectly_even_rhythm_is_compared_by_its_value():
    """One onset in every 16th leaves a flat profile with no correlation to
    take: the same profile is unchanged, a louder one changed."""
    even = np.zeros(1000)
    even[np.round(np.arange(0.0, 10.0, 0.125) * mc.FPS).astype(int)] = 1.0
    same = mc.bar_changes(_env(1000, flux=even), _env(1000, flux=even.copy()), GRID)
    assert all(b.detail["flux"]["r"] == 1.0 for b in same)
    louder = mc.bar_changes(_env(1000, flux=even), _env(1000, flux=2.0 * even), GRID)
    assert all(b.detail["flux"]["r"] == 0.0 and b.changed for b in louder)


def test_bars_are_compared_after_aligning_by_the_shift():
    rng = np.random.default_rng(4)
    mid = -40.0 + 10.0 * rng.standard_normal(1000)
    new = np.concatenate([np.full(50, -60.0), mid])  # the same, 0.5 s later
    bars = mc.bar_changes(_env(1000, mid=mid), _env(1050, mid=new, rms=np.full(1050, -60.0)), GRID, 0.5)
    assert not any(b.changed for b in bars)


def test_sections_are_eight_bar_phrases_with_both_correlations():
    rng = np.random.default_rng(0)
    old = {"vocal": rng.standard_normal(4000) - 40, "rms": rng.standard_normal(4000) - 20}
    new = {"vocal": old["vocal"].copy(), "rms": rng.standard_normal(4000) - 20}
    sections = mc.section_matches(old, new, GRID)
    assert [(s.first_bar, s.last_bar) for s in sections] == [(1, 8), (9, 16), (17, 20)]
    assert all(s.vocal_r == pytest.approx(1.0) for s in sections)
    assert all(abs(s.mix_r) < 0.2 for s in sections)


def test_bars_before_bar_1_are_one_pickup_section():
    rng = np.random.default_rng(1)
    env = {"vocal": rng.standard_normal(4000) - 40, "rms": rng.standard_normal(4000) - 20}
    grid = mc.Grid(bpm=120.0, downbeat=5.0, beats_per_bar=4, source="given")
    sections = mc.section_matches(env, env, grid)
    assert [(s.first_bar, s.last_bar) for s in sections][:2] == [(-2, 0), (1, 8)]


def test_a_flat_or_silent_section_has_no_correlation_rather_than_a_fake_one():
    flat = {"vocal": np.full(1600, -100.0), "rms": np.full(1600, -100.0)}
    assert all(s.vocal_r is None and s.mix_r is None for s in mc.section_matches(flat, flat, GRID))
    sound = _texture(3200, seed=6)
    old = {
        "vocal": np.concatenate([sound[:1600], np.full(1600, -100.0)]),
        "rms": np.concatenate([sound[:1600], np.full(1600, -100.0)]),
    }
    new = {"vocal": sound, "rms": sound}
    first, second = mc.section_matches(old, new, GRID)
    assert first.mix_r == pytest.approx(1.0)
    assert second.mix_r is None and second.vocal_r is None  # the old master is silent there


def test_a_bar_that_starts_within_a_frame_of_the_end_is_skipped_not_measured_empty():
    grid = mc.Grid(bpm=120.0, downbeat=0.005, beats_per_bar=4, source="given")
    envelope = np.append(np.tile([-60.0, -10.0], 500), -60.0)  # 1001 frames: bar 6 would start at 10.005 s
    env = _env(1001, vocal=envelope, rms=envelope)
    bars = mc.bar_changes(env, env, grid)
    assert [b.bar for b in bars] == [0, 1, 2, 3, 4, 5]
    assert mc.section_matches(env, env, grid)[-1].last_bar == 6


def test_bar_numbers_before_the_downbeat_count_down_from_bar_1():
    grid = mc.Grid(bpm=120.0, downbeat=3.0, beats_per_bar=4, source="given")
    assert mc._bar_span(grid, 10.0) == (-1, 4)
    assert grid.bar_start(0) == 1.0 and grid.bar_seconds == 2.0


def test_ranges_merge_consecutive_bars():
    assert mc._ranges([5, 3, 4, 9, 10, 12]) == [(3, 5), (9, 10), (12, 12)]
    assert mc._describe_ranges([(3, 5), (12, 12)]) == "3-5, 12"


def test_head_changes_tell_an_insertion_or_a_cut_from_new_silence():
    assert mc._head_change((0.5, 90.0), (0.85, 90.35), 0.35, GRID) is None  # only silence moved
    assert "insertion at the head" in mc._head_change((0.5, 90.0), (0.5, 94.0), 4.0, GRID)
    assert "cut at the head" in mc._head_change((0.5, 90.0), (0.0, 88.0), -2.0, GRID)


def test_length_notes_say_what_runs_past_or_stops_short_of_the_picture():
    past = mc._length_notes((0.5, 100.0), (0.5, 108.0), 0.0, GRID)
    assert past[0].startswith("the new master runs 8.00 s past the old one's end (01:40.00): bars from 51 on")
    short = mc._length_notes((0.5, 100.0), (0.2, 96.0), 0.0, GRID)
    assert short[0].startswith("the new master ends 4.00 s before the old one did")
    assert mc._length_notes((0.5, 100.0), (0.85, 100.35), 0.35, GRID) == ()


def test_section_notes_read_the_two_correlations_together():
    def section(first, vocal_r, mix_r):
        return mc.SectionMatch(first, first + 7, 0.0, 16.0, vocal_r, mix_r)

    notes = mc._section_notes(
        (section(1, 0.3, 0.95), section(9, 0.9, 0.3), section(17, 0.2, 0.2), section(25, None, None))
    )
    assert "different take" in notes[0] and "1-8" in notes[0]
    assert notes[1].startswith("the arrangement changed in bars 9-16")
    assert notes[2].startswith("bars 17-24 changed throughout")
    assert len(mc._section_notes((section(1, 0.3, 0.95),), skip_vocal=True)) == 0


def test_grid_notes_say_when_an_estimated_grid_is_uncertain():
    sure = mc.Grid(
        bpm=80.0, downbeat=0.5, beats_per_bar=4, source="estimated", confidence=1.0, octave=(160.0, 0.5)
    )
    unsure = mc.Grid(
        bpm=160.0, downbeat=0.2, beats_per_bar=4, source="estimated", confidence=0.25, octave=(80.0, 0.93)
    )
    assert mc._grid_notes(sure) == ()
    notes = mc._grid_notes(unsure)
    assert "close call against 80.00 BPM" in notes[0] and "--bpm 80" in notes[0]
    assert "guessed downbeat (confidence 0.25)" in notes[1]


def test_audible_extent_ignores_silence_at_both_ends():
    rms = np.full(1000, -100.0)
    rms[120:880] = -12.0
    assert mc._audible(rms) == (1.2, 8.79)


def test_clock_and_numbers_print_the_way_a_person_reads_them():
    assert mc._clock(36.51) == "00:36.51" and mc._clock(125.0) == "02:05.00" and mc._clock(-1.0) == "00:00.00"
    assert (
        mc._num(0.35) == "0.35"
        and mc._num(-0.023) == "-0.023"
        and mc._num(0.0) == "0"
        and mc._num(2.0) == "2"
    )


# --------------------------------------------------------------------------
# the report and the JSON
# --------------------------------------------------------------------------
def _check(**overrides) -> mc.MasterCheck:
    fields = {
        "verdict": "new grid",
        "detail": "new grid",
        "diagnosis": "moved",
        "grid": GRID,
        "windows": (),
        "offset": 0.0,
        "offset_r": 0.99,
        "sections": (),
        "bars": (),
        "old_duration": 90.0,
        "new_duration": 90.0,
        "old_audible": (0.0, 90.0),
        "new_audible": (0.5, 90.0),
    }
    fields.update(overrides)
    return mc.MasterCheck(**fields)


def test_the_report_ends_with_the_verdict_and_its_exit_code(old):
    start = FIRST + 7 * BAR
    check = mc.compare_signals(old, old + burst(40.0, start, BAR), SR, **GIVEN)
    report = mc.format_report(check)
    assert report.startswith("master-check: old -> new")
    assert "00:14.50-00:16.50" in report and "sections" in report
    assert report.splitlines()[-1].startswith("verdict: rerender bar 8 (00:14.50-00:16.50): ")
    assert report.splitlines()[-1].endswith("(exit 3)")


def test_the_report_gives_the_delivery_sheets_new_silent_start():
    report = mc.format_report(
        _check(verdict="offset", detail="offset", offset=0.35, new_silent_start=1.85, silent_start=1.5)
    )
    assert "delivery  silent_start 1.85 for the new master (was 1.5)" in report
    assert report.endswith("(exit 5)")


def test_the_report_lists_the_windows_that_moved():
    windows = (mc.LagWindow(0.0, 0.0, 0.9), mc.LagWindow(4.0, 0.0, 0.9), mc.LagWindow(8.0, 1.0, 0.8))
    report = mc.format_report(_check(windows=windows))
    assert "windows   8s +1.00" in report and "0s +0.00" not in report


def test_a_long_list_of_moved_windows_is_cut_short_in_the_report():
    windows = tuple(mc.LagWindow(start=4.0 * i, lag=0.5, r=0.9) for i in range(20))
    report = mc.format_report(_check(windows=windows, offset=0.0))
    assert "... and 8 more (see --json)" in report


def test_the_report_prints_every_note():
    report = mc.format_report(_check(notes=("vocal moved +3.00 s (r 0.94): ...", "second note")))
    assert "  note      vocal moved +3.00 s (r 0.94): ..." in report and "  note      second note" in report


def test_a_tempo_change_reports_the_speed_it_lines_up_at():
    report = mc.format_report(_check(tempo_ratio=1.0595, offset_r=0.99))
    assert "at 1.0595x speed the whole song lines up (r 0.99)" in report


def test_to_dict_is_json_and_carries_every_bar(old):
    check = mc.compare_signals(old, delayed(old, 0.1), SR, silent_start=2.0, **GIVEN)
    data = json.loads(json.dumps(check.to_dict()))
    assert data["kaleidophone"] == mc.MASTERCHECK_FORMAT
    assert data["verdict"] == "offset" and data["exit_code"] == 5
    assert len(data["bars"]) == len(check.bars)
    assert data["grid"] == {
        "bpm": BPM,
        "downbeat": FIRST,
        "beats_per_bar": 4,
        "source": "given",
        "confidence": None,
        "octave": None,
    }
    assert data["offset"]["new_silent_start"] == pytest.approx(2.1, abs=0.001)
    assert data["offset"]["tolerance"] == pytest.approx(0.0208, abs=1e-4)
    assert data["tempo_ratio"] is None and data["vocal"] == {"lag": None, "r": None}
    assert set(data["bars"][3]["detail"]) == set(mc.ENVELOPES) - {"voc"}  # mono input: no voc


# --------------------------------------------------------------------------
# master_check(): the decode wrapper, with ffmpeg stubbed
# --------------------------------------------------------------------------
def test_master_check_decodes_both_masters_as_stereo_at_48k(monkeypatch, old):
    seen = []
    stereo = np.stack([old, old], axis=1)

    def decode(path, *, sample_rate, channels, **kwargs):
        seen.append((path, sample_rate, channels))
        return stereo.astype("<f4").tobytes()

    monkeypatch.setattr(mc, "decode_f32le", decode)
    check = mc.master_check("mix_v1.wav", "mix_v2.wav", **GIVEN)
    assert seen == [("mix_v1.wav", 48000, 2), ("mix_v2.wav", 48000, 2)]
    assert (check.old_label, check.new_label, check.verdict) == ("mix_v1.wav", "mix_v2.wav", "remux")


def test_master_check_refuses_a_file_with_no_audio(monkeypatch):
    monkeypatch.setattr(mc, "decode_f32le", lambda path, **kw: b"")
    with pytest.raises(ValueError, match="no audio"):
        mc.master_check("a.wav", "b.wav")
