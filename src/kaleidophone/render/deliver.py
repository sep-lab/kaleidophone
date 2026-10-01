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

Endings as variants (issue #58). A piece can end more than one way: `render.mjs
--endings <axis>` renders the body once and every ending from the same
point, one encoder setting for all, and writes `<stem>.variants.json`. A cut
with `endings` -- that manifest, or a `body`, `at` and a list -- delivers one
file per ending, `<out stem>.<ending><suffix>`: the body and that ending
joined by the concat demuxer with stream copy (behind the card, if the cut
has one), and the master muxed over the whole cut at the master's one gain,
every file measured. Then `<out stem>.endings.jpg` shows the endings side
by side, so the artist can choose -- or post them all as trial reels and
keep the one people watch to the end. Before anything runs, every part is
probed: its frame count, a keyframe at its start, and the stream parameters
of the rest. Measured with ffmpeg 6.1 on synthetic x264 parts and on the
canvas template's own: every delivered ending had all its frames on a
uniform clock, a keyframe at the join, video and audio starting at 0 and no
lag between them (0 samples, cross-correlated against the master), and the
--dry-run script wrote the same bytes, contact sheet included.

A sheet whose every cut has endings needs no `silent`.

Platforms (issue #57). A cut with `platform: <id>` -- or `platforms: [...]`,
one file per platform -- is delivered to that platform's published spec
(render/platforms.py; `kaleidophone platforms` prints it). The picture is
stream-copied when the render already is a size the platform documents
(the sheet says the render's `size`, so --dry-run plans the same way without
it); otherwise it is scaled once, with Lanczos, into an intermediate that
every round of the guard then stream-copies like any other cut. When the
shape differs as well, the cut says how to fit it: `reframe: pad-blur` (the
picture centred over a scaled copy of itself, blurred, darkened and
desaturated), `pad-color` (bars) or `crop`. Before anything runs, every output is held to its platform: a
length past its limit, a frame rate it doesn't take, a shape it won't take,
is refused; past a softer limit (Instagram's 3 min for reach) it is
delivered with a warning. After, the files themselves are -- their size,
length, frame rate, audio stream and file size, and their loudness against
the level the platform plays at. That last one is information, not a gain:
there is still one gain per master. A platform that takes no audio (a Spotify
Canvas, Apple's motion art) gets a file with no audio stream.

Names, covers and the manifest (#34, #27). A cut without `out` is named from
the sheet's `title`, `<title>.<name>.<platform>[.<ending>].mp4`. `covers`
turns one square master into every cover a platform asks for, with Pillow
(cover/matrix.py). Every delivery writes `<title>.delivery.json` next to the
files: each artifact with its platform, what was planned and what was
measured, and the findings, and every platform's spec. --dry-run's script
writes the planned one, and leaves the covers to `kaleidophone deliver`:
they are Pillow's work, not ffmpeg's.

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
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from kaleidophone import __version__
from kaleidophone.cover import matrix
from kaleidophone.render import platforms as pf
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

# The endings' contact sheet (module docstring, "Endings"): the last body
# frame, then this many frames of each ending, its first and last included.
ENDING_SHEET_FRAMES = 6
_SHEET_CELL_H = 320  # px, each frame's height on the sheet
_SHEET_GAP = 8  # px, around and between the frames
_SHEET_LABEL_H = 36  # px, the strip above each row that carries its ending's name
_SHEET_BACKGROUND = "0x111111"
_SHEET_JOIN = "0xe03c31"  # the mark between the last body frame and the ending
# What every part of a join has to share, as ffprobe names it (`stream=`).
_STREAM_PARAMS = (
    "codec_name", "profile", "level", "pix_fmt", "width", "height", "r_frame_rate", "time_base", "sample_aspect_ratio",
)

# A platform's picture, when the render isn't a size it documents (module
# docstring, "Platforms"): scaled once with Lanczos and encoded at a quality
# the platform's own transcode can't tell from the render.
PICTURE_CRF = 18
PICTURE_PRESET = "medium"
_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX]\s*(\d{1,5})\s*$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MANIFEST_SUFFIX = ".delivery.json"
MANIFEST_VERSION = 1

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


def _plain_name(name: str, what: str) -> str:
    """A name that becomes part of a file name: any text but a path."""
    _no_control_characters(name, what)
    if not name.strip() or name != name.strip() or name.startswith(".") or "/" in name or "\\" in name:
        raise ValueError(
            f"{what} {name!r} must be a plain name -- no '/' or '\\', no leading '.', "
            f"no leading or trailing spaces"
        )
    return name


def _ending_name(name: str) -> str:
    """An ending's name becomes part of a file name, `<cut>.<name>.mp4`, and
    the label of its row on the contact sheet: any text but a path."""
    return _plain_name(name, "ending name")


def slugify(title: str) -> str:
    """A title as the first part of a file name: lowercased, every run of
    anything but a letter or a digit one hyphen (`SHOULD I ?` -> should-i).
    Letters in any script stay letters."""
    text = unicodedata.normalize("NFKC", title).casefold()
    return re.sub(r"[\W_]+", "-", text).strip("-")


def _platform_id(name: str, kind: pf.Kind) -> str:
    """A platform id or alias from a sheet, as the registry's id -- refusing
    one of the other kind, and saying where it goes."""
    platform = pf.get(name)
    if platform.kind != kind:
        where = "`covers.platforms`" if platform.kind == "image" else "a cut's `platform`"
        raise ValueError(f"{platform.id} is {'an image' if platform.kind == 'image' else 'a video'}: it goes in {where}")
    return platform.id


def _platform_ids(names: list[str], kind: pf.Kind) -> list[str]:
    ids = [_platform_id(name, kind) for name in names]
    twice = sorted({i for i in ids if ids.count(i) > 1})
    if twice:
        raise ValueError(f"{', '.join(twice)} is listed twice (an alias counts as its platform)")
    return ids


def _plain_file_name(name: str) -> str:
    """A variants manifest names its files, never paths: they sit next to it."""
    _no_control_characters(name, "file")
    if name in ("", ".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"file {name!r} must be a file name next to the manifest, not a path")
    return name


def _same_names(names: list[str]) -> tuple[str, str] | None:
    """The first two names that would write one file -- compared the way a
    case-insensitive disk (macOS's, by default) compares them."""
    seen: dict[str, str] = {}
    for name in names:
        key = name.casefold()
        if key in seen:
            return seen[key], name
        seen[key] = name
    return None


def _error_lines(exc: ValidationError, prefix: tuple[int | str, ...] = (), top: str | None = None) -> list[str]:
    """A ValidationError as `where: what` lines -- `cuts[1].fade_in: ...`."""
    lines = []
    for err in exc.errors():
        loc = (*prefix, *err["loc"])
        where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in loc).lstrip(".") or top
        message = err["msg"].removeprefix("Value error, ")
        lines.append(f"{where}: {message}" if where else message)
    return lines


class EndingConfig(_Strict):
    """One ending of a cut that lists its own: its name and its file."""

    name: str
    file: str

    @field_validator("name")
    @classmethod
    def _name_is_not_a_path(cls, v: str) -> str:
        return _ending_name(v)

    @field_validator("file")
    @classmethod
    def _file_is_a_plain_path(cls, v: str) -> str:
        return _no_control_characters(v, "file")


class CutConfig(_Strict):
    """One deliverable: `dur` seconds of picture and audio from `t0`.

    With a `card`, the picture is the card (a separately rendered segment
    covering `t0`..`video_from`) followed by the film from the keyframe at
    `video_from`; the audio still runs from `t0`. With `audio: none` the cut
    has no audio stream.

    With `endings`, the picture isn't cut from the silent render at all: it
    is a body and one of several endings, joined, and the cut delivers one
    file per ending, `<out stem>.<ending><suffix>` -- see the module
    docstring, "Endings".

    With `platform`, the file is held to that platform's spec; `platforms`
    delivers one file per platform, `<out stem>.<platform><suffix>`. Without
    `out`, the sheet's `title` and the cut's `name` name its files -- see
    the module docstring, "Platforms" and "Names".
    """

    out: str | None = Field(
        default=None,
        description="The file, relative to the output directory. Without it, the sheet's title and the "
        "cut's name name it: <title>.<name>[.<platform>][.<ending>].mp4.",
    )
    name: str | None = Field(default=None, description="The cut's name, for its files when it has no `out`.")
    platform: str | None = Field(default=None, description="The platform this file is for (an id or alias).")
    platforms: list[str] | None = Field(default=None, description="One file per platform.")
    reframe: Literal["pad-blur", "pad-color", "crop"] | None = Field(
        default=None,
        description="How the render fits a platform of another shape: pad-blur (the picture over a "
        "blurred copy of itself), pad-color (bars) or crop.",
    )
    pad_color: str | None = Field(default=None, description="pad-color's colour, #rrggbb (default #000000).")
    t0: float = Field(ge=0.0, allow_inf_nan=False)
    dur: float = Field(gt=0.0, allow_inf_nan=False)
    fade_in: float = Field(default=DEFAULT_FADE_IN, ge=0.0, allow_inf_nan=False)
    fade_out: float = Field(default=DEFAULT_FADE_OUT, ge=0.0, allow_inf_nan=False)
    audio: Literal["none"] | None = Field(
        default=None, description="`none`: no audio stream (a Spotify Canvas). Default: the sheet's master."
    )
    card: str | None = None
    video_from: float | None = Field(default=None, allow_inf_nan=False)
    endings: str | list[EndingConfig] | None = Field(
        default=None,
        description="A render.mjs variants manifest (`<stem>.variants.json`), or a list of {name, file} "
        "with `body` and `at`: one delivered file per ending.",
    )
    body: str | None = Field(default=None, description="With a list of `endings`: the picture from t0 to `at`.")
    at: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="With a list of `endings`: where the body ends and every ending begins, on the render's clock.",
    )

    @field_validator("endings", mode="before")
    @classmethod
    def _a_manifest_or_a_list(cls, v: object) -> object:
        # Validated here, one ending at a time, so a mistake in one reads as
        # `[1].file: Field required` rather than as two failed union members.
        if v is None or isinstance(v, str):
            return _no_control_characters(v, "endings")
        if not isinstance(v, list):
            raise ValueError("`endings` is a variants manifest (its path) or a list of {name, file}")
        parsed = []
        for k, item in enumerate(v):
            try:
                parsed.append(EndingConfig.model_validate(item))
            except ValidationError as exc:
                raise ValueError("; ".join(_error_lines(exc, prefix=(k,)))) from None
        return parsed

    @field_validator("body")
    @classmethod
    def _body_is_a_plain_path(cls, v: str | None) -> str | None:
        return _no_control_characters(v, "body")

    @field_validator("out")
    @classmethod
    def _out_stays_inside_the_output_directory(cls, v: str | None) -> str | None:
        # SECURITY.md: nothing in a shared file may write outside the
        # directory the user asked for.
        if v is None:
            return v
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

    @field_validator("name")
    @classmethod
    def _name_is_not_a_path(cls, v: str | None) -> str | None:
        return v if v is None else _plain_name(v, "name")

    @field_validator("platform")
    @classmethod
    def _a_video_platform(cls, v: str | None) -> str | None:
        return v if v is None else _platform_id(v, "video")

    @field_validator("platforms")
    @classmethod
    def _video_platforms(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("`platforms` lists no platforms")
        return _platform_ids(v, "video")

    @field_validator("pad_color")
    @classmethod
    def _a_hex_color(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_COLOR.match(v):
            raise ValueError(f"pad_color {v!r} is not a colour -- use #rrggbb, like '#000000'")
        return v

    @field_validator("card")
    @classmethod
    def _card_is_a_plain_path(cls, v: str | None) -> str | None:
        return _no_control_characters(v, "card")

    @model_validator(mode="after")
    def _named_and_aimed(self) -> CutConfig:
        if self.out is None and self.name is None:
            raise ValueError(
                f"a cut needs `out` (its file) or `name` (with the sheet's title it names the cut's files) "
                f"-- the cut at t0 {self.t0:g}"
            )
        if self.platform is not None and self.platforms is not None:
            raise ValueError(f"{self.label}: `platform` or `platforms`, not both")
        if self.reframe is not None and not self.targets:
            raise ValueError(f"{self.label}: `reframe` fits the render to a platform's frame -- it needs `platform`")
        if self.pad_color is not None and self.reframe != "pad-color":
            raise ValueError(f"{self.label}: pad_color is the colour of `reframe: pad-color`'s bars")
        return self

    @model_validator(mode="after")
    def _fades_and_card_are_consistent(self) -> CutConfig:
        if not self.voiced:
            faded = sorted({"fade_in", "fade_out"} & self.model_fields_set)
            if faded:
                why = "`audio: none`" if not self.has_audio else f"{', '.join(self.targets)} takes no audio, so it"
                raise ValueError(f"{self.label}: {why} has no audio to fade -- drop {' and '.join(faded)}")
        elif self.fade_in + self.fade_out > self.dur + 1e-9:
            raise ValueError(
                f"{self.label}: fade_in ({self.fade_in:g}) + fade_out ({self.fade_out:g}) is longer "
                f"than the cut ({self.dur:g} s)"
            )
        if (self.card is None) != (self.video_from is None):
            raise ValueError(
                f"{self.label}: `card` and `video_from` go together -- the card covers t0..video_from, "
                f"and the film resumes from the keyframe at video_from"
            )
        if self.video_from is not None and not self.t0 < self.video_from < self.t0 + self.dur:
            raise ValueError(
                f"{self.label}: video_from ({self.video_from:g}) must fall inside the cut "
                f"({self.t0:g}..{self.t0 + self.dur:g})"
            )
        return self

    @model_validator(mode="after")
    def _endings_are_consistent(self) -> CutConfig:
        given = [name for name in ("body", "at") if getattr(self, name) is not None]
        if not isinstance(self.endings, list):
            if given:
                where = "come from its variants manifest" if self.endings else "go with a list of `endings`"
                raise ValueError(f"{self.label}: {' and '.join(given)} {where}")
            return self
        if not self.endings:
            raise ValueError(f"{self.label}: `endings` lists no endings")
        if len(given) < 2:
            raise ValueError(
                f"{self.label}: a list of `endings` needs `body` (the picture from t0) and `at` (where the "
                f"body ends and every ending begins)"
            )
        if not self.t0 < self.at < self.t0 + self.dur:
            raise ValueError(f"{self.label}: at ({self.at:g}) must fall inside the cut ({self.t0:g}..{self.t0 + self.dur:g})")
        if self.video_from is not None and self.video_from >= self.at:
            raise ValueError(
                f"{self.label}: the card runs until video_from ({self.video_from:g}), and the endings begin at "
                f"{self.at:g} -- the card has to end in the body"
            )
        same = _same_names([e.name for e in self.endings])
        if same:
            raise ValueError(f"{self.label}: two endings named {same[0]!r} and {same[1]!r} would write one file")
        return self

    @property
    def has_audio(self) -> bool:
        """The cut's audio isn't `none` (a platform may still take none: see `voiced`)."""
        return self.audio != "none"

    @property
    def label(self) -> str:
        """What messages call the cut: its `out`, or its `name`."""
        return self.out if self.out is not None else str(self.name)

    @property
    def targets(self) -> tuple[str, ...]:
        """The platforms the cut is delivered to, as registry ids -- none for a plain cut."""
        if self.platform is not None:
            return (self.platform,)
        return tuple(self.platforms or ())

    @property
    def voiced(self) -> bool:
        """Whether any file the cut delivers has audio."""
        return self.has_audio and (not self.targets or any(pf.get(t).audio != "none" for t in self.targets))

    def frames(self, fps: float) -> int:
        return round(self.dur * fps)

    def card_frames(self, fps: float) -> int:
        return round((self.video_from - self.t0) * fps) if self.video_from is not None else 0


class CoversConfig(_Strict):
    """Every cover a platform asks for, from one square master (cover/matrix.py)."""

    master: str = Field(description="A square image, as large as the largest cover drawn from it or larger.")
    portrait: str | None = Field(
        default=None,
        description="A 9:16 still for the 9:16 covers. Without it they are the master centred over a "
        "blurred copy of itself.",
    )
    platforms: list[str] = Field(min_length=1, description="Image platforms (ids or aliases), one cover each.")
    background: str | None = Field(
        default=None,
        description="What a master or portrait with real transparency is flattened onto, #rrggbb "
        "(default #ffffff, white). An alpha channel that is opaque everywhere is just dropped.",
    )

    @field_validator("master", "portrait")
    @classmethod
    def _plain_paths(cls, v: str | None) -> str | None:
        return _no_control_characters(v, "path")

    @field_validator("background")
    @classmethod
    def _a_hex_color(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_COLOR.match(v):
            raise ValueError(f"covers.background {v!r} is not a colour -- use #rrggbb, like '#ffffff'")
        return v

    @field_validator("platforms")
    @classmethod
    def _image_platforms(cls, v: list[str]) -> list[str]:
        return _platform_ids(v, "image")

    @model_validator(mode="after")
    def _a_portrait_is_for_a_tall_cover(self) -> CoversConfig:
        tall = [pid for pid in self.platforms if pf.same_aspect(pf.get(pid).size, matrix.PORTRAIT_SHAPE)]
        if self.portrait is not None and not tall:
            shaped = ", ".join(p.id for p in pf.of_kind("image") if pf.same_aspect(p.size, matrix.PORTRAIT_SHAPE))
            raise ValueError(f"`portrait` is for the 9:16 covers, and none is asked for ({shaped})")
        return self


class DeliverySheet(_Strict):
    """Top-level document -- what `kaleidophone deliver sheet.yaml` reads.

    Relative `silent`, `audio`, `card`, `body`, ending and manifest paths
    resolve against the sheet's own directory, so a project folder can move
    without editing the sheet. `silent_start` is only for a render that
    doesn't begin at the top of the song (see the module docstring); it is
    not snapped to the frame grid, because the song's clock has no frames.
    """

    title: str | None = Field(
        default=None,
        description="The release's title: it names the manifest, the covers and every cut without `out`.",
    )
    slug: str | None = Field(
        default=None,
        description="The title as file names start, when the title alone won't do (a title of "
        "punctuation). Default: the title, lowercased, with hyphens.",
    )
    size: str | None = Field(
        default=None,
        description="The silent render's frame size, WxH -- required with `platform`/`platforms`: "
        "whether a platform's file is stream-copied or scaled depends on it.",
    )
    covers: CoversConfig | None = None
    silent: str | None = Field(
        default=None, description="The one silent render. Required unless every cut has `endings`."
    )
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
    cuts: list[CutConfig] = Field(default_factory=list)
    check: bool = True

    @field_validator("silent", "audio")
    @classmethod
    def _inputs_are_plain_paths(cls, v: str | None) -> str | None:
        return _no_control_characters(v, "path")

    @field_validator("title")
    @classmethod
    def _a_title(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title is empty")
        return _no_control_characters(v, "title")

    @field_validator("slug")
    @classmethod
    def _slug_is_not_a_path(cls, v: str | None) -> str | None:
        return v if v is None else _plain_name(v, "slug")

    @field_validator("size")
    @classmethod
    def _a_frame_size(cls, v: str | None) -> str | None:
        if v is None:
            return v
        match = _SIZE_RE.match(v)
        if not match or not all(0 < int(n) <= 16384 for n in match.groups()):
            raise ValueError(f"size {v!r} is not a frame size -- use WxH, like 1080x1920")
        return f"{int(match.group(1))}x{int(match.group(2))}"

    @model_validator(mode="after")
    def _cuts_are_deliverable(self) -> DeliverySheet:
        if not self.cuts and self.covers is None:
            raise ValueError("nothing to deliver: `cuts` is empty and there are no `covers`")
        named = [cut.label for cut in self.cuts if cut.out is None]
        if self.file_stem is None and (named or self.covers is not None):
            what = (
                f"{', '.join(named)} {'has' if len(named) == 1 else 'have'} no `out`, and a cut's files are "
                f"then named <title>.<name>[.<platform>].mp4" if named else "covers are named <title>.cover.<platform>.jpg"
            )
            if self.title is not None:
                raise ValueError(
                    f"title {self.title!r} has no letter or digit to start a file name with ({what}) -- give "
                    f"`slug` as well, the title as file names should start"
                )
            raise ValueError(f"`title` is required: {what}")
        aimed = [cut.label for cut in self.cuts if cut.targets]
        if aimed and self.frame is None:
            raise ValueError(
                f"`size` (the silent render's, WxH) is required: {', '.join(aimed)} "
                f"{'goes' if len(aimed) == 1 else 'go'} to a platform, and whether its picture is stream-copied "
                f"or scaled depends on it"
            )
        # A manifest's endings are only known once it is read: its files are
        # checked again then (_resolve_endings), with every name.
        listed = {i: tuple(e.name for e in cut.endings) for i, cut in enumerate(self.cuts, 1)
                  if isinstance(cut.endings, list)}
        twice = _written_twice(self, listed)
        if twice:
            raise ValueError(f"two cuts write {twice!r} -- the second would silently overwrite the first")
        for cut in self.cuts:
            for name in ("t0", "video_from", "at"):
                value = getattr(cut, name)
                if value is not None:
                    self._on_frame_grid(cut, name, value)
        framed = [cut.label for cut in self.cuts if cut.endings is None]
        if self.silent is None and framed:
            raise ValueError(
                f"`silent` (the render) is required: {', '.join(framed)} "
                f"{'is' if len(framed) == 1 else 'are'} cut from it. Only a sheet whose every cut has "
                f"`endings` can leave it out"
            )
        voiced = [cut.label for cut in self.cuts if cut.voiced]
        if self.audio is None and voiced:
            raise ValueError(
                f"`audio` (the master) is required: {', '.join(voiced)} "
                f"{'has' if len(voiced) == 1 else 'have'} audio. Only a sheet whose every cut is "
                f"`audio: none` (or goes only to platforms that take none) can leave it out"
            )
        return self

    @property
    def file_stem(self) -> str | None:
        """How the sheet's own file names start: `slug`, or the title made one."""
        if self.slug is not None:
            return self.slug
        return (slugify(self.title) or None) if self.title is not None else None

    @property
    def frame(self) -> tuple[int, int] | None:
        """The silent render's (width, height), from `size`."""
        if self.size is None:
            return None
        width, height = self.size.split("x")
        return int(width), int(height)

    def _on_frame_grid(self, cut: CutConfig, name: str, value: float) -> None:
        frames = value * self.fps
        if abs(frames - round(frames)) > _GRID_TOLERANCE:
            below = math.floor(frames) / self.fps
            above = math.ceil(frames) / self.fps
            raise ValueError(
                f"{cut.label}: {name} {value:g} isn't on the {self.fps:g} fps frame grid (nearest "
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
    return "\n".join(f"  {line}" for line in _error_lines(exc, top="sheet"))


# --------------------------------------------------------------------------
# endings: the manifest, and the files a cut with endings writes
# --------------------------------------------------------------------------
class _VariantPart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file: str
    frames: int = Field(ge=1)

    @field_validator("file")
    @classmethod
    def _a_file_name(cls, v: str) -> str:
        return _plain_file_name(v)


class _VariantEnding(_VariantPart):
    option: str

    @field_validator("option")
    @classmethod
    def _a_name(cls, v: str) -> str:
        return _ending_name(v)


class VariantsManifest(BaseModel):
    """What `node tools/render.mjs <piece> --endings <axis>` writes next to its
    parts: `<stem>.variants.json`. `t0` and `at` are song seconds, `dur` the
    window's length; the files are names in the manifest's own directory.
    Keys beyond these are ignored -- its `stream` block among them, because
    `deliver` probes every part itself."""

    model_config = ConfigDict(extra="ignore")

    piece: str | None = None
    axis: str | None = None
    at: float = Field(allow_inf_nan=False)
    t0: float = Field(allow_inf_nan=False)
    dur: float = Field(gt=0.0, allow_inf_nan=False)
    fps: float = Field(gt=0.0, allow_inf_nan=False)
    body: _VariantPart
    endings: list[_VariantEnding] = Field(min_length=1)


def load_variants(path: str) -> VariantsManifest:
    """Read a variants manifest; a malformed one is refused in one line."""
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a variants manifest: expected an object with body and endings")
    try:
        return VariantsManifest.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{path} is not a variants manifest: {'; '.join(_error_lines(exc))}") from None


@dataclass(frozen=True)
class _Ending:
    name: str
    file: str  # as the commands name it
    frames: int


@dataclass(frozen=True)
class _Endings:
    """A cut's picture as a body and its endings, from its manifest or the sheet."""

    body: str  # as the commands name it
    frames: int  # the cut's frames before the join: the body's, a card's included
    endings: tuple[_Ending, ...]


def _resolve_endings(sheet: DeliverySheet, paths: _Paths) -> dict[int, _Endings]:
    """Every cut's endings, by the cut's position in the sheet (from 1): its
    manifest read, and its times and frame counts held to the cut's -- or,
    for a cut that lists them, its body up to `at` and the rest per ending.
    Every mismatch is refused, one line each, before anything runs."""
    resolved: dict[int, _Endings] = {}
    problems: list[str] = []
    for i, cut in enumerate(sheet.cuts, 1):
        if isinstance(cut.endings, str):
            manifest = paths.src(cut.endings)
            variants = load_variants(manifest)
            found = _manifest_problems(sheet, cut, variants)
            problems += [f"{cut.label}: {p}" for p in found]
            if not found:
                here = os.path.dirname(manifest)
                resolved[i] = _Endings(
                    os.path.normpath(os.path.join(here, variants.body.file)),
                    variants.body.frames,
                    tuple(
                        _Ending(e.option, os.path.normpath(os.path.join(here, e.file)), e.frames)
                        for e in variants.endings
                    ),
                )
        elif cut.endings:
            body_frames = round((cut.at - cut.t0) * sheet.fps)
            rest = cut.frames(sheet.fps) - body_frames
            resolved[i] = _Endings(
                paths.src(cut.body), body_frames, tuple(_Ending(e.name, paths.src(e.file), rest) for e in cut.endings)
            )
    if problems:
        raise ValueError("the endings don't fit their cuts:\n  " + "\n  ".join(problems))
    twice = _written_twice(sheet, {i: tuple(e.name for e in r.endings) for i, r in resolved.items()})
    if twice:
        raise ValueError(f"two cuts write {twice!r} -- the second would silently overwrite the first")
    return resolved


def _manifest_problems(sheet: DeliverySheet, cut: CutConfig, variants: VariantsManifest) -> list[str]:
    """Where a manifest and its cut disagree: the frame rate, where it starts
    in the song, how long it runs, where the join is, how many frames each
    part has -- and names two endings would share a file under."""
    fps = sheet.fps
    if abs(variants.fps - fps) > 1e-6:
        return [f"its variants were rendered at {variants.fps:g} fps; the sheet's fps is {fps:g}"]
    half = 0.5 / fps
    problems = []
    song_t0 = _song_t0(sheet, cut)
    if abs(variants.t0 - song_t0) > half:
        cut_at = f"song time {song_t0:.3f} s (silent_start {sheet.silent_start:g} + t0 {cut.t0:g})"
        problems.append(
            f"its variants start at song time {variants.t0:.3f} s, the cut at "
            + (cut_at if sheet.silent_start else f"{song_t0:.3f} s")
        )
    if abs(variants.dur - cut.dur) > half:
        problems.append(f"its variants run {variants.dur:g} s, the cut {cut.dur:g} s")
    body = variants.body.frames
    if not variants.t0 < variants.at < variants.t0 + variants.dur:
        problems.append(
            f"its manifest's at ({variants.at:g} s) isn't inside its window "
            f"({variants.t0:g}..{variants.t0 + variants.dur:g} s)"
        )
    elif body != round((variants.at - variants.t0) * fps):
        problems.append(
            f"its body has {body} frames, but {variants.t0:g}..{variants.at:g} s at {fps:g} fps is "
            f"{round((variants.at - variants.t0) * fps)}"
        )
    total = cut.frames(fps)
    for e in variants.endings:
        if body + e.frames != total:
            problems.append(
                f"ending {e.option!r} has {e.frames} frames: after the body's {body} that is "
                f"{body + e.frames}, and the cut is {total}"
            )
    if cut.card and cut.card_frames(fps) >= body:
        problems.append(
            f"its card ({cut.card_frames(fps)} frames) runs to or past the join at frame {body}: "
            f"the card has to end in the body"
        )
    same = _same_names([e.option for e in variants.endings])
    if same:
        problems.append(f"two endings named {same[0]!r} and {same[1]!r} would write one file")
    return problems


def _split_suffix(out: str) -> tuple[str, str]:
    """`reels/SONG_reel.mp4` -> (`reels/SONG_reel`, `.mp4`); `out` always has one of OUTPUT_SUFFIXES."""
    suffix = next(s for s in OUTPUT_SUFFIXES if out.lower().endswith(s))
    return out[: -len(suffix)], out[-len(suffix) :]


def ending_out(out: str, name: str) -> str:
    """The file one ending of a cut is delivered as: `<out stem>.<name><suffix>`."""
    stem, suffix = _split_suffix(out)
    return f"{stem}.{name}{suffix}"


def contact_sheet_out(out: str) -> str:
    """Where a cut's endings are shown side by side: `<out stem>.endings.jpg`."""
    return _split_suffix(out)[0] + ".endings.jpg"


def output_name(sheet: DeliverySheet, cut: CutConfig, platform: str | None = None, ending: str | None = None) -> str:
    """The file one output of a cut is delivered as (#34). With `out`: `out`
    itself, `<out stem>.<platform><suffix>` for each of a list of
    `platforms`, and `.<ending>` after either for an ending. Without:
    `<title>.<name>[.<platform>][.<ending>].mp4`."""
    if cut.out is not None:
        stem, suffix = _split_suffix(cut.out)
        listed = platform if platform is not None and cut.platforms is not None else None
    else:
        stem, suffix, listed = f"{sheet.file_stem}.{cut.name}", ".mp4", platform
    return ".".join(part for part in (stem, listed, ending) if part is not None) + suffix


def cut_file(sheet: DeliverySheet, cut: CutConfig) -> str:
    """The name a cut's own files hang off: its `out`, or `<title>.<name>.mp4`
    -- what its contact sheet is named after."""
    return cut.out if cut.out is not None else f"{sheet.file_stem}.{cut.name}.mp4"


def cover_name(sheet: DeliverySheet, platform: str) -> str:
    """The file a cover is written as: `<title>.cover.<platform>.jpg`."""
    return f"{sheet.file_stem}.cover.{platform}.jpg"


def manifest_name(sheet: DeliverySheet) -> str:
    """The delivery's manifest: `<title>.delivery.json`, or `delivery.json` for a sheet with no title."""
    return f"{sheet.file_stem}{MANIFEST_SUFFIX}" if sheet.file_stem is not None else MANIFEST_SUFFIX.lstrip(".")


def _cut_files(sheet: DeliverySheet, cut: CutConfig, endings: tuple[str, ...]) -> list[str]:
    """Every file a cut writes: each platform's (each ending's), and a cut
    with endings its contact sheet."""
    files = [
        output_name(sheet, cut, platform, ending)
        for platform in (cut.targets or (None,))
        for ending in (endings or (None,))
    ]
    return files + ([contact_sheet_out(cut_file(sheet, cut))] if cut.endings is not None else [])


def _written_twice(sheet: DeliverySheet, names: dict[int, tuple[str, ...]]) -> str | None:
    """The first file two cuts would both write, if any -- every platform's,
    ending and contact sheet included (`names`: each cut's endings, where
    known)."""
    seen: set[str] = set()
    for i, cut in enumerate(sheet.cuts, 1):
        for name in _cut_files(sheet, cut, names.get(i, ())):
            key = os.path.normpath(name)
            if key in seen:
                return name
            seen.add(key)
    return None


@dataclass(frozen=True)
class _Reframe:
    """How one output's picture is made from its cut's when the render isn't
    a size the platform documents: scaled (`how` "scale"), or fitted to
    another shape ("pad-blur", "pad-color", "crop"). `graph` is the
    -filter_complex, from [0:v:0] to [v]; `drawn` the size the picture is
    drawn at inside the platform's frame."""

    how: str
    source: tuple[int, int]
    target: tuple[int, int]
    drawn: tuple[int, int]
    graph: str

    @property
    def enlarged(self) -> float:
        """How many times larger the picture is drawn than it was rendered (1 or less: not enlarged)."""
        return self.drawn[0] / self.source[0]

    def describe(self) -> str:
        (sw, sh), (tw, th), (dw, dh) = self.source, self.target, self.drawn
        if self.how == "scale":
            return f"{sw}x{sh} scaled to {tw}x{th}, Lanczos"
        then = {
            "crop": f"cropped to {tw}x{th}",
            "pad-color": f"on {tw}x{th} with bars",
            "pad-blur": f"over a blurred copy of itself filling {tw}x{th}",
        }[self.how]
        return f"{sw}x{sh} scaled to {dw}x{dh}, Lanczos, {then}"


@dataclass(frozen=True)
class _Output:
    """One file a sheet delivers: a cut, one ending of a cut with endings,
    one platform of a cut with platforms -- or one ending for one platform."""

    cut: CutConfig
    index: int  # the cut's position in the sheet, from 1 -- it names the cut's intermediates
    out: str  # relative to the output directory
    ending: _Ending | None = None
    platform: pf.Platform | None = None
    reframe: _Reframe | None = None  # None: the picture is stream-copied

    @property
    def has_audio(self) -> bool:
        return self.cut.has_audio and (self.platform is None or self.platform.audio != "none")


def _outputs(sheet: DeliverySheet, endings: dict[int, _Endings]) -> list[_Output]:
    outputs = []
    for i, cut in enumerate(sheet.cuts, 1):
        for platform in [pf.get(t) for t in cut.targets] or [None]:
            reframe = _plan_reframe(sheet, cut, platform) if platform is not None else None
            pid = platform.id if platform is not None else None
            if i in endings:
                outputs += [
                    _Output(cut, i, output_name(sheet, cut, pid, e.name), e, platform, reframe)
                    for e in endings[i].endings
                ]
            else:
                outputs.append(_Output(cut, i, output_name(sheet, cut, pid), None, platform, reframe))
    return outputs


# --------------------------------------------------------------------------
# platforms: fitting the picture, and holding every output to its spec
# --------------------------------------------------------------------------
def _centred(outer: int, inner: int) -> int:
    """The even offset that centres `inner` in `outer` (chroma is subsampled by two)."""
    return (outer - inner) // 4 * 2


def _shaped(source: tuple[int, int], platform: pf.Platform) -> tuple[int, int] | None:
    """The first size the platform documents in the render's shape -- what
    the picture is scaled to -- or None: it needs a reframe."""
    return next((size for size in platform.all_sizes if pf.same_aspect(source, size)), None)


def _plan_reframe(sheet: DeliverySheet, cut: CutConfig, platform: pf.Platform) -> _Reframe | None:
    """How a cut's picture becomes a platform's: None to stream-copy it (the
    render is a size the platform documents); scaled to the platform's size
    in the render's shape (a square render to a 1080x1080 Short); else
    fitted into the platform's own size the way the cut says. A shape the
    cut doesn't say how to fit is planned as a crop here, and refused by
    _plan_findings(), which says so."""
    source = sheet.frame
    if source is None or source in platform.all_sizes:
        return None
    shaped = _shaped(source, platform)
    if shaped is not None:
        return _reframe("scale", source, shaped, "#000000")
    return _reframe(cut.reframe or "crop", source, platform.size, cut.pad_color or "#000000")


def _reframe(how: str, source: tuple[int, int], target: tuple[int, int], pad_color: str) -> _Reframe:
    (tw, th) = target
    lanczos = "flags=lanczos"
    if how == "scale":
        return _Reframe(how, source, target, target, f"[0:v:0]scale={tw}:{th}:{lanczos},setsar=1[v]")
    if how == "crop":
        cw, ch = pf.cover_size(source, target)
        crop = f"crop={tw}:{th}:{_centred(cw, tw)}:{_centred(ch, th)}"
        return _Reframe(how, source, target, (cw, ch), f"[0:v:0]scale={cw}:{ch}:{lanczos},{crop},setsar=1[v]")
    fw, fh = pf.fit_size(source, target)
    x, y = _centred(tw, fw), _centred(th, fh)
    if how == "pad-color":
        pad = f"pad={tw}:{th}:{x}:{y}:color=0x{pad_color.lstrip('#').lower()}"
        return _Reframe(how, source, target, (fw, fh), f"[0:v:0]scale={fw}:{fh}:{lanczos},{pad},setsar=1[v]")
    # pad-blur (platforms.py, PAD_BLUR_*): the picture covering a small
    # frame, blurred, darkened and desaturated there and scaled back up; the
    # picture, fitted, over it.
    bw, bh = pf.blur_frame(target)
    cw, ch = pf.cover_size(source, (bw, bh))
    dim = f"eq=brightness={pf.PAD_BLUR_BRIGHTNESS:g}:saturation={pf.PAD_BLUR_SATURATION:g}"
    background = (
        f"[bg]scale={cw}:{ch}:{lanczos},crop={bw}:{bh}:{_centred(cw, bw)}:{_centred(ch, bh)},"
        f"gblur=sigma={pf.blur_sigma(target):g},{dim},scale={tw}:{th}:flags=bicubic[blur]"
    )
    graph = (
        f"[0:v:0]split=2[bg][fg];{background};[fg]scale={fw}:{fh}:{lanczos}[pic];"
        f"[blur][pic]overlay={x}:{y},setsar=1[v]"
    )
    return _Reframe(how, source, target, (fw, fh), graph)


def _seconds(cut: CutConfig, fps: float) -> float:
    """A cut's length as delivered: its frames at the sheet's rate."""
    return cut.frames(fps) / fps


def _plan_findings(sheet: DeliverySheet, outputs: list[_Output]) -> list[list[pf.Finding]]:
    """Every output held to its platform before anything runs: its size,
    length, frame rate and audio as planned, and how its picture is made.
    One list per output (empty for a plain cut); a `refuse` stops the
    delivery (_refuse_planned)."""
    found: list[list[pf.Finding]] = []
    for output in outputs:
        p, cut = output.platform, output.cut
        if p is None:
            found.append([])
            continue
        r = output.reframe
        size = r.target if r is not None else sheet.frame
        findings = pf.check_video(p, *size, sheet.fps, _seconds(cut, sheet.fps), output.has_audio, None)
        findings += _picture_findings(sheet, cut, p, r)
        found.append(findings)
    return found


def _picture_findings(sheet: DeliverySheet, cut: CutConfig, p: pf.Platform, r: _Reframe | None) -> list[pf.Finding]:
    """How an output's picture is made, held to the cut: a reframe the shape
    needs and the cut doesn't give, or one the cut gives and no platform of
    it needs, is refused; an enlarged picture is a warning; a crop says what
    it keeps."""
    if cut.reframe is not None and p.id == cut.targets[0]:
        if all(_shaped(sheet.frame, pf.get(t)) is not None for t in cut.targets):
            return [pf.Finding(
                "refuse", p.id, "picture",
                f"reframe: {cut.reframe} has nothing to fit: the render ({sheet.size}) is already the shape of "
                f"every platform the cut goes to -- drop it",
            )]
    if r is None:
        return []
    if r.how != "scale" and cut.reframe is None:
        return [pf.Finding(
            "refuse", p.id, "picture",
            f"{p.id} is {p.aspect} ({p.width}x{p.height}) and the render is {sheet.size}: say how to fit it -- "
            f"reframe: pad-blur (the picture centred over a blurred copy of itself), pad-color (bars) or crop",
        )]
    findings = []
    if r.enlarged > 1.001:
        findings.append(pf.Finding(
            "warn", p.id, "picture",
            f"the picture is enlarged {r.enlarged:.2f}x ({r.describe()}): rendered at {r.drawn[0]}x{r.drawn[1]} "
            f"or more, it wouldn't be",
        ))
    if r.how == "crop":
        (sw, sh), (cw, ch), (tw, th) = r.source, r.drawn, r.target
        findings.append(pf.Finding(
            "info", p.id, "picture",
            f"crop keeps the centre {round(sw * tw / cw)}x{round(sh * th / ch)} of the {sw}x{sh} render",
        ))
    return findings


def _refuse_planned(outputs: list[_Output], planned: list[list[pf.Finding]]) -> None:
    """Every planned `refuse`, at once, before anything runs."""
    refused = [
        f"{o.out} ({f.platform}): {f.message}" for o, fs in zip(outputs, planned) for f in fs if f.level == "refuse"
    ]
    refused = list(dict.fromkeys(refused))  # a cut's reframe, refused once per ending
    if refused:
        raise ValueError("the platforms won't take what the sheet asks of them:\n  " + "\n  ".join(refused))


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
class ContactSheet:
    """A cut's endings side by side, one row per ending, top to bottom: the
    last body frame, then `frames` frames of the ending, evenly spaced."""

    out: str
    endings: tuple[str, ...]
    frames: int
    labelled: bool = False
    note: str | None = None  # why it has no labels

    def describe(self) -> str:
        text = (
            f"contact sheet {os.path.basename(self.out)}: {', '.join(self.endings)}, top to bottom -- the "
            f"last body frame, then {self.frames} frame{'' if self.frames == 1 else 's'} of each ending"
        )
        return text if self.labelled else f"{text}; unlabelled: {self.note}"


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
    cut: str | None = None  # one of several files from a cut (an ending, a platform): the cut's out or name,
    ending: str | None = None  # ... the ending's name,
    contact_sheet: ContactSheet | None = None  # ... and the cut's contact sheet
    platform: str | None = None  # the platform it is for (registry id)
    picture: str = "copy"  # how its picture was made: stream copy, or the platform's reframe
    findings: list[pf.Finding] = field(default_factory=list)  # held to its platform, as delivered
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    audio_stream: bool | None = None  # whether the file has one; None: not probed
    size_bytes: int | None = None

    def over(self, ceiling: float | None = None) -> bool:
        ceiling = self.ceiling_dbtp if ceiling is None else ceiling
        return ceiling is not None and self.true_peak is not None and self.true_peak > ceiling


class Delivery(list):
    """What deliver() returns: one Delivered per video file, in sheet order
    -- a list, as it always was -- plus the covers made and the manifest
    written."""

    def __init__(self, results=(), covers=(), manifest: str | None = None) -> None:
        super().__init__(results)
        self.covers: list[matrix.Cover] = list(covers)
        self.manifest = manifest


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
    tail_argv = _tail_argv(paths.src(sheet.silent), _frame_time(cut.video_from, sheet.fps), tail_frames, tail)
    listing = _listing([paths.src(cut.card), tail], work)
    return _CardSteps(tail_argv, listing, list_path, _concat_argv(list_path, joined), joined, (tail, list_path, joined))


def _tail_argv(source: str, seek: str, frames: int, out: str) -> list[str]:
    """`frames` of the picture from the keyframe at `seek`, stream-copied."""
    return [
        "-y",
        "-ss", seek, "-i", _arg(source),
        "-map", "0:v:0", "-c:v", "copy", "-frames:v", str(frames),
        "-an", *CLEAN_OUTPUT,
        _arg(out),
    ]


def _listing(files: list[str], work: str) -> str:
    """A concat list. The demuxer resolves relative entries against the list
    file's own directory, not the working directory -- so they are written
    relative to it, which also keeps an absolute path out of a --dry-run
    script."""
    return "".join(f"file {concat_quote(os.path.relpath(f, work))}\n" for f in files)


def _concat_argv(list_path: str, joined: str) -> list[str]:
    return ["-y", "-f", "concat", "-safe", "0", "-i", _arg(list_path), "-c", "copy", _arg(joined)]


@dataclass(frozen=True)
class _Join:
    listing: str  # contents of the concat list
    list_path: str
    concat: list[str]  # the parts -> work/cutNN.eMM.silent.mp4
    joined: str


@dataclass(frozen=True)
class _EndingSteps:
    tail: list[str] | None  # with a card: the body from the card's end -> work/cutNN.tail.mp4
    joins: tuple[_Join, ...]  # one per ending, in order
    intermediates: tuple[str, ...]


def _ending_steps(sheet: DeliverySheet, cut: CutConfig, index: int, paths: _Paths, endings: _Endings) -> _EndingSteps:
    """A cut with endings: per ending, the body and that ending
    stream-concatenated -- behind the card, when the cut has one, with the
    body resuming from its keyframe where the card ends -- then muxed like
    any other cut. As with the card, only the picture is joined: the master
    runs on unbroken under the whole cut, so there is no audio seam."""
    work = paths.work
    stem = os.path.join(work, f"cut{index:02d}")
    head, tail_argv, made = [endings.body], None, []
    if cut.card:
        tail = f"{stem}.tail.mp4"
        card_frames = cut.card_frames(sheet.fps)
        seek = _frame_time(cut.video_from - cut.t0, sheet.fps)  # on the body's own clock
        tail_argv = _tail_argv(endings.body, seek, endings.frames - card_frames, tail)
        head, made = [paths.src(cut.card), tail], [tail]
    joins = []
    for j, ending in enumerate(endings.endings, 1):
        list_path, joined = f"{stem}.e{j:02d}.concat.txt", f"{stem}.e{j:02d}.silent.mp4"
        joins.append(_Join(_listing([*head, ending.file], work), list_path, _concat_argv(list_path, joined), joined))
        made += [list_path, joined]
    return _EndingSteps(tail_argv, tuple(joins), tuple(made))


def _sheet_picks(body_frames: int, total: int, count: int = ENDING_SHEET_FRAMES) -> list[int]:
    """The frames on a contact-sheet row, by index in the delivered picture:
    the last body frame, then `count` frames spread evenly over the ending,
    its first and last included (rounded half up, in integers, so the
    --dry-run script's awk arrives at the same frames)."""
    span = total - body_frames
    count = max(1, min(count, span))
    if count == 1:
        return [body_frames - 1, body_frames]
    return [body_frames - 1] + [
        body_frames + (2 * k * (span - 1) + count - 1) // (2 * (count - 1)) for k in range(count)
    ]


def _filter_text(text: str) -> str:
    """Text as a filter option's value inside a -filter_complex graph, quoted
    for both of the graph's parsers: the option parser (a `'`-quoted value,
    each `'` in it closed, escaped and reopened) and the graph parser (a
    backslash before each of \\ ' [ ] , ;). Any name reaches drawtext as
    written -- colons, commas, quotes, brackets, Persian (measured with
    ffmpeg 6.1)."""
    quoted = "'" + text.replace("'", "'\\''") + "'"
    return re.sub(r"([\\'\[\],;])", r"\\\1", quoted)


def _contact_sheet_argv(files: list[str], names: list[str], picks: list[int], out: str, labelled: bool) -> list[str]:
    """One -filter_complex graph: per delivered ending, the picked frames
    (by index, so the sheet is the same every run), scaled, tiled into a
    row with a mark at the join -- and a label strip with the ending's name
    when `labelled` -- then the rows stacked top to bottom."""
    cells, gap = len(picks), _SHEET_GAP
    select = "select='" + "+".join(f"eq(n,{p})" for p in picks) + "'"
    # The mark sits in the gap after the first cell: tile's width is
    # cells * w + (cells + 1) * gap, margins included.
    row = (
        f"{select},scale=-2:{_SHEET_CELL_H},setsar=1,"
        f"tile={cells}x1:margin={gap}:padding={gap}:color={_SHEET_BACKGROUND},"
        f"drawbox=x=(iw-{(cells + 1) * gap})/{cells}+{gap + gap // 2 - 2}:y=0:w=4:h=ih:color={_SHEET_JOIN}:t=fill"
    )
    chains = []
    for r, name in enumerate(names):
        chain = f"[{r}:v:0]{row}"
        if labelled:
            chain += (
                f",pad=iw:ih+{_SHEET_LABEL_H}:0:{_SHEET_LABEL_H}:color={_SHEET_BACKGROUND},"
                f"drawtext=text={_filter_text(name)}:expansion=none:fontcolor=white:fontsize=22:"
                f"x={gap}:y=({_SHEET_LABEL_H}-th)/2"
            )
        chains.append(f"{chain}[{'sheet' if len(names) == 1 else f'r{r}'}]")
    if len(names) > 1:
        chains.append("".join(f"[r{r}]" for r in range(len(names))) + f"vstack=inputs={len(names)}[sheet]")
    inputs = [arg for f in files for arg in ("-i", _arg(f))]
    return [
        "-y", *inputs,
        "-filter_complex", ";".join(chains),
        "-map", "[sheet]", "-frames:v", "1", "-q:v", "2", "-update", "1",
        _arg(out),
    ]


@dataclass(frozen=True)
class _SheetSteps:
    out: str
    names: tuple[str, ...]
    frames: int  # of each ending
    labelled: list[str]
    unlabelled: list[str]


def _contact_sheet_steps(sheet: DeliverySheet, cut: CutConfig, paths: _Paths, endings: _Endings) -> _SheetSteps:
    """The contact sheet of a cut's endings, made from the files delivered --
    a cut with platforms, from its first platform's."""
    picks = _sheet_picks(endings.frames, cut.frames(sheet.fps))
    first = cut.targets[0] if cut.targets else None
    files = [paths.out(output_name(sheet, cut, first, e.name)) for e in endings.endings]
    names = [e.name for e in endings.endings]
    out = paths.out(contact_sheet_out(cut_file(sheet, cut)))
    return _SheetSteps(
        out, tuple(names), len(picks) - 1,
        _contact_sheet_argv(files, names, picks, out, labelled=True),
        _contact_sheet_argv(files, names, picks, out, labelled=False),
    )


def _video_input(sheet: DeliverySheet, cut: CutConfig, paths: _Paths, card: _CardSteps | None) -> list[str]:
    if card is not None:
        return ["-i", _arg(card.joined)]
    seek = ["-ss", _frame_time(cut.t0, sheet.fps)] if cut.t0 > 0 else []
    return [*seek, "-i", _arg(paths.src(sheet.silent))]


def _picture_encode(platform: pf.Platform, fps: float) -> list[str]:
    """x264 for a platform's picture, from its codec notes: CRF PICTURE_CRF
    under the platform's bitrate ceiling where it has one (Instagram's 25
    Mbps); where it has a floor (Apple's motion art, 45 Mbps), an average
    bitrate in the middle of its range instead, because CRF can't promise a
    floor; YouTube's closed GOP of half the frame rate and two B-frames.

    The average is set alone, with no VBV buffer: measured with ffmpeg 6.1.1
    (its libx264, two cores), a 3840x3840 encode at -b:v with -maxrate and
    -bufsize wrote different bytes on each of three runs; -b:v alone, CRF
    under a buffer, and either at 1080x1920 wrote the same bytes every time
    -- and the same bytes are what lets --dry-run's script deliver the same
    files. Every delivered file's average bitrate is checked against the
    platform's range instead."""
    args = ["-c:v", "libx264", "-preset", PICTURE_PRESET, "-profile:v", "high", "-pix_fmt", "yuv420p"]
    ceiling = platform.max_video_mbps
    if platform.min_video_mbps is not None:
        middle = (platform.min_video_mbps + (ceiling if ceiling is not None else 2 * platform.min_video_mbps)) / 2
        args += ["-b:v", f"{middle:g}M"]
    else:
        args += ["-crf", str(PICTURE_CRF)]
        if ceiling is not None:
            args += ["-maxrate", f"{ceiling:g}M", "-bufsize", f"{2 * ceiling:g}M"]
    if platform.gop_seconds is not None:
        args += ["-g", str(max(1, round(fps * platform.gop_seconds)))]
    if platform.b_frames is not None:
        args += ["-bf", str(platform.b_frames)]
    return args


@dataclass(frozen=True)
class _ReframeStep:
    """One output's picture made for its platform: the cut's picture, fitted
    and encoded once, into the work directory."""

    argv: list[str]
    out: str
    note: str


def _reframe_step(sheet: DeliverySheet, output: _Output, j: int | None, video_in: list[str], paths: _Paths) -> _ReframeStep:
    platform, reframe = output.platform, output.reframe
    name = f"cut{output.index:02d}" + (f".e{j:02d}" if j is not None else "") + f".{platform.id}.mp4"
    out = os.path.join(paths.work, name)
    argv = [
        "-y", *video_in,
        "-filter_complex", reframe.graph, "-map", "[v]", "-frames:v", str(output.cut.frames(sheet.fps)),
        *_picture_encode(platform, sheet.fps),
        "-an", *CLEAN_OUTPUT,
        _arg(out),
    ]
    return _ReframeStep(argv, out, f"{output.out}: the picture for {platform.id} -- {reframe.describe()}")


@dataclass(frozen=True)
class _Pictures:
    """Every output's picture: the steps that join the card and ending cuts,
    the steps that fit a picture to its platform, and each output's picture
    as ffmpeg input arguments, in output order."""

    cards: dict[int, _CardSteps]  # by the cut's position in the sheet, from 1
    joins: dict[int, _EndingSteps]
    inputs: list[list[str]]
    reframes: dict[int, _ReframeStep] = field(default_factory=dict)  # by the output's position, from 0

    @property
    def intermediates(self) -> list[str]:
        made = [p for steps in (*self.cards.values(), *self.joins.values()) for p in steps.intermediates]
        return made + [step.out for step in self.reframes.values()]


def _pictures(sheet: DeliverySheet, paths: _Paths, endings: dict[int, _Endings], outputs: list[_Output]) -> _Pictures:
    cards, joins = {}, {}
    for i, cut in enumerate(sheet.cuts, 1):
        if i in endings:
            joins[i] = _ending_steps(sheet, cut, i, paths, endings[i])
        elif cut.card:
            cards[i] = _card_steps(sheet, cut, i, paths)
    inputs, reframes = [], {}
    for k, output in enumerate(outputs):
        j = None
        if output.ending is None:
            video_in = _video_input(sheet, output.cut, paths, cards.get(output.index))
        else:
            j = endings[output.index].endings.index(output.ending) + 1
            video_in = ["-i", _arg(joins[output.index].joins[j - 1].joined)]
        if output.reframe is not None:
            reframes[k] = _reframe_step(sheet, output, j, video_in, paths)
            video_in = ["-i", _arg(reframes[k].out)]
        inputs.append(video_in)
    return _Pictures(cards, joins, inputs, reframes)


# --------------------------------------------------------------------------
# the real run
# --------------------------------------------------------------------------
def deliver(
    sheet_path: str, *, out_dir: str | None = None, log: Callable[[str], None] | None = None
) -> Delivery:
    """Cut, gain and mux every deliverable in the sheet, holding every one
    under the true-peak ceiling -- and to its platform, before and after;
    make its covers; measure what was written if `check` is on; write the
    manifest. Returns one Delivered per video file, in sheet order -- a cut
    with endings gives one per ending, each carrying the cut's contact sheet,
    and a cut with platforms one per platform -- with the covers and the
    manifest's path alongside (Delivery)."""
    sheet = load_sheet(sheet_path)
    paths = _paths(sheet_path, out_dir)
    say = log or (lambda _msg: None)
    endings = _resolve_endings(sheet, paths)
    outputs = _outputs(sheet, endings)
    planned = _plan_findings(sheet, outputs)
    _refuse_planned(outputs, planned)
    covers = _cover_plans(sheet)
    ffmpeg = require_ffmpeg() if outputs else ""
    for warning in _preflight(sheet, paths, endings, ffmpeg, covers):
        say(f"warning: {warning}")
    for output, findings in zip(outputs, planned):
        for finding in findings:
            say(finding_line(output.out, finding))

    voiced = [k for k, output in enumerate(outputs) if output.has_audio]
    plan = None
    if voiced:
        audio = paths.src(sheet.audio)
        plan = plan_gain(sheet, measure_master(ffmpeg, sheet, audio))
        say(_describe_plan(sheet, plan))
        for warning in (*plan.warnings, *_edge_warnings(sheet, paths, plan.start.gain_db)):
            say(f"warning: {warning}")

    results = [
        Delivered(
            out=paths.out(o.out),
            frames_expected=o.cut.frames(sheet.fps),
            mode=sheet.gain.mode if o.has_audio else "none",
            has_audio=o.has_audio,
            cut=o.cut.label if o.ending or o.platform else None,
            ending=o.ending.name if o.ending else None,
            platform=o.platform.id if o.platform else None,
            picture="copy" if o.reframe is None else o.reframe.how,
        )
        for o in outputs
    ]
    pictures = _pictures(sheet, paths, endings, outputs)
    try:
        for output in outputs:
            os.makedirs(os.path.dirname(paths.out(output.out)) or ".", exist_ok=True)
        if pictures.cards or pictures.joins or pictures.reframes:
            os.makedirs(paths.work, exist_ok=True)
        for i, cut in enumerate(sheet.cuts, 1):
            card, joins = pictures.cards.get(i), pictures.joins.get(i)
            if card is not None:
                run(ffmpeg, card.tail)
                Path(card.list_path).write_text(card.listing, encoding="utf-8")
                run(ffmpeg, card.concat)
            if joins is not None:
                say(f"{cut.label}: the body and each of {len(joins.joins)} endings, joined by stream copy")
                if joins.tail is not None:
                    run(ffmpeg, joins.tail)
                for join in joins.joins:
                    Path(join.list_path).write_text(join.listing, encoding="utf-8")
                    run(ffmpeg, join.concat)
        for step in pictures.reframes.values():
            say(step.note)
            run(ffmpeg, step.argv)

        for k, output in enumerate(outputs):
            if not output.has_audio:
                say(f"[{k + 1}/{len(outputs)}] {output.out} (no audio)")
                run(ffmpeg, _silent_argv(sheet, output.cut, pictures.inputs[k], results[k].out))

        if plan is not None:
            _deliver_voiced(ffmpeg, sheet, paths, plan, outputs, voiced, pictures.inputs, results, say)

        for i, cut in enumerate(sheet.cuts, 1):
            if i in endings:
                made = _make_contact_sheet(ffmpeg, _contact_sheet_steps(sheet, cut, paths, endings[i]))
                for k, output in enumerate(outputs):
                    if output.index == i:
                        results[k].contact_sheet = made
                say(made.describe())
    finally:
        for path in pictures.intermediates:
            if os.path.exists(path):
                os.remove(path)
        _remove_work_dir(paths)
    made_covers = []
    if covers:
        portrait = paths.src(sheet.covers.portrait) if sheet.covers.portrait else None
        made_covers = matrix.make_covers(
            covers, paths.src(sheet.covers.master), portrait, paths.out, say, sheet.covers.background or matrix.WHITE
        )
    if sheet.check:
        for result in results:
            _measure_delivered(result)
    for k, output in enumerate(outputs):
        results[k].findings = _delivered_findings(output, results[k], planned[k])
    manifest = paths.out(manifest_name(sheet))
    document = _manifest(sheet, sheet_path, outputs, planned, covers, results=results, made=made_covers, gain=plan)
    os.makedirs(os.path.dirname(manifest) or ".", exist_ok=True)
    Path(manifest).write_text(_manifest_text(document), encoding="utf-8")
    return Delivery(results, made_covers, manifest)


def finding_line(out: str, finding: pf.Finding) -> str:
    """A finding as a report line: `warning: <file> (<platform>): ...`."""
    level = "warning" if finding.level == "warn" else finding.level
    return f"{level}: {os.path.basename(out)} ({finding.platform}): {finding.message}"


def _cover_plans(sheet: DeliverySheet) -> list[matrix.CoverPlan]:
    if sheet.covers is None:
        return []
    return matrix.plan_covers(
        sheet.covers.platforms, lambda pid: cover_name(sheet, pid), portrait=sheet.covers.portrait is not None
    )


def _delivered_findings(output: _Output, result: Delivered, planned: list[pf.Finding]) -> list[pf.Finding]:
    """An output held to its platform as written: every rule whose value was
    measured, on the measurement; the rest -- and how the picture was made
    -- as planned. Its length is its frame count at its rate: exact, where
    a container's duration is its longer stream's."""
    if output.platform is None:
        return []
    seconds = result.frames / result.fps if result.frames and result.fps else None
    file_mb = result.size_bytes / pf.MB if result.size_bytes is not None else None
    audio = result.audio_stream if result.audio_stream is not None else (True if result.lufs is not None else None)
    measured = pf.check_video(
        output.platform, result.width, result.height, result.fps, seconds, audio, file_mb, lufs=result.lufs
    )
    known = set()
    for rules, value in (
        (("size", "aspect"), result.width if result.height is not None else None),
        (("length",), seconds),
        (("bitrate",), file_mb if seconds else None),
        (("frame rate",), result.fps),
        (("audio",), audio),
        (("file size",), file_mb),
        (("loudness",), result.lufs),
    ):
        if value is not None:
            known.update(rules)
    return [f for f in planned if f.rule not in known] + measured


def _make_contact_sheet(ffmpeg: str, steps: _SheetSteps) -> ContactSheet:
    """The contact sheet, labelled where this ffmpeg can draw text, and
    unlabelled -- saying why -- where it can't: no drawtext filter, or one
    that fails (no font to draw with)."""
    note = "this ffmpeg has no drawtext filter"
    if "text" in filter_options(ffmpeg, "drawtext"):
        try:
            run(ffmpeg, steps.labelled)
            return ContactSheet(steps.out, steps.names, steps.frames, labelled=True)
        except RuntimeError as exc:
            said = [line.strip() for line in str(exc).splitlines() if line.strip()]
            why = next((line for line in said if "drawtext" in line.lower() or "font" in line.lower()), said[-1])
            note = f"this ffmpeg's drawtext failed ({why})"
    run(ffmpeg, steps.unlabelled)
    return ContactSheet(steps.out, steps.names, steps.frames, labelled=False, note=note)


def _deliver_voiced(
    ffmpeg: str,
    sheet: DeliverySheet,
    paths: _Paths,
    plan: GainPlan,
    outputs: list[_Output],
    voiced: list[int],
    video_in: list[list[str]],
    results: list[Delivered],
    say: Callable[[str], None],
) -> None:
    """Every output with audio, at the master's one setting, through the guard."""
    audio = paths.src(sheet.audio)
    latency = isinstance(sheet.gain, LoudnessGain) and "latency" in filter_options(ffmpeg, "alimiter")

    def encode(k: int, setting: Setting) -> None:
        i = voiced[k]
        output = outputs[i]
        say(f"[{i + 1}/{len(outputs)}] {output.out}")
        limiter = limiter_filter(setting.limiter_dbfs, latency) if setting.limiter_dbfs is not None else None
        gain = f"{setting.gain_db:.2f}"
        run(ffmpeg, _encode_argv(sheet, output.cut, video_in[i], audio, results[i].out, gain, limiter))

    def measure(k: int) -> tuple[float, float]:
        return parse_ebur128(run_measure(ffmpeg, _ebur128_argv(results[voiced[k]].out)))

    def again(finished: Round, following: Setting) -> None:
        worst = max(range(len(voiced)), key=lambda k: finished.measured[k][1])
        say(
            f"{outputs[voiced[worst]].out} peaked at {finished.worst:+.1f} dBTP, over the "
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
        if not cut.voiced:
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
                warnings.append(f"{cut.label}: couldn't read the audio at its {where} to check it is silent ({exc})")
                continue
            if level > NEAR_SILENT_DBFS:
                warnings.append(
                    f"{cut.label}: {name} is 0 and the audio at its {where} peaks at {level:.1f} dBFS, not "
                    f"silence -- that edge clicks (every loop, where a platform loops it). Leave {name} "
                    f"out for the default {default * 1000:g} ms, or cut where the song is silent."
                )
    return warnings


def _int(text: str | None) -> int | None:
    return int(text) if text and text.strip().isdigit() else None


def _measure_delivered(result: Delivered) -> None:
    """Frames, duration, size, frame rate, whether it has audio, and bytes
    of what was written -- measured on the file, because the file is what
    ships. Its loudness and true peak were measured by the guard, on the
    same file."""
    packets = probe_stream(result.out, "v:0", "nb_read_packets", count_packets=True)
    result.frames = int(packets) if packets and packets.isdigit() else None
    result.duration = probe_duration(result.out)
    result.size_bytes = os.path.getsize(result.out)
    result.size_mb = round(result.size_bytes / 1048576, 1)
    # One ffprobe for three entries: it prints them in its own order, which
    # is this one.
    entries = (probe_stream(result.out, "v:0", "width,height,r_frame_rate") or "").split(",")
    if len(entries) == 3:
        result.width, result.height, result.fps = _int(entries[0]), _int(entries[1]), _rate(entries[2])
    if result.frames is not None:  # ffprobe answers: an audio stream is there, or it isn't
        result.audio_stream = probe_stream(result.out, "a:0", "codec_name") is not None


def _preflight(
    sheet: DeliverySheet,
    paths: _Paths,
    endings: dict[int, _Endings],
    ffmpeg: str,
    covers: list[matrix.CoverPlan] | None = None,
) -> list[str]:
    """Everything that can be checked before a minute of encoding is spent.

    All problems at once, not the first one: a sheet usually has several
    cuts, and fixing them one failed run at a time is how an afternoon goes.
    Returns the warnings -- things that deliver, but not perfectly.
    """
    voiced = any(cut.voiced for cut in sheet.cuts)
    framed = len(endings) < len(sheet.cuts)  # some cut is cut from the silent render
    silent = paths.src(sheet.silent) if framed else None
    audio = paths.src(sheet.audio) if voiced else None
    parts = [path for joined in endings.values() for path in (joined.body, *(e.file for e in joined.endings))]
    pictures = [
        *([paths.src(sheet.covers.master)] if covers else []),
        *([paths.src(sheet.covers.portrait)] if covers and sheet.covers.portrait else []),
    ]
    inputs = [
        *([silent] if silent else []), *([audio] if audio else []),
        *(paths.src(c.card) for c in sheet.cuts if c.card), *parts, *pictures,
    ]
    for path in inputs:
        if not os.path.exists(path):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)

    problems, warnings = [], []
    if covers:
        portrait = paths.src(sheet.covers.portrait) if sheet.covers.portrait else None
        problems += matrix.check_sources(covers, paths.src(sheet.covers.master), portrait)
    frame = 1.0 / sheet.fps
    if silent and sheet.frame is not None:
        problems += _size_problems(sheet, "the silent render", silent)
    silent_dur = probe_duration(silent) if silent else None
    audio_dur = probe_duration(audio) if audio else None
    keyframes = probe_keyframes(silent) if silent else None
    unkeyed = between = False
    for i, cut in enumerate(sheet.cuts, 1):
        end = cut.t0 + cut.dur
        joined = endings.get(i)
        if joined is None and silent_dur is not None and end > silent_dur + frame:
            problems.append(f"{cut.label}: ends at {end:.3f} s, past the end of the silent render ({silent_dur:.3f} s)")
        if cut.voiced:
            # The audio is on the song's clock, the picture on the render's.
            song_t0 = _song_t0(sheet, cut)
            song_end = sheet.silent_start + end
            if song_t0 + cut.dur <= 0:
                problems.append(
                    f"{cut.label}: its audio, song time {song_t0:.3f} to {song_t0 + cut.dur:.3f} s, is all before "
                    f"the song starts (silent_start {sheet.silent_start:g}) -- `audio: none` delivers it silent"
                )
            elif audio_dur is not None and song_end > audio_dur + 0.05:
                at = f"{end:.3f} s"
                if sheet.silent_start:
                    at = f"song time {song_end:.3f} s (silent_start {sheet.silent_start:g} + {end:.3f})"
                problems.append(f"{cut.label}: its audio ends at {at}, past the end of the audio ({audio_dur:.3f} s)")
        if joined is not None:
            found, cautions = _endings_checks(ffmpeg, sheet, paths, cut, joined)
            problems += found
            warnings += cautions
        else:
            start = cut.video_from if cut.card else cut.t0
            if keyframes is not None and start > 0 and not any(abs(k - start) < frame / 2 for k in keyframes):
                before = max((k for k in keyframes if k < start), default=0.0)
                after = min((k for k in keyframes if k > start), default=None)
                nearest = f"{before:.3f} s" + (f" / {after:.3f} s" if after is not None else "")
                problems.append(
                    f"{cut.label}: the film cut starts at {start:.3f} s, but the silent render has no keyframe "
                    f"there (nearest: {nearest})"
                )
                unkeyed = True
            end_at = _cut_end(cut, sheet.fps)
            before_the_end = silent_dur is None or end_at < silent_dur - frame / 2
            if keyframes is not None and before_the_end and not any(abs(k - end_at) < frame / 2 for k in keyframes):
                warnings.append(
                    f"{cut.label}: ends at {end_at:.3f} s, between keyframes -- its last frame can come out "
                    f"of B-frame order. A keyframe forced there too makes the cut exact."
                )
                between = True
        if cut.card:
            if sheet.frame is not None and joined is None:
                problems += [f"{cut.label}: {p}" for p in _size_problems(sheet, "the card", paths.src(cut.card))]
            want = cut.card_frames(sheet.fps)
            got = probe_stream(paths.src(cut.card), "v:0", "nb_read_packets", count_packets=True)
            if got and got.isdigit() and int(got) != want:
                problems.append(
                    f"{cut.label}: the card has {got} frames, but {cut.t0:g}..{cut.video_from:g} s at "
                    f"{sheet.fps:g} fps needs {want} -- the film would land {int(got) - want:+d} frames "
                    f"off its audio"
                )
    if problems:
        hint = ""
        if unkeyed:
            hint = (
                "\nRe-render the silent video with a keyframe at every cut point, e.g.\n"
                f"  -force_key_frames {_keyframe_list(sheet)}"
            )
        raise ValueError("the sheet can't be delivered as it stands:\n  " + "\n  ".join(problems) + hint)
    if between:
        warnings.append(f"keyframes for every cut point: -force_key_frames {_keyframe_list(sheet)}")
    return warnings


def _size_problems(sheet: DeliverySheet, what: str, path: str) -> list[str]:
    """A picture that isn't the size the sheet says the render is (`size`):
    the platforms' files are planned from that size."""
    width, height = _int(probe_stream(path, "v:0", "width")), _int(probe_stream(path, "v:0", "height"))
    if width is None or height is None or (width, height) == sheet.frame:
        return []
    return [f"{what} ({os.path.basename(path)}) is {width}x{height}; the sheet's size is {sheet.size}"]


def _endings_checks(
    ffmpeg: str, sheet: DeliverySheet, paths: _Paths, cut: CutConfig, joined: _Endings
) -> tuple[list[str], list[str]]:
    """A cut's body and endings, probed before anything is joined: each has
    the frames its span needs, each starts on a keyframe (and the body has
    one where a card ends), and every part -- the card's too -- is the same
    encode. Returns (problems, warnings)."""
    frame = 1.0 / sheet.fps
    card = [("the card", paths.src(cut.card))] if cut.card else []
    endings = [(f"ending {e.name!r}", e.file, e.frames) for e in joined.endings]
    parts = [*card, ("the body", joined.body), *((what, path) for what, path, _ in endings)]
    problems = []
    for what, path, want in (("the body", joined.body, joined.frames), *endings):
        got = probe_stream(path, "v:0", "nb_read_packets", count_packets=True)
        if got and got.isdigit() and int(got) != want:
            problems.append(f"{cut.label}: {what} ({os.path.basename(path)}) has {got} frames; its span needs {want}")
    for what, path in parts:
        keyframes = probe_keyframes(path)
        if keyframes is not None and not any(abs(k - _start_time(path)) < frame / 2 for k in keyframes[:1]):
            first = f"its first is {keyframes[0] - _start_time(path):.3f} s in" if keyframes else "it has none"
            problems.append(
                f"{cut.label}: {what} ({os.path.basename(path)}) doesn't start on a keyframe ({first}) -- a "
                f"stream-copied join can only begin a part on one"
            )
    if cut.card:
        resume = round((cut.video_from - cut.t0) * sheet.fps) / sheet.fps  # on the body's own clock
        keyframes = probe_keyframes(joined.body)
        at = _start_time(joined.body) + resume
        if keyframes is not None and not any(abs(k - at) < frame / 2 for k in keyframes):
            problems.append(
                f"{cut.label}: the body has no keyframe at {resume:.3f} s, where the card ends and the body "
                f"resumes -- render the body with one there"
            )
    probed = [(what, path, {key: probe_stream(path, "v:0", key) for key in _STREAM_PARAMS}) for what, path in parts]
    first_what, first_path, first = probed[0]
    rate = _rate(first["r_frame_rate"])
    if rate is not None and abs(rate - sheet.fps) > 1e-3 * sheet.fps:
        problems.append(
            f"{cut.label}: {first_what} ({os.path.basename(first_path)}) runs at {first['r_frame_rate']} fps; "
            f"the sheet's fps is {sheet.fps:g}"
        )
    size = (_int(first["width"]), _int(first["height"]))
    if sheet.frame is not None and None not in size and size != sheet.frame:
        problems.append(
            f"{cut.label}: {first_what} ({os.path.basename(first_path)}) is {size[0]}x{size[1]}; the sheet's "
            f"size is {sheet.size}"
        )
    for what, path, params in probed[1:]:
        differ = [
            f"{key} {params[key]}, not {first[key]}"
            for key in _STREAM_PARAMS
            if params[key] is not None and first[key] is not None and params[key] != first[key]
        ]
        if differ:
            problems.append(
                f"{cut.label}: {what} ({os.path.basename(path)}) isn't the same encode as {first_what}: "
                f"{'; '.join(differ)}"
            )
    warnings = []
    if not problems:
        headers = [(what, path, _parameter_sets(ffmpeg, path)) for what, path in parts]
        first_what, _, first_headers = headers[0]
        for what, path, fields in headers[1:]:
            differ = _header_difference(first_headers, fields) if first_headers and fields else None
            if differ:
                warnings.append(
                    f"{cut.label}: {what} ({os.path.basename(path)}) was encoded with other settings than "
                    f"{first_what}: their stream headers differ ({differ}). The join carries each part's own "
                    f"headers, which ffmpeg decodes, but a player that reads only the file's first ones may "
                    f"not -- render every part with the same encoder settings."
                )
    return problems, warnings


def _start_time(path: str) -> float:
    """When the first frame is presented, in the file's own seconds (0 unless it says otherwise)."""
    try:
        return float(probe_stream(path, "v:0", "start_time") or 0.0)
    except ValueError:
        return 0.0


def _rate(text: str | None) -> float | None:
    """ffprobe's `24/1`, `30000/1001` as frames per second; None if it isn't one."""
    num, _, den = (text or "").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None


_TRACE_FIELD = re.compile(r"\]\s+\d+\s+(\S+)\s+[01]+\s+=\s+(-?\d+)\s*$")


def _parameter_sets(ffmpeg: str, path: str) -> list[tuple[str, str]] | None:
    """A video stream's own headers -- H.264's SPS and PPS -- field by field,
    as ffmpeg's trace_headers bitstream filter reads them from the file; None
    where it can't (a codec it doesn't parse, an ffmpeg without it).

    Two parts made with different encoder settings can agree on every
    stream parameter above and still differ here: an x264 CRF sets the PPS's
    pic_init_qp. ffmpeg 6.1's concat demuxer carried a CRF-30 ending's own
    headers into the joined file in-band, and ffmpeg decoded it
    frame-identically (measured, synthetic parts) -- but the MP4's sample
    description keeps only the first part's, and a player that reads only
    those would decode the ending with the wrong ones (inferred). Hence a
    warning, not a refusal."""
    try:
        log = run_measure(
            ffmpeg,
            ["-i", _arg(path), "-map", "0:v:0", "-c:v", "copy", "-bsf:v", "trace_headers",
             "-frames:v", "1", "-f", "null", "-"],
        )
    except RuntimeError:
        return None
    head = log.partition("] Extradata")[2].partition("] Packet:")[0]
    fields = [m.groups() for m in map(_TRACE_FIELD.search, head.splitlines()) if m]
    return fields or None


def _header_difference(first: list[tuple[str, str]], other: list[tuple[str, str]]) -> str | None:
    """The first header field two parts disagree on, in words; None if none."""
    for (name, value), (other_name, other_value) in zip(first, other):
        if name != other_name:
            return f"{other_name} where the first has {name}"
        if value != other_value:
            return f"{name} {other_value}, not {value}"
    if len(first) != len(other):
        return f"{len(other)} header fields, not {len(first)}"
    return None


def _cut_end(cut: CutConfig, fps: float) -> float:
    """The time of the first frame after the cut -- where its GOP should end."""
    return (round(cut.t0 * fps) + cut.frames(fps)) / fps


def _keyframe_list(sheet: DeliverySheet) -> str:
    """Every point a cut starts, resumes or ends at -- the argument the
    silent render needs (see the module docstring for why ends too). A cut
    with endings isn't cut from it: its parts bring their own keyframes."""
    points = {0.0}
    for cut in sheet.cuts:
        if cut.endings is not None:
            continue
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
    sheets: list[ContactSheet] = []
    for r in results:
        if r.contact_sheet is not None and r.contact_sheet not in sheets:
            sheets.append(r.contact_sheet)
    findings = [finding_line(r.out, f) for r in results for f in r.findings]
    return "\n".join(lines + [s.describe() for s in sheets] + [f"warning: {w}" for w in warnings] + findings)


# --------------------------------------------------------------------------
# the manifest: <title>.delivery.json, next to the files
# --------------------------------------------------------------------------
def _jnum(x: float | None, digits: int = 3) -> float | None:
    """A number for JSON: rounded, and None where it isn't finite -- silence measures -inf LUFS."""
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), digits)


