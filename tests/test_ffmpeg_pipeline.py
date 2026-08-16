"""render/ffmpeg_pipeline.py: the argv it builds, without invoking ffmpeg.

This module was at 0% coverage while being the one that decides what every
pixel of the output looks like. `run()` and `require_ffmpeg()` are
monkeypatched to record their arguments instead of shelling out, so the whole
suite stays true to the project's rule that pytest never calls ffmpeg (see
AGENTS.md, "Testing") while still pinning the things that have actually gone
wrong here: frame counts, quoting, and the stream-copy in mux_audio.
"""

from __future__ import annotations

import pytest
from factories import make_brief, make_station

from kaleidophone.render import ffmpeg_pipeline as fp
from kaleidophone.timeline.model import EDL, Cut


@pytest.fixture
def calls(monkeypatch):
    """Record every ffmpeg invocation instead of running one."""
    recorded: list[list[str]] = []
    monkeypatch.setattr(fp, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(fp, "run", lambda ffmpeg, args: recorded.append(args))
    monkeypatch.setattr(fp, "probe_duration", lambda path: None)
    return recorded


def _edl(*cuts: Cut, fps: int = 24, resolution: tuple[int, int] = (640, 360)) -> EDL:
    return EDL(
        song_title="t",
        audio_path="/audio/song.wav",
        duration=sum(c.duration for c in cuts),
        fps=fps,
        resolution=resolution,
        cuts=cuts,
    )


def _cut(index: int, start: float, end: float, source: str = "/media/a.jpg", **kw) -> Cut:
    fields = {"station": "s", "section": "SEC", "effects": ()}
    fields.update(kw)
    return Cut(index=index, start=start, end=end, source_path=source, **fields)


def _brief():
    return make_brief(stations=[make_station(name="s", grain=0.0, vignette=0.0)])


def _arg_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


# --- frame counts --------------------------------------------------------
#
# The load-bearing property. See docs/ARCHITECTURE.md, "Frame-accurate cuts":
# passing a duration in seconds made ffmpeg truncate a fractional frame on
# every cut, always downward, for 3.25s of drift over a 640-cut render.


def test_a_segment_is_bounded_by_an_exact_frame_count_not_a_duration(calls, tmp_path):
    fp.render_silent(_edl(_cut(0, 0.0, 0.5)), _brief(), str(tmp_path / "s.mp4"))
    segment = calls[0]
    assert "-frames:v" in segment
    assert _arg_after(segment, "-frames:v") == "12"  # 0.5s x 24fps
    assert "-t" not in segment  # a duration in seconds is what caused the drift


@pytest.mark.parametrize(
    ("duration", "fps", "expected"),
    [(1.0, 24, "24"), (0.5, 24, "12"), (1.0, 30, "30"), (2.0, 25, "50")],
)
def test_frame_count_follows_the_edls_own_fps(calls, tmp_path, duration, fps, expected):
    edl = _edl(_cut(0, 0.0, duration), fps=fps)
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"))
    assert _arg_after(calls[0], "-frames:v") == expected


def test_a_zero_length_cut_still_renders_at_least_one_frame(calls, tmp_path):
    fp.render_silent(_edl(_cut(0, 0.0, 0.0)), _brief(), str(tmp_path / "s.mp4"))
    assert _arg_after(calls[0], "-frames:v") == "1"


# --- source handling -----------------------------------------------------


def test_a_still_image_is_looped_and_a_video_is_stream_looped(calls, tmp_path):
    edl = _edl(_cut(0, 0.0, 1.0, "/media/a.jpg"), _cut(1, 1.0, 2.0, "/media/b.mp4"))
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"))
    image_seg, video_seg = calls[0], calls[1]

    assert "-loop" in image_seg and _arg_after(image_seg, "-loop") == "1"
    # A clip shorter than its cut used to end early and silently shorten the
    # segment; -stream_loop fills it instead.
    assert "-stream_loop" in video_seg and _arg_after(video_seg, "-stream_loop") == "-1"


def test_source_paths_are_absolute_so_a_leading_dash_is_not_read_as_a_flag(calls, tmp_path):
    fp.render_silent(_edl(_cut(0, 0.0, 1.0, "media/-weird.jpg")), _brief(), str(tmp_path / "s.mp4"))
    assert _arg_after(calls[0], "-i").startswith("/")


def test_scale_crop_and_fps_are_in_the_linear_filter_chain(calls, tmp_path):
    edl = _edl(_cut(0, 0.0, 1.0), resolution=(1280, 720), fps=30)
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"))
    vf = _arg_after(calls[0], "-vf")
    assert "scale=1280:720" in vf
    assert "crop=1280:720" in vf
    assert "fps=30" in vf


# --- effects: linear vs graph -------------------------------------------


def test_linear_effects_join_the_single_vf_chain(calls, tmp_path):
    edl = _edl(_cut(0, 0.0, 1.0, effects=("grain", "scanlines")))
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"))
    vf = _arg_after(calls[0], "-vf")
    assert "noise=" in vf and "drawgrid=" in vf
    assert not any("-filter_complex" in a for a in calls[0])


def test_each_graph_effect_gets_its_own_pass(calls, tmp_path):
    """N graph effects means N+1 ffmpeg calls for that segment, chained through
    stage files -- see render/effects.py's module docstring for why they can't
    share the linear chain."""
    edl = _edl(_cut(0, 0.0, 1.0, effects=("kaleidoscope", "halation")))
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"))

    segment_calls = [c for c in calls if "-filter_complex" in c]
    assert len(segment_calls) == 2
    # Each graph pass reads the previous stage's output.
    assert _arg_after(segment_calls[1], "-i") == segment_calls[0][-1]


def test_an_unknown_effect_name_is_ignored_rather_than_crashing_the_render(calls, tmp_path):
    edl = _edl(_cut(0, 0.0, 1.0, effects=("not_a_real_effect",)))
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"))
    assert calls  # rendered anyway


# --- the concat list -----------------------------------------------------


def test_concat_list_escapes_apostrophes_in_the_work_directory_path(calls, tmp_path):
    """The concat list holds the generated segment paths, so what has to be
    escaped is the *work directory* -- e.g. TMPDIR under "/Users/me/Dad's
    scratch", or an explicit work_dir. Unescaped, the apostrophe closes the
    token early and ffmpeg tries to open a path that doesn't exist.

    (Source media paths do NOT need this: they're passed to ffmpeg as argv
    elements, never through a file the demuxer re-parses.)
    """
    work = tmp_path / "Dad's work"
    edl = _edl(_cut(0, 0.0, 1.0))
    fp.render_silent(edl, _brief(), str(tmp_path / "s.mp4"), work_dir=str(work), keep_work_dir=True)

    listing = (work / "concat.txt").read_text()
    assert "'\\''" in listing  # ffmpeg's concat escaping, not the shell's
    assert "Dad" in listing


def test_concat_quote_leaves_an_ordinary_path_alone():
    assert fp._concat_quote("/media/plain.mp4") == "'/media/plain.mp4'"


def test_concat_quote_escapes_every_apostrophe():
    assert fp._concat_quote("/a'b'c") == "'/a'\\''b'\\''c'"


# --- mux_audio -----------------------------------------------------------


def test_mux_audio_stream_copies_the_video_and_re_encodes_only_audio(calls):
    """The entire cheap-resync workflow (ADR-0001) depends on the video side
    never being re-encoded here."""
    fp.mux_audio("/tmp/silent.mp4", "/tmp/song.wav", "/tmp/master.mp4")
    args = calls[0]
    assert _arg_after(args, "-c:v") == "copy"
    assert _arg_after(args, "-c:a") == "aac"
    assert args[-1] == "/tmp/master.mp4"


def test_mux_audio_warns_when_the_streams_disagree_in_length(monkeypatch, capsys):
    monkeypatch.setattr(fp, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(fp, "run", lambda ffmpeg, args: None)
    durations = {"/tmp/silent.mp4": 100.0, "/tmp/song.wav": 130.0}
    monkeypatch.setattr(fp, "probe_duration", durations.get)

    fp.mux_audio("/tmp/silent.mp4", "/tmp/song.wav", "/tmp/master.mp4")

    err = capsys.readouterr().err
    assert "audio is 30.00s longer" in err
    assert "kaleidophone compose" in err  # tells the user what to actually do


def test_mux_audio_stays_quiet_when_the_streams_agree(monkeypatch, capsys):
    monkeypatch.setattr(fp, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(fp, "run", lambda ffmpeg, args: None)
    monkeypatch.setattr(fp, "probe_duration", {"a": 100.0, "b": 100.2}.get)

    fp.mux_audio("a", "b", "/tmp/master.mp4")

    assert capsys.readouterr().err == ""


def test_render_removes_the_intermediate_silent_file(calls, tmp_path, monkeypatch):
    out = tmp_path / "master.mp4"
    silent = tmp_path / "master.mp4.silent.mp4"
    monkeypatch.setattr(fp, "run", lambda ffmpeg, args: silent.write_text("x"))

    fp.render(_edl(_cut(0, 0.0, 1.0)), _brief(), str(out))

    assert not silent.exists()
