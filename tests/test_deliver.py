"""render/deliver.py: the delivery sheet, without ever running ffmpeg.

`run()` and `run_measure()` are monkeypatched to record the argv they would
have been given and to answer with canned ffmpeg logs -- loudnorm's JSON,
ebur128's summary -- so the whole suite stays true to the rule that pytest
never calls ffmpeg (AGENTS.md, "Testing"). The sheets are YAML text written
into tmp_path; the media they name never exists, because nothing reads it.
The --dry-run script is run for real, under sh, with a stand-in ffmpeg and
ffprobe (small sh scripts written into tmp_path) on PATH.

What is pinned is each rule a hand-written delivery script had to learn:
frame counts instead of -t, the clean-output flags, no make_zero, seek times
that never round down past a keyframe, one gain per master, the true-peak
guard on the delivered file in every mode, the limiter's delay taken back,
click-guard fades, a render that starts before the song, a silent cut -- and
a --dry-run script that does the same thing and is safe to run somewhere
else.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import textwrap
from typing import ClassVar

import numpy as np
import pytest
import yaml

from kaleidophone.render import _ffmpeg_util as fu
from kaleidophone.render import deliver as dv

LOUDNORM_LOG = """\
Input #0, wav, from 'Song.wav':
  Metadata:
    comment         : {not json}
[Parsed_loudnorm_0 @ 0x55ba540a5a40]
{
\t"input_i" : "-8.81",
\t"input_tp" : "+6.05",
\t"input_lra" : "4.20",
\t"input_thresh" : "-18.90",
\t"output_i" : "-14.02",
\t"output_tp" : "-1.50",
\t"output_lra" : "3.90",
\t"output_thresh" : "-24.10",
\t"normalization_type" : "dynamic",
\t"target_offset" : "0.02"
}
"""


def loudnorm_log(integrated: str = "-8.81", true_peak: str = "+6.05") -> str:
    return LOUDNORM_LOG.replace('"-8.81"', f'"{integrated}"').replace('"+6.05"', f'"{true_peak}"')


def trace_log(init_qp: str = "-6") -> str:
    """trace_headers' real shape (ffmpeg 6.1): the extradata's SPS and PPS,
    field by field, then the first packet. An x264 CRF sets pic_init_qp."""
    return textwrap.dedent(
        f"""\
        [trace_headers @ 0x1] Extradata
        [trace_headers @ 0x1] 4 bytes left at end of AVCC header.
        [trace_headers @ 0x1] Sequence Parameter Set
        [trace_headers @ 0x1] 8           profile_idc                                          01100100 = 100
        [trace_headers @ 0x1] 24          level_idc                                            00011111 = 31
        [trace_headers @ 0x1] Picture Parameter Set
        [trace_headers @ 0x1] 18          pic_init_qp_minus26                                   0001101 = {init_qp}
        [trace_headers @ 0x1] Packet: 11418 bytes, key frame, pts 0, dts -2048, duration 1024.
        [trace_headers @ 0x1] 0           forbidden_zero_bit                                          0 = 0
        """
    )


def ebur128_log(integrated: str, peak: str) -> str:
    """ebur128's real shape: a running `I:` every 100 ms, then the Summary."""
    frames = "".join(
        f"[Parsed_ebur128_0 @ 0x1] t: {t / 10:.1f}  TARGET:-23 LUFS  M: -20.0 S: -20.0  "
        f"I: -70.0 LUFS  LRA: 0.0 LU  FTPK: -3.0 -3.0 dBFS  TPK: -3.0 -3.0 dBFS\n"
        for t in range(1, 4)
    )
    return frames + textwrap.dedent(
        f"""\
        [Parsed_ebur128_0 @ 0x1] Summary:

          Integrated loudness:
            I:         {integrated} LUFS
            Threshold: -24.0 LUFS

          Loudness range:
            LRA:         5.1 LU

          True peak:
            Peak:      {peak} dBFS
        """
    )


SPEC_SHEET = """\
silent: _work/full_silent.mp4      # rendered once, keyframes forced at every cut point
audio: "Song.wav"
fps: 24
defaults: {audio_bitrate: 256k, sample_rate: 48000, ceiling_dbtp: -1.0}
gain: {mode: loudness, target_lufs: -14, limiter_dbfs: -2.0}
cuts:
  - {out: SONG_reel_1080x1920.mp4, t0: 0, dur: 72.25, fade_in: 0.005, fade_out: 0.06}
  - {out: SONG_story_16s.mp4, t0: 26.25, dur: 16, fade_in: 0.25, fade_out: 1.2}
  - {out: SONG_reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}
check: true
"""

# alimiter's delay taken back by hand, for an ffmpeg without `latency`.
HAND_TRIM = (
    "apad=pad_len=767,alimiter=limit=0.7943:attack=4:release=200:level=disabled,"
    "atrim=start_sample=767,asetpts=PTS-STARTPTS"
)


def write_sheet(tmp_path, text: str, name: str = "deliver.yaml") -> str:
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def rel_sheet(here, text: str, name: str = "deliver.yaml") -> str:
    """Write a sheet into the working directory and name it relatively -- how
    a sheet is used from its project folder, and what keeps a --dry-run
    script free of absolute paths."""
    write_sheet(here, text, name)
    return name


def sheet_with(gain: str = "{mode: fixed, db: -2.5}", cuts: str | None = None, **extra) -> str:
    cuts = cuts or "  - {out: SONG_reel.mp4, t0: 0, dur: 72.25, fade_in: 0.005, fade_out: 0.06}\n"
    lines = ["silent: _work/full_silent.mp4", "audio: Song.wav", "fps: 24", f"gain: {gain}"]
    lines += [f"{k}: {v}" for k, v in extra.items()]
    return "\n".join(lines) + "\ncuts:\n" + cuts


def arg_after(argv: list[str], flag: str, occurrence: int = 0) -> str:
    positions = [i for i, a in enumerate(argv) if a == flag]
    return argv[positions[occurrence] + 1]


class FakeFfmpeg:
    """Stands in for every ffmpeg the delivery would start.

    `peaks` are the delivered files' true peaks, handed out one per ebur128
    measurement in the order they are asked for (every cut of round 1, then
    round 2 ...); the last one repeats. `log` is every call in order, with
    the prefix the real helper puts in front -- what a --dry-run script's
    ffmpeg lines are compared with.
    """

    def __init__(self, peaks=(-3.0,), integrated="-14.0", loudnorm=LOUDNORM_LOG):
        self.runs: list[list[str]] = []
        self.measures: list[list[str]] = []
        self.log: list[list[str]] = []
        self.peaks = list(peaks)
        self.integrated = integrated
        self.loudnorm = loudnorm
        # The preflight's look at each part's stream headers (trace_headers):
        # answered from `headers` by file name, and kept out of `log` -- it is
        # a check before the delivery, not a step --dry-run's script repeats.
        self.traces: list[list[str]] = []
        self.headers: dict[str, str] = {}

    def run(self, ffmpeg, args):
        self.runs.append(args)
        self.log.append(["-hide_banner", "-loglevel", "error", "-nostdin", *args])
        # Leave a file where ffmpeg would have, so the check can stat it.
        if args[-1].endswith(".mp4"):
            with open(args[-1], "wb") as fh:
                fh.write(b"\0" * 2048)

    def run_measure(self, ffmpeg, args):
        if "-bsf:v" in args:
            self.traces.append(args)
            return self.headers.get(os.path.basename(args[args.index("-i") + 1]), trace_log())
        self.measures.append(args)
        self.log.append(["-hide_banner", "-nostats", "-nostdin", *args])
        filters = args[args.index("-af") + 1]
        if filters.startswith("loudnorm"):
            return self.loudnorm
        peak = self.peaks.pop(0) if len(self.peaks) > 1 else self.peaks[0]
        return ebur128_log(self.integrated, f"{peak:.1f}")

    @property
    def encodes(self) -> list[list[str]]:
        """Every encode of a cut with audio, in order."""
        return [a for a in self.runs if "-af" in a]

    @property
    def silent_cuts(self) -> list[list[str]]:
        return [a for a in self.runs if "-an" in a and ".kaleidophone-cache" not in a[-1]]

    @property
    def peak_measures(self) -> list[list[str]]:
        return [m for m in self.measures if arg_after(m, "-af") == "ebur128=peak=true"]


@pytest.fixture
def media(tmp_path):
    """Placeholder files where the sheet's inputs are expected -- a few bytes
    of nothing, never media, and gone with tmp_path."""
    (tmp_path / "_work").mkdir()
    for name in ("_work/full_silent.mp4", "_work/card_silent.mp4", "Song.wav"):
        (tmp_path / name).write_bytes(b"placeholder")
    return tmp_path


@pytest.fixture
def fake(monkeypatch):
    # A finished master: -8.81 LUFS, -0.30 dBTP. (LOUDNORM_LOG's +6.05 is a
    # float pre-master's; the loudness-mode tests that care set it.)
    ff = FakeFfmpeg(loudnorm=loudnorm_log("-8.81", "-0.30"))
    monkeypatch.setattr(dv, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(dv, "run", ff.run)
    monkeypatch.setattr(dv, "run_measure", ff.run_measure)
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset({"limit", "latency"}))
    monkeypatch.setattr(dv, "decode_f32le", lambda *a, **k: b"")  # edges: silence
    monkeypatch.setattr(dv, "probe_duration", lambda path: 300.0)
    monkeypatch.setattr(dv, "probe_keyframes", lambda path: [0.0, 26.25, 51.0, 53.0])
    frames = {"card_silent.mp4": "48", "SONG_reel.mp4": "1734"}
    monkeypatch.setattr(
        dv, "probe_stream", lambda path, stream, entry, count_packets=False: frames.get(os.path.basename(path))
    )
    return ff


# --------------------------------------------------------------------------
# the sheet
# --------------------------------------------------------------------------
def test_the_documented_example_sheet_parses(tmp_path):
    sheet = dv.load_sheet(write_sheet(tmp_path, SPEC_SHEET))
    assert isinstance(sheet.gain, dv.LoudnessGain)
    assert sheet.gain.target_lufs == -14 and sheet.gain.limiter_dbfs == -2.0
    assert [c.out for c in sheet.cuts][-1] == "SONG_reel_card.mp4"
    card = sheet.cuts[2]
    assert card.frames(24) == 3144 and card.card_frames(24) == 48


def test_a_minimal_sheet_gets_the_documented_defaults(tmp_path):
    text = "silent: s.mp4\naudio: a.wav\ncuts:\n  - {out: x.mp4, t0: 0, dur: 10}\n"
    sheet = dv.load_sheet(write_sheet(tmp_path, text))
    assert sheet.fps == 24 and sheet.check is True and sheet.silent_start == 0.0
    assert isinstance(sheet.gain, dv.FixedGain) and sheet.gain.db == 0.0
    assert sheet.defaults.audio_bitrate == "256k"
    assert sheet.defaults.sample_rate == 48000 and sheet.defaults.ceiling_dbtp == "auto"
    cut = sheet.cuts[0]
    assert (cut.fade_in, cut.fade_out) == (0.005, 0.015)  # click guards unless the sheet says otherwise
    assert cut.has_audio and cut.audio is None


def test_each_gain_mode_parses_with_its_defaults(tmp_path):
    auto = dv.load_sheet(write_sheet(tmp_path, sheet_with("{mode: auto}"))).gain
    assert (auto.start_db, auto.step_db, auto.max_steps) == (0.0, 0.5, 12)
    loud = dv.load_sheet(write_sheet(tmp_path, sheet_with("{mode: loudness}"))).gain
    assert (loud.target_lufs, loud.limiter_dbfs, loud.step_db, loud.max_steps) == (-14.0, -2.0, 0.5, 12)


def test_a_ceiling_is_auto_or_a_number_at_or_under_zero(tmp_path):
    def ceiling(value):
        return dv.load_sheet(write_sheet(tmp_path, sheet_with(defaults=f"{{ceiling_dbtp: {value}}}"))).defaults.ceiling_dbtp

    assert ceiling("auto") == "auto" and ceiling(-2) == -2.0 and ceiling(0) == 0.0


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 10, fadeout: 1}\n"), "fadeout"),
        (sheet_with(cuts="  - {out: ../x.mp4, t0: 0, dur: 10}\n"), "inside the output directory"),
        (sheet_with(cuts="  - {out: /abs/x.mp4, t0: 0, dur: 10}\n"), "inside the output directory"),
        (sheet_with(cuts="  - {out: x.wav, t0: 0, dur: 10}\n"), "must end in"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 10}\n  - {out: ./x.mp4, t0: 10, dur: 5}\n"), "overwrite"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 1, fade_in: 0.6, fade_out: 0.6}\n"), "longer than the cut"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 10, card: c.mp4}\n"), "go together"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 10, video_from: 2}\n"), "go together"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 5, dur: 10, card: c.mp4, video_from: 15}\n"), "inside the cut"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 26.26, dur: 10}\n"), "26.2500 / 26.2917"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 10}\n", defaults="{audio_bitrate: loud}"), "not a bitrate"),
        (sheet_with(defaults="{ceiling_dbtp: 0.5}"), "not a ceiling"),
        (sheet_with(defaults="{ceiling_dbtp: loud}"), "not a ceiling"),
        (sheet_with(defaults="{ceiling_dbtp: .nan}"), "not a ceiling"),
        (sheet_with("{mode: loudness, limiter_dbfs: -30}"), "limiter_dbfs"),
        (sheet_with("{mode: auto, step_db: 0}"), "step_db"),
        (sheet_with("{mode: louder}"), "gain"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 5, audio: silent}\n"), "audio"),
        (sheet_with(cuts="  - {out: x.mp4, t0: 0, dur: 5, audio: none, fade_out: 1}\n"), "no audio to fade"),
        (sheet_with(silent_start=".inf"), "silent_start"),
        ("silent: s.mp4\ncuts:\n  - {out: x.mp4, t0: 0, dur: 1}\n", r"`audio` \(the master\) is required"),
        ("silent: s.mp4\naudio: a.wav\ncuts: []\n", "cuts"),
        ('silent: "s\\n.mp4"\naudio: a.wav\ncuts:\n  - {out: x.mp4, t0: 0, dur: 1}\n', "control character"),
    ],
)
def test_a_sheet_that_cant_be_delivered_says_why(tmp_path, text, match):
    with pytest.raises(ValueError, match=match) as exc:
        dv.load_sheet(write_sheet(tmp_path, text))
    assert "is not a valid delivery sheet" in str(exc.value)


