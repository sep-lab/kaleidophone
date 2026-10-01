"""
The song pack: one song -> a 100 Hz envelope file that canvas pieces and
frame effects read to move with the music.

    kaleidophone envelope song.wav -o songpack.json

A piece rendered at any frame rate reads frame `round(t * 100)` of each
envelope, so one pack drives a 24 fps film, a 30 fps reel and a live canvas
identically. That is the point of computing it once: the picture gets
re-rendered many times, and every render has to agree with every other one
about where the beats are. Every release before this module re-wrote the
same envelope script by hand, and the copies had drifted apart -- different
band edges, different normalisation, one labelling each frame by where its
window starts and another by its centre. This is the version they converge
on.

Format (`"kaleidophone": "songpack/1"`): `fps`, `dur`, the tempo grid (`bpm`,
`beat0`, `period`, `beats`, `downbeat`), five band levels (`bass` 20-150 Hz,
`lowmid` 150-400, `mid` 400-2000, `high` 2000-6000, `air` 6000-16000), `rms`
and `rmsdb`, three spectral-flux envelopes (`flux`, `bflux`, `hflux`), the
spectral centroid (`cent`), `voc` for stereo input only (and `voc_source`,
where it came from), `loudest`, the loudest 60 s window, and `grid_check`,
what the analysis is unsure of. Every envelope is 0..1 unless its name says
otherwise: `rmsdb` is in dB, and the flux envelopes may exceed 1 (see
_flux_envelope).

Session in (TECHNIQUES #55): the artist's DAW session knows what the master
can only be guessed from. Given its MIDI (`--midi`, read by audio/midi.py),
the grid is the session's -- every quarter note of its tempo map, its felt
pulse (`pulses`: the dotted quarter in 6/8), bar 1 on its bar lines or where
`--downbeat` says -- placed on the master where its notes line up with the
master's onsets, and the pack gains `midi` (the file, the offset and how sure
it is, the tempo map, the time signatures, the tracks) and `events`: every
note (`events.midi.<track>`) and every chord change (`events.chords.<track>`)
in seconds on the master's clock. Given stems (`--stem NAME=path`), each is
lined up with the master (_align_stems: a mastered bounce is often trimmed or
padded at the head, and its stems aren't) and gets the master's envelopes
under `stems.<name>`, and the vocal stem's level replaces the mid-side `voc`
proxy. Nothing else in the pack changes meaning, so a 0.3 reader still
reads a 0.4 pack.

Why numpy and ffmpeg rather than librosa (audio/analysis.py): this runs on
whatever machine the WAV lives on, often a small VM, and has to be fast there.
It also wants a different answer. librosa's beat tracker returns the beats it
detected, one by one; a piece wants a *grid* -- `beat0 + k * period` -- that it
can extrapolate into a fade-out or a silent intro where there is nothing to
detect. analysis.py stays what `compose` uses.

Decisions that are not obvious from the code:

- Frames are centred: frame i is the window centred on i/100 s. Labelling a
  frame by where its window *starts* puts every envelope ~21 ms ahead of the
  audio at 48 kHz -- half a frame at 24 fps, on every beat of the song.
- Levels are in dB, floored at FLOOR_DB, then percentile-normalised per
  envelope (5th percentile -> 0, 99.5th -> 1). Per envelope, so a quiet air
  band still spans its full range and still drives something. The 5th
  percentile, so fades and the noise floor read as nothing; the 99.5th, so one
  peak doesn't flatten the rest of the song. The floor is what keeps that
  honest: FFT leakage from a loud bass note lands far below anything audible
  in the high bands, and the normalisation would otherwise stretch it into a
  signal that isn't there.
- The spectrogram never exists in full. Frames are strided views into the
  signal, windowed and transformed a block at a time (_CHUNK), so memory
  stays a small multiple of the decoded PCM however long the song is. Held
  whole, 4 minutes of float32 magnitudes would add another ~100 MB per
  channel (arithmetic: 24,000 frames x 1,025 bins x 4 bytes).
- A fixed grid is a claim about the song, and the pack says how far to trust
  it (`grid_check`): the octave the tempo search nearly chose instead, how
  far the music's pulse sits from the grid in every 8-bar section, and how
  sure the downbeat is. A grid a person corrects with `--bpm-range` or
  `--downbeat` is cheaper than a film cut to the wrong one.
"""

from __future__ import annotations

import errno
import functools
import itertools
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from kaleidophone.audio.midi import (
    ALIGN_MIN_R,
    ALIGN_SEARCH,
    EDGE,
    Alignment,
    MidiFile,
    SessionGrid,
    align,
    chord_events,
    correlation_at,
    is_harmonic,
    onset_impulses,
    reachable,
    read_midi,
    session_grid,
)
from kaleidophone.render._ffmpeg_util import decode_f32le, probe_stream

SONGPACK_FORMAT = "songpack/1"

FPS = 100
SAMPLE_RATE = 48000
# 2048 samples at 48 kHz: 42.7 ms, long enough to resolve the bass band
# (23 Hz bins), short enough that a kick doesn't smear across three beats.
WINDOW = 2048

BANDS: dict[str, tuple[float, float]] = {
    "bass": (20.0, 150.0),
    "lowmid": (150.0, 400.0),
    "mid": (400.0, 2000.0),
    "high": (2000.0, 6000.0),
    "air": (6000.0, 16000.0),
}
# (lo, hi) in Hz for each flux envelope: everything up to the air band's top,
# the kick/bass region, and the hats/cymbals region.
FLUX_BANDS: dict[str, tuple[float, float]] = {
    "flux": (20.0, 16000.0),
    "bflux": (20.0, 150.0),
    "hflux": (2000.0, 16000.0),
}
VOCAL_BAND = (250.0, 3500.0)

FLOOR_DB = -100.0
DEFAULT_BPM_RANGE = (60.0, 200.0)
DEFAULT_BEATS_PER_BAR = 4
LOUDEST_SECONDS = 60
# Half a frame at 24 fps: a grid further than this from the music puts a cut
# on the wrong frame. The same tolerance `master-check` uses.
GRID_TOLERANCE = 1.0 / 48.0
GRID_SECTION_BARS = 8

_CHUNK = 1024  # frames per STFT block -- see the module docstring
_FLUX_CEILING = 1.5
_CENTROID_SCALE = 8000.0
# Mid-over-side contrast is clipped here before normalising: a passage that
# is mono in an otherwise stereo mix has no side at all, and its unbounded
# contrast would set the 99.5th percentile for the whole song.
_VOC_CONTRAST_LIMIT_DB = 30.0
# Side this far below mid over the whole song means the two channels are the
# same signal -- see _vocal_envelope.
_DUAL_MONO_DB = -60.0

# The octave tie-breaker in estimate_tempo(): librosa.feature.tempo's default
# prior (start_bpm=120, std_bpm=1.0), cited rather than re-derived.
_PRIOR_BPM = 120.0
_PRIOR_OCTAVES = 1.0
# +-1.5% around each autocorrelation candidate: neighbouring whole-frame lags
# are ~2% apart at these tempos, and the parabolic peak lands far closer.
_COMB_SPAN = 0.015
_AUTOCORR_CANDIDATES = 4
# Off-beats carrying at least this share of the beats' onset energy mean the
# pulse is twice as fast -- see estimate_tempo().
_DOUBLE_EVIDENCE = 0.85
# An octave alternative scoring at least this share of the chosen grid's
# (prior included) is a close call, and the pack says so.
_OCTAVE_CLOSE = 0.9
_FLUX_LEAD_FRAMES = 1  # see _measure()

# The grid check: a section's comb must collect this many times the onset of
# the average offset before its best offset counts as the pulse -- a beatless
# intro has no pulse to be early or late against (see grid_fit).
_PULSE_CONTRAST = 4.0
# Bars per vote in the downbeat's confidence, and the confidence below which
# the pack calls bar 1 a guess.
_DOWNBEAT_BLOCK_BARS = 4
_DOWNBEAT_SURE = 0.6
# Harmony is read from 27.5 Hz (A0) to 1 kHz: bass notes and chords, not the
# melody's upper harmonics.
_CHROMA_BAND = (27.5, 1000.0)

# Session in. A stem named one of these (any case) is the voice, and becomes
# `voc`, unless --voc-stem names another. Once lined up (_align_stems), a stem
# must end where the master does to within STEM_TOLERANCE s: a DAW bounces
# every stem over one range, and a stem much shorter or longer than that was
# bounced over another -- a verse alone, a different version. Inside the
# tolerance its tail is padded or trimmed.
VOCAL_STEMS = ("vocals", "vocal", "vox", "voice")
STEM_TOLERANCE = 0.5
_STEM_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
# The most tempo changes a warning lists by name.
_LISTED_CHANGES = 5
# A given --midi-offset is used as given; the notes are only checked this far
# either side of it, for an offset a little off by ear.
_GIVEN_CHECK = 0.5
# A MIDI file whose last event is further than this past the song's end is
# refused: not a parked region or a long session, a corrupt length.
_MIDI_REACH = 24 * 3600.0

# Stem alignment (_align_stems): lags within +-STEM_SEARCH s are searched, in
# 1/6-octave bands from 40 Hz to 16 kHz. A stem lines up when its correlation
# with the master reaches STEM_MIN_R and beats the best distinct other lag
# (more than 50 ms away) by STEM_MIN_MARGIN; how they were set is in
# _align_stems. Stems whose lags agree to within _STEM_AGREE s were bounced
# together.
STEM_SEARCH = 2.0
STEM_MIN_R = 0.2
STEM_MIN_MARGIN = 0.05
_STEM_AGREE = 0.02
_ALIGN_BANDS_PER_OCTAVE = 6
_ALIGN_RANGE = (40.0, 16000.0)


# --------------------------------------------------------------------------
# public entry points
# --------------------------------------------------------------------------
def envelope(
    path: str,
    *,
    bpm_range: tuple[float, float] = DEFAULT_BPM_RANGE,
    downbeat: float | None = None,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
    midi: str | None = None,
    midi_offset: float | None = None,
    stems: Mapping[str, str] | None = None,
    stem_offsets: Mapping[str, float] | None = None,
    voc_stem: str | None = None,
) -> dict:
    """Decode `path` with ffmpeg and build its song pack.

    Decodes at 48 kHz so the analysis is identical whatever rate the master
    was bounced at. Mono stays mono (and gets no `voc`); anything with two or
    more channels is decoded as stereo. If ffprobe isn't available to say
    which, the file is decoded as stereo -- a mono source then arrives as two
    identical channels, which _vocal_envelope already treats as mono.

    `midi` is the session's MIDI file and `stems` maps a name to a stem's
    audio file (see analyze_signal). Every path is checked, and the MIDI read,
    before anything is decoded; the stems are decoded one at a time, so a
    session's worth of them never sits in memory at once (twice each, when one
    has to be moved to line up: once to find its lag, once to measure it there).
    """
    for p in (path, midi, *(stems or {}).values()):
        if p is not None and not os.path.exists(p):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), p)
    _check_session_args(midi, midi_offset, downbeat, stems, stem_offsets, voc_stem)
    session: dict = {}
    if midi is not None:
        session.update(midi=read_midi(midi), midi_offset=midi_offset)
    if stems:
        session["stems"] = {name: functools.partial(_decode, p) for name, p in stems.items()}
        session.update(stem_offsets=stem_offsets, voc_stem=voc_stem)
    return analyze_signal(
        _decode(path),
        SAMPLE_RATE,
        bpm_range=bpm_range,
        downbeat=downbeat,
        beats_per_bar=beats_per_bar,
        **session,
    )


