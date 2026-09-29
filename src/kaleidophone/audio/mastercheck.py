"""
Is a new master a drop-in for the one the picture was cut against?

    kaleidophone master-check old.wav new.wav [--bpm B --downbeat D] [--silent-start S] [--json out.json]

The silent render is cut to one specific master: every cut, flash and card
sits on its beat grid. When a new master arrives -- a re-limit, a mix note,
a changed arrangement after the drop -- the cheap path (`remux`, `deliver`)
is only safe if the grid under the picture didn't move. The reference
project learned what happens when nobody checks: its replacement master
moved the switch ~5 s earlier, and a stream-copy remux would have desynced
every cut after the first section without raising an error anywhere (see
docs/case-studies/love.md). This is ROADMAP's "remux landmark-drift guard",
GitHub issue #18, built from two techniques that were run by hand on real
releases before they were code (docs/TECHNIQUES.md #49 and #52).

1. Did the grid move? The two files' log-RMS envelopes (100 Hz) are
   cross-correlated in 8 s windows every 4 s, searching +-1.5 s, and the
   whole song once more over +-20 s. One shift that explains every window
   and the song as a whole is one constant: within the tolerance (default
   half a frame at 24 fps, ~21 ms) the grid is the same; beyond it the new
   master is the same material starting earlier or later -- an `offset`,
   which the delivery sheet's `silent_start` absorbs without a render. The
   shift is refined past the envelopes' 10 ms frames (a parabola on the
   correlation, then phase-only cross-correlation of the audio) because a
   20 ms trim and a 23 ms MP3 decoder delay sit either side of that
   tolerance. A shift with new sound *before* the old master's first note
   is not an offset but an insertion: new grid. Lags that grow steadily
   with time are a tempo change; a master that is the same material a few
   percent faster (varispeed) is found by stretching one envelope against
   the other, and said as such.

2. What would a piece hear differently, bar by bar? After aligning the new
   master by that shift, the envelopes a piece reads (the song pack's bass,
   lowmid, mid, high, air, rms, cent and voc, and the flux envelopes) are
   compared per bar of the grid. Level envelopes are put on the old master's
   scale first -- each band's overall gain difference taken out, then both
   mapped through the old master's percentiles -- so a remaster that is
   louder, brighter or limited harder reads as unchanged; a bar changes when
   its mean |difference| or its shape (r) crosses a threshold. The flux
   envelopes are compared as the rhythm they describe: onset energy per
   16th of the bar. Removing every hi-hat leaves the vocal alone but changes
   air, hflux and cent in every bar, and a piece that sparkles on the hats
   would sparkle to nothing -- that is a re-render, not a remux. Two more
   readings stay from the technique as first run by hand: the "new voice"
   fraction (the vocal band sounding clearly where it was near silent), and
   the vocal band's and full mix's correlation per 8-bar section.

   The vocal band here (350-3400 Hz) is the full mix's, not a separated
   vocal: it hears guitars, keys and the snare's body as well. SHOULD I ?'s
   first comparison read 0.65-0.95 in that band per section where the
   arrangement after the drop had changed (full mix 0.2-0.6) and was a
   re-mux; its per-bar comparison of the next master ran on separated vocal
   stems. So a low vocal-band r is a pointer to listen, not proof of a new
   take -- and when the whole vocal band lines up better at another shift
   than the mix does, the report says the vocal moved, and by how much.

Verdicts, and the exit code each one returns:

    remux      0   same grid, nothing changed -- mux the new master and ship
    rerender   3   same grid, some bars changed -- re-render those, remux the rest
    new grid   4   something moved -- re-analyse and re-compose
    offset     5   same material, starting earlier or later -- set the delivery
                   sheet's silent_start to the printed value and deliver

(1 and 2 are kaleidophone's own usage and error codes, so a script can tell
"the check failed to run" from "the check says no". Changed bars outrank an
offset: they need a person, so the verdict is rerender and the report still
gives the silent_start.)

Pure functions on arrays do the work (compare_signals and below); master_check
is the thin wrapper that decodes two files with ffmpeg.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from kaleidophone.audio.envelope import (
    DEFAULT_BPM_RANGE,
    FLOOR_DB,
    FPS,
    SAMPLE_RATE,
    analyze_signal,
    raw_envelopes,
)
from kaleidophone.render._ffmpeg_util import decode_f32le

MASTERCHECK_FORMAT = "mastercheck/1"

EXIT_REMUX = 0
EXIT_RERENDER = 3
EXIT_NEW_GRID = 4
EXIT_OFFSET = 5
_EXIT_CODES = {
    "remux": EXIT_REMUX,
    "rerender": EXIT_RERENDER,
    "new grid": EXIT_NEW_GRID,
    "offset": EXIT_OFFSET,
}

VOCAL_BAND = (350.0, 3400.0)

WINDOW_SECONDS = 8.0
STEP_SECONDS = 4.0
SEARCH_SECONDS = 1.5
# Half a frame at 24 fps: a picture this far from its audio is still on the
# right frame. Anything within it is the same grid.
TOLERANCE = 1.0 / 48.0
# Windows agree with one song-wide shift when they sit within two envelope
# frames of it -- the windows only resolve whole frames.
_AGREE = 0.02
# The whole-song alignment searches wider than the windows do -- see
# global_offset().
GLOBAL_SEARCH_SECONDS = 20.0
SECTION_BARS = 8

# What a piece reads, compared bar by bar: the song pack's envelopes.
ENVELOPES = ("bass", "lowmid", "mid", "high", "air", "rms", "flux", "bflux", "hflux", "cent", "voc")
_RHYTHMS = ("flux", "bflux", "hflux")

# Starting points, not laws -- tune per song. Measured on synthetic masters
# (the 0.3 review's 80 BPM song and its variants; not representative of real
# mixes): a remaster, a 44.1 kHz bounce, the vocal +-3 dB, a -12 dB reverb,
# an MP3 draft and a 1-semitone pitch shift stayed at or under a mean
# |difference| of 0.11 and at or above a shape r of 0.90 in every bar and
# envelope; the bars of a new vocal take and an ad-lib reached 0.21-0.30 and
# r 0.22-0.51 in mid and voc; removing the hi-hats took air to 0.18-0.21 /
# r 0.58-0.61 and cent to r 0.37 in every bar.
DELTA_THRESHOLD = 0.15
SHAPE_THRESHOLD = 0.75
# The flux envelopes' 16th-note profile r: 0.85 or more on the same
# variants, down to 0.70 for hflux with the hats gone.
RHYTHM_THRESHOLD = 0.8
NEW_VOICE_THRESHOLD = 0.10
NEW_VOICE_ON = 0.35
NEW_VOICE_OFF = 0.15
# The bottom of the 0.65-0.95 vocal-band range that same takes measured.
SAME_TAKE_R = 0.65
# A full-mix section correlation under this is an arrangement change.
SAME_MIX_R = 0.65
# New sound this long before the old master's first note, once aligned, is
# an insertion rather than a new head of silence.
_HEAD_MARGIN = 0.25

# A window whose level moves less than this (dB, standard deviation) has
# nothing to line up -- silence, a held drone.
_FLAT_DB = 1.0
# A window whose best alignment explains less than this is reported but
# doesn't vote: an arbitrary argmax over noise is not evidence of a shift.
_MIN_MATCH_R = 0.3
# Alignments within this much correlation of the best count as ties, and a
# tie goes to the smallest shift. A looped bar correlates equally well one
# bar later; "nothing moved" is the explanation to prefer.
_TIE_R = 0.002
_AUDIBLE_DB = 50.0  # "audible" = within this many dB of the file's loudest frame
# A stretched alignment must reach this r, and beat the unstretched one by
# _STRETCH_GAIN, to call a master the same material at another speed.
_STRETCH_R = 0.8
_STRETCH_GAIN = 0.05
# The onset (flux) envelopes of two masters that really are one shift apart
# correlate at that shift: measured 0.74-1.00 on the review's variants, the
# hi-hat removal the lowest and a pitch shift 0.84; a master 0.5% or 6%
# faster, ~0.00 at any single shift.
_ONSETS_ALIGNED = 0.4
# ...and a stretch that explains them must bring them to at least this.
_ONSETS_STRETCHED = 0.6
# The vocal band moved when it lines up this well somewhere else, and that
# much better than where the mix does.
_VOCAL_MOVED_R = 0.8
_VOCAL_MOVED_GAIN = 0.2
# A bar's level envelope needs this much movement (0..1 scale, standard
# deviation) in both masters before its shape r means anything.
_SHAPE_ACTIVITY = 0.03
# A bar's rhythm counts as sounding when its onset energy is at least this
# share of the song's median bar.
_RHYTHM_ACTIVITY = 0.2
# Phase-only cross-correlation of the audio: segment length (2^17 samples,
# 2.7 s at 48 kHz), how far around the envelope's answer it looks, and how
# far apart the segments' answers may be before they are not trusted.
_FINE_SEGMENT = 1 << 17
_FINE_REACH = 0.03
_FINE_SPREAD = 0.001


@dataclass(frozen=True)
class Grid:
    """The bar grid the picture was cut to: bar 1 starts at `downbeat`.

    `confidence` is the song pack's confidence in an estimated downbeat
    (envelope.estimate_downbeat), None when it was given.
    """

    bpm: float
    downbeat: float
    beats_per_bar: int
    source: str
    confidence: float | None = None
    # An estimated tempo's other octave and its score over the chosen one's
    # (envelope.Tempo.alt_bpm / alt_score); None when the tempo was given.
    octave: tuple[float, float] | None = None

    @property
    def bar_seconds(self) -> float:
        return self.beats_per_bar * 60.0 / self.bpm

    def bar_start(self, bar: int) -> float:
        return self.downbeat + (bar - 1) * self.bar_seconds


@dataclass(frozen=True)
class LagWindow:
    """One 8 s window: where the new master lines up against the old.

    `lag` is how much later (s) the same material sits in the new master;
    None when the window is flat or nothing in reach matched it.
    """

    start: float
    lag: float | None
    r: float | None


@dataclass(frozen=True)
class SectionMatch:
    first_bar: int
    last_bar: int
    start: float
    end: float
    vocal_r: float | None
    mix_r: float | None


@dataclass(frozen=True)
class BarChange:
    """One bar of the grid, compared. `delta` is the largest mean |difference|
    of any level envelope, `envelopes` the ones that crossed a threshold, and
    `detail` every envelope's numbers: `delta` and `r` for levels, `r` of the
    16th-note profile for the flux envelopes (None where nothing sounds)."""

    bar: int
    start: float
    end: float
    delta: float
    new_voice: float
    changed: bool
    envelopes: tuple[str, ...] = ()
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MasterCheck:
    verdict: str  # "remux" | "rerender" | "new grid" | "offset"
    detail: str
    diagnosis: str
    grid: Grid
    windows: tuple[LagWindow, ...]
    offset: float
    offset_r: float
    sections: tuple[SectionMatch, ...]
    bars: tuple[BarChange, ...]
    old_duration: float
    new_duration: float
    old_audible: tuple[float, float]
    new_audible: tuple[float, float]
    notes: tuple[str, ...] = ()
    old_label: str = "old"
    new_label: str = "new"
    tolerance: float = TOLERANCE
    silent_start: float = 0.0
    # The delivery sheet's silent_start for the new master: the current one
    # plus the shift. None when no one shift explains the new master.
    new_silent_start: float | None = None
    # The new master's speed over the old one's when it is the same material
    # faster (> 1) or slower; None otherwise.
    tempo_ratio: float | None = None
    vocal_lag: float | None = None
    vocal_r: float | None = None

    @property
    def exit_code(self) -> int:
        return _EXIT_CODES[self.verdict]

    @property
    def changed_ranges(self) -> list[tuple[int, int]]:
        return _ranges([b.bar for b in self.bars if b.changed])

    def to_dict(self) -> dict:
        return {
            "kaleidophone": MASTERCHECK_FORMAT,
            "old": self.old_label,
            "new": self.new_label,
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "detail": self.detail,
            "diagnosis": self.diagnosis,
            "grid": {
                "bpm": self.grid.bpm,
                "downbeat": self.grid.downbeat,
                "beats_per_bar": self.grid.beats_per_bar,
                "source": self.grid.source,
                "confidence": self.grid.confidence,
                "octave": None if self.grid.octave is None else list(self.grid.octave),
            },
            "duration": {"old": self.old_duration, "new": self.new_duration},
            "audible": {"old": list(self.old_audible), "new": list(self.new_audible)},
            "offset": {
                "lag": self.offset,
                "r": self.offset_r,
                "tolerance": round(self.tolerance, 4),
                "silent_start": self.silent_start,
                "new_silent_start": self.new_silent_start,
            },
            "tempo_ratio": self.tempo_ratio,
            "vocal": {"lag": self.vocal_lag, "r": self.vocal_r},
            "windows": [vars(w) for w in self.windows],
            "sections": [vars(s) for s in self.sections],
            "bars": [{**vars(b), "envelopes": list(b.envelopes)} for b in self.bars],
            "changed": [list(r) for r in self.changed_ranges],
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------
def master_check(old_path: str, new_path: str, **options) -> MasterCheck:
    """Decode both masters (stereo, 48 kHz) and run compare_signals().

    Stereo because the song pack's `voc` is a centre-against-sides reading;
    48 kHz for both, so a 44.1 kHz bounce against a 48 kHz one compares frame
    for frame instead of drifting apart by the ratio of the two rates. A mono
    file arrives as two identical channels and simply has no `voc`.
    """
    old = _decode(old_path)
    new = _decode(new_path)
    return compare_signals(old, new, SAMPLE_RATE, old_label=old_path, new_label=new_path, **options)


def compare_signals(
    old: np.ndarray,
    new: np.ndarray,
    sr: int = SAMPLE_RATE,
    *,
    bpm: float | None = None,
    downbeat: float | None = None,
    beats_per_bar: int = 4,
    max_delta: float = DELTA_THRESHOLD,
    max_new_voice: float = NEW_VOICE_THRESHOLD,
    min_r: float = SHAPE_THRESHOLD,
    tolerance: float = TOLERANCE,
    silent_start: float = 0.0,
    envelopes: tuple[str, ...] | list[str] | None = None,
    old_label: str = "old",
    new_label: str = "new",
) -> MasterCheck:
    """The whole check on two sample arrays (mono (n,) or stereo (n, 2)).

    `bpm` and `downbeat` describe the grid the picture was cut to. Either one
    left out is estimated from the *old* master -- the one the picture
    actually follows -- with the song-pack analysis (audio/envelope.py).
    `silent_start` is the current delivery sheet's value; the report adds the
    shift to it. `envelopes` narrows the per-bar comparison to what the piece
    actually reads (default: all of ENVELOPES).
    """
    if bpm is not None and not bpm > 0:
        raise ValueError(f"--bpm must be positive, got {bpm:g}")
    if downbeat is not None and downbeat < 0:
        raise ValueError(f"--downbeat is a time in seconds and can't be negative, got {downbeat:g}")
    if beats_per_bar < 1:
        raise ValueError(f"--beats-per-bar must be at least 1, got {beats_per_bar}")
    if not tolerance >= 0:
        raise ValueError(f"--tolerance-ms can't be negative, got {tolerance * 1000:g}")
    keys = tuple(ENVELOPES if envelopes is None else envelopes)
    unknown = [k for k in keys if k not in ENVELOPES]
    if unknown or not keys:
        raise ValueError(
            f"--envelopes takes song-pack envelopes from {', '.join(ENVELOPES)}; got {', '.join(keys) or 'none'}"
        )

    old_env = raw_envelopes(old, sr, extra_bands={"vocal": VOCAL_BAND})
    new_env = raw_envelopes(new, sr, extra_bands={"vocal": VOCAL_BAND})
    grid = _grid(old, sr, bpm, downbeat, beats_per_bar)

    windows = local_lags(old_env["rms"], new_env["rms"])
    coarse, offset_r = global_offset(old_env["rms"], new_env["rms"])
    kind, diagnosis = classify_lags(windows, coarse, offset_r, bpm=grid.bpm)

    old_audible = _audible(old_env["rms"])
    new_audible = _audible(new_env["rms"])
    # From the sample counts: the envelopes have one frame more than whole hops.
    old_duration = round(len(old) / sr, 2)
    new_duration = round(len(new) / sr, 2)

    lag, ratio = coarse, None
    onsets_r = None
    if kind == "shift":
        lag = refine_lag(_mono(old), _mono(new), sr, old_env["rms"], new_env["rms"], coarse)
        # The level envelope of a looped groove lines up with itself at any
        # speed near 1, and so do its windows; the onsets don't. A shift that
        # leaves the onsets uncorrelated gets the stretch test too.
        onsets_r = onset_alignment(old_env["flux"], new_env["flux"], lag)
    if kind != "shift" or onsets_r < _ONSETS_ALIGNED:
        found = tempo_change(old_env, new_env, windows, old_audible, new_audible, tolerance)
        if found is not None:
            ratio, lag, offset_r = found
            kind = "tempo"
            pace = "faster" if ratio > 1 else "slower"
            diagnosis = (
                f"the same material {abs(ratio - 1.0) * 100:.2f}% {pace}, {grid.bpm * ratio:.2f} BPM against "
                f"{grid.bpm:.2f}: stretched by that much, the whole new master lines up with the old one "
                f"(r {offset_r:.2f}) -- a new grid under everything"
            )

    common = {
        "grid": grid,
        "windows": tuple(windows),
        "offset_r": offset_r,
        "old_duration": old_duration,
        "new_duration": new_duration,
        "old_audible": old_audible,
        "new_audible": new_audible,
        "old_label": old_label,
        "new_label": new_label,
        "tolerance": tolerance,
        "silent_start": silent_start,
        "tempo_ratio": None if ratio is None else round(ratio, 5),
    }
    notes = _grid_notes(grid)
    if kind != "shift":
        return MasterCheck(
            verdict="new grid",
            detail=f"new grid: {diagnosis.split(': ')[0]} -- re-analyse the new master and re-compose",
            diagnosis=diagnosis,
            offset=round(lag, 4),
            sections=(),
            bars=(),
            notes=notes,
            **common,
        )

    new_start = round(silent_start + lag, 4)
    head = _head_change(old_audible, new_audible, lag, grid) if abs(lag) > tolerance else None
    if head is not None:
        return MasterCheck(
            verdict="new grid",
            detail=f"new grid: {head} -- re-analyse the new master and re-compose",
            diagnosis=diagnosis,
            offset=round(lag, 4),
            sections=(),
            bars=(),
            notes=notes,
            **common,
        )

    sections = tuple(section_matches(old_env, new_env, grid, lag))
    bars = tuple(
        bar_changes(
            old_env,
            new_env,
            grid,
            lag,
            keys=keys,
            max_delta=max_delta,
            max_new_voice=max_new_voice,
            min_r=min_r,
            tolerance=tolerance,
        )
    )
    vocal_lag, vocal_r = vocal_shift(old_env["vocal"], new_env["vocal"], lag)
    moved = vocal_lag is not None and abs(vocal_lag - lag) > max(tolerance, _AGREE)
    if onsets_r is not None and onsets_r < _ONSETS_ALIGNED:
        notes += (
            f"the onsets correlate only r {onsets_r:.2f} at this shift, and no steady speed change explains "
            f"them either: the rhythm itself changed, or the shift is wrong -- listen before trusting the bars",
        )
    if moved:
        notes += (
            f"vocal moved {vocal_lag - lag:+.2f} s (r {vocal_r:.2f}): the beat holds, but the vocal band lines up "
            f"{abs(vocal_lag - lag):.2f} s {'later' if vocal_lag > lag else 'earlier'} -- cues cut to the vocal "
            f"move with it",
        )
    notes += _section_notes(sections, skip_vocal=moved)
    notes += _length_notes(old_audible, new_audible, lag, grid)

    changed = _ranges([b.bar for b in bars if b.changed])
    shift = abs(lag) > tolerance
    where = _shift_clause(lag, silent_start, new_start, tolerance)
    if changed:
        verdict = "rerender"
        detail = "rerender " + _describe_changes(changed, bars, grid)
        if shift:
            detail += f"; {where}"
    elif shift:
        verdict = "offset"
        detail = f"offset {lag:+.3f} s: {where}, and deliver -- nothing to re-render"
    else:
        verdict = "remux"
        detail = "remux: same grid, no bar changed"
        if abs(lag) >= 0.0005:
            detail += f" ({where})"
    return MasterCheck(
        verdict=verdict,
        detail=detail,
        diagnosis=diagnosis,
        offset=round(lag, 4),
        sections=sections,
        bars=bars,
        notes=notes,
        new_silent_start=new_start,
        vocal_lag=None if vocal_lag is None else round(vocal_lag, 2),
        vocal_r=vocal_r,
        **common,
    )


# --------------------------------------------------------------------------
# 1. did the grid move?
# --------------------------------------------------------------------------
def local_lags(
    old_db: np.ndarray,
    new_db: np.ndarray,
    *,
    window: float = WINDOW_SECONDS,
    step: float = STEP_SECONDS,
    search: float = SEARCH_SECONDS,
) -> list[LagWindow]:
    """Where each 8 s stretch of the old master sits in the new one.

    Normalised cross-correlation (Pearson r at every lag), so a louder or
    quieter new master lines up exactly as well as an identical one: loudness
    is not what moved the picture off its grid.
    """
    old_db = np.asarray(old_db, dtype=np.float64)
    new_db = np.asarray(new_db, dtype=np.float64)
    width = min(round(window * FPS), len(old_db))
    hop = round(step * FPS)
    reach = round(search * FPS)
    # Floor-padded both sides (and out to the old master's length), so every
    # window has every lag to compare against -- past either end of the new
    # master, it is silence.
    tail = max(0, len(old_db) - len(new_db)) + width + reach
    padded = np.concatenate([np.full(reach, FLOOR_DB), new_db, np.full(tail, FLOOR_DB)])

    windows = []
    for start in range(0, max(1, len(old_db) - width + 1), hop):
        a = old_db[start : start + width]
        if a.std() < _FLAT_DB:
            windows.append(LagWindow(start=start / FPS, lag=None, r=None))
            continue
        candidates = np.lib.stride_tricks.sliding_window_view(
            padded[start : start + width + 2 * reach], width
        )
        r = _pearson_rows(candidates, a)
        best = _tie_break(r, reach)
        if r[best] < _MIN_MATCH_R:
            windows.append(LagWindow(start=start / FPS, lag=None, r=round(float(r[best]), 3)))
            continue
        windows.append(
            LagWindow(start=start / FPS, lag=round((best - reach) / FPS, 2), r=round(float(r[best]), 3))
        )
    return windows


def global_offset(
    old_db: np.ndarray, new_db: np.ndarray, *, search: float = GLOBAL_SEARCH_SECONDS
) -> tuple[float, float]:
    """(lag, r) that best aligns the new master with the old *as a whole*.

    The windows alone have a blind spot: they search +-1.5 s, and a loop
    lines up with itself one bar later. Two bars of new intro on a steady
    groove moves everything by exactly a whole number of beats, and every
    window happily finds the drums lining up at 0.00 s. The song as a whole
    -- intro, drop, breakdown -- doesn't repeat like that, so one alignment
    of the entire envelope over a wider search catches what the windows
    can't.
    """
    lags, r = _offset_curve(old_db, new_db, round(search * FPS))
    best = _tie_break(r, len(lags) // 2)
    return round(float(lags[best]) / FPS, 2), round(float(r[best]), 3)


def _offset_curve(old_db: np.ndarray, new_db: np.ndarray, reach: int) -> tuple[np.ndarray, np.ndarray]:
    """Pearson r of the overlap at every lag in [-reach, reach] frames (-1
    where the overlap is under half the shorter envelope, or flat)."""
    a = np.asarray(old_db, dtype=np.float64)
    b = np.asarray(new_db, dtype=np.float64)
    min_overlap = max(1, min(len(a), len(b)) // 2)
    ca = np.concatenate([[0.0], np.cumsum(a)])
    caa = np.concatenate([[0.0], np.cumsum(a * a)])
    cb = np.concatenate([[0.0], np.cumsum(b)])
    cbb = np.concatenate([[0.0], np.cumsum(b * b)])

    lags = np.arange(-reach, reach + 1)
    r = np.full(len(lags), -1.0)
    for i, lag in enumerate(lags):
        lo, hi = max(0, -lag), min(len(a), len(b) - lag)
        m = hi - lo
        if m < min_overlap:
            continue
        sa, sb = ca[hi] - ca[lo], cb[hi + lag] - cb[lo + lag]
        va = (caa[hi] - caa[lo]) - sa * sa / m
        vb = (cbb[hi + lag] - cbb[lo + lag]) - sb * sb / m
        if va <= 1e-9 or vb <= 1e-9:
            continue
        cov = float(np.dot(a[lo:hi], b[lo + lag : hi + lag])) - sa * sb / m
        r[i] = cov / math.sqrt(va * vb)
    return lags, r


def classify_lags(
    windows: list[LagWindow], offset: float, offset_r: float = 1.0, *, bpm: float | None = None
) -> tuple[str, str]:
    """(kind, one line saying what the lags show).

    `kind` is "shift" when one constant shift -- the song-wide `offset` --
    explains every window that matched; compare_signals() then decides
    whether that shift is inside the tolerance, an offset, or an insertion.
    Otherwise "tempo" (lags that grow steadily with time), "moved" (lags
    that jump partway), or "unconfirmed" (no window matched at all) -- and
    the rest of this function only decides how to describe those, because
    "re-compose" is a much smaller job when the answer is "the tempo
    differs" than when it is "the second half moved".
    """
    matched = [w for w in windows if w.lag is not None]
    unmatched = len(windows) - len(matched)
    tail = f", {unmatched} without a confident match" if unmatched else ""
    if not matched:
        return "unconfirmed", (
            f"none of {len(windows)} windows matched confidently: the grid can't be confirmed, "
            f"so treat it as moved"
        )

    lags = np.array([w.lag for w in matched])
    times = np.array([w.start for w in matched])
    agree = float(np.mean(np.abs(lags - offset) <= _AGREE + 1e-9))
    # Windows that had something to line up (not flat): one shift must be
    # confirmed by most of them, not by the one that happened to match.
    voting = sum(1 for w in windows if w.lag is not None or w.r is not None)
    if agree == 1.0 and len(matched) >= voting / 2:
        return "shift", (
            f"one shift for the whole song: {len(matched)}/{len(windows)} windows and the song as a whole "
            f"line up at {offset:+.2f} s{tail}"
        )

    # One shift for the whole song that the windows can't see: they can't
    # reach it (+-1.5 s), or they found the loop lining up with itself a whole
    # number of beats away -- 0.00 s included. A song-wide match that strong
    # isn't something a partial move produces: half a song lining up at one
    # offset scores far lower.
    at_zero = float(np.mean(np.abs(lags) <= _AGREE + 1e-9))
    if offset_r >= 0.8:
        if at_zero == 1.0:
            return "shift", (
                f"every window lines up at 0.00 s, but the song as a whole lines up at "
                f"{offset:+.2f} s -- an offset of whole beats, which a loop hides from the "
                f"+-{SEARCH_SECONDS:g} s windows"
            )
        beyond = abs(offset) > SEARCH_SECONDS and (at_zero < 1 / 3 or offset_r >= 0.9)
        if agree >= 2 / 3 or beyond:
            return "shift", f"the whole new master sits {offset:+.2f} s from the old one{tail}"

    # A tempo change: lags that grow steadily with time. A median-of-slopes
    # line, and most windows sitting on it, so one window that locked onto
    # the wrong beat of a loop can't hide the trend -- nor fake one.
    if len(lags) >= 3 and np.ptp(times) > 0:
        slope = _theil_sen(times, lags)
        fitted = float(np.median(lags - slope * times)) + slope * times
        on_line = float(np.mean(np.abs(lags - fitted) <= _AGREE + 1e-9))
        if on_line >= 0.7 and abs(slope) * np.ptp(times) > _AGREE:
            pace = "slower" if slope > 0 else "faster"
            tempo = f", about {bpm / (1.0 + slope):.2f} BPM against {bpm:.2f}" if bpm else ""
            return "tempo", (
                f"the tempo differs{tempo}: lags drift {slope * 60:+.2f} s per minute, the new master "
                f"runs {abs(slope) * 100:.2f}% {pace}"
            )

    moved = [w for w in matched if abs(w.lag - offset) > _AGREE]
    if not moved:
        return "unconfirmed", (
            f"only {len(matched)} of {len(windows)} windows matched confidently: the grid can't be "
            f"confirmed, so treat it as moved"
        )
    first_moved = moved[0]
    return "moved", (
        f"material moved inside the song from {first_moved.start:.0f} s on: lags range "
        f"{lags.min():+.2f} to {lags.max():+.2f} s{tail}"
    )


def refine_lag(
    old: np.ndarray,
    new: np.ndarray,
    sr: int,
    old_db: np.ndarray,
    new_db: np.ndarray,
    coarse: float,
) -> float:
    """The song-wide shift to the millisecond, from its whole-frame estimate.

    First a parabola through the envelope correlation at the three frames
    around `coarse`. Then the audio itself: up to four 2.7 s stretches of
    the old master, spread over its audible length, each cross-correlated
    with the new one around that answer, phase only (every frequency weighted
    alike, so a remaster's EQ doesn't pull the peak). When at least two
    stretches agree within a millisecond their median is the shift -- the
    same material gives a peak that lands on the sample. A pitch-shifted or
    heavily processed master doesn't, and keeps the envelope's answer.
    """
    frames = round(coarse * FPS)
    lags, r = _offset_curve(old_db, new_db, abs(frames) + 1)
    centre = int(np.flatnonzero(lags == frames)[0])
    lag = coarse
    if 0 < centre < len(r) - 1 and min(r[centre - 1 : centre + 2]) > -1.0:
        left, mid, right = r[centre - 1], r[centre], r[centre + 1]
        denom = left - 2.0 * mid + right
        if denom < 0:
            lag = coarse + float(np.clip(0.5 * (left - right) / denom, -0.5, 0.5)) / FPS

    old = np.asarray(old, dtype=np.float64)
    new = np.asarray(new, dtype=np.float64)
    length = min(_FINE_SEGMENT, len(old) // 2)
    reach = round(_FINE_REACH * sr)
    base = round(lag * sr)
    start, end = _audible(np.asarray(old_db, dtype=np.float64))
    first = max(0, round(start * sr), -base + reach)
    last = min(round(end * sr) - length, len(old) - length, len(new) - base - length - reach)
    if length < 1024 or last < first:
        return round(lag, 4)
    answers = []
    for s in np.linspace(first, last, 4).astype(np.int64) if last > first else [first]:
        x = old[s : s + length]
        y = new[s + base - reach : s + base + length + reach]
        found = _phase_peak(x, y, reach)
        if found is not None:
            answers.append((base + found) / sr)
    if len(answers) >= 2 and np.ptp(answers) <= _FINE_SPREAD:
        return round(float(np.median(answers)), 4)
    return round(lag, 4)


def _phase_peak(x: np.ndarray, y: np.ndarray, reach: int) -> float | None:
    """Where `x` sits inside `y` (samples past `reach`), phase-only cross-
    correlation with parabolic interpolation; None without a clear peak."""
    if np.std(x) < 1e-6 or np.std(y) < 1e-6:
        return None
    n = 1 << (len(y) + len(x)).bit_length()
    spectrum = np.fft.rfft(y, n) * np.conj(np.fft.rfft(x * np.hanning(len(x)), n))
    spectrum /= np.maximum(np.abs(spectrum), 1e-12)
    cc = np.fft.irfft(spectrum, n)[: 2 * reach + 1]
    peak = int(np.argmax(cc))
    rest = np.concatenate([cc[: max(0, peak - 8)], cc[peak + 9 :]])
    if cc[peak] <= 0 or (len(rest) and cc[peak] < 3.0 * float(np.max(np.abs(rest)))):
        return None
    shift = 0.0
    if 0 < peak < len(cc) - 1:
        left, mid, right = cc[peak - 1], cc[peak], cc[peak + 1]
        denom = left - 2.0 * mid + right
        if denom < 0:
            shift = float(np.clip(0.5 * (left - right) / denom, -0.5, 0.5))
    return peak + shift - reach


def tempo_change(
    old_env: dict,
    new_env: dict,
    windows: list[LagWindow],
    old_audible: tuple[float, float],
    new_audible: tuple[float, float],
    tolerance: float = TOLERANCE,
) -> tuple[float, float, float] | None:
    """(speed ratio, lag, r) if the new master is the old one played faster or
    slower -- a varispeed, or a time-stretch -- else None.

    Windows only see a tempo change they can follow: at 6% faster, material
    has moved past their +-1.5 s search within half a minute, and the 8 s
    windows no longer even look alike. So the new level envelope (`rms`) is
    resampled onto the old one's timeline at trial speeds and the whole song
    aligned again. The trials start from two guesses -- the drift of the
    windows that did match, and the ratio of the two audible lengths -- and
    search 0.5% either side in 0.1% steps, then 0.01%. Where five or more
    windows followed the drift, their line is the sharper measure (it is the
    material's displacement itself, where the song-wide r is flat-topped to
    about 0.01%) and wins whenever it aligns within 0.005 of the best r:
    0.5% faster at 80 BPM reads 80.40, where the r peak alone said 80.39.

    A stretch is accepted when it aligns the levels clearly better than no
    stretch does -- or, on a loop whose levels line up at any speed near 1,
    when it is what brings the onsets (`flux`) into line.
    """
    old_db = np.asarray(old_env["rms"], dtype=np.float64)
    new_db = np.asarray(new_env["rms"], dtype=np.float64)
    guesses = []
    followed = None
    matched = [w for w in windows if w.lag is not None]
    if len(matched) >= 3:
        times = np.array([w.start for w in matched])
        if np.ptp(times) > 0:
            slope = _theil_sen(times, np.array([w.lag for w in matched]))
            if slope > -0.9:
                guesses.append(1.0 / (1.0 + slope))
                if len(matched) >= 5:
                    followed = guesses[-1]
    new_length = new_audible[1] - new_audible[0]
    if new_length > 0:
        guesses.append((old_audible[1] - old_audible[0]) / new_length)
    guesses = [g for g in guesses if 0.5 <= g <= 2.0]
    if not guesses:
        return None

    def trial(ratio: float) -> tuple[float, float, float]:
        warped = np.interp(np.arange(round(len(new_db) * ratio)) / ratio, np.arange(len(new_db)), new_db)
        lags, r = _offset_curve(old_db, warped, round(5.0 * FPS))
        best = int(np.argmax(r))
        peak, shift = float(r[best]), 0.0
        # The peak between whole-frame lags: without it r steps as the best
        # lag jumps a frame, and speeds a hundredth of a percent apart can't
        # be told apart.
        if 0 < best < len(r) - 1 and min(r[best - 1], r[best + 1]) > -1.0:
            left, mid, right = r[best - 1], r[best], r[best + 1]
            denom = left - 2.0 * mid + right
            if denom < 0:
                shift = float(np.clip(0.5 * (left - right) / denom, -0.5, 0.5))
                peak = float(mid - 0.25 * (left - right) * shift)
        return peak, ratio, (float(lags[best]) + shift) / FPS

    best = max(trial(g * (1.0 + 0.001 * k)) for g in guesses for k in range(-5, 6))
    best = max([best] + [trial(best[1] * (1.0 + 0.0001 * k)) for k in range(-10, 11)])
    if followed is not None:
        line = trial(followed)
        if line[0] >= best[0] - 0.005:
            best = line
    r, ratio, lag = best
    drift = abs(1.0 - 1.0 / ratio) * len(old_db) / FPS
    if r < _STRETCH_R or drift <= tolerance:
        return None
    lags, unstretched = _offset_curve(old_db, new_db, round(5.0 * FPS))
    at = int(np.argmax(unstretched))
    if r < float(unstretched[at]) + _STRETCH_GAIN:
        if "flux" not in old_env or "flux" not in new_env:
            return None
        # On the old timeline, frame i of the old master is frame (i + L) / ratio of the new.
        before = onset_alignment(old_env["flux"], new_env["flux"], float(lags[at]) / FPS)
        after = onset_alignment(old_env["flux"], new_env["flux"], lag / ratio, ratio)
        if not (before < _ONSETS_ALIGNED and after >= _ONSETS_STRETCHED):
            return None
    # The lag is on the old timeline; the new master's own clock runs 1/ratio as fast.
    return ratio, lag / ratio, round(r, 3)


def onset_alignment(old_flux: np.ndarray, new_flux: np.ndarray, lag: float, ratio: float = 1.0) -> float:
    """Pearson r of the two onset envelopes, the new one read `lag` seconds
    later and `ratio` times as fast (frame i of the old master against the
    new master at lag + i / (FPS * ratio) seconds). Onsets are what a real
    alignment lines up and a near miss doesn't -- see _ONSETS_ALIGNED."""
    old_flux = np.asarray(old_flux, dtype=np.float64)
    new_flux = np.asarray(new_flux, dtype=np.float64)
    at = lag * FPS + np.arange(len(old_flux)) / ratio
    inside = (at >= 0) & (at <= len(new_flux) - 1)
    if int(inside.sum()) < 2:
        return 0.0
    a = old_flux[inside]
    b = np.interp(at[inside], np.arange(len(new_flux)), new_flux)
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return 0.0
    # Unrounded: the speed search compares values a few 1e-4 apart.
    return float(np.corrcoef(a, b)[0, 1])