def test_errors_point_at_the_cut_they_are_about(tmp_path):
    text = sheet_with(cuts="  - {out: a.mp4, t0: 0, dur: 5}\n  - {out: b.mp4, t0: 0, dur: 1, fade_in: 2}\n")
    with pytest.raises(ValueError, match=r"cuts\[1\]: b\.mp4: fade_in"):
        dv.load_sheet(write_sheet(tmp_path, text))


def test_yaml_that_isnt_a_mapping_or_isnt_yaml_is_refused_plainly(tmp_path):
    with pytest.raises(ValueError, match="not valid YAML"):
        dv.load_sheet(write_sheet(tmp_path, "silent: [unclosed\n"))
    with pytest.raises(ValueError, match="expected a mapping"):
        dv.load_sheet(write_sheet(tmp_path, "- just\n- a list\n"))


def test_a_missing_sheet_is_a_file_not_found():
    with pytest.raises(FileNotFoundError):
        dv.load_sheet("/nope/deliver.yaml")


def test_a_sheet_of_silent_cuts_needs_no_master(tmp_path):
    text = "silent: canvas.mp4\ncuts:\n  - {out: SONG_canvas.mp4, t0: 0, dur: 8, audio: none}\n"
    sheet = dv.load_sheet(write_sheet(tmp_path, text))
    assert sheet.audio is None and not sheet.cuts[0].has_audio


# --------------------------------------------------------------------------
# seek times and number formatting
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("t", "fps", "expected"),
    [(26.25, 24, "26.250000"), (242 / 24, 24, "10.083333"), (10.083, 24, "10.083333"),
     (241 / 24, 24, "10.041666"), (289 / 24, 24, "12.041666"), (12.042, 24, "12.041666"),
     (12.0, 25, "12.000000"), (0.1, 30, "0.100000")],
)
def test_a_cut_point_is_its_frames_time_floored_to_the_microsecond(t, fps, expected):
    """Three decimals is what a hand-written script types: `10.083` for frame
    242 at 24 fps is 0.33 ms early, and with stream copy ffmpeg 6.1 wrote a
    cut with no decodable frames from it. And never rounded up: rounded,
    frame 241 becomes 10.041667, which -force_key_frames puts on frame 242
    (both measured on a synthetic render)."""
    assert dv._frame_time(t, fps) == expected
    exact = round(t * fps) / fps
    assert 0 <= exact - float(dv._frame_time(t, fps)) < 1e-6


def test_the_keyframe_list_never_rounds_a_cut_point_up():
    sheet = dv.DeliverySheet.model_validate({
        "silent": "s.mp4", "audio": "a.wav", "fps": 24,
        "cuts": [{"out": "a.mp4", "t0": 241 / 24, "dur": 1 / 24}, {"out": "b.mp4", "t0": 242 / 24, "dur": 2}],
    })
    assert dv._keyframe_list(sheet) == "0,10.041666,10.083333,12.083333"


def test_filter_numbers_are_plain_decimals():
    assert dv._num(0.005) == "0.005"
    assert dv._num(72.19) == "72.19"
    assert dv._num(1e-7) == "0"
    assert dv._num(-1.0) == "-1"


def test_relative_paths_get_a_leading_dot_slash():
    assert dv._arg("-weird.mp4") == "./-weird.mp4"
    assert dv._arg("a:b.mp4") == "./a:b.mp4"
    assert dv._arg("/abs/x.mp4") == "/abs/x.mp4"
    assert dv._arg("../x.mp4") == "../x.mp4"


# --------------------------------------------------------------------------
# the argv
# --------------------------------------------------------------------------
def test_fixed_mode_stream_copies_by_frame_count_with_clean_output(media, fake):
    dv.deliver(write_sheet(media, sheet_with()))
    (argv,) = fake.encodes
    assert arg_after(argv, "-c:v") == "copy"
    assert arg_after(argv, "-frames:v") == "1734"  # round(72.25 * 24)
    # The only -t is the audio's, on the input side; the picture is bounded
    # by frame count. -ss -t -c:v copy kept 2 extra frames per cut.
    assert argv.count("-t") == 1 and argv.index("-t") > argv.index("-i")
    assert "-avoid_negative_ts" not in argv
    for flag in ("-dn", "-sn"):
        assert flag in argv
    assert arg_after(argv, "-map_metadata") == "-1" and arg_after(argv, "-map_chapters") == "-1"
    assert arg_after(argv, "-movflags") == "+faststart"
    assert arg_after(argv, "-af") == "volume=-2.50dB,afade=t=in:st=0:d=0.005,afade=t=out:st=72.19:d=0.06"
    assert (arg_after(argv, "-c:a"), arg_after(argv, "-b:a"), arg_after(argv, "-ar")) == ("aac", "256k", "48000")
    assert argv[-1].endswith("SONG_reel.mp4")


def test_every_cut_is_faded_5_ms_in_and_15_ms_out_unless_the_sheet_says_otherwise(media, fake):
    """Unfaded, a story ended on a -22 dBFS step: a click, and a click every
    loop where a platform loops it."""
    cuts = "  - {out: a.mp4, t0: 0, dur: 10}\n  - {out: b.mp4, t0: 26.25, dur: 16, fade_in: 0, fade_out: 0}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    first, second = fake.encodes
    assert arg_after(first, "-af") == "volume=-2.50dB,afade=t=in:st=0:d=0.005,afade=t=out:st=9.985:d=0.015"
    assert arg_after(second, "-af") == "volume=-2.50dB"  # an explicit 0 is honoured


def test_a_cut_from_zero_has_no_seek_and_a_later_one_seeks_both_inputs_alike(media, fake):
    cuts = "  - {out: a.mp4, t0: 0, dur: 10}\n  - {out: b.mp4, t0: 26.25, dur: 16}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    first, second = fake.encodes
    assert "-ss" not in first
    assert arg_after(second, "-ss", 0) == arg_after(second, "-ss", 1) == "26.250000"
    assert second.index("-ss") < second.index("-i")  # an input seek: jump, don't decode
    assert arg_after(second, "-t") == "16.000000"


def test_the_card_cut_is_film_tail_then_concat_then_mux(media, fake):
    cuts = "  - {out: reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    tail, concat, mux = fake.runs
    assert arg_after(tail, "-ss") == "53.000000"
    assert arg_after(tail, "-frames:v") == "3096"  # 3144 total - 48 card frames
    assert arg_after(tail, "-c:v") == "copy" and "-an" in tail
    assert "-avoid_negative_ts" not in tail  # it starts on a keyframe; make_zero would shift it
    assert concat[concat.index("-f") + 1 : concat.index("-f") + 5] == ["concat", "-safe", "0", "-i"]
    assert arg_after(concat, "-c") == "copy"
    assert arg_after(mux, "-i", 0) == concat[-1]  # the joined silent video, not a seek into the film
    assert mux.index("-ss") > mux.index("-i")  # the only seek is the audio's
    assert arg_after(mux, "-ss") == "51.000000" and arg_after(mux, "-frames:v") == "3144"


def test_the_concat_list_is_relative_to_itself_and_quoted(media, fake, monkeypatch):
    listings = []
    real_run = fake.run

    def run(ffmpeg, args):
        if "concat" in args:
            listings.append(open(args[args.index("-i") + 1]).read())
        real_run(ffmpeg, args)

    monkeypatch.setattr(dv, "run", run)
    cuts = "  - {out: reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    assert listings == ["file '../../_work/card_silent.mp4'\nfile 'cut01.tail.mp4'\n"]
    assert not (media / ".kaleidophone-cache").exists()  # intermediates and their directory are gone


def test_a_card_path_with_an_apostrophe_is_quoted_the_concat_demuxers_way(tmp_path):
    sheet = dv.load_sheet(write_sheet(tmp_path, sheet_with(cuts=(
        "  - {out: r.mp4, t0: 51, dur: 131, card: \"_work/the artist's card.mp4\", video_from: 53}\n"
    ))))
    steps = dv._card_steps(sheet, sheet.cuts[0], 1, dv._paths("deliver.yaml", None))
    assert steps.listing.splitlines()[0] == "file " + fu.concat_quote("../../_work/the artist's card.mp4")
    assert "'\\''" in steps.listing


def test_the_intermediates_go_even_when_an_encode_fails(media, fake, monkeypatch):
    def run(ffmpeg, args):
        fake.run(ffmpeg, args)
        if "-af" in args:
            raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(dv, "run", run)
    cuts = "  - {out: reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}\n"
    with pytest.raises(RuntimeError):
        dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    assert not (media / ".kaleidophone-cache").exists()


def test_out_dir_moves_the_deliverables_but_not_the_inputs(media, fake, tmp_path):
    out = media / "renders" / "v2"
    (result,) = dv.deliver(write_sheet(media, sheet_with()), out_dir=str(out))
    assert result.out == str(out / "SONG_reel.mp4")
    (argv,) = fake.encodes
    assert arg_after(argv, "-i", 0).endswith(os.path.join("_work", "full_silent.mp4"))


# --------------------------------------------------------------------------
# one gain per master
# --------------------------------------------------------------------------
STORIES = (
    "  - {out: full.mp4, t0: 0, dur: 72.25}\n"
    "  - {out: intro.mp4, t0: 0, dur: 15}\n"
    "  - {out: chorus.mp4, t0: 26.25, dur: 16}\n"
)


def test_loudness_mode_measures_the_whole_master_once_and_gains_every_cut_alike(media, fake):
    """A story from a sparse intro must not be pushed up to the chorus: the
    song's own dynamics are what the cuts share."""
    results = dv.deliver(write_sheet(media, sheet_with("{mode: loudness, target_lufs: -14}", cuts=STORIES)))
    (measure,) = [m for m in fake.measures if arg_after(m, "-af").startswith("loudnorm")]
    assert "-ss" not in measure and "-t" not in measure  # the whole master, not a window
    assert measure[1].endswith("Song.wav")
    assert measure[2:] == ["-vn", "-af", "loudnorm=I=-14:TP=-1.5:print_format=json", "-f", "null", "-"]
    assert {arg_after(a, "-af").split(",")[1] for a in fake.encodes} == {"volume=-5.19dB"}  # -14 - (-8.81)
    assert all(r.source_lufs == -8.81 and r.gain_db == -5.19 for r in results)


def test_loudness_mode_limits_4x_oversampled_with_a_200_ms_release_and_no_delay(media, fake):
    (result,) = dv.deliver(write_sheet(media, sheet_with("{mode: loudness}", cuts="  - {out: s.mp4, t0: 26.25, dur: 16}\n")))
    (argv,) = fake.encodes
    assert arg_after(argv, "-af") == (
        "aresample=192000,volume=-5.19dB,"
        "alimiter=limit=0.7943:attack=4:release=200:level=disabled:latency=1,aresample=48000,"
        "afade=t=in:st=0:d=0.005,afade=t=out:st=15.985:d=0.015"
    )
    assert result.limiter_dbfs == -2.0 and result.ceiling_dbtp == -1.0


def test_an_ffmpeg_without_alimiter_latency_gets_the_same_delay_taken_back_by_hand(media, fake, monkeypatch):
    """alimiter's 4 ms lookahead delays its output 767 samples at 192 kHz;
    uncompensated, the audio landed 4.0 ms late (ffmpeg 4.2.2, 6.1.1 and
    7.0.2 measured). latency=1 arrived in ffmpeg 5.1; before it, the same
    767 samples are padded and trimmed around the limiter -- measured
    sample-identical to latency=1."""
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset({"limit", "attack", "release"}))
    dv.deliver(write_sheet(media, sheet_with("{mode: loudness}", cuts="  - {out: s.mp4, t0: 26.25, dur: 16}\n")))
    (argv,) = fake.encodes
    assert f"volume=-5.19dB,{HAND_TRIM},aresample=48000" in arg_after(argv, "-af")
    assert "latency" not in arg_after(argv, "-af")


def test_the_limiter_delay_is_alimiters_own_trim():
    # af_alimiter.c: in_trim = buffer_size / channels - 1, the lookahead in samples less one.
    assert dv.LIMITER_DELAY_SAMPLES == round(192000 * 0.004) - 1 == 767
    assert dv.limiter_filter(-2.0, latency=True) == "alimiter=limit=0.7943:attack=4:release=200:level=disabled:latency=1"
    assert dv.limiter_filter(-2.0, latency=False) == HAND_TRIM
    assert "limit=0.7079:" in dv.limiter_filter(-3.0, latency=True)


def test_a_loudness_chain_without_its_limiter_is_a_bug_not_a_quiet_default(tmp_path):
    sheet = dv.load_sheet(write_sheet(tmp_path, sheet_with("{mode: loudness}")))
    with pytest.raises(ValueError, match="needs its limiter"):
        dv._audio_filter(sheet, sheet.cuts[0], "-5.19", None)