def _decode(path: str) -> np.ndarray:
    """`path` as float32 samples at SAMPLE_RATE: (n,) mono or (n, 2) stereo."""
    channels = 1 if probe_stream(path, "a:0", "channels") == "1" else 2
    pcm = decode_f32le(path, sample_rate=SAMPLE_RATE, channels=channels)
    samples = np.frombuffer(pcm, dtype="<f4")
    if channels == 2:
        samples = samples[: len(samples) // 2 * 2].reshape(-1, 2)
    if len(samples) == 0:
        raise ValueError(f"{path}: ffmpeg decoded no audio from it -- does it have an audio stream?")
    return samples


def analyze_signal(
    samples: np.ndarray,
    sr: int = SAMPLE_RATE,
    *,
    bpm_range: tuple[float, float] = DEFAULT_BPM_RANGE,
    downbeat: float | None = None,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
    midi: MidiFile | None = None,
    midi_offset: float | None = None,
    stems: Mapping[str, np.ndarray | Callable[[], np.ndarray]] | None = None,
    stem_offsets: Mapping[str, float] | None = None,
    voc_stem: str | None = None,
) -> dict:
    """The song pack for `samples`: shape (n,) for mono or (n, 2) for stereo.

    Pure: no file, no subprocess. Everything envelope() does after decoding
    happens here, which is what lets the tests feed it synthetic signals.
    The result is JSON-ready -- plain lists of rounded floats -- so what a
    test inspects is exactly what write_songpack() writes.

    `downbeat` (seconds) is bar 1 when a person knows it; left out, it is
    estimated (estimate_downbeat) and `grid_check` says how sure that is.

    `midi` (audio/midi.py's MidiFile) is the session's MIDI: the grid comes
    from it instead of from the tempo search, placed at `midi_offset` seconds
    (master time = MIDI time + offset) or, left out, wherever its notes line
    up best with the master's onsets (_session). Bar 1 is then the MIDI's
    first bar line in the song, or `downbeat` when given -- a clip exported
    from a pickup, whose tick 0 isn't a bar line -- with the bars following
    the MIDI's meter from there; `beats_per_bar` only stands in for a MIDI
    file with no time signature. `stems` maps a name to a stem's samples at
    `sr`, or to a function that returns them (decoded when its turn comes);
    each is lined up with the master, or moved by `stem_offsets[name]`
    seconds (master time = stem time + offset), and analysed like the master
    (_stems). `voc_stem` names the stem that becomes `voc`; left out, one
    named in VOCAL_STEMS does.
    """
    if beats_per_bar < 1:
        raise ValueError(f"--beats-per-bar must be at least 1, got {beats_per_bar}")
    _check_session_args(midi, midi_offset, downbeat, stems, stem_offsets, voc_stem)
    mid, side = _split_channels(samples)
    dur = len(mid) / sr
    if dur < 2.0:
        raise ValueError(
            f"{dur:.2f}s of audio is too short for a song pack -- the tempo "
            f"search needs a few seconds of music to lock onto."
        )
    if downbeat is not None and not 0.0 <= downbeat < dur:
        raise ValueError(f"--downbeat must be a time inside the song (0 to {dur:.2f} s), got {downbeat:g}")

    raw = _measure(mid, side, sr, bands=BANDS, flux=True, align=bool(stems))
    fluxes = {name: _flux_envelope(values) for name, values in raw.flux.items()}

    onset = onset_strength(raw.tempo_flux)
    session = None
    if midi is None:
        tempo = estimate_tempo(onset, bpm_range=bpm_range)
        beats = tempo.beats(dur)
        if downbeat is None:
            bar1 = estimate_downbeat(
                beats, fluxes["bflux"], harmonic_novelty(mid, sr, beats), beats_per_bar=beats_per_bar
            )
        else:
            bar1 = Downbeat(t=float(downbeat), confidence=None, runner_up=None, source="given")
        bar_seconds = beats_per_bar * tempo.period
        grid = {
            "bpm": round(tempo.bpm, 2),
            "beat0": round(tempo.beat0, 4),
            "period": round(tempo.period, 6),
            "beats": _rounded(beats, 4),
            "downbeat": round(bar1.t, 4),
        }
    else:
        if not np.any(onset > 0):
            raise ValueError("no onsets to line the MIDI up with -- is the audio silent?")
        session = _session(midi, midi_offset, onset, dur, beats_per_bar, downbeat)
        beats = session.grid.beats
        period = 60.0 / session.grid.bpm
        grid = {
            # More decimals than an estimated grid: the tempo is known, not measured.
            "bpm": round(session.grid.bpm, 4),
            "beat0": round(float(beats[0]) if len(beats) else session.grid.downbeat, 4),
            "period": round(period, 6),
            "beats": _rounded(beats, 4),
            "downbeat": round(session.grid.downbeat, 4),
            "pulses": _rounded(session.grid.pulses, 4),
            "pulses_per_bar": session.grid.pulses_per_bar,
        }

    cent = np.clip(raw.centroid_hz / _CENTROID_SCALE, 0.0, 1.0)
    cent[raw.rms_db <= FLOOR_DB] = 0.0  # the centroid of silence is noise

    pack: dict = {"kaleidophone": SONGPACK_FORMAT, "fps": FPS, "dur": round(dur, 3), **grid}
    for name in BANDS:
        pack[name] = _rounded(percentile_normalize(raw.bands_db[name]), 3)
    pack["rms"] = _rounded(percentile_normalize(raw.rms_db), 3)
    pack["rmsdb"] = _rounded(raw.rms_db, 1)
    for name in FLUX_BANDS:
        pack[name] = _rounded(fluxes[name], 3)
    pack["cent"] = _rounded(cent, 3)

    stem_packs, lined_up, stem_warnings = {}, {}, []
    if stems:
        stem_packs, lined_up, stem_warnings = _stems(stems, sr, len(mid), raw, stem_offsets or {})
    vocal = voc_stem or next((name for name in stem_packs if name.lower() in VOCAL_STEMS), None)
    if vocal is not None:
        pack["voc"] = list(stem_packs[vocal]["rms"])
        pack["voc_source"] = "stem"
    elif raw.vocal_side_db is not None:
        pack["voc"] = _rounded(_vocal_envelope(raw.vocal_mid_db, raw.vocal_side_db, raw.side_to_mid_db), 3)
        pack["voc_source"] = "mid-side proxy"
    if session is not None:
        pack["midi"] = session.info
        pack["events"] = session.events
    if stem_packs:
        pack["stems"] = stem_packs
        pack["stems_alignment"] = lined_up

    if session is None:
        pack["loudest"] = _loudest_window(raw.rms_db, bar1.t, bar_seconds, dur)
        sections = grid_fit(onset, beats, tempo.period, bar1.t, beats_per_bar)
        pack["grid_check"] = _grid_check(tempo, bar1, beats, sections, beats_per_bar, bpm_range)
    else:
        g = session.grid
        quarters = _quarters_per_bar(g)
        pack["loudest"] = _loudest_window(
            raw.rms_db, g.downbeat, quarters * period, dur, bar_lines=[bar[0] for bar in g.bars]
        )
        sections = grid_fit(
            onset,
            beats,
            period,
            g.downbeat,
            max(1, round(quarters)),
            bar_of_beat=g.beat_bars - g.downbeat_bar + 1,
        )
        pack["grid_check"] = _session_check(session, sections, quarters)
    pack["grid_check"]["warnings"].extend(stem_warnings)
    return pack


def _check_session_args(midi, midi_offset, downbeat, stems, stem_offsets=None, voc_stem=None) -> None:
    """Refuse what can't go together, before anything is decoded."""
    if midi_offset is not None and midi is None:
        raise ValueError("--midi-offset places the MIDI on the master: it needs --midi")
    for flag, value in (("--midi-offset", midi_offset), ("--downbeat", downbeat)):
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{flag} must be a number of seconds, got {value}")
    for name in stems or {}:
        if not _STEM_NAME.match(name):
            raise ValueError(
                f"stem name {name!r}: use letters, digits, '-' and '_' -- it becomes the pack's key stems.{name}"
            )
    for name, value in (stem_offsets or {}).items():
        if name not in (stems or {}):
            raise ValueError(f"--stem-offset {name}=... names no stem: give it with --stem {name}=PATH")
        if not math.isfinite(value):
            raise ValueError(f"--stem-offset {name} must be a number of seconds, got {value}")
    if voc_stem is not None and voc_stem not in (stems or {}):
        raise ValueError(f"--voc-stem {voc_stem} names no stem: give it with --stem {voc_stem}=PATH")


def write_songpack(pack: dict, path: str) -> str:
    """Write a pack as compact JSON. A 4-minute song is ~24k frames per
    envelope, so the separators are worth dropping."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    return str(out)


def load_songpack(path: str) -> dict:
    """Read a pack back, refusing anything that isn't one.

    The format tag is checked rather than trusted because the older,
    hand-rolled envelope files look almost identical -- same keys, a
    different frame convention -- and silently driving a render from one
    would put every beat in the wrong place.
    """
    with open(path, encoding="utf-8") as fh:
        pack = json.load(fh)
    tag = pack.get("kaleidophone") if isinstance(pack, dict) else None
    if tag != SONGPACK_FORMAT:
        raise ValueError(
            f"{path} is not a {SONGPACK_FORMAT} song pack (format tag: {tag!r}). "
            f"Regenerate it with `kaleidophone envelope <audio> -o {os.path.basename(path)}`."
        )
    return pack


def level_envelopes(
    samples: np.ndarray, sr: int, bands: dict[str, tuple[float, float]]
) -> dict[str, np.ndarray]:
    """Band levels (dB, floored at FLOOR_DB) at 100 Hz, plus `"rms"`.

    The raw material of the pack before normalisation, for callers that need
    to compare two files on one scale rather than drive a picture. Stereo
    input is folded to mid first.
    """
    mid, _ = _split_channels(samples)
    raw = _measure(mid, None, sr, bands=bands, flux=False)
    return {**raw.bands_db, "rms": raw.rms_db}


def raw_envelopes(
    samples: np.ndarray, sr: int = SAMPLE_RATE, *, extra_bands: dict[str, tuple[float, float]] | None = None
) -> dict[str, np.ndarray]:
    """Every per-frame envelope of the pack before it is normalised.

    For comparing two files on one scale -- audio/mastercheck.py -- rather
    than driving a picture: the five bands, `rms` and any `extra_bands` in dB
    (floored at FLOOR_DB); `flux`, `bflux` and `hflux` as raw sums, already
    moved onto the attack (see _measure); `cent` in Hz; and, for stereo input
    that isn't dual mono, `voc` as the vocal band's centre-over-sides contrast
    in dB (clipped at +-30, the bottom of the range where the band is silent).
    One STFT pass, no tempo search.
    """
    mid, side = _split_channels(samples)
    raw = _measure(mid, side, sr, bands={**BANDS, **(extra_bands or {})}, flux=True)
    out: dict[str, np.ndarray] = {**raw.bands_db, "rms": raw.rms_db, **raw.flux, "cent": raw.centroid_hz}
    if raw.vocal_side_db is not None and raw.side_to_mid_db > _DUAL_MONO_DB:
        contrast = np.clip(
            raw.vocal_mid_db - raw.vocal_side_db, -_VOC_CONTRAST_LIMIT_DB, _VOC_CONTRAST_LIMIT_DB
        )
        contrast[raw.vocal_mid_db <= FLOOR_DB] = -_VOC_CONTRAST_LIMIT_DB
        out["voc"] = contrast
    return out


def percentile_normalize(values, lo: float = 5.0, hi: float = 99.5, *, mask=None) -> np.ndarray:
    """Map the `lo` percentile to 0 and the `hi` percentile to 1, clipped.

    A flat envelope maps to all zeros rather than being divided by nothing:
    a band with no movement carries no information, and stretching float
    noise to full scale would manufacture some. `mask` restricts which frames
    set the percentiles -- every frame is still mapped.
    """
    x = np.asarray(values, dtype=np.float64)
    ref = x if mask is None else x[np.asarray(mask, dtype=bool)]
    if ref.size == 0:
        return np.zeros_like(x)
    a, b = np.percentile(ref, [lo, hi])
    if not b - a > 1e-9:
        return np.zeros_like(x)
    return np.clip((x - a) / (b - a), 0.0, 1.0)


# --------------------------------------------------------------------------
# tempo
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Tempo:
    """A fixed beat grid: beat k is at `beat0 + k * period` seconds.

    `alt_bpm` is the other octave the search weighed -- half or double -- and
    `alt_score` its score over the chosen grid's, the tempo prior included:
    near 1 is a coin toss, above 1 means the off-beat evidence overruled the
    prior (estimate_tempo). None when neither octave fits the range.
    """

    bpm: float
    beat0: float
    period: float
    score: float
    alt_bpm: float | None = None
    alt_score: float | None = None

    def beats(self, duration: float) -> np.ndarray:
        """Every grid beat in [0, duration)."""
        if duration <= self.beat0:
            return np.zeros(0)
        count = math.ceil((duration - self.beat0) / self.period)
        return self.beat0 + self.period * np.arange(count)


def onset_strength(flux: np.ndarray, *, fps: int = FPS) -> np.ndarray:
    """Spectral flux with its local average removed, rectified, lightly smoothed.

    Removing a 0.5 s moving average is what lets a quiet verse's hi-hats count
    as much as a loud chorus's: the comb in estimate_tempo() should find the
    pulse, not the loudest section. The 3-frame smoothing lets a comb tooth
    that lands a frame off an onset still collect it.
    """
    flux = np.asarray(flux, dtype=np.float64)
    width = max(1, round(fps * 0.5))
    local = np.convolve(flux, np.ones(width) / width, mode="same")
    onset = np.maximum(flux - local, 0.0)
    return np.convolve(onset, np.ones(3) / 3.0, mode="same")


def estimate_tempo(
    onset: np.ndarray,
    *,
    fps: int = FPS,
    bpm_range: tuple[float, float] = DEFAULT_BPM_RANGE,
) -> Tempo:
    """The beat grid: the tempo and phase whose comb best fits `onset`.

    Two stages, because each is good at what the other is bad at.
    Autocorrelation of the onset envelope finds the few periods the song
    repeats at, but only to the nearest frame -- at 120 BPM one 10 ms lag step
    is 2.4 BPM wide. The comb search then walks each candidate in 0.01 BPM
    steps with the phase free, and keeps the grid that lands on the most onset
    energy. 0.01 BPM because the grid is extrapolated across the whole song:
    at 120 BPM an error of 0.01 BPM moves the 480th beat by 20 ms, half a
    frame at 24 fps (arithmetic, not a measurement).

    The octave check: a comb that hits every beat and one that hits every
    other beat score the same on an evenly accented track, so every
    candidate is also tried at half and double speed, and rivals are weighed
    with librosa's own log-normal tempo prior (centred on 120 BPM, one octave
    wide). The prior alone would call a 174 BPM click track 87 -- 87 is the
    nearer of the two to 120 -- so it gets one piece of evidence on top: if the
    chosen grid's off-beats carry nearly as much onset as its beats, the
    pulse is the double, and the grid moves up to it.

    That settles clicks, not music. On synthetic genre patterns (measured,
    not representative of real songs) a 70 BPM ballad of 8th-note piano came
    back at 140 with the two octaves 1% apart, and a 174 BPM drum-and-bass
    two-step at 87 -- every beat landing on the snare. So the octave that lost
    is reported with its score (`alt_bpm`, `alt_score`), and `bpm_range` is
    the lever: `--bpm-range 50 100` for the ballad, `150 190` for the DnB.
    """
    lo, hi = float(bpm_range[0]), float(bpm_range[1])
    if not 0.0 < lo <= hi:
        raise ValueError(f"bpm range must satisfy 0 < lo <= hi, got {lo:g}..{hi:g}")
    onset = np.asarray(onset, dtype=np.float64)
    slowest = 60.0 * fps / lo  # frames per beat at the slow end
    if len(onset) < 2 * slowest:
        raise ValueError(
            f"{len(onset) / fps:.1f}s is too short to find a tempo down to {lo:g} BPM -- "
            f"it needs at least two beats ({2 * 60.0 / lo:.1f}s). Narrow --bpm-range."
        )
    if not np.any(onset > 0):
        raise ValueError("no onsets to find a beat in -- is the audio silent?")

    # Clamped, not filtered: parabolic interpolation can nudge a peak at the
    # edge of the range just outside it, and a fixed tempo (lo == hi) must
    # still have its one candidate. Octave rivals outside the range are
    # simply not tempos the caller allowed.
    candidates = [min(max(c, lo), hi) for c in _autocorr_candidates(onset, fps, lo, hi)]
    octaves = [c * f for c in candidates for f in (2.0, 0.5)]
    pool = _dedupe(candidates + [c for c in octaves if lo <= c <= hi])

    tried: list[tuple[float, float, float]] = []  # (weighted, bpm, phase) of every candidate
    best = None
    for centre in pool:
        _, bpm, phase = _comb_search(onset, fps, centre, lo, hi)
        score, bpm, phase = _refine(onset, fps, bpm, phase, lo, hi)
        weighted = score * _tempo_prior(bpm)
        tried.append((weighted, bpm, phase))
        if best is None or weighted > best[0]:
            best = (weighted, score, bpm, phase)
    _, score, bpm, phase = best

    while bpm * 2.0 <= hi + 1e-9:
        period = 60.0 * fps / bpm
        if _comb_mean(onset, period, phase + period / 2.0) < _DOUBLE_EVIDENCE * score:
            break
        score, bpm, phase = _refine(onset, fps, bpm * 2.0, phase, lo, hi)

    alt_bpm, alt_score = _octave_alternative(onset, fps, bpm, score, lo, hi, tried)
    period_s = 60.0 / bpm
    beat0 = phase / fps
    # A phase within a frame of wrapping is a beat at 0.0, not one a whole
    # period later: reported as the latter, the song's first beat vanishes.
    if period_s - beat0 < 1.0 / fps:
        beat0 = 0.0
    return Tempo(bpm=bpm, beat0=beat0, period=period_s, score=score, alt_bpm=alt_bpm, alt_score=alt_score)


def _octave_alternative(
    onset: np.ndarray,
    fps: int,
    bpm: float,
    score: float,
    lo: float,
    hi: float,
    tried: list[tuple[float, float, float]],
) -> tuple[float | None, float | None]:
    """(bpm, score over the chosen grid's) of the better of half and double
    time, prior included; (None, None) if neither is inside the range."""
    chosen = score * _tempo_prior(bpm)
    best: tuple[float, float] | None = None
    for factor in (0.5, 2.0):
        target = bpm * factor
        # With the comb's own slack: 119.99 BPM's half, 59.995, is still the
        # 60 BPM grid a range starting at 60 allows.
        if not lo * (1.0 - _COMB_SPAN) <= target <= hi * (1.0 + _COMB_SPAN):
            continue
        near = [t for t in tried if abs(t[1] - target) <= _COMB_SPAN * target]
        if near:
            weighted, alt, _ = max(near)
        else:
            _, alt, phase = _comb_search(onset, fps, min(max(target, lo), hi), lo, hi)
            alt_score, alt, _ = _refine(onset, fps, alt, phase, lo, hi)
            weighted = alt_score * _tempo_prior(alt)
        if best is None or weighted > best[0]:
            best = (weighted, alt)
    if best is None or chosen <= 0.0:
        return None, None
    return best[1], best[0] / chosen


def _autocorr_candidates(onset: np.ndarray, fps: int, lo: float, hi: float) -> list[float]:
    """The strongest autocorrelation peaks inside the tempo range, as BPM."""
    centred = onset - onset.mean()
    n = len(centred)
    size = 1 << (2 * n - 1).bit_length()
    spectrum = np.fft.rfft(centred, size)
    ac = np.fft.irfft(spectrum * np.conj(spectrum), size)[:n]
    first = max(1, math.floor(60.0 * fps / hi))
    last = min(n - 2, math.ceil(60.0 * fps / lo))
    if last <= first:
        return [(lo + hi) / 2.0]
    lags = np.arange(first, last + 1)
    peaks = [lag for lag in lags if ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1]]
    if not peaks:
        peaks = [int(lags[np.argmax(ac[lags])])]
    peaks.sort(key=lambda lag: ac[lag], reverse=True)

    bpms = []
    for lag in peaks[:_AUTOCORR_CANDIDATES]:
        # Parabolic interpolation: the true period is rarely a whole frame.
        left, mid, right = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = left - 2.0 * mid + right
        shift = 0.5 * (left - right) / denom if denom < 0 else 0.0
        bpms.append(60.0 * fps / (lag + shift))
    return bpms


def _dedupe(bpms: list[float], tolerance: float = 0.015) -> list[float]:
    kept: list[float] = []
    for bpm in bpms:
        if all(abs(bpm - k) > tolerance * k for k in kept):
            kept.append(bpm)
    return kept


def _tempo_prior(bpm: float) -> float:
    return math.exp(-0.5 * (math.log2(bpm / _PRIOR_BPM) / _PRIOR_OCTAVES) ** 2)


def _bpm_grid(lo: float, hi: float) -> np.ndarray:
    """Every 0.01 BPM step in [lo, hi]; just `lo` if the range is narrower."""
    first = math.ceil(lo * 100.0 - 1e-6)
    last = math.floor(hi * 100.0 + 1e-6)
    return np.arange(first, last + 1) / 100.0 if first <= last else np.array([lo])


def _comb_search(
    onset: np.ndarray, fps: int, centre: float, lo: float, hi: float
) -> tuple[float, float, float]:
    """Best (score, bpm, phase in frames) within +-_COMB_SPAN of `centre`.

    The phase is found by folding: every frame is binned by its position
    within one beat period, and the bin with the most onset energy per beat
    is the phase. That is one pass over the envelope per tempo, instead of
    one per (tempo, phase) pair -- and only over frames with any onset in
    them, since the rest add nothing to any bin.
    """
    grid = _bpm_grid(max(lo, centre * (1.0 - _COMB_SPAN)), min(hi, centre * (1.0 + _COMB_SPAN)))
    active = np.flatnonzero(onset > 0)
    positions = active.astype(np.float64)
    weights = onset[active]
    n = len(onset)

    best = (-1.0, float(grid[0]), 0.0)
    for bpm in grid:
        period = 60.0 * fps / bpm
        nbins = max(1, round(period))
        bins = np.minimum((np.mod(positions, period) * (nbins / period)).astype(np.int64), nbins - 1)
        # Bins are equal-width slices of one period, so each holds n / nbins
        # frames to within one: dividing by that instead of counting is exact
        # enough to rank phases and skips a second pass.
        means = np.bincount(bins, weights=weights, minlength=nbins) * (nbins / n)
        b = int(np.argmax(means))
        if means[b] > best[0]:
            best = (float(means[b]), float(bpm), (b + 0.5) * period / nbins)
    return best


def _comb_mean(onset: np.ndarray, period: float, phase: float) -> float:
    """Mean onset under the comb `phase + k * period`, sampled between frames."""
    p = phase % period
    teeth = p + period * np.arange(int((len(onset) - 1 - p) // period) + 1)
    return float(np.interp(teeth, np.arange(len(onset)), onset).mean())


def _refine(
    onset: np.ndarray, fps: int, bpm: float, phase: float, lo: float, hi: float
) -> tuple[float, float, float]:
    """Polish a folded (bpm, phase) with the comb sampled between frames.

    Folding scores a phase to the nearest frame, which leaves a flat top a
    few hundredths of a BPM wide: on a short clip, 119.96 and 120.00 fold
    identically. Sampling the envelope *between* frames separates them. The
    grid pivots on the beat nearest the middle of the song rather than on
    frame 0, so nudging the tempo swings both ends a little instead of
    throwing the far end a long way off -- and the phase search can stay
    narrow.
    """
    n = len(onset)
    frames = np.arange(n)
    period0 = 60.0 * fps / bpm
    middle = phase + round(((n - 1) / 2.0 - phase) / period0) * period0
    centres = middle + np.arange(-1.5, 1.5001, 0.1)
    best = (-1.0, bpm, phase % period0)
    for candidate in _bpm_grid(max(lo, bpm - 0.10), min(hi, bpm + 0.10)):
        period = 60.0 * fps / candidate
        reach = math.ceil(n / period) + 1
        teeth = centres[:, None] + period * np.arange(-reach, reach + 1)[None, :]
        inside = (teeth >= 0) & (teeth <= n - 1)
        sampled = np.interp(teeth, frames, onset) * inside
        scores = sampled.sum(axis=1) / np.maximum(inside.sum(axis=1), 1)
        i = int(np.argmax(scores))
        if scores[i] > best[0]:
            best = (float(scores[i]), float(candidate), float(centres[i] % period))
    return best


# --------------------------------------------------------------------------
# how well the grid fits
# --------------------------------------------------------------------------
def grid_fit(
    onset: np.ndarray,
    beats: np.ndarray,
    period: float,
    downbeat: float,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
    *,
    fps: int = FPS,
    bars: int = GRID_SECTION_BARS,
    bar_of_beat: np.ndarray | None = None,
) -> list[dict]:
    """How far the music's pulse sits from the grid, one `bars`-bar section at a time.

    A fixed grid is only as good as the tempo is steady. Per section, a comb
    of the section's grid beats is slid across one whole period (2 ms steps,
    the onset sampled between frames) and stretched by up to +-3% about the
    section's middle beat, and the fit that collects the most onset is where
    the section's pulse actually is. The stretch is what lets a section whose
    tempo is moving be measured at all: held rigid, the comb smears across a
    drifting beat and finds nothing. Every section reports, in ms, where the
    music sits against the grid at its middle beat (`offset_ms`, > 0 = the
    music is late), the worst beat in it (`max_ms`), and its own tempo
    (`bpm`). The grid's own tempo is kept unless a stretch collects clearly
    more (5%), so an ordinary groove's humanising can't fake a drift.

    A section whose best fit doesn't stand out from the average over all
    offsets (_PULSE_CONTRAST, 4x: measured 5.7-16 on pulsed synthetic
    sections, 2.9 on a beatless intro of random chimes) has no pulse to be
    early or late against and gets None -- a beatless intro, a breakdown.
    Sections count bars from `downbeat`: bars 1-8, 9-16, ..., and the bars
    before bar 1, if any, as one pickup section. `bar_of_beat` (1 = bar 1,
    <= 0 before it) numbers the bars instead when they aren't all one length
    -- a MIDI grid whose time signature changes -- and each section's `bpm` is
    measured from its own beats, so a tempo map's sections read their own.
    """
    beats = np.asarray(beats, dtype=np.float64)
    bar = beats_per_bar * period
    if len(beats) == 0 or not bar > 0:
        return []
    frames = np.arange(len(onset))
    offsets = np.arange(-period / 2.0, period / 2.0, 0.002)
    stretches = 1.0 + 0.0025 * np.arange(-12, 13)
    if bar_of_beat is None:
        index = np.floor((beats - downbeat) / bar + 1e-9).astype(int) + 1  # the bar each beat is in
    else:
        index = np.asarray(bar_of_beat, dtype=int)
    groups: dict[int, list[int]] = {}
    for i, b in enumerate(index):
        key = 0 if b <= 0 else (b - 1) // bars + 1
        groups.setdefault(key, []).append(i)

    sections = []
    for key in sorted(groups):
        members = beats[groups[key]]
        fit = (
            _section_fit(onset, frames, members, offsets, stretches, fps)
            if len(members) >= 2 * beats_per_bar
            else None
        )
        section = {
            "bars": [int(index[groups[key][0]]), int(index[groups[key][-1]])],
            "start": round(float(max(0.0, members[0])), 3),
            "end": round(float(members[-1] + period), 3),
            "offset_ms": None,
            "max_ms": None,
            "bpm": None,
            "beats": len(members),
            "off": None,
        }
        if fit is not None:
            stretch, shift, deviations = fit
            own = float(np.median(np.diff(members)))  # the section's own beat: `period` on a fixed grid
            section.update(
                offset_ms=round(shift * 1000.0),
                max_ms=round(float(np.max(np.abs(deviations))) * 1000.0),
                bpm=round(60.0 / own / stretch, 2),
                off=int(np.sum(np.abs(deviations) > GRID_TOLERANCE)),
            )
        sections.append(section)
    return sections


def _section_fit(
    onset: np.ndarray,
    frames: np.ndarray,
    members: np.ndarray,
    offsets: np.ndarray,
    stretches: np.ndarray,
    fps: int,
) -> tuple[float, float, np.ndarray] | None:
    """(stretch, shift s, per-beat music-minus-grid s) of one section, or None
    if it has no pulse. The music's beat for grid beat m is at
    middle + (m - middle) * stretch + shift."""
    middle = members[len(members) // 2]
    # The section's own onsets only: stretched, the comb's outer teeth would
    # otherwise reach into the next section and borrow its pulse.
    period = float(np.median(np.diff(members)))
    lo = max(0, math.floor((members[0] - period / 2.0) * fps))
    hi = min(len(onset), math.ceil((members[-1] + period / 2.0) * fps) + 1)
    own, own_frames = onset[lo:hi], frames[lo:hi]
    if len(own) < 2:
        return None
    best = None  # (peak, contrast, stretch, shift)
    rigid = None
    for stretch in stretches:
        teeth = middle + (members - middle) * stretch
        comb = np.interp(
            (teeth[None, :] + offsets[:, None]) * fps, own_frames, own, left=0.0, right=0.0
        ).mean(axis=1)
        b = int(np.argmax(comb))
        average = float(comb.mean())
        entry = (
            float(comb[b]),
            float(comb[b]) / average if average > 0 else 0.0,
            float(stretch),
            float(offsets[b]),
        )
        if abs(stretch - 1.0) < 1e-9:
            rigid = entry
        if best is None or entry[0] > best[0]:
            best = entry
    if rigid is not None and rigid[0] >= best[0] / 1.05:
        best = rigid
    peak, contrast, stretch, shift = best
    if peak <= 0.0 or contrast < _PULSE_CONTRAST:
        return None
    deviations = (members - middle) * (stretch - 1.0) + shift
    return stretch, shift, deviations


# --------------------------------------------------------------------------
# the downbeat
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Downbeat:
    """Bar 1: `t` seconds, a beat of the grid unless a person gave it.

    `confidence` is the share of 4-bar blocks of the song whose own evidence
    picks the same beat of the bar (None when given); `runner_up` is the first
    beat of the next-best choice.
    """

    t: float
    confidence: float | None
    runner_up: float | None
    source: str = "estimated"


def harmonic_novelty(mid: np.ndarray, sr: int, beats: np.ndarray) -> np.ndarray:
    """How much the harmony changes going into each beat: 0 (none) .. ~1.

    Chords and bass notes change on the bar line far more often than
    anywhere else in it, and that is the bar's clearest mark when the drums
    give none -- a kick on every beat of a house track says nothing about
    which beat is the one. Each beat's audio, one beat long, gets one long
    FFT (a few Hz per bin, where the 100 Hz frames' 23 Hz bins can't tell a
    41 Hz bass note from a 49 Hz one) folded into a 12-pitch-class chroma
    over 27.5-1000 Hz; the novelty is the cosine distance from the previous
    beat's. The first beat, and a beat on either side of silence, get 0.
    """
    beats = np.asarray(beats, dtype=np.float64)
    novelty = np.zeros(len(beats))
    if len(beats) < 2:
        return novelty
    period = float(np.median(np.diff(beats)))
    length = max(64, round(period * sr))
    nfft = 1 << (length - 1).bit_length()
    window = np.hanning(length).astype(np.float32)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    select = np.flatnonzero((freqs >= _CHROMA_BAND[0]) & (freqs <= _CHROMA_BAND[1]))
    pitch_class = np.round(12.0 * np.log2(freqs[select] / 440.0)).astype(int) % 12
    fold = np.zeros((len(select), 12))
    fold[np.arange(len(select)), pitch_class] = 1.0

    signal = np.concatenate([np.asarray(mid, dtype=np.float32), np.zeros(length, dtype=np.float32)])
    starts = np.clip(np.round(beats * sr).astype(np.int64), 0, len(mid))
    chroma = np.zeros((len(beats), 12))
    for s in range(0, len(beats), 32):
        idx = starts[s : s + 32, None] + np.arange(length)[None, :]
        spectrum = np.abs(np.fft.rfft(signal[idx] * window, nfft, axis=1))[:, select]
        chroma[s : s + 32] = (spectrum * spectrum) @ fold

    energy = chroma.sum(axis=1)
    sounding = energy > max(float(energy.max()), 1e-30) * 1e-6  # within 60 dB of the loudest beat
    shape = np.sqrt(chroma / np.maximum(energy, 1e-30)[:, None])
    shape -= shape.mean(axis=1, keepdims=True)
    shape /= np.maximum(np.linalg.norm(shape, axis=1, keepdims=True), 1e-12)
    change = 1.0 - np.sum(shape[1:] * shape[:-1], axis=1)
    both = sounding[1:] & sounding[:-1]
    novelty[1:] = np.where(both, change, 0.0)
    return novelty


def estimate_downbeat(
    beats: np.ndarray,
    bflux: np.ndarray,
    novelty: np.ndarray | None = None,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
) -> Downbeat:
    """Which beat of the bar is the one, and how sure that is.

    Two kinds of evidence, each measured per bar at every beat of the bar:
    the strongest bass-band onset within 3 frames of the beat (kicks land on
    the one more than anywhere else in most grooves), and the harmonic
    novelty going into it (harmonic_novelty: chords and bass notes change on
    the bar line). Each is centred within its bar and divided by its own
    typical size, so neither outweighs the other by units alone, and the
    summed evidence for each choice of bar 1 is weighed like a t-test across
    the song's bars: a beat that wins a little in every bar beats one that
    wins a lot in a few.

    Measured on 17 synthetic songs with a known bar 1, made for the 0.3
    review (boom-bap, house, trap, rock, pop, dembow, drum and bass, a
    ballad, a 3/4 waltz, a pickup, a beatless intro, a drifting tempo; each
    analysed at its true octave): this picked bar 1 in all 17, where the
    previous guess -- the kick alone -- put two four-on-the-floor house
    tracks' bar 1 on beat 4 and a dembow's on beat 2. tests/test_envelope.py
    pins the house case. On clicks, or a kick and clap with no harmony,
    nothing in the audio marks the bar, and the confidence (4-bar blocks
    agreeing: 0.0-0.4 there) says so -- that is when to pass `--downbeat`.
    """
    beats = np.asarray(beats, dtype=np.float64)
    if len(beats) == 0:
        return Downbeat(t=0.0, confidence=0.0, runner_up=None)
    if len(beats) < beats_per_bar or beats_per_bar < 2:
        return Downbeat(t=float(beats[0]), confidence=0.0, runner_up=None)

    features = [_near_beat_max(np.asarray(bflux, dtype=np.float64), beats)]
    if novelty is not None:
        features.append(np.asarray(novelty, dtype=np.float64))
    bars = len(beats) // beats_per_bar
    evidence = np.zeros((bars, beats_per_bar))
    for feature in features:
        per_bar = feature[: bars * beats_per_bar].reshape(bars, beats_per_bar)
        centred = per_bar - per_bar.mean(axis=1, keepdims=True)
        # Over the feature's own typical size, so a feature that barely
        # differs from beat to beat -- a kick on every beat -- stays small
        # instead of being stretched to count as much as one that does.
        level = float(np.mean(np.abs(feature)))
        if level > 1e-12:
            evidence += centred / level

    mean = evidence.mean(axis=0)
    if bars >= 2:
        # The t-statistic, with a floor under the standard error: a perfectly
        # repeating synthetic bar would otherwise divide by zero.
        spread = evidence.std(axis=0, ddof=1) / math.sqrt(bars)
        scores = mean / np.maximum(spread, 1e-3)
    else:
        scores = mean
    order = np.argsort(-scores, kind="stable")
    winner = int(order[0])
    runner = int(order[1])

    votes = 0
    blocks = 0
    for s in range(0, bars, _DOWNBEAT_BLOCK_BARS):
        block = evidence[s : s + _DOWNBEAT_BLOCK_BARS].mean(axis=0)
        blocks += 1
        top = np.sort(block)[::-1]
        if top[0] - top[1] > 0.05 and int(np.argmax(block)) == winner:
            votes += 1
    confidence = votes / blocks if blocks else 0.0
    return Downbeat(t=float(beats[winner]), confidence=round(confidence, 2), runner_up=float(beats[runner]))


def guess_downbeat(
    beats: np.ndarray,
    bflux: np.ndarray,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
    novelty: np.ndarray | None = None,
) -> float:
    """estimate_downbeat(), just the time: the beat most likely to be a bar's first."""
    return estimate_downbeat(beats, bflux, novelty, beats_per_bar).t