def _pair(size: tuple[int, int] | None) -> list[int] | None:
    return None if size is None else list(size)


def _picture_block(output: _Output) -> dict:
    r = output.reframe
    if r is None:
        return {"how": "copy"}
    return {"how": r.how, "from": _pair(r.source), "to": _pair(r.target), "drawn": _pair(r.drawn)}


def _video_artifact(sheet: DeliverySheet, output: _Output, planned: list[pf.Finding], r: Delivered | None) -> dict:
    cut = output.cut
    size = output.reframe.target if output.reframe is not None else sheet.frame
    measured = None
    if r is not None:
        measured = {
            "width": r.width, "height": r.height, "fps": _jnum(r.fps), "frames": r.frames,
            "seconds": _jnum(r.frames / r.fps) if r.frames and r.fps else None, "duration": _jnum(r.duration),
            "audio": r.audio_stream, "lufs": _jnum(r.lufs, 2), "true_peak_dbtp": _jnum(r.true_peak, 2),
            "bytes": r.size_bytes, "mb": _jnum(r.size_bytes / pf.MB, 2) if r.size_bytes is not None else None,
        }
    return {
        "file": output.out,
        "kind": "video",
        "cut": cut.label,
        "platform": output.platform.id if output.platform else None,
        "ending": output.ending.name if output.ending else None,
        "picture": _picture_block(output),
        "planned": {
            "width": size[0] if size else None, "height": size[1] if size else None, "fps": _jnum(sheet.fps),
            "frames": cut.frames(sheet.fps), "seconds": _jnum(_seconds(cut, sheet.fps)), "audio": output.has_audio,
            "t0": _jnum(cut.t0),
        },
        "measured": measured,
        "findings": [f.to_dict() for f in (r.findings if r is not None else planned)],
    }