def test_loudness_mode_refuses_a_silent_master(media, fake):
    fake.loudnorm = loudnorm_log("-inf", "-inf")
    with pytest.raises(ValueError, match="silent"):
        dv.deliver(write_sheet(media, sheet_with("{mode: loudness}")))
    assert fake.encodes == []


def test_auto_mode_gives_every_cut_one_gain_and_steps_them_all_together(media, fake):
    """Round 1 at 0 dB: the chorus comes out at -0.2 dBTP, 1.8 dB over the
    -2 dBTP ceiling of a -8.81 LUFS master -- so every cut goes again, 2 dB
    down, not just the chorus."""
    fake.peaks = [-2.5, -9.0, -0.2, -4.4, -11.0, -2.3]
    results = dv.deliver(write_sheet(media, sheet_with("{mode: auto}", cuts=STORIES)))
    volumes = [arg_after(a, "-af").split(",")[0] for a in fake.encodes]
    assert volumes == ["volume=0.00dB"] * 3 + ["volume=-2.00dB"] * 3
    assert [r.gain_db for r in results] == [-2.0, -2.0, -2.0]
    assert [r.true_peak for r in results] == [-4.4, -11.0, -2.3]
    assert results[2].attempts == [(0.0, None, -0.2), (-2.0, None, -2.3)]
    assert not any(r.guard_failed for r in results)
    # Measured on what was written, not on the source.
    assert [os.path.basename(m[m.index("-i") + 1]) for m in fake.peak_measures] == [
        "full.mp4", "intro.mp4", "chorus.mp4"
    ] * 2


def test_a_guard_that_ran_out_of_steps_is_reported_and_the_files_share_one_gain(media, fake):
    fake.peaks = [0.5]
    results = dv.deliver(write_sheet(media, sheet_with("{mode: auto, max_steps: 1}", cuts=STORIES)))
    assert all(r.guard_failed for r in results) and all(r.gain_db == -0.5 for r in results)
    assert len(results[0].attempts) == 2


def test_the_true_peak_guard_runs_after_the_limiter_too(media, fake):
    """A window limited at -2.0 dBFS came out of AAC at -0.1 dBTP. The
    loudness mode's guard steps the limiter -- never the gain -- so the
    loudness stays on target."""
    fake.peaks = [-0.1, -1.4]
    (result,) = dv.deliver(write_sheet(media, sheet_with("{mode: loudness}", cuts="  - {out: s.mp4, t0: 26.25, dur: 16}\n")))
    first, second = (arg_after(a, "-af") for a in fake.encodes)
    assert "volume=-5.19dB,alimiter=limit=0.7943" in first  # -2 dBFS
    assert "volume=-5.19dB,alimiter=limit=0.7079" in second  # -3 dBFS: 0.9 dB over, in two 0.5 dB steps
    assert (result.gain_db, result.limiter_dbfs, result.true_peak) == (-5.19, -3.0, -1.4)


def test_fixed_mode_measures_every_file_and_calls_one_over_the_ceiling_a_failure(media, fake):
    fake.peaks = [-2.5, -0.4]
    cuts = "  - {out: a.mp4, t0: 0, dur: 10}\n  - {out: b.mp4, t0: 26.25, dur: 16}\n"
    a, b = dv.deliver(write_sheet(media, sheet_with("{mode: fixed, db: -1}", cuts=cuts)))
    assert len(fake.encodes) == 2  # nothing to step: one encode each
    assert (a.guard_failed, b.guard_failed) == (False, True)
    assert b.true_peak == -0.4 and b.ceiling_dbtp == -2.0  # -8.81 - 1 dB is louder than -14


def test_a_render_that_starts_before_the_song_gets_a_silent_head(media, fake):
    """silent_start -0.5: master-check found the new master sitting half a
    second earlier (its head trimmed). The first cut's audio is 0.5 s of
    silence, then the song from its top -- 9.5 s of it, so the cut is still
    10 s."""
    cuts = "  - {out: a.mp4, t0: 0, dur: 10}\n  - {out: b.mp4, t0: 26.25, dur: 16}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts, silent_start="-0.5")))
    first, second = fake.encodes
    assert "-ss" not in first and arg_after(first, "-t") == "9.500000"
    assert arg_after(first, "-af").startswith("aresample=48000,adelay=delays=24000S:all=1,volume=-2.50dB,")
    assert arg_after(second, "-ss", 1) == "25.750000" and arg_after(second, "-t") == "16.000000"
    assert "adelay" not in arg_after(second, "-af")


def test_a_silent_head_under_the_limiter_is_padded_at_its_rate(media, fake):
    dv.deliver(write_sheet(media, sheet_with("{mode: loudness}", cuts="  - {out: a.mp4, t0: 0, dur: 10}\n", silent_start="-0.25")))
    (argv,) = fake.encodes
    assert arg_after(argv, "-af").startswith("aresample=192000,adelay=delays=48000S:all=1,volume=-5.19dB,")


def test_a_cut_all_before_the_song_is_refused(media, fake):
    with pytest.raises(ValueError, match=r"all before the song starts.*audio: none"):
        dv.deliver(write_sheet(media, sheet_with(cuts="  - {out: a.mp4, t0: 0, dur: 2}\n", silent_start="-3")))


def test_a_silent_cut_has_no_audio_stream_and_no_measurement(media, fake):
    cuts = "  - {out: canvas.mp4, t0: 26.25, dur: 8, audio: none}\n  - {out: story.mp4, t0: 26.25, dur: 16}\n"
    canvas, story = dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    assert story.has_audio and story.true_peak == -3.0
    (silent,) = fake.silent_cuts
    assert "-an" in silent and "-af" not in silent and "1:a:0" not in silent and silent.count("-i") == 1
    assert arg_after(silent, "-frames:v") == "192" and arg_after(silent, "-c:v") == "copy"
    assert not canvas.has_audio and canvas.mode == "none" and canvas.true_peak is None
    assert [os.path.basename(m[m.index("-i") + 1]) for m in fake.peak_measures] == ["story.mp4"]


def test_a_sheet_of_silent_cuts_never_touches_audio(tmp_path, fake):
    (tmp_path / "canvas.mp4").write_bytes(b"placeholder")
    text = "silent: canvas.mp4\ncuts:\n  - {out: SONG_canvas.mp4, t0: 0, dur: 8, audio: none}\n"
    (result,) = dv.deliver(write_sheet(tmp_path, text))
    assert fake.measures == [] and len(fake.silent_cuts) == 1 and result.size_mb is not None


# --------------------------------------------------------------------------
# the plan: the gain and the ceiling
# --------------------------------------------------------------------------
def _sheet(**fields):
    return dv.DeliverySheet.model_validate({
        "silent": "s.mp4", "audio": "a.wav", "cuts": [{"out": "x.mp4", "t0": 0, "dur": 10}], **fields
    })


@pytest.mark.parametrize(
    ("gain", "master", "ceiling"),
    [
        ({"mode": "auto"}, -8.8, -2.0),  # a finished master, louder than -14 LUFS
        ({"mode": "auto", "start_db": -6}, -8.8, -1.0),  # planned at -14.8
        ({"mode": "fixed", "db": 0}, -15.0, -1.0),
        ({"mode": "loudness"}, -8.8, -1.0),  # delivered at the -14 target
        ({"mode": "loudness", "target_lufs": -9}, -12.0, -2.0),
    ],
)
def test_the_auto_ceiling_is_minus_2_for_a_delivery_louder_than_minus_14_lufs(gain, master, ceiling):
    """Spotify: true peak under -1 dBTP, under -2 for masters louder than -14
    LUFS (support.spotify.com/us/artists/article/loudness-normalization/)."""
    plan = dv.plan_gain(_sheet(gain=gain), dv.MasterLevel(master, -0.5))
    assert plan.ceiling == ceiling


def test_an_explicit_ceiling_is_kept_but_a_loud_delivery_is_warned_about():
    plan = dv.plan_gain(_sheet(gain={"mode": "auto"}, defaults={"ceiling_dbtp": -1}), dv.MasterLevel(-9.0, -0.3))
    assert plan.ceiling == -1.0
    assert any("louder than -14" in w and "-2 dBTP" in w for w in plan.warnings)
    quiet = dv.plan_gain(_sheet(gain={"mode": "auto"}, defaults={"ceiling_dbtp": -1}), dv.MasterLevel(-16.0, -0.3))
    assert quiet.warnings == ()


def test_a_master_over_0_dbtp_in_a_clean_gain_mode_is_pointed_at_loudness_mode():
    plan = dv.plan_gain(_sheet(gain={"mode": "fixed"}), dv.MasterLevel(-10.6, 6.05))
    assert any("mode: loudness" in w for w in plan.warnings)


def test_a_silent_master_is_quiet_as_far_as_the_ceiling_goes():
    plan = dv.plan_gain(_sheet(gain={"mode": "auto"}), dv.MasterLevel(-math.inf, -math.inf))
    assert plan.ceiling == -1.0 and plan.start == dv.Setting(0.0)


def test_the_plan_is_logged_with_the_masters_numbers(media, fake):
    logged = []
    dv.deliver(write_sheet(media, sheet_with("{mode: auto}")), log=logged.append)
    assert "master Song.wav: -8.81 LUFS, -0.30 dBTP -- every cut at gain +0.00 dB (auto), " \
        "true-peak ceiling -2 dBTP (auto: louder than -14 LUFS)" in logged


def test_a_pre_master_in_a_clean_gain_mode_is_warned_about_in_the_run(media, fake):
    fake.loudnorm = LOUDNORM_LOG  # +6.05 dBTP: a float pre-master
    logged = []
    dv.deliver(write_sheet(media, sheet_with("{mode: auto}")), log=logged.append)
    assert any("true peak is +6.05 dBTP, over 0" in line for line in logged)


# --------------------------------------------------------------------------
# the true-peak guard, on its own
# --------------------------------------------------------------------------
def _guard(peaks, gain, count=1, ceiling=-1.0, start=None):
    """Run master_guard with canned delivered peaks, one per encode."""
    encoded, answers = [], list(peaks)
    start = start or dv.Setting(getattr(gain, "start_db", getattr(gain, "db", 0.0)), getattr(gain, "limiter_dbfs", None))
    result = dv.master_guard(
        lambda i, s: encoded.append((i, s)), lambda i: (-14.0, answers.pop(0)), count, start, gain, ceiling
    )
    return result, encoded


def test_the_guard_encodes_once_when_the_first_round_is_already_under():
    result, encoded = _guard([-1.3], dv.AutoGain(mode="auto", start_db=-2.5))
    assert encoded == [(0, dv.Setting(-2.5))] and result.ok and len(result.rounds) == 1


def test_the_guard_steps_by_the_overshoot_in_whole_steps():
    """-0.2 against -1 is 0.8 dB over: two 0.5 dB steps at once, not two rounds."""
    result, encoded = _guard([-0.2, -1.3], dv.AutoGain(mode="auto"))
    assert [s.gain_db for _, s in encoded] == [0.0, -1.0]
    assert result.ok and result.setting == dv.Setting(-1.0)


def test_the_guard_takes_at_least_one_step():
    result, encoded = _guard([-0.95, -1.5], dv.AutoGain(mode="auto", step_db=0.5), ceiling=-1.0)
    assert [s.gain_db for _, s in encoded] == [0.0, -0.5] and result.ok


def test_the_guard_steps_no_more_than_3_db_in_one_round():
    """An encoder pop is not an overshoot: ffmpeg 6.1's native AAC encoder
    put one of +5.3 dBTP into a synthetic master at -4 dB of gain."""
    result, encoded = _guard([5.3, -0.5, -1.6], dv.AutoGain(mode="auto"))
    assert [s.gain_db for _, s in encoded] == [0.0, -3.0, -3.5]
    assert result.ok


def test_every_round_encodes_every_cut_so_the_files_share_one_gain():
    result, encoded = _guard([-3.0, -0.5, -2.0, -1.5], dv.AutoGain(mode="auto"), count=2)
    assert encoded == [(0, dv.Setting(0.0)), (1, dv.Setting(0.0)), (0, dv.Setting(-0.5)), (1, dv.Setting(-0.5))]
    assert [r.worst for r in result.rounds] == [-0.5, -1.5]


def test_the_guard_gives_up_after_max_steps_and_says_so():
    result, encoded = _guard([0.5, 0.4, 0.3], dv.AutoGain(mode="auto", start_db=-2.0, step_db=1.0, max_steps=2))
    assert [s.gain_db for _, s in encoded] == [-2.0, -4.0]  # 1.5 over: two steps, all there were
    assert not result.ok and result.setting == dv.Setting(-4.0)
    result, encoded = _guard([0.5, 0.4, 0.3], dv.AutoGain(mode="auto", start_db=-2.0, step_db=1.0, max_steps=3))
    assert [s.gain_db for _, s in encoded] == [-2.0, -4.0, -5.0]  # then the one step left


def test_fixed_mode_never_steps():
    result, encoded = _guard([0.5], dv.FixedGain(mode="fixed", db=-1.0))
    assert len(encoded) == 1 and not result.ok


def test_loudness_mode_steps_the_limiter_and_keeps_the_gain():
    gain = dv.LoudnessGain(mode="loudness")
    result, encoded = _guard([-0.1, -1.2], gain, start=dv.Setting(-5.19, -2.0))
    assert [s for _, s in encoded] == [dv.Setting(-5.19, -2.0), dv.Setting(-5.19, -3.0)]
    assert result.ok and result.setting.gain_db == -5.19


def test_the_limiter_stops_at_minus_24_dbfs():
    gain = dv.LoudnessGain(mode="loudness", step_db=6.0, max_steps=40)
    following, used = dv.next_setting(gain, dv.Setting(-5.0, -22.0), overshoot=12.0, steps_used=0)
    assert following == dv.Setting(-5.0, -24.0) and used == 1
    assert dv.next_setting(gain, following, overshoot=1.0, steps_used=used) == (None, used)


