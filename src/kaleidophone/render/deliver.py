"""
The delivery sheet: cut every deliverable from ONE silent render and mux the
audio under each, the way the last releases were delivered by hand.

    kaleidophone deliver sheet.yaml [-o DIR] [--dry-run]

A release ships a full film, a reel and a few stories, all out of the same
picture. Rendering each one separately would pay for the expensive step once
per deliverable for no difference in the picture. Instead the film is
rendered once, silent, with keyframes forced at every cut point, and every
deliverable is a stream-copied slice of it with its window of the master
muxed underneath -- no re-encode of the picture, and frame-identical to the
film. Every release re-wrote that as a shell script, and every script
re-learned the same rules. They live here now, with what each one cost.

The picture:

- It is cut with `-c:v copy` plus `-frames:v N`, N = round(dur * fps), never
  `-t`. `-ss t0 -t dur -c:v copy` kept 2 extra frames per cut even with
  keyframes forced at t0 (B-frame reordering); a frame count can't be
  reordered.
- Every output gets `-dn -sn -map_metadata -1 -map_chapters -1 -movflags
  +faststart`. Without them a WAV's chapter/text track rides along as a stray
  `bin_data` stream and players log a dangling "Referenced QT chapter track
  not found".
- No `-avoid_negative_ts make_zero` when the cut already starts on a keyframe,
  which every cut here does: it delayed the audio by the AAC encoder's
  1024-sample priming, +21 ms measured.
- Seek times are the frame's exact time, to the microsecond: a cut point
  typed to three decimals is off by a fraction of a millisecond whenever the
  frame time isn't a round number, and with stream copy that was enough to
  lose the whole cut or its first frame. See _frame_time().
- Keyframes belong at every cut's *end* as well as its start. `-frames:v N`
  counts packets in decode order, so a cut that ends mid-GOP can take the
  P-frame after its last frame and drop a B-frame before it. Measured with
  ffmpeg 6.1 and x264 on a synthetic render: of 11 cuts from one keyframe,
  150 to 160 frames long, 8 ended with a frame out of order; a keyframe
  forced at the end made the cut exact. The count is still right, so this is
  a warning, not an error -- the last frame is usually under a fade.

The audio -- one gain per master, and the true peak measured on what ships:

- The master is measured once, whole (loudnorm's measuring pass: integrated
  loudness and true peak), and every cut is encoded with the same gain and
  the same limiter, so a story sits at the level it has in the song. Gaining
  each cut's own window to the target flattens the song instead. Measured on
  the synthetic 100 s masters of the 0.3.0 review (ffmpeg 6.1): a 15 s story
  from a sparse intro, 16.4 dB under the chorus in the song, got +10.85 dB
  (+15.86 on the float pre-master) while the film got -5.39 (-3.88), and
  arrived 1.4 dB under the chorus, its rim shots in the limiter. The whole
  master rather than the film cut: it is what a streaming service measures,
  it doesn't depend on which cuts a sheet happens to list, and a windowed
  render (below) gets the song's gain, not its window's.
- The true-peak guard runs in every gain mode, on the delivered AAC -- after
  the limiter too. AAC overshoots: in the same review, a window limited to
  -2.0 dBTP was delivered at -0.1 against a -1 dBTP ceiling. Every cut is
  encoded at the master's setting and measured (`ebur128=peak=true`); while
  one is over the ceiling, the setting steps down by that overshoot -- in
  whole `step_db` steps, 3 dB at most in one round, `max_steps` of them in
  all -- and every cut is encoded again: stepping them all is what keeps one
  gain per master. `fixed` has nothing to step, so a file over the ceiling
  there is an error.
- The ceiling is `defaults.ceiling_dbtp`. `auto` (the default) is -1 dBTP, or
  -2 dBTP when the delivery is planned louder than -14 LUFS. Cited: Spotify
  normalises to -14 LUFS and asks for a true peak under -1 dBTP, under -2
  for masters louder than -14 LUFS, because "louder tracks are more
  susceptible to extra distortion when encoded for streaming"
  (https://support.spotify.com/us/artists/article/loudness-normalization/).
  Instagram and TikTok document no loudness normalisation (nothing in their
  help centres, September 2026), so a loud master stays loud there -- and is
  still transcoded.
- The limiter looks 4 ms ahead, and that delays its output by 767 samples at
  192 kHz (af_alimiter.c: buffer_size / channels - 1). ffmpeg 5.1 and later
  take it back with `latency=1`; on an older ffmpeg the same 767 samples are
  padded on and trimmed off around it (apad, atrim, asetpts). Measured on
  ffmpeg 4.2.2, 6.1.1 and 7.0.2: the hand trim's output is sample-identical
  to 6.1.1's latency=1, both mux at 0.0 ms against the picture, and the
  uncompensated limiter at +4.0 ms. filter_options() asks the local ffmpeg
  once which to use, and --dry-run's script asks its own.
- The limiter releases over 200 ms. Measured on a 55 Hz sine with 4 dB of
  gain reduction (ffmpeg 6.1): -41 dB of harmonic distortion at 60 ms,
  -51 dB at 200 ms.
- Every cut is faded, 5 ms in and 15 ms out, unless the sheet says otherwise:
  a story delivered unfaded ended on a step of about -22 dBFS -- a click, and
  on a platform that loops it, a click every loop. A fade set to 0 is
  checked instead: `deliver` warns unless the audio at that edge is near
  silence (under -60 dBFS).

The gain, three ways (`gain.mode`):

- `loudness` -- for an unlimited pre-master. The master's gain to the
  target, then a 4x-oversampled limiter: at 48 kHz a limiter can't see the
  peaks between samples, and a 32-bit float pre-master sat at +6.05 dBTP.
  The guard steps the limiter's ceiling down, never the gain. The target is
  the loudness going into the limiter, and a limiter working hard takes some
  off: a synthetic pre-master at -13.3 LUFS and +3.45 dBTP, gained to -14
  and limited at -2 dBFS, was delivered at -15.5 LUFS (ffmpeg 6.1).
- `fixed` -- for an already-limited master whose gain is known. Clean gain,
  no limiter: a second limiter on a finished master is a second master.
- `auto` -- clean gain from `start_db`, stepped down until every delivered
  file is under the ceiling. MIKONAMET's master, at -0.3 dBFS sample peak,
  was delivered at +1.7 dBTP through AAC at 0 dB -- not all of it the
  encoder's: a true peak is never lower than the sample peak, and the WAV's
  wasn't measured at the time. Another master needed -2.5 dB
  to stay under the ceiling, a busier one -3.5 dB. How much of that the
  encoder adds can't be predicted from the master, so the delivered file is
  measured.

Not every silent render starts at the top of the song. A stateful canvas
piece renders its reel as a window -- the harness snaps the window's start to
a beat and prints it -- and a brief with `output.window` renders a stretch.
`silent_start` says where the render's first frame sits in the song: `t0`,
`dur` and `video_from` stay on the render's own clock, and the audio is read
from `silent_start + t0`. It can be negative -- a render that starts before
the song, as when `kaleidophone master-check` finds a new master sitting
earlier than the one the picture was cut to (its `offset` verdict prints the
value) -- and the audio's head is then padded with silence until the song
begins.

`audio: none` on a cut writes it with no audio stream at all: a Spotify
Canvas is silent. A sheet whose every cut is silent needs no `audio`.

The sheet is its own file rather than a block in the CreativeBrief, on
purpose. The brief describes an edit; the sheet describes cuts of a
*finished* silent render, which may not have come from a brief at all -- a
canvas piece rendered by a browser harness, say. And the two usually run on
different machines: the picture is rendered wherever that's fast, the mux
happens where the WAV lives. That is what --dry-run is for: it prints the
whole delivery as a POSIX shell script, measurements and all, to run over
there.
"""

from __future__ import annotations

import errno
import json
import math
import os
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from kaleidophone.render._ffmpeg_util import (
    BITRATE_RE,
    concat_quote,
    decode_f32le,
    filter_options,
    probe_duration,
    probe_keyframes,
    probe_stream,
    require_ffmpeg,
    run,
    run_measure,
)

# The flags every deliverable gets -- see the module docstring.
CLEAN_OUTPUT = ["-dn", "-sn", "-map_metadata", "-1", "-map_chapters", "-1"]
FASTSTART = ["-movflags", "+faststart"]
OUTPUT_SUFFIXES = (".mp4", ".m4v", ".mov")
# Intermediates (card cuts) live here, under the output directory; .gitignore
# already ignores the name, so a stray one can't be committed.
WORK_DIR = os.path.join(".kaleidophone-cache", "deliver")
# The target in the measuring pass only shapes loudnorm's (discarded) output;
# input_i, the number read back, is the source's own loudness.
_MEASURE_TP = -1.5
_GRID_TOLERANCE = 0.01  # frames: how far off the frame grid a cut time may be typed