def _near_beat_max(envelope: np.ndarray, beats: np.ndarray, reach: int = 3) -> np.ndarray:
    """The largest value within `reach` frames of each beat: a flux peak can
    sit a frame either side of the beat it belongs to."""
    padded = np.pad(envelope, reach)
    strongest = np.max(np.lib.stride_tricks.sliding_window_view(padded, 2 * reach + 1), axis=1)
    idx = np.clip(np.round(beats * FPS).astype(int), 0, len(strongest) - 1)
    return strongest[idx]


def _grid_check(
    tempo: Tempo,
    bar1: Downbeat,
    beats: np.ndarray,
    sections: list[dict],
    beats_per_bar: int,
    bpm_range: tuple[float, float],
) -> dict:
    """The pack's `grid_check`: what to double-check before cutting to the grid."""
    warnings = []
    octave = None
    if tempo.alt_bpm is not None:
        octave = {"bpm": round(tempo.alt_bpm, 2), "score": round(tempo.alt_score, 2)}
        if tempo.alt_score >= _OCTAVE_CLOSE:
            lo, hi = _octave_range(tempo.alt_bpm, bpm_range)
            warnings.append(
                f"the tempo octave is a close call: {tempo.alt_bpm:.2f} BPM scores {tempo.alt_score:.2f} "
                f"of the chosen {tempo.bpm:.2f}. If the music moves at {tempo.alt_bpm:.2f}, re-run with "
                f"--bpm-range {lo:g} {hi:g}."
            )
    measured = [s for s in sections if s["off"] is not None]
    off = sum(s["off"] for s in measured)
    if off:
        total = sum(s["beats"] for s in measured)
        worst = max(measured, key=lambda s: s["max_ms"])
        warnings.append(
            f"the music drifts off the fixed grid: {off} of {total} beats ({off / total:.0%}) in the "
            f"sections with a pulse sit more than {GRID_TOLERANCE * 1000:.0f} ms (half a frame at 24 fps) "
            f"from it, worst {worst['max_ms']} ms in bars {worst['bars'][0]}-{worst['bars'][1]}, where the "
            f"music runs at ~{worst['bpm']:.2f} BPM against the grid's {tempo.bpm:.2f}. A fixed grid can't "
            f"follow a tempo that moves (a live take): cut to a tempo map -- the beats tracked one by one, "
            f"`kaleidophone analyze` -- or analyse the song in parts."
        )
    downbeat: dict = {"source": bar1.source}
    if bar1.source == "given":
        if len(beats):
            gap = float(np.min(np.abs(beats - bar1.t)))
            if gap > GRID_TOLERANCE:
                warnings.append(
                    f"the given downbeat sits {gap * 1000:.0f} ms from the nearest grid beat: the grid's "
                    f"phase or tempo may be off there."
                )
    else:
        downbeat["confidence"] = bar1.confidence
        downbeat["runner_up"] = None if bar1.runner_up is None else round(bar1.runner_up, 4)
        if bar1.confidence is not None and bar1.confidence < _DOWNBEAT_SURE:
            runner = "" if bar1.runner_up is None else f", runner-up {bar1.runner_up:.3f} s"
            warnings.append(
                f"bar 1 is a guess (confidence {bar1.confidence:.2f}{runner}): nothing in the audio marks "
                f"the bar clearly. Check it by ear and pass --downbeat."
            )
    return {
        "beats_per_bar": beats_per_bar,
        "octave": octave,
        "downbeat": downbeat,
        "sections": sections,
        "warnings": warnings,
    }