# --------------------------------------------------------------------------
# an edge left unfaded is checked
# --------------------------------------------------------------------------
def _decoding(level_dbfs):
    amp = 10 ** (level_dbfs / 20)
    return lambda *a, **k: (np.full(960, amp, dtype="<f4")).tobytes()


def test_an_unfaded_edge_that_isnt_silent_is_a_warning(media, fake, monkeypatch):
    seen = []
    monkeypatch.setattr(dv, "decode_f32le", lambda path, **kw: seen.append(kw) or _decoding(-22.0)())
    logged = []
    cuts = "  - {out: story.mp4, t0: 26.25, dur: 16, fade_out: 0}\n"
    dv.deliver(write_sheet(media, sheet_with("{mode: fixed, db: 0}", cuts=cuts)), log=logged.append)
    (warning,) = [line for line in logged if "fade_out is 0" in line]
    assert "story.mp4" in warning and "-22.0 dBFS" in warning and "every loop" in warning
    assert seen == [{"sample_rate": 48000, "channels": 2, "start": 42.24, "duration": 0.01}]


def test_an_unfaded_edge_in_silence_is_fine_and_a_faded_one_is_not_even_read(media, fake, monkeypatch):
    calls = []
    monkeypatch.setattr(dv, "decode_f32le", lambda *a, **k: calls.append(k) or _decoding(-70.0)())
    logged = []
    cuts = "  - {out: a.mp4, t0: 0, dur: 10, fade_in: 0}\n  - {out: b.mp4, t0: 26.25, dur: 16}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts)), log=logged.append)
    assert len(calls) == 1 and not any("is 0" in line for line in logged)


def test_the_padded_head_of_an_early_render_needs_no_check(media, fake, monkeypatch):
    calls = []
    monkeypatch.setattr(dv, "decode_f32le", lambda *a, **k: calls.append(k) or b"")
    dv.deliver(write_sheet(media, sheet_with(cuts="  - {out: a.mp4, t0: 0, dur: 10, fade_in: 0}\n", silent_start="-0.5")))
    assert calls == []


def test_an_edge_that_cant_be_read_is_said_so(media, fake, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("could not decode")

    monkeypatch.setattr(dv, "decode_f32le", boom)
    logged = []
    dv.deliver(write_sheet(media, sheet_with(cuts="  - {out: a.mp4, t0: 0, dur: 10, fade_out: 0}\n")), log=logged.append)
    assert any("couldn't read the audio at its end" in line for line in logged)


# --------------------------------------------------------------------------
# a windowed render: silent_start
# --------------------------------------------------------------------------
#
# A stateful canvas piece renders its reel as a window whose first frame is,
# say, song time 43.890 s (the harness snaps it to a beat and prints it); a
# brief with output.window does the same. Cut times stay on the render's
# clock; only the audio moves to song time.

WINDOW_CUTS = "  - {out: reel.mp4, t0: 0, dur: 60}\n  - {out: story.mp4, t0: 10, dur: 16}\n"


@pytest.fixture
def windowed(fake, monkeypatch):
    """A 60 s render of song time 43.89-103.89 s, cut against a 180 s master."""
    monkeypatch.setattr(dv, "probe_keyframes", lambda path: [0.0, 10.0, 12.0, 26.0])
    monkeypatch.setattr(dv, "probe_duration", lambda path: 180.0 if path.endswith(".wav") else 60.0)
    return fake


def test_silent_start_defaults_to_the_top_of_the_song_and_may_be_negative(tmp_path):
    assert dv.load_sheet(write_sheet(tmp_path, sheet_with())).silent_start == 0.0
    assert dv.load_sheet(write_sheet(tmp_path, sheet_with(silent_start="43.89"))).silent_start == 43.89
    assert dv.load_sheet(write_sheet(tmp_path, sheet_with(silent_start="-0.35"))).silent_start == -0.35


def test_silent_start_is_not_held_to_the_frame_grid(tmp_path):
    """The song's clock has no frames: a beat-snapped 43.890 is 1053.36 of them."""
    sheet = dv.load_sheet(write_sheet(tmp_path, sheet_with(silent_start="43.89")))
    assert sheet.silent_start * sheet.fps % 1 != 0


def test_a_windowed_render_seeks_the_picture_on_its_clock_and_the_audio_in_song_time(media, windowed):
    dv.deliver(write_sheet(media, sheet_with(cuts=WINDOW_CUTS, silent_start="43.89")))
    reel, story = windowed.encodes
    # The reel starts on the render's frame 0: no picture seek, audio from 43.89 s.
    assert reel.count("-ss") == 1 and reel.index("-ss") > reel.index("-i")
    assert arg_after(reel, "-ss") == "43.890000" and arg_after(reel, "-t") == "60.000000"
    assert arg_after(reel, "-frames:v") == "1440"
    # The story: picture from the render's 10 s, audio from song time 53.89 s.
    assert arg_after(story, "-ss", 0) == "10.000000" and story.index("-ss") < story.index("-i")
    assert arg_after(story, "-ss", 1) == "53.890000" and arg_after(story, "-t") == "16.000000"


def test_a_windowed_render_gets_the_songs_gain_not_its_windows(media, windowed):
    dv.deliver(write_sheet(media, sheet_with("{mode: loudness}", cuts=WINDOW_CUTS, silent_start="43.89")))
    (measure,) = [m for m in windowed.measures if arg_after(m, "-af").startswith("loudnorm")]
    assert "-ss" not in measure  # the whole master
    reel, story = windowed.encodes
    assert arg_after(story, "-ss", 1) == "53.890000"
    assert "volume=-5.19dB" in arg_after(reel, "-af") and "volume=-5.19dB" in arg_after(story, "-af")


def test_a_windowed_card_cut_keeps_the_film_on_the_render_clock_and_the_audio_on_the_songs(media, windowed):
    cuts = "  - {out: card.mp4, t0: 10, dur: 16, card: _work/card_silent.mp4, video_from: 12}\n"
    dv.deliver(write_sheet(media, sheet_with(cuts=cuts, silent_start="43.89")))
    tail, concat, mux = windowed.runs
    assert arg_after(tail, "-ss") == "12.000000"  # the film resumes at the render's 12 s
    assert arg_after(mux, "-i", 0) == concat[-1]
    assert arg_after(mux, "-ss") == "53.890000"  # the audio, card included, from song time 43.89 + 10


def test_a_windowed_cut_whose_audio_runs_past_the_master_is_refused(media, windowed, monkeypatch):
    """The picture fits the 60 s render; its audio, 43.89 s into the song,
    doesn't fit a 100 s master -- and only the second is a problem."""
    monkeypatch.setattr(dv, "probe_duration", lambda path: 100.0 if path.endswith(".wav") else 60.0)
    with pytest.raises(ValueError) as exc:
        dv.deliver(write_sheet(media, sheet_with(cuts=WINDOW_CUTS, silent_start="43.89")))
    message = str(exc.value)
    assert (
        "reel.mp4: its audio ends at song time 103.890 s (silent_start 43.89 + 60.000), "
        "past the end of the audio (100.000 s)"
    ) in message
    assert "story.mp4" not in message  # 43.89 + 26 fits
    assert "past the end of the silent render" not in message
    assert windowed.runs == []


def test_the_dry_run_of_a_windowed_render_reads_the_audio_in_song_time(here):
    sheet = rel_sheet(here, sheet_with("{mode: loudness}", cuts=WINDOW_CUTS, silent_start="43.89"))
    script = dv.delivery_script(sheet)
    assert "# The render starts at song time 43.89 s (silent_start)" in script
    assert "-force_key_frames 0,10,26,60\n" in script  # keyframes stay on the render's clock
    assert "# 1/2  reel.mp4: 0.000-60.000 s (song 43.890-103.890 s), 1440 frames" in script
    assert "I=$(lufs ./Song.wav loudnorm=I=-14:TP=-1.5:print_format=json)" in script  # the whole master
    assert "-i ./_work/full_silent.mp4 -ss 43.890000 -t 60.000000 -i ./Song.wav " in script
    assert "-ss 10.000000 -i ./_work/full_silent.mp4 -ss 53.890000 -t 16.000000 -i ./Song.wav " in script
    unwindowed = dv.delivery_script(rel_sheet(here, sheet_with(cuts=WINDOW_CUTS), "plain.yaml"))
    assert "(song " not in unwindowed and "silent_start" not in unwindowed


def test_the_dry_run_of_an_early_render_says_so_and_pads_the_head(here):
    script = dv.delivery_script(rel_sheet(here, sheet_with(cuts=WINDOW_CUTS, silent_start="-0.5")))
    assert "# The render starts 0.5 s before the song (silent_start -0.5)" in script
    assert "-t 59.500000 -i ./Song.wav" in script and "aresample=48000,adelay=delays=24000S:all=1," in script


# --------------------------------------------------------------------------
# parsing ffmpeg's measurements
# --------------------------------------------------------------------------
def test_parse_loudnorm_finds_the_measurement_block_among_other_braces():
    assert dv.parse_loudnorm(LOUDNORM_LOG)["input_i"] == "-8.81"


def test_parse_loudnorm_skips_brace_blocks_that_are_not_its_json():
    log = LOUDNORM_LOG + "[out#0/null @ 0x1] {muxing overhead: unknown}\n"
    assert dv.parse_loudnorm(log)["input_i"] == "-8.81"


def test_parse_loudnorm_without_a_measurement_says_what_ffmpeg_said():
    with pytest.raises(RuntimeError, match="no measurement"):
        dv.parse_loudnorm("Error opening input files: Invalid data found")


def test_the_masters_level_reads_signs_and_infinities():
    assert dv._level("+6.05") == 6.05 and dv._level("-inf") == -math.inf and math.isnan(dv._level(None))


def test_parse_ebur128_reads_the_summary_not_the_running_values():
    assert dv.parse_ebur128(ebur128_log("-14.2", "-1.3")) == (-14.2, -1.3)


def test_parse_ebur128_understands_silence():
    assert dv.parse_ebur128(ebur128_log("-70.0", "-inf")) == (-70.0, float("-inf"))


@pytest.mark.parametrize(
    ("log", "match"),
    [("nothing here", "no summary"), ("Summary:\n  Integrated loudness:\n    I: -14.0 LUFS\n", "peak=true")],
)
def test_parse_ebur128_failures_are_explained(log, match):
    with pytest.raises(RuntimeError, match=match):
        dv.parse_ebur128(log)


def test_the_true_peak_is_measured_without_decoding_the_picture():
    assert dv._ebur128_argv("a.mp4") == ["-i", "./a.mp4", "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]


# --------------------------------------------------------------------------
# preflight: everything checkable before a minute of encoding
# --------------------------------------------------------------------------
def test_a_missing_input_is_named(tmp_path, fake):
    with pytest.raises(FileNotFoundError) as exc:
        dv.deliver(write_sheet(tmp_path, sheet_with()))
    assert exc.value.filename.endswith("full_silent.mp4")


def test_a_cut_without_a_keyframe_under_it_is_refused_with_the_fix(media, fake):
    cuts = "  - {out: a.mp4, t0: 8, dur: 4}\n  - {out: b.mp4, t0: 26.25, dur: 4}\n"
    with pytest.raises(ValueError) as exc:
        dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    message = str(exc.value)
    assert "a.mp4: the film cut starts at 8.000 s" in message and "nearest: 0.000 s / 26.250 s" in message
    assert "b.mp4" not in message
    assert "-force_key_frames 0,8,12,26.25,30.25" in message
    assert fake.runs == [] and fake.measures == []  # nothing was encoded, nothing measured


def test_a_card_of_the_wrong_length_is_refused_before_it_desyncs_the_film(media, fake, monkeypatch):
    monkeypatch.setattr(dv, "probe_stream", lambda path, stream, entry, count_packets=False: "50")
    cuts = "  - {out: reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}\n"
    with pytest.raises(ValueError, match=r"card has 50 frames.*needs 48.*\+2 frames"):
        dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))


def test_a_cut_past_the_end_of_either_input_is_refused(media, fake, monkeypatch):
    monkeypatch.setattr(dv, "probe_duration", lambda path: 60.0)
    with pytest.raises(ValueError) as exc:
        dv.deliver(write_sheet(media, sheet_with()))
    assert "past the end of the silent render (60.000 s)" in str(exc.value)
    assert "past the end of the audio (60.000 s)" in str(exc.value)


def test_a_cut_ending_between_keyframes_delivers_with_a_warning(media, fake, monkeypatch):
    """-frames:v N counts packets in decode order: ending mid-GOP, the last
    frame can come out of B-frame order. Worth saying; not worth refusing."""
    logged = []
    cuts = "  - {out: a.mp4, t0: 0, dur: 26.25}\n  - {out: b.mp4, t0: 26.25, dur: 10}\n"
    results = dv.deliver(write_sheet(media, sheet_with(cuts=cuts)), log=logged.append)
    assert len(results) == 2
    warnings = [line for line in logged if line.startswith("warning:")]
    assert len(warnings) == 2
    assert "b.mp4: ends at 36.250 s, between keyframes" in warnings[0]
    assert "-force_key_frames 0,26.25,36.25" in warnings[1]


def test_a_cut_ending_at_the_end_of_the_render_needs_no_keyframe_there(media, fake, monkeypatch):
    monkeypatch.setattr(dv, "probe_duration", lambda path: 72.25)
    logged = []
    dv.deliver(write_sheet(media, sheet_with()), log=logged.append)
    assert not any(line.startswith("warning:") for line in logged)


