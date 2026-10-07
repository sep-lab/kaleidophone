"""
The frame-program runner: decode a clip window with ffmpeg, hand every frame
to a Python function, encode the result back through ffmpeg -- resumably.

render/ffmpeg_pipeline.py renders with ffmpeg filter graphs, and for most cuts
that is the right engine: fast, and a broken cut is a readable one-line error.
Two real releases needed effects that are per-pixel AND remember earlier
frames (see frames/effects.py), and both ended up hand-building this same loop
around ffmpeg. This module is that loop, with the parts that went wrong fixed
once:

- Decode once, then read sequentially. A window is opened with `-ss` before
  `-i` -- a keyframe jump plus a short decode-and-discard, ffmpeg's
  accurate-seek default -- and frames stream out of that one process as raw
  rgb24. Seeking per frame is the trap: in the real engine, per-frame seeks
  into 50p h264 ran at ~1.5 fps until the reader was made sequential.
- Encode to numbered part files and checkpoint between them. Every
  `checkpoint_every` frames, and when the wall-clock budget runs out, the
  current part is closed and the program's state saved to a .npz with the
  next frame index; the next call resumes there. The real renders ran on a
  4-core ARM VM under a 180 s limit per call, with background processes
  killed when the call returned -- a render that can't stop and resume can't
  finish there at all. The release ran each call with a 150 s budget: the
  encoder still has to flush after the last frame.
- Workers. run_workers() splits the frame range across N resumable jobs in
  parallel processes. Measured on a real release (that VM, 1080p): ~8.7 fps
  for one worker, ~13 fps aggregate with three.
- Concat without re-encoding. Every part of a job shares one encode setting,
  so concat_parts() joins them with the concat demuxer and `-c:v copy`; the
  song goes back on with render.ffmpeg_pipeline.mux_audio(), the same cheap
  half of the render split as the filter-graph engine (ADR-0001).

Every ffmpeg command line is built by a small function (decode_argv,
encode_argv, concat_args) so tests can assert on it without running ffmpeg,
and the decoder and encoder are injectable (open_source / open_sink) so the
checkpoint logic is testable with fakes.

FfmpegSource and FfmpegSink stream frames for as long as a render lasts,
which a run-to-completion call can't, so they start ffmpeg with
render/_ffmpeg_util.spawn() rather than run(). Like every other subprocess
call in the package, that lives in _ffmpeg_util: an argument list, never a
shell string (SECURITY.md), and stdin kept off the terminal.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import multiprocessing
import os
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Protocol

import numpy as np

from kaleidophone.render._ffmpeg_util import concat_quote, require_ffmpeg, run, spawn

__all__ = [
    "FfmpegSink",
    "FfmpegSource",
    "FrameSink",
    "FrameSource",
    "Program",
    "RenderJob",
    "RenderResult",
    "checkpoint_path",
    "concat_args",
    "concat_parts",
    "decode_argv",
    "encode_argv",
    "ffmpeg_sink",
    "ffmpeg_source",
    "job_parts",
    "job_status",
    "part_path",
    "plan_workers",
    "run_job",
    "run_workers",
    "split_frames",
    "write_concat_list",
]

# program(frame, t, env, state) -> frame. `frame` is float32 RGB (H, W, 3) in
# 0..1 and is the program's to modify; `t` is timeline seconds; `env` is
# read-only data shared by every frame (the song's envelope pack -- beats,
# onsets, band energies); `state` is the dict the program remembers things in,
# and the only thing a checkpoint carries.
Program = Callable[[np.ndarray, float, Any, dict], np.ndarray]

_CHECKPOINT_VERSION = 1


# --------------------------------------------------------------------------
# The job
# --------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RenderJob:
    """One stretch of output: which clip, which frames, how to encode them.

    Frame numbers count output frames from the start of the clip window.
    Frame i is on screen at t = t0 + i / fps -- the time the program sees,
    normally song time -- and shows the source at source_start + i / fps *
    speed. A job renders frames [start_frame, end_frame); the jobs that
    run_workers() splits one job into share its numbering.

    speed < 1 is slow motion. The decoder samples the source at fps / speed so
    every output frame gets its own source frame; sampling at fps * speed
    instead is the easy mistake, and in a real release it shipped segments
    short of their slot until it was caught. Playback is forward only.

    The encode settings live on the job rather than on each call because every
    part is stream-copied into one file at the end -- concat with -c:v copy
    stitches bitstreams, it doesn't reconcile them -- so a resume refuses to
    continue a job whose settings changed. The defaults are the real
    release's: crf 20, preset medium, 2 threads per worker (three workers on
    four cores), a 2 s GOP. Parts are copied, never re-encoded, so this is the
    final encode; there is no later pass to recover quality in. (The release
    also passed maxrate 12M / bufsize 24M at 1080p; set both here to do the
    same.)

    `pre_filter` is an ffmpeg filter chain applied to the source before it is
    fitted to `size` -- a crop that follows a face for a 9:16 cut, say.
    Without one, the source is scaled to cover `size` and centre-cropped. It
    reaches ffmpeg verbatim, so treat it as code: never build it from text you
    didn't write (some ffmpeg filters open other files).
    """

    source: str
    out_dir: str
    end_frame: int
    tag: str = "frames"
    start_frame: int = 0
    fps: float = 25.0
    size: tuple[int, int] = (1920, 1080)
    source_start: float = 0.0
    speed: float = 1.0
    t0: float = 0.0
    pre_filter: str | None = None
    crf: int = 20
    preset: str = "medium"
    threads: int | None = 2
    gop: int | None = None
    maxrate: str | None = None
    bufsize: str | None = None
    checkpoint_every: int = 250

    def __post_init__(self) -> None:
        if not self.tag or "/" in self.tag or os.sep in self.tag:
            raise ValueError(f"tag must be a plain file-name prefix, got {self.tag!r}")
        if self.start_frame < 0 or self.end_frame < self.start_frame:
            raise ValueError(f"frame range {self.start_frame}..{self.end_frame} runs backwards or starts below 0")
        if self.fps <= 0:
            raise ValueError(f"fps must be positive, got {self.fps}")
        if self.speed <= 0:
            raise ValueError(f"speed must be positive (the decoder reads forward), got {self.speed}")
        w, h = self.size
        if w <= 0 or h <= 0 or w % 2 or h % 2:
            raise ValueError(
                f"size {w}x{h} must be positive and even: yuv420p, which players expect from "
                "h264, halves chroma resolution in both directions"
            )
        if self.checkpoint_every < 1:
            raise ValueError("checkpoint_every must be at least 1 frame")

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame

    def time_at(self, frame: int) -> float:
        return self.t0 + frame / self.fps

    def source_time_at(self, frame: int) -> float:
        return self.source_start + frame / self.fps * self.speed

    @property
    def keyframe_interval(self) -> int:
        return self.gop if self.gop else max(1, round(2 * self.fps))


@dataclass(frozen=True)
class RenderResult:
    """What one call to run_job() did: where the job now stands, and what this
    call rendered and wrote.

    `read_s`, `program_s` and `write_s` split the frames' time three ways:
    waiting for the decoder and converting its bytes to float; the program;
    converting back and waiting for the encoder to take the frame. Each part's
    log line says the same per frame, so a run log shows which of the three a
    render waits on (benchmarks/ reads them)."""

    job: RenderJob
    next_frame: int
    frames: int = 0
    parts: tuple[str, ...] = ()
    elapsed_s: float = 0.0
    read_s: float = 0.0
    program_s: float = 0.0
    write_s: float = 0.0

    @property
    def done(self) -> bool:
        return self.next_frame >= self.job.end_frame

    @property
    def fps(self) -> float:
        return self.frames / self.elapsed_s if self.elapsed_s > 0 else 0.0


def part_path(job: RenderJob, index: int) -> str:
    return os.path.join(job.out_dir, f"{job.tag}_part{index:03d}.mp4")


def checkpoint_path(job: RenderJob) -> str:
    return os.path.join(job.out_dir, f"{job.tag}.ckpt.npz")


def _partial_path(job: RenderJob, index: int) -> str:
    # A part is written under this name and renamed when its encoder exits
    # cleanly, so a killed call can leave a truncated file behind but never a
    # truncated file under a name job_parts() would hand to concat.
    return os.path.join(job.out_dir, f"{job.tag}_part{index:03d}.partial.mp4")


# --------------------------------------------------------------------------
# ffmpeg command lines
# --------------------------------------------------------------------------


def _fps_arg(fps: float) -> str:
    """An exact rate for ffmpeg: 25 -> "25", 30000/1001 -> "30000/1001"."""
    frac = Fraction(fps).limit_denominator(1001)
    return str(frac.numerator) if frac.denominator == 1 else f"{frac.numerator}/{frac.denominator}"


def decode_argv(
    source: str,
    *,
    start_s: float,
    fps: float,
    size: tuple[int, int],
    frames: int | None = None,
    speed: float = 1.0,
    pre_filter: str | None = None,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """ffmpeg reading `frames` frames of `source` from `start_s`, as raw rgb24
    on stdout, at `size` and `fps / speed`.

    `-ss` goes before `-i`: ffmpeg jumps to the keyframe before `start_s` and
    decodes forward to it, once. Everything after that is a sequential read.
    The path is made absolute, so a file whose name begins with "-" can't be
    read as a flag.
    """
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")
    w, h = size
    chain = [pre_filter] if pre_filter else []
    chain += [
        f"fps={_fps_arg(fps / speed)}",
        f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos",
        f"crop={w}:{h}",
    ]
    argv = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start_s > 0:
        argv += ["-ss", f"{start_s:.6f}"]
    argv += ["-i", os.path.abspath(source), "-an", "-sn", "-vf", ",".join(chain)]
    if frames is not None:
        argv += ["-frames:v", str(int(frames))]
    argv += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return argv


def encode_argv(
    out_path: str,
    *,
    size: tuple[int, int],
    fps: float,
    crf: int = 20,
    preset: str = "medium",
    threads: int | None = 2,
    gop: int | None = None,
    maxrate: str | None = None,
    bufsize: str | None = None,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """ffmpeg reading raw rgb24 frames of `size` on stdin and writing h264 to
    `out_path`. maxrate only takes effect together with bufsize, as in
    EncodeConfig."""
    w, h = size
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", _fps_arg(fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
    ]
    if gop:
        argv += ["-g", str(gop)]
    if maxrate and bufsize:
        argv += ["-maxrate", maxrate, "-bufsize", bufsize]
    if threads:
        argv += ["-threads", str(threads)]
    argv.append(os.path.abspath(out_path))
    return argv


def write_concat_list(parts: Iterable[str], list_path: str) -> str:
    """The concat demuxer's list of `parts`, absolute and quoted with
    render/_ffmpeg_util.concat_quote() (the demuxer's escaping, not the
    shell's)."""
    with open(list_path, "w", encoding="utf-8") as fh:
        for p in parts:
            fh.write(f"file {concat_quote(os.path.abspath(p))}\n")
    return list_path


def concat_args(list_path: str, output_path: str) -> list[str]:
    """Arguments for render._ffmpeg_util.run(): join the listed parts by
    stream copy. Video only -- the parts have no audio, and the song goes on
    afterwards with mux_audio()."""
    return [
        "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-map", "0:v:0", "-c:v", "copy", output_path,
    ]


# --------------------------------------------------------------------------
# Decoder and encoder processes
# --------------------------------------------------------------------------


class FrameSource(Protocol):
    """Yields uint8 RGB frames shaped (H, W, 3), in order."""

    def __iter__(self) -> Iterator[np.ndarray]: ...

    def close(self) -> None: ...


class FrameSink(Protocol):
    """Accepts uint8 RGB frames shaped (H, W, 3); close() finishes the file."""

    def write(self, frame: np.ndarray) -> None: ...

    def close(self) -> None: ...


def _tail(fh: Any) -> str:
    fh.seek(0)
    return fh.read()[-2000:].decode("utf-8", errors="replace").strip()


class FfmpegSource:
    """A running ffmpeg decoder, read one raw frame at a time.

    stderr goes to a temporary file rather than a pipe: a pipe nobody drains
    blocks ffmpeg once it fills, which would look like a hung render.
    """

    def __init__(self, argv: list[str], size: tuple[int, int]):
        w, h = size
        self._shape = (h, w, 3)
        self._frame_bytes = w * h * 3
        self._stderr = tempfile.TemporaryFile()
        self._proc = spawn(argv, read_stdout=True, stderr=self._stderr)

    def __iter__(self) -> Iterator[np.ndarray]:
        while True:
            buf = self._proc.stdout.read(self._frame_bytes)
            if len(buf) < self._frame_bytes:
                code = self._proc.wait()
                if code != 0:
                    raise RuntimeError(f"ffmpeg decode failed (exit {code}):\n{_tail(self._stderr)}")
                return
            yield np.frombuffer(buf, np.uint8).reshape(self._shape)

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
        self._proc.wait()
        if self._proc.stdout is not None:
            self._proc.stdout.close()
        self._stderr.close()


class FfmpegSink:
    """A running ffmpeg encoder fed raw frames on stdin."""

    def __init__(self, argv: list[str]):
        self._stderr = tempfile.TemporaryFile()
        self._proc = spawn(argv, feed_stdin=True, stderr=self._stderr)

    def write(self, frame: np.ndarray) -> None:
        try:
            self._proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).data)
        except BrokenPipeError:
            code = self._proc.wait()
            raise RuntimeError(f"ffmpeg encode died (exit {code}):\n{_tail(self._stderr)}") from None

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        code = self._proc.wait()
        tail = _tail(self._stderr)
        self._stderr.close()
        if code != 0:
            raise RuntimeError(f"ffmpeg encode failed (exit {code}):\n{tail}")