# Click guards every cut gets unless the sheet says otherwise (seconds).
DEFAULT_FADE_IN = 0.005
DEFAULT_FADE_OUT = 0.015
# An edge left unfaded is checked: the peak within _EDGE_S of it, gain
# included, must be under this.
NEAR_SILENT_DBFS = -60.0
_EDGE_S = 0.010

# `ceiling_dbtp: auto` -- Spotify's published numbers (module docstring).
NORMALISED_LUFS = -14.0
CEILING_DBTP = -1.0
LOUD_CEILING_DBTP = -2.0

# The limiter, loudness mode only.
OVERSAMPLE_HZ = 192000  # 4x: the limiter sees the peaks between 48 kHz samples
LIMITER_ATTACK_MS = 4
LIMITER_RELEASE_MS = 200
# alimiter's output lags its input by its lookahead buffer less one sample:
# round(192000 * 0.004) - 1. It is af_alimiter.c's own `in_trim`, the delay
# latency=1 removes; measured the same on ffmpeg 4.2.2, 6.1.1 and 7.0.2.
LIMITER_DELAY_SAMPLES = round(OVERSAMPLE_HZ * LIMITER_ATTACK_MS / 1000) - 1
LIMITER_FLOOR_DBFS = -24.0  # alimiter's `limit` stops at 0.0625
# The most the guard steps down in one round, however far over a file came
# out: an encoder glitch is not an overshoot (see next_setting()).
MAX_STEP_PER_ROUND_DB = 3.0
_DEFAULT_MAX_STEPS = 12  # of step_db: 6 dB below the start, at 0.5 dB steps


# --------------------------------------------------------------------------
# the sheet
# --------------------------------------------------------------------------
class _Strict(BaseModel):
    # A typo in a hand-written sheet -- `fadeout:` for `fade_out:` -- must be
    # an error, not a story that quietly ships with a click at its end.
    model_config = ConfigDict(extra="forbid")


class DeliverDefaults(_Strict):
    audio_bitrate: str = "256k"
    sample_rate: int = Field(default=48000, ge=8000, le=192000)
    ceiling_dbtp: float | Literal["auto"] = Field(
        default="auto",
        description="True-peak ceiling for the delivered AAC, measured on every file. `auto`: "
        "-1 dBTP, or -2 dBTP when the delivery is planned louder than -14 LUFS.",
    )

    @field_validator("audio_bitrate")
    @classmethod
    def _is_a_bitrate(cls, v: str) -> str:
        if not BITRATE_RE.match(v):
            raise ValueError(f"{v!r} is not a bitrate -- use a number with an optional k/M suffix, like '256k'")
        return v

    @field_validator("ceiling_dbtp", mode="before")
    @classmethod
    def _auto_or_at_most_0(cls, v: object) -> object:
        if v == "auto":
            return v
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v > 0:
            raise ValueError(f"{v!r} is not a ceiling -- use auto, or a true peak in dBTP at or under 0")
        return float(v)


class LoudnessGain(_Strict):
    mode: Literal["loudness"]
    target_lufs: float = Field(default=-14.0, ge=-40.0, le=0.0)
    # alimiter's `limit` only goes down to 0.0625 (-24 dBFS).
    limiter_dbfs: float = Field(default=-2.0, ge=LIMITER_FLOOR_DBFS, le=0.0)
    step_db: float = Field(default=0.5, gt=0.0, le=6.0, description="How far the guard lowers the limiter per step.")
    max_steps: int = Field(
        default=_DEFAULT_MAX_STEPS, ge=0, le=40, description="Step-downs of the limiter the guard may take, in all."
    )


class FixedGain(_Strict):
    mode: Literal["fixed"]
    db: float = Field(default=0.0, ge=-60.0, le=24.0)


class AutoGain(_Strict):
    mode: Literal["auto"]
    start_db: float = Field(default=0.0, ge=-60.0, le=24.0)
    step_db: float = Field(default=0.5, gt=0.0, le=6.0)
    max_steps: int = Field(
        default=_DEFAULT_MAX_STEPS, ge=0, le=40, description="Step-downs of the gain the guard may take, in all."
    )


Gain = Annotated[LoudnessGain | FixedGain | AutoGain, Field(discriminator="mode")]


def _no_control_characters(value: str | None, what: str) -> str | None:
    """Paths go into argv, a concat list and --dry-run's shell script; a
    newline in one would end a line in two of those three. (The script also
    relies on it: its placeholders are control characters, so no path can
    contain one.)"""
    if value is not None and any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{what} {value!r} contains a control character")
    return value


class CutConfig(_Strict):
    """One deliverable: `dur` seconds of picture and audio from `t0`.

    With a `card`, the picture is the card (a separately rendered segment
    covering `t0`..`video_from`) followed by the film from the keyframe at
    `video_from`; the audio still runs from `t0`. With `audio: none` the cut
    has no audio stream.
    """

    out: str
    t0: float = Field(ge=0.0, allow_inf_nan=False)
    dur: float = Field(gt=0.0, allow_inf_nan=False)
    fade_in: float = Field(default=DEFAULT_FADE_IN, ge=0.0, allow_inf_nan=False)
    fade_out: float = Field(default=DEFAULT_FADE_OUT, ge=0.0, allow_inf_nan=False)
    audio: Literal["none"] | None = Field(
        default=None, description="`none`: no audio stream (a Spotify Canvas). Default: the sheet's master."
    )
    card: str | None = None
    video_from: float | None = Field(default=None, allow_inf_nan=False)

    @field_validator("out")
    @classmethod
    def _out_stays_inside_the_output_directory(cls, v: str) -> str:
        # SECURITY.md: nothing in a shared file may write outside the
        # directory the user asked for.
        _no_control_characters(v, "out")
        parts = Path(v).parts
        if not v or os.path.isabs(v) or ".." in parts:
            raise ValueError(
                f"out {v!r} must be a file name (or relative path) inside the output directory -- "
                f"no absolute paths, no '..'"
            )
        if not v.lower().endswith(OUTPUT_SUFFIXES):
            raise ValueError(f"out {v!r} must end in {', '.join(OUTPUT_SUFFIXES)}")
        return v

    @field_validator("card")
    @classmethod
    def _card_is_a_plain_path(cls, v: str | None) -> str | None:
        return _no_control_characters(v, "card")

    @model_validator(mode="after")
    def _fades_and_card_are_consistent(self) -> CutConfig:
        if not self.has_audio:
            faded = sorted({"fade_in", "fade_out"} & self.model_fields_set)
            if faded:
                raise ValueError(f"{self.out}: `audio: none` has no audio to fade -- drop {' and '.join(faded)}")
        elif self.fade_in + self.fade_out > self.dur + 1e-9:
            raise ValueError(
                f"{self.out}: fade_in ({self.fade_in:g}) + fade_out ({self.fade_out:g}) is longer "
                f"than the cut ({self.dur:g} s)"
            )
        if (self.card is None) != (self.video_from is None):
            raise ValueError(
                f"{self.out}: `card` and `video_from` go together -- the card covers t0..video_from, "
                f"and the film resumes from the keyframe at video_from"
            )
        if self.video_from is not None and not self.t0 < self.video_from < self.t0 + self.dur:
            raise ValueError(
                f"{self.out}: video_from ({self.video_from:g}) must fall inside the cut "
                f"({self.t0:g}..{self.t0 + self.dur:g})"
            )
        return self

    @property
    def has_audio(self) -> bool:
        return self.audio != "none"

    def frames(self, fps: float) -> int:
        return round(self.dur * fps)

    def card_frames(self, fps: float) -> int:
        return round((self.video_from - self.t0) * fps) if self.video_from is not None else 0