def test_preflight_is_best_effort_when_ffprobe_is_missing(media, fake, monkeypatch):
    monkeypatch.setattr(dv, "probe_duration", lambda path: None)
    monkeypatch.setattr(dv, "probe_keyframes", lambda path: None)
    monkeypatch.setattr(dv, "probe_stream", lambda *a, **k: None)
    cuts = "  - {out: a.mp4, t0: 8, dur: 4, card: _work/card_silent.mp4, video_from: 9}\n"
    (result,) = dv.deliver(write_sheet(media, sheet_with(cuts=cuts)))
    assert result.frames is None and result.size_mb is not None


# --------------------------------------------------------------------------
# the check
# --------------------------------------------------------------------------
def test_check_measures_every_deliverable_on_the_file_itself(media, fake):
    fake.integrated = "-14.3"
    (result,) = dv.deliver(write_sheet(media, sheet_with()))
    assert result.frames == 1734 and result.frames_expected == 1734
    assert result.duration == 300.0 and result.lufs == -14.3 and result.true_peak == -3.0
    assert result.size_mb == 0.0  # 2 KB placeholder
    assert len(fake.peak_measures) == 1  # the guard's measurement is the check's: one decode, not two


def test_check_false_still_guards_the_true_peak_but_probes_nothing_else(media, fake):
    (result,) = dv.deliver(write_sheet(media, sheet_with(check="false")))
    assert len(fake.peak_measures) == 1 and result.true_peak == -3.0
    assert result.frames is None and result.size_mb is None


def test_the_table_flags_a_frame_mismatch_and_a_peak_over_the_ceiling():
    good = dv.Delivered("out/a.mp4", 384, -2.5, frames=384, duration=16.0, lufs=-14.1, true_peak=-1.3, size_mb=3.2)
    bad = dv.Delivered("out/b.mp4", 384, 0.0, frames=386, duration=16.1, lufs=-10.0, true_peak=0.4, size_mb=3.3)
    table = dv.format_table([good, bad], ceiling=-1.0)
    lines = table.splitlines()
    assert lines[0].split()[:2] == ["deliverable", "frames"]
    assert "384/384" in lines[1] and "!" not in lines[1]
    assert "386/384" in lines[2] and "!frames" in lines[2] and "!peak" in lines[2]
    assert "warning: b.mp4: 386 frames written, 384 expected" in table
    assert "mode: auto" in table  # the fix for an over at a fixed gain


def test_each_row_is_held_to_its_masters_ceiling_and_a_silent_row_to_none():
    loud = dv.Delivered("a.mp4", 10, -3.0, true_peak=-1.5, ceiling_dbtp=-2.0, mode="auto", limiter_dbfs=None)
    limited = dv.Delivered("b.mp4", 10, -5.19, true_peak=-0.5, ceiling_dbtp=-1.0, mode="loudness", limiter_dbfs=-3.0)
    canvas = dv.Delivered("c.mp4", 10, mode="none", has_audio=False)
    table = dv.format_table([loud, limited, canvas])
    rows = table.splitlines()
    assert "!peak" in rows[1] and "!peak" in rows[2] and "limiter -3.00 dBFS" in rows[2]
    assert "no audio" in rows[3] and "!" not in rows[3]
    assert "gain.start_db" in table and "gain.limiter_dbfs" in table


def test_the_table_survives_a_missing_measurement():
    row = dv.format_table([dv.Delivered("a.mp4", 10, 0.0)], ceiling=-1.0).splitlines()[1]
    assert "?/10" in row


# --------------------------------------------------------------------------
# --dry-run: the shell script
# --------------------------------------------------------------------------
@pytest.fixture
def here(tmp_path, monkeypatch):
    """Run from the sheet's directory, as a project folder is used."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_dry_run_script_needs_neither_ffmpeg_nor_the_media(tmp_path, monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: None)
    script = dv.delivery_script(write_sheet(tmp_path, SPEC_SHEET))
    assert script.startswith("#!/bin/sh\n")
    assert "\nset -e\n" in script
    # Starts, the card cut's resume point, and ends.
    assert "-force_key_frames 0,26.25,42.25,51,53,72.25,182" in script


def test_the_dry_run_measures_the_master_once_and_gains_to_the_target(here):
    script = dv.delivery_script(rel_sheet(here, SPEC_SHEET))
    assert "lufs() {" in script and "gain_to() {" in script and "limiter() {" in script
    assert script.count("I=$(lufs ") == 1
    assert 'G=$(gain_to -14 "$I" ./Song.wav)' in script and "L=-2.00" in script
    assert ",volume=\"$G\"dB,\"$LIM\",aresample=48000" in script
    assert "grep -q '^ *latency  *<'" in script  # the script asks its own ffmpeg


def test_the_dry_run_guard_is_a_loop_with_the_sheets_limits(tmp_path):
    script = dv.delivery_script(write_sheet(tmp_path, sheet_with("{mode: auto, start_db: -2.5, max_steps: 4}")))
    assert "truepeak() {" in script and "gain_to() {" not in script and "limiter() {" not in script
    assert "G=-2.50" in script and "while :; do" in script
    assert "left=$((4 - steps))" in script and 'steps_for "$W" "$C" 0.5' in script
    assert 'if [ "$N" -gt 6 ]; then N=6; fi' in script  # 3 dB in one round at most


def test_the_dry_run_of_fixed_mode_measures_but_never_steps(tmp_path):
    script = dv.delivery_script(write_sheet(tmp_path, sheet_with("{mode: fixed, db: -3}")))
    assert "G=-3.00" in script and "steps_for" in script  # the helper is there; the loop never calls it
    assert "at the fixed gain" in script and "\n  N=$(steps_for" not in script


def test_the_dry_run_ceiling_is_the_sheets_or_worked_out_like_the_real_runs(tmp_path):
    auto = dv.delivery_script(write_sheet(tmp_path, sheet_with("{mode: auto}")))
    assert "print (p > -14) ? -2 : -1" in auto
    fixed = dv.delivery_script(write_sheet(tmp_path, sheet_with("{mode: auto}", defaults="{ceiling_dbtp: -1.5}")))
    assert "C=-1.5" in fixed and "Spotify asks for a true peak under -2 dBTP" in fixed


def test_the_dry_run_card_cut_writes_its_concat_list_inline(here):
    script = dv.delivery_script(rel_sheet(here, SPEC_SHEET))
    assert "cat > .kaleidophone-cache/deliver/cut03.concat.txt <<'EOF'\n" in script
    assert "file '../../_work/card_silent.mp4'\nfile 'cut03.tail.mp4'\nEOF\n" in script
    assert "rm -f -- .kaleidophone-cache/deliver/cut03.tail.mp4" in script
    assert "rmdir -- .kaleidophone-cache/deliver 2>/dev/null || true" in script


def test_the_dry_run_checks_what_it_delivered(here):
    script = dv.delivery_script(rel_sheet(here, SPEC_SHEET))
    assert "check() {" in script
    assert script.rstrip().splitlines()[-5:-2] == [
        "check ./SONG_reel_1080x1920.mp4 1734",
        "check ./SONG_story_16s.mp4 384",
        "check ./SONG_reel_card.mp4 3144",
    ]
    assert script.rstrip().endswith('[ -z "$FAILED" ] || exit 1')
    quiet = dv.delivery_script(rel_sheet(here, sheet_with(check="false"), "quiet.yaml"))
    assert "check" not in quiet


def test_the_dry_run_writes_no_absolute_path_for_a_relative_sheet(here):
    """The script runs on another machine: this one's paths mean nothing there,
    and a username has no business in a file that gets passed around."""
    write_sheet(here, SPEC_SHEET)
    script = dv.delivery_script("deliver.yaml")
    assert str(here) not in script
    assert "/home/" not in script and "/Users/" not in script and "/tmp/" not in script


def test_the_dry_run_keeps_every_ffmpeg_off_stdin(here):
    """Run inside `while read x; do sh deliver.sh; done`, an ffmpeg reading
    stdin eats the next line."""
    script = dv.delivery_script(rel_sheet(here, SPEC_SHEET))
    for line in script.splitlines():
        if line.lstrip().startswith(("ffmpeg ", "if ffmpeg")) or "$(ffmpeg" in line:
            assert "-nostdin" in line, line


def outside_the_manifest(script: str) -> list[str]:
    """The script's lines less the planned manifest's: JSON under a quoted
    here-document, which sh never expands (tested on its own, run, in
    test_platforms_deliver.py)."""
    lines, inside = [], False
    for line in script.splitlines():
        if inside:
            inside = line != dv._MANIFEST_END
            continue
        inside = line.endswith(f"<<'{dv._MANIFEST_END}'")
        lines.append(line)
    return lines


def test_an_out_name_cannot_inject_into_the_dry_run_script(here):
    """Every place the name reaches a command it is single-quoted; the only
    bare copies are in a comment, and in the planned manifest's quoted
    here-document -- and a newline, the one way out of either, is refused by
    the sheet's validation."""
    cuts = "  - {out: 'x $(touch pwned) `id`.mp4', t0: 0, dur: 4}\n"
    script = dv.delivery_script(rel_sheet(here, sheet_with("{mode: auto}", cuts=cuts)))
    commands = [line for line in outside_the_manifest(script) if "pwned" in line and not line.lstrip().startswith("#")]
    assert len(commands) >= 4  # the encode, the measure, the printf, the check
    for line in commands:
        assert "'./x $(touch pwned) `id`.mp4'" in line or "'x $(touch pwned) `id`.mp4'" in line


def test_a_sheet_file_name_cannot_break_out_of_the_header_comment(tmp_path):
    name = "deliver\ntouch pwned\n.yaml"
    script = dv.delivery_script(write_sheet(tmp_path, sheet_with(), name))
    assert "\ntouch pwned" not in script and "# kaleidophone deliver -- deliver?touch pwned?.yaml" in script


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh to parse the script")
@pytest.mark.parametrize("gain", ["{mode: fixed, db: -2}", "{mode: loudness}", "{mode: auto}"])
def test_the_dry_run_script_is_valid_sh(here, gain):
    """`sh -n` parses without running anything -- no ffmpeg, no media."""
    cuts = (
        "  - {out: 'my reel.mp4', t0: 0, dur: 72.25, fade_in: 0.005, fade_out: 0.06}\n"
        "  - {out: reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}\n"
        "  - {out: canvas.mp4, t0: 51, dur: 8, audio: none}\n"
    )
    script = here / "deliver.sh"
    script.write_text(dv.delivery_script(rel_sheet(here, sheet_with(gain, cuts=cuts))))
    proc = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_the_dry_run_honours_out_dir(here):
    script = dv.delivery_script(rel_sheet(here, SPEC_SHEET), out_dir="renders")
    assert "mkdir -p -- renders renders/.kaleidophone-cache/deliver" in script
    assert "./renders/SONG_story_16s.mp4" in script


# --- the script, run: stand-in ffmpeg and ffprobe on PATH -------------------

FAKE_FFMPEG = r"""#!/bin/sh
# A stand-in for ffmpeg, for kaleidophone's tests: logs its argv, answers the
# measurements the script asks for, and touches the file it would write.
{
  printf '%s' ffmpeg
  for a in "$@"; do printf '\037%s' "$a"; done
  printf '\n'
} >> "$FAKE_LOG"
case "$*" in
  *"-h filter=alimiter"*)
    printf 'alimiter AVOptions:\n   limit             <double>     ..F.A....T. set limit\n'
    if [ -n "$FAKE_LATENCY" ]; then printf '   latency           <boolean>    ..F.A....T. compensate delay\n'; fi
    exit 0;;
  *"-h filter=drawtext"*)
    if [ -n "$FAKE_DRAWTEXT" ]; then printf 'drawtext AVOptions:\n   text              <string>     ..FV.....T. set text\n'; fi
    exit 0;;
  *drawtext=*)
    if [ -n "$FAKE_DRAWTEXT_FAILS" ]; then echo "Cannot find a valid font for the family Sans" >&2; exit 1; fi;;
  *loudnorm*)
    printf '{\n\t"input_i" : "%s",\n\t"input_tp" : "+6.05"\n}\n' "$FAKE_LUFS" >&2
    exit 0;;
  *ebur128*)
    p=$(head -n 1 "$FAKE_PEAKS")
    if [ "$(wc -l < "$FAKE_PEAKS")" -gt 1 ]; then
      tail -n +2 "$FAKE_PEAKS" > "$FAKE_PEAKS.next" && mv "$FAKE_PEAKS.next" "$FAKE_PEAKS"
    fi
    printf '[Parsed_ebur128_0 @ 0x1] Summary:\n\n  Integrated loudness:\n    I:         -14.0 LUFS\n\n  True peak:\n    Peak:      %s dBFS\n' "$p" >&2
    exit 0;;
esac
for last in "$@"; do :; done
case "$last" in *.mp4) : > "$last";; esac
"""

FAKE_FFPROBE = "#!/bin/sh\necho 1\n"


def run_script(here, script: str, *, peaks=("-3.0",), lufs="-8.81", latency=True, drawtext="no"):
    """Run a --dry-run script under sh with the stand-ins; returns (the
    process, every ffmpeg argv it ran, the ffmpeg path excluded). `drawtext`:
    whether the stand-in has the filter -- "yes", "no", or "fails" (it has
    it, and drawing fails)."""
    bin_dir = here / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("ffmpeg", FAKE_FFMPEG), ("ffprobe", FAKE_FFPROBE)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    (here / "peaks.txt").write_text("\n".join(peaks) + "\n")
    (here / "deliver.sh").write_text(script)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_LOG": str(here / "ffmpeg.log"),
        "FAKE_PEAKS": str(here / "peaks.txt"),
        "FAKE_LUFS": lufs,
        "FAKE_LATENCY": "1" if latency else "",
        "FAKE_DRAWTEXT": "" if drawtext == "no" else "1",
        "FAKE_DRAWTEXT_FAILS": "1" if drawtext == "fails" else "",
    }
    proc = subprocess.run(["sh", "deliver.sh"], cwd=here, env=env, capture_output=True, text=True)
    log = (here / "ffmpeg.log").read_text().splitlines() if (here / "ffmpeg.log").exists() else []
    return proc, [line.split("\x1f")[1:] for line in log]


