"""Shared ffmpeg subprocess helpers, used across the package.

Everything here shells out to the system ffmpeg/ffprobe binaries rather than
depending on a Python video library -- see
docs/decisions/0002-deterministic-edit-engine.md. Helpers that are merely
*useful* (probe_duration, probe_stream, probe_keyframes, first_frame_png,
filter_options) degrade to None or nothing when the binary isn't there; only
the paths that cannot do their job without it -- the render, and decoding
audio for analysis -- call require_ffmpeg() and hard-fail.

Every subprocess call in the package lives in this module -- the
run-to-completion helpers below, and spawn() for the frame engine's decoder
and encoder, which stream for as long as a render lasts -- so there is one
place to check that nothing reaches a shell as a string (see SECURITY.md),
and one place that keeps ffmpeg off the terminal. tests/test_ffmpeg_util.py
checks the package's source for any other use.

No helper lets ffmpeg read the caller's stdin unless it is feeding it frames
itself: each passes /dev/null, and each ffmpeg command line carries
`-nostdin`. ffmpeg reads stdin for its interactive keys while it works, and
an inherited stdin is whatever the calling shell was reading next -- in
`printf 'first\\nsecond\\n' | while read x; do kaleidophone deliver ...; done`
the second iteration got "econd".
"""

from __future__ import annotations

import errno
import functools
import os
import re
import shutil
import subprocess
from typing import IO

# A bitrate as ffmpeg's -b:a / -maxrate / -bufsize take it: a number with an
# optional k/M suffix. The brief and the delivery sheet both validate against
# it, because the value goes straight into an argv (SECURITY.md).
BITRATE_RE = re.compile(r"^\d+(\.\d+)?[kKmM]?$")


class FfmpegNotFound(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FfmpegNotFound(
            "ffmpeg was not found on PATH. kaleidophone renders through the system ffmpeg "
            "binary rather than a Python dependency -- install it (e.g. `brew install "
            "ffmpeg` or `apt install ffmpeg`) and try again."
        )
    return path


def concat_quote(path: str) -> str:
    """Quote a path for ffmpeg's concat demuxer.

    The demuxer's own escaping rules, not the shell's: inside a single-quoted
    token a literal ' is written by closing the quote, emitting an escaped
    quote, and reopening. A list entry is re-parsed by the demuxer, so an
    apostrophe anywhere in the path -- a TMPDIR under "Dad's scratch", a
    card named "the artist's card.mp4" -- ends the token early without this.
    One definition for every concat list the package writes: the filter-graph
    render's segments, the frame engine's parts, and the delivery's card cuts.
    """
    return "'" + path.replace("'", "'\\''") + "'"


def run(ffmpeg: str, args: list[str]) -> None:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (args tail: {' '.join(args[-6:])}):\n{proc.stderr[-2000:]}")


def spawn(
    argv: list[str],
    *,
    feed_stdin: bool = False,
    read_stdout: bool = False,
    stderr: IO[bytes] | None = None,
) -> subprocess.Popen:
    """Start ffmpeg and return it still running.

    For a process that streams for as long as a render lasts, which run()'s
    run-to-completion can't: the frame engine's decoder (`read_stdout`, raw
    frames out) and encoder (`feed_stdin`, raw frames in). stdin is /dev/null
    unless the caller feeds it; stdout is /dev/null unless the caller reads
    it. stderr goes where the caller says -- a temporary file, because a pipe
    nobody drains blocks ffmpeg once it fills -- and to /dev/null otherwise.
    """
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise TypeError("spawn() takes an argument list, never a shell string")
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if feed_stdin else subprocess.DEVNULL,
        stdout=subprocess.PIPE if read_stdout else subprocess.DEVNULL,
        stderr=stderr if stderr is not None else subprocess.DEVNULL,
    )


