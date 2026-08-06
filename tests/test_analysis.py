"""audio/analysis.py: the quiet-passage / energy-jump detectors as pure
array logic, plus one real (tiny, synthetic, throwaway) run through the
actual librosa pipeline.

These two heuristics are the load-bearing signal for auto-mode's section
boundaries (timeline/autobrief.py) and for "the hush" / "the switch" in
docs/CREATIVE-GUIDE.md's vocabulary, so their edge cases (a dip too short to
count, a quiet stretch that runs to the end of the song) are worth pinning
directly against hand-built arrays rather than only ever through a full
analyze() call.
"""

from __future__ import annotations

import numpy as np
import pytest
from factories import make_analysis

from mvideo.audio.analysis import _find_energy_jumps, _find_quiet_passages, analyze

# --- _find_quiet_passages ---------------------------------------------


def test_find_quiet_passages_detects_a_stretch_below_threshold_and_long_enough():
    rms_times = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    rms_db = np.array([-10.0, -10.0, -40.0, -40.0, -40.0, -10.0, -10.0])

    passages = _find_quiet_passages(rms_db, rms_times, threshold_db=-35.0, min_duration=1.0)

    assert len(passages) == 1
    assert passages[0].start == pytest.approx(1.0)
    assert passages[0].end == pytest.approx(2.5)
    assert passages[0].mean_rms_db == pytest.approx(-40.0)


def test_find_quiet_passages_ignores_a_dip_shorter_than_min_duration():
    rms_times = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    rms_db = np.array([-10.0, -40.0, -10.0, -10.0, -10.0])  # one lone quiet frame, 0.5s wide

    assert _find_quiet_passages(rms_db, rms_times, threshold_db=-35.0, min_duration=1.0) == ()


def test_find_quiet_passages_handles_a_quiet_stretch_running_to_the_songs_end():
    rms_times = np.array([0.0, 0.5, 1.0, 1.5])
    rms_db = np.array([-10.0, -40.0, -40.0, -40.0])  # never rises back above threshold

    passages = _find_quiet_passages(rms_db, rms_times, threshold_db=-35.0, min_duration=1.0)

    assert len(passages) == 1
    assert passages[0].end == pytest.approx(1.5)


# --- _find_energy_jumps -------------------------------------------------


def test_find_energy_jumps_flags_a_sharp_rise_above_the_zscore_threshold():
    # a long flat baseline before and after one spike -- with too few frames
    # the spike's own symmetric fall-back inflates the std and can mask
    # itself; a real onset envelope has enough frames that this isn't an
    # issue, so the test baseline needs to as well.
    onset_env = np.array([0.1] * 10 + [5.0] + [0.1] * 9)
    onset_times = np.arange(len(onset_env)) * 0.5

    jumps = _find_energy_jumps(onset_env, onset_times, z_threshold=2.0)

    assert len(jumps) == 1
    assert jumps[0].time == pytest.approx(5.0)
    assert jumps[0].onset_strength == pytest.approx(5.0)
    assert jumps[0].z_score >= 2.0


def test_find_energy_jumps_empty_for_a_flat_envelope():
    onset_env = np.array([0.3, 0.3, 0.3, 0.3])
    onset_times = np.array([0.0, 0.5, 1.0, 1.5])
    assert _find_energy_jumps(onset_env, onset_times, z_threshold=2.0) == ()


def test_find_energy_jumps_handles_fewer_than_two_frames_without_crashing():
    assert _find_energy_jumps(np.array([0.5]), np.array([0.0]), z_threshold=2.0) == ()
    assert _find_energy_jumps(np.array([]), np.array([]), z_threshold=2.0) == ()


# --- AudioAnalysis.beats_in ----------------------------------------------


def test_beats_in_filters_to_a_half_open_range():
    analysis = make_analysis(duration=10.0, beat_times=(0.0, 1.0, 2.0, 3.0, 4.0))
    assert analysis.beats_in(1.0, 3.0) == [1.0, 2.0]


# --- analyze() end to end -------------------------------------------------


def test_analyze_runs_end_to_end_on_a_tiny_synthetic_click_track(tmp_path):
    """One real (short, synthetic, throwaway) file through the actual
    librosa pipeline -- everything above tests the pure-logic detectors
    directly against hand-built arrays. Procedurally generated, same rule
    as examples/demo/generate_fixtures.py: never a real/personal recording,
    never committed (tmp_path is outside the repo and cleaned up by pytest)."""
    sf = pytest.importorskip("soundfile")

    sr = 22050
    duration = 4.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.05 * np.sin(2 * np.pi * 220 * t)
    clicks = np.zeros_like(t)
    for beat_t in np.arange(0, duration, 0.5):  # a click every 0.5s -> 120 BPM
        idx = int(beat_t * sr)
        clicks[idx : idx + int(sr * 0.02)] = 0.8
    y = (tone + clicks).astype(np.float32)

    wav_path = tmp_path / "tone.wav"
    sf.write(wav_path, y, sr)

    result = analyze(str(wav_path))

    assert result.duration == pytest.approx(duration, abs=0.05)
    assert result.sr == sr
    assert result.bpm > 0
    assert len(result.beat_times) > 0
    assert len(result.onset_env) > 0
    assert len(result.rms_db) == len(result.rms_times)