def _octave_range(alt: float, bpm_range: tuple[float, float]) -> tuple[float, float]:
    """A --bpm-range around `alt` that shuts out the octave that won: +-25%,
    rounded outward to 5 BPM and kept inside the range that was searched."""
    lo = max(float(bpm_range[0]), math.floor(alt * 0.8 / 5.0) * 5.0)
    hi = min(float(bpm_range[1]), math.ceil(alt * 1.25 / 5.0) * 5.0)
    return lo, hi


# --------------------------------------------------------------------------
# session in: the DAW's MIDI and stems
# --------------------------------------------------------------------------
@dataclass
class _Session:
    grid: SessionGrid
    alignment: Alignment
    info: dict  # the pack's `midi`
    events: dict  # the pack's `events`
    warnings: list[str]
    downbeat_given: bool = False


def _session(
    midi: MidiFile,
    offset: float | None,
    onset: np.ndarray,
    dur: float,
    beats_per_bar: int,
    downbeat: float | None = None,
) -> _Session:
    """The MIDI on the master: where it sits, its grid, its notes and chords.

    The offset is `offset` as given or, left out, found by midi.align() over
    +-ALIGN_SEARCH s. A given one is used as given: the notes are checked only
    within _GIVEN_CHECK s of it, and a warning says where they fit if that is
    more than GRID_TOLERANCE away. A found one that isn't sure
    (midi.ALIGN_MIN_R, ALIGN_MIN_MARGIN) is warned about. A file whose last
    event lies more than _MIDI_REACH past the song is refused. Bar 1 is the
    MIDI's first bar line in the song, or `downbeat` (s) when given. Notes and
    chord changes outside the song are dropped and counted.
    """
    label = midi.name or "the MIDI file"
    past = midi.end + (offset or 0.0) - dur
    if past > _MIDI_REACH:
        raise ValueError(
            f"{label} runs on until {midi.end:.0f} s, {past / 3600:.0f} hours past the end of the {dur:.0f} s "
            f"song -- a corrupt file, or not this song's session. Export the MIDI over the song's range."
        )
    times, weights = onset_impulses(midi.tracks)
    warnings = []
    if offset is None:
        if times.size == 0:
            raise ValueError(
                f"{label} has no notes to line up with the audio: pass --midi-offset (0 when the bounce "
                f"starts where the session does) to use its tempo map and bars."
            )
        if reachable(times, weights, dur, 0.0, ALIGN_SEARCH)[0].size == 0:
            raise ValueError(
                f"none of {label}'s notes comes within {ALIGN_SEARCH:g} s of the {dur:.1f} s song (the first is "
                f"at {times[0]:.1f} s), so there is nothing to line up: pass --midi-offset S (master time = MIDI "
                f"time + S) to place it."
            )
        alignment = align(times, weights, onset)
        if not alignment.sure:
            warnings.append(_alignment_warning(alignment, label))
    else:
        alignment = Alignment(
            offset=float(offset), r=correlation_at(times, weights, onset, offset), source="given"
        )
        if reachable(times, weights, dur, offset, _GIVEN_CHECK)[0].size:
            found = align(times, weights, onset, search=_GIVEN_CHECK, center=offset)
            if found.sure and abs(found.offset - offset) > GRID_TOLERANCE:
                warnings.append(
                    f"the given --midi-offset {offset:+.3f} s is {abs(found.offset - offset) * 1000:.0f} ms from "
                    f"where {label}'s notes line up best with the audio near it ({found.offset:+.3f} s, r "
                    f"{found.r:.2f}) -- check it."
                )

    meter = None
    if beats_per_bar != DEFAULT_BEATS_PER_BAR:
        if midi.has_meter:
            warnings.append(
                f"--beats-per-bar {beats_per_bar} is ignored: {label}'s time signatures set the bars."
            )
        else:
            meter = ((0.0, beats_per_bar, 4),)
    grid = session_grid(midi, alignment.offset, dur, meter=meter, downbeat=downbeat)
    if downbeat is not None:
        # Bar 1 falls on a note of the MIDI's grid; one eyeballed off it is
        # off every note in the song.
        q = float(midi.tempo.quarters_at(downbeat - alignment.offset))
        nearest = float(midi.tempo.seconds_at(round(q * 4.0) / 4.0)) + alignment.offset
        if abs(nearest - downbeat) > GRID_TOLERANCE:
            warnings.append(
                f"the given --downbeat {downbeat:.3f} s sits {abs(nearest - downbeat) * 1000:.0f} ms from the "
                f"MIDI's nearest 16th note ({nearest:.3f} s), and bar 1 falls on one: check --downbeat (or the "
                f"offset)."
            )

    notes: dict[str, list] = {}
    dropped = 0
    for track in midi.tracks:
        rows = []
        for note in track.notes:
            t = note.t + alignment.offset
            if not -EDGE <= t < dur:
                dropped += 1
                continue
            rows.append(
                [round(max(t, 0.0), 4), round(note.velocity / 127.0, 3), round(note.dur, 4), note.pitch]
            )
        notes[track.slug] = rows
    if midi.notes and dropped == midi.notes:
        warnings.append(
            f"none of {label}'s {midi.notes} notes falls inside the song at an offset of "
            f"{alignment.offset:+.3f} s, so `events.midi` is empty -- check --midi-offset."
        )
    chords = {
        track.slug: _chord_rows(
            chord_events(track, midi.tempo, key_signature=midi.key_signature), alignment.offset, dur
        )
        for track in midi.tracks
        if is_harmonic(track)
    }
    confidence = None
    if alignment.r is not None:
        confidence = {
            "r": round(alignment.r, 3),
            "margin": None if alignment.margin is None else round(alignment.margin, 3),
            "runner_up": None if alignment.runner_up is None else round(alignment.runner_up, 3),
        }
    info = {
        "file": midi.name,
        "ppq": midi.ppq,
        "offset": round(alignment.offset, 4) + 0.0,
        "offset_source": alignment.source,
        "confidence": confidence,
        "tempo_map": [[round(t, 4), round(bpm, 4)] for t, bpm in grid.tempo_map],
        "time_signatures": [[round(t, 4), num, den] for t, num, den in grid.time_signatures],
        "tracks": [track.label for track in midi.tracks],
        "dropped": dropped,
    }
    return _Session(grid, alignment, info, {"midi": notes, "chords": chords}, warnings, downbeat is not None)