def ffmpeg_source(job: RenderJob, start_frame: int, count: int) -> FfmpegSource:
    """The default decoder: frames [start_frame, start_frame + count) of `job`."""
    argv = decode_argv(
        job.source,
        start_s=job.source_time_at(start_frame),
        fps=job.fps,
        size=job.size,
        frames=count,
        speed=job.speed,
        pre_filter=job.pre_filter,
        ffmpeg=require_ffmpeg(),
    )
    return FfmpegSource(argv, job.size)


def ffmpeg_sink(job: RenderJob, path: str) -> FfmpegSink:
    """The default encoder: one part file of `job`."""
    return FfmpegSink(
        encode_argv(
            path,
            size=job.size,
            fps=job.fps,
            crf=job.crf,
            preset=job.preset,
            threads=job.threads,
            gop=job.keyframe_interval,
            maxrate=job.maxrate,
            bufsize=job.bufsize,
            ffmpeg=require_ffmpeg(),
        )
    )


# --------------------------------------------------------------------------
# Checkpoints
# --------------------------------------------------------------------------


def _job_signature(job: RenderJob) -> dict[str, Any]:
    """Everything that changes what a frame looks like or how it is encoded.
    A checkpoint only resumes a job whose signature matches."""
    return {
        "start_frame": job.start_frame,
        "end_frame": job.end_frame,
        "fps": job.fps,
        "size": list(job.size),
        "source_start": job.source_start,
        "speed": job.speed,
        "t0": job.t0,
        "pre_filter": job.pre_filter,
        "crf": job.crf,
        "preset": job.preset,
        "gop": job.keyframe_interval,
        "maxrate": job.maxrate,
        "bufsize": job.bufsize,
    }