needs_sh = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("sh", "awk", "sed", "grep")), reason="needs a POSIX shell and tools"
)

PARITY_CUTS = (
    "  - {out: full.mp4, t0: 0, dur: 72.25}\n"
    "  - {out: reel_card.mp4, t0: 51, dur: 131, card: _work/card_silent.mp4, video_from: 53}\n"
    "  - {out: story.mp4, t0: 26.25, dur: 16, fade_out: 0}\n"
    "  - {out: canvas.mp4, t0: 26.25, dur: 8, audio: none}\n"
)


@needs_sh
@pytest.mark.parametrize(
    ("gain", "peaks", "latency", "extra"),
    [
        ("{mode: auto}", ["-1.0", "-3.0", "-2.5", "-3.1", "-4.0", "-2.9"], True, {}),  # two rounds
        ("{mode: loudness}", ["-0.1", "-2.0", "-1.5", "-1.4", "-2.2", "-2.0"], False, {}),  # the limiter steps
        ("{mode: loudness}", ["-2.0"], True, {"silent_start": "-0.5"}),
        ("{mode: fixed, db: -1}", ["-3.0", "-0.5", "-2.5"], True, {"defaults": "{ceiling_dbtp: -1}"}),
    ],
)
def test_the_dry_run_script_runs_the_same_ffmpeg_commands_as_the_real_run(here, media, fake, monkeypatch, gain, peaks, latency, extra):
    """Parity: the script, run under sh, starts exactly the ffmpeg command
    lines deliver() does -- the master's measurement, the card, the silent
    cut, and every round of the guard, the measured gains included."""
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset({"latency"} if latency else set()))
    fake.peaks = [float(p) for p in peaks]
    sheet = rel_sheet(here, sheet_with(gain, cuts=PARITY_CUTS, check="false", **extra))
    results = dv.deliver(sheet)
    script = dv.delivery_script(sheet)
    proc, ran = run_script(here, script, peaks=peaks, latency=latency)
    failed = any(r.guard_failed for r in results)
    assert proc.returncode == (1 if failed else 0), proc.stderr
    assert [argv for argv in ran if "-h" not in argv] == fake.log


@needs_sh
def test_the_dry_run_script_stops_on_a_true_peak_it_cannot_read(here, media):
    script = dv.delivery_script(rel_sheet(here, sheet_with("{mode: auto}", cuts=PARITY_CUTS, check="false")))
    proc, _ = run_script(here, script, peaks=[""])
    assert proc.returncode != 0 and "could not measure the true peak" in proc.stderr


@needs_sh
def test_the_dry_run_script_refuses_an_unmeasurable_master_in_loudness_mode(here, media):
    script = dv.delivery_script(rel_sheet(here, sheet_with("{mode: loudness}", check="false")))
    proc, ran = run_script(here, script, lufs="-inf")
    assert proc.returncode != 0 and "could not measure the loudness" in proc.stderr
    assert not any("-af" in argv and "aac" in argv for argv in ran)  # nothing was encoded


@needs_sh
def test_nothing_in_a_path_expands_or_runs_in_the_dry_run_script(here):
    """The review's cases -- $(...), backticks, quotes, $HOME -- and two of
    this script's own: a literal ${G} (the gain's variable) and a directory
    whose name starts with '-' (mkdir would read it as an option)."""
    (here / "_work").mkdir()
    for name in ("_work/film $(touch pwned2).mp4", "_work/the artist's card.mp4", "Song.wav"):
        (here / name).write_bytes(b"placeholder")
    nasty = "x $(touch pwned) ${G} `touch pwned3` \"q\" 's $HOME.mp4"
    cuts = (
        f"  - {{out: '{nasty.replace(chr(39), chr(39) * 2)}', t0: 0, dur: 4}}\n"
        "  - {out: -renders/y.mp4, t0: 51, dur: 131, card: \"_work/the artist's card.mp4\", video_from: 53}\n"
    )
    text = sheet_with("{mode: loudness}", cuts=cuts).replace("_work/full_silent.mp4", "'_work/film $(touch pwned2).mp4'")
    script = dv.delivery_script(rel_sheet(here, text))
    proc, ran = run_script(here, script)
    assert proc.returncode == 0, proc.stderr
    assert not any((here / p).exists() for p in ("pwned", "pwned2", "pwned3"))
    assert (here / nasty).exists() and (here / "-renders" / "y.mp4").exists()
    assert any(argv[-1] == f"./{nasty}" for argv in ran)  # the literal name reached ffmpeg
    listing = [argv for argv in ran if "concat" in argv]
    assert listing and not (here / ".kaleidophone-cache").exists()


# --------------------------------------------------------------------------
# no private helpers borrowed from elsewhere
# --------------------------------------------------------------------------
def test_deliver_uses_the_public_quoting_and_bitrate_check():
    """One concat quoting and one bitrate pattern for the package, both in
    _ffmpeg_util (the staff-engineering review found this module importing
    two private names from others)."""
    assert dv.concat_quote is fu.concat_quote and dv.BITRATE_RE is fu.BITRATE_RE


# --------------------------------------------------------------------------
# endings as variants (issue #58)
# --------------------------------------------------------------------------
#
# A piece rendered with `render.mjs --endings`: a body from song time 51 s to
# the join at 61 s, and two endings from 61 s to the window's end at 67 s --
# 240 and 144 frames at 24 fps. Each ending is delivered as a file of its
# own: the body and that ending joined, the master under the whole 16 s.

MANIFEST = "_work/reel.variants.json"
REEL = "  - {out: SONG_reel.mp4, t0: 51, dur: 16, endings: _work/reel.variants.json}\n"
CARD_REEL = (
    "  - {out: SONG_reel.mp4, t0: 51, dur: 16, card: _work/card_silent.mp4, video_from: 53, "
    "endings: _work/reel.variants.json}\n"
)
LISTED = (
    "  - out: SONG_reel.mp4\n    t0: 51\n    dur: 16\n    body: _work/reel.body.mp4\n    at: 61\n"
    "    endings:\n      - {name: rain, file: _work/reel.ending-rain.mp4}\n"
    "      - {name: door, file: _work/reel.ending-door.mp4}\n"
)


def variants(**overrides) -> dict:
    """render.mjs's manifest, as the interface fixes it."""
    data = {
        "piece": "template", "axis": "ending", "at": 61.0, "t0": 51.0, "dur": 16.0, "fps": 24,
        "body": {"file": "reel.body.mp4", "frames": 240},
        "endings": [
            {"option": "rain", "file": "reel.ending-rain.mp4", "frames": 144},
            {"option": "door", "file": "reel.ending-door.mp4", "frames": 144},
        ],
        "stream": {"codec": "h264", "profile": "High", "level": 31, "pix_fmt": "yuv420p", "width": 1080,
                   "height": 1920, "fps": 24, "time_base": "1/12288", "sar": "1:1"},
    }
    data.update(overrides)
    return data


def write_variants(where, **overrides) -> None:
    (where / "_work").mkdir(exist_ok=True)
    (where / MANIFEST).write_text(json.dumps(variants(**overrides)))


class FakeProbe:
    """ffprobe for the parts (and the delivered files): per file name, its
    frame count, any `stream=` entry, and its keyframes. By default every
    part is one encode and starts on a keyframe."""

    STREAM: ClassVar[dict[str, str]] = {
        "codec_name": "h264", "profile": "High", "level": "31", "pix_fmt": "yuv420p", "width": "1080",
        "height": "1920", "r_frame_rate": "24/1", "time_base": "1/12288", "sample_aspect_ratio": "1:1",
        "start_time": "0.000000",
    }

    def __init__(self):
        self.frames = {
            "reel.body.mp4": "240", "reel.ending-rain.mp4": "144", "reel.ending-door.mp4": "144",
            "card_silent.mp4": "48", "SONG_reel.rain.mp4": "384", "SONG_reel.door.mp4": "384",
        }
        self.entries: dict[str, dict[str, str]] = {}
        self.keyframes: dict[str, list[float]] = {"full_silent.mp4": [0.0, 26.25, 51.0, 53.0]}

    def stream(self, path, stream, entry, count_packets=False):
        name = os.path.basename(path)
        if entry == "nb_read_packets":
            return self.frames.get(name)
        return self.entries.get(name, {}).get(entry, self.STREAM.get(entry))

    def keyframes_of(self, path):
        return self.keyframes.get(os.path.basename(path), [0.0])


@pytest.fixture
def parts(media, fake, monkeypatch):
    """The parts and their manifest next to the other placeholders, and an
    ffprobe that answers for them."""
    for name in ("reel.body.mp4", "reel.ending-rain.mp4", "reel.ending-door.mp4"):
        (media / "_work" / name).write_bytes(b"placeholder")
    write_variants(media)
    probe = FakeProbe()
    monkeypatch.setattr(dv, "probe_stream", probe.stream)
    monkeypatch.setattr(dv, "probe_keyframes", probe.keyframes_of)
    return probe


def capture_listings(fake, monkeypatch) -> list[str]:
    """Every concat list, read as ffmpeg is handed it."""
    listings = []

    def run(ffmpeg, args):
        if "concat" in args:
            listings.append(open(args[args.index("-i") + 1]).read())
        fake.run(ffmpeg, args)

    monkeypatch.setattr(dv, "run", run)
    return listings


# --- the sheet ---------------------------------------------------------------
def test_a_cut_takes_its_endings_from_a_manifest_or_lists_them(tmp_path):
    from_manifest = dv.load_sheet(write_sheet(tmp_path, sheet_with(cuts=REEL))).cuts[0]
    assert from_manifest.endings == MANIFEST and from_manifest.body is None
    listed = dv.load_sheet(write_sheet(tmp_path, sheet_with(cuts=LISTED))).cuts[0]
    assert [(e.name, e.file) for e in listed.endings] == [
        ("rain", "_work/reel.ending-rain.mp4"), ("door", "_work/reel.ending-door.mp4")
    ]
    assert (listed.body, listed.at) == ("_work/reel.body.mp4", 61)


def test_a_sheet_whose_every_cut_has_endings_needs_no_silent_render(tmp_path):
    sheet = dv.load_sheet(write_sheet(tmp_path, "audio: Song.wav\ncuts:\n" + REEL))
    assert sheet.silent is None
    with pytest.raises(ValueError, match=r"`silent` \(the render\) is required: x.mp4 is cut from it"):
        dv.load_sheet(write_sheet(tmp_path, "audio: Song.wav\ncuts:\n" + REEL + "  - {out: x.mp4, t0: 0, dur: 1}\n"))