def _chord_rows(changes: list[tuple[float, float, str]], offset: float, dur: float) -> list[list]:
    """Chord changes as `events.chords` rows on the master's clock. The chord
    already sounding when the song starts is an event at 0 s, so a piece
    knows the harmony from the first frame."""
    rows = []
    for start, until, name in changes:
        t = start + offset
        if t >= dur or until + offset <= 0.0:
            continue
        rows.append([round(max(t, 0.0), 4), 1, name])
    return rows


def _alignment_warning(found: Alignment, label: str) -> str:
    detail = f"r {found.r:.2f}"
    if found.margin is not None:
        detail += f", {found.margin:.2f} over the runner-up at {found.runner_up:+.3f} s"
    if found.r < ALIGN_MIN_R:
        why = (
            f"{label}'s notes hardly match the audio's onsets anywhere within +-{ALIGN_SEARCH:g} s. Is it this "
            f"song's session, at this bounce's tempo, and does the bounce start within {ALIGN_SEARCH:g} s of it?"
        )
    else:
        why = (
            "the notes fit nearly as well at the runner-up -- the song repeats itself there -- so the offset may "
            "be a beat or a bar out."
        )
    return (
        f"the MIDI's offset {found.offset:+.3f} s is a guess ({detail}): {why} Check an event against the audio "
        f"by ear, and pass --midi-offset S: where the MIDI's 0 s falls on the master (+ for pre-roll, - for a "
        f"bounce that starts after the session does)."
    )


