"""
Turn a song into numbers the rest of kaleidophone can use: tempo, beat grid, and a
couple of structural heuristics -- a quiet passage, a sudden jump in energy --
that map directly onto the vocabulary in docs/CREATIVE-GUIDE.md ("the hush",
"the switch"). None of this is exact; it's a fast, deterministic first pass
you're meant to override in the brief (SongConfig.bpm, SectionConfig.start/
end) when it gets something wrong. See
docs/decisions/0002-deterministic-edit-engine.md for why this is librosa +
heuristics and not a model call.
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np


@dataclass(frozen=True)
class QuietPassage:
    start: float
    end: float
    mean_rms_db: float


@dataclass(frozen=True)
class EnergyJump:
    time: float
    onset_strength: float
    z_score: float


@dataclass(frozen=True)
class AudioAnalysis:
    path: str
    duration: float
    sr: int
    bpm: float
    beat_times: tuple[float, ...]
    onset_times: tuple[float, ...]
    onset_env: tuple[float, ...]  # onset strength, one value per analysis frame
    onset_env_times: tuple[float, ...]
    rms_db: tuple[float, ...]
    rms_times: tuple[float, ...]
    quiet_passages: tuple[QuietPassage, ...]
    energy_jumps: tuple[EnergyJump, ...]

    def beats_in(self, start: float, end: float) -> list[float]:
        return [t for t in self.beat_times if start <= t < end]


def analyze(
    path: str,
    *,
    bpm_override: float | None = None,
    quiet_db_threshold: float = -35.0,
    quiet_min_duration: float = 1.5,
    jump_z_threshold: float = 2.0,
) -> AudioAnalysis:
    """Load `path` and run the full analysis pass. This is the only function
    most callers need; `kaleidophone analyze` is a thin CLI wrapper around it."""
    y, sr = librosa.load(path, sr=None, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(bpm_override) if bpm_override else float(np.atleast_1d(tempo)[0])
    beat_times = tuple(librosa.frames_to_time(beat_frames, sr=sr).tolist())

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_env_times = librosa.times_like(onset_env, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    onset_times = tuple(librosa.frames_to_time(onset_frames, sr=sr).tolist())

    rms = librosa.feature.rms(y=y)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    rms_times = librosa.times_like(rms, sr=sr)

    quiet_passages = _find_quiet_passages(rms_db, rms_times, quiet_db_threshold, quiet_min_duration)
    energy_jumps = _find_energy_jumps(onset_env, onset_env_times, jump_z_threshold)

    return AudioAnalysis(
        path=path,
        duration=float(duration),
        sr=int(sr),
        bpm=bpm,
        beat_times=beat_times,
        onset_times=onset_times,
        onset_env=tuple(onset_env.tolist()),
        onset_env_times=tuple(onset_env_times.tolist()),
        rms_db=tuple(rms_db.tolist()),
        rms_times=tuple(rms_times.tolist()),
        quiet_passages=quiet_passages,
        energy_jumps=energy_jumps,
    )


def _find_quiet_passages(
    rms_db: np.ndarray, rms_times: np.ndarray, threshold_db: float, min_duration: float
) -> tuple[QuietPassage, ...]:
    """Contiguous stretches below `threshold_db` for at least `min_duration`
    seconds -- the reference case study's 'the hush' (3:10-3:28)."""
    passages = []
    below = rms_db < threshold_db
    start_idx = None
    for i, is_below in enumerate(below):
        if is_below and start_idx is None:
            start_idx = i
        elif not is_below and start_idx is not None:
            start_t, end_t = rms_times[start_idx], rms_times[i]
            if end_t - start_t >= min_duration:
                passages.append(
                    QuietPassage(float(start_t), float(end_t), float(np.mean(rms_db[start_idx:i])))
                )
            start_idx = None
    if start_idx is not None:
        start_t, end_t = rms_times[start_idx], rms_times[-1]
        if end_t - start_t >= min_duration:
            passages.append(QuietPassage(float(start_t), float(end_t), float(np.mean(rms_db[start_idx:]))))
    return tuple(passages)


def _find_energy_jumps(
    onset_env: np.ndarray, onset_env_times: np.ndarray, z_threshold: float
) -> tuple[EnergyJump, ...]:
    """Frame-to-frame onset-strength jumps more than `z_threshold` standard
    deviations above the mean -- the reference case study's 'the switch' (3:28.3)."""
    if len(onset_env) < 2:
        return ()
    delta = np.diff(onset_env, prepend=onset_env[0])
    mean, std = float(np.mean(delta)), float(np.std(delta)) or 1e-9
    z = (delta - mean) / std
    jumps = [
        EnergyJump(float(onset_env_times[i]), float(onset_env[i]), float(zi))
        for i, zi in enumerate(z)
        if zi >= z_threshold
    ]
    return tuple(jumps)
