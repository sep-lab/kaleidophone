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
from kaleidophone.overlay.card import render_overlay_cards
from kaleidophone.render import effects as fx
from kaleidophone.render._ffmpeg_util import concat_quote as _concat_quote
from kaleidophone.render._ffmpeg_util import probe_duration, require_ffmpeg, run
from kaleidophone.timeline.model import EDL, Cut
from kaleidophone.timeline.schema import (
    CreativeBrief,
    EncodeConfig,
    FramingConfig,
    OverlayConfig,
    StationConfig,
)


def _overlay_graph(overlays: list[OverlayConfig]) -> tuple[str, str]:
    """A filter_complex chaining one `overlay` per card, and the label to map.

    Each card is a full-frame RGBA PNG composited at 0:0, gated by
    `enable='between(t,start,end)'`. Chaining rather than one multi-input
    filter is what makes the cards stack predictably: a later overlay in the
    brief draws on top of an earlier one wherever their time ranges intersect.

    `t` here is the concatenated video's own timeline, which is the output
    timeline -- so an overlay at 0.25s appears a quarter-second into what you
    watch, whether or not output.window shifted which part of the song that is.
    """
    steps = []
    current = "0:v"
    for i, ov in enumerate(overlays):
        nxt = f"v{i + 1}"
        start, end = ov.at
        steps.append(
            f"[{current}][{i + 1}:v]"
            f"overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'"
            f"[{nxt}]"
        )
        current = nxt
    return ";".join(steps), current


# x264's names for each colour standard, which are not always ffmpeg's --
# bt601's primaries are "smpte170m", and bt2020's matrix is non-constant
# luminance ("bt2020nc"). Getting these wrong writes a tag that is confidently
# incorrect, which is worse than none.
_X264_COLOR: dict[str, tuple[str, str, str]] = {
    #          primaries    transfer      matrix
    "bt709": ("bt709", "bt709", "bt709"),
    "bt601": ("smpte170m", "smpte170m", "smpte170m"),
    "bt2020": ("bt2020", "bt2020-10", "bt2020nc"),
}


def _video_encode_args(enc: EncodeConfig) -> list[str]:
    """The x264 half of an output spec, shared by every pass.

    Kept in one place because a segment, the concat pass and each graph-effect
    hop all have to agree: re-encoding a segment at CRF 20 and then the concat
    at CRF 28 would quietly throw away the quality the expensive pass just paid
    for.
    """
    args = [
        "-c:v", "libx264",
        "-preset", enc.preset,
        "-crf", str(enc.crf),
        "-pix_fmt", "yuv420p",
    ]
    if enc.maxrate and enc.bufsize:
        args += ["-maxrate", enc.maxrate, "-bufsize", enc.bufsize]
    if enc.color:
        prim, trc, matrix = _X264_COLOR[enc.color]
        # All three, always. Tagging only one is worse than tagging none: a
        # player that reads primaries but not transfer gets a half-described
        # stream and guesses the rest.
        #
        # The -color_* flags alone are not enough. Measured on ffmpeg 7.1:
        # they set the container's colr box but leave the H.264 SPS VUI empty,
        # so ffprobe reports color_space=bt709 with primaries and transfer
        # "unknown", and so does anything else reading the bitstream. Passing
        # them to x264 as well writes the VUI, and both survive the stream-copy
        # in mux_audio().
        args += [
            "-colorspace", matrix,
            "-color_primaries", prim,
            "-color_trc", trc,
            "-x264-params", f"colorprim={prim}:transfer={trc}:colormatrix={matrix}",
        ]
    return args


def _framing_filter(framing: FramingConfig, w: int, h: int, fps: int) -> str:
    """Fit a source frame into a `w`x`h` output frame.

    `fill` is scale-to-cover plus a centre crop: correct when the source and
    the output share an aspect, and a blunt instrument when they don't --
    which is exactly why the other two modes exist. See FramingConfig.
    """
    if framing.mode == "crop":
        # A full-height slice at `x`, in *source* pixels. `ih*w/h` is evaluated
        # by ffmpeg against the real input, so one brief works across sources of
        # different heights -- which the eyeballed pixel widths in a hand-written
        # script never do.
        return (
            f"crop=ih*{w}/{h}:ih:{framing.x}:0,"
            f"scale={w}:{h}:flags=lanczos,fps={fps}"
        )
    if framing.mode == "window":
        ww = framing.width
        # -2 keeps the source's aspect and guarantees an even height (h.264
        # chroma subsampling needs it). Inside pad, iw/ih are the *scaled*
        # dimensions, so this stays correct without knowing the source size.
        y = f"{framing.y_center}-ih/2" if framing.y_center is not None else "(oh-ih)/2"
        return (
            f"scale={ww}:-2:flags=lanczos,"
            f"pad={w}:{h}:(ow-iw)/2:{y}:color=black,fps={fps}"
        )
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"


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
    enc = brief.output.encode
    w, h = edl.resolution

    with _WorkDirectory(work_dir, keep_work_dir) as tmp:
        segment_paths = []
        for cut in edl.cuts:
            station = stations[cut.station]
            seg_path = os.path.join(tmp, f"seg_{cut.index:05d}.mp4")
            _render_segment(ffmpeg, cut, station, w, h, edl.fps, seg_path, enc)
            segment_paths.append(seg_path)

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as fh:
            for p in segment_paths:
                fh.write(f"file {_concat_quote(os.path.abspath(p))}\n")

        # Overlay cards are rendered once, at the output resolution, and
        # composited in this single finishing pass -- not baked into each
        # segment. A card that spans a cut would otherwise have to be split
        # across segments and would visibly restart at the boundary.
        cards = render_overlay_cards(brief.overlays, w, h, tmp) if brief.overlays else []

        overlay_args: list[str] = []
        for _, png in cards:
            overlay_args += ["-i", png]
        if cards:
            graph, last = _overlay_graph([ov for ov, _ in cards])
            overlay_args += ["-filter_complex", graph, "-map", f"[{last}]"]

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
                *overlay_args,
                *_video_encode_args(enc),
                silent_output_path,
            ],
        )

    return silent_output_path