def first_frame_png(path: str) -> bytes | None:
    """The first decodable frame of a video, as PNG bytes, or None.

    Used by asset curation and the contact-sheet preview to look at a clip
    without pulling in a second video-decoding stack -- ffmpeg is already a
    hard requirement of the render path, so a ~90MB OpenCV wheel to read one
    frame was the more expensive of the two options. Returns None (rather than
    raising) when ffmpeg is absent or the file won't decode: both callers have
    a "couldn't read this one" path already, and neither should abort a scan
    of several hundred files over one bad clip.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    proc = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", os.path.abspath(path),
            "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def probe_duration(path: str) -> float | None:
    """Duration of a media file in seconds, or None if it can't be determined.

    Best-effort on purpose: ffprobe normally ships alongside ffmpeg but isn't
    guaranteed to, and nothing in the render path should hard-fail because a
    *diagnostic* couldn't run.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def run_measure(ffmpeg: str, args: list[str]) -> str:
    """Run ffmpeg for a *measurement* and return its log (stderr).

    run() pins ffmpeg to `-loglevel error`, which is right for a render and
    wrong here: loudnorm and ebur128 report what they measured at the info
    level, so under run() the numbers would simply never arrive. `-nostats`
    drops the progress line, the only other thing info adds.
    """
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-nostdin", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (args tail: {' '.join(args[-6:])}):\n{proc.stderr[-2000:]}")
    return proc.stderr


@functools.lru_cache(maxsize=None)
def filter_options(ffmpeg: str, name: str) -> frozenset[str]:
    """The option names this ffmpeg's filter `name` accepts -- empty if it has
    no such filter, or can't say.

    Asked once per binary and filter (`ffmpeg -h filter=NAME`), for options
    that arrived in some ffmpeg versions and not others: alimiter's
    `latency`, which kaleidophone deliver uses where it exists (5.1 and
    later), is the reason this exists.
    """
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-h", f"filter={name}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
    except OSError:
        return frozenset()
    if proc.returncode != 0:
        return frozenset()
    return frozenset(re.findall(r"^\s+([A-Za-z_][\w-]*)\s+<\w+>", proc.stdout, re.MULTILINE))


def decode_f32le(
    path: str,
    *,
    sample_rate: int,
    channels: int,
    start: float | None = None,
    duration: float | None = None,
) -> bytes:
    """Decode any audio ffmpeg can read to raw little-endian float32 PCM.

    The analysis modules (audio/envelope.py, audio/mastercheck.py) work on
    numpy arrays, never on a file format. ffmpeg already reads everything a
    release hands over -- the WAV master, an mp3 draft, the audio track of a
    video -- so decoding goes through the binary the render path requires
    anyway, not a second decoding stack. Raw f32le on a pipe needs no temp
    file and no header to parse; the caller already knows the rate and the
    channel count, because it asked for them.

    `start` and `duration` (seconds) decode a window instead of the whole
    file -- an input seek, which is sample-exact for PCM.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
    ffmpeg = require_ffmpeg()
    window = []
    if start is not None and start > 0:
        window += ["-ss", f"{start:.6f}"]
    if duration is not None:
        window += ["-t", f"{duration:.6f}"]
    proc = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            # Absolute, so a file whose name begins with "-" can't be read as a flag.
            *window, "-i", os.path.abspath(path),
            "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-f", "f32le", "-",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg could not decode {path}:\n{stderr[-2000:]}")
    return proc.stdout


def probe_stream(path: str, stream: str, entry: str, *, count_packets: bool = False) -> str | None:
    """One `stream=<entry>` value of the first `stream` ("a:0", "v:0"), or None.

    Best-effort for the same reason as probe_duration(). `count_packets`
    makes ffprobe demux the whole file to fill `nb_read_packets` -- the only
    frame count that describes the file as written rather than as its header
    claims.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    args = [ffprobe, "-v", "error"]
    if count_packets:
        args.append("-count_packets")
    args += ["-select_streams", stream, "-show_entries", f"stream={entry}", "-of", "csv=p=0"]
    proc = subprocess.run(
        [*args, os.path.abspath(path)], stdin=subprocess.DEVNULL, capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    value = lines[0].strip().rstrip(",") if lines else ""
    return value or None


def probe_keyframes(path: str) -> list[float] | None:
    """Presentation times of every keyframe in the first video stream, or None.

    Reads packet flags rather than decoding, so it costs a demux, not a
    decode -- cheap enough to run before every delivery.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0",
            os.path.abspath(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    times = []
    for line in proc.stdout.splitlines():
        pts, _, flags = line.partition(",")
        if "K" not in flags:
            continue
        try:
            times.append(float(pts))
        except ValueError:
            continue
    return sorted(times)
