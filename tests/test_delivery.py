"""
Delivery controls: framing, encode profile, and the song window.

These are the fields that turn "a rendered video" into "a deliverable" -- the
frame shape a platform wants, the bitrate ceiling it will accept, and the
stretch of the song a cutdown actually uses.

Same rule as the rest of the ffmpeg-facing suite: never invoke ffmpeg, assert
on the argv it would have been given. See tests/test_ffmpeg_pipeline.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaleidophone.render import ffmpeg_pipeline as fp
from kaleidophone.timeline.compose import compose
from kaleidophone.timeline.model import EDL, Cut
from kaleidophone.timeline.schema import (
    ASPECT_RESOLUTIONS,
    EncodeConfig,
    FramingConfig,
    OutputConfig,
)
from tests.factories import make_analysis, make_brief, make_media_asset, make_section, make_station


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def capture_argv(monkeypatch):
    """Collect every argv `run()` would have handed ffmpeg."""
    calls: list[list[str]] = []
    monkeypatch.setattr(fp, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(fp, "run", lambda ffmpeg, args: calls.append(args))
    return calls


def vf_of(argv: list[str]) -> str:
    return argv[argv.index("-vf") + 1]


def flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def render_one_cut(monkeypatch, framing=None, encode=None, *, w=1080, h=1920, fps=25):
    calls = capture_argv(monkeypatch)
    cut = Cut(0, 0.0, 1.0, "a.jpg", "s", "sec", framing=framing)
    fp._render_segment("ffmpeg", cut, make_station("s"), w, h, fps, "o.mp4", encode)
    return calls


# --------------------------------------------------------------------------
# framing
# --------------------------------------------------------------------------
def test_fill_is_the_default_and_matches_the_pre_framing_behaviour(monkeypatch):
    """A brief that never mentions framing must render exactly as it did before
    framing existed -- this field is opt-in, not a silent change to every edit."""
    calls = render_one_cut(monkeypatch, framing=None, w=1280, h=720, fps=24)
    assert vf_of(calls[0]).startswith(
        "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=24"
    )


def test_crop_mode_takes_a_full_height_slice_at_x():
    """`ih` is evaluated by ffmpeg against the real input, so one brief works
    across sources of different heights."""
    f = fp._framing_filter(FramingConfig(mode="crop", x=700), 1080, 1920, 25)
    assert f == "crop=ih*1080/1920:ih:700:0,scale=1080:1920:flags=lanczos,fps=25"


def test_window_mode_scales_down_and_pads_onto_black():
    f = fp._framing_filter(FramingConfig(mode="window", width=380, y_center=870), 1080, 1920, 25)
    assert f == (
        "scale=380:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:870-ih/2:color=black,fps=25"
    )


def test_window_mode_centres_vertically_when_no_y_centre_is_given():
    f = fp._framing_filter(FramingConfig(mode="window", width=380), 1080, 1920, 25)
    assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black" in f


def test_window_scale_uses_minus_two_so_the_height_stays_even():
    """h.264 chroma subsampling needs even dimensions; -1 can land on an odd
    number and ffmpeg refuses the encode."""
    assert "scale=380:-2:" in fp._framing_filter(FramingConfig(mode="window", width=380), 1080, 1920, 24)


@pytest.mark.parametrize(
    "kwargs,missing",
    [({"mode": "crop"}, "x"), ({"mode": "window"}, "width")],
)
def test_a_framing_mode_without_its_required_field_is_refused(kwargs, missing):
    with pytest.raises(ValidationError, match=missing):
        FramingConfig(**kwargs)


def test_framing_reaches_the_edl_from_the_section(monkeypatch):
    brief = make_brief(
        sections=[make_section(framing=FramingConfig(mode="crop", x=656), station="test-station")]
    )
    edl = compose(brief, make_analysis(duration=10.0), {"test-station": [make_media_asset("a.jpg")]})
    assert all(c.framing is not None and c.framing.x == 656 for c in edl.cuts)


def test_default_framing_is_left_off_the_edl_entirely():
    """So an EDL produced from a brief that predates framing is byte-identical."""
    brief = make_brief()
    edl = compose(brief, make_analysis(duration=10.0), {"test-station": [make_media_asset("a.jpg")]})
    assert all(c.framing is None for c in edl.cuts)
    assert "framing" not in edl.to_dict()["cuts"][0]


# --------------------------------------------------------------------------
# encode profile
# --------------------------------------------------------------------------
def test_encode_defaults_reproduce_the_previous_hardcoded_settings(monkeypatch):
    calls = render_one_cut(monkeypatch)
    argv = calls[0]
    assert flag(argv, "-c:v") == "libx264"
    assert flag(argv, "-preset") == "veryfast"
    assert flag(argv, "-crf") == "20"
    assert flag(argv, "-pix_fmt") == "yuv420p"
    assert "-maxrate" not in argv and "-colorspace" not in argv


def test_a_bitrate_ceiling_reaches_ffmpeg(monkeypatch):
    calls = render_one_cut(monkeypatch, encode=EncodeConfig(maxrate="4500k", bufsize="9M"))
    assert flag(calls[0], "-maxrate") == "4500k"
    assert flag(calls[0], "-bufsize") == "9M"


def test_colour_tagging_sets_all_three_tags_together(monkeypatch):
    """Half-describing a stream is worse than not describing it: a player that
    reads primaries but not trc guesses the rest."""
    calls = render_one_cut(monkeypatch, encode=EncodeConfig(color="bt709"))
    for tag in ("-colorspace", "-color_primaries", "-color_trc"):
        assert flag(calls[0], tag) == "bt709"


def test_maxrate_without_bufsize_is_refused():
    """x264 ignores a ceiling with no buffer, which looks like the setting
    silently not working."""
    with pytest.raises(ValidationError, match="must be set together"):
        EncodeConfig(maxrate="4500k")


@pytest.mark.parametrize("bad", ["fast", "4500kbps", "-1k", "; rm -rf /"])
def test_a_bitrate_that_is_not_a_bitrate_is_refused(bad):
    """These are interpolated into an ffmpeg argv and briefs are meant to be
    shared -- same reasoning as the duotone hex check. See SECURITY.md."""
    with pytest.raises(ValidationError, match="not a bitrate"):
        EncodeConfig(maxrate=bad, bufsize="9M")


def test_every_pass_encodes_with_the_same_settings(monkeypatch):
    """A segment at CRF 20 concatenated at CRF 28 throws away the quality the
    expensive pass just paid for."""
    calls = render_one_cut(
        monkeypatch,
        framing=None,
        encode=EncodeConfig(crf=22, preset="medium"),
    )
    cut = Cut(0, 0.0, 1.0, "a.jpg", "s", "sec", effects=("kaleidoscope", "halation"))
    calls.clear()
    fp._render_segment("ffmpeg", cut, make_station("s"), 1080, 1920, 25, "o.mp4",
                       EncodeConfig(crf=22, preset="medium"))
    assert len(calls) == 3  # linear pass + one per graph effect
    for argv in calls:
        assert flag(argv, "-crf") == "22"
        assert flag(argv, "-preset") == "medium"


def test_mux_audio_honours_the_audio_settings_and_still_stream_copies_video(monkeypatch):
    calls = capture_argv(monkeypatch)
    monkeypatch.setattr(fp, "_warn_if_streams_disagree", lambda *a, **k: None)
    fp.mux_audio("s.mp4", "a.wav", "o.mp4", EncodeConfig(audio_bitrate="320k", audio_rate=48000))
    argv = calls[0]
    assert flag(argv, "-c:v") == "copy", "re-encoding here would defeat the cheap/expensive split"
    assert flag(argv, "-b:a") == "320k"
    assert flag(argv, "-ar") == "48000"


# --------------------------------------------------------------------------
# aspect
# --------------------------------------------------------------------------
@pytest.mark.parametrize("aspect,expected", sorted(ASPECT_RESOLUTIONS.items()))
def test_setting_aspect_alone_picks_the_canonical_resolution(aspect, expected):
    assert OutputConfig(aspect=aspect).resolution == expected


def test_an_explicit_resolution_at_the_same_shape_is_kept():
    """A 4K vertical master is a legitimate thing to ask for."""
    assert OutputConfig(aspect="9:16", resolution=(2160, 3840)).resolution == (2160, 3840)


def test_an_aspect_that_contradicts_its_resolution_is_refused():
    with pytest.raises(ValidationError, match="rather than"):
        OutputConfig(aspect="9:16", resolution=(1280, 720))


def test_no_aspect_leaves_the_default_resolution_alone():
    assert OutputConfig().resolution == (1280, 720)
    assert OutputConfig().aspect is None


# --------------------------------------------------------------------------
# output.window
# --------------------------------------------------------------------------
def _windowed_edl(window, *, duration=40.0, fps=24) -> EDL:
    brief = make_brief(
        stations=[make_station("s")],
        sections=[make_section(station="s", start=0.0, end=duration)],
        output=OutputConfig(window=window, fps=fps),
    )
    return compose(brief, make_analysis(duration=duration), {"s": [make_media_asset("a.jpg")]})


def test_a_window_rebases_the_timeline_to_start_at_zero():
    edl = _windowed_edl((10.0, 20.0))
    assert edl.cuts[0].start == 0.0
    assert edl.cuts[0].index == 0
    assert edl.duration == pytest.approx(10.0, abs=1 / 24)


def test_a_window_keeps_only_the_cuts_inside_it():
    full = _windowed_edl(None)
    windowed = _windowed_edl((10.0, 20.0))
    assert len(windowed.cuts) < len(full.cuts)
    assert windowed.cuts[-1].end <= 10.0 + 1e-6


def test_windowed_cuts_stay_on_the_frame_grid():
    """Rebasing by an off-grid offset would reintroduce exactly the sub-frame
    drift the frame-count render was built to eliminate -- see
    docs/ARCHITECTURE.md, "Frame-accurate cuts"."""
    fps = 25
    edl = _windowed_edl((10.037, 20.0), fps=fps)
    for cut in edl.cuts:
        for t in (cut.start, cut.end):
            assert abs(t * fps - round(t * fps)) < 1e-6, f"{t} is not on the {fps}fps grid"


def test_the_windowed_edl_still_tiles_without_gaps():
    """EDL.__post_init__ enforces this; a window that broke it would raise."""
    edl = _windowed_edl((10.0, 20.0))
    for a, b in zip(edl.cuts, edl.cuts[1:]):
        assert b.start == pytest.approx(a.end, abs=1e-6)


def test_a_window_containing_no_cuts_says_so():
    with pytest.raises(ValueError, match="contains no cuts"):
        _windowed_edl((500.0, 520.0))


def test_a_backwards_window_is_refused():
    with pytest.raises(ValidationError, match="must be after start"):
        OutputConfig(window=(90.0, 10.0))


def test_render_seeks_the_audio_to_the_window_start(monkeypatch):
    """Without this the cutdown's picture is right and its audio starts from
    the top of the song."""
    calls = capture_argv(monkeypatch)
    monkeypatch.setattr(fp, "_warn_if_streams_disagree", lambda *a, **k: None)
    fp.mux_audio("s.mp4", "a.wav", "o.mp4", EncodeConfig(), audio_start=161.0)
    argv = calls[0]
    assert argv[argv.index("-ss") + 1] == "161.000"
    assert argv.index("-ss") < argv.index("a.wav"), "-ss must precede its -i to seek, not decode"


def test_a_full_render_emits_no_seek(monkeypatch):
    calls = capture_argv(monkeypatch)
    monkeypatch.setattr(fp, "_warn_if_streams_disagree", lambda *a, **k: None)
    fp.mux_audio("s.mp4", "a.wav", "o.mp4")
    assert "-ss" not in calls[0]