def _warn_if_streams_disagree(
    silent_video_path: str,
    audio_path: str,
    tolerance: float = 0.5,
    *,
    audio_start: float = 0.0,
    windowed: bool = False,
) -> None:
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
    # Only the part of the audio this render will actually use is comparable.
    audio = max(0.0, audio - audio_start)
    delta = audio - video
    if abs(delta) <= tolerance:
        return
    if windowed and delta > 0:
        # output.window deliberately renders a slice, so there is meant to be
        # song left over on either side and -shortest trimming it is the
        # feature working. Only the other direction -- the audio running out
        # before the picture does -- is worth saying anything about.
        return
    longer, amount = ("audio", delta) if delta > 0 else ("video", -delta)
    print(
        f"warning: {longer} is {amount:.2f}s longer than the other stream "
        f"(video {video:.2f}s, audio {audio:.2f}s). -shortest will cut the longer one. "
        f"If this audio isn't the track the edit was composed against, re-run "
        f"`kaleidophone compose` before remuxing -- the cuts are placed for the old one.",
        file=sys.stderr,
    )


def mux_audio(
    silent_video_path: str,
    audio_path: str,
    output_path: str,
    encode: EncodeConfig | None = None,
    audio_start: float = 0.0,
    windowed: bool = False,
) -> str:
    """Stitch a (possibly new) audio track onto an already-rendered silent
    video: a fast stream-copy on the video side. This is the operation for
    'we uploaded a draft mp3, everyone signed off on the edit, now put the
    mastered wave on it' -- it never re-runs a single effect."""
    ffmpeg = require_ffmpeg()
    enc = encode or EncodeConfig()
    _warn_if_streams_disagree(
        silent_video_path, audio_path, audio_start=audio_start, windowed=windowed
    )
    # Seek before -i so ffmpeg jumps rather than decoding and discarding. For a
    # windowed edit (output.window) this is what puts the audio under the right
    # part of the song; for a full render it is 0.0 and emits nothing.
    seek = ["-ss", f"{audio_start:.3f}"] if audio_start > 0 else []
    audio_args = ["-c:a", "aac", "-b:a", enc.audio_bitrate]
    if enc.audio_rate:
        audio_args += ["-ar", str(enc.audio_rate)]
    run(
        ffmpeg,
        [
            "-y",
            "-i",
            silent_video_path,
            *seek,
            "-i",
            audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            # Video is stream-copied: this is the cheap half of the split, and
            # re-encoding here would defeat the entire point of render_silent.
            "-c:v",
            "copy",
            *audio_args,
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
        window = brief.output.window
        mux_audio(
            silent_path,
            edl.audio_path,
            output_path,
            brief.output.encode,
            audio_start=window[0] if window else 0.0,
            windowed=window is not None,
        )
    finally:
        if not keep_work_dir and os.path.exists(silent_path):
            os.remove(silent_path)
    return output_path


def _render_segment(
    ffmpeg: str,
    cut: Cut,
    station: StationConfig,
    w: int,
    h: int,
    fps: int,
    out_path: str,
    enc: EncodeConfig | None = None,
) -> None:
    enc = enc or EncodeConfig()
    duration = cut.duration
    is_video = os.path.splitext(cut.source_path)[1].lower() in VIDEO_EXTS

    framing = cut.framing or FramingConfig()
    linear_chain = [_framing_filter(framing, w, h, fps), fx.color_grade(station)]
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
            *_video_encode_args(enc),
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
                *_video_encode_args(enc),
                "-an",
                dst,
            ],
        )


class _WorkDirectory:
    """A directory for intermediate render artifacts. An explicit `work_dir`
    is kept (pass `keep_work_dir=True` to inspect the per-cut segments);
    otherwise a temp dir is created
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
