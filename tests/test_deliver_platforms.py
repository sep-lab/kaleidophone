"""render/deliver.py, issue #57: one render and one cover to every platform.

The same rule as tests/test_deliver.py: ffmpeg never runs. run() and
run_measure() record their argv (FakeFfmpeg, from that module), ffprobe is
a stand-in that answers per file name, the --dry-run script runs under sh
with a stand-in ffmpeg, and the covers are Pillow's work on pictures drawn
in code. What is pinned: which picture is stream-copied and which is
scaled (and how), that every output is held to its platform before and
after, the names (#34), the covers (#27), the manifest, and that --dry-run
still runs the same ffmpeg commands and still can't be made to run anything
else.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import shutil
import subprocess
import zlib

import pytest
import yaml
from PIL import Image
from test_deliver import (
    FakeFfmpeg,
    arg_after,
    loudnorm_log,
    needs_sh,
    outside_the_manifest,
    rel_sheet,
    run_script,
    write_sheet,
    write_variants,
)

from kaleidophone import cli
from kaleidophone.render import deliver as dv
from kaleidophone.render import platforms as pf

STREAM = {
    "codec_name": "h264", "profile": "High", "level": "31", "pix_fmt": "yuv420p", "r_frame_rate": "24/1",
    "time_base": "1/12288", "sample_aspect_ratio": "1:1", "start_time": "0.000000",
}


class Probe:
    """ffprobe for these tests: every file the render's size at 24 fps unless
    `sizes` says otherwise, 192 frames unless `frames` does, an AAC stream
    unless its name is in `silent`."""

    def __init__(self) -> None:
        self.size = (1080, 1920)
        self.sizes: dict[str, tuple[int, int]] = {}
        self.frames: dict[str, str] = {}
        self.silent: set[str] = set()
        self.rate = "24/1"

    def stream(self, path, stream, entry, count_packets=False):
        name = os.path.basename(path)
        if entry == "nb_read_packets":
            return self.frames.get(name, "192")
        width, height = self.sizes.get(name, self.size)
        if entry == "width,height,r_frame_rate":
            return f"{width},{height},{self.rate}"
        if entry in ("width", "height"):
            return str(width if entry == "width" else height)
        if stream == "a:0":
            return None if name in self.silent else "aac"
        return STREAM.get(entry)


@pytest.fixture
def fake(monkeypatch):
    ff = FakeFfmpeg(loudnorm=loudnorm_log("-8.81", "-0.30"))
    monkeypatch.setattr(dv, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(dv, "run", ff.run)
    monkeypatch.setattr(dv, "run_measure", ff.run_measure)
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset({"limit", "latency"}))
    monkeypatch.setattr(dv, "decode_f32le", lambda *a, **k: b"")
    monkeypatch.setattr(dv, "probe_duration", lambda path: 300.0)
    monkeypatch.setattr(dv, "probe_keyframes", lambda path: [0.0, 2.0, 10.0, 16.0, 26.25, 51.0, 53.0, 61.0, 67.0])
    ff.probe = Probe()
    monkeypatch.setattr(dv, "probe_stream", ff.probe.stream)
    return ff


@pytest.fixture
def media(tmp_path):
    """Placeholders where the sheet's inputs are expected -- a few bytes of nothing, never media."""
    (tmp_path / "_work").mkdir()
    for name in ("_work/full_silent.mp4", "_work/card_silent.mp4", "Song.wav"):
        (tmp_path / name).write_bytes(b"placeholder")
    return tmp_path


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def sheet(cuts: str, *, size: str | None = "1080x1920", title: str | None = "Song", covers: str | None = None,
          **extra) -> str:
    lines = [f"title: {json.dumps(title)}"] if title is not None else []
    lines += ["silent: _work/full_silent.mp4", "audio: Song.wav", "fps: 24", "gain: {mode: auto}"]
    lines += [f"size: {size}"] if size else []
    lines += [f"{k}: {v}" for k, v in extra.items()]
    lines += [f"covers: {covers}"] if covers else []
    return "\n".join(lines) + "\ncuts:\n" + cuts


LOOP = "  - {name: loop, t0: 2, dur: 8, platforms: [ig-reel, tiktok, youtube-short, canvas]}\n"
FILM = "  - {name: film, t0: 0, dur: 16, platform: youtube-video, reframe: pad-blur}\n"