def _quarters_per_bar(grid: SessionGrid) -> float:
    """Quarter notes in the bar the downbeat opens: 4 in 4/4, 3 in 6/8, 3.5 in 7/8."""
    num, den = next((n, d) for t, _, n, d in grid.bars if t >= grid.downbeat - 1e-9)
    quarters = num * 4.0 / den
    return int(quarters) if quarters == int(quarters) else quarters


def _session_bar(grid: SessionGrid, t: float) -> int:
    """The session's bar number at master time `t` -- before the song's first
    bar line, the bar before it."""
    numbers = [number for start, number, _, _ in grid.bars if start <= t + 1e-9]
    return numbers[-1] if numbers else grid.bars[0][1] - 1


def _session_check(session: _Session, sections: list[dict], quarters: float) -> dict:
    """`grid_check` for a MIDI grid: bar 1 is known, so what is left to check
    is the offset, the tempo and meter changes a one-BPM piece would miss, and
    whether the audio's pulse actually sits on the MIDI's beats."""
    g = session.grid
    warnings = list(session.warnings)
    if len(g.tempo_map) > 1:
        changes = g.tempo_map[1:]
        listed = ", ".join(
            f"{bpm:.2f} BPM at {t:.3f} s (the session's bar {_session_bar(g, t)})"
            for t, bpm in changes[:_LISTED_CHANGES]
        )
        if len(changes) > _LISTED_CHANGES:
            listed += f", and {len(changes) - _LISTED_CHANGES} more"
        period = 60.0 / g.bpm
        after = g.beats >= g.downbeat - 1e-9
        fixed = g.downbeat + period * np.arange(int(np.sum(after)))
        drift = np.abs(g.beats[after] - fixed)
        off = np.flatnonzero(drift > GRID_TOLERANCE)
        if off.size:
            t = float(g.beats[after][off[0]])
            tail = (
                f"a piece that assumes one BPM ({g.bpm:.2f}, bar 1's) is more than {GRID_TOLERANCE * 1000:.0f} ms "
                f"off the MIDI's beats from {t:.3f} s (the session's bar {_session_bar(g, t)}) on"
            )
        else:
            tail = f"a piece that assumes one BPM stays within {float(drift.max()) * 1000:.0f} ms of them"
        warnings.append(
            f"the tempo changes inside the song ({g.tempo_map[0][1]:.2f} BPM at 0 s, then {listed}): `beats` "
            f"follows the MIDI, and {tail}. Read `beats` or `midi.tempo_map` instead of extrapolating `bpm`."
        )
    if len(g.time_signatures) > 1:
        listed = ", ".join(
            f"{num}/{den} at {t:.3f} s (the session's bar {_session_bar(g, t)})"
            for t, num, den in g.time_signatures[1:]
        )
        head = g.time_signatures[0]
        warnings.append(
            f"the time signature changes inside the song ({head[1]}/{head[2]}, then {listed}): the pack's bars "
            f"follow it, and a piece that counts one bar length miscounts from there."
        )
    measured = [s for s in sections if s["off"] is not None]
    off = sum(s["off"] for s in measured)
    if off:
        total = sum(s["beats"] for s in measured)
        worst = max(measured, key=lambda s: s["max_ms"])
        warnings.append(
            f"the audio's pulse sits off the MIDI's beats: {off} of {total} beats ({off / total:.0%}) in the "
            f"sections with a pulse are more than {GRID_TOLERANCE * 1000:.0f} ms from them, worst "
            f"{worst['max_ms']} ms in bars {worst['bars'][0]}-{worst['bars'][1]}, where the audio runs at "
            f"~{worst['bpm']:.2f} BPM. Is the MIDI from this bounce -- the same version of the song, at its "
            f"tempo? A wrong offset or a time-stretched bounce reads the same way."
        )
    downbeat = {"source": "midi", "confidence": 1.0, "runner_up": None, "session_bar": g.downbeat_bar}
    if session.downbeat_given:
        downbeat = {"source": "given"}
    return {
        "beats_per_bar": quarters,
        "octave": None,
        "downbeat": downbeat,
        "sections": sections,
        "warnings": warnings,
    }


@dataclass
class _StemFit:
    """One stem's lag search (_stems, first pass): its length, its correlation
    with the master at every frame lag within +-STEM_SEARCH (None: nothing in
    it to line up by), the correlation at a given --stem-offset, and its
    measurement where it starts, for when it doesn't have to move."""

    samples: int
    r: np.ndarray | None
    given_r: float | None
    raw: _Raw


def _stems(
    stems: Mapping[str, np.ndarray | Callable[[], np.ndarray]],
    sr: int,
    length: int,
    master: _Raw,
    given: Mapping[str, float],
) -> tuple[dict, dict, list[str]]:
    """(stems.<name>, stems_alignment.<name>, warnings) for every stem, lined
    up with the master (_align_stems) and measured there. One stem is in
    memory at a time: each is decoded to find its lag and, if it has to move,
    once more to be measured where it lands."""
    reach = round(STEM_SEARCH * FPS)
    master_features = _align_features(master)
    fits = {}
    for name, source in stems.items():
        samples = source() if callable(source) else source
        mono, _ = _split_channels(samples)
        raw = _measure(_fit_length(mono, length), None, sr, bands=BANDS, flux=True, align=True)
        lags = np.arange(-reach, reach + 1)
        if name in given:
            lags = np.append(lags, round(given[name] * FPS))
        correlation = _stem_correlation(raw, master_features, lags, 2 * reach + 1)
        raw.align_power = raw.align_flux = None
        r, given_r = correlation if correlation is not None else (None, None)
        fits[name] = _StemFit(samples=len(mono), r=r, given_r=given_r, raw=raw)
        del samples, mono
    del master_features
    lined_up, warnings = _align_stems(fits, given, sr, length)
    out = {}
    for name, source in stems.items():
        shift = round(lined_up[name]["lag"] * sr)
        if shift == 0:
            raw = fits[name].raw
        else:
            samples = source() if callable(source) else source
            raw = _measure(_lined_up(_split_channels(samples)[0], shift, length), None, sr, bands=BANDS, flux=True)
            del samples
        out[name] = _stem_envelopes(raw)
    return out, lined_up, warnings


def _fit_length(mono: np.ndarray, length: int) -> np.ndarray:
    """`mono` padded with silence or trimmed at the tail to `length` samples."""
    if len(mono) < length:
        return np.concatenate([mono, np.zeros(length - len(mono), dtype=np.float32)])
    return mono[:length]


def _lined_up(mono: np.ndarray, shift: int, length: int) -> np.ndarray:
    """`mono` moved `shift` samples later (earlier if negative) onto the
    master's `length` samples: master sample i is stem sample i - shift, and
    silence where the stem has none."""
    out = np.zeros(length, dtype=np.float32)
    start, skip = max(0, shift), max(0, -shift)
    n = min(len(mono) - skip, length - start)
    if n > 0:
        out[start : start + n] = mono[skip : skip + n]
    return out


def _align_features(raw: _Raw) -> tuple[np.ndarray, np.ndarray]:
    """(band power, band onset) per frame in the alignment bands: the levels
    as they add up in a mix, and onset_strength of each band's flux."""
    onsets = np.stack([onset_strength(raw.align_flux[:, b]) for b in range(raw.align_flux.shape[1])], axis=1)
    return raw.align_power.astype(np.float64), onsets


def _stem_correlation(
    stem: _Raw, master: tuple[np.ndarray, np.ndarray], lags: np.ndarray, searched: int
) -> tuple[np.ndarray, float | None] | None:
    """The stem's correlation with the master at each of the first `searched`
    frame lags (master time = stem time + lag), and at the lag after them if
    there is one (a given --stem-offset), from two band-by-band
    correlations: the band power's -- weighted by how much of the stem's
    energy each band holds, so the bands it lives in decide -- and the band
    onsets', weighted by its onset energy. Where the two peak within
    _STEM_AGREE of each other, their mean; where they don't, the one that
    peaks higher -- one of them is fooled (see _align_stems). At the given
    lag, their mean. None when the stem has neither to correlate (silence, a
    drone)."""
    power, onsets = _align_features(stem)
    by_power = _band_ncc(power, master[0], power.sum(axis=0), lags)
    by_onset = _band_ncc(onsets, master[1], ((onsets - onsets.mean(axis=0)) ** 2).sum(axis=0), lags)
    parts = [part for part in (by_power, by_onset) if part is not None]
    if not parts:
        return None
    at_given = float(np.mean([part[searched] for part in parts])) if len(lags) > searched else None
    if len(parts) == 1:
        return parts[0][:searched], at_given
    p, o = int(np.argmax(by_power[:searched])), int(np.argmax(by_onset[:searched]))
    if abs(p - o) <= round(_STEM_AGREE * FPS):
        return (by_power[:searched] + by_onset[:searched]) / 2.0, at_given
    return (by_power if by_power[p] >= by_onset[o] else by_onset)[:searched], at_given


def _band_ncc(x: np.ndarray, y: np.ndarray, weight: np.ndarray, lags: np.ndarray) -> np.ndarray | None:
    """The weighted mean over bands of each band's normalised
    cross-correlation of `x` (frames x bands) moved by each of `lags` frames
    against `y`, normalised once by both signals' whole energy, as midi.align
    is. None if no band has weight."""
    xs = x - x.mean(axis=0)
    ys = y - y.mean(axis=0)
    x_norm = np.sqrt(np.einsum("ij,ij->j", xs, xs))
    y_norm = np.sqrt(np.einsum("ij,ij->j", ys, ys))
    w = np.where((x_norm > 1e-9) & (y_norm > 1e-9), weight, 0.0)
    if not w.sum() > 0:
        return None
    bands = np.flatnonzero(w > 1e-4 * w.sum())  # a band with a hundredth of a percent decides nothing
    w = w[bands] / w[bands].sum()
    size = 1 << (len(xs) + len(ys)).bit_length()
    overlap = (lags > -len(xs)) & (lags < len(ys))
    r = np.zeros(len(lags))
    for share, b in zip(w, bands):
        cross = np.fft.irfft(np.fft.rfft(ys[:, b], size) * np.conj(np.fft.rfft(xs[:, b], size)), size)
        r += share * np.where(overlap, cross[lags % size], 0.0) / (x_norm[b] * y_norm[b])
    return r