def _to_array(value: Any, label: str) -> np.ndarray:
    if isinstance(value, np.ndarray):
        if value.dtype == object:
            raise TypeError(f"state {label!r} is an object array, which a checkpoint can't hold without pickle")
        return value
    if isinstance(value, (bool, int, float, str, np.generic)):
        return np.asarray(value)
    raise TypeError(
        f"state {label!r} is a {type(value).__name__}, which a checkpoint can't hold: checkpoints "
        "are loaded without pickle, so they hold arrays, numbers and strings. Give it "
        "state_dict()/load_state_dict(), or rebuild it in make_state() instead of storing it."
    )


def _from_array(value: np.ndarray) -> Any:
    # A 0-d array comes back as a numpy scalar, not a Python one, so its dtype
    # -- and therefore every later computation with it -- matches the run that
    # saved it.
    return value[()] if value.ndim == 0 else value


def _write_checkpoint(path: str, job: RenderJob, next_frame: int, part: int, state: dict) -> None:
    arrays: dict[str, np.ndarray] = {}
    manifest: list[dict[str, Any]] = []
    for i, (name, value) in enumerate(state.items()):
        if hasattr(value, "state_dict"):
            sub = value.state_dict()
            keys = list(sub)
            for j, key in enumerate(keys):
                arrays[f"s{i}_{j}"] = _to_array(sub[key], f"{name}.{key}")
            manifest.append({"name": name, "kind": "stateful", "keys": keys})
        elif value is None:
            manifest.append({"name": name, "kind": "none"})
        else:
            arrays[f"s{i}"] = _to_array(value, name)
            manifest.append({"name": name, "kind": "value"})
    meta = {
        "version": _CHECKPOINT_VERSION,
        "next_frame": int(next_frame),
        "part": int(part),
        "job": _job_signature(job),
        "manifest": manifest,
    }
    arrays["meta"] = np.asarray(json.dumps(meta))
    # Write, then rename: a call killed mid-write leaves the previous
    # checkpoint intact instead of a truncated one.
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        np.savez(fh, **arrays)
    os.replace(tmp, path)