def _cover_artifact(plan: matrix.CoverPlan, cover: matrix.Cover | None) -> dict:
    p = plan.platform
    measured = None
    if cover is not None:
        measured = {
            "width": cover.width, "height": cover.height, "bytes": cover.size_bytes,
            "mb": _jnum(cover.file_mb, 2), "jpeg_quality": cover.quality,
        }
    return {
        "file": plan.out,
        "kind": "image",
        "platform": p.id,
        "source": plan.source,
        "method": plan.method,
        "preview": plan.preview,
        "planned": {"width": p.width, "height": p.height, "jpeg_quality": p.jpeg_quality},
        "measured": measured,
        "findings": [f.to_dict() for f in (cover.findings if cover is not None else [])],
    }


def _master_block(sheet: DeliverySheet, results: list[Delivered] | None, gain: GainPlan | None) -> dict | None:
    if sheet.audio is None:
        return None
    voiced = [r for r in results or () if r.has_audio]
    used = voiced[0] if voiced else None
    return {
        "file": os.path.basename(sheet.audio),
        "mode": sheet.gain.mode,
        "lufs": _jnum(gain.master.lufs, 2) if gain else None,
        "true_peak_dbtp": _jnum(gain.master.true_peak, 2) if gain else None,
        "gain_db": used.gain_db if used else None,
        "limiter_dbfs": used.limiter_dbfs if used else None,
        "ceiling_dbtp": gain.ceiling if gain else None,
    }