def _align_stems(fits: Mapping[str, _StemFit], given: Mapping[str, float], sr: int, length: int) -> tuple[dict, list]:
    """Each stem's lag on the master -- master time = stem time + lag -- as
    the pack's `stems_alignment`, or a ValueError naming every stem that
    can't be lined up and what to pass instead.

    A mastered bounce is often trimmed or padded at the head and its stems
    aren't, so a stem is never assumed to start where the master does. Its
    correlation with the master (_stem_correlation) is searched over
    +-STEM_SEARCH s and its best lag refined below a frame, then kept to the
    millisecond -- finer than the refinement is good for. Why two features,
    measured on tests/test_envelope.py's synthetic stems (stem_session, the
    0.4 review's case, a voice fading in under clicks; not representative of
    real mixes): band power alone lines up a voice (r 0.93-1.0) but not keys
    sharing their bands with a louder voice (r 0.16-0.17, 22-142 ms out);
    band onsets alone line up the keys and the drums (r 0.49-1.0, within 3 ms)
    but not a voice (r 0.10-0.17; 0.65-1.35 s out, the review's case 1.12 s).
    Their plain mean put the voice fading in 249 ms out, its one faint onset
    matched to a click (and called that sure); so where the two peak more than
    _STEM_AGREE apart, the one that correlates more is taken. That way every
    stem lined up within 3 ms, r 0.37-1.0, with the master trimmed 0.3 s,
    padded 0.4 s, or trimmed 1.234 s and soft-clipped, and with the voice
    10 dB down.

    A lag is trusted when its r is at least STEM_MIN_R and it beats the best
    distinct other lag by STEM_MIN_MARGIN. Measured on the same stems: a stem
    from elsewhere scored r 0.08-0.12 with margins under 0.03, and a pad
    swelling in over 1.5 s 0.16-0.23, its margin under 0.01 wherever its r
    reached 0.2 (and up to 430 ms out). A loop scores high but nearly as well a
    beat or a bar away: a strict click loop r 0.95 with margins of 0.024-0.026,
    and 500 ms out on its own with the master trimmed 0.55 s. Stems bounced
    together share one lag, so such a stem takes its own best lag within
    _STEM_AGREE of the lag most trusted stems agree on, and is refused when
    there is none; and a trusted stem that disagrees with that majority is
    refused too -- a part from another version can line up surely somewhere
    else. Nothing here checks a stem for drift: one from another version at
    another tempo can line up where its start does. A stem with nothing to line
    up by (silence, a drone) stays where it starts. A given --stem-offset is
    used as given, with a warning when the stem plainly fits elsewhere.
    """
    reach = round(STEM_SEARCH * FPS)
    found: dict[str, tuple[float, float, float | None, float | None, bool]] = {}
    for name, fit in fits.items():
        if fit.r is not None:
            found[name] = _stem_peak(fit.r, reach)
    sure = {
        name: lag for name, (lag, r, margin, _, edge) in found.items() if name not in given and _sure(r, margin, edge)
    }
    agreed, outliers = _agreement(sure)

    lined_up: dict[str, dict] = {}
    warnings: list[str] = []
    refused: list[str] = []
    for name, fit in fits.items():
        if name in given:
            lag = float(given[name])
            entry = {"lag": round(lag, 3) + 0.0, "r": _round_r(fit.given_r), "source": "given"}
            best = found.get(name)
            if best is not None and _sure(best[1], best[2], best[4]) and abs(best[0] - lag) > GRID_TOLERANCE:
                warnings.append(
                    f"the given --stem-offset {name}={lag:+.3f} s is {abs(best[0] - lag) * 1000:.0f} ms from where "
                    f"the stem lines up best with the master ({best[0]:+.3f} s, r {best[1]:.2f}) -- check it."
                )
        elif name not in found:
            lag, entry = 0.0, {"lag": 0.0, "r": None, "source": "none"}
        else:
            lag, r, margin, runner, edge = found[name]
            if name in outliers:
                others = ", ".join(f"{other} at {sure[other]:+.3f} s" for other in sure if other != name)
                if agreed is not None:
                    others = f"the other stems at {agreed:+.3f} s"
                refused.append(
                    f"{name} -- it lines up at {lag:+.3f} s (r {r:.2f}) and {others}, while stems bounced together "
                    f"share one lag"
                )
                continue
            if not _sure(r, margin, edge):
                settled = None if r < STEM_MIN_R or edge or agreed is None else _near(fit.r, reach, agreed, r)
                if settled is None:
                    refused.append(_stem_refusal(name, r, lag, margin, runner, edge, agreed))
                    continue
                lag, r = settled
            entry = {"lag": round(lag, 3) + 0.0, "r": _round_r(r), "source": "auto"}
        lined_up[name] = entry
    if refused:
        hint = f" The other stems line up at {agreed:+.3f} s." if agreed is not None else ""
        raise ValueError(
            "can't line up " + "; ".join(refused) + ". Is each this master's stem, bounced over the master's range? "
            "If it is, give its lag: --stem-offset NAME=S, where the stem's 0 s falls on the master (- for a "
            "master trimmed at the head, + for one padded)." + hint
        )
    for name, fit in fits.items():
        gap = lined_up[name]["lag"] + (fit.samples - length) / sr
        if abs(gap) > STEM_TOLERANCE:
            raise ValueError(
                f"stem {name!r} is {abs(gap):.2f} s {'longer' if gap > 0 else 'shorter'} than the master once "
                f"lined up with it (lag {lined_up[name]['lag']:+.3f} s; {fit.samples / sr:.2f} s against "
                f"{length / sr:.2f} s): it must end where the master does, to within {STEM_TOLERANCE:g} s -- it "
                f"was bounced over another range. Bounce every stem over the master's range."
            )
    return lined_up, warnings


def _sure(r: float, margin: float | None, edge: bool) -> bool:
    return r >= STEM_MIN_R and not edge and (margin is None or margin >= STEM_MIN_MARGIN)


def _agreement(sure: Mapping[str, float]) -> tuple[float | None, set[str]]:
    """(the lag most trusted stems agree on, the trusted stems that don't).
    Lags within _STEM_AGREE of one are one lag; it is agreed when more than
    half the stems share it, or there is only one. Without a majority there
    is no agreed lag, and no stem can be trusted over another."""
    if not sure:
        return None, set()
    _, centre = max((sum(abs(other - lag) <= _STEM_AGREE for other in sure.values()), lag) for lag in sure.values())
    members = [name for name, lag in sure.items() if abs(lag - centre) <= _STEM_AGREE]
    if 2 * len(members) <= len(sure):
        return None, set(sure)
    return float(np.median([sure[name] for name in members])), set(sure) - set(members)


def _round_r(r: float | None) -> float | None:
    return None if r is None else round(r, 3)


def _stem_peak(r: np.ndarray, reach: int) -> tuple[float, float, float | None, float | None, bool]:
    """(lag s, r there, margin over the runner-up, the runner-up's lag s, at
    the search's edge) of a stem's best lag, refined below a frame. The
    runner-up is the best other local maximum more than 50 ms away."""
    best = int(np.argmax(r))
    edge = best in (0, len(r) - 1)
    lag = (best - reach + (0.0 if edge else _vertex(r, best))) / FPS
    interior = np.zeros(len(r), dtype=bool)
    interior[1:-1] = (r[1:-1] >= r[:-2]) & (r[1:-1] >= r[2:])
    interior &= np.abs(np.arange(len(r)) - best) > 5
    if not np.any(interior):
        return lag, float(r[best]), None, None, edge
    j = int(np.argmax(np.where(interior, r, -np.inf)))
    return lag, float(r[best]), float(r[best] - r[j]), (j - reach) / FPS, edge


def _near(r: np.ndarray, reach: int, lag: float, best: float) -> tuple[float, float] | None:
    """(lag s, r) of the stem's own local maximum within _STEM_AGREE of
    `lag`, when it is about as good as its best (`best`) -- a loop's right
    lag among its near-equals; None if it has none there."""
    centre = round(lag * FPS) + reach
    spread = round(_STEM_AGREE * FPS)
    peaks = [
        k
        for k in range(max(1, centre - spread), min(len(r) - 1, centre + spread + 1))
        if r[k] >= r[k - 1] and r[k] >= r[k + 1]
    ]
    if not peaks:
        return None
    k = max(peaks, key=lambda k: r[k])
    if r[k] < STEM_MIN_R or r[k] < best - STEM_MIN_MARGIN:
        return None
    return (k - reach + _vertex(r, k)) / FPS, float(r[k])


def _vertex(values: np.ndarray, k: int) -> float:
    """The vertex of the parabola through values[k-1..k+1], in steps from k."""
    left, mid, right = values[k - 1], values[k], values[k + 1]
    denom = left - 2.0 * mid + right
    return float(0.5 * (left - right) / denom) if denom < 0 else 0.0


def _stem_refusal(
    name: str, r: float, lag: float, margin: float | None, runner: float | None, edge: bool, agreed: float | None
) -> str:
    if edge:
        return (
            f"{name} -- it fits best at the edge of the +-{STEM_SEARCH:g} s search ({lag:+.3f} s, r {r:.2f}), so its "
            f"lag may be further out than that"
        )
    if r < STEM_MIN_R:
        return (
            f"{name} -- its levels and onsets hardly match the master's anywhere within +-{STEM_SEARCH:g} s (r {r:.2f} "
            f"at best, at {lag:+.3f} s; a stem of this master scores {STEM_MIN_R:g} or more)"
        )
    which = "no other stem settles which" if agreed is None else f"its fit near {agreed:+.3f} s isn't one of them"
    return (
        f"{name} -- it fits nearly as well at {runner:+.3f} s as at {lag:+.3f} s (r {r:.2f}, {margin:.2f} apart): "
        f"it repeats itself, and {which}"
    )


def _stem_envelopes(raw: _Raw) -> dict:
    """A stem's envelopes from its measurement on the master's frames.

    The same measurement as the master's (_measure: bands, rms, flux,
    centroid; no `voc`, which is a stereo-mix proxy), lined up and padded or
    trimmed to the master's length so every array has the master's frame
    count. Normalised the same way too, per envelope, with one difference: a
    stem is often silent for most of the song, and its digital silence
    (frames at the FLOOR_DB floor) is kept out of the percentiles and reads
    0, as the mix's silent frames do in _vocal_envelope -- otherwise the
    floor sets the 5th percentile and a breath reads as half the voice.
    """
    out: dict[str, list[float]] = {}
    for band in BANDS:
        out[band] = _rounded(_sounding_normalize(raw.bands_db[band]), 3)
    out["rms"] = _rounded(_sounding_normalize(raw.rms_db), 3)
    out["rmsdb"] = _rounded(raw.rms_db, 1)
    for flux in FLUX_BANDS:
        out[flux] = _rounded(_flux_envelope(raw.flux[flux]), 3)
    cent = np.clip(raw.centroid_hz / _CENTROID_SCALE, 0.0, 1.0)
    cent[raw.rms_db <= FLOOR_DB] = 0.0
    out["cent"] = _rounded(cent, 3)
    return out


def _sounding_normalize(level_db: np.ndarray) -> np.ndarray:
    """percentile_normalize over the frames above the floor; floor frames are 0."""
    sounding = level_db > FLOOR_DB
    normalized = percentile_normalize(level_db, mask=sounding)
    normalized[~sounding] = 0.0
    return normalized


# --------------------------------------------------------------------------
# the measurement
# --------------------------------------------------------------------------
@dataclass
class _Raw:
    bands_db: dict[str, np.ndarray]
    rms_db: np.ndarray
    flux: dict[str, np.ndarray]
    tempo_flux: np.ndarray | None
    centroid_hz: np.ndarray
    vocal_mid_db: np.ndarray | None
    vocal_side_db: np.ndarray | None
    # Side over mid in the vocal band across the whole song, in dB, from the
    # raw energies -- before the floor, which would otherwise decide it.
    side_to_mid_db: float | None = None
    # Power and flux per frame in the stem-alignment bands (_align_masks),
    # frames x bands, when asked for.
    align_power: np.ndarray | None = None
    align_flux: np.ndarray | None = None


def _align_masks(freqs: np.ndarray) -> np.ndarray:
    """0/1 columns for the stem-alignment bands: _ALIGN_BANDS_PER_OCTAVE a
    octave over _ALIGN_RANGE, each at least one bin wide, none twice (at the
    bottom, where the bins are wider than the bands, neighbours merge)."""
    lo, hi = _ALIGN_RANGE
    count = math.ceil(_ALIGN_BANDS_PER_OCTAVE * math.log2(hi / lo))
    edges = np.minimum(lo * 2.0 ** (np.arange(count + 1) / _ALIGN_BANDS_PER_OCTAVE), hi)
    spans = []
    for a, b in itertools.pairwise(edges):
        i0 = int(np.searchsorted(freqs, a))
        i1 = max(i0 + 1, int(np.searchsorted(freqs, b)))
        if not spans or i0 >= spans[-1][1]:
            spans.append((i0, i1))
        else:
            spans[-1] = (spans[-1][0], max(i1, spans[-1][1]))
    columns = np.zeros((len(freqs), len(spans)), np.float32)
    for k, (i0, i1) in enumerate(spans):
        columns[i0:i1, k] = 1.0
    return columns