def _read_checkpoint(path: str) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    with np.load(path, allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    meta = json.loads(str(arrays.pop("meta")[()]))
    if meta.get("version") != _CHECKPOINT_VERSION:
        raise ValueError(f"{path} is checkpoint format {meta.get('version')}, expected {_CHECKPOINT_VERSION}")
    return meta, arrays


def _new_state(make_state: Callable[[], dict] | None) -> dict:
    state = make_state() if make_state is not None else {}
    if not isinstance(state, dict):
        raise TypeError(f"make_state() must return a dict, got {type(state).__name__}")
    return state


def _restore_state(meta: dict, arrays: dict[str, np.ndarray], make_state: Callable[[], dict] | None) -> dict:
    state = _new_state(make_state)
    for i, entry in enumerate(meta["manifest"]):
        name, kind = entry["name"], entry["kind"]
        if kind == "none":
            state[name] = None
        elif kind == "value":
            state[name] = _from_array(arrays[f"s{i}"])
        else:
            target = state.get(name)
            if not hasattr(target, "load_state_dict"):
                raise ValueError(
                    f"the checkpoint holds state for {name!r}, but make_state() built no object with "
                    "load_state_dict() under that name -- build the same effects the run that wrote it did"
                )
            target.load_state_dict({key: _from_array(arrays[f"s{i}_{j}"]) for j, key in enumerate(entry["keys"])})
    return state


def _check_resumable(meta: dict, job: RenderJob, path: str) -> None:
    saved, current = meta["job"], _job_signature(job)
    changed = sorted(k for k in current if saved.get(k) != current[k])
    if changed:
        detail = ", ".join(f"{k}: {saved.get(k)!r} -> {current[k]!r}" for k in changed)
        raise ValueError(
            f"{path} was written for a different job ({detail}). Its parts can't be stream-copied "
            "together with parts rendered under the new settings. Pass resume=False to start this "
            "job over (its parts are overwritten), or use a different tag."
        )


# --------------------------------------------------------------------------
# Running a job
# --------------------------------------------------------------------------


def _decoded_to_float(raw: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    arr = np.asarray(raw)
    if arr.shape != shape or arr.dtype != np.uint8:
        raise ValueError(f"source frame is {arr.dtype} {arr.shape}, expected uint8 {shape}")
    return arr.astype(np.float32) * np.float32(1.0 / 255.0)


def _float_to_u8(out: Any, scratch: np.ndarray, index: int) -> np.ndarray:
    arr = np.asarray(out)
    if arr.shape != scratch.shape:
        raise ValueError(f"the program returned shape {arr.shape} for frame {index}, expected {scratch.shape}")
    if not np.issubdtype(arr.dtype, np.floating):
        raise TypeError(f"the program returned {arr.dtype} for frame {index}; return float RGB in 0..1")
    # Rounded, not truncated: truncation darkens every frame by half a code
    # value on average. Written into engine-owned scratch, so the program's
    # array -- which may be an effect's live state -- is never clipped in place.
    np.clip(arr, 0.0, 1.0, out=scratch)
    scratch *= 255.0
    scratch += 0.5
    return scratch.astype(np.uint8)


def run_job(
    job: RenderJob,
    program: Program,
    *,
    make_state: Callable[[], dict] | None = None,
    env: Any = None,
    budget_s: float | None = None,
    resume: bool = True,
    open_source: Callable[[RenderJob, int, int], FrameSource] | None = None,
    open_sink: Callable[[RenderJob, str], FrameSink] | None = None,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] | None = None,
) -> RenderResult:
    """Render `job` through `program`, resuming from its checkpoint if it has one.

    Frames are written to part files of `job.checkpoint_every` frames. After
    each part the program's state is checkpointed with the next frame index;
    when `budget_s` of wall-clock time has passed, the current part is closed
    and checkpointed early and the call returns. Call it again -- in this
    process or a new one -- and it continues from there. Returns where the
    job stands; `.done` says whether it's finished.

    `make_state()` builds a fresh state dict: the effects the program uses,
    with the same arguments every time. On resume it is called first and the
    checkpoint is loaded into what it returns, so configuration (sizes,
    schedules, seeds) comes from code and only state comes from disk. Values
    in the dict are checkpointed through their state_dict() if they have one;
    arrays, numbers, strings and None are stored as they are.

    A resume re-seeks the source. For a source whose frame grid doesn't line
    up with the output's (29.97 into 25, say), ffmpeg's fps filter can choose
    a neighbouring source frame at the part boundary -- the same caveat as any
    cut at that frame.
    """
    started = clock()
    os.makedirs(job.out_dir, exist_ok=True)
    ckpt = checkpoint_path(job)
    open_source = open_source or ffmpeg_source
    open_sink = open_sink or ffmpeg_sink

    if resume and os.path.exists(ckpt):
        meta, arrays = _read_checkpoint(ckpt)
        _check_resumable(meta, job, ckpt)
        next_frame, part = meta["next_frame"], meta["part"]
        state = _restore_state(meta, arrays, make_state)
    else:
        if os.path.exists(ckpt):
            # Starting over: drop the old checkpoint now, so a crash before the
            # first new part can't resume the old run on top of new parts.
            os.remove(ckpt)
        next_frame, part, state = job.start_frame, 0, _new_state(make_state)

    if next_frame >= job.end_frame:
        return RenderResult(job, next_frame, elapsed_s=clock() - started)

    w, h = job.size
    shape = (h, w, 3)
    scratch = np.empty(shape, np.float32)
    source = open_source(job, next_frame, job.end_frame - next_frame)
    rendered = 0
    in_part = 0
    written: list[str] = []
    sink: FrameSink | None = None
    partial: str | None = None
    part_started = clock()
    # Seconds spent reading, in the program, and writing: this call's, and this part's.
    spent = [0.0, 0.0, 0.0]
    in_part_spent = [0.0, 0.0, 0.0]
    try:
        frames = iter(source)
        while next_frame < job.end_frame:
            t_read = clock()
            raw = next(frames, None)
            read = clock() - t_read
            if raw is None:
                raise RuntimeError(
                    f"{job.tag}: the source ended at frame {next_frame} of {job.start_frame}..{job.end_frame} "
                    f"(source time {job.source_time_at(next_frame):.3f}s) -- the window runs past the end of the clip"
                )
            if sink is None:
                partial = _partial_path(job, part)
                sink = open_sink(job, partial)
                part_started = clock()
            t_convert = clock()
            frame = _decoded_to_float(raw, shape)
            t_program = clock()
            out = program(frame, job.time_at(next_frame), env, state)
            t_write = clock()
            sink.write(_float_to_u8(out, scratch, next_frame))
            t_done = clock()
            split = (read + t_program - t_convert, t_write - t_program, t_done - t_write)
            for k in range(3):
                spent[k] += split[k]
                in_part_spent[k] += split[k]
            next_frame += 1
            rendered += 1
            in_part += 1
            out_of_time = budget_s is not None and clock() - started >= budget_s
            if in_part >= job.checkpoint_every or next_frame >= job.end_frame or out_of_time:
                sink.close()
                sink = None
                final = part_path(job, part)
                os.replace(partial, final)
                partial = None
                written.append(final)
                _write_checkpoint(ckpt, job, next_frame, part + 1, state)
                if log is not None:
                    took = clock() - part_started
                    rate = in_part / took if took > 0 else 0.0
                    read_ms, program_ms, write_ms = (1000.0 * s / in_part for s in in_part_spent)
                    log(
                        f"{job.tag}: part {part:03d} done, next frame {next_frame} of {job.end_frame} ({rate:.1f} fps; "
                        f"read {read_ms:.1f} / program {program_ms:.1f} / write {write_ms:.1f} ms a frame)"
                    )
                part += 1
                in_part = 0
                in_part_spent = [0.0, 0.0, 0.0]
                if out_of_time:
                    break
    finally:
        if sink is not None:
            try:
                sink.close()
            except Exception:
                pass  # already failing; the original error is the one worth reporting
        if partial is not None and os.path.exists(partial):
            os.remove(partial)
        source.close()
    return RenderResult(job, next_frame, rendered, tuple(written), clock() - started, *spent)


def job_status(job: RenderJob) -> RenderResult:
    """Where `job` stands according to its checkpoint, without running it."""
    ckpt = checkpoint_path(job)
    if job.frame_count <= 0:
        return RenderResult(job, job.end_frame)
    if not os.path.exists(ckpt):
        return RenderResult(job, job.start_frame)
    meta, _ = _read_checkpoint(ckpt)
    return RenderResult(job, int(meta["next_frame"]))


def job_parts(jobs: RenderJob | Iterable[RenderJob]) -> list[str]:
    """The finished part files of one or more jobs, in timeline order -- what
    concat_parts() should join.

    Refuses an unfinished job, and jobs that don't tile their range without a
    gap or an overlap: concatenating either would silently shorten or repeat
    the picture against the audio -- the same reason EDL refuses a timeline
    with gaps.
    """
    ordered = [jobs] if isinstance(jobs, RenderJob) else sorted(jobs, key=lambda j: j.start_frame)
    for a, b in itertools.pairwise(ordered):
        if a.end_frame != b.start_frame:
            raise ValueError(
                f"{a.tag} ends at frame {a.end_frame} but {b.tag} starts at {b.start_frame}: "
                "jobs must tile their range with no gap or overlap"
            )
    parts: list[str] = []
    for job in ordered:
        if job.frame_count <= 0:
            continue
        ckpt = checkpoint_path(job)
        if not os.path.exists(ckpt):
            raise RuntimeError(f"{job.tag} has not been rendered yet (no {os.path.basename(ckpt)})")
        meta, _ = _read_checkpoint(ckpt)
        if meta["next_frame"] < job.end_frame:
            raise RuntimeError(
                f"{job.tag} is unfinished: next frame {meta['next_frame']} of "
                f"{job.start_frame}..{job.end_frame}. Run it again -- it resumes from its checkpoint -- "
                "before concatenating; joining it now would silently drop the rest."
            )
        paths = [part_path(job, i) for i in range(meta["part"])]
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            raise FileNotFoundError(f"{job.tag}: checkpoint lists parts that are gone: {missing}")
        parts += paths
    return parts


def concat_parts(parts: Sequence[str], output_path: str, *, list_path: str | None = None) -> str:
    """Join part files into one video by stream copy -- no re-encode, so it
    takes seconds and costs no quality. The concat list is written next to the
    parts unless `list_path` says otherwise."""
    parts = list(parts)
    if not parts:
        raise ValueError("concat_parts() needs at least one part")
    missing = [p for p in parts if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"parts not found: {missing}")
    if list_path is None:
        list_path = os.path.join(
            os.path.dirname(os.path.abspath(parts[0])), os.path.basename(output_path) + ".concat.txt"
        )
    write_concat_list(parts, list_path)
    run(require_ffmpeg(), concat_args(list_path, output_path))
    return output_path


# --------------------------------------------------------------------------
# Workers
# --------------------------------------------------------------------------


def _snap_bounds(bounds: list[int], snap_to: Iterable[int]) -> list[int]:
    start, end = bounds[0], bounds[-1]
    n = len(bounds) - 1
    reach = (end - start) / (2 * n)
    cuts = sorted({int(c) for c in snap_to if start < int(c) < end})
    snapped = [start]
    for ideal in bounds[1:-1]:
        near = [c for c in cuts if c > snapped[-1] and abs(c - ideal) <= reach]
        choice = min(near, key=lambda c: (abs(c - ideal), c)) if near else ideal
        if snapped[-1] < choice < end:
            snapped.append(choice)
    snapped.append(end)
    return snapped


def split_frames(
    start: int,
    end: int,
    n: int,
    *,
    mode: str = "contiguous",
    chunk: int = 250,
    snap_to: Iterable[int] = (),
) -> list[list[tuple[int, int]]]:
    """Split frames [start, end) across `n` workers: one list of ranges each.

    "contiguous" gives each worker one unbroken range. A stateful effect runs
    continuously inside it and starts fresh at each worker's first frame, so a
    memory canvas resets n - 1 times -- acceptable at a cut, visible
    mid-shot. Pass the edit's cut frames as `snap_to` and each boundary moves
    to the nearest cut within half a worker's share (the real release placed
    its chunk boundaries at cuts for exactly this reason). The cost: workers
    whose ranges hold the expensive passages finish last.

    "stride" deals fixed `chunk`-frame ranges round-robin, so expensive
    passages spread over every worker and they finish together. The cost:
    every chunk boundary is a state reset, so stride is for programs whose
    effects are stateless or forget within a few frames.
    """
    if n < 1:
        raise ValueError("need at least one worker")
    total = end - start
    if total <= 0:
        return []
    if mode == "contiguous":
        n = min(n, total)
        bounds = [start + round(k * total / n) for k in range(n + 1)]
        if snap_to:
            bounds = _snap_bounds(bounds, snap_to)
        return [[(a, b)] for a, b in itertools.pairwise(bounds) if b > a]
    if mode == "stride":
        if chunk < 1:
            raise ValueError("chunk must be at least 1 frame")
        chunks = [(a, min(a + chunk, end)) for a in range(start, end, chunk)]
        return [chunks[k::n] for k in range(min(n, len(chunks)))]
    raise ValueError(f"mode must be 'contiguous' or 'stride', got {mode!r}")


def plan_workers(
    job: RenderJob,
    n: int,
    *,
    mode: str = "contiguous",
    chunk: int | None = None,
    snap_to: Iterable[int] = (),
) -> list[list[RenderJob]]:
    """The sub-jobs run_workers() would run, one list per worker. Pure: running
    it again gives the same jobs and tags, which is what lets a later call find
    the earlier call's checkpoints."""
    chunk = chunk or job.checkpoint_every
    plan = split_frames(job.start_frame, job.end_frame, n, mode=mode, chunk=chunk, snap_to=snap_to)
    workers: list[list[RenderJob]] = []
    for k, ranges in enumerate(plan):
        jobs = []
        for a, b in ranges:
            tag = f"{job.tag}_w{k:02d}" if mode == "contiguous" else f"{job.tag}_c{(a - job.start_frame) // chunk:04d}"
            jobs.append(dataclasses.replace(job, tag=tag, start_frame=a, end_frame=b))
        workers.append(jobs)
    return workers


def _run_worker(
    jobs: list[RenderJob],
    program: Program,
    make_state: Callable[[], dict] | None,
    env: Any,
    budget_s: float | None,
    open_source: Callable[[RenderJob, int, int], FrameSource] | None,
    open_sink: Callable[[RenderJob, str], FrameSink] | None,
    clock: Callable[[], float],
    log: Callable[[str], None] | None,
) -> list[RenderResult]:
    started = clock()
    results = []
    for job in jobs:
        remaining = None if budget_s is None else budget_s - (clock() - started)
        if remaining is not None and remaining <= 0:
            results.append(job_status(job))
            continue
        results.append(
            run_job(
                job,
                program,
                make_state=make_state,
                env=env,
                budget_s=remaining,
                open_source=open_source,
                open_sink=open_sink,
                clock=clock,
                log=log,
            )
        )
    return results


def run_workers(
    job: RenderJob,
    program: Program,
    n: int,
    budget_s: float | None = None,
    *,
    mode: str = "contiguous",
    chunk: int | None = None,
    snap_to: Iterable[int] = (),
    make_state: Callable[[], dict] | None = None,
    env: Any = None,
    parallel: bool = True,
    open_source: Callable[[RenderJob, int, int], FrameSource] | None = None,
    open_sink: Callable[[RenderJob, str], FrameSink] | None = None,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] | None = None,
) -> list[RenderResult]:
    """Render `job` as `n` resumable workers in parallel, each stopping at
    `budget_s`. Call it again until every result is done, then
    concat_parts(job_parts(r.job for r in results), ...).

    The split is split_frames()'s (see it for contiguous vs stride). Finished
    sub-jobs are skipped, so repeated calls under a per-call time limit simply
    make progress: the real release ran three workers per 180 s call with a
    150 s budget. Workers are separate processes started with "spawn" -- the
    same behaviour on macOS and Linux, and no fork of a process whose BLAS
    threads are running -- so `program`, `make_state`, `env` and any custom
    `open_source`/`open_sink` must be picklable: module-level functions, not
    lambdas, in a script with an `if __name__ == "__main__":` guard.
    parallel=False runs the workers one after another in this process (each
    with the full budget), for debugging and tests.
    """
    plan = plan_workers(job, n, mode=mode, chunk=chunk, snap_to=snap_to)
    args = (program, make_state, env, budget_s, open_source, open_sink, clock, log)
    if parallel and len(plan) > 1:
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=len(plan), mp_context=context) as pool:
            futures = [pool.submit(_run_worker, jobs, *args) for jobs in plan]
            batches = [f.result() for f in futures]
    else:
        batches = [_run_worker(jobs, *args) for jobs in plan]
    return sorted((r for batch in batches for r in batch), key=lambda r: r.job.start_frame)
