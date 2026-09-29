"""audio/envelope.py: the song pack, fed synthetic signals built in code.

Every fixture here is a numpy array -- clicks, gated sines, noise -- handed to
analyze_signal() directly, so nothing is decoded and ffmpeg is never run (see
AGENTS.md, "Testing"). The one function that does shell out, envelope(), is
tested with the decode stubbed to return synthetic PCM bytes, and the new
_ffmpeg_util helpers with subprocess stubbed, the same way
tests/test_ffmpeg_util.py does it.

What is pinned is what went wrong, or nearly did, while this was written:
beats landing on the off-beat hi-hat instead of the kick, a grid one frame
ahead of every attack, a first beat at 0.0 reported a period late, and FFT
leakage normalised into a band with nothing in it. Then what the 0.3 review
found: a house groove whose bar 1 the kick alone put on beat 4, reels that
opened mid-bar, an octave choice with nothing said about the octave that
lost, and a drifting tempo with no warning.
"""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from kaleidophone.audio import envelope as env
from kaleidophone.render import _ffmpeg_util as fu

SR = 48000

KEYS_IN_ORDER = [
    "kaleidophone",
    "fps",
    "dur",
    "bpm",
    "beat0",
    "period",
    "beats",
    "downbeat",
    "bass",
    "lowmid",
    "mid",
    "high",
    "air",
    "rms",
    "rmsdb",
    "flux",
    "bflux",
    "hflux",
    "cent",
]


# --------------------------------------------------------------------------
# synthetic signals -- procedural, never a recording
# --------------------------------------------------------------------------
def _place(x: np.ndarray, sound: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = round(t * SR)
    n = min(len(sound), len(x) - i)
    if n > 0:
        x[i : i + n] += gain * sound[:n]


def _click(seed: int = 0) -> np.ndarray:
    n = int(0.02 * SR)
    return np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / (0.003 * SR))


def _kick() -> np.ndarray:
    t = np.arange(int(0.25 * SR)) / SR
    sweep = np.cumsum(45 + 110 * np.exp(-t / 0.025)) / SR
    return np.minimum(1.0, t / 0.001) * np.sin(2 * np.pi * sweep) * np.exp(-t / 0.12)


def _hat(seed: int, length: float = 0.06) -> np.ndarray:
    n = int(length * SR)
    return np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / (0.012 * SR))


def _tone(freqs, length: float, gain: float) -> np.ndarray:
    """A held chord or note with 10 ms / 20 ms edges -- no click of its own."""
    t = np.arange(int(length * SR)) / SR
    edges = np.minimum(1.0, t / 0.01) * np.minimum(1.0, (t[-1] - t) / 0.02)
    return gain * sum(np.sin(2 * np.pi * f * t) for f in freqs) * edges