def _split_channels(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    """(mid, side) as float32; side is None for mono input."""
    x = np.asarray(samples)
    if x.ndim == 2 and x.shape[1] == 1:
        x = x[:, 0]
    if x.ndim == 1:
        return x.astype(np.float32, copy=False), None
    if x.ndim == 2 and x.shape[1] == 2:
        left = x[:, 0].astype(np.float32)
        right = x[:, 1].astype(np.float32)
        return 0.5 * (left + right), 0.5 * (left - right)
    raise ValueError(f"expected samples shaped (n,) for mono or (n, 2) for stereo, got {x.shape}")


def _analysis_params(sr: int) -> tuple[int, int]:
    """(hop, window) in samples for `sr`: a 10 ms hop, and WINDOW scaled from
    48 kHz to the nearest power of two so the window stays ~43 ms long."""
    if sr <= 0 or sr % FPS:
        raise ValueError(
            f"sample rate {sr} Hz is not a multiple of {FPS} Hz, so a 10 ms hop isn't a "
            f"whole number of samples. Resample first -- envelope() decodes at {SAMPLE_RATE} Hz."
        )
    if sr == SAMPLE_RATE:
        return sr // FPS, WINDOW
    return sr // FPS, max(256, 1 << round(math.log2(WINDOW * sr / SAMPLE_RATE)))


def _frame_view(signal: np.ndarray, window: int, hop: int) -> np.ndarray:
    """Centred frames as a strided view: frame i is centred on sample i*hop."""
    padded = np.pad(signal, (window // 2, window // 2))
    count = 1 + len(signal) // hop
    return np.lib.stride_tricks.sliding_window_view(padded, window)[::hop][:count]


def _to_db(mean_square: np.ndarray) -> np.ndarray:
    return np.maximum(10.0 * np.log10(np.maximum(mean_square, 1e-30)), FLOOR_DB)


def _measure(
    mid: np.ndarray,
    side: np.ndarray | None,
    sr: int,
    *,
    bands: dict[str, tuple[float, float]],
    flux: bool,
    align: bool = False,
) -> _Raw:
    """One chunked pass over the STFT; every per-frame number comes from here.

    Band, flux and centroid sums are matrix products against 0/1 band masks
    rather than a slice-and-sum per band: one BLAS call per block instead of a
    dozen reductions, which is most of the difference between this running in
    about a second on a 4-minute song and running in several. `align` (with
    `flux`) adds power and flux in the stem-alignment bands.
    """
    hop, win = _analysis_params(sr)
    window = np.hanning(win).astype(np.float32)
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    # Power in a band -> the mean square of the signal in that band, so a
    # full-scale sine reads -3 dB in its band exactly as it does in rmsdb.
    to_mean_square = 2.0 / (win * float(np.sum(window.astype(np.float64) ** 2)))

    def mask(lo: float, hi: float) -> np.ndarray:
        column = np.zeros(len(freqs), np.float32)
        column[int(np.searchsorted(freqs, lo)) : int(np.searchsorted(freqs, hi))] = 1.0
        return column

    names = list(bands)
    # The vocal band rides along as the last column, for voc.
    band_masks = np.stack([mask(*bands[name]) for name in names] + [mask(*VOCAL_BAND)], axis=1)
    # The published flux envelopes, plus one more column for the tempo search:
    # 1/f-weighted, so every octave counts equally. A plain sum over linear
    # bins gives the top three octaves (2-16 kHz) most of the weight, and a
    # comb fed that locks onto off-beat hi-hats instead of the kick -- measured
    # on a synthetic kick-and-offbeat-hat loop, where it put every beat on the hat.
    tempo_weights = np.where((freqs >= 30.0) & (freqs < 16000.0), 1.0 / np.maximum(freqs, 30.0), 0.0)
    flux_masks = np.stack(
        [mask(*FLUX_BANDS[name]) for name in FLUX_BANDS] + [tempo_weights.astype(np.float32)], axis=1
    )
    moment_masks = np.stack([np.ones(len(freqs)), freqs], axis=1).astype(np.float32)

    frames = _frame_view(mid, win, hop)
    side_frames = _frame_view(side, win, hop) if side is not None else None
    n = len(frames)

    band_power = np.zeros((n, band_masks.shape[1]))
    rms_ms = np.zeros(n)
    flux_sums = np.zeros((n, flux_masks.shape[1]))
    moments = np.zeros((n, 2))
    side_vocal = np.zeros(n) if side is not None else None
    align_masks = _align_masks(freqs) if align else None
    align_power = align_flux = None
    if align_masks is not None:
        align_power = np.zeros((n, align_masks.shape[1]), np.float32)
        align_flux = np.zeros((n, align_masks.shape[1]), np.float32)

    previous = None
    for s in range(0, n, _CHUNK):
        e = min(n, s + _CHUNK)
        block = frames[s:e]
        rms_ms[s:e] = np.einsum("ij,ij->i", block, block) / win
        mag = np.abs(np.fft.rfft(block * window, axis=1))
        power = mag * mag
        band_power[s:e] = power @ band_masks
        if align_masks is not None:
            align_power[s:e] = power @ align_masks
        if flux:
            # Positive log-magnitude difference: log1p(100 * mag), so a quiet
            # hat entering counts, not only the loudest bins.
            logmag = np.log1p(100.0 * mag)
            head = logmag[:1] if previous is None else previous[None, :]
            rising = np.maximum(np.diff(logmag, axis=0, prepend=head), 0.0)
            flux_sums[s:e] = rising @ flux_masks
            if align_masks is not None:
                align_flux[s:e] = rising @ align_masks
            previous = logmag[-1]
            moments[s:e] = mag @ moment_masks
        if side_frames is not None:
            side_mag = np.abs(np.fft.rfft(side_frames[s:e] * window, axis=1))
            side_vocal[s:e] = (side_mag * side_mag) @ band_masks[:, -1]

    band_ms = band_power * to_mean_square
    fluxes: dict[str, np.ndarray] = {}
    tempo_flux = None
    if flux:
        # Calibrated latency: log flux jumps as soon as an attack enters the
        # window, one frame before the frame centred on it. Measured on
        # synthetic clicks, kicks, snares, a 20 ms swell and a plucked
        # harmonic tone, the peak led the attack by 9-13 ms every time -- so
        # every flux envelope is moved one frame later, and beats and hits
        # land on the attack rather than ahead of it.
        lagged = np.vstack(
            [np.zeros((_FLUX_LEAD_FRAMES, flux_sums.shape[1])), flux_sums[:-_FLUX_LEAD_FRAMES]]
        )
        fluxes = {name: lagged[:, i] for i, name in enumerate(FLUX_BANDS)}
        tempo_flux = lagged[:, -1]
        if align_flux is not None:
            align_flux = np.vstack([np.zeros((_FLUX_LEAD_FRAMES, align_flux.shape[1]), np.float32), align_flux[:-1]])
    centroid = np.divide(moments[:, 1], moments[:, 0], out=np.zeros(n), where=moments[:, 0] > 0)

    side_to_mid_db = None
    if side_vocal is not None:
        mid_total = float(band_ms[:, -1].sum())
        side_total = float(side_vocal.sum()) * to_mean_square
        side_to_mid_db = 10.0 * math.log10(max(side_total, 1e-30) / max(mid_total, 1e-30))

    return _Raw(
        bands_db={name: _to_db(band_ms[:, i]) for i, name in enumerate(names)},
        rms_db=_to_db(rms_ms),
        flux=fluxes,
        tempo_flux=tempo_flux,
        centroid_hz=centroid,
        vocal_mid_db=_to_db(band_ms[:, -1]) if side is not None else None,
        vocal_side_db=_to_db(side_vocal * to_mean_square) if side_vocal is not None else None,
        side_to_mid_db=side_to_mid_db,
        align_power=align_power,
        align_flux=align_flux,
    )


def _flux_envelope(values: np.ndarray) -> np.ndarray:
    """Flux over its 99.5th percentile, clipped at 1.5 rather than 1.

    The top half-percent are the hits a piece most wants to react to;
    clipping them at 1 would make the biggest hit in the song
    indistinguishable from an ordinary strong one.
    """
    ref = float(np.percentile(values, 99.5)) if len(values) else 0.0
    if ref <= 0.0:
        return np.zeros(len(values))
    return np.clip(values / ref, 0.0, _FLUX_CEILING)


def _vocal_envelope(mid_db: np.ndarray, side_db: np.ndarray, side_to_mid_db: float) -> np.ndarray:
    """How far the vocal band's centre stands out from its sides, 0..1.

    Vocals sit in the centre of nearly every mix, while the guitars, keys and
    reverb that share their band are spread across the stereo field. So
    mid-minus-side (in dB) in 250-3500 Hz rises when the voice comes in, where
    the band's plain level mostly tracks the arrangement. It is a proxy, not a
    voice detector: a vocal doubled and panned hard left and right reads low,
    and a lead synth parked in the centre reads high.

    A dual-mono file -- a mono bounce exported as a stereo WAV, which is
    common -- has no side at all. There is then nothing to contrast the
    centre with, and the honest answer is zeros: the naive ratio pins at its
    ceiling wherever there is sound, and normalised, that reads as "the voice
    is always there". The test uses the raw energies (`side_to_mid_db`): summed
    after flooring, a sparse track's silent frames outweigh its sound and
    hide the fact that the side is empty. Silent frames are 0 for the same
    reason as dual mono, and are kept out of the percentiles.
    """
    if side_to_mid_db <= _DUAL_MONO_DB:
        return np.zeros(len(mid_db))
    contrast = np.clip(mid_db - side_db, -_VOC_CONTRAST_LIMIT_DB, _VOC_CONTRAST_LIMIT_DB)
    voiced = mid_db > FLOOR_DB
    voc = percentile_normalize(contrast, mask=voiced)
    voc[~voiced] = 0.0
    return voc


def _loudest_window(
    rms_db: np.ndarray, downbeat: float, bar: float, dur: float, *, bar_lines: list[float] | None = None
) -> dict:
    """The loudest LOUDEST_SECONDS of the song -- a default reel -- starting
    on the bar line nearest it, so a cut made from it starts where a phrase
    does. (It started on the nearest *beat* until 0.3; on test songs half the
    reels then opened on beat 2, 3 or 4.) Bar lines run both ways from
    `downbeat`, so a loud stretch before bar 1 still snaps to a bar.
    `bar_lines` (s) are the bar lines themselves, when a MIDI file says
    where they are and they aren't all one bar apart."""
    width = LOUDEST_SECONDS * FPS
    if dur <= LOUDEST_SECONDS or len(rms_db) <= width:
        return {"start": 0.0, "len": round(dur, 3)}
    power = 10.0 ** (rms_db / 10.0)
    cumulative = np.concatenate([[0.0], np.cumsum(power)])
    start = int(np.argmax(cumulative[width:] - cumulative[:-width])) / FPS
    latest = dur - LOUDEST_SECONDS
    reachable = [b for b in bar_lines or [] if 0.0 <= b <= latest + 1e-9]
    if reachable:
        start = min(reachable, key=lambda b: abs(b - start))
    elif bar > 0:
        first = math.ceil((0.0 - downbeat) / bar - 1e-9)
        last = math.floor((latest - downbeat) / bar + 1e-9)
        if first <= last:
            k = min(max(round((start - downbeat) / bar), first), last)
            start = downbeat + k * bar
    start = min(max(0.0, start), latest)
    return {"start": round(start, 3), "len": LOUDEST_SECONDS}


def _rounded(values, decimals: int) -> list[float]:
    # `+ 0.0` turns -0.0 into 0.0, which would otherwise be written as "-0.0".
    return (np.round(np.asarray(values, dtype=np.float64), decimals) + 0.0).tolist()