def _theil_sen(x: np.ndarray, y: np.ndarray) -> float:
    """Median of pairwise slopes -- a line fit that ignores a few wild points."""
    i, j = np.triu_indices(len(x), k=1)
    dx = x[j] - x[i]
    keep = dx != 0
    return float(np.median((y[j] - y[i])[keep] / dx[keep])) if keep.any() else 0.0


def vocal_shift(
    old_vocal_db: np.ndarray, new_vocal_db: np.ndarray, lag: float
) -> tuple[float | None, float | None]:
    """(lag, r) where the vocal band lines up best, when that is clearly
    somewhere other than `lag` -- where the mix lines up -- else (None, None).

    A new master can keep the beat and move the voice: a bar of intro
    added under a loop that carries on unchanged moves the vocal, and every
    cue cut to it, a bar later while every window of the mix still reads
    0.00 s. Per section that looks like a different take everywhere; the
    whole vocal band lining up at one other shift says what it is.
    """
    lags, r = _offset_curve(old_vocal_db, new_vocal_db, round(GLOBAL_SEARCH_SECONDS * FPS))
    best = _tie_break(r, len(lags) // 2)
    at_mix = int(np.clip(round(lag * FPS) + len(lags) // 2, 0, len(lags) - 1))
    if r[best] >= _VOCAL_MOVED_R and r[best] - r[at_mix] >= _VOCAL_MOVED_GAIN and best != at_mix:
        return float(lags[best]) / FPS, round(float(r[best]), 2)
    return None, None


# --------------------------------------------------------------------------
# 2. what would a piece hear differently?
# --------------------------------------------------------------------------
def section_matches(old_env: dict, new_env: dict, grid: Grid, lag: float = 0.0) -> list[SectionMatch]:
    """Vocal-band and full-mix correlation, one SECTION_BARS phrase at a time,
    the new master aligned by `lag`. A section where the old master is silent
    -- past its end, before its start -- has nothing to correlate: None."""
    n = _span(old_env, new_env, lag)
    old_voc, new_voc = _pad(old_env["vocal"], n), _aligned(new_env["vocal"], n, lag, FLOOR_DB)
    old_mix, new_mix = _pad(old_env["rms"], n), _aligned(new_env["rms"], n, lag, FLOOR_DB)
    sounding = old_mix > float(np.max(old_env["rms"])) - _AUDIBLE_DB
    # Only frames both masters have: the floor that pads one past its end is
    # an outlier that would drag a correlation down on its own.
    at = np.arange(n) + lag * FPS
    shared = (np.arange(n) < len(old_env["rms"])) & (at >= 0) & (at <= len(new_env["rms"]) - 1)
    first, last = _bar_span(grid, n / FPS)
    # Phrases count from bar 1; any bars before it are one pickup section.
    spans = [(first, min(0, last))] if first <= 0 else []
    spans += [
        (bar, min(bar + SECTION_BARS - 1, last)) for bar in range(max(1, first), last + 1, SECTION_BARS)
    ]
    sections = []
    for bar, end_bar in spans:
        lo, hi = _frames(grid.bar_start(bar), grid.bar_start(end_bar + 1), n)
        if hi - lo < 2:
            continue
        use = np.flatnonzero(shared[lo:hi]) + lo
        measured = len(use) >= 2 and float(np.mean(sounding[lo:hi])) >= 0.5
        sections.append(
            SectionMatch(
                first_bar=bar,
                last_bar=end_bar,
                start=round(max(0.0, grid.bar_start(bar)), 2),
                end=round(min((n - 1) / FPS, grid.bar_start(end_bar + 1)), 2),
                vocal_r=_pearson(old_voc[use], new_voc[use]) if measured else None,
                mix_r=_pearson(old_mix[use], new_mix[use]) if measured else None,
            )
        )
    return sections


def bar_changes(
    old_env: dict,
    new_env: dict,
    grid: Grid,
    lag: float = 0.0,
    *,
    keys: tuple[str, ...] = ENVELOPES,
    max_delta: float = DELTA_THRESHOLD,
    max_new_voice: float = NEW_VOICE_THRESHOLD,
    min_r: float = SHAPE_THRESHOLD,
    rhythm_r: float = RHYTHM_THRESHOLD,
    tolerance: float = TOLERANCE,
) -> list[BarChange]:
    """Every bar of the grid: which envelopes a piece reads would move differently.

    `old_env` and `new_env` are raw_envelopes() of each master (plus the
    `vocal` band); the new one is read `lag` seconds later. Level envelopes
    go on the old master's 0..1 scale (_on_old_scale) and are compared frame
    by frame, the new one allowed to slide by up to `tolerance` -- inside
    the tolerance is the same grid, here as everywhere. The flux envelopes
    are compared as rhythm: onset energy summed per 16th of the bar, square-
    rooted so the hats count next to the snare, correlated old against new.
    `voc` is compared only when both masters have one (stereo, not dual
    mono). Past the end of either master it is silence.
    """
    n = _span(old_env, new_env, lag)
    slide = math.floor(tolerance * FPS + 1e-9)
    first, last = _bar_span(grid, n / FPS)
    bounds = [(_frames(grid.bar_start(b), grid.bar_start(b + 1), n), b) for b in range(first, last + 1)]
    bounds = [(lo, hi, b) for (lo, hi), b in bounds if hi > lo]
    los = np.array([lo for lo, _, _ in bounds])
    his = np.array([hi for _, hi, _ in bounds])

    readings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for key in keys:
        if key in _RHYTHMS or key not in old_env or key not in new_env:
            continue
        old_level, new_level = _on_old_scale(old_env, new_env, key, n, lag)
        readings[key] = _level_stats(old_level, new_level, los, his, slide)
    rhythms: dict[str, np.ndarray] = {}
    for key in keys:
        if key in _RHYTHMS:
            rhythms[key] = _rhythm_stats(old_env[key], new_env[key], n, lag, grid, [b for _, _, b in bounds])
    old_vocal, new_vocal = _on_old_scale(old_env, new_env, "vocal", n, lag)

    changes = []
    for i, (lo, hi, bar) in enumerate(bounds):
        detail: dict = {}
        flagged = []
        deltas = []
        for key, (delta, shape) in readings.items():
            d = round(float(delta[i]), 3)
            r = None if np.isnan(shape[i]) else round(float(shape[i]), 3)
            detail[key] = {"delta": d, "r": r}
            deltas.append(d)
            if d > max_delta or (r is not None and r < min_r):
                flagged.append((max(d - max_delta, (min_r - r) if r is not None else 0.0), key))
        for key, profile in rhythms.items():
            r = profile[i]
            detail[key] = {"r": None if np.isnan(r) else round(float(r), 3)}
            if not np.isnan(r) and r < rhythm_r:
                flagged.append((rhythm_r - r, key))
        fresh = float(np.mean((new_vocal[lo:hi] > NEW_VOICE_ON) & (old_vocal[lo:hi] < NEW_VOICE_OFF)))
        names = tuple(key for _, key in sorted(flagged, key=lambda f: -f[0]))
        changes.append(
            BarChange(
                bar=bar,
                start=round(max(0.0, grid.bar_start(bar)), 2),
                end=round(min((n - 1) / FPS, grid.bar_start(bar + 1)), 2),
                delta=max(deltas) if deltas else 0.0,
                new_voice=round(fresh, 3),
                changed=bool(names) or fresh > max_new_voice,
                envelopes=names,
                detail=detail,
            )
        )
    return changes


def _on_old_scale(
    old_env: dict, new_env: dict, key: str, n: int, lag: float
) -> tuple[np.ndarray, np.ndarray]:
    """Both masters' `key` on the old master's 0..1 scale, the new one aligned.

    For the dB envelopes, the new one's overall gain difference in that band
    (the median over frames where both sound) is taken out first, then both
    go through the old master's 5th/99.5th percentiles -- the pack's own
    normalisation, but one scale for both, so a louder or brighter master
    lands where the old one was instead of being stretched onto its own
    range. `cent` is already absolute: Hz over 8000, 0 where there is silence.
    """
    if key == "cent":
        old = _pad(old_env["cent"], n, 0.0) / 8000.0
        new = _aligned(new_env["cent"], n, lag, 0.0) / 8000.0
        old[_pad(old_env["rms"], n) <= FLOOR_DB] = 0.0
        new[_aligned(new_env["rms"], n, lag, FLOOR_DB) <= FLOOR_DB] = 0.0
        return np.clip(old, 0.0, 1.0), np.clip(new, 0.0, 1.0)
    floor = float(np.min(old_env[key])) if key == "voc" else FLOOR_DB
    raw_old = np.asarray(old_env[key], dtype=np.float64)
    old = _pad(raw_old, n, floor)
    new = _aligned(new_env[key], n, lag, floor)
    both = (old > float(np.max(old)) - _AUDIBLE_DB) & (new > float(np.max(new)) - _AUDIBLE_DB)
    both &= (old > floor) & (new > floor)
    if int(both.sum()) >= FPS:
        new = new - float(np.median(new[both] - old[both]))
    lo, hi = np.percentile(raw_old, [5.0, 99.5])
    if not hi - lo > 1e-9:
        return np.zeros(n), np.zeros(n)
    return np.clip((old - lo) / (hi - lo), 0.0, 1.0), np.clip((new - lo) / (hi - lo), 0.0, 1.0)


def _level_stats(
    old: np.ndarray, new: np.ndarray, los: np.ndarray, his: np.ndarray, slide: int
) -> tuple[np.ndarray, np.ndarray]:
    """Per bar: the smallest mean |old - new| and the best Pearson r over
    every slide of the new envelope within +-`slide` frames (NaN where either
    barely moves)."""
    counts = (his - los).astype(np.float64)

    def sums(values: np.ndarray) -> np.ndarray:
        c = np.concatenate([[0.0], np.cumsum(values)])
        return c[his] - c[los]

    so, soo = sums(old), sums(old * old)
    var_o = np.maximum(soo / counts - (so / counts) ** 2, 0.0)
    delta = np.full(len(los), np.inf)
    shape = np.full(len(los), -np.inf)
    active = np.zeros(len(los), dtype=bool)
    for s in range(-slide, slide + 1):
        moved = np.roll(new, s)
        if s > 0:
            moved[:s] = new[0]
        elif s < 0:
            moved[s:] = new[-1]
        delta = np.minimum(delta, sums(np.abs(old - moved)) / counts)
        sn, snn, son = sums(moved), sums(moved * moved), sums(old * moved)
        var_n = np.maximum(snn / counts - (sn / counts) ** 2, 0.0)
        ok = (np.sqrt(var_o) > _SHAPE_ACTIVITY) & (np.sqrt(var_n) > _SHAPE_ACTIVITY) & (counts >= 2)
        cov = son / counts - (so / counts) * (sn / counts)
        r = np.divide(cov, np.sqrt(var_o * var_n), out=np.full(len(los), -np.inf), where=ok)
        shape = np.maximum(shape, r)
        active |= ok
    return delta, np.where(active, shape, np.nan)


def _rhythm_stats(
    old_flux: np.ndarray, new_flux: np.ndarray, n: int, lag: float, grid: Grid, bars: list[int]
) -> np.ndarray:
    """Per bar: Pearson r of old and new onset energy per 16th (square-rooted);
    NaN where neither sounds, 0 where only one does."""
    old = _pad(old_flux, n, 0.0)
    new = _aligned(new_flux, n, lag, 0.0)
    slots = 4 * grid.beats_per_bar
    step = grid.bar_seconds / slots
    c_old = np.concatenate([[0.0], np.cumsum(old)])
    c_new = np.concatenate([[0.0], np.cumsum(new)])
    profiles_old = np.zeros((len(bars), slots))
    profiles_new = np.zeros((len(bars), slots))
    for i, bar in enumerate(bars):
        centres = grid.bar_start(bar) + step * np.arange(slots)
        lo = np.clip(np.ceil((centres - step / 2) * FPS - 1e-9).astype(int), 0, n)
        hi = np.clip(np.ceil((centres + step / 2) * FPS - 1e-9).astype(int), 0, n)
        profiles_old[i] = c_old[hi] - c_old[lo]
        profiles_new[i] = c_new[hi] - c_new[lo]
    totals_old = profiles_old.sum(axis=1)
    totals_new = profiles_new.sum(axis=1)
    sounds_old = totals_old > _RHYTHM_ACTIVITY * max(
        float(np.median(totals_old[totals_old > 0])) if np.any(totals_old > 0) else 0.0, 1e-12
    )
    sounds_new = totals_new > _RHYTHM_ACTIVITY * max(
        float(np.median(totals_new[totals_new > 0])) if np.any(totals_new > 0) else 0.0, 1e-12
    )
    out = np.full(len(bars), np.nan)
    for i in range(len(bars)):
        if sounds_old[i] and sounds_new[i]:
            a, b = np.sqrt(profiles_old[i]), np.sqrt(profiles_new[i])
            if np.std(a) > 1e-12 and np.std(b) > 1e-12:
                out[i] = float(np.corrcoef(a, b)[0, 1])
            else:
                out[i] = 1.0 if np.allclose(a, b) else 0.0
        elif sounds_old[i] != sounds_new[i]:
            out[i] = 0.0
    return out


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------
def format_report(check: MasterCheck) -> str:
    """The printed verdict: what was compared, what the lags say, what changed."""
    g = check.grid
    confidence = "" if g.confidence is None else f", downbeat confidence {g.confidence:.2f}"
    lines = [
        f"master-check: {check.old_label} -> {check.new_label}",
        f"  grid      {g.bpm:.2f} BPM, bar 1 at {g.downbeat:.3f} s, "
        f"{g.beats_per_bar} beats/bar ({g.source}{confidence})",
        f"  length    old {check.old_duration:.2f} s (audible {check.old_audible[0]:.2f}-"
        f"{check.old_audible[1]:.2f}), new {check.new_duration:.2f} s (audible "
        f"{check.new_audible[0]:.2f}-{check.new_audible[1]:.2f})",
        f"  lag       {check.diagnosis}",
    ]
    if check.tempo_ratio is not None:
        lines.append(
            f"  offset    at {check.tempo_ratio:.4f}x speed the whole song lines up (r {check.offset_r:.2f})"
        )
    else:
        lines.append(
            f"  offset    whole song lines up at {check.offset:+.3f} s (r {check.offset_r:.2f}); "
            f"tolerance +-{check.tolerance:.3f} s"
        )
    if check.new_silent_start is not None and abs(check.offset) >= 0.0005:
        lines.append(
            f"  delivery  silent_start {_num(check.new_silent_start)} for the new master "
            f"(was {_num(check.silent_start)})"
        )
    moved = [w for w in check.windows if w.lag is not None and abs(w.lag - check.offset) > _AGREE]
    if moved:
        lines.append("  windows   " + ", ".join(f"{w.start:.0f}s {w.lag:+.2f}" for w in moved[:12]))
        if len(moved) > 12:
            lines.append(f"            ... and {len(moved) - 12} more (see --json)")
    if check.sections:
        lines.append("  sections  bars        time                   vocal r   mix r")
        for s in check.sections:
            lines.append(
                f"            {s.first_bar:>3}-{s.last_bar:<5}  {_clock(s.start)}-{_clock(s.end):<9}  "
                f"{_r(s.vocal_r):>7}   {_r(s.mix_r):>5}"
            )
    changed = [b for b in check.bars if b.changed]
    if changed:
        lines.append(f"  changed   {len(changed)} bar(s)    time                   what changed")
        for first, last in _ranges([b.bar for b in changed]):
            group = [b for b in changed if first <= b.bar <= last]
            label = f"{first}-{last}" if first != last else f"{first}"
            what = _what_changed(group)
            lines.append(
                f"            {label:<10}  {_clock(group[0].start)}-{_clock(group[-1].end):<9}  {what}"
            )
    for note in check.notes:
        lines.append(f"  note      {note}")
    lines.append(f"verdict: {check.detail}  (exit {check.exit_code})")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _decode(path: str) -> np.ndarray:
    pcm = decode_f32le(path, sample_rate=SAMPLE_RATE, channels=2)
    samples = np.frombuffer(pcm, dtype="<f4")
    if len(samples) < 2:
        raise ValueError(f"{path}: ffmpeg decoded no audio from it -- does it have an audio stream?")
    return samples[: len(samples) // 2 * 2].reshape(-1, 2)


def _mono(samples: np.ndarray) -> np.ndarray:
    x = np.asarray(samples)
    return x.mean(axis=1) if x.ndim == 2 else x


def _grid(old: np.ndarray, sr: int, bpm: float | None, downbeat: float | None, beats_per_bar: int) -> Grid:
    if bpm is not None and downbeat is not None:
        return Grid(bpm=float(bpm), downbeat=float(downbeat), beats_per_bar=beats_per_bar, source="given")
    pack = analyze_signal(
        old,
        sr,
        bpm_range=(bpm, bpm) if bpm is not None else DEFAULT_BPM_RANGE,
        downbeat=downbeat,
        beats_per_bar=beats_per_bar,
    )
    confidence = None
    octave = None
    if downbeat is None:
        downbeat = pack["downbeat"]
        confidence = pack["grid_check"]["downbeat"].get("confidence")
        source = "estimated from the old master" if bpm is None else "downbeat estimated from the old master"
    else:
        source = "tempo estimated from the old master"
    if bpm is None and pack["grid_check"]["octave"] is not None:
        octave = (pack["grid_check"]["octave"]["bpm"], pack["grid_check"]["octave"]["score"])
    bpm = float(bpm) if bpm is not None else float(pack["bpm"])
    return Grid(
        bpm=bpm,
        downbeat=float(downbeat),
        beats_per_bar=beats_per_bar,
        source=source,
        confidence=confidence,
        octave=octave,
    )


def _pearson_rows(rows: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Pearson r of `a` against every row of `rows`; 0 where a row is flat."""
    a0 = a - a.mean()
    rows0 = rows - rows.mean(axis=1, keepdims=True)
    denom = np.sqrt((rows0 * rows0).sum(axis=1) * float(a0 @ a0))
    return np.divide(rows0 @ a0, denom, out=np.zeros(len(rows)), where=denom > 1e-12)


def _tie_break(r: np.ndarray, zero_index: int) -> int:
    """Index of the best r, preferring the smallest shift among near-tied *peaks*.

    Only separate local maxima can tie -- a loop's aliases a beat or a bar
    apart. The neighbours of one peak are always nearly as high as the peak
    on a smooth envelope, and letting them tie would drag every answer a few
    frames toward zero: a real 0.02 s shift would read as 0.00.
    """
    padded = np.concatenate([[-np.inf], r, [-np.inf]])
    peaks = np.flatnonzero((r >= padded[:-2]) & (r >= padded[2:]))
    top = float(np.max(r))
    ties = peaks[r[peaks] >= top - _TIE_R]
    return int(ties[np.argmin(np.abs(ties - zero_index))])


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2 or np.std(a) < 1e-6 or np.std(b) < 1e-6:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def _pad(values: np.ndarray, n: int, fill: float = FLOOR_DB) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.concatenate([values, np.full(n - len(values), fill)]) if len(values) < n else values[:n].copy()


def _aligned(values: np.ndarray, n: int, lag: float, fill: float) -> np.ndarray:
    """The new master's envelope read on the old one's frames: frame i of the
    result is the new master at i/FPS + lag seconds (interpolated)."""
    values = np.asarray(values, dtype=np.float64)
    at = np.arange(n) + lag * FPS
    return np.interp(at, np.arange(len(values)), values, left=fill, right=fill)


def _span(old_env: dict, new_env: dict, lag: float) -> int:
    """Frames on the old master's timeline covering both masters once aligned."""
    return max(len(old_env["rms"]), math.ceil(len(new_env["rms"]) - lag * FPS))


def _bar_span(grid: Grid, duration: float) -> tuple[int, int]:
    """First and last bar numbers that overlap [0, duration). Bars before the
    downbeat get numbers <= 0 -- a pickup is bar 0, not a renumbered bar 1."""
    first = math.floor((0.0 - grid.downbeat) / grid.bar_seconds) + 1
    last = math.ceil((duration - grid.downbeat) / grid.bar_seconds)
    return first, max(first, last)


def _frames(start: float, end: float, n: int) -> tuple[int, int]:
    return max(0, math.ceil(start * FPS - 1e-9)), min(n, math.ceil(end * FPS - 1e-9))


def _audible(rms_db: np.ndarray) -> tuple[float, float]:
    """First and last frame within _AUDIBLE_DB of the loudest one, in seconds.
    (Never empty: the loudest frame always clears its own threshold.)"""
    loud = np.flatnonzero(rms_db > float(np.max(rms_db)) - _AUDIBLE_DB)
    return (round(loud[0] / FPS, 2), round(loud[-1] / FPS, 2))


def _head_change(old: tuple[float, float], new: tuple[float, float], lag: float, grid: Grid) -> str | None:
    """A shift that adds sound before the old master's first note, or drops
    some of it, is an insertion or a cut at the head -- the picture's opening
    no longer has its music -- not an offset. None when only silence moved."""
    expected = old[0] + lag  # where the old master's first note is in the new one
    extra = expected - new[0]
    if extra > _HEAD_MARGIN:
        bars = extra / grid.bar_seconds
        return (
            f"an insertion at the head, everything from the old master's first note on sits {lag:+.2f} s later "
            f"after {extra:.2f} s of new material ({bars:.1f} bars at {grid.bpm:.2f} BPM)"
        )
    if expected < -_HEAD_MARGIN:
        return (
            f"a cut at the head, the old master's {old[0]:.2f}-{old[0] - expected:.2f} s is gone and everything "
            f"after it sits {lag:+.2f} s"
        )
    return None


def _grid_notes(grid: Grid) -> tuple[str, ...]:
    """What to distrust about an estimated grid: bar numbers inherit both."""
    notes = []
    if grid.octave is not None and grid.octave[1] >= 0.9:
        notes.append(
            f"the estimated tempo is a close call against {grid.octave[0]:.2f} BPM (score {grid.octave[1]:.2f}): "
            f"if the edit was cut at that tempo, pass --bpm {grid.octave[0]:g}"
        )
    if grid.confidence is not None and grid.confidence < 0.6:
        notes.append(
            f"bar numbers follow a guessed downbeat (confidence {grid.confidence:.2f}): pass --downbeat "
            f"with the edit's bar 1 to count them from the right beat"
        )
    return tuple(notes)


def _length_notes(
    old: tuple[float, float], new: tuple[float, float], lag: float, grid: Grid
) -> tuple[str, ...]:
    """What the audible ends say once the shift is taken out: music past the
    old master's end has no picture yet; a master that stops early leaves
    the picture's last bars without it."""
    notes = []
    after = new[1] - (old[1] + lag)
    if after > 0.5:
        first = math.floor((old[1] - grid.downbeat) / grid.bar_seconds) + 1
        notes.append(
            f"the new master runs {after:.2f} s past the old one's end ({_clock(old[1])}): bars from "
            f"{first} on have no picture yet -- extend it, or fade the audio where the picture ends"
        )
    elif after < -0.5:
        notes.append(
            f"the new master ends {-after:.2f} s before the old one did ({_clock(new[1] - lag)} on the "
            f"picture's clock): the picture's last {-after:.2f} s would play over silence"
        )
    return tuple(notes)


def _section_notes(sections: tuple[SectionMatch, ...], *, skip_vocal: bool = False) -> tuple[str, ...]:
    """What each 8-bar section's two correlations say together: a low vocal
    band under a steady mix is the vocal changing; a low mix around a steady
    vocal band is the arrangement changing (SHOULD I ?'s re-mux case)."""
    vocal, arrangement, whole = [], [], []
    for s in sections:
        if s.vocal_r is None or s.mix_r is None:
            continue
        low_vocal, low_mix = s.vocal_r < SAME_TAKE_R, s.mix_r < SAME_MIX_R
        if low_vocal and low_mix:
            whole.append(s)
        elif low_vocal and not skip_vocal:
            vocal.append(s)
        elif low_mix:
            arrangement.append(s)
    notes = []
    if vocal:
        notes.append(
            f"vocal-band r under {SAME_TAKE_R} while the mix holds in bars {_section_list(vocal)}: a different take "
            f"or a new line there, perhaps -- the band is the full mix's, so listen before recutting"
        )
    if arrangement:
        notes.append(
            f"the arrangement changed in bars {_section_list(arrangement)} (mix r under {SAME_MIX_R}) around a "
            f"steady vocal band: a piece that follows the voice still fits, one that follows the drums may not"
        )
    if whole:
        notes.append(
            f"bars {_section_list(whole)} changed throughout (vocal-band and mix r both under {SAME_MIX_R})"
        )
    return tuple(notes)


def _section_list(sections: list[SectionMatch]) -> str:
    return ", ".join(f"{s.first_bar}-{s.last_bar}" for s in sections)


def _shift_clause(lag: float, silent_start: float, new_start: float, tolerance: float) -> str:
    within = abs(lag) <= tolerance
    where = "later" if lag > 0 else "earlier"
    head = f"the new master sits {abs(lag):.3f} s {where}"
    if within:
        return (
            f"{head}, inside the +-{tolerance:.3f} s tolerance; silent_start {_num(new_start)} makes it exact"
        )
    return f"{head} -- set the delivery sheet's silent_start to {_num(new_start)} (was {_num(silent_start)})"


def _describe_changes(ranges: list[tuple[int, int]], bars: tuple[BarChange, ...], grid: Grid) -> str:
    parts = []
    for first, last in ranges:
        group = [b for b in bars if first <= b.bar <= last and b.changed]
        label = f"bars {first}-{last}" if first != last else f"bar {first}"
        parts.append(f"{label} ({_clock(group[0].start)}-{_clock(group[-1].end)}): {_what_changed(group)}")
    return "; ".join(parts)


def _what_changed(group: list[BarChange]) -> str:
    """The envelopes that changed across a run of bars, most-changed first,
    plus the new-voice reading when that is what flagged them."""
    order: dict[str, int] = {}
    for b in group:
        for rank, key in enumerate(b.envelopes):
            order[key] = min(order.get(key, rank), rank)
    names = sorted(order, key=lambda k: (order[k], ENVELOPES.index(k)))
    compared = {key for b in group for key in b.detail}
    voice = max(b.new_voice for b in group)
    parts = []
    if names and len(names) >= 3 and set(names) == compared:
        parts.append(f"all {len(names)} envelopes changed")
    elif names:
        parts.append(", ".join(names) + " changed")
    if voice > 0 and (not names or voice >= NEW_VOICE_THRESHOLD):
        parts.append(f"new voice {voice:.2f}")
    return "; ".join(parts) if parts else "changed"


def _clock(t: float) -> str:
    """mm:ss.ss"""
    t = max(0.0, float(t))
    minutes = int(t // 60)
    return f"{minutes:02d}:{t - 60 * minutes:05.2f}"


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") if value else "0"


def _ranges(bars: list[int]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for bar in sorted(bars):
        if ranges and bar == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], bar)
        else:
            ranges.append((bar, bar))
    return ranges


def _describe_ranges(ranges: list[tuple[int, int]]) -> str:
    return ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in ranges)


def _r(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"