def _manifest(
    sheet: DeliverySheet,
    sheet_path: str,
    outputs: list[_Output],
    planned: list[list[pf.Finding]],
    covers: list[matrix.CoverPlan],
    *,
    results: list[Delivered] | None = None,
    made: list[matrix.Cover] | None = None,
    gain: GainPlan | None = None,
) -> dict:
    """The delivery as data: every artifact with its platform, what was
    planned and -- once delivered -- what was measured on the file, and the
    findings; every platform's spec once, by id. Planned (--dry-run) when
    `results` is None."""
    artifacts = [
        _video_artifact(sheet, output, planned[k], results[k] if results is not None else None)
        for k, output in enumerate(outputs)
    ]
    made_by = {cover.platform: cover for cover in made or ()}
    artifacts += [_cover_artifact(plan, made_by.get(plan.platform.id)) for plan in covers]
    ids = list(dict.fromkeys(a["platform"] for a in artifacts if a["platform"] is not None))
    render = None
    if sheet.cuts:
        render = {
            "file": os.path.basename(sheet.silent) if sheet.silent else None, "size": _pair(sheet.frame),
            "fps": _jnum(sheet.fps), "song_time": _jnum(sheet.silent_start),
        }
    return {
        "manifest": MANIFEST_VERSION,
        "kaleidophone": __version__,
        "state": "planned" if results is None else "delivered",
        "title": sheet.title,
        "sheet": os.path.basename(sheet_path),
        "render": render,
        "master": _master_block(sheet, results, gain),
        "findings": {level: sum(f["level"] == level for a in artifacts for f in a["findings"]) for level in pf.LEVELS},
        "artifacts": artifacts,
        "platforms": {pid: pf.get(pid).to_dict() for pid in ids},
    }


