"""
Turn an EDL into an actual MP4 via ffmpeg subprocess calls.

Renders each cut as its own short clip (color grade + effects baked in), then
concatenates them and muxes the original audio back on. Multiple small,
inspectable ffmpeg calls rather than one giant filter_complex graph: slower,
but a broken cut is a five-second re-render and a readable error, not a
500-line graph to debug. See docs/ARCHITECTURE.md, "Why segment-then-concat".
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from kaleidophone.assets.curation import VIDEO_EXTS
from kaleidophone.render import effects as fx
from kaleidophone.render._ffmpeg_util import probe_duration, require_ffmpeg, run
from kaleidophone.timeline.model import EDL, Cut
from kaleidophone.timeline.schema import CreativeBrief, StationConfig


def render_silent(
    edl: EDL,
    brief: CreativeBrief,
    silent_output_path: str,
    *,
    work_dir: str | None = None,
    keep_work_dir: bool = False,
) -> str:
    """Render every cut and concatenate them into a silent video. This is the
    expensive step -- one or more ffmpeg calls per cut. Its output is a real,
    reusable file: swapping in a different or updated audio track afterward
    is `mux_audio()`, a single fast stream-copy pass, not this."""
    ffmpeg = require_ffmpeg()
    stations = {s.name: s for s in brief.stations}
    w, h = edl.resolution

    with _WorkDirectory(work_dir, keep_work_dir) as tmp:
        segment_paths = []
        for cut in edl.cuts:
            station = stations[cut.station]
            seg_path = os.path.join(tmp, f"seg_{cut.index:05d}.mp4")
            _render_segment(ffmpeg, cut, station, w, h, edl.fps, seg_path)
            segment_paths.append(seg_path)

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as fh:
            for p in segment_paths:
                fh.write(f"file {_concat_quote(os.path.abspath(p))}\n")

        run(
            ffmpeg,
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                silent_output_path,
            ],
        )

    return silent_output_path


def _concat_quote(path: str) -> str:
    """Quote a path for ffmpeg's concat demuxer.

    The demuxer's own escaping rules, not the shell's: inside a single-quoted
    token a literal ' is written by closing the quote, emitting an escaped
    quote, and reopening.

    What passes through here is the *segment* paths, so the apostrophe that
    breaks a render comes from the work directory -- an explicit work_dir, or
    a TMPDIR under something like "/Users/me/Dad's scratch" -- not from the
    user's media filenames, which reach ffmpeg as argv elements and never get
    re-parsed. Narrow trigger, one-line fix, and it is what the concat format
    actually specifies.
    """
    return "'" + path.replace("'", "'\\''") + "'"


def _warn_if_streams_disagree(silent_video_path: str, audio_path: str, tolerance: float = 0.5) -> None:
    """`-shortest` truncates whichever stream is longer, without comment.

    That is the right default -- but a silent truncation is exactly the failure
    the reference project's iteration 2 hit, where a replacement master moved
    the landmarks and the edit desynced with nothing on screen to say so (see
    docs/case-studies/love.md, and ROADMAP's "remux landmark-drift guard",
    which this is the first half of). Say something.
    """
    video = probe_duration(silent_video_path)
    audio = probe_duration(audio_path)
    if video is None or audio is None:
        return
    delta = audio - video
    if abs(delta) <= tolerance:
        return
    longer, amount = ("audio", delta) if delta > 0 else ("video", -delta)
    print(
        f"warning: {longer} is {amount:.2f}s longer than the other stream "
        f"(video {video:.2f}s, audio {audio:.2f}s). -shortest will cut the longer one. "
        f"If this audio isn't the track the edit was composed against, re-run "
        f"`kaleidophone compose` before remuxing -- the cuts are placed for the old one.",
        file=sys.stderr,
    )


def mux_audio(silent_video_path: str, audio_path: str, output_path: str) -> str:
    """Stitch a (possibly new) audio track onto an already-rendered silent
    video: a fast stream-copy on the video side. This is the operation for
    'we uploaded a draft mp3, everyone signed off on the edit, now put the
    mastered wave on it' -- it never re-runs a single effect."""
    ffmpeg = require_ffmpeg()
    _warn_if_streams_disagree(silent_video_path, audio_path)
    run(
        ffmpeg,
        [
            "-y",
            "-i",
            silent_video_path,
            "-i",
            audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            output_path,
        ],
    )
    return output_path