class DeliverySheet(_Strict):
    """Top-level document -- what `kaleidophone deliver sheet.yaml` reads.

    Relative `silent`, `audio` and `card` paths resolve against the sheet's
    own directory, so a project folder can move without editing the sheet.
    `silent_start` is only for a render that doesn't begin at the top of the
    song (see the module docstring); it is not snapped to the frame grid,
    because the song's clock has no frames.
    """

    silent: str
    audio: str | None = Field(
        default=None, description="The master. Required unless every cut is `audio: none`."
    )
    silent_start: float = Field(
        default=0.0,
        allow_inf_nan=False,
        description="Song time, in seconds, of the silent render's first frame -- negative when the "
        "render starts before the song. t0, dur and video_from are on the render's clock; the audio "
        "is read from silent_start + t0, silence-padded before the song starts.",
    )
    fps: float = Field(default=24, gt=0.0, le=240.0)
    defaults: DeliverDefaults = Field(default_factory=DeliverDefaults)
    gain: Gain = Field(default_factory=lambda: FixedGain(mode="fixed", db=0.0))
    cuts: list[CutConfig] = Field(min_length=1)
    check: bool = True

    @field_validator("silent", "audio")
    @classmethod
    def _inputs_are_plain_paths(cls, v: str | None) -> str | None:
        return _no_control_characters(v, "path")

    @model_validator(mode="after")
    def _cuts_are_deliverable(self) -> DeliverySheet:
        seen: set[str] = set()
        for cut in self.cuts:
            key = os.path.normpath(cut.out)
            if key in seen:
                raise ValueError(f"two cuts write {cut.out!r} -- the second would silently overwrite the first")
            seen.add(key)
            for name in ("t0", "video_from"):
                value = getattr(cut, name)
                if value is not None:
                    self._on_frame_grid(cut, name, value)
        voiced = [cut.out for cut in self.cuts if cut.has_audio]
        if self.audio is None and voiced:
            raise ValueError(
                f"`audio` (the master) is required: {', '.join(voiced)} "
                f"{'has' if len(voiced) == 1 else 'have'} audio. Only a sheet whose every cut is "
                f"`audio: none` can leave it out"
            )
        return self

    def _on_frame_grid(self, cut: CutConfig, name: str, value: float) -> None:
        frames = value * self.fps
        if abs(frames - round(frames)) > _GRID_TOLERANCE:
            below = math.floor(frames) / self.fps
            above = math.ceil(frames) / self.fps
            raise ValueError(
                f"{cut.out}: {name} {value:g} isn't on the {self.fps:g} fps frame grid (nearest "
                f"frames: {below:.4f} / {above:.4f}). A stream-copied cut can only start on a "
                f"frame -- and on a keyframe at that."
            )


def load_sheet(path: str) -> DeliverySheet:
    """Parse and validate a delivery sheet, with errors a person can act on."""
    with open(path, encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path} is not valid YAML:\n{exc}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a delivery sheet: expected a mapping with silent, audio and cuts")
    try:
        return DeliverySheet.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{path} is not a valid delivery sheet:\n{_explain(exc)}") from None


def _explain(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err["loc"]).lstrip(".")
        message = err["msg"].removeprefix("Value error, ")
        lines.append(f"  {where or 'sheet'}: {message}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# the master's one gain, and the guard
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MasterLevel:
    """The master, measured once, whole: integrated LUFS and true peak dBTP."""

    lufs: float
    true_peak: float


@dataclass(frozen=True)
class Setting:
    """What every cut of one master is encoded with."""

    gain_db: float
    limiter_dbfs: float | None = None  # loudness mode's limiter; None: no limiter


@dataclass(frozen=True)
class GainPlan:
    """The master's starting setting, and the ceiling every cut is held to."""

    master: MasterLevel
    start: Setting
    ceiling: float
    planned_lufs: float  # the delivery's loudness as planned: the master plus the gain
    warnings: tuple[str, ...] = ()


def _round2(x: float) -> float:
    """Two decimals the way printf rounds them -- which is what --dry-run's
    awk does, so the script arrives at the same numbers."""
    return float(f"{x:.2f}")


def plan_gain(sheet: DeliverySheet, master: MasterLevel) -> GainPlan:
    """One gain for the whole master (see the module docstring), and the
    ceiling: `auto` is -1 dBTP, or -2 dBTP for a delivery planned louder
    than -14 LUFS."""
    g = sheet.gain
    warnings = []
    if isinstance(g, LoudnessGain):
        if not math.isfinite(master.lufs):
            raise ValueError(
                f"the master measured {master.lufs} LUFS -- silent, or unreadable: nothing to gain to "
                f"{g.target_lufs:g} LUFS"
            )
        start = Setting(_round2(g.target_lufs - master.lufs), g.limiter_dbfs)
        planned = g.target_lufs
    else:
        start = Setting(g.db if isinstance(g, FixedGain) else g.start_db)
        planned = master.lufs + start.gain_db
        if master.true_peak > 0:
            warnings.append(
                f"the master's true peak is {master.true_peak:+.2f} dBTP, over 0: a pre-master? "
                f"`mode: {g.mode}` can only turn it down; `mode: loudness` limits it"
            )
    loud = planned > NORMALISED_LUFS
    ceiling = sheet.defaults.ceiling_dbtp
    if ceiling == "auto":
        ceiling = LOUD_CEILING_DBTP if loud else CEILING_DBTP
    elif loud and ceiling > LOUD_CEILING_DBTP:
        warnings.append(
            f"the delivery is planned at {planned:.1f} LUFS, louder than -14: Spotify asks masters that "
            f"loud for a true peak under -2 dBTP, and ceiling_dbtp is {ceiling:g} (auto would use -2)"
        )
    return GainPlan(master, start, float(ceiling), planned, tuple(warnings))


def next_setting(
    gain: LoudnessGain | FixedGain | AutoGain, setting: Setting, overshoot: float, steps_used: int
) -> tuple[Setting | None, int]:
    """The setting to try after a round whose worst cut came out `overshoot`
    dB over the ceiling -- lower by that much, in whole `step_db` steps (one
    at least, and no more than MAX_STEP_PER_ROUND_DB in one round), within
    what is left of `max_steps` -- and the steps now used. None when there
    is nothing left to step: `fixed` never steps, and the limiter stops at
    -24 dBFS.

    `auto` steps the gain; `loudness` steps the limiter and keeps the gain,
    so its loudness stays on target. Stepping by the overshoot takes one
    round where half-dB steps took several, because clean gain moves a
    delivered true peak about dB for dB. The cap is for when it doesn't:
    on one synthetic limited master, ffmpeg 6.1's native AAC encoder put
    isolated pops into the delivered file -- +3.6 dBTP at -2 dB of gain,
    -1.2 at -2.5, +5.3 at -4 -- and one pop must not throw the gain 6 dB
    down in one go."""
    if isinstance(gain, FixedGain):
        return None, steps_used
    left = gain.max_steps - steps_used
    if left <= 0:
        return None, steps_used
    n = min(left, _max_jump(gain.step_db), max(1, math.ceil(overshoot / gain.step_db - 1e-9)))
    if isinstance(gain, LoudnessGain):
        if setting.limiter_dbfs is None or setting.limiter_dbfs <= LIMITER_FLOOR_DBFS:
            return None, steps_used
        limiter = max(_round2(setting.limiter_dbfs - n * gain.step_db), LIMITER_FLOOR_DBFS)
        return Setting(setting.gain_db, limiter), steps_used + n
    return Setting(_round2(setting.gain_db - n * gain.step_db)), steps_used + n


def _max_jump(step_db: float) -> int:
    """MAX_STEP_PER_ROUND_DB in steps of step_db -- one at least."""
    return max(1, math.floor(MAX_STEP_PER_ROUND_DB / step_db + 1e-9))


@dataclass(frozen=True)
class Round:
    """One encode of every cut at one setting: (LUFS, dBTP) per cut, as delivered."""

    setting: Setting
    measured: tuple[tuple[float, float], ...]

    @property
    def worst(self) -> float:
        return max(peak for _, peak in self.measured)


@dataclass(frozen=True)
class GuardResult:
    setting: Setting  # the setting every file on disk was encoded with
    rounds: list[Round]
    ok: bool  # every delivered file under the ceiling


def master_guard(
    encode: Callable[[int, Setting], None],
    measure: Callable[[int], tuple[float, float]],
    count: int,
    start: Setting,
    gain: LoudnessGain | FixedGain | AutoGain,
    ceiling: float,
    log: Callable[[Round, Setting], None] | None = None,
) -> GuardResult:
    """Encode all `count` cuts at one setting, measure each delivered file,
    and step the setting down until every one is under `ceiling`.

    `encode(i, setting)` writes cut i; `measure(i)` returns its (integrated
    LUFS, true peak dBTP). Every round encodes every cut, so the files on
    disk always share one setting -- including when the guard runs out of
    steps, in which case `ok` is False and the caller says so.
    """
    setting, steps, rounds = start, 0, []
    while True:
        measured = []
        for i in range(count):
            encode(i, setting)
            measured.append(measure(i))
        rounds.append(Round(setting, tuple(measured)))
        if rounds[-1].worst <= ceiling:
            return GuardResult(setting, rounds, ok=True)
        following, steps = next_setting(gain, setting, rounds[-1].worst - ceiling, steps)
        if following is None:
            return GuardResult(setting, rounds, ok=False)
        if log is not None:
            log(rounds[-1], following)
        setting = following


# --------------------------------------------------------------------------
# what a run produces
# --------------------------------------------------------------------------
class Attempt(NamedTuple):
    """One encode of a cut: the master's setting, and the delivered true peak."""

    gain_db: float
    limiter_dbfs: float | None
    true_peak: float


@dataclass
class Delivered:
    """One deliverable, and what was measured on the file actually written."""

    out: str
    frames_expected: int
    gain_db: float = 0.0
    source_lufs: float | None = None  # the master's integrated loudness (every cut shares it)
    attempts: list[Attempt] = field(default_factory=list)
    guard_failed: bool = False
    frames: int | None = None
    duration: float | None = None
    lufs: float | None = None
    true_peak: float | None = None
    size_mb: float | None = None
    limiter_dbfs: float | None = None
    ceiling_dbtp: float | None = None
    mode: str = "fixed"  # the gain mode -- "none" for a cut without audio
    has_audio: bool = True

    def over(self, ceiling: float | None = None) -> bool:
        ceiling = self.ceiling_dbtp if ceiling is None else ceiling
        return ceiling is not None and self.true_peak is not None and self.true_peak > ceiling


# --------------------------------------------------------------------------
# measurement parsing
# --------------------------------------------------------------------------
def parse_loudnorm(stderr: str) -> dict:
    """The JSON block loudnorm prints after its measuring pass (`input_i` etc.)."""
    for block in reversed(re.findall(r"\{[^{}]*\}", stderr)):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "input_i" in data:
            return data
    raise RuntimeError(
        "loudnorm printed no measurement -- ffmpeg's log ended with:\n" + stderr[-600:]
    )


def parse_ebur128(stderr: str) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) from ebur128's closing Summary.

    Only what follows the last "Summary:" counts: ebur128 also logs a
    running `I:` for every 100 ms of audio, and the first one of those is the
    loudness of the first tenth of a second.
    """
    at = stderr.rfind("Summary:")
    if at < 0:
        raise RuntimeError("ebur128 printed no summary -- ffmpeg's log ended with:\n" + stderr[-600:])
    summary = stderr[at:]
    number = r"(-?inf|-?\d+(?:\.\d+)?)"
    integrated = re.search(rf"^\s*I:\s*{number}\s*LUFS", summary, re.MULTILINE)
    peak = re.search(rf"^\s*Peak:\s*{number}\s*dBFS", summary, re.MULTILINE)
    if not integrated or not peak:
        raise RuntimeError("ebur128's summary had no I:/Peak: lines -- was peak=true passed?")
    return float(integrated.group(1)), float(peak.group(1))


def _level(text: object) -> float:
    """A loudnorm number ("-8.81", "+6.05", "-inf") as a float; NaN if it isn't one."""
    try:
        return float(str(text))
    except ValueError:
        return math.nan