def click_track(bpm: float, dur: float, offset: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    x = np.zeros(int(dur * SR))
    times = np.arange(offset, dur - 0.1, 60.0 / bpm)
    for k, t in enumerate(times):
        _place(x, _click(k), t, 0.5)
    return x.astype(np.float32), times


def tempo_ramp(bpm0: float, bpm1: float, dur: float, offset: float = 0.3) -> np.ndarray:
    """Clicks whose tempo glides from bpm0 to bpm1 -- a band that speeds up."""
    x = np.zeros(int(dur * SR))
    t, k = offset, 0
    while t < dur - 0.1:
        _place(x, _click(k), t, 0.5)
        t += 60.0 / (bpm0 + (bpm1 - bpm0) * t / dur)
        k += 1
    return x.astype(np.float32)


def kick_and_offbeat_hats(bpm: float, dur: float, offset: float) -> tuple[np.ndarray, np.ndarray]:
    """Four-on-the-floor kick with an open hat on every off-beat -- the pattern
    that pulled an unweighted comb onto the hat."""
    x = np.zeros(int(dur * SR))
    period = 60.0 / bpm
    beats = np.arange(offset, dur - 0.5, period)
    for k, b in enumerate(beats):
        _place(x, _kick(), b, 0.8)
        _place(x, _hat(k, 0.15), b + period / 2, 0.25)
    return x.astype(np.float32), beats


def house(
    bpm: float = 120.0, dur: float = 24.0, first: float = 0.25, bar1: int = 1
) -> tuple[np.ndarray, float]:
    """A kick on every beat -- nothing in the drums marks the bar -- over a
    bass note and a chord that change on every bar line. Beat `bar1` (0-based)
    is bar 1, so the song opens with a pickup. Returns (samples, bar 1 in s)."""
    x = np.zeros(int(dur * SR))
    period = 60.0 / bpm
    beats = np.arange(first, dur - 0.3, period)
    for b in beats:
        _place(x, _kick(), b, 0.8)
    roots = [55.0, 43.65, 65.41, 49.0]
    chords = [[220.0, 261.6, 329.6], [174.6, 220.0, 261.6], [261.6, 329.6, 392.0], [196.0, 246.9, 293.7]]
    t, k = beats[bar1] - 4 * period, 0
    while t < dur:
        if t >= 0:
            _place(x, _tone([roots[k % 4], 2 * roots[k % 4]], 4 * period, 0.2), t)
            _place(x, _tone(chords[k % 4], 4 * period, 0.05), t)
        t += 4 * period
        k += 1
    return x.astype(np.float32), float(beats[bar1])


def slow_pop(bpm: float, dur: float, offset: float = 0.3) -> np.ndarray:
    """Kick/snare on the beats and 8th-note hats: the classic octave trap."""
    rng = np.random.default_rng(3)
    x = np.zeros(int(dur * SR))
    period = 60.0 / bpm
    for k, b in enumerate(np.arange(offset, dur - 0.5, period)):
        if k % 2 == 0:
            _place(x, _kick(), b, 0.7)
        else:
            _place(x, rng.standard_normal(int(0.1 * SR)) * np.exp(-np.arange(int(0.1 * SR)) / 2400), b, 0.5)
        _place(x, _hat(2 * k), b, 0.12)
        _place(x, _hat(2 * k + 1), b + period / 2, 0.12)
    return x.astype(np.float32)


def _snare(seed: int) -> np.ndarray:
    n = int(0.15 * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / 0.05)
    return 0.8 * noise + 0.5 * np.sin(2 * np.pi * 185.0 * t) * np.exp(-t / 0.04)


def ballad(bpm: float = 70.0, dur: float = 30.0, first: float = 0.6) -> np.ndarray:
    """8th-note piano plucks, a kick on 1 and a snare on 3: the review's
    ballad, which comes back at double time."""
    x = np.zeros(int(dur * SR))
    eighth = 60.0 / bpm / 2
    t = np.arange(int(0.8 * SR)) / SR
    for k, at in enumerate(np.arange(first, dur - 1.0, eighth)):
        f = [261.6, 329.6, 392.0, 523.3][k % 4]
        pluck = (
            sum(np.sin(2 * np.pi * f * h * t) / h for h in (1, 2, 3))
            * np.exp(-t / 0.35)
            * np.minimum(1, t / 0.002)
        )
        _place(x, pluck, at, 0.12)
        if k % 8 == 0:
            _place(x, _kick(), at, 0.6)
        if k % 8 == 4:
            _place(x, _snare(k), at, 0.35)
    return x.astype(np.float32)


def two_step(bpm: float = 174.0, dur: float = 30.0, first: float = 0.1) -> np.ndarray:
    """Drum and bass: kick on 1 and the and-of-3, snare on 2 and 4, 8th hats --
    the review's case that comes back at half time, every beat on a snare."""
    x = np.zeros(int(dur * SR))
    for k, at in enumerate(np.arange(first, dur - 0.5, 30.0 / bpm)):
        if k % 8 in (0, 5):
            _place(x, _kick(), at, 0.9)
        if k % 8 in (2, 6):
            _place(x, _snare(k), at, 0.8)
        _place(x, _hat(k), at, 0.1)
    return x.astype(np.float32)


def gated_sine(freq: float, dur: float, on: float = 0.5, every: float = 1.0) -> np.ndarray:
    """A sine switched on for `on` of every `every` seconds, with 20 ms
    raised-cosine ramps -- an abrupt switch would itself be a broadband click."""
    t = np.arange(int(dur * SR)) / SR
    gate = np.zeros_like(t)
    ramp = int(0.02 * SR)
    shape = 0.5 - 0.5 * np.cos(np.pi * np.arange(ramp) / ramp)
    for start in np.arange(0.0, dur, every):
        a, b = int(start * SR), int((start + on) * SR)
        seg = np.ones(b - a)
        seg[:ramp], seg[-ramp:] = shape, shape[::-1]
        gate[a:b] = seg
    return (0.5 * np.sin(2 * np.pi * freq * t) * gate).astype(np.float32)


@pytest.fixture(scope="module")
def click_pack():
    x, times = click_track(120.0, 20.0, offset=0.37)
    return env.analyze_signal(x, SR), times


# --------------------------------------------------------------------------
# tempo and the beat grid
# --------------------------------------------------------------------------
def test_a_120_bpm_click_track_comes_back_at_120_with_every_beat_on_a_click(click_pack):
    pack, clicks = click_pack
    assert pack["bpm"] == pytest.approx(120.0, abs=0.05)  # the README quotes this
    beats = np.array(pack["beats"])
    assert len(beats) == len(clicks)
    assert np.max(np.abs(beats - clicks)) < 0.020


def test_the_grid_is_beat0_plus_k_periods(click_pack):
    pack, _ = click_pack
    beats = np.array(pack["beats"])
    expected = pack["beat0"] + pack["period"] * np.arange(len(beats))
    assert beats == pytest.approx(expected, abs=1e-3)
    assert pack["period"] == pytest.approx(60.0 / pack["bpm"], rel=1e-6)
    assert 0.0 <= pack["beat0"] < pack["period"]


def test_flux_peaks_on_the_attack_not_a_frame_ahead_of_it(click_pack):
    """Log flux jumps as the attack *enters* the window; the calibration moves
    it a frame later so hits land on the click."""
    pack, clicks = click_pack
    flux = np.array(pack["flux"])
    for t in clicks[2:-2]:
        centre = round(t * env.FPS)
        window = flux[centre - 4 : centre + 5]
        assert abs(int(np.argmax(window)) - 4) <= 1


def test_a_click_at_zero_is_the_first_beat_not_one_a_period_later():
    x, clicks = click_track(140.0, 12.0, offset=0.0)
    pack = env.analyze_signal(x, SR)
    assert pack["beat0"] == 0.0
    assert pack["beats"][0] == 0.0
    assert len(pack["beats"]) == len(clicks)


@pytest.mark.parametrize("bpm", [60.0, 93.5, 174.0])
def test_the_octave_check_keeps_evenly_accented_clicks_at_their_own_tempo(bpm):
    """174 is the case the prior alone gets wrong -- 87 is nearer to 120 -- and
    the off-beat evidence is what keeps it at 174."""
    x, _ = click_track(bpm, 20.0, offset=0.11)
    assert env.analyze_signal(x, SR)["bpm"] == pytest.approx(bpm, abs=0.05)


def test_beats_land_on_the_kick_not_on_the_off_beat_hat():
    """Unweighted, the hat's broadband flux outweighed the kick and the whole
    grid sat half a beat late. The comb is fed 1/f-weighted flux instead."""
    x, kicks = kick_and_offbeat_hats(124.0, 30.0, offset=0.3)
    pack = env.analyze_signal(x, SR)
    period = 60.0 / 124.0
    phase_error = (pack["beat0"] - kicks[0] + period / 2) % period - period / 2
    assert abs(phase_error) < 0.010


def test_bpm_range_is_the_lever_for_an_octave_error():
    x = slow_pop(76.0, 30.0)
    default = env.analyze_signal(x, SR)["bpm"]
    narrowed = env.analyze_signal(x, SR, bpm_range=(60.0, 100.0))["bpm"]
    assert narrowed == pytest.approx(76.0, abs=0.1)
    assert default in (pytest.approx(76.0, abs=0.1), pytest.approx(152.0, abs=0.2))


def test_the_octave_that_lost_is_reported_with_its_score_and_a_close_call_says_so():
    """The review's ballad came back at double time with the two octaves 1%
    apart and nothing said. Now the pack names the other octave, scores it,
    and a close call becomes a warning with the --bpm-range that selects it."""
    pack = env.analyze_signal(slow_pop(76.0, 30.0), SR)
    octave = pack["grid_check"]["octave"]
    other = 76.0 if pack["bpm"] > 100 else 152.0
    assert octave["bpm"] == pytest.approx(other, abs=0.2)
    assert 0.0 < octave["score"]
    if octave["score"] >= 0.9:
        warning = next(w for w in pack["grid_check"]["warnings"] if "close call" in w)
        lo, hi = env._octave_range(octave["bpm"], env.DEFAULT_BPM_RANGE)
        assert f"--bpm-range {lo:g} {hi:g}" in warning
        assert lo < octave["bpm"] < hi and not lo <= pack["bpm"] <= hi


@pytest.mark.parametrize(
    ("make", "true_bpm", "wrong_bpm"),
    [(ballad, 70.0, 140.0), (two_step, 174.0, 87.0)],
    ids=["ballad", "two-step"],
)
def test_the_known_octave_errors_name_the_right_tempo_and_bpm_range_fixes_them(make, true_bpm, wrong_bpm):
    """Pinned as they are, not as they should be: by default the ballad comes
    back at double time and the two-step at half, and the pack's other octave
    is the true tempo. The range the warning suggests gets it."""
    x = make()
    pack = env.analyze_signal(x, SR)
    assert pack["bpm"] == pytest.approx(wrong_bpm, abs=0.1)
    assert pack["grid_check"]["octave"]["bpm"] == pytest.approx(true_bpm, abs=0.1)
    assert env.analyze_signal(x, SR, bpm_range=env._octave_range(true_bpm, env.DEFAULT_BPM_RANGE))["bpm"] == (
        pytest.approx(true_bpm, abs=0.05)
    )


def test_an_octave_outside_the_range_is_not_offered():
    pack = env.analyze_signal(slow_pop(76.0, 30.0), SR, bpm_range=(60.0, 100.0))
    assert pack["grid_check"]["octave"] is None
    assert not any("close call" in w for w in pack["grid_check"]["warnings"])


def test_estimate_tempo_names_the_octave_alternative():
    x, _ = click_track(120.0, 20.0, offset=0.2)
    from_pack = env.analyze_signal(x, SR)["grid_check"]["octave"]
    raw = env._measure(x, None, SR, bands=env.BANDS, flux=True)
    tempo = env.estimate_tempo(env.onset_strength(raw.tempo_flux))
    assert tempo.alt_bpm in (pytest.approx(60.0, abs=0.1), pytest.approx(240.0, abs=0.1))
    assert tempo.alt_bpm == pytest.approx(from_pack["bpm"], abs=0.01)
    fixed = env.estimate_tempo(env.onset_strength(raw.tempo_flux), bpm_range=(120.0, 120.0))
    assert fixed.alt_bpm is None and fixed.alt_score is None


def test_the_suggested_range_shuts_out_the_winning_octave_and_stays_in_bounds():
    assert env._octave_range(70.0, (60.0, 200.0)) == (60.0, 90.0)
    assert env._octave_range(174.0, (60.0, 200.0)) == (135.0, 200.0)


def test_an_octave_the_search_never_tried_is_measured_on_the_spot():
    """119.99 BPM's half, 59.995, sits a hair under a range starting at 60:
    no candidate tried it, and it is still the 60 BPM grid the range allows."""
    x, _ = click_track(120.0, 20.0, offset=0.2)
    raw = env._measure(x, None, SR, bands=env.BANDS, flux=True)
    onset = env.onset_strength(raw.tempo_flux)
    alt, score = env._octave_alternative(onset, env.FPS, 119.99, 1.0, 60.0, 200.0, tried=[])
    assert alt == pytest.approx(60.0, abs=0.05) and score > 0.0
    assert env._octave_alternative(onset, env.FPS, 150.0, 1.0, 100.0, 200.0, tried=[]) == (None, None)


def test_a_fixed_tempo_range_still_finds_the_phase():
    x, clicks = click_track(120.0, 12.0, offset=0.21)
    pack = env.analyze_signal(x, SR, bpm_range=(120.0, 120.0))
    assert pack["bpm"] == 120.0
    assert np.max(np.abs(np.array(pack["beats"]) - clicks)) < 0.020


def test_autocorrelation_with_no_peak_in_range_still_offers_a_candidate():
    """A slow swell has no periodicity at all inside 60-200 BPM; the strongest
    lag in range is offered anyway, and the comb decides."""
    candidates = env._autocorr_candidates(np.linspace(1.0, 0.0, 3000), 100, 60.0, 200.0)
    assert len(candidates) == 1 and 60.0 <= candidates[0] <= 200.0


def test_estimate_tempo_refuses_an_inverted_range():
    with pytest.raises(ValueError, match="0 < lo <= hi"):
        env.estimate_tempo(np.ones(1000), bpm_range=(150.0, 90.0))


def test_estimate_tempo_says_how_long_the_audio_needs_to_be():
    with pytest.raises(ValueError, match="at least two beats"):
        env.estimate_tempo(np.ones(150), bpm_range=(60.0, 200.0))


def test_silence_is_refused_rather_than_given_a_tempo():
    with pytest.raises(ValueError, match="silent"):
        env.analyze_signal(np.zeros(5 * SR, dtype=np.float32), SR)


def test_tempo_beats_is_empty_when_the_song_ends_before_the_first_beat():
    assert len(env.Tempo(bpm=120.0, beat0=0.4, period=0.5, score=1.0).beats(0.3)) == 0


# --------------------------------------------------------------------------
# how well the fixed grid fits
# --------------------------------------------------------------------------
def test_a_steady_tempo_fits_its_grid_in_every_section(click_pack):
    x, _ = click_track(90.0, 40.0, offset=0.3)
    pack = env.analyze_signal(x, SR)
    measured = [s for s in pack["grid_check"]["sections"] if s["max_ms"] is not None]
    assert len(measured) >= 2
    assert all(s["max_ms"] <= 5 and s["off"] == 0 for s in measured)
    assert all(s["bpm"] == pytest.approx(pack["bpm"], abs=0.01) for s in measured)
    assert not any("drifts" in w for w in pack["grid_check"]["warnings"])


def test_a_drifting_tempo_is_measured_per_section_and_warned_about():
    """The review's live-band case: a tempo gliding 88 -> 92 BPM had most of
    its beats more than a frame off the one fixed grid, and nothing said so."""
    pack = env.analyze_signal(tempo_ramp(88.0, 92.0, 60.0), SR)
    sections = [s for s in pack["grid_check"]["sections"] if s["max_ms"] is not None]
    assert max(s["max_ms"] for s in sections) > 21
    local = [s["bpm"] for s in sections]
    assert local[-1] > local[0]  # each section's own tempo follows the glide
    warning = next(w for w in pack["grid_check"]["warnings"] if "drifts off the fixed grid" in w)
    assert "tempo map" in warning and "BPM against the grid's" in warning


def test_a_section_with_no_pulse_is_not_measured():
    """A beatless stretch has nothing to be early or late against: None, not
    whatever offset random onsets happen to line up at."""
    onset = np.zeros(4000)
    beats = np.arange(0.5, 40.0, 0.5)
    onset[np.round(beats[beats >= 20.5] * 100).astype(int)] = 1.0  # a pulse only from 20.5 s
    sections = env.grid_fit(onset, beats, 0.5, 20.5, 4)
    assert sections[0]["bars"][1] == 0 and sections[0]["offset_ms"] is None  # the pickup: bars before 20.5 s
    assert sections[0]["off"] is None and sections[0]["beats"] == 40
    assert all(s["offset_ms"] == 0 and s["max_ms"] == 0 for s in sections[1:] if s["beats"] >= 8)


def test_a_late_pulse_reads_as_a_positive_offset():
    onset = np.zeros(3000)
    beats = np.arange(0.0, 30.0, 0.5)
    onset[np.round((beats + 0.03) * 100).astype(int)] = 1.0  # the music lands 30 ms after the grid
    sections = env.grid_fit(onset, beats, 0.5, 0.0, 4)
    assert sections[0]["offset_ms"] == 30 and sections[0]["off"] == sections[0]["beats"]


def test_grid_fit_of_no_beats_is_empty():
    assert env.grid_fit(np.zeros(100), np.zeros(0), 0.5, 0.0) == []


def test_a_section_past_the_end_of_the_onsets_is_not_measured():
    onset = np.zeros(1000)  # 10 s of onsets, a grid running on to 30 s
    sections = env.grid_fit(onset, np.arange(0.0, 30.0, 0.5), 0.5, 0.0)
    assert sections[-1]["start"] > 10.0 and sections[-1]["offset_ms"] is None


# --------------------------------------------------------------------------
# the downbeat
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bar1", [0, 1, 2, 3])
def test_bar_1_is_found_on_a_house_groove_where_the_kick_says_nothing(bar1):
    """The review's 120 BPM four-on-the-floor put bar 1 on beat 4: a kick on
    every beat can't mark the bar. The bass note and chord changing on the
    bar line can, whichever beat of the song bar 1 falls on."""
    x, truth = house(bar1=bar1)
    pack = env.analyze_signal(x, SR)
    assert pack["downbeat"] == pytest.approx(truth, abs=0.02)
    assert pack["grid_check"]["downbeat"]["confidence"] >= 0.8
    assert pack["grid_check"]["downbeat"]["runner_up"] != pytest.approx(truth, abs=0.02)
    assert not any("bar 1 is a guess" in w for w in pack["grid_check"]["warnings"])


def test_the_kick_alone_misses_the_house_groove_bar_that_harmony_finds():
    """Measured on this signal: the bass-band onsets alone favour the beat
    in the middle of the bar -- the kick and the held bass note interact the
    same way every bar -- and the harmony moves bar 1 back to the bar line."""
    x, truth = house(bar1=2)
    pack = env.analyze_signal(x, SR)
    beats = np.array(pack["beats"])
    kick_only = env.estimate_downbeat(beats, np.array(pack["bflux"]), None)
    with_harmony = env.estimate_downbeat(beats, np.array(pack["bflux"]), env.harmonic_novelty(x, SR, beats))
    assert with_harmony.t == pytest.approx(truth, abs=0.02)
    assert kick_only.t != pytest.approx(truth, abs=0.02)


def test_with_nothing_to_mark_the_bar_the_downbeat_says_it_is_a_guess(click_pack):
    pack, _ = click_pack
    check = pack["grid_check"]["downbeat"]
    assert check["source"] == "estimated" and check["confidence"] < 0.6
    assert any("bar 1 is a guess" in w and "--downbeat" in w for w in pack["grid_check"]["warnings"])


def test_a_given_downbeat_is_used_as_given_and_checked_against_the_grid():
    x, _ = click_track(120.0, 12.0, offset=0.25)
    on_grid = env.analyze_signal(x, SR, downbeat=0.75)
    assert on_grid["downbeat"] == 0.75
    assert on_grid["grid_check"]["downbeat"] == {"source": "given"}
    assert not any("given downbeat" in w for w in on_grid["grid_check"]["warnings"])
    off_grid = env.analyze_signal(x, SR, downbeat=0.9)
    assert any("given downbeat sits 150 ms" in w for w in off_grid["grid_check"]["warnings"])


@pytest.mark.parametrize("downbeat", [-0.5, 12.0])
def test_a_downbeat_outside_the_song_is_refused(downbeat):
    x, _ = click_track(120.0, 12.0, offset=0.25)
    with pytest.raises(ValueError, match="--downbeat"):
        env.analyze_signal(x, SR, downbeat=downbeat)


def test_beats_per_bar_must_be_positive():
    x, _ = click_track(120.0, 6.0, offset=0.25)
    with pytest.raises(ValueError, match="--beats-per-bar"):
        env.analyze_signal(x, SR, beats_per_bar=0)


def test_a_waltz_finds_its_one_among_three():
    """3/4: kick and a bass note on 1, a click on 2 and 3, the bass changing
    every bar. With beats_per_bar=3 the one is the beat the bar starts on."""
    x = np.zeros(int(24.0 * SR))
    period = 60.0 / 90.0
    beats = np.arange(0.3, 23.5, period)
    for k, b in enumerate(beats):
        if (k - 2) % 3 == 0:  # bar 1 is the third beat of the song
            _place(x, _kick(), b, 0.8)
            _place(x, _tone([[55.0, 65.41, 49.0][((k - 2) // 3) % 3]], 3 * period, 0.2), b)
        else:
            _place(x, _click(k), b, 0.3)
    pack = env.analyze_signal(x.astype(np.float32), SR, beats_per_bar=3)
    assert pack["downbeat"] == pytest.approx(beats[2], abs=0.02)
    assert pack["grid_check"]["beats_per_bar"] == 3


def test_guess_downbeat_picks_the_beat_carrying_the_most_bass_flux():
    beats = np.arange(16) * 0.5 + 0.25
    bflux = np.zeros(1000)
    for b in beats[2::4]:
        bflux[round(b * env.FPS)] = 1.0
    assert env.guess_downbeat(beats, bflux) == beats[2]
    assert env.estimate_downbeat(beats, bflux).confidence == 1.0


def test_guess_downbeat_falls_back_to_the_first_beat():
    assert env.guess_downbeat(np.array([0.3, 0.8]), np.zeros(200)) == 0.3
    assert env.guess_downbeat(np.array([]), np.zeros(200)) == 0.0
    assert env.estimate_downbeat(np.array([0.3, 0.8, 1.3, 1.8]), np.zeros(200), beats_per_bar=1).t == 0.3


def test_one_bar_is_too_little_to_be_confident_about():
    beats = np.arange(5) * 0.5
    bflux = np.zeros(300)
    bflux[round(beats[1] * env.FPS)] = 1.0
    result = env.estimate_downbeat(beats, bflux)
    assert result.t == beats[1]
    assert result.runner_up is not None


def test_harmonic_novelty_rises_where_the_chord_changes_and_ignores_silence():
    beats = np.arange(0.0, 8.0, 0.5)
    x = np.zeros(int(8.0 * SR))
    _place(x, _tone([220.0, 277.2, 329.6], 4.0, 0.2), 0.0)  # A major for 4 s
    _place(x, _tone([196.0, 246.9, 293.7], 2.0, 0.2), 4.0)  # G major for 2 s, then silence
    novelty = env.harmonic_novelty(x.astype(np.float32), SR, beats)
    change = int(np.flatnonzero(beats == 4.0)[0])
    assert novelty[change] == max(novelty) and novelty[change] > 0.3
    assert novelty[0] == 0.0
    assert np.all(novelty[beats >= 6.5] == 0.0)  # silence on either side
    assert np.all(env.harmonic_novelty(x, SR, np.array([1.0])) == 0.0)


# --------------------------------------------------------------------------
# bands, voc, normalisation
# --------------------------------------------------------------------------
def test_a_60hz_sine_shows_up_in_bass_and_not_in_high():
    pack = env.analyze_signal(gated_sine(60.0, 8.0), SR)
    bass, high = np.array(pack["bass"]), np.array(pack["high"])
    # Middles of the on-segments (0.1-0.4 s into each second).
    on = np.concatenate([np.arange(s * 100 + 10, s * 100 + 40) for s in range(8)])
    assert bass[on].min() > 0.9
    assert high[on].max() < 0.05


def test_leakage_far_below_audibility_is_floored_not_normalised_into_a_signal():
    """The Hann window leaks a -9 dB 60 Hz tone into 2-6 kHz at around -120 dB.
    Without the floor the percentiles would stretch that to full scale."""
    levels = env.level_envelopes(gated_sine(60.0, 4.0), SR, env.BANDS)
    assert np.all(levels["high"] == env.FLOOR_DB)
    assert np.all(levels["air"] == env.FLOOR_DB)
    assert levels["bass"].max() == pytest.approx(-9.03, abs=0.1)


def test_a_full_scale_sine_reads_minus_3_db_in_its_band_as_in_rmsdb():
    t = np.arange(4 * SR) / SR
    levels = env.level_envelopes(
        np.sin(2 * np.pi * 1000.0 * t).astype(np.float32), SR, {"mid": (400.0, 2000.0)}
    )
    assert levels["mid"][100:300] == pytest.approx(-3.01, abs=0.05)
    assert levels["rms"][100:300] == pytest.approx(-3.01, abs=0.05)


def test_identical_left_and_right_give_a_voc_of_zero():
    """A mono bounce exported as stereo has no side at all: nothing to
    contrast the centre with, so no voice -- not a voice everywhere."""
    x, _ = click_track(120.0, 10.0, offset=0.2)
    t = np.arange(len(x)) / SR
    x = x + (0.2 * np.sin(2 * np.pi * 330.0 * t)).astype(np.float32)
    pack = env.analyze_signal(np.stack([x, x], axis=1), SR)
    assert max(pack["voc"]) < 0.01


def _wide_mix_with_a_voice(n_seconds: int = 16) -> np.ndarray:
    rng = np.random.default_rng(11)
    n = n_seconds * SR
    t = np.arange(n) / SR
    wide = 0.05 * rng.standard_normal((n, 2))  # decorrelated: all side
    x, _ = click_track(120.0, float(n_seconds), offset=0.25)
    voice = np.zeros(n)
    voice[8 * SR :] = sum(np.sin(2 * np.pi * 220.0 * h * t[8 * SR :]) / h for h in range(1, 6))
    return (wide + (x + 0.1 * voice)[:, None]).astype(
        np.float32
    )  # the voice and the clicks sit in the centre


def test_voc_rises_when_a_centred_voice_enters_a_wide_mix():
    voc = np.array(env.analyze_signal(_wide_mix_with_a_voice(), SR)["voc"])
    assert voc[900:1500].mean() > voc[100:700].mean() + 0.4


def test_mono_input_gets_no_voc():
    x, _ = click_track(120.0, 6.0, offset=0.2)
    assert "voc" not in env.analyze_signal(x, SR)
    assert "voc" not in env.analyze_signal(x[:, None], SR)


def test_raw_envelopes_are_the_pack_before_normalisation():
    """What master-check compares: dB levels, raw flux, cent in Hz, and voc as
    a contrast in dB -- for stereo that isn't dual mono only."""
    stereo = _wide_mix_with_a_voice(8)
    raw = env.raw_envelopes(stereo, SR, extra_bands={"vocal": (350.0, 3400.0)})
    for key in (*env.BANDS, "rms", *env.FLUX_BANDS, "cent", "voc", "vocal"):
        assert len(raw[key]) == 1 + len(stereo) // (SR // env.FPS), key
    assert raw["rms"].max() <= 0.0 and raw["rms"].min() >= env.FLOOR_DB
    assert raw["cent"].max() > 100.0  # Hz, not 0..1
    assert raw["voc"].min() >= -30.0 and raw["voc"].max() <= 30.0
    mono = stereo.mean(axis=1)
    assert "voc" not in env.raw_envelopes(mono, SR)
    assert "voc" not in env.raw_envelopes(np.stack([mono, mono], axis=1), SR)


def test_percentile_normalize_maps_its_percentiles_onto_0_and_1_and_clips():
    x = np.arange(1001, dtype=float)
    y = env.percentile_normalize(x)
    assert y.min() == 0.0 and y.max() == 1.0
    assert y[50] == pytest.approx(0.0, abs=1e-9)  # 5th percentile
    assert y[995] == pytest.approx(1.0, abs=1e-9)  # 99.5th percentile
    assert y[500] == pytest.approx((500 - 50) / (995 - 50))


def test_percentile_normalize_of_a_flat_envelope_is_zero_not_noise():
    assert np.all(env.percentile_normalize(np.full(100, -42.0)) == 0.0)
    assert np.all(env.percentile_normalize(np.array([])) == 0.0)


def test_percentile_normalize_mask_sets_the_percentiles_but_maps_every_frame():
    x = np.concatenate([np.full(50, -100.0), np.linspace(-40.0, 0.0, 50)])
    y = env.percentile_normalize(x, mask=x > -100.0)
    assert y[:50].max() == 0.0
    assert y[-1] == 1.0
    assert np.all(env.percentile_normalize(x, mask=np.zeros(100, bool)) == 0.0)


def test_every_envelope_has_one_value_per_frame_and_stays_in_range(click_pack):
    pack, _ = click_pack
    frames = 1 + int(20.0 * SR) // (SR // env.FPS)
    for key in ("bass", "lowmid", "mid", "high", "air", "rms", "cent"):
        assert len(pack[key]) == frames, key
        assert 0.0 <= min(pack[key]) and max(pack[key]) <= 1.0, key
    for key in ("flux", "bflux", "hflux"):
        assert len(pack[key]) == frames
        assert 0.0 <= min(pack[key]) and max(pack[key]) <= 1.5
    assert len(pack["rmsdb"]) == frames
    assert min(pack["rmsdb"]) >= env.FLOOR_DB


def test_the_pack_keys_follow_the_documented_order(click_pack):
    pack, _ = click_pack
    assert list(pack)[: len(KEYS_IN_ORDER)] == KEYS_IN_ORDER
    assert list(pack)[-2:] == ["loudest", "grid_check"]
    assert set(pack["grid_check"]) == {"beats_per_bar", "octave", "downbeat", "sections", "warnings"}
    assert pack["kaleidophone"] == env.SONGPACK_FORMAT
    assert pack["fps"] == 100


def test_a_44_1_khz_signal_keeps_the_10_ms_hop():
    x, _ = click_track(120.0, 6.0, offset=0.2)
    sr = 44100
    resampled = np.interp(np.arange(0, len(x), SR / sr), np.arange(len(x)), x).astype(np.float32)
    pack = env.analyze_signal(resampled, sr)
    assert len(pack["bass"]) == 1 + len(resampled) // 441
    assert pack["bpm"] == pytest.approx(120.0, abs=0.5)


# --------------------------------------------------------------------------
# loudest window
# --------------------------------------------------------------------------
def test_the_loudest_minute_is_found_and_starts_on_a_bar_line():
    """It snapped to the nearest beat until 0.3, and half the review's reels
    opened on beat 2, 3 or 4. A reel starts where a phrase does."""
    x, _ = click_track(120.0, 100.0, offset=0.25)
    t = np.arange(len(x)) / SR
    pad = 0.3 * np.sin(2 * np.pi * 220.0 * t)
    pad[: 35 * SR] *= 0.05  # a quiet opening third
    pack = env.analyze_signal((x + pad).astype(np.float32), SR, downbeat=0.75)
    loudest = pack["loudest"]
    assert loudest["len"] == 60
    assert loudest["start"] >= 30.0
    assert loudest["start"] + 60 <= pack["dur"]
    bars = (loudest["start"] - pack["downbeat"]) / (4 * pack["period"])
    assert bars == pytest.approx(round(bars), abs=1e-3)


def test_the_loudest_window_snaps_to_a_bar_before_the_downbeat_too():
    rms = np.full(10001, -60.0)
    rms[500:6500] = -6.0  # loudest from 5.0 s
    assert env._loudest_window(rms, downbeat=30.0, bar=2.0, dur=100.0)["start"] == 6.0
    assert env._loudest_window(rms, downbeat=0.0, bar=0.0, dur=100.0)["start"] == 5.0  # no bar: as found


def test_a_song_shorter_than_a_minute_is_its_own_loudest_window(click_pack):
    pack, _ = click_pack
    assert pack["loudest"] == {"start": 0.0, "len": 20.0}


# --------------------------------------------------------------------------
# input validation
# --------------------------------------------------------------------------
def test_audio_too_short_for_a_tempo_is_refused_with_a_reason():
    with pytest.raises(ValueError, match="too short"):
        env.analyze_signal(np.zeros(SR, dtype=np.float32), SR)


@pytest.mark.parametrize("shape", [(10, 3), (2, 10, 1)])
def test_shapes_other_than_mono_or_stereo_are_refused(shape):
    with pytest.raises(ValueError, match="expected samples shaped"):
        env.analyze_signal(np.zeros(shape, dtype=np.float32), SR)


def test_a_sample_rate_that_is_not_a_whole_number_of_hops_is_refused():
    with pytest.raises(ValueError, match="multiple of 100"):
        env.analyze_signal(np.zeros(5 * 22050, dtype=np.float32), 22050)


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------
def test_the_pack_round_trips_through_json_exactly(click_pack, tmp_path):
    pack, _ = click_pack
    path = env.write_songpack(pack, str(tmp_path / "packs" / "songpack.json"))
    assert env.load_songpack(path) == pack
    text = (tmp_path / "packs" / "songpack.json").read_text()
    assert text == json.dumps(pack, separators=(",", ":"))  # compact
    assert "-0.0," not in text  # no negative zeros


def test_load_songpack_refuses_a_file_that_is_not_one(tmp_path):
    old_style = tmp_path / "env.json"
    old_style.write_text(json.dumps({"sr": 100, "bpm": 120.0, "bass": [0.0]}))
    with pytest.raises(ValueError, match="kaleidophone envelope"):
        env.load_songpack(str(old_style))
    listing = tmp_path / "list.json"
    listing.write_text("[1, 2, 3]")
    with pytest.raises(ValueError, match="not a songpack/1"):
        env.load_songpack(str(listing))


# --------------------------------------------------------------------------
# envelope(): the decode wrapper, with ffmpeg stubbed
# --------------------------------------------------------------------------
@pytest.fixture
def audio_file(tmp_path):
    """A placeholder path that exists -- its bytes are never read, because the
    decode is stubbed. Not audio, and nothing under tmp_path is committed."""
    path = tmp_path / "song.bin"
    path.write_bytes(b"not decoded")
    return str(path)


def _stub_decode(monkeypatch, samples: np.ndarray, channels_reported: str | None):
    seen = {}

    def decode(path, *, sample_rate, channels, **kwargs):
        seen.update(path=path, sample_rate=sample_rate, channels=channels)
        return samples.astype("<f4").tobytes()

    monkeypatch.setattr(env, "decode_f32le", decode)
    monkeypatch.setattr(env, "probe_stream", lambda path, stream, entry, **kwargs: channels_reported)
    return seen


def test_envelope_decodes_a_stereo_file_at_48k_as_two_channels(monkeypatch, audio_file):
    x, _ = click_track(120.0, 6.0, offset=0.2)
    seen = _stub_decode(monkeypatch, np.stack([x, 0.5 * x], axis=1), "2")
    pack = env.envelope(audio_file)
    assert seen["sample_rate"] == 48000 and seen["channels"] == 2
    assert "voc" in pack
    assert pack["dur"] == pytest.approx(6.0)


def test_envelope_passes_the_downbeat_and_bar_length_through(monkeypatch, audio_file):
    x, _ = click_track(120.0, 6.0, offset=0.25)
    _stub_decode(monkeypatch, x, "1")
    pack = env.envelope(audio_file, downbeat=0.75, beats_per_bar=3)
    assert pack["downbeat"] == 0.75
    assert pack["grid_check"]["beats_per_bar"] == 3


def test_envelope_keeps_a_mono_file_mono(monkeypatch, audio_file):
    x, _ = click_track(120.0, 6.0, offset=0.2)
    seen = _stub_decode(monkeypatch, x, "1")
    assert "voc" not in env.envelope(audio_file)
    assert seen["channels"] == 1


def test_envelope_decodes_as_stereo_when_ffprobe_cannot_say(monkeypatch, audio_file):
    x, _ = click_track(120.0, 6.0, offset=0.2)
    seen = _stub_decode(monkeypatch, np.stack([x, x], axis=1), None)
    pack = env.envelope(audio_file)
    assert seen["channels"] == 2
    assert max(pack["voc"]) == 0.0  # a mono source upmixed: dual mono


def test_envelope_reports_a_missing_file_by_name(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        env.envelope(str(tmp_path / "nope.wav"))
    assert exc.value.filename.endswith("nope.wav")


def test_envelope_refuses_a_file_with_no_audio(monkeypatch, audio_file):
    _stub_decode(monkeypatch, np.zeros(0), "2")
    with pytest.raises(ValueError, match="no audio"):
        env.envelope(audio_file)


# --------------------------------------------------------------------------
# the new _ffmpeg_util helpers, with subprocess stubbed
# --------------------------------------------------------------------------
class _Proc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_decode_f32le_asks_for_raw_float_pcm_at_the_given_rate_and_channels(monkeypatch, audio_file):
    seen = {}
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    def fake(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Proc(stdout=b"\x00" * 8)

    monkeypatch.setattr(subprocess, "run", fake)
    assert fu.decode_f32le(audio_file, sample_rate=48000, channels=2) == b"\x00" * 8
    cmd = seen["cmd"]
    assert cmd[cmd.index("-ar") + 1] == "48000"
    assert cmd[cmd.index("-ac") + 1] == "2"
    assert cmd[cmd.index("-f") + 1] == "f32le"
    assert cmd[cmd.index("-i") + 1].startswith("/")  # absolute: a leading '-' can't be a flag
    assert "-vn" in cmd and cmd[-1] == "-"


def test_decode_f32le_raises_with_ffmpegs_own_words(monkeypatch, audio_file):
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, b"", b"Invalid data found"))
    with pytest.raises(RuntimeError, match="Invalid data found"):
        fu.decode_f32le(audio_file, sample_rate=48000, channels=1)


def test_decode_f32le_reports_a_missing_file_before_looking_for_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(fu.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        fu.decode_f32le(str(tmp_path / "missing.wav"), sample_rate=48000, channels=1)


def test_probe_stream_returns_one_value(monkeypatch):
    seen = {}
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffprobe")

    def fake(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Proc(stdout="2\n")

    monkeypatch.setattr(subprocess, "run", fake)
    assert fu.probe_stream("song.wav", "a:0", "channels") == "2"
    assert "-count_packets" not in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("-show_entries") + 1] == "stream=channels"


@pytest.mark.parametrize(
    ("which", "proc"),
    [(None, _Proc(stdout="2")), ("/usr/bin/ffprobe", _Proc(1, "")), ("/usr/bin/ffprobe", _Proc(0, ""))],
)
def test_probe_stream_degrades_to_none(monkeypatch, which, proc):
    monkeypatch.setattr(fu.shutil, "which", lambda name: which)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    assert fu.probe_stream("song.wav", "a:0", "channels") is None