def render(
    edl: EDL,
    brief: CreativeBrief,
    output_path: str,
    *,
    work_dir: str | None = None,
    keep_work_dir: bool = False,
) -> str:
    """Convenience: render_silent() + mux_audio() in one call, discarding the
    intermediate silent video. Call them separately (via `kaleidophone silent` /
    `kaleidophone remux`) if you expect to re-sync audio later without redoing the
    (expensive) visual render -- see mux_audio()."""
    silent_path = output_path + ".silent.mp4"
    render_silent(edl, brief, silent_path, work_dir=work_dir, keep_work_dir=keep_work_dir)
    try:
        mux_audio(silent_path, edl.audio_path, output_path)
    finally:
        if not keep_work_dir and os.path.exists(silent_path):
            os.remove(silent_path)
    return output_path


def _render_segment(
    ffmpeg: str, cut: Cut, station: StationConfig, w: int, h: int, fps: int, out_path: str
) -> None:
    duration = cut.duration
    is_video = os.path.splitext(cut.source_path)[1].lower() in VIDEO_EXTS

    scale_crop = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"
    linear_chain = [scale_crop, fx.color_grade(station)]
    graph_effects = [e for e in cut.effects if e in fx.GRAPH_EFFECT_BUILDERS]
    for effect in cut.effects:
        if effect in fx.GRAPH_EFFECT_BUILDERS:
            continue
        builder = fx.LINEAR_EFFECT_BUILDERS.get(effect)
        if builder is None:
            continue
        built = builder(fps=fps, w=w, h=h, duration=duration)
        if built:
            linear_chain.append(built)

    # Drive the segment by an exact frame count, never by a duration in
    # seconds. `-t 0.464` asks for 11.1456 frames and ffmpeg truncates to 11,
    # losing a fraction of a frame on every cut, always downward -- 3.25s of
    # accumulated drift over a 640-cut render before this was fixed. compose()
    # already snaps every boundary onto the frame grid (see
    # timeline/compose.py's snap_to_frame), so this round() is exact rather
    # than a second guess at the same number.
    frames = max(1, round(duration * fps))

    # Absolute, so a file whose name begins with "-" can't be read as a flag.
    source = os.path.abspath(cut.source_path)

    # A video source shorter than its cut used to just end early, silently
    # shortening the segment; -stream_loop -1 fills the cut instead, and
    # -frames:v is what actually bounds it.
    src_args = (
        ["-stream_loop", "-1", "-i", source, "-frames:v", str(frames)]
        if is_video
        else ["-loop", "1", "-i", source, "-frames:v", str(frames)]
    )

    # N graph effects need N+1 stage files: the linear pass, then one hop per
    # graph effect. With zero graph effects this collapses to [out_path], and
    # the linear pass writes the final file directly.
    stages = [f"{out_path}.stage{i}.mp4" for i in range(len(graph_effects))] + [out_path]

    run(
        ffmpeg,
        [
            "-y",
            *src_args,
            "-vf",
            ",".join(linear_chain),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            stages[0],
        ],
    )
    for effect, src, dst in zip(graph_effects, stages, stages[1:]):
        builder = fx.GRAPH_EFFECT_BUILDERS[effect]
        run(
            ffmpeg,
            [
                "-y",
                "-i",
                src,
                "-filter_complex",
                builder(),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-an",
                dst,
            ],
        )


class _WorkDirectory:
    """A directory for intermediate render artifacts. An explicit `work_dir`
    is kept (useful for `--keep` debugging); otherwise a temp dir is created
    and removed on exit -- which is also why the `.stageN.mp4` intermediates
    from _render_segment never need manual cleanup."""

    def __init__(self, work_dir: str | None, keep: bool):
        self._explicit = work_dir
        self._keep = keep
        self._tmp: str | None = None

    def __enter__(self) -> str:
        if self._explicit:
            os.makedirs(self._explicit, exist_ok=True)
            return self._explicit
        self._tmp = tempfile.mkdtemp(prefix="kaleidophone_")
        return self._tmp

    def __exit__(self, *exc) -> bool:
        if self._tmp and not self._keep:
            shutil.rmtree(self._tmp, ignore_errors=True)
        return False