def _listed(extra: str = "", endings: str = "[{name: rain, file: r.mp4}, {name: door, file: d.mp4}]") -> str:
    return sheet_with(cuts=f"  - {{out: r.mp4, t0: 51, dur: 16, body: b.mp4, at: 61, endings: {endings}{extra}}}\n")


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, endings: v.json, at: 61}\n"), "at come from its variants manifest"),
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, body: b.mp4}\n"), "body go with a list of `endings`"),
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, endings: [{name: a, file: a.mp4}]}\n"), "needs `body`"),
        (_listed(endings="[]"), "lists no endings"),
        (_listed(endings="5"), "a variants manifest \\(its path\\) or a list"),
        (_listed(endings="[{name: rain}]"), r"cuts\[0\].endings: \[0\].file: Field required"),
        (_listed(endings="[{name: a, file: a.mp4}, {name: b, file: b.mp4, oops: 1}]"), r"\[1\].oops: Extra inputs"),
        (_listed(endings="[rain]"), r"\[0\]: Input should be a valid dictionary"),
        (_listed(endings="[{name: a/b, file: a.mp4}]"), "must be a plain name"),
        (_listed(endings="[{name: .hidden, file: a.mp4}]"), "must be a plain name"),
        (_listed(endings="[{name: 'rain ', file: a.mp4}]"), "must be a plain name"),
        (_listed(endings="[{name: Rain, file: a.mp4}, {name: rain, file: b.mp4}]"), "'Rain' and 'rain' would write one file"),
        (_listed(endings="[{name: rain, file: \"a\\n.mp4\"}]"), "control character"),
        (_listed(", video_from: 62, card: c.mp4"), "the card has to end in the body"),
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, body: b.mp4, at: 70, endings: [{name: a, file: a.mp4}]}\n"),
         r"at \(70\) must fall inside the cut \(51..67\)"),
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, body: b.mp4, at: 61.01, endings: [{name: a, file: a.mp4}]}\n"),
         "at 61.01 isn't on the 24 fps frame grid"),
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, body: \"b\\n.mp4\", at: 61, endings: [{name: a, file: a.mp4}]}\n"),
         "control character"),
        (sheet_with(cuts="  - {out: r.mp4, t0: 51, dur: 16, endings: \"v\\n.json\"}\n"), "control character"),
        (_listed() + "  - {out: r.rain.mp4, t0: 0, dur: 4}\n", "two cuts write 'r.rain.mp4'"),
        (sheet_with(cuts="  - {out: a.mp4, t0: 0, dur: 4, endings: v.json}\n  - {out: a.mov, t0: 0, dur: 4, endings: w.json}\n"),
         "two cuts write 'a.endings.jpg'"),
    ],
)
def test_a_sheet_with_endings_that_cant_be_delivered_says_why(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        dv.load_sheet(write_sheet(tmp_path, text))


def test_each_ending_is_delivered_beside_its_cut_and_shown_on_one_contact_sheet():
    assert dv.ending_out("reels/SONG_reel.mp4", "rain") == "reels/SONG_reel.rain.mp4"
    assert dv.ending_out("SONG.MOV", "door") == "SONG.door.MOV"
    assert dv.contact_sheet_out("reels/SONG_reel.m4v") == "reels/SONG_reel.endings.jpg"


# --- the manifest ---------------------------------------------------------------
def test_the_manifests_files_sit_next_to_it(here):
    write_variants(here)
    sheet = dv.load_sheet(rel_sheet(here, sheet_with(cuts=REEL)))
    (resolved,) = dv._resolve_endings(sheet, dv._paths("deliver.yaml", None)).values()
    assert resolved.body == "_work/reel.body.mp4" and resolved.frames == 240
    assert [(e.name, e.file, e.frames) for e in resolved.endings] == [
        ("rain", "_work/reel.ending-rain.mp4", 144), ("door", "_work/reel.ending-door.mp4", 144)
    ]


@pytest.mark.parametrize(
    ("overrides", "extra", "problem"),
    [
        ({"fps": 12}, {}, "its variants were rendered at 12 fps; the sheet's fps is 24"),
        ({"t0": 50.0, "at": 60.0}, {}, "its variants start at song time 50.000 s, the cut at 51.000 s"),
        ({}, {"silent_start": "1"},
         "its variants start at song time 51.000 s, the cut at song time 52.000 s (silent_start 1 + t0 51)"),
        ({"dur": 20.0}, {}, "its variants run 20 s, the cut 16 s"),
        ({"at": 80.0}, {}, "its manifest's at (80 s) isn't inside its window (51..67 s)"),
        ({"body": {"file": "reel.body.mp4", "frames": 239}, "endings": [{"option": "rain", "file": "r.mp4", "frames": 145}]},
         {}, "its body has 239 frames, but 51..61 s at 24 fps is 240"),
        ({"endings": [{"option": "rain", "file": "r.mp4", "frames": 143}]}, {},
         "ending 'rain' has 143 frames: after the body's 240 that is 383, and the cut is 384"),
        ({"endings": [{"option": "rain", "file": "r.mp4", "frames": 144}, {"option": "RAIN", "file": "s.mp4", "frames": 144}]},
         {}, "two endings named 'rain' and 'RAIN' would write one file"),
    ],
)
def test_a_manifest_that_doesnt_fit_its_cut_is_refused_in_one_line(tmp_path, overrides, extra, problem):
    write_variants(tmp_path, **overrides)
    with pytest.raises(ValueError) as exc:
        dv.delivery_script(write_sheet(tmp_path, sheet_with(cuts=REEL, **extra)))
    assert str(exc.value).splitlines() == ["the endings don't fit their cuts:", f"  SONG_reel.mp4: {problem}"]


def test_a_card_that_runs_past_the_join_is_refused(tmp_path):
    write_variants(tmp_path, body={"file": "reel.body.mp4", "frames": 240}, at=61.0)
    cuts = "  - {out: SONG_reel.mp4, t0: 51, dur: 16, card: c.mp4, video_from: 66, endings: _work/reel.variants.json}\n"
    with pytest.raises(ValueError, match="its card \\(360 frames\\) runs to or past the join at frame 240"):
        dv.delivery_script(write_sheet(tmp_path, sheet_with(cuts=cuts)))


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("{not json", "is not JSON"),
        ("[1, 2]", "expected an object with body and endings"),
        (json.dumps({k: v for k, v in variants().items() if k != "body"}), "is not a variants manifest: body: Field required"),
        (json.dumps(variants(body={"file": "../reel.body.mp4", "frames": 240})), "must be a file name next to the manifest"),
        (json.dumps(variants(body={"file": "reel.body.mp4", "frames": 0})), r"body.frames: Input should be greater than"),
        (json.dumps(variants(endings=[])), "endings: List should have at least 1 item"),
    ],
)
def test_a_malformed_manifest_is_refused_in_one_line(tmp_path, content, match):
    (tmp_path / "_work").mkdir()
    (tmp_path / MANIFEST).write_text(content)
    with pytest.raises(ValueError, match=match) as exc:
        dv.delivery_script(write_sheet(tmp_path, sheet_with(cuts=REEL)))
    assert len(str(exc.value).splitlines()) == 1


def test_a_missing_manifest_is_a_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        dv.delivery_script(write_sheet(tmp_path, sheet_with(cuts=REEL)))


def test_a_manifests_endings_cant_overwrite_another_cut(tmp_path):
    write_variants(tmp_path)
    with pytest.raises(ValueError, match=r"two cuts write 'SONG_reel\.door\.mp4'"):
        dv.delivery_script(write_sheet(tmp_path, sheet_with(cuts=REEL + "  - {out: SONG_reel.door.mp4, t0: 0, dur: 4}\n")))


# --- the joins, the mux, the guard ------------------------------------------
def test_each_ending_is_the_body_and_the_ending_joined_then_muxed_under_the_whole_cut(parts, fake, media, monkeypatch):
    listings = capture_listings(fake, monkeypatch)
    logged = []
    rain, door = dv.deliver(write_sheet(media, sheet_with(cuts=REEL)), log=logged.append)
    join_rain, join_door, mux_rain, mux_door, contact = fake.runs
    assert listings == [
        "file '../../_work/reel.body.mp4'\nfile '../../_work/reel.ending-rain.mp4'\n",
        "file '../../_work/reel.body.mp4'\nfile '../../_work/reel.ending-door.mp4'\n",
    ]
    assert arg_after(join_rain, "-c") == "copy" and join_rain[-1].endswith("cut01.e01.silent.mp4")
    for mux, join in ((mux_rain, join_rain), (mux_door, join_door)):
        assert arg_after(mux, "-i", 0) == join[-1]  # the joined picture, whole
        assert mux.index("-ss") > mux.index("-i") and arg_after(mux, "-ss") == "51.000000"  # the audio's seek only
        assert arg_after(mux, "-t") == "16.000000" and arg_after(mux, "-frames:v") == "384"
    assert mux_rain[-1].endswith("SONG_reel.rain.mp4") and mux_door[-1].endswith("SONG_reel.door.mp4")
    assert (rain.cut, rain.ending, door.ending, rain.frames_expected) == ("SONG_reel.mp4", "rain", "door", 384)
    assert rain.contact_sheet is door.contact_sheet and rain.contact_sheet.endings == ("rain", "door")
    assert contact[-1].endswith("SONG_reel.endings.jpg") and rain.frames == 384
    assert "SONG_reel.mp4: the body and each of 2 endings, joined by stream copy" in logged
    assert not (media / ".kaleidophone-cache").exists()


def test_endings_listed_in_the_sheet_join_the_same_way(parts, fake, media, monkeypatch):
    listings = capture_listings(fake, monkeypatch)
    dv.deliver(write_sheet(media, sheet_with(cuts=LISTED)))
    assert listings[1] == "file '../../_work/reel.body.mp4'\nfile '../../_work/reel.ending-door.mp4'\n"


def test_the_endings_share_the_masters_one_gain_and_are_stepped_together(parts, fake, media):
    """The door ending comes out at -0.2 dBTP, 1.8 dB over a -2 dBTP ceiling:
    both endings go again, 2 dB down -- one gain per master."""
    fake.peaks = [-2.5, -0.2, -4.4, -2.3]
    logged = []
    rain, door = dv.deliver(write_sheet(media, sheet_with("{mode: auto}", cuts=REEL)), log=logged.append)
    assert [arg_after(a, "-af").split(",")[0] for a in fake.encodes] == ["volume=0.00dB"] * 2 + ["volume=-2.00dB"] * 2
    assert rain.gain_db == door.gain_db == -2.0 and (rain.true_peak, door.true_peak) == (-4.4, -2.3)
    assert any(line.startswith("SONG_reel.door.mp4 peaked at -0.2 dBTP") for line in logged)
    assert [os.path.basename(m[m.index("-i") + 1]) for m in fake.peak_measures] == [
        "SONG_reel.rain.mp4", "SONG_reel.door.mp4"
    ] * 2


def test_a_card_cut_with_endings_puts_the_card_in_front_of_every_join(parts, fake, media, monkeypatch):
    parts.keyframes["reel.body.mp4"] = [0.0, 2.0]
    listings = capture_listings(fake, monkeypatch)
    dv.deliver(write_sheet(media, sheet_with(cuts=CARD_REEL)))
    tail = fake.runs[0]
    assert arg_after(tail, "-ss") == "2.000000" and arg_after(tail, "-i").endswith("reel.body.mp4")
    assert arg_after(tail, "-frames:v") == "192"  # the body's 240 frames, less the 48 under the card
    assert listings[0] == "file '../../_work/card_silent.mp4'\nfile 'cut01.tail.mp4'\nfile '../../_work/reel.ending-rain.mp4'\n"


def test_a_silent_cut_with_endings_delivers_every_ending_silent(parts, fake, media):
    text = "cuts:\n  - {out: SONG_canvas.mp4, t0: 51, dur: 16, audio: none, endings: _work/reel.variants.json}\n"
    canvas_rain, _ = dv.deliver(write_sheet(media, text))
    assert len(fake.silent_cuts) == 2 and fake.measures == [] and not canvas_rain.has_audio
    assert arg_after(fake.silent_cuts[0], "-i").endswith("cut01.e01.silent.mp4")


def test_the_joins_intermediates_go_even_when_an_encode_fails(parts, fake, media, monkeypatch):
    def run(ffmpeg, args):
        fake.run(ffmpeg, args)
        if "-af" in args:
            raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(dv, "run", run)
    parts.keyframes["reel.body.mp4"] = [0.0, 2.0]
    with pytest.raises(RuntimeError):
        dv.deliver(write_sheet(media, sheet_with(cuts=CARD_REEL)))
    assert not (media / ".kaleidophone-cache").exists()


def test_the_keyframe_list_leaves_out_a_cut_with_endings():
    sheet = dv.DeliverySheet.model_validate({
        "silent": "s.mp4", "audio": "a.wav",
        "cuts": [{"out": "a.mp4", "t0": 10, "dur": 2}, {"out": "r.mp4", "t0": 51, "dur": 16, "endings": "v.json"}],
    })
    assert dv._keyframe_list(sheet) == "0,10,12"


# --- the preflight -------------------------------------------------------------
def test_every_part_of_a_join_must_exist(parts, fake, media):
    (media / "_work" / "reel.ending-door.mp4").unlink()
    with pytest.raises(FileNotFoundError) as exc:
        dv.deliver(write_sheet(media, sheet_with(cuts=REEL)))
    assert exc.value.filename.endswith("reel.ending-door.mp4") and fake.runs == []


def _wrong_frames(probe):
    probe.frames["reel.ending-door.mp4"] = "143"


def _late_keyframe(probe):
    probe.keyframes["reel.ending-rain.mp4"] = [0.5]


def _no_keyframe(probe):
    probe.keyframes["reel.ending-rain.mp4"] = []


def _other_encode(probe):
    probe.entries["reel.ending-door.mp4"] = {"width": "720", "pix_fmt": "yuv444p"}


def _other_rate(probe):
    for name in ("reel.body.mp4", "reel.ending-rain.mp4", "reel.ending-door.mp4"):
        probe.entries[name] = {"r_frame_rate": "25/1"}


@pytest.mark.parametrize(
    ("spoil", "problem"),
    [
        (_wrong_frames, "ending 'door' (reel.ending-door.mp4) has 143 frames; its span needs 144"),
        (_late_keyframe, "ending 'rain' (reel.ending-rain.mp4) doesn't start on a keyframe (its first is 0.500 s in)"),
        (_no_keyframe, "ending 'rain' (reel.ending-rain.mp4) doesn't start on a keyframe (it has none)"),
        (_other_encode, "ending 'door' (reel.ending-door.mp4) isn't the same encode as the body: "
                        "pix_fmt yuv444p, not yuv420p; width 720, not 1080"),
        (_other_rate, "the body (reel.body.mp4) runs at 25/1 fps; the sheet's fps is 24"),
    ],
)
def test_parts_that_cant_be_joined_are_refused_before_anything_runs(parts, fake, media, spoil, problem):
    spoil(parts)
    with pytest.raises(ValueError) as exc:
        dv.deliver(write_sheet(media, sheet_with(cuts=REEL)))
    (line,) = str(exc.value).splitlines()[1:]
    assert line.startswith(f"  SONG_reel.mp4: {problem}")
    assert "-force_key_frames" not in str(exc.value)  # nothing to re-render in the silent render
    assert fake.runs == [] and fake.measures == []


def test_a_card_cut_with_endings_needs_a_body_keyframe_where_the_card_ends(parts, fake, media):
    with pytest.raises(ValueError, match=r"the body has no keyframe at 2\.000 s, where the card ends"):
        dv.deliver(write_sheet(media, sheet_with(cuts=CARD_REEL)))


def test_a_part_that_starts_later_than_zero_is_held_to_its_own_start(parts, fake, media):
    parts.entries["reel.ending-rain.mp4"] = {"start_time": "0.500000"}
    parts.keyframes["reel.ending-rain.mp4"] = [0.5]
    parts.entries["reel.ending-door.mp4"] = {"start_time": "N/A"}  # unreadable: from 0
    assert len(dv.deliver(write_sheet(media, sheet_with(cuts=REEL)))) == 2