def picture(path, width: int, height: int) -> None:
    """A synthetic cover: two flat halves, drawn in code."""
    img = Image.new("RGB", (width, height), (200, 80, 60))
    img.paste((40, 90, 200), (0, height // 2, width, height))
    img.save(path, compress_level=1)


def manifest_of(directory, name="song.delivery.json") -> dict:
    return json.loads((directory / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# the sheet
# --------------------------------------------------------------------------
def test_a_cut_names_its_platforms_by_id_or_alias_and_the_sheet_the_renders_size(tmp_path):
    s = dv.load_sheet(write_sheet(tmp_path, sheet(LOOP + FILM, size=" 1080 X 1920 ")))
    loop, film = s.cuts
    assert loop.targets == ("instagram-reel", "tiktok", "youtube-short", "spotify-canvas")
    assert film.targets == ("youtube-video",) and film.reframe == "pad-blur" and film.label == "film"
    assert s.size == "1080x1920" and s.frame == (1080, 1920) and s.file_stem == "song"
    assert loop.voiced and not dv.load_sheet(write_sheet(tmp_path, sheet(
        "  - {name: c, t0: 2, dur: 8, platform: spotify-canvas}\n"))).cuts[0].voiced


def test_a_field_written_null_is_a_field_left_out(tmp_path):
    text = "title: Song\nsilent: s.mp4\naudio: a.wav\nsize: null\ncuts:\n  - {name: a, out: null, platforms: null, t0: 0, dur: 1}\n"
    s = dv.load_sheet(write_sheet(tmp_path, text))
    assert s.size is None and s.cuts[0].out is None and s.cuts[0].targets == ()


def test_a_sheet_of_cuts_that_go_only_where_audio_isnt_taken_needs_no_master(tmp_path):
    text = "title: Song\nsilent: s.mp4\nsize: 1080x1920\ncuts:\n  - {name: c, t0: 0, dur: 8, platform: canvas}\n"
    assert dv.load_sheet(write_sheet(tmp_path, text)).audio is None


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (sheet("  - {t0: 0, dur: 8, platform: tiktok}\n"), r"a cut needs `out` \(its file\) or `name`"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok, platforms: [ig-reel]}\n"), "`platform` or `platforms`, not both"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: ig-reels}\n"), r"unknown platform 'ig-reels' -- did you mean ig-reel"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: spotify-cover}\n"), r"spotify-cover is an image: it goes in `covers.platforms`"),
        (sheet("  - {name: a, t0: 0, dur: 8, platforms: [ig-reel, instagram-reel]}\n"), "instagram-reel is listed twice"),
        (sheet("  - {name: a, t0: 0, dur: 8, platforms: []}\n"), "`platforms` lists no platforms"),
        (sheet("  - {name: a, t0: 0, dur: 8, reframe: crop}\n"), r"a: `reframe` fits the render to a platform's frame -- it needs `platform`"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: youtube, reframe: crop, pad_color: '#ffffff'}\n"),
         "pad_color is the colour of `reframe: pad-color`'s bars"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: youtube, reframe: pad-color, pad_color: white}\n"), "not a colour"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: youtube, reframe: blur}\n"), "reframe"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok}\n", size="1080by1920"), "is not a frame size"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok}\n", size="1080x0"), "is not a frame size"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok}\n", size=None),
         r"`size` \(the silent render's, WxH\) is required: a goes to a platform"),
        (sheet("  - {name: a, t0: 0, dur: 8}\n", title=None), r"`title` is required: a has no `out`"),
        (sheet("  - {name: a, t0: 0, dur: 8}\n  - {name: b, t0: 0, dur: 8}\n", title=None), "a, b have no `out`"),
        (sheet("  - {out: a.mp4, t0: 0, dur: 8}\n", title=None, covers="{master: c.png, platforms: [spotify-cover]}"),
         r"`title` is required: covers are named <title>.cover.<platform>.jpg"),
        (sheet("  - {name: a, t0: 0, dur: 8}\n", title="( - )"), r"title '\( - \)' has no letter or digit .* give `slug`"),
        (sheet("  - {name: a, t0: 0, dur: 8}\n", slug="a/b"), "slug 'a/b' must be a plain name"),
        (sheet("  - {name: a, t0: 0, dur: 8}\n", title=" "), "title is empty"),
        (sheet("  - {name: .a, t0: 0, dur: 8}\n"), "name '.a' must be a plain name"),
        ("title: Song\ncuts: []\n", "nothing to deliver: `cuts` is empty and there are no `covers`"),
        (sheet("  - {name: c, t0: 0, dur: 8, platform: canvas, fade_out: 1}\n"),
         "c: spotify-canvas takes no audio, so it has no audio to fade -- drop fade_out"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok}\n",
               covers="{master: c.png, portrait: p.png, platforms: [spotify-cover]}"),
         r"`portrait` is for the 9:16 covers, and none is asked for \(instagram-reel-cover, youtube-short-thumbnail\)"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok}\n", covers="{master: c.png, platforms: [tiktok]}"),
         r"tiktok is a video: it goes in a cut's `platform`"),
        (sheet("  - {name: a, t0: 0, dur: 8, platform: tiktok}\n",
               covers="{master: c.png, platforms: [spotify-cover], background: white}"),
         r"covers.background 'white' is not a colour -- use #rrggbb"),
        (sheet("  - {name: a, t0: 0, dur: 8, platforms: [tiktok]}\n  - {name: a, t0: 2, dur: 8, platform: tiktok}\n"),
         r"two cuts write 'song.a.tiktok.mp4'"),
        (sheet("  - {out: x.mp4, t0: 0, dur: 8, platforms: [tiktok]}\n  - {out: x.tiktok.mp4, t0: 2, dur: 8}\n"),
         r"two cuts write 'x.tiktok.mp4'"),
    ],
)
def test_a_platform_sheet_that_cant_be_delivered_says_why(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        dv.load_sheet(write_sheet(tmp_path, text))


@pytest.mark.parametrize(
    ("title", "slug"),
    [("SHOULD I ?", "should-i"), ("Same As You", "same-as-you"), ("( - )", ""), ("a__b..c", "a-b-c"),
     ("HAMECHI MANZOR DARE", "hamechi-manzor-dare"), ("آهنگ‌های تازه", "آهنگ-های-تازه")],
)
def test_a_title_becomes_the_start_of_a_file_name(title, slug):
    assert dv.slugify(title) == slug


def test_a_slug_names_files_when_the_title_cant(tmp_path):
    s = dv.load_sheet(write_sheet(tmp_path, sheet("  - {name: reel, t0: 0, dur: 8}\n", title="( - )", slug="minus")))
    assert s.file_stem == "minus" and dv.output_name(s, s.cuts[0]) == "minus.reel.mp4"


def test_files_are_named_one_way(tmp_path):
    cuts = (
        "  - {out: reels/SONG_reel.mp4, t0: 0, dur: 8, platform: tiktok}\n"
        "  - {out: SONG_loop.MOV, t0: 2, dur: 8, platforms: [tiktok, ig-reel]}\n"
        "  - {name: story, t0: 4, dur: 8, platform: ig-story}\n"
        "  - {name: film, t0: 6, dur: 8}\n"
    )
    s = dv.load_sheet(write_sheet(tmp_path, sheet(cuts)))
    single, listed, named, plain = s.cuts
    assert dv.output_name(s, single, "tiktok") == "reels/SONG_reel.mp4"  # an explicit name is kept
    assert dv.output_name(s, single, "tiktok", "rain") == "reels/SONG_reel.rain.mp4"
    assert dv.output_name(s, listed, "tiktok") == "SONG_loop.tiktok.MOV"
    assert dv.output_name(s, listed, "instagram-reel", "rain") == "SONG_loop.instagram-reel.rain.MOV"
    assert dv.output_name(s, named, "instagram-story") == "song.story.instagram-story.mp4"
    assert dv.output_name(s, named, "instagram-story", "rain") == "song.story.instagram-story.rain.mp4"
    assert dv.output_name(s, plain) == "song.film.mp4" and dv.cut_file(s, plain) == "song.film.mp4"
    assert dv.cut_file(s, single) == "reels/SONG_reel.mp4"
    assert dv.cover_name(s, "spotify-cover") == "song.cover.spotify-cover.jpg"
    assert dv.manifest_name(s) == "song.delivery.json"
    untitled = dv.load_sheet(write_sheet(tmp_path, "silent: s.mp4\naudio: a.wav\ncuts:\n  - {out: x.mp4, t0: 0, dur: 1}\n"))
    assert dv.manifest_name(untitled) == "delivery.json"


# --------------------------------------------------------------------------
# the plan: copied, scaled or reframed -- and held to the platform
# --------------------------------------------------------------------------
def plan(tmp_path, cuts: str, **kw):
    s = dv.load_sheet(write_sheet(tmp_path, sheet(cuts, **kw)))
    outputs = dv._outputs(s, {})
    return s, outputs, dv._plan_findings(s, outputs)


def test_a_render_at_a_size_the_platform_documents_is_stream_copied(tmp_path):
    _, outputs, found = plan(tmp_path, LOOP)
    assert [(o.out, o.reframe, o.has_audio) for o in outputs] == [
        ("song.loop.instagram-reel.mp4", None, True), ("song.loop.tiktok.mp4", None, True),
        ("song.loop.youtube-short.mp4", None, True), ("song.loop.spotify-canvas.mp4", None, False),
    ]
    assert found == [[], [], [], []]
    _, (film,), _ = plan(tmp_path, "  - {name: film, t0: 0, dur: 16, platform: youtube}\n", size="1920x1080")
    assert film.reframe is None  # 1080p is a size YouTube lists


@pytest.mark.parametrize(
    ("size", "platform", "target", "graph"),
    [
        ("2160x3840", "instagram-reel", (1080, 1920), "[0:v:0]scale=1080:1920:flags=lanczos,setsar=1[v]"),
        ("2160x2160", "youtube-short", (1080, 1080), "[0:v:0]scale=1080:1080:flags=lanczos,setsar=1[v]"),
        ("960x540", "youtube-video", (3840, 2160), "[0:v:0]scale=3840:2160:flags=lanczos,setsar=1[v]"),
    ],
)
def test_a_render_of_the_platforms_shape_is_scaled_to_its_size_in_that_shape(tmp_path, size, platform, target, graph):
    _, (output,), _ = plan(tmp_path, f"  - {{name: a, t0: 0, dur: 8, platform: {platform}}}\n", size=size)
    assert output.reframe.how == "scale" and output.reframe.target == target and output.reframe.graph == graph


def test_another_shape_is_fitted_the_way_the_cut_says(tmp_path):
    cuts = "".join(
        f"  - {{name: {how}, t0: 0, dur: 8, platform: youtube-video, reframe: {how}}}\n"
        for how in ("crop", "pad-color", "pad-blur")
    )
    _, (crop, bars, blur), found = plan(tmp_path, cuts.replace("reframe: pad-color", "reframe: pad-color, pad_color: '#1A2B3C'"))
    assert crop.reframe.graph == "[0:v:0]scale=3840:6828:flags=lanczos,crop=3840:2160:0:2334,setsar=1[v]"
    assert bars.reframe.graph == "[0:v:0]scale=1216:2160:flags=lanczos,pad=3840:2160:1312:0:color=0x1a2b3c,setsar=1[v]"
    # The copy behind the picture: blurred by 6 % of the frame's width (28.8 px in the 480x270
    # frame it is blurred in, 230 px at 3840), darkened and half desaturated -- atmosphere, not
    # a second picture.
    assert blur.reframe.graph == (
        "[0:v:0]split=2[bg][fg];[bg]scale=480:854:flags=lanczos,crop=480:270:0:292,gblur=sigma=28.8,"
        "eq=brightness=-0.12:saturation=0.5,scale=3840:2160:flags=bicubic[blur];[fg]scale=1216:2160:flags=lanczos[pic];"
        "[blur][pic]overlay=1312:0,setsar=1[v]"
    )
    assert [(f.level, f.rule) for f in found[0]] == [("warn", "picture"), ("info", "picture")]
    assert found[0][1].message == "crop keeps the centre 1080x607 of the 1080x1920 render"
    assert found[2][0].message == (
        "the picture is enlarged 1.13x (1080x1920 scaled to 1216x2160, Lanczos, over a blurred copy of itself "
        "filling 3840x2160): rendered at 1216x2160 or more, it wouldn't be"
    )
    assert "on 3840x2160 with bars" in bars.reframe.describe() and "cropped to 3840x2160" in crop.reframe.describe()
    _, (wide,), found = plan(tmp_path, "  - {name: a, t0: 0, dur: 8, platform: ig-reel, reframe: pad-blur}\n", size="3840x2160")
    assert wide.reframe.drawn == (1080, 608) and found == [[]]  # drawn smaller: nothing enlarged


def test_a_shape_the_cut_doesnt_say_how_to_fit_is_refused_before_anything_runs(media, fake):
    text = sheet("  - {name: film, t0: 0, dur: 8, platform: youtube-video}\n" + LOOP)
    with pytest.raises(ValueError) as exc:
        dv.deliver(write_sheet(media, text))
    assert str(exc.value).splitlines() == [
        "the platforms won't take what the sheet asks of them:",
        "  song.film.youtube-video.mp4 (youtube-video): youtube-video is 16:9 (3840x2160) and the render is "
        "1080x1920: say how to fit it -- reframe: pad-blur (the picture centred over a blurred copy of itself), "
        "pad-color (bars) or crop",
    ]
    assert fake.runs == [] and fake.measures == []


def test_a_reframe_nothing_needs_is_refused(tmp_path):
    text = sheet("  - {name: loop, t0: 2, dur: 8, platforms: [ig-reel, tiktok], reframe: crop}\n")
    with pytest.raises(ValueError, match=r"reframe: crop has nothing to fit: the render \(1080x1920\) is already the "
                                         r"shape of every platform the cut goes to -- drop it"):
        dv.delivery_script(write_sheet(tmp_path, text))


def test_what_a_platform_wont_take_is_refused_all_at_once(tmp_path):
    cuts = (
        "  - {name: long, t0: 0, dur: 30, platforms: [canvas, ig-story]}\n"
        "  - {name: square, t0: 0, dur: 10, platform: apple-motion-square, reframe: crop}\n"
    )
    with pytest.raises(ValueError) as exc:
        dv.delivery_script(write_sheet(tmp_path, sheet(cuts, fps=60)))
    assert str(exc.value).splitlines()[1:] == [
        "  song.long.spotify-canvas.mp4 (spotify-canvas): 30.000 s is longer than 8 s: Spotify Canvas takes 3 s to 8 s",
        "  song.square.apple-music-motion-square.mp4 (apple-music-motion-square): 60 fps isn't a rate Apple Music "
        "motion art, square takes (23.976, 24, 25, 29.97 or 30)",
    ]


def test_warnings_go_ahead_and_are_said(media, fake):
    logged = []
    dv.deliver(write_sheet(media, sheet("  - {name: reel, t0: 0, dur: 200, platform: ig-reel}\n")), log=logged.append)
    assert "warning: song.reel.instagram-reel.mp4 (instagram-reel): 200.000 s is over 3 min: Instagram recommends " \
        "Reels under 3 min to reach non-followers; up to 15 min is allowed (20 min from the app's camera since " \
        "Nov 2025)" in logged


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def test_one_cut_to_four_platforms_one_gain_the_canvas_silent(media, fake):
    fake.probe.silent.add("song.loop.spotify-canvas.mp4")
    fake.integrated = "-9.0"
    results = dv.deliver(write_sheet(media, sheet(LOOP)))
    reel, tiktok, short, canvas = results
    assert [os.path.basename(r.out) for r in results] == [
        "song.loop.instagram-reel.mp4", "song.loop.tiktok.mp4", "song.loop.youtube-short.mp4",
        "song.loop.spotify-canvas.mp4",
    ]
    assert [r.platform for r in results] == ["instagram-reel", "tiktok", "youtube-short", "spotify-canvas"]
    assert {arg_after(a, "-af").split(",")[0] for a in fake.encodes} == {"volume=0.00dB"}  # one gain for all
    assert len(fake.encodes) == 3 and arg_after(fake.encodes[0], "-c:v") == "copy"
    (silent,) = fake.silent_cuts
    assert silent[-1].endswith("song.loop.spotify-canvas.mp4") and "-an" in silent
    assert not canvas.has_audio and canvas.audio_stream is False and canvas.findings == []
    assert (reel.width, reel.height, reel.fps, reel.audio_stream, reel.size_bytes) == (1080, 1920, 24.0, True, 2048)
    assert reel.cut == "loop" and reel.picture == "copy" and reel.findings == [] and tiktok.findings == []
    (loud,) = short.findings
    assert loud.rule == "loudness" and "YouTube will turn this down by ~5.0 dB" in loud.message
    assert results.covers == [] and results.manifest == str(media / "song.delivery.json")


def test_a_reframed_picture_is_made_once_and_every_round_stream_copies_it(media, fake):
    fake.peaks = [-1.0, -3.0]  # one round over the ceiling: the reframe still runs once
    fake.probe.sizes["song.film.youtube-video.mp4"] = (3840, 2160)
    (film,) = dv.deliver(write_sheet(media, sheet(FILM)))
    reframe, mux, again = fake.runs
    assert reframe[:2] == ["-y", "-i"] and arg_after(reframe, "-i").endswith("_work/full_silent.mp4")
    assert arg_after(reframe, "-filter_complex").startswith("[0:v:0]split=2[bg][fg];")
    assert arg_after(reframe, "-map") == "[v]" and arg_after(reframe, "-frames:v") == "384"
    assert arg_after(reframe, "-c:v") == "libx264" and arg_after(reframe, "-crf") == "18"
    assert (arg_after(reframe, "-g"), arg_after(reframe, "-bf")) == ("12", "2")  # YouTube's closed GOP of half the rate
    assert "-an" in reframe and reframe[-1].endswith(".kaleidophone-cache/deliver/cut01.youtube-video.mp4")
    for encode in (mux, again):
        assert arg_after(encode, "-i", 0) == reframe[-1] and "-ss" not in encode  # from song time 0: no seek
        assert arg_after(encode, "-c:v") == "copy" and arg_after(encode, "-frames:v") == "384"
    assert film.picture == "pad-blur" and not (media / ".kaleidophone-cache").exists()
    assert [f.rule for f in film.findings] == ["picture", "loudness"]


def test_each_platform_gets_its_own_encoder_settings(media, fake):
    cuts = (
        "  - {name: reel, t0: 0, dur: 8, platform: ig-reel}\n"
        "  - {name: motion, t0: 2, dur: 10, platform: apple-motion-square, reframe: pad-blur}\n"
    )
    fake.probe.size = (2160, 3840)
    dv.deliver(write_sheet(media, sheet(cuts, size="2160x3840")))
    reel, motion = (a for a in fake.runs if "-filter_complex" in a)
    assert (arg_after(reel, "-crf"), arg_after(reel, "-maxrate"), arg_after(reel, "-bufsize")) == ("18", "25M", "50M")
    assert "-g" not in reel and "-b:v" not in reel
    assert arg_after(motion, "-b:v") == "72.5M" and "-crf" not in motion
    assert "-maxrate" not in motion and "-bufsize" not in motion  # no VBV buffer: x264 repeats its bytes without one
    assert arg_after(motion, "-ss") == "2.000000"  # an input seek: decoded from the keyframe before, frame-exact
    assert arg_after(motion, "-filter_complex").endswith("[blur][pic]overlay=840:0,setsar=1[v]")
    assert len(fake.silent_cuts) == 1  # Apple's motion art takes no audio


def test_a_card_cut_is_joined_first_and_reframed_from_the_join(media, fake):
    fake.probe.frames["card_silent.mp4"] = "48"
    cut = "  - {name: card, t0: 51, dur: 16, card: _work/card_silent.mp4, video_from: 53, platform: youtube, reframe: crop}\n"
    dv.deliver(write_sheet(media, sheet(cut)))
    _tail, concat, reframe, mux = fake.runs
    assert arg_after(reframe, "-i") == concat[-1] and "-ss" not in reframe[: reframe.index("-i")]
    assert arg_after(mux, "-i", 0) == reframe[-1] and arg_after(mux, "-ss") == "51.000000"


def test_endings_times_platforms_join_once_and_reframe_each(media, fake):
    write_variants(media)
    for name in ("reel.body.mp4", "reel.ending-rain.mp4", "reel.ending-door.mp4"):
        (media / "_work" / name).write_bytes(b"placeholder")
    fake.probe.frames.update({"reel.body.mp4": "240", "reel.ending-rain.mp4": "144", "reel.ending-door.mp4": "144"})
    fake.probe.frames.update({f"song.reel.{p}.{e}.mp4": "384" for p in ("tiktok", "youtube-video") for e in ("rain", "door")})
    cut = "  - {name: reel, t0: 51, dur: 16, endings: _work/reel.variants.json, platforms: [tiktok, youtube], reframe: pad-color}\n"
    results = dv.deliver(write_sheet(media, sheet(cut)))
    assert [os.path.basename(r.out) for r in results] == [
        "song.reel.tiktok.rain.mp4", "song.reel.tiktok.door.mp4",
        "song.reel.youtube-video.rain.mp4", "song.reel.youtube-video.door.mp4",
    ]
    joins = [a for a in fake.runs if "concat" in a]
    reframes = [a for a in fake.runs if "-filter_complex" in a and "pad=" in arg_after(a, "-filter_complex")]
    assert len(joins) == 2 and [os.path.basename(r[-1]) for r in reframes] == [
        "cut01.e01.youtube-video.mp4", "cut01.e02.youtube-video.mp4"
    ]
    assert [arg_after(r, "-i") for r in reframes] == [j[-1] for j in joins]
    (contact,) = [a for a in fake.runs if a[-1].endswith(".jpg")]
    assert contact[-1].endswith("song.reel.endings.jpg") and "song.reel.tiktok.rain.mp4" in arg_after(contact, "-i", 0)
    assert results[0].contact_sheet is results[3].contact_sheet and results[0].ending == "rain"


def test_a_render_or_a_part_that_isnt_the_sheets_size_is_refused(media, fake):
    fake.probe.sizes["full_silent.mp4"] = (1920, 1080)
    fake.probe.sizes["card_silent.mp4"] = (720, 1280)
    fake.probe.frames["card_silent.mp4"] = "48"
    cuts = LOOP + "  - {name: card, t0: 51, dur: 16, card: _work/card_silent.mp4, video_from: 53, platform: tiktok}\n"
    with pytest.raises(ValueError) as exc:
        dv.deliver(write_sheet(media, sheet(cuts)))
    lines = str(exc.value).splitlines()
    assert "  the silent render (full_silent.mp4) is 1920x1080; the sheet's size is 1080x1920" in lines
    assert "  card: the card (card_silent.mp4) is 720x1280; the sheet's size is 1080x1920" in lines


def test_an_endings_body_that_isnt_the_sheets_size_is_refused(media, fake):
    write_variants(media)
    for name in ("reel.body.mp4", "reel.ending-rain.mp4", "reel.ending-door.mp4"):
        (media / "_work" / name).write_bytes(b"placeholder")
        fake.probe.sizes[name] = (720, 1280)
    fake.probe.frames.update({"reel.body.mp4": "240", "reel.ending-rain.mp4": "144", "reel.ending-door.mp4": "144"})
    cut = "  - {name: reel, t0: 51, dur: 16, endings: _work/reel.variants.json, platform: tiktok}\n"
    with pytest.raises(ValueError, match=r"reel: the body \(reel.body.mp4\) is 720x1280; the sheet's size is 1080x1920"):
        dv.deliver(write_sheet(media, sheet(cut)))


def test_a_file_a_platform_wont_take_as_written_is_refused_after_and_still_written(media, fake, monkeypatch):
    monkeypatch.setitem(pf.PLATFORMS, "instagram-story", dataclasses.replace(pf.get("ig-story"), max_file_mb=0.001))
    fake.probe.sizes["song.story.instagram-story.mp4"] = (1080, 1920)
    (story,) = dv.deliver(write_sheet(media, sheet("  - {name: story, t0: 0, dur: 8, platform: ig-story}\n")))
    assert [(f.level, f.rule) for f in story.findings] == [("refuse", "file size")]
    assert "0.00 MB is over the 0.001 MB Instagram Story takes" in story.findings[0].message
    assert manifest_of(media)["findings"] == {"refuse": 1, "warn": 0, "info": 0}


def test_what_was_measured_replaces_what_was_planned(media, fake):
    """Planned at the sheet's 24 fps; written, ffprobe says 12 -- the file is what ships."""
    fake.probe.rate = "12/1"
    (reel,) = dv.deliver(write_sheet(media, sheet("  - {name: reel, t0: 0, dur: 8, platform: ig-reel}\n")))
    assert [(f.level, f.rule) for f in reel.findings] == [("refuse", "frame rate")]
    assert "12 fps is outside the 23-60 fps" in reel.findings[0].message


def test_without_the_check_the_plan_stands_and_the_loudness_is_still_compared(media, fake):
    fake.integrated = "-14.2"
    (film,) = dv.deliver(write_sheet(media, sheet(FILM, check="false")))
    assert film.width is None and film.size_bytes is None
    assert [(f.level, f.rule) for f in film.findings] == [("warn", "picture"), ("info", "loudness")]
    assert "within half a dB of YouTube's -14 LUFS" in film.findings[1].message


def test_a_silent_master_measures_no_loudness_and_the_manifest_stays_json(media, fake):
    fake.integrated = "-inf"
    fake.probe.sizes["song.film.youtube-video.mp4"] = (3840, 2160)
    (film,) = dv.deliver(write_sheet(media, sheet(FILM)))
    assert film.lufs == float("-inf") and [f.rule for f in film.findings] == ["picture"]
    artifact = manifest_of(media)["artifacts"][0]
    assert artifact["measured"]["lufs"] is None


# --------------------------------------------------------------------------
# the manifest
# --------------------------------------------------------------------------
def test_the_manifest_has_every_artifact_planned_and_measured_and_every_spec(media, fake):
    picture(media / "cover.png", 3000, 3000)
    fake.probe.silent.add("song.loop.spotify-canvas.mp4")
    fake.probe.sizes["song.film.youtube-video.mp4"] = (3840, 2160)
    covers = "{master: cover.png, platforms: [sc-artwork, ig-reel-cover]}"
    dv.deliver(write_sheet(media, sheet(LOOP + FILM, covers=covers)))
    m = manifest_of(media)
    assert (m["manifest"], m["state"], m["title"], m["sheet"]) == (1, "delivered", "Song", "deliver.yaml")
    assert m["render"] == {"file": "full_silent.mp4", "size": [1080, 1920], "fps": 24.0, "song_time": 0.0}
    assert m["master"] == {"file": "Song.wav", "mode": "auto", "lufs": -8.81, "true_peak_dbtp": -0.3, "gain_db": 0.0,
                           "limiter_dbfs": None, "ceiling_dbtp": -2.0}
    files = [a["file"] for a in m["artifacts"]]
    assert files == [
        "song.loop.instagram-reel.mp4", "song.loop.tiktok.mp4", "song.loop.youtube-short.mp4",
        "song.loop.spotify-canvas.mp4", "song.film.youtube-video.mp4", "song.cover.soundcloud-artwork.jpg",
        "song.cover.instagram-reel-cover.jpg", "song.cover.instagram-grid-thumbnail.jpg",
    ]
    canvas, film = m["artifacts"][3], m["artifacts"][4]
    assert canvas["planned"] == {"width": 1080, "height": 1920, "fps": 24.0, "frames": 192, "seconds": 8.0,
                                 "audio": False, "t0": 2.0}
    assert canvas["measured"]["audio"] is False and canvas["measured"]["lufs"] is None
    assert film["picture"] == {"how": "pad-blur", "from": [1080, 1920], "to": [3840, 2160], "drawn": [1216, 2160]}
    assert film["planned"]["width"] == 3840 and film["measured"]["bytes"] == 2048
    assert [f["rule"] for f in film["findings"]] == ["picture", "loudness"]
    grid = m["artifacts"][-1]
    assert (grid["kind"], grid["source"], grid["method"], grid["preview"]) == (
        "image", "instagram-reel-cover", "grid crop", True
    )
    assert (grid["measured"]["width"], grid["measured"]["height"], grid["measured"]["jpeg_quality"]) == (1080, 1440, 95)
    assert grid["planned"] == {"width": 1080, "height": 1440, "jpeg_quality": 95}
    assert list(m["platforms"]) == [
        "instagram-reel", "tiktok", "youtube-short", "spotify-canvas", "youtube-video", "soundcloud-artwork",
        "instagram-reel-cover", "instagram-grid-thumbnail",
    ]
    assert m["platforms"]["tiktok"] == pf.get("tiktok").to_dict()
    assert m["findings"] == {"refuse": 0, "warn": 1, "info": 3}


def test_a_plain_sheet_gets_a_manifest_too(media, fake):
    dv.deliver(write_sheet(media, "silent: _work/full_silent.mp4\naudio: Song.wav\ncuts:\n  - {out: x.mp4, t0: 0, dur: 8}\n"))
    m = manifest_of(media, "delivery.json")
    assert m["title"] is None and m["platforms"] == {} and m["artifacts"][0]["platform"] is None
    assert m["artifacts"][0]["picture"] == {"how": "copy"} and m["artifacts"][0]["planned"]["width"] is None


# --------------------------------------------------------------------------
# covers
# --------------------------------------------------------------------------
def test_a_sheet_of_covers_alone_needs_no_ffmpeg_render_or_master(tmp_path, monkeypatch):
    def no_ffmpeg():
        raise AssertionError("covers don't need ffmpeg")

    monkeypatch.setattr(dv, "require_ffmpeg", no_ffmpeg)
    picture(tmp_path / "cover.png", 3000, 3000)
    text = "title: Song\ncovers: {master: cover.png, platforms: [spotify-cover, sc-header, yt-thumbnail]}\n"
    result = dv.deliver(write_sheet(tmp_path, text), out_dir=str(tmp_path / "out"))
    assert list(result) == [] and [c.platform for c in result.covers] == ["spotify-cover", "soundcloud-header", "youtube-thumbnail"]
    assert Image.open(tmp_path / "out" / "song.cover.youtube-thumbnail.jpg").size == (3840, 2160)
    m = manifest_of(tmp_path / "out")
    assert m["render"] is None and m["master"] is None and len(m["artifacts"]) == 3
    assert m["findings"] == {"refuse": 0, "warn": 1, "info": 0}  # the header's crop


def test_a_transparent_master_is_flattened_onto_the_sheets_background(tmp_path):
    master = Image.new("RGBA", (3000, 3000), (200, 80, 60, 255))
    master.paste((0, 0, 0, 0), (0, 0, 3000, 1500))  # the top half: nothing at all
    master.save(tmp_path / "cover.png", compress_level=1)
    text = "title: Song\ncovers: {master: cover.png, platforms: [spotify-cover], background: '#203040'}\n"
    logged: list[str] = []
    dv.deliver(write_sheet(tmp_path, text), out_dir=str(tmp_path / "out"), log=logged.append)
    assert "covers.master: its transparency flattened onto #203040" in logged
    cover = Image.open(tmp_path / "out" / "song.cover.spotify-cover.jpg")
    assert all(abs(a - b) <= 3 for a, b in zip(cover.getpixel((1500, 300)), (32, 48, 64)))
    assert all(abs(a - b) <= 3 for a, b in zip(cover.getpixel((1500, 2700)), (200, 80, 60)))


def test_a_master_too_large_to_open_is_one_clean_line(here, capsys):
    """Over Pillow's decompression-bomb limit (178,956,970 pixels): a PNG whose header says
    20000x20000 -- drawn in code, 1x1 underneath -- is refused before anything is written."""
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, "PNG")
    head = bytearray(buffer.getvalue())
    head[16:24] = (20000).to_bytes(4, "big") * 2  # IHDR width, height
    head[29:33] = zlib.crc32(bytes(head[12:29])).to_bytes(4, "big")
    (here / "bomb.png").write_bytes(bytes(head))
    (here / "deliver.yaml").write_text("title: Song\ncovers: {master: bomb.png, platforms: [spotify-cover]}\n")
    assert cli.main(["deliver", "deliver.yaml"]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith("kaleidophone: error: ") and "Traceback" not in err
    assert "bomb.png has more than 178,956,970 pixels, more than Pillow will open" in err
    assert not (here / "song.cover.spotify-cover.jpg").exists()


def test_covers_are_checked_with_everything_else_before_anything_runs(media, fake):
    picture(media / "cover.png", 2000, 2000)
    covers = "{master: cover.png, platforms: [spotify-cover]}"
    with pytest.raises(ValueError, match=r"covers.master is 2000x2000; spotify-cover draws it at 3000x3000"):
        dv.deliver(write_sheet(media, sheet(LOOP, covers=covers)))
    assert fake.runs == []
    with pytest.raises(FileNotFoundError) as exc:
        dv.deliver(write_sheet(media, sheet(LOOP, covers="{master: missing.png, platforms: [spotify-cover]}")))
    assert exc.value.filename.endswith("missing.png")


def test_the_9_16_covers_come_from_the_portrait(media, fake):
    picture(media / "cover.png", 1200, 1200)
    picture(media / "portrait.png", 1080, 1920)
    covers = "{master: cover.png, portrait: portrait.png, platforms: [ig-reel-cover]}"
    results = dv.deliver(write_sheet(media, sheet(LOOP, covers=covers)))
    assert [(c.platform, c.source) for c in results.covers] == [
        ("instagram-reel-cover", "portrait"), ("instagram-grid-thumbnail", "instagram-reel-cover")
    ]


# --------------------------------------------------------------------------
# --dry-run
# --------------------------------------------------------------------------
def test_the_dry_run_plans_the_platforms_writes_the_manifest_and_leaves_the_covers(here):
    picture(here / "cover.png", 3000, 3000)
    text = sheet(LOOP + FILM, covers="{master: cover.png, platforms: [spotify-cover, ig-reel-cover]}")
    script = dv.delivery_script(rel_sheet(here, text))
    assert "# warning: song.film.youtube-video.mp4 (youtube-video): the picture is enlarged 1.13x" in script
    assert "# 3 covers, in the manifest: made by `kaleidophone deliver` (Pillow), not by this script." in script
    assert "mkdir -p -- .kaleidophone-cache/deliver\n" in script
    assert "cat > song.delivery.json <<'KALEIDOPHONE_MANIFEST'\n{\n" in script
    body = script.split("<<'KALEIDOPHONE_MANIFEST'\n")[1].split("\nKALEIDOPHONE_MANIFEST\n")[0]
    m = json.loads(body)
    assert m["state"] == "planned" and m["master"]["lufs"] is None and m["artifacts"][0]["measured"] is None
    assert [a["file"] for a in m["artifacts"]][-3:] == [
        "song.cover.spotify-cover.jpg", "song.cover.instagram-reel-cover.jpg", "song.cover.instagram-grid-thumbnail.jpg"
    ]
    assert "# song.film.youtube-video.mp4: the picture for youtube-video -- 1080x1920 scaled to 1216x2160" in script
    assert "-filter_complex '[0:v:0]split=2[bg][fg];" in script
    assert "# 4/5  song.loop.spotify-canvas.mp4: 2.000-10.000 s, 192 frames, for spotify-canvas, no audio" in script
    assert "fits() {" in script and "\nREFUSED=\n" in script
    assert "fits ./song.loop.tiktok.mp4 tiktok 4096 72\n" in script
    assert "fits ./song.loop.instagram-reel.mp4 instagram-reel 300 ''\n" in script
    assert script.rstrip().endswith('[ -z "$FAILED" ] || exit 1\n[ -z "$REFUSED" ] || exit 1')
    assert str(here) not in script


def test_the_dry_run_needs_neither_the_cover_images_nor_a_check(here):
    text = sheet(LOOP, covers="{master: not-here.png, platforms: [spotify-cover]}", check="false")
    script = dv.delivery_script(rel_sheet(here, text))
    assert "fits" not in script and "REFUSED" not in script and "spotify-cover" in script


def test_the_dry_run_of_covers_alone_writes_the_manifest(here):
    script = dv.delivery_script(rel_sheet(here, "title: Song\ncovers: {master: c.png, platforms: [sc-artwork]}\n"))
    assert "\ncheck " not in script and "ffmpeg" not in script.split("KALEIDOPHONE_MANIFEST")[0]
    if shutil.which("sh"):
        proc = subprocess.run(["sh", "-c", script], cwd=here, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert manifest_of(here)["artifacts"][0]["file"] == "song.cover.soundcloud-artwork.jpg"


@needs_sh
@pytest.mark.parametrize("cuts", [LOOP + FILM, "  - {name: s, t0: 2, dur: 10, platform: apple-motion-square, reframe: crop}\n"])
def test_the_dry_run_script_runs_the_same_ffmpeg_commands_as_deliver(here, media, fake, cuts):
    """Parity, a picture reframed for its platform included: the script
    starts exactly the ffmpeg command lines deliver() does."""
    peaks = ["-1.0", "-3.0", "-2.5", "-3.1", "-4.0", "-2.9"]
    fake.peaks = [float(p) for p in peaks]
    s = rel_sheet(here, sheet(cuts, check="false"))
    dv.deliver(s)
    assert manifest_of(here)["state"] == "delivered"
    proc, ran = run_script(here, dv.delivery_script(s), peaks=peaks)
    assert proc.returncode == 0, proc.stderr
    assert [argv for argv in ran if "-h" not in argv] == fake.log
    assert manifest_of(here)["state"] == "planned"  # the script's own


@needs_sh
@pytest.mark.parametrize(("size", "limit", "out"), [(3_000_001, "3 ''", "refuse"), (2_500_000, "'' 2", "warning"),
                                                     (1_000_000, "3 2", None)])
def test_the_scripts_fits_says_when_a_file_is_over_its_platforms_limit(tmp_path, size, limit, out):
    (tmp_path / "x.mp4").write_bytes(b"\0" * size)
    script = f"set -e\nREFUSED=\n{dv._SCRIPT_HELPERS['fits']}\nfits ./x.mp4 sc-artwork {limit}\necho \"R=$REFUSED\"\n"
    proc = subprocess.run(["sh", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    if out is None:
        assert proc.stderr == "" and proc.stdout == "R=\n"
    elif out == "refuse":
        assert proc.stderr == "refuse: ./x.mp4 (sc-artwork): 3.00 MB is over the 3 MB it takes\n" and proc.stdout == "R=1\n"
    else:
        assert proc.stderr == "warning: ./x.mp4 (sc-artwork): 2.50 MB is over 2 MB\n" and proc.stdout == "R=\n"


@needs_sh
def test_nothing_in_a_title_or_a_cut_name_runs_or_ends_the_manifest_early(here):
    """The title and every name reach the planned manifest as JSON under a
    quoted here-document: nothing in it expands, and no line of JSON can
    be the line that ends it."""
    (here / "_work").mkdir()
    for name in ("_work/full_silent.mp4", "Song.wav"):
        (here / name).write_bytes(b"placeholder")
    nasty = "x $(touch pwned) ${G} `touch pwned2` \"q\" 's $HOME"
    doc = {
        "title": nasty + "\nKALEIDOPHONE_MANIFEST\ntouch pwned3", "silent": "_work/full_silent.mp4", "audio": "Song.wav",
        "size": "1080x1920", "gain": {"mode": "auto"}, "slug": "song",
        "cuts": [{"name": nasty, "t0": 0, "dur": 4, "platform": "tiktok"}],
    }
    with pytest.raises(ValueError, match="control character"):
        dv.delivery_script(rel_sheet(here, yaml.safe_dump(doc)))
    doc["title"] = nasty + " KALEIDOPHONE_MANIFEST"
    script = dv.delivery_script(rel_sheet(here, yaml.safe_dump(doc)))
    commands = [line for line in outside_the_manifest(script) if "pwned" in line and not line.lstrip().startswith("#")]
    quoted = "song.x $(touch pwned) ${G} `touch pwned2` \"q\" '"
    assert commands and all(f"'./{quoted}" in line or f"'{quoted}" in line for line in commands)
    proc, _ = run_script(here, script)
    assert proc.returncode == 0, proc.stderr
    assert not any((here / p).exists() for p in ("pwned", "pwned2", "pwned3"))
    assert manifest_of(here)["title"] == nasty + " KALEIDOPHONE_MANIFEST"
    assert (here / f"song.{nasty}.tiktok.mp4").exists()


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------
def test_deliver_reports_the_covers_their_findings_and_the_manifest(here, monkeypatch, capsys):
    (here / "deliver.yaml").write_text("title: Song\ncovers: {master: c.png, platforms: [sc-header]}\n")
    header = pf.Finding("warn", "soundcloud-header", "crop", "check the crop")
    cover = dv.matrix.Cover("out/song.cover.soundcloud-header.jpg", "soundcloud-header", "master", "centre band",
                            False, 2480, 520, 600_000, 95, [header])
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: dv.Delivery([], [cover], "out/song.delivery.json"))
    assert cli.main(["deliver", "deliver.yaml"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "wrote out/song.cover.soundcloud-header.jpg (2480x520, 0.60 MB, JPEG quality 95; soundcloud-header)",
        "warning: song.cover.soundcloud-header.jpg (soundcloud-header): check the crop",
        "manifest out/song.delivery.json",
    ]


def test_deliver_fails_when_a_platform_wont_take_a_file_as_written(here, monkeypatch, capsys):
    (here / "deliver.yaml").write_text(sheet("  - {name: story, t0: 0, dur: 8, platform: ig-story}\n"))
    over = pf.Finding("refuse", "instagram-story", "file size", "120.00 MB is over the 100 MB Instagram Story takes")
    story = dv.Delivered("song.story.instagram-story.mp4", 192, findings=[over], platform="instagram-story",
                         picture="scale", frames=192)
    big = dv.matrix.Cover("song.cover.soundcloud-artwork.jpg", "soundcloud-artwork", "master", "scale", False, 800,
                          800, 3_000_000, 50, [pf.Finding("refuse", "soundcloud-artwork", "file size", "too big")])
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: dv.Delivery([story], [big], "song.delivery.json"))
    assert cli.main(["deliver", "deliver.yaml"]) == cli.EXIT_ERROR
    captured = capsys.readouterr()
    assert "wrote song.story.instagram-story.mp4 (192 frames, gain +0.00 dB, picture scale)" in captured.out
    assert "refuse: song.story.instagram-story.mp4 (instagram-story): 120.00 MB is over the 100 MB" in captured.out
    assert "a platform won't take these files as delivered: song.story.instagram-story.mp4 (instagram-story): " \
           "120.00 MB is over the 100 MB Instagram Story takes; song.cover.soundcloud-artwork.jpg " \
           "(soundcloud-artwork): too big. The files are written, and the manifest has every finding." in captured.err


def test_deliver_dry_run_of_a_platform_sheet_prints_only_the_script(here, capsys):
    (here / "deliver.yaml").write_text(sheet(LOOP))
    assert cli.main(["deliver", "deliver.yaml", "--dry-run"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert captured.out.startswith("#!/bin/sh\n") and "KALEIDOPHONE_MANIFEST" in captured.out and captured.err == ""