def measure_master(ffmpeg: str, sheet: DeliverySheet, audio: str) -> MasterLevel:
    """The whole master, once: loudnorm's integrated loudness and true peak."""
    data = parse_loudnorm(run_measure(ffmpeg, _loudnorm_argv(sheet, audio)))
    return MasterLevel(_level(data.get("input_i")), _level(data.get("input_tp")))


# --------------------------------------------------------------------------
# argv
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Paths:
    """Where things are, as the commands will name them: joined as given,
    never made absolute. A relative sheet path therefore gives a script with
    no absolute path in it -- one that runs on another machine from the same
    project folder, and that carries no username or folder layout with it."""

    base: str  # the sheet's directory: inputs resolve against it
    out_dir: str  # where deliverables are written

    def src(self, path: str) -> str:
        return path if os.path.isabs(path) else os.path.normpath(os.path.join(self.base, path))

    def out(self, name: str) -> str:
        return os.path.normpath(os.path.join(self.out_dir, name))

    @property
    def work(self) -> str:
        return os.path.normpath(os.path.join(self.out_dir, WORK_DIR))


def _paths(sheet_path: str, out_dir: str | None) -> _Paths:
    base = os.path.dirname(sheet_path)
    return _Paths(base=base, out_dir=out_dir if out_dir is not None else (base or "."))


def _arg(path: str) -> str:
    """A path as an ffmpeg argument: relative ones get a leading ./ so a name
    starting with '-' isn't read as a flag, nor 'x:y.mp4' as a protocol."""
    return path if os.path.isabs(path) or path.startswith(("./", "../")) else "./" + path


def _num(x: float) -> str:
    """Plain decimal, never scientific: ffmpeg's option parsers don't read 1e-05."""
    text = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _frame_time(t: float, fps: float) -> str:
    """A cut point as ffmpeg should be given it: snapped to its frame, then
    floored to the microsecond -- ffmpeg's own clock -- and never rounded up.

    An input `-ss` with stream copy has to name the keyframe's time, not
    approximately, and three decimals are only exact when the frame time
    happens to be a round millisecond. Measured with ffmpeg 6.1 on a
    synthetic 24 fps render: frame 242 is 10.08333... s, and `-ss 10.083`,
    0.33 ms early, wrote a cut with no decodable frames at all; frame 289,
    asked for as 12.042 (0.33 ms late), came out with its keyframe hidden --
    the cut started a frame late and ran a frame short.

    `-force_key_frames` needs the floor rather than the nearest: it keys the
    first frame at or after each time, and 10.041667 -- frame 241 rounded up
    by a third of a microsecond -- keyed frame 242 instead, which then
    swallowed the next cut point's keyframe too. Floored, both were exact.
    """
    return _clock(round(t * fps) / fps)


def _clock(t: float) -> str:
    """Seconds to the microsecond, floored -- see _frame_time() for why."""
    return f"{math.floor(t * 1e6 + 1e-3) / 1e6:.6f}"


def _song_t0(sheet: DeliverySheet, cut: CutConfig) -> float:
    """Where a cut's audio starts in the song: the render's own start plus
    the cut's frame-exact t0 on the render's clock. Negative when the cut
    opens before the song does."""
    return sheet.silent_start + round(cut.t0 * sheet.fps) / sheet.fps


def _head_pad(sheet: DeliverySheet, cut: CutConfig) -> float:
    """Seconds of silence ahead of the song at the head of a cut that opens
    before song time 0 (a negative silent_start); 0 for every other cut."""
    return max(0.0, -_song_t0(sheet, cut))


def _audio_input(sheet: DeliverySheet, cut: CutConfig, audio: str) -> list[str]:
    """The master's window as an input: seeked (sample-exact for PCM) to the
    cut's song time, or -- when the cut opens before the song -- read from
    the top for what is left once the head is padded."""
    song_t0 = _song_t0(sheet, cut)
    seek = ["-ss", _clock(song_t0)] if song_t0 > 0 else []
    return [*seek, "-t", f"{cut.dur - _head_pad(sheet, cut):.6f}", "-i", _arg(audio)]


def _delay(seconds: float, rate: int) -> str:
    """Silence at the head, in samples at a rate the chain has just been
    resampled to -- exact, and the same whatever rate the master is at."""
    return f"adelay=delays={round(seconds * rate)}S:all=1"


def limiter_filter(limiter_dbfs: float, latency: bool) -> str:
    """The loudness mode's limiter at 192 kHz, with its lookahead delay taken
    back: by alimiter itself where it can (`latency`, ffmpeg 5.1+), else by
    the same trim done around it -- see the module docstring."""
    limit = 10 ** (limiter_dbfs / 20.0)
    core = (
        f"alimiter=limit={limit:.4f}:attack={LIMITER_ATTACK_MS}:release={LIMITER_RELEASE_MS}"
        f":level=disabled"
    )
    if latency:
        return f"{core}:latency=1"
    n = LIMITER_DELAY_SAMPLES
    return f"apad=pad_len={n},{core},atrim=start_sample={n},asetpts=PTS-STARTPTS"


def _audio_filter(sheet: DeliverySheet, cut: CutConfig, gain: str, limiter: str | None) -> str:
    """The cut's audio chain. `gain` is dB as text and `limiter` the
    limiter's own filter text, so --dry-run can put shell variables there."""
    pad = _head_pad(sheet, cut)
    rate = sheet.defaults.sample_rate
    if isinstance(sheet.gain, LoudnessGain):
        if limiter is None:
            raise ValueError("loudness mode needs its limiter")
        chain = [f"aresample={OVERSAMPLE_HZ}"]
        if pad:
            chain.append(_delay(pad, OVERSAMPLE_HZ))
        chain += [f"volume={gain}dB", limiter, f"aresample={rate}"]
    else:
        chain = [f"aresample={rate}", _delay(pad, rate)] if pad else []
        chain.append(f"volume={gain}dB")
    if cut.fade_in > 0:
        chain.append(f"afade=t=in:st=0:d={_num(cut.fade_in)}")
    if cut.fade_out > 0:
        chain.append(f"afade=t=out:st={_num(cut.dur - cut.fade_out)}:d={_num(cut.fade_out)}")
    return ",".join(chain)