def test_a_part_encoded_with_other_settings_is_a_warning(parts, fake, media):
    """An x264 CRF sets the PPS's pic_init_qp: every stream parameter agrees
    and the headers still differ. ffmpeg decodes the join; a strict player
    may not."""
    fake.headers["reel.ending-door.mp4"] = trace_log("4")
    logged = []
    dv.deliver(write_sheet(media, sheet_with(cuts=REEL)), log=logged.append)
    (warning,) = [line for line in logged if "encoded with other settings" in line]
    assert "ending 'door' (reel.ending-door.mp4) was encoded with other settings than the body" in warning
    assert "their stream headers differ (pic_init_qp_minus26 4, not -6)" in warning
    assert len(fake.traces) == 3 and "keyframes for every cut point" not in "\n".join(logged)


def test_the_header_check_is_skipped_where_ffmpeg_cant_trace_the_headers(parts, fake, media, monkeypatch):
    def run_measure(ffmpeg, args):
        if "-bsf:v" in args:
            raise RuntimeError("Codec 'prores' is not supported by the bitstream filter 'trace_headers'")
        return fake.run_measure(ffmpeg, args)

    monkeypatch.setattr(dv, "run_measure", run_measure)
    logged = []
    dv.deliver(write_sheet(media, sheet_with(cuts=REEL)), log=logged.append)
    assert not any(line.startswith("warning:") for line in logged)
    assert dv._parameter_sets("ffmpeg", "x.mp4") is None
    monkeypatch.setattr(dv, "run_measure", lambda ffmpeg, args: "no extradata here")
    assert dv._parameter_sets("ffmpeg", "x.mp4") is None


def test_the_first_header_field_two_parts_disagree_on_is_named():
    first = [("profile_idc", "100"), ("pic_init_qp_minus26", "-6")]
    assert dv._header_difference(first, list(first)) is None
    assert dv._header_difference(first, [("profile_idc", "100"), ("pic_init_qp_minus26", "4")]) == (
        "pic_init_qp_minus26 4, not -6"
    )
    assert dv._header_difference(first, [("level_idc", "31")]) == "level_idc where the first has profile_idc"
    assert dv._header_difference(first, first[:1]) == "1 header fields, not 2"


@pytest.mark.parametrize(("text", "rate"), [("24/1", 24.0), ("30000/1001", 30000 / 1001), ("25", 25.0),
                                            ("N/A", None), (None, None), ("1/0", None)])
def test_a_frame_rate_reads_as_ffprobe_writes_it(text, rate):
    assert dv._rate(text) == rate


def test_the_endings_preflight_is_best_effort_without_ffprobe(parts, fake, media, monkeypatch):
    monkeypatch.setattr(dv, "probe_stream", lambda *a, **k: None)
    monkeypatch.setattr(dv, "probe_keyframes", lambda path: None)
    rain, _ = dv.deliver(write_sheet(media, sheet_with(cuts=CARD_REEL)))
    assert rain.frames is None and rain.size_mb is not None


# --- the contact sheet ---------------------------------------------------------
SHEET_ROW = (
    "select='eq(n,239)+eq(n,240)+eq(n,269)+eq(n,297)+eq(n,326)+eq(n,354)+eq(n,383)',scale=-2:320,setsar=1,"
    "tile=7x1:margin=8:padding=8:color=0x111111,drawbox=x=(iw-64)/7+10:y=0:w=4:h=ih:color=0xe03c31:t=fill"
)
SHEET_LABEL = (
    ",pad=iw:ih+36:0:36:color=0x111111,"
    "drawtext=text=\\'{}\\':expansion=none:fontcolor=white:fontsize=22:x=8:y=(36-th)/2"
)


def test_a_contact_sheet_row_is_the_last_body_frame_then_six_frames_of_its_ending():
    """By frame index, so the sheet is the same every run: 239 is the body's
    last; 240..383 the ending, its first and last included."""
    assert dv._sheet_picks(240, 384) == [239, 240, 269, 297, 326, 354, 383]
    assert dv._sheet_picks(240, 243) == [239, 240, 241, 242]  # a short ending: every frame
    assert dv._sheet_picks(240, 241) == [239, 240]


def test_the_contact_sheet_is_one_filter_graph_of_rows_stacked_top_to_bottom():
    picks = dv._sheet_picks(240, 384)
    argv = dv._contact_sheet_argv(["a.rain.mp4", "a.door.mp4"], ["rain", "door"], picks, "a.endings.jpg", labelled=True)
    assert arg_after(argv, "-filter_complex") == (
        f"[0:v:0]{SHEET_ROW}{SHEET_LABEL.format('rain')}[r0];[1:v:0]{SHEET_ROW}{SHEET_LABEL.format('door')}[r1];"
        "[r0][r1]vstack=inputs=2[sheet]"
    )
    assert argv[:5] == ["-y", "-i", "./a.rain.mp4", "-i", "./a.door.mp4"]
    assert argv[-9:] == ["-map", "[sheet]", "-frames:v", "1", "-q:v", "2", "-update", "1", "./a.endings.jpg"]
    single = dv._contact_sheet_argv(["a.rain.mp4"], ["rain"], picks, "a.endings.jpg", labelled=False)
    assert arg_after(single, "-filter_complex") == f"[0:v:0]{SHEET_ROW}[sheet]"  # nothing to stack


@pytest.mark.parametrize(
    ("name", "quoted"),
    [("rain", "\\'rain\\'"), ("it's: a, [b]; c\\d", "\\'it\\'\\\\\\'\\'s: a\\, \\[b\\]\\; c\\\\d\\'"), ("خانه", "\\'خانه\\'")],
)
def test_a_label_is_quoted_for_both_of_the_graphs_parsers(name, quoted):
    """Measured with ffmpeg 6.1: each of these drew exactly as written."""
    assert dv._filter_text(name) == quoted


def test_a_contact_sheet_without_drawtext_is_unlabelled_and_says_so(parts, fake, media):
    rain, _ = dv.deliver(write_sheet(media, sheet_with(cuts=REEL)))
    (contact,) = [a for a in fake.runs if a[-1].endswith(".jpg")]
    assert "drawtext" not in arg_after(contact, "-filter_complex")
    assert not rain.contact_sheet.labelled and rain.contact_sheet.note == "this ffmpeg has no drawtext filter"


def test_a_contact_sheet_is_labelled_where_drawtext_works(parts, fake, media, monkeypatch):
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset({"text", "latency"}))
    rain, _ = dv.deliver(write_sheet(media, sheet_with(cuts=REEL)))
    (contact,) = [a for a in fake.runs if a[-1].endswith(".jpg")]
    assert "drawtext=text=\\'door\\'" in arg_after(contact, "-filter_complex") and rain.contact_sheet.labelled


@pytest.mark.parametrize(
    ("said", "why"),
    [
        ("[Parsed_drawtext_9 @ 0x1] Cannot find a valid font for the family Sans\nError initializing filters",
         "[Parsed_drawtext_9 @ 0x1] Cannot find a valid font for the family Sans"),
        ("Error initializing filters", "Error initializing filters"),
    ],
)
def test_a_contact_sheet_whose_drawtext_fails_is_made_again_unlabelled(parts, fake, media, monkeypatch, said, why):
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset({"text", "latency"}))

    def run(ffmpeg, args):
        fake.run(ffmpeg, args)
        if any("drawtext" in a for a in args):
            raise RuntimeError(f"ffmpeg failed (args tail: -update 1 ./x.jpg):\n{said}")

    monkeypatch.setattr(dv, "run", run)
    rain, _ = dv.deliver(write_sheet(media, sheet_with(cuts=REEL)))
    labelled, unlabelled = [a for a in fake.runs if a[-1].endswith(".jpg")]
    assert "drawtext" in arg_after(labelled, "-filter_complex") and "drawtext" not in arg_after(unlabelled, "-filter_complex")
    assert rain.contact_sheet.note == f"this ffmpeg's drawtext failed ({why})"


def test_the_table_lists_every_ending_and_its_contact_sheet_once():
    contact = dv.ContactSheet("out/SONG_reel.endings.jpg", ("rain", "door"), 6, labelled=False, note="no drawtext")
    rows = [dv.Delivered(f"out/SONG_reel.{n}.mp4", 384, frames=384, ending=n, contact_sheet=contact) for n in ("rain", "door")]
    lines = dv.format_table(rows).splitlines()
    assert lines[1].startswith("SONG_reel.rain.mp4") and lines[2].startswith("SONG_reel.door.mp4")
    assert lines[3:] == [
        "contact sheet SONG_reel.endings.jpg: rain, door, top to bottom -- the last body frame, then 6 frames "
        "of each ending; unlabelled: no drawtext"
    ]
    one = dv.ContactSheet("x.endings.jpg", ("a",), 1, labelled=True)
    assert one.describe() == "contact sheet x.endings.jpg: a, top to bottom -- the last body frame, then 1 frame of each ending"


# --- --dry-run ----------------------------------------------------------------
def test_the_dry_run_of_a_sheet_of_endings(here):
    write_variants(here)
    script = dv.delivery_script(rel_sheet(here, "audio: Song.wav\ncuts:\n" + REEL))
    assert "-force_key_frames" not in script  # nothing is cut from a silent render
    assert "# A cut with endings is its body and each ending, joined by stream copy" in script
    assert "mkdir -p -- .kaleidophone-cache/deliver\n" in script
    assert "# the endings of SONG_reel.mp4: the body, then each ending, joined by stream copy\n" in script
    assert (
        "cat > .kaleidophone-cache/deliver/cut01.e02.concat.txt <<'EOF'\n"
        "file '../../_work/reel.body.mp4'\nfile '../../_work/reel.ending-door.mp4'\nEOF\n"
    ) in script
    assert "\n  DRAWTEXT=1\n" in script and '\nif [ "$DRAWTEXT" = 1 ] && ffmpeg ' in script
    assert "# 2/2  SONG_reel.door.mp4: 51.000-67.000 s, 384 frames, ending door" in script
    assert "check ./SONG_reel.rain.mp4 384\ncheck ./SONG_reel.door.mp4 384" in script
    assert str(here) not in script


def test_the_dry_run_of_a_card_cut_with_endings_says_where_the_body_resumes(here):
    write_variants(here)
    script = dv.delivery_script(rel_sheet(here, sheet_with(cuts=CARD_REEL + "  - {out: x.mp4, t0: 0, dur: 4}\n")))
    assert "# the endings of SONG_reel.mp4: the card, the body from its keyframe at 2 s, then each ending" in script
    assert "-force_key_frames 0,4\n" in script  # only the cut from the silent render


PARITY_ENDINGS = REEL + "  - {out: full.mp4, t0: 0, dur: 72.25}\n"


@needs_sh
@pytest.mark.parametrize(
    ("cuts", "drawtext", "peaks"),
    [
        (PARITY_ENDINGS, "yes", ["-1.0", "-3.0", "-2.5", "-3.1", "-4.0", "-2.9"]),  # two rounds
        (CARD_REEL, "no", ["-3.0"]),
        (LISTED, "fails", ["-3.0"]),
    ],
)
def test_the_dry_run_script_runs_the_same_ffmpeg_commands_with_endings(here, parts, fake, monkeypatch, cuts, drawtext, peaks):
    parts.keyframes["reel.body.mp4"] = [0.0, 2.0]
    options = {"text", "latency"} if drawtext != "no" else {"latency"}
    monkeypatch.setattr(dv, "filter_options", lambda ffmpeg, name: frozenset(options))
    if drawtext == "fails":
        def run(ffmpeg, args):
            fake.run(ffmpeg, args)
            if any("drawtext" in a for a in args):
                raise RuntimeError("ffmpeg failed:\nCannot find a valid font for the family Sans")

        monkeypatch.setattr(dv, "run", run)
    fake.peaks = [float(p) for p in peaks]
    sheet = rel_sheet(here, sheet_with("{mode: auto}", cuts=cuts, check="false"))
    dv.deliver(sheet)
    proc, ran = run_script(here, dv.delivery_script(sheet), peaks=peaks, drawtext=drawtext)
    assert proc.returncode == 0, proc.stderr
    assert [argv for argv in ran if "-h" not in argv] == fake.log
    assert ("unlabelled" in proc.stdout) == (drawtext != "yes")


@needs_sh
def test_nothing_in_an_endings_name_or_path_expands_or_runs_in_the_dry_run_script(here):
    """Every name and path in single quotes for sh, in the concat demuxer's
    quoting in a list, and in the filter graph's for a label."""
    (here / "_work").mkdir()
    nasty = "x $(touch pwned) ${G} `touch pwned3` \"q\" 's $HOME"
    body, ending = "_work/body $(touch pwned2).mp4", "_work/-end 'n' `touch pwned4`.mp4"
    for name in (body, ending, "Song.wav"):
        (here / name).write_bytes(b"placeholder")
    cut = {"out": "reel.mp4", "t0": 0, "dur": 4, "body": body, "at": 2,
           "endings": [{"name": nasty, "file": ending}, {"name": "plain", "file": ending}]}
    sheet = rel_sheet(here, yaml.safe_dump({"audio": "Song.wav", "gain": {"mode": "auto"}, "cuts": [cut]}))
    proc, ran = run_script(here, dv.delivery_script(sheet), drawtext="yes")
    assert proc.returncode == 0, proc.stderr
    assert not any((here / p).exists() for p in ("pwned", "pwned2", "pwned3", "pwned4"))
    assert (here / f"reel.{nasty}.mp4").exists() and (here / "reel.plain.mp4").exists()
    (contact,) = [argv for argv in ran if "-filter_complex" in argv and "drawtext" in arg_after(argv, "-filter_complex")]
    assert dv._filter_text(nasty) in arg_after(contact, "-filter_complex") and contact[-1] == "./reel.endings.jpg"
    assert f"contact sheet reel.endings.jpg: {nasty}, plain, top to bottom" in proc.stdout