def _manifest_text(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


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
    "drawtext": """\
# Whether this ffmpeg can label a contact sheet with the endings' names (drawtext); if it can't, or
# drawing fails, the sheet is made unlabelled and says so.
if ffmpeg -hide_banner -nostdin -h filter=drawtext 2>/dev/null </dev/null | grep -q '^ *text  *<'; then
  DRAWTEXT=1
else
  DRAWTEXT=0
fi""",
    "fits": """\
# Whether a delivered file is under its platform's file limit ($3, refused over it) and its softer one
# ($4, a warning) -- MB of 10^6 bytes; '' for none.
fits() {
  s=$(wc -c < "$1")
  m=$(awk -v s="$s" 'BEGIN { printf "%.2f", s / 1000000 }')
  if [ -n "$3" ] && awk -v s="$s" -v l="$3" 'BEGIN { exit !(s > l * 1000000) }'; then
    printf 'refuse: %s (%s): %s MB is over the %s MB it takes\\n' "$1" "$2" "$m" "$3" >&2
    REFUSED=1
  elif [ -n "$4" ] && awk -v s="$s" -v l="$4" 'BEGIN { exit !(s > l * 1000000) }'; then
    printf 'warning: %s (%s): %s MB is over %s MB\\n' "$1" "$2" "$m" "$4" >&2
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
    true-peak guard's rounds, measured by the script itself. A cut's endings
    are read from its variants manifest here -- the manifest has to exist,
    the render doesn't. The platforms are held to the plan here, and the
    script writes the planned manifest; the covers are Pillow's work, so it
    lists them there and leaves them to `kaleidophone deliver`.
    """
    sheet = load_sheet(sheet_path)
    paths = _paths(sheet_path, out_dir)
    loudness = isinstance(sheet.gain, LoudnessGain)
    endings = _resolve_endings(sheet, paths)
    outputs = _outputs(sheet, endings)
    planned = _plan_findings(sheet, outputs)
    _refuse_planned(outputs, planned)
    covers = _cover_plans(sheet)
    voiced = [(k, output) for k, output in enumerate(outputs, 1) if output.has_audio]
    limited = [o for o in outputs if o.platform and (o.platform.max_file_mb or o.platform.recommended_max_file_mb)]

    needed = []
    if voiced:
        needed += ["master", *(["gain_to"] if loudness else []), "truepeak", *(["limiter"] if loudness else [])]
    if endings:
        needed.append("drawtext")
    if sheet.check:
        needed += ["check", *(["fits"] if limited else [])]

    manifest = paths.out(manifest_name(sheet))
    out_dirs = sorted(({os.path.dirname(paths.out(o.out)) for o in outputs} | {os.path.dirname(manifest)}) - {""})
    pictures = _pictures(sheet, paths, endings, outputs)
    lines = [
        "#!/bin/sh",
        _comment(f"# kaleidophone deliver -- {os.path.basename(sheet_path)}, printed by --dry-run."),
        "# Every path is relative to the directory kaleidophone ran in: run this from there.",
    ]
    if len(endings) < len(sheet.cuts):
        lines += [
            "# The silent render needs a keyframe wherever a cut starts (or it can't be stream-copied)",
            "# and wherever one ends (or its last frame can come out of B-frame order):",
            f"#   -force_key_frames {_keyframe_list(sheet)}",
        ]
    if endings:
        lines += [
            "# A cut with endings is its body and each ending, joined by stream copy: every part the same",
            "# encode, each starting on a keyframe (render.mjs --endings writes them so).",
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
    lines += [_comment(f"# {finding_line(o.out, f)}") for o, fs in zip(outputs, planned) for f in fs]
    if covers:
        lines.append(
            f"# {len(covers)} cover{'' if len(covers) == 1 else 's'}, in the manifest: made by `kaleidophone deliver` "
            f"(Pillow), not by this script."
        )
    lines.append("set -e")
    made = out_dirs + ([paths.work] if pictures.cards or pictures.joins or pictures.reframes else [])
    if made:
        lines.append("mkdir -p -- " + " ".join(shlex.quote(d) for d in made))
    document = _manifest_text(_manifest(sheet, sheet_path, outputs, planned, covers))
    lines += [
        "# The delivery as planned; `kaleidophone deliver` writes it with what it measured.",
        f"cat > {shlex.quote(manifest)} <<'{_MANIFEST_END}'",
        document.rstrip("\n"),
        _MANIFEST_END,
        "",
    ]
    for name in needed:
        lines += [_SCRIPT_HELPERS[name], ""]

    if voiced:
        lines += _script_master(sheet, paths)

    for i, cut in enumerate(sheet.cuts, 1):
        card, joins = pictures.cards.get(i), pictures.joins.get(i)
        if card is not None:
            lines += [
                _comment(f"# the card cut {cut.label}: the film from its keyframe at {cut.video_from:g} s, behind the card"),
                _command(card.tail),
                f"cat > {shlex.quote(card.list_path)} <<'EOF'",
                card.listing.rstrip("\n"),
                "EOF",
                _command(card.concat),
                "",
            ]
        if joins is not None:
            head = f"the card, the body from its keyframe at {cut.video_from - cut.t0:g} s" if cut.card else "the body"
            lines.append(_comment(f"# the endings of {cut.label}: {head}, then each ending, joined by stream copy"))
            if joins.tail is not None:
                lines.append(_command(joins.tail))
            for join in joins.joins:
                lines += [
                    f"cat > {shlex.quote(join.list_path)} <<'EOF'",
                    join.listing.rstrip("\n"),
                    "EOF",
                    _command(join.concat),
                ]
            lines.append("")
    for step in pictures.reframes.values():
        lines += [_comment(f"# {step.note}"), _command(step.argv), ""]
    for k, output in enumerate(outputs, 1):
        if not output.has_audio:
            lines += [
                _output_comment(sheet, output, k, len(outputs), silent=True),
                _command(_silent_argv(sheet, output.cut, pictures.inputs[k - 1], paths.out(output.out))),
                "",
            ]
    if voiced:
        lines += _script_guard(sheet, paths, voiced, pictures.inputs, len(outputs))
    for i, cut in enumerate(sheet.cuts, 1):
        if i in endings:
            lines += _script_contact_sheet(_contact_sheet_steps(sheet, cut, paths, endings[i]))

    if pictures.intermediates:
        lines += [
            "rm -f -- " + " ".join(shlex.quote(p) for p in pictures.intermediates),
            f"rmdir -- {shlex.quote(paths.work)} 2>/dev/null || true",
            f"rmdir -- {shlex.quote(os.path.dirname(paths.work))} 2>/dev/null || true",
            "",
        ]
    if sheet.check and outputs:
        lines.append("# check what was delivered")
        lines += [
            f"check {_sh(_arg(paths.out(o.out)))} {o.cut.frames(sheet.fps)}" + ("" if o.has_audio else " silent")
            for o in outputs
        ]
        if limited:
            lines.append("REFUSED=")
            lines += [
                f"fits {_sh(_arg(paths.out(o.out)))} {o.platform.id} {_limit_arg(o.platform.max_file_mb)} "
                f"{_limit_arg(o.platform.recommended_max_file_mb)}"
                for o in limited
            ]
    if voiced:
        lines += ["", '[ -z "$FAILED" ] || exit 1']
    if sheet.check and limited:
        lines += ['[ -z "$REFUSED" ] || exit 1']
    return "\n".join(lines).rstrip("\n") + "\n"


# The manifest's here-document ends on a line no JSON line can be: every line
# of json.dumps(indent=2) is a bracket, or indented.
_MANIFEST_END = "KALEIDOPHONE_MANIFEST"


def _limit_arg(mb: float | None) -> str:
    """A file limit as the script's `fits` takes it: MB, or '' for none."""
    return "''" if mb is None else f"{mb:g}"


def _output_comment(sheet: DeliverySheet, output: _Output, index: int, total: int, *, silent: bool = False) -> str:
    cut = output.cut
    song_t0 = _song_t0(sheet, cut)
    song = f" (song {song_t0:.3f}-{song_t0 + cut.dur:.3f} s)" if sheet.silent_start and not silent else ""
    return _comment(
        f"# {index}/{total}  {output.out}: {cut.t0:.3f}-{cut.t0 + cut.dur:.3f} s{song}, "
        f"{cut.frames(sheet.fps)} frames"
        + (f", card until {cut.video_from:g} s" if cut.card else "")
        + (f", ending {output.ending.name}" if output.ending else "")
        + (f", for {output.platform.id}" if output.platform else "")
        + (", no audio" if silent else "")
    )


def _script_contact_sheet(steps: _SheetSteps) -> list[str]:
    """_make_contact_sheet() in sh: labelled if this ffmpeg can draw text,
    else unlabelled, and saying so."""
    name, rows = shlex.quote(os.path.basename(steps.out)), shlex.quote(", ".join(steps.names))
    return [
        _comment(
            f"# the endings side by side, one row per ending: the last body frame, then {steps.frames} "
            f"frame{'' if steps.frames == 1 else 's'} of the ending"
        ),
        f'if [ "$DRAWTEXT" = 1 ] && {_command(steps.labelled)}; then',
        f"  printf 'contact sheet %s: %s, top to bottom\\n' {name} {rows}",
        "else",
        "  " + _command(steps.unlabelled),
        f"  printf 'contact sheet %s: %s, top to bottom; unlabelled: this ffmpeg could not draw text\\n' {name} {rows}",
        "fi",
        "",
    ]


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
    voiced: list[tuple[int, _Output]],
    video_in: list[list[str]],
    total: int,
) -> list[str]:
    """master_guard() in sh: every cut at the master's setting, a round at a
    time, until the worst delivered true peak is under the ceiling. `voiced`
    is every output with audio, numbered from 1 among all `total`."""
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
    for k, output in voiced:
        out = paths.out(output.out)
        limiter = _LIMITER if loudness else None
        lines += [
            "  " + _output_comment(sheet, output, k, total),
            "  " + _command(_encode_argv(sheet, output.cut, video_in[k - 1], audio, out, _GAIN, limiter)),
            f"  P=$(truepeak {_sh(_arg(out))}); W=$(worst \"$W\" \"$P\" {_sh(_arg(out))})",
            f"  printf '%s: true peak %s dBTP\\n' {shlex.quote(output.out)} \"$P\"",
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