def _encode_argv(
    sheet: DeliverySheet,
    cut: CutConfig,
    video_in: list[str],
    audio: str,
    out: str,
    gain: str,
    limiter: str | None = None,
) -> list[str]:
    """Picture stream-copied and bounded by frame count; audio windowed on
    input at song time, gained (limited), faded, AAC'd."""
    return [
        "-y",
        *video_in,
        *_audio_input(sheet, cut, audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-frames:v", str(cut.frames(sheet.fps)),
        "-af", _audio_filter(sheet, cut, gain, limiter),
        "-c:a", "aac", "-b:a", sheet.defaults.audio_bitrate, "-ar", str(sheet.defaults.sample_rate),
        *CLEAN_OUTPUT, *FASTSTART,
        _arg(out),
    ]


def _silent_argv(sheet: DeliverySheet, cut: CutConfig, video_in: list[str], out: str) -> list[str]:
    """A cut with no audio stream: the picture alone, stream-copied."""
    return [
        "-y",
        *video_in,
        "-map", "0:v:0", "-c:v", "copy", "-frames:v", str(cut.frames(sheet.fps)),
        "-an", *CLEAN_OUTPUT, *FASTSTART,
        _arg(out),
    ]


def _loudnorm_argv(sheet: DeliverySheet, audio: str) -> list[str]:
    target = sheet.gain.target_lufs if isinstance(sheet.gain, LoudnessGain) else NORMALISED_LUFS
    return [
        "-i", _arg(audio), "-vn",
        "-af", f"loudnorm=I={_num(target)}:TP={_num(_MEASURE_TP)}:print_format=json",
        "-f", "null", "-",
    ]


def _ebur128_argv(path: str) -> list[str]:
    # -vn: the measurement is of the audio; decoding the picture too only costs time.
    return ["-i", _arg(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]


@dataclass(frozen=True)
class _CardSteps:
    tail: list[str]  # film from video_from -> work/cutNN.tail.mp4
    listing: str  # contents of the concat list
    list_path: str
    concat: list[str]  # card + tail -> work/cutNN.silent.mp4
    joined: str
    intermediates: tuple[str, ...]


def _card_steps(sheet: DeliverySheet, cut: CutConfig, index: int, paths: _Paths) -> _CardSteps:
    """The card cut, by hand from the last releases: film tail from the
    keyframe at video_from, then card + tail stream-concatenated, then muxed
    like any other cut. Only the picture is joined -- the audio runs on
    unbroken from t0 underneath -- so there is no audio seam to crossfade."""
    work = paths.work
    stem = os.path.join(work, f"cut{index:02d}")
    tail, list_path, joined = f"{stem}.tail.mp4", f"{stem}.concat.txt", f"{stem}.silent.mp4"
    tail_frames = cut.frames(sheet.fps) - cut.card_frames(sheet.fps)
    tail_argv = [
        "-y",
        "-ss", _frame_time(cut.video_from, sheet.fps), "-i", _arg(paths.src(sheet.silent)),
        "-map", "0:v:0", "-c:v", "copy", "-frames:v", str(tail_frames),
        "-an", *CLEAN_OUTPUT,
        _arg(tail),
    ]
    # The demuxer resolves relative entries against the list file's own
    # directory, not the working directory -- so they are written relative
    # to it, which also keeps an absolute path out of a --dry-run script.
    card = os.path.relpath(paths.src(cut.card), work)
    listing = f"file {concat_quote(card)}\nfile {concat_quote(os.path.basename(tail))}\n"
    concat_argv = ["-y", "-f", "concat", "-safe", "0", "-i", _arg(list_path), "-c", "copy", _arg(joined)]
    return _CardSteps(tail_argv, listing, list_path, concat_argv, joined, (tail, list_path, joined))


def _video_input(sheet: DeliverySheet, cut: CutConfig, paths: _Paths, card: _CardSteps | None) -> list[str]:
    if card is not None:
        return ["-i", _arg(card.joined)]
    seek = ["-ss", _frame_time(cut.t0, sheet.fps)] if cut.t0 > 0 else []
    return [*seek, "-i", _arg(paths.src(sheet.silent))]


# --------------------------------------------------------------------------
# the real run
# --------------------------------------------------------------------------
def deliver(
    sheet_path: str, *, out_dir: str | None = None, log: Callable[[str], None] | None = None
) -> list[Delivered]:
    """Cut, gain and mux every deliverable in the sheet, holding every one
    under the true-peak ceiling; measure them if `check` is on. Returns one
    Delivered per cut, in sheet order."""
    sheet = load_sheet(sheet_path)
    paths = _paths(sheet_path, out_dir)
    say = log or (lambda _msg: None)
    ffmpeg = require_ffmpeg()
    for warning in _preflight(sheet, paths):
        say(f"warning: {warning}")

    voiced = [i for i, cut in enumerate(sheet.cuts) if cut.has_audio]
    plan = None
    if voiced:
        audio = paths.src(sheet.audio)
        plan = plan_gain(sheet, measure_master(ffmpeg, sheet, audio))
        say(_describe_plan(sheet, plan))
        for warning in (*plan.warnings, *_edge_warnings(sheet, paths, plan.start.gain_db)):
            say(f"warning: {warning}")

    results = [
        Delivered(
            out=paths.out(cut.out),
            frames_expected=cut.frames(sheet.fps),
            mode=sheet.gain.mode if cut.has_audio else "none",
            has_audio=cut.has_audio,
        )
        for cut in sheet.cuts
    ]
    cards: list[_CardSteps] = []
    try:
        video_in = []
        for i, cut in enumerate(sheet.cuts, 1):
            os.makedirs(os.path.dirname(paths.out(cut.out)) or ".", exist_ok=True)
            card = _card_steps(sheet, cut, i, paths) if cut.card else None
            if card is not None:
                os.makedirs(paths.work, exist_ok=True)
                cards.append(card)
                run(ffmpeg, card.tail)
                Path(card.list_path).write_text(card.listing, encoding="utf-8")
                run(ffmpeg, card.concat)
            video_in.append(_video_input(sheet, cut, paths, card))

        for i, cut in enumerate(sheet.cuts):
            if not cut.has_audio:
                say(f"[{i + 1}/{len(sheet.cuts)}] {cut.out} (no audio)")
                run(ffmpeg, _silent_argv(sheet, cut, video_in[i], results[i].out))

        if plan is not None:
            _deliver_voiced(ffmpeg, sheet, paths, plan, voiced, video_in, results, say)
    finally:
        for card in cards:
            for path in card.intermediates:
                if os.path.exists(path):
                    os.remove(path)
        _remove_work_dir(paths)
    if sheet.check:
        for result in results:
            _measure_delivered(result)
    return results


def _deliver_voiced(
    ffmpeg: str,
    sheet: DeliverySheet,
    paths: _Paths,
    plan: GainPlan,
    voiced: list[int],
    video_in: list[list[str]],
    results: list[Delivered],
    say: Callable[[str], None],
) -> None:
    """Every cut with audio, at the master's one setting, through the guard."""
    audio = paths.src(sheet.audio)
    latency = isinstance(sheet.gain, LoudnessGain) and "latency" in filter_options(ffmpeg, "alimiter")

    def encode(k: int, setting: Setting) -> None:
        i = voiced[k]
        cut = sheet.cuts[i]
        say(f"[{i + 1}/{len(sheet.cuts)}] {cut.out}")
        limiter = limiter_filter(setting.limiter_dbfs, latency) if setting.limiter_dbfs is not None else None
        gain = f"{setting.gain_db:.2f}"
        run(ffmpeg, _encode_argv(sheet, cut, video_in[i], audio, results[i].out, gain, limiter))

    def measure(k: int) -> tuple[float, float]:
        return parse_ebur128(run_measure(ffmpeg, _ebur128_argv(results[voiced[k]].out)))

    def again(finished: Round, following: Setting) -> None:
        worst = max(range(len(voiced)), key=lambda k: finished.measured[k][1])
        say(
            f"{sheet.cuts[voiced[worst]].out} peaked at {finished.worst:+.1f} dBTP, over the "
            f"{plan.ceiling:g} dBTP ceiling: every cut again at {_describe_setting(following)}"
        )

    guard = master_guard(encode, measure, len(voiced), plan.start, sheet.gain, plan.ceiling, log=again)
    for k, i in enumerate(voiced):
        r = results[i]
        r.gain_db, r.limiter_dbfs = guard.setting.gain_db, guard.setting.limiter_dbfs
        r.source_lufs, r.ceiling_dbtp = plan.master.lufs, plan.ceiling
        r.attempts = [Attempt(rd.setting.gain_db, rd.setting.limiter_dbfs, rd.measured[k][1]) for rd in guard.rounds]
        r.lufs, r.true_peak = guard.rounds[-1].measured[k]
        r.guard_failed = not guard.ok and r.over()


def _describe_setting(setting: Setting) -> str:
    text = f"gain {setting.gain_db:+.2f} dB"
    if setting.limiter_dbfs is not None:
        text += f", limiter {setting.limiter_dbfs:.2f} dBFS"
    return text


def _describe_plan(sheet: DeliverySheet, plan: GainPlan) -> str:
    audio = os.path.basename(sheet.audio or "")
    ceiling = f"true-peak ceiling {plan.ceiling:g} dBTP"
    if sheet.defaults.ceiling_dbtp == "auto":
        ceiling += " (auto: louder than -14 LUFS)" if plan.ceiling == LOUD_CEILING_DBTP else " (auto)"
    return (
        f"master {audio}: {plan.master.lufs:.2f} LUFS, {plan.master.true_peak:+.2f} dBTP -- every cut "
        f"at {_describe_setting(plan.start)} ({sheet.gain.mode}), {ceiling}"
    )


def _peak_dbfs(path: str, start: float, duration: float) -> float:
    """The sample peak of a window of `path`, in dBFS (-inf for silence)."""
    raw = decode_f32le(path, sample_rate=48000, channels=2, start=start, duration=duration)
    samples = np.frombuffer(raw, dtype="<f4")
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return 20 * math.log10(peak) if peak > 0 else -math.inf


def _edge_warnings(sheet: DeliverySheet, paths: _Paths, gain_db: float) -> list[str]:
    """A fade set to 0 is a promise that the song is silent at that edge;
    check it. Unfaded sound at an edge is a click -- and a click every loop
    on a platform that loops the cut."""
    audio = paths.src(sheet.audio)
    warnings = []
    for cut in sheet.cuts:
        if not cut.has_audio:
            continue
        song_t0 = _song_t0(sheet, cut)
        song_end = song_t0 + cut.dur
        edges = []
        if cut.fade_in == 0 and song_t0 >= 0:  # a padded head starts in silence anyway
            edges.append(("start", "fade_in", song_t0, DEFAULT_FADE_IN))
        if cut.fade_out == 0 and song_end > 0:
            edges.append(("end", "fade_out", max(song_end - _EDGE_S, 0.0), DEFAULT_FADE_OUT))
        for where, name, at, default in edges:
            try:
                level = _peak_dbfs(audio, at, _EDGE_S) + gain_db
            except (OSError, RuntimeError) as exc:
                warnings.append(f"{cut.out}: couldn't read the audio at its {where} to check it is silent ({exc})")
                continue
            if level > NEAR_SILENT_DBFS:
                warnings.append(
                    f"{cut.out}: {name} is 0 and the audio at its {where} peaks at {level:.1f} dBFS, not "
                    f"silence -- that edge clicks (every loop, where a platform loops it). Leave {name} "
                    f"out for the default {default * 1000:g} ms, or cut where the song is silent."
                )
    return warnings


def _measure_delivered(result: Delivered) -> None:
    """Frames, duration and size of what was written -- measured on the
    file, because the file is what ships. Its loudness and true peak were
    measured by the guard, on the same file."""
    packets = probe_stream(result.out, "v:0", "nb_read_packets", count_packets=True)
    result.frames = int(packets) if packets and packets.isdigit() else None
    result.duration = probe_duration(result.out)
    result.size_mb = round(os.path.getsize(result.out) / 1048576, 1)


def _preflight(sheet: DeliverySheet, paths: _Paths) -> list[str]:
    """Everything that can be checked before a minute of encoding is spent.

    All problems at once, not the first one: a sheet usually has several
    cuts, and fixing them one failed run at a time is how an afternoon goes.
    Returns the warnings -- things that deliver, but not perfectly.
    """
    voiced = any(cut.has_audio for cut in sheet.cuts)
    silent = paths.src(sheet.silent)
    audio = paths.src(sheet.audio) if voiced else None
    inputs = [silent, *([audio] if audio else []), *(paths.src(c.card) for c in sheet.cuts if c.card)]
    for path in inputs:
        if not os.path.exists(path):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    problems, warnings = [], []
    frame = 1.0 / sheet.fps
    silent_dur = probe_duration(silent)
    audio_dur = probe_duration(audio) if audio else None
    keyframes = probe_keyframes(silent)
    for cut in sheet.cuts:
        end = cut.t0 + cut.dur
        if silent_dur is not None and end > silent_dur + frame:
            problems.append(f"{cut.out}: ends at {end:.3f} s, past the end of the silent render ({silent_dur:.3f} s)")
        if cut.has_audio:
            # The audio is on the song's clock, the picture on the render's.
            song_t0 = _song_t0(sheet, cut)
            song_end = sheet.silent_start + end
            if song_t0 + cut.dur <= 0:
                problems.append(
                    f"{cut.out}: its audio, song time {song_t0:.3f} to {song_t0 + cut.dur:.3f} s, is all before "
                    f"the song starts (silent_start {sheet.silent_start:g}) -- `audio: none` delivers it silent"
                )
            elif audio_dur is not None and song_end > audio_dur + 0.05:
                at = f"{end:.3f} s"
                if sheet.silent_start:
                    at = f"song time {song_end:.3f} s (silent_start {sheet.silent_start:g} + {end:.3f})"
                problems.append(f"{cut.out}: its audio ends at {at}, past the end of the audio ({audio_dur:.3f} s)")
        start = cut.video_from if cut.card else cut.t0
        if keyframes is not None and start > 0 and not any(abs(k - start) < frame / 2 for k in keyframes):
            before = max((k for k in keyframes if k < start), default=0.0)
            after = min((k for k in keyframes if k > start), default=None)
            nearest = f"{before:.3f} s" + (f" / {after:.3f} s" if after is not None else "")
            problems.append(
                f"{cut.out}: the film cut starts at {start:.3f} s, but the silent render has no keyframe "
                f"there (nearest: {nearest})"
            )
        end_at = _cut_end(cut, sheet.fps)
        before_the_end = silent_dur is None or end_at < silent_dur - frame / 2
        if keyframes is not None and before_the_end and not any(abs(k - end_at) < frame / 2 for k in keyframes):
            warnings.append(
                f"{cut.out}: ends at {end_at:.3f} s, between keyframes -- its last frame can come out "
                f"of B-frame order. A keyframe forced there too makes the cut exact."
            )
        if cut.card:
            want = cut.card_frames(sheet.fps)
            got = probe_stream(paths.src(cut.card), "v:0", "nb_read_packets", count_packets=True)
            if got and got.isdigit() and int(got) != want:
                problems.append(
                    f"{cut.out}: the card has {got} frames, but {cut.t0:g}..{cut.video_from:g} s at "
                    f"{sheet.fps:g} fps needs {want} -- the film would land {int(got) - want:+d} frames "
                    f"off its audio"
                )
    if problems:
        hint = ""
        if any("keyframe" in p for p in problems):
            hint = (
                "\nRe-render the silent video with a keyframe at every cut point, e.g.\n"
                f"  -force_key_frames {_keyframe_list(sheet)}"
            )
        raise ValueError("the sheet can't be delivered as it stands:\n  " + "\n  ".join(problems) + hint)
    if warnings:
        warnings.append(f"keyframes for every cut point: -force_key_frames {_keyframe_list(sheet)}")
    return warnings


def _cut_end(cut: CutConfig, fps: float) -> float:
    """The time of the first frame after the cut -- where its GOP should end."""
    return (round(cut.t0 * fps) + cut.frames(fps)) / fps


def _keyframe_list(sheet: DeliverySheet) -> str:
    """Every point a cut starts, resumes or ends at -- the argument the
    silent render needs (see the module docstring for why ends too)."""
    points = {0.0}
    for cut in sheet.cuts:
        points.add(round(cut.t0 * sheet.fps) / sheet.fps)
        points.add(_cut_end(cut, sheet.fps))
        if cut.video_from is not None:
            points.add(round(cut.video_from * sheet.fps) / sheet.fps)
    return ",".join(_frame_time(p, sheet.fps).rstrip("0").rstrip(".") for p in sorted(points))


def _remove_work_dir(paths: _Paths) -> None:
    """Remove the intermediates directory if the run left it empty -- and its
    .kaleidophone-cache parent, if nothing else lives there."""
    for directory in (paths.work, os.path.dirname(paths.work)):
        try:
            os.rmdir(directory)
        except OSError:
            break


_FIX = {
    "auto": "`gain: {mode: auto}` has run out of steps -- raise gain.max_steps or lower gain.start_db",
    "loudness": "the limiter has run out of steps -- raise gain.max_steps or lower gain.limiter_dbfs",
    "fixed": "lower gain.db, or use `gain: {mode: auto}`, which steps the gain down until every file is under it",
}


def format_table(results: list[Delivered], ceiling: float | None = None) -> str:
    """The check table: what was written, measured on the files themselves.
    Each row is held to its own ceiling (the master's), or to `ceiling`."""
    width = max([12, *(len(os.path.basename(r.out)) for r in results)])
    lines = [
        f"{'deliverable':<{width}}  {'frames':>11}  {'duration':>9}  {'LUFS':>6}  {'dBTP':>6}  {'MB':>6}  gain",
    ]
    warnings = []
    for r in results:
        name = os.path.basename(r.out)
        frames = f"{r.frames if r.frames is not None else '?'}/{r.frames_expected}"
        duration = f"{r.duration:.3f}s" if r.duration is not None else "?"
        silent = "-" if not r.has_audio else "?"
        lufs = f"{r.lufs:.1f}" if r.lufs is not None else silent
        peak = f"{r.true_peak:.1f}" if r.true_peak is not None else silent
        size = f"{r.size_mb:.1f}" if r.size_mb is not None else "?"
        gain = f"{r.gain_db:+.2f} dB" if r.has_audio else "no audio"
        if r.limiter_dbfs is not None:
            gain += f", limiter {r.limiter_dbfs:.2f} dBFS"
        flag = ""
        if r.frames is not None and r.frames != r.frames_expected:
            flag += " !frames"
            warnings.append(f"{name}: {r.frames} frames written, {r.frames_expected} expected")
        limit = r.ceiling_dbtp if r.ceiling_dbtp is not None else ceiling
        if r.over(limit):
            flag += " !peak"
            warnings.append(
                f"{name}: true peak {r.true_peak:.1f} dBTP is over the {limit:g} dBTP ceiling -- "
                + _FIX.get(r.mode, _FIX["fixed"])
            )
        lines.append(
            f"{name:<{width}}  {frames:>11}  {duration:>9}  {lufs:>6}  {peak:>6}  {size:>6}  {gain}{flag}"
        )
    return "\n".join(lines + [f"warning: {w}" for w in warnings])


# --------------------------------------------------------------------------
# --dry-run: the same delivery as a shell script
# --------------------------------------------------------------------------
# Placeholders for the values the script measures itself. They are control
# characters, which no path in a sheet can contain (_no_control_characters),
# so _sh() can tell them from anything a path might hold -- a literal "${G}"
# included.
_GAIN = "\x01gain\x01"
_LIMITER = "\x01limiter\x01"
_SHELL_VARIABLES = {_GAIN: '"$G"', _LIMITER: '"$LIM"'}

_SCRIPT_HELPERS = {
    "master": """\
# The master's integrated loudness (LUFS), measured once, whole: loudnorm's measuring pass.
lufs() {
  ffmpeg -hide_banner -nostats -nostdin -i "$1" -vn -af "$2" -f null - 2>&1 </dev/null \\
    | sed -n 's/.*"input_i" : "\\([^"]*\\)".*/\\1/p' | tail -n 1
}""",
    "gain_to": """\
# The gain from the master's loudness to a target -- refusing a measurement that isn't a number.
gain_to() {
  case "$2" in ''|*inf*|*nan*) echo "kaleidophone: could not measure the loudness of $3" >&2; exit 1;; esac
  awk -v t="$1" -v i="$2" 'BEGIN { printf "%.2f", t - i }'
}""",
    "truepeak": """\
# True peak (dBTP) of a delivered file, from ebur128's closing summary.
truepeak() {
  ffmpeg -hide_banner -nostats -nostdin -i "$1" -vn -af ebur128=peak=true -f null - 2>&1 </dev/null \\
    | awk '/Summary:/ { s = 1 } s && $1 == "Peak:" { print $2 }' | tail -n 1
}
# The louder of the worst true peak so far and a new one; a measurement that isn't a number stops the delivery.
worst() {
  case "$2" in
    -inf) set -- "$1" -999 "$3";;
    ''|*[!0-9.+-]*) echo "kaleidophone: could not measure the true peak of $3" >&2; exit 1;;
  esac
  awk -v a="$1" -v b="$2" 'BEGIN { print (b + 0 > a + 0) ? b : a }'
}
# How many steps of $3 dB take a true peak of $1 under a ceiling of $2 (one at least).
steps_for() {
  awk -v w="$1" -v c="$2" -v s="$3" 'BEGIN { n = (w - c) / s; k = int(n); if (k < n - 1e-9) k++; if (k < 1) k = 1; print k }'
}""",
    "limiter": """\
# The limiter looks 4 ms ahead, which delays its output 767 samples at 192 kHz. ffmpeg 5.1+ takes
# that back itself (latency=1); an older one gets the same trim around the limiter.
if ffmpeg -hide_banner -nostdin -h filter=alimiter 2>/dev/null </dev/null | grep -q '^ *latency  *<'; then
  LATENCY=1
else
  LATENCY=0
fi
limiter() {
  x=$(awk -v d="$1" 'BEGIN { printf "%.4f", 10 ^ (d / 20) }')
  if [ "$LATENCY" = 1 ]; then
    printf 'alimiter=limit=%s:attack=4:release=200:level=disabled:latency=1' "$x"
  else
    printf 'apad=pad_len=767,alimiter=limit=%s:attack=4:release=200:level=disabled,atrim=start_sample=767,asetpts=PTS-STARTPTS' "$x"
  fi
}""",
    "check": """\
# What was delivered: frames (counted, not the header's claim), duration, loudness, true peak, size.
check() {
  n=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$1" </dev/null)
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$1" </dev/null)
  m=
  if [ "$3" != silent ]; then
    m=$(ffmpeg -hide_banner -nostats -nostdin -i "$1" -vn -af ebur128=peak=true -f null - 2>&1 </dev/null \\
      | awk '/Summary:/ { s = 1 } s && ($1 == "I:" || $1 == "Peak:") { printf "%s %s  ", $1, $2 }')
  fi
  s=$(wc -c < "$1" | awk '{ printf "%.1f MB", $1 / 1048576 }')
  echo "$1  frames=$n/$2  dur=$d  $m$s"
}""",
}


def _sh(arg: str) -> str:
    """Quote one argv element for sh. Every piece of it is single-quoted, so
    nothing a path holds -- $(...), backticks, quotes, $HOME, a literal
    ${G} -- is expanded; the only expansions are the script's own "$G" and
    "$LIM", which go exactly where the placeholders are."""
    pieces = re.split(f"({re.escape(_GAIN)}|{re.escape(_LIMITER)})", arg)
    quoted = "".join(_SHELL_VARIABLES.get(p) or shlex.quote(p) for p in pieces if p)
    return quoted or "''"


def _comment(text: str) -> str:
    """Text for a `#` comment line: a control character (a newline in the
    sheet's own file name, say) can't end the comment."""
    return re.sub(r"[\x00-\x1f\x7f]", "?", text)


def _command(argv: list[str]) -> str:
    return " ".join(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *(_sh(a) for a in argv)])


def delivery_script(sheet_path: str, *, out_dir: str | None = None) -> str:
    """The whole delivery as a POSIX sh script, for another machine.

    Nothing is run and nothing needs to exist: this is how a sheet written
    where the picture was rendered becomes a script run where the WAV lives.
    It does what deliver() does, in the same order and with the same ffmpeg
    command lines: the master measured once, one gain for every cut, and the
    true-peak guard's rounds, measured by the script itself.
    """
    sheet = load_sheet(sheet_path)
    paths = _paths(sheet_path, out_dir)
    ceiling = sheet.defaults.ceiling_dbtp
    loudness = isinstance(sheet.gain, LoudnessGain)
    voiced = [(i, cut) for i, cut in enumerate(sheet.cuts, 1) if cut.has_audio]

    needed = []
    if voiced:
        needed += ["master", *(["gain_to"] if loudness else []), "truepeak", *(["limiter"] if loudness else [])]
    if sheet.check:
        needed.append("check")

    out_dirs = sorted({os.path.dirname(paths.out(c.out)) for c in sheet.cuts} - {""})
    has_card = any(c.card for c in sheet.cuts)
    lines = [
        "#!/bin/sh",
        _comment(f"# kaleidophone deliver -- {os.path.basename(sheet_path)}, printed by --dry-run."),
        "# Every path is relative to the directory kaleidophone ran in: run this from there.",
        "# The silent render needs a keyframe wherever a cut starts (or it can't be stream-copied)",
        "# and wherever one ends (or its last frame can come out of B-frame order):",
        f"#   -force_key_frames {_keyframe_list(sheet)}",
    ]
    if sheet.silent_start > 0:
        lines.append(
            f"# The render starts at song time {_num(sheet.silent_start)} s (silent_start): cut times "
            f"are on its clock, the audio is read {_num(sheet.silent_start)} s later."
        )
    elif sheet.silent_start < 0:
        lines.append(
            f"# The render starts {_num(-sheet.silent_start)} s before the song (silent_start "
            f"{_num(sheet.silent_start)}): cut times are on its clock, and the audio's head is "
            f"silence until the song starts."
        )
    lines.append("set -e")
    made = out_dirs + ([paths.work] if has_card else [])
    if made:
        lines.append("mkdir -p -- " + " ".join(shlex.quote(d) for d in made))
    lines.append("")
    for name in needed:
        lines += [_SCRIPT_HELPERS[name], ""]

    if voiced:
        lines += _script_master(sheet, paths)

    cards = {}
    for i, cut in enumerate(sheet.cuts, 1):
        if cut.card:
            card = cards[i] = _card_steps(sheet, cut, i, paths)
            lines += [
                _comment(f"# the card cut {cut.out}: the film from its keyframe at {cut.video_from:g} s, behind the card"),
                _command(card.tail),
                f"cat > {shlex.quote(card.list_path)} <<'EOF'",
                card.listing.rstrip("\n"),
                "EOF",
                _command(card.concat),
                "",
            ]
    for i, cut in enumerate(sheet.cuts, 1):
        if not cut.has_audio:
            video_in = _video_input(sheet, cut, paths, cards.get(i))
            lines += [
                _cut_comment(sheet, cut, i, silent=True),
                _command(_silent_argv(sheet, cut, video_in, paths.out(cut.out))),
                "",
            ]
    if voiced:
        lines += _script_guard(sheet, paths, voiced, cards, ceiling)

    if cards:
        intermediates = [p for card in cards.values() for p in card.intermediates]
        lines += [
            "rm -f -- " + " ".join(shlex.quote(p) for p in intermediates),
            f"rmdir -- {shlex.quote(paths.work)} 2>/dev/null || true",
            f"rmdir -- {shlex.quote(os.path.dirname(paths.work))} 2>/dev/null || true",
            "",
        ]
    if sheet.check:
        lines.append("# check what was delivered")
        lines += [
            f"check {_sh(_arg(paths.out(c.out)))} {c.frames(sheet.fps)}" + ("" if c.has_audio else " silent")
            for c in sheet.cuts
        ]
    if voiced:
        lines += ["", '[ -z "$FAILED" ] || exit 1']
    return "\n".join(lines).rstrip("\n") + "\n"


def _cut_comment(sheet: DeliverySheet, cut: CutConfig, index: int, *, silent: bool = False) -> str:
    song_t0 = _song_t0(sheet, cut)
    song = f" (song {song_t0:.3f}-{song_t0 + cut.dur:.3f} s)" if sheet.silent_start and not silent else ""
    return _comment(
        f"# {index}/{len(sheet.cuts)}  {cut.out}: {cut.t0:.3f}-{cut.t0 + cut.dur:.3f} s{song}, "
        f"{cut.frames(sheet.fps)} frames"
        + (f", card until {cut.video_from:g} s" if cut.card else "")
        + (", no audio" if silent else "")
    )


def _script_master(sheet: DeliverySheet, paths: _Paths) -> list[str]:
    """The master, measured once, and the plan: G, L (loudness) and C."""
    audio = _arg(paths.src(sheet.audio))
    measure = _loudnorm_argv(sheet, paths.src(sheet.audio))
    g = sheet.gain
    lines = [
        "# The master, measured once, whole: every cut gets the same gain.",
        f"I=$(lufs {_sh(audio)} {_sh(measure[measure.index('-af') + 1])})",
    ]
    if isinstance(g, LoudnessGain):
        lines += [
            f"G=$(gain_to {_num(g.target_lufs)} \"$I\" {_sh(audio)})",
            f"L={g.limiter_dbfs:.2f}",
        ]
        planned = f"{_num(g.target_lufs)}"
    else:
        start = g.db if isinstance(g, FixedGain) else g.start_db
        lines += [
            f"G={start:.2f}",
            # A silent master measures -inf: quiet, as far as the ceiling goes.
            'case "$I" in \'\'|*inf*|*nan*) J=-99;; *) J=$I;; esac',
        ]
        planned = '$(awk -v i="$J" -v g="$G" \'BEGIN { print i + g }\')'
    ceiling = sheet.defaults.ceiling_dbtp
    if ceiling == "auto":
        lines.append(
            f"P={planned}; C=$(awk -v p=\"$P\" 'BEGIN {{ print (p > {_num(NORMALISED_LUFS)}) ? "
            f"{_num(LOUD_CEILING_DBTP)} : {_num(CEILING_DBTP)} }}')"
        )
    else:
        lines += [
            f"P={planned}; C={_num(ceiling)}",
            f"if awk -v p=\"$P\" 'BEGIN {{ exit !(p > {_num(NORMALISED_LUFS)} && {_num(ceiling)} > "
            f"{_num(LOUD_CEILING_DBTP)}) }}'; then echo \"warning: the delivery is planned at $P LUFS, "
            f"louder than -14: Spotify asks for a true peak under -2 dBTP there, and the ceiling is "
            f"{_num(ceiling)}\" >&2; fi",
        ]
    lines += [
        "printf 'master: %s LUFS -- every cut at gain %s dB, true-peak ceiling %s dBTP\\n' \"$I\" \"$G\" \"$C\"",
        "",
    ]
    return lines


def _script_guard(
    sheet: DeliverySheet,
    paths: _Paths,
    voiced: list[tuple[int, CutConfig]],
    cards: dict[int, _CardSteps],
    ceiling: float | str,
) -> list[str]:
    """master_guard() in sh: every cut at the master's setting, a round at a
    time, until the worst delivered true peak is under the ceiling."""
    g = sheet.gain
    loudness = isinstance(g, LoudnessGain)
    audio = paths.src(sheet.audio)
    max_steps = 0 if isinstance(g, FixedGain) else g.max_steps
    lines = [
        "# Every cut at the master's one setting; while a delivered file is over the ceiling, step",
        "# " + ("the limiter" if loudness else "the gain") + " down by its overshoot and encode every cut again.",
        "steps=0; FAILED=",
        "while :; do",
        "  W=-999",
    ]
    if loudness:
        lines.append('  LIM=$(limiter "$L")')
    for i, cut in voiced:
        out = paths.out(cut.out)
        video_in = _video_input(sheet, cut, paths, cards.get(i))
        limiter = _LIMITER if loudness else None
        lines += [
            "  " + _cut_comment(sheet, cut, i),
            "  " + _command(_encode_argv(sheet, cut, video_in, audio, out, _GAIN, limiter)),
            f"  P=$(truepeak {_sh(_arg(out))}); W=$(worst \"$W\" \"$P\" {_sh(_arg(out))})",
            f"  printf '%s: true peak %s dBTP\\n' {shlex.quote(cut.out)} \"$P\"",
        ]
    lines += [
        "  if awk -v w=\"$W\" -v c=\"$C\" 'BEGIN { exit !(w + 0 <= c + 0) }'; then break; fi",
    ]
    if isinstance(g, FixedGain):
        lines += [
            "  printf 'kaleidophone: a delivered file peaks at %s dBTP, over the %s dBTP ceiling, at the "
            "fixed gain %s dB -- lower gain.db, or use mode: auto\\n' \"$W\" \"$C\" \"$G\" >&2",
            "  FAILED=1; break",
        ]
    else:
        what = "limiter" if loudness else "gain"
        lines += [
            f"  N=$(steps_for \"$W\" \"$C\" {_num(g.step_db)}); left=$(({max_steps} - steps))",
        ]
        if loudness:
            lines.append(
                f"  if [ \"$left\" -le 0 ] || awk -v l=\"$L\" 'BEGIN {{ exit !(l <= {_num(LIMITER_FLOOR_DBFS)}) }}'; then"
            )
        else:
            lines.append('  if [ "$left" -le 0 ]; then')
        lines += [
            f"    printf 'kaleidophone: the {what} has run out of steps: a delivered file still peaks at %s "
            f"dBTP, over the %s dBTP ceiling\\n' \"$W\" \"$C\" >&2",
            "    FAILED=1; break",
            "  fi",
            f'  if [ "$N" -gt {_max_jump(g.step_db)} ]; then N={_max_jump(g.step_db)}; fi',
            '  if [ "$N" -gt "$left" ]; then N=$left; fi',
            "  steps=$((steps + N))",
        ]
        if loudness:
            lines += [
                f"  L=$(awk -v l=\"$L\" -v n=\"$N\" -v s={_num(g.step_db)} 'BEGIN {{ x = l - n * s; "
                f"if (x < {_num(LIMITER_FLOOR_DBFS)}) x = {_num(LIMITER_FLOOR_DBFS)}; printf \"%.2f\", x }}')",
                "  printf 'over the ceiling: every cut again with the limiter at %s dBFS\\n' \"$L\"",
            ]
        else:
            lines += [
                f"  G=$(awk -v g=\"$G\" -v n=\"$N\" -v s={_num(g.step_db)} 'BEGIN {{ printf \"%.2f\", g - n * s }}')",
                "  printf 'over the ceiling: every cut again at gain %s dB\\n' \"$G\"",
            ]
    lines += ["done"]
    if loudness:
        lines.append("printf 'every cut at gain %s dB, limiter %s dBFS\\n' \"$G\" \"$L\"")
    else:
        lines.append("printf 'every cut at gain %s dB\\n' \"$G\"")
    return [*lines, ""]
