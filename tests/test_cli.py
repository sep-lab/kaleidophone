"""cli.py: argument wiring, exit codes, and the failure path.

This module was at 0% coverage while being the first thing every user
touches. The expensive stages (analyze, render, ffmpeg) are monkeypatched --
what's under test is the CLI's own behaviour: does it exit with the right
code, does it pass the right things through, and does a failure produce one
actionable line instead of a traceback.
"""

from __future__ import annotations

import json

import pytest
import yaml
from factories import make_analysis, make_brief, make_media_asset, make_section, make_station

from kaleidophone import cli
from kaleidophone.render._ffmpeg_util import FfmpegNotFound


@pytest.fixture
def brief_file(tmp_path):
    brief = make_brief(
        stations=[make_station(name="s", media_dir=str(tmp_path / "media"))],
        sections=[make_section(name="A", start=0.0, end=10.0, station="s")],
    )
    path = tmp_path / "brief.yaml"
    path.write_text(yaml.safe_dump(brief.model_dump(exclude_none=True, mode="json"), sort_keys=False))
    return path


@pytest.fixture
def no_heavy_lifting(monkeypatch):
    """Stub out everything that decodes audio or shells out to ffmpeg."""
    monkeypatch.setattr(cli, "analyze", lambda *a, **k: make_analysis(duration=10.0))
    monkeypatch.setattr(cli, "_curate", lambda brief: {s.name: [make_media_asset("/m/0.jpg")] for s in brief.stations})
    monkeypatch.setattr(cli, "render_wavemap", lambda *a, **k: "wavemap.png")
    monkeypatch.setattr(cli, "generate_cover", lambda *a, **k: "cover.jpg")
    monkeypatch.setattr(cli, "generate_contact_sheet", lambda *a, **k: "sheet.jpg")
    monkeypatch.setattr(cli, "render_edl", lambda *a, **k: "master.mp4")
    monkeypatch.setattr(cli, "extract_teaser", lambda *a, **k: "teaser.mp4")
    monkeypatch.setattr(cli, "extract_thumbnail", lambda *a, **k: "thumb.jpg")


# --- top level -----------------------------------------------------------


def test_version_flag_reports_the_package_version(capsys):
    from kaleidophone import __version__

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_subcommand_prints_help_and_exits_nonzero(capsys):
    assert cli.main([]) == cli.EXIT_USAGE
    assert "usage" in capsys.readouterr().out.lower()


# --- the failure path ----------------------------------------------------
#
# Before this, every one of these surfaced as a raw traceback, burying the
# actionable message the code had already written.


def test_a_missing_brief_reports_one_clean_line_not_a_traceback(capsys):
    assert cli.main(["compose", "/nope/missing.yaml"]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith("kaleidophone: error:")
    assert "missing.yaml" in err
    assert "Traceback" not in err


def test_an_invalid_brief_reports_the_validation_error(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("song:\n  title: x\nstations: []\nsections: []\n")

    assert cli.main(["compose", str(bad)]) == cli.EXIT_ERROR

    err = capsys.readouterr().err
    assert "is not a valid brief" in err
    assert "Traceback" not in err


def test_a_missing_ffmpeg_surfaces_the_install_hint(monkeypatch, brief_file, tmp_path, capsys):
    edl = tmp_path / "edl.json"
    edl.write_text(json.dumps({"song_title": "t", "audio_path": "a", "duration": 1.0,
                               "fps": 24, "resolution": [640, 360], "cuts": []}))
    monkeypatch.setattr(cli, "render_silent", lambda *a, **k: (_ for _ in ()).throw(
        FfmpegNotFound("ffmpeg was not found on PATH. install it (e.g. `brew install ffmpeg`)")))

    assert cli.main(["silent", str(edl), str(brief_file)]) == cli.EXIT_ERROR

    err = capsys.readouterr().err
    assert "brew install ffmpeg" in err  # the useful half of the message survives
    assert "Traceback" not in err


def test_traceback_flag_re_raises_instead_of_swallowing():
    with pytest.raises(FileNotFoundError):
        cli.main(["--traceback", "compose", "/nope/missing.yaml"])


def test_debug_env_var_also_re_raises(monkeypatch):
    monkeypatch.setenv("KALEIDOPHONE_DEBUG", "1")
    with pytest.raises(FileNotFoundError):
        cli.main(["compose", "/nope/missing.yaml"])


# --- commands ------------------------------------------------------------


def test_compose_writes_an_edl_the_model_can_read_back(brief_file, tmp_path, no_heavy_lifting):
    out = tmp_path / "edl.json"
    assert cli.main(["compose", str(brief_file), "-o", str(out)]) == cli.EXIT_OK

    from kaleidophone.timeline.model import EDL

    edl = EDL.from_dict(json.loads(out.read_text()))
    assert edl.cuts
    assert edl.fps == 24


def test_run_preview_only_stops_before_the_render(brief_file, tmp_path, monkeypatch, no_heavy_lifting):
    rendered = []
    monkeypatch.setattr(cli, "render_edl", lambda *a, **k: rendered.append(a))

    assert cli.main(["run", str(brief_file), "-o", str(tmp_path / "out"), "--preview-only"]) == cli.EXIT_OK

    assert rendered == []
    assert (tmp_path / "out" / "edl.json").exists()


def test_run_writes_every_documented_artifact(brief_file, tmp_path, no_heavy_lifting):
    out = tmp_path / "out"
    assert cli.main(["run", str(brief_file), "-o", str(out)]) == cli.EXIT_OK
    assert (out / "edl.json").exists()
    assert (out / "promo_pack.md").exists()


def test_auto_writes_an_editable_brief_that_parses_back(tmp_path, monkeypatch, no_heavy_lifting):
    """ADR-0004's promise: auto mode's output is a normal brief, not a black
    box -- so it has to survive a round trip through the real schema."""
    brief = make_brief(
        stations=[make_station(name="s", media_dir=str(tmp_path))],
        sections=[make_section(name="A", start=0.0, end=10.0, station="s")],
    )
    monkeypatch.setattr(cli, "build_default_brief",
                        lambda *a, **k: (brief, {"s": [make_media_asset("/m/0.jpg")]}))
    out = tmp_path / "out"

    assert cli.main(["auto", "song.wav", str(tmp_path), "-o", str(out), "--preview-only"]) == cli.EXIT_OK

    from kaleidophone.timeline.schema import CreativeBrief

    reloaded = CreativeBrief.from_yaml(out / "generated_brief.yaml")
    assert reloaded.sections[0].name == "A"


def test_curate_writes_a_station_bucket_map(brief_file, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "scan_media", lambda d: [make_media_asset("/m/0.jpg")])
    out = tmp_path / "suggestion.json"

    assert cli.main(["curate", str(tmp_path), str(brief_file), "-o", str(out)]) == cli.EXIT_OK

    assert json.loads(out.read_text()) == {"s": ["/m/0.jpg"]}


# --- _curate's scan cache ------------------------------------------------


def test_stations_sharing_one_media_dir_are_scanned_once(tmp_path, monkeypatch):
    """`kaleidophone auto` writes a brief pointing every station at the same
    folder, and the README's next step re-runs it through `kaleidophone run`.
    Without the cache that decodes every photo once per station."""
    scanned = []
    monkeypatch.setattr(cli, "scan_media", lambda d: scanned.append(d) or [make_media_asset("/m/0.jpg")])
    shared = str(tmp_path / "photos")
    brief = make_brief(
        stations=[make_station(name=n, media_dir=shared) for n in ("a", "b", "c")],
        sections=[make_section(name="S", start=0.0, end=5.0, station="a")],
    )

    assets = cli._curate(brief)

    assert len(scanned) == 1
    assert set(assets) == {"a", "b", "c"}


def test_a_station_without_a_media_dir_gets_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "scan_media", lambda d: [make_media_asset("/m/0.jpg")])
    brief = make_brief(
        stations=[make_station(name="a", media_dir=None)],
        sections=[make_section(name="S", start=0.0, end=5.0, station="a")],
    )
    assert cli._curate(brief) == {"a": []}


# --- envelope ------------------------------------------------------------
#
# The analysis itself is tests/test_envelope.py's job; here it is stubbed and
# what's under test is the wiring: flags in, the pack out, one clean line on
# failure.


def _pack(**overrides) -> dict:
    pack = {
        "kaleidophone": "songpack/1",
        "fps": 100,
        "dur": 30.0,
        "bpm": 120.0,
        "beat0": 0.25,
        "period": 0.5,
        "beats": [0.25 + 0.5 * i for i in range(60)],
        "downbeat": 0.25,
        "bass": [0.0, 1.0],
        "loudest": {"start": 0.0, "len": 30.0},
    }
    pack.update(overrides)
    return pack


def test_envelope_writes_the_pack_and_passes_the_bpm_range_through(monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(cli, "envelope", lambda path, **kw: seen.update(path=path, **kw) or _pack())
    out = tmp_path / "packs" / "songpack.json"

    assert cli.main(["envelope", "song.wav", "-o", str(out), "--bpm-range", "60", "100"]) == cli.EXIT_OK

    assert seen == {"path": "song.wav", "bpm_range": (60.0, 100.0), "downbeat": None, "beats_per_bar": 4}
    assert json.loads(out.read_text())["bpm"] == 120.0
    printed = capsys.readouterr().out
    assert "bpm=120.00 beats=60" in printed
    assert "voc=no (mono input)" in printed
    assert "--bpm-range" in printed  # the hint for an octave error


def test_envelope_searches_60_to_200_bpm_by_default(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "envelope", lambda path, **kw: seen.update(kw) or _pack(voc=[0.0]))
    assert cli.main(["envelope", "song.wav", "-o", str(tmp_path / "p.json")]) == cli.EXIT_OK
    assert seen["bpm_range"] == (60.0, 200.0)


def test_envelope_passes_a_known_downbeat_and_bar_length_through(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "envelope", lambda path, **kw: seen.update(kw) or _pack())
    cli.main(
        ["envelope", "song.wav", "-o", str(tmp_path / "p.json"), "--downbeat", "1.25", "--beats-per-bar", "3"]
    )
    assert (seen["downbeat"], seen["beats_per_bar"]) == (1.25, 3)


def _grid_check(**overrides) -> dict:
    check = {
        "beats_per_bar": 4,
        "octave": {"bpm": 60.0, "score": 0.93},
        "downbeat": {"source": "estimated", "confidence": 0.45, "runner_up": 1.25},
        "sections": [
            {
                "bars": [1, 8],
                "start": 0.25,
                "end": 16.25,
                "offset_ms": 3,
                "max_ms": 12,
                "bpm": 120.0,
                "beats": 32,
                "off": 0,
            },
            {
                "bars": [9, 15],
                "start": 16.25,
                "end": 30.0,
                "offset_ms": None,
                "max_ms": None,
                "bpm": None,
                "beats": 28,
                "off": None,
            },
        ],
        "warnings": ["the tempo octave is a close call: ...", "bar 1 is a guess (confidence 0.45, ...)"],
    }
    check.update(overrides)
    return check


def test_envelope_prints_what_the_grid_check_is_unsure_of(monkeypatch, tmp_path, capsys):
    """The octave that lost and its score, how sure bar 1 is, how well the
    fixed grid fits, and every warning -- before the 'wrote' line."""
    monkeypatch.setattr(cli, "envelope", lambda path, **kw: _pack(grid_check=_grid_check()))
    cli.main(["envelope", "song.wav", "-o", str(tmp_path / "p.json")])
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "tempo     120.00 BPM; the other octave, 60.00 BPM, scores 0.93 of it"
    assert lines[2] == "downbeat  0.250 s (estimated, confidence 0.45; runner-up 1.250 s)"
    assert lines[3] == "grid fit  within 12 ms of the music in all 1 sections with a pulse"
    assert lines[4].startswith("warning: the tempo octave is a close call")
    assert lines[5].startswith("warning: bar 1 is a guess")
    assert lines[-1].startswith("wrote ")


def test_envelope_lists_every_section_when_the_grid_drifts(monkeypatch, tmp_path, capsys):
    sections = [
        {
            "bars": [1, 8],
            "start": 0.4,
            "end": 22.0,
            "offset_ms": 3,
            "max_ms": 29,
            "bpm": 88.31,
            "beats": 32,
            "off": 4,
        },
        {
            "bars": [9, 16],
            "start": 22.0,
            "end": 44.0,
            "offset_ms": -45,
            "max_ms": 96,
            "bpm": 88.97,
            "beats": 32,
            "off": 30,
        },
    ]
    check = _grid_check(octave=None, downbeat={"source": "given"}, sections=sections, warnings=[])
    monkeypatch.setattr(cli, "envelope", lambda path, **kw: _pack(grid_check=check))
    cli.main(["envelope", "song.wav", "-o", str(tmp_path / "p.json")])
    printed = capsys.readouterr().out
    assert "tempo     " not in printed
    assert "downbeat  0.250 s (given)" in printed
    assert "grid fit  ms from the music per 8 bars: 1-8 +3 (worst 29), 9-16 -45 (worst 96)" in printed


def test_envelope_on_a_missing_file_is_one_clean_line(tmp_path, capsys):
    assert cli.main(["envelope", str(tmp_path / "nope.wav")]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "nope.wav: no such file or directory" in err
    assert "Traceback" not in err


# --- master-check ----------------------------------------------------------


def _check(verdict: str):
    from kaleidophone.audio.mastercheck import Grid, MasterCheck

    detail = {
        "remux": "remux",
        "rerender": "rerender bars 8",
        "new grid": "new grid",
        "offset": "offset +0.350 s: set the delivery sheet's silent_start to 0.35",
    }[verdict]
    return MasterCheck(
        verdict=verdict,
        detail=detail,
        diagnosis="11/11 windows line up at 0.00 s",
        grid=Grid(bpm=120.0, downbeat=0.5, beats_per_bar=4, source="given"),
        windows=(),
        offset=0.35 if verdict == "offset" else 0.0,
        offset_r=1.0,
        sections=(),
        bars=(),
        old_duration=40.0,
        new_duration=40.0,
        old_audible=(0.5, 39.5),
        new_audible=(0.5, 39.5),
        new_silent_start=0.35 if verdict == "offset" else None,
    )


@pytest.mark.parametrize(("verdict", "code"), [("remux", 0), ("rerender", 3), ("new grid", 4), ("offset", 5)])
def test_master_check_exits_with_its_verdict(monkeypatch, capsys, verdict, code):
    """The exit code is the verdict, so a delivery script can stop itself
    before remuxing onto a grid that moved -- or, on 5, set silent_start."""
    monkeypatch.setattr(cli, "master_check", lambda *a, **k: _check(verdict))
    assert cli.main(["master-check", "old.wav", "new.wav"]) == code
    assert capsys.readouterr().out.rstrip().endswith(f"(exit {code})")


def test_master_check_passes_the_grid_and_thresholds_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "master_check", lambda old, new, **kw: seen.update(old=old, new=new, **kw) or _check("remux")
    )
    cli.main(
        [
            "master-check",
            "a.wav",
            "b.wav",
            "--bpm",
            "80",
            "--downbeat",
            "0.73",
            "--beats-per-bar",
            "3",
            "--max-delta",
            "0.2",
            "--max-new-voice",
            "0.3",
            "--min-r",
            "0.6",
            "--tolerance-ms",
            "10",
            "--silent-start",
            "43.89",
            "--envelopes",
            "voc, mid,rms",
        ]
    )
    assert seen == {
        "old": "a.wav",
        "new": "b.wav",
        "bpm": 80.0,
        "downbeat": 0.73,
        "beats_per_bar": 3,
        "max_delta": 0.2,
        "max_new_voice": 0.3,
        "min_r": 0.6,
        "tolerance": 0.01,
        "silent_start": 43.89,
        "envelopes": ("voc", "mid", "rms"),
    }


def test_master_check_leaves_the_grid_to_be_estimated_by_default(monkeypatch):
    from kaleidophone.audio.mastercheck import ENVELOPES

    seen = {}
    monkeypatch.setattr(cli, "master_check", lambda old, new, **kw: seen.update(kw) or _check("remux"))
    cli.main(["master-check", "a.wav", "b.wav"])
    assert seen["bpm"] is None and seen["downbeat"] is None and seen["beats_per_bar"] == 4
    assert seen["tolerance"] == pytest.approx(1 / 48, abs=1e-4)  # half a frame at 24 fps
    assert seen["silent_start"] == 0.0 and seen["envelopes"] == ENVELOPES


def test_master_check_json_writes_the_whole_check(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "master_check", lambda *a, **k: _check("rerender"))
    out = tmp_path / "checks" / "v2.json"
    assert cli.main(["master-check", "a.wav", "b.wav", "--json", str(out)]) == 3
    data = json.loads(out.read_text())
    assert data["verdict"] == "rerender" and data["exit_code"] == 3


def test_master_check_on_a_missing_master_is_one_clean_line(tmp_path, capsys):
    assert cli.main(["master-check", str(tmp_path / "old.wav"), str(tmp_path / "new.wav")]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "old.wav: no such file or directory" in err
    assert "Traceback" not in err


# --- deliver ---------------------------------------------------------------


@pytest.fixture
def sheet_here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "deliver.yaml").write_text(
        "silent: silent.mp4\naudio: Song.wav\nfps: 24\ngain: {mode: auto, start_db: -1.5}\n"
        "cuts:\n  - {out: SONG_story.mp4, t0: 26.25, dur: 16, fade_in: 0.25, fade_out: 1.2}\n"
    )
    return "deliver.yaml"


def test_deliver_dry_run_prints_only_the_script_on_stdout(sheet_here, capsys):
    assert cli.main(["deliver", sheet_here, "--dry-run"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert captured.out.startswith("#!/bin/sh\n")
    assert "-ss 26.250000 -i ./silent.mp4" in captured.out
    assert captured.err == ""  # so `> deliver.sh` captures exactly the script


def test_deliver_dry_run_notes_when_an_absolute_path_pins_the_script(sheet_here, tmp_path, capsys):
    assert cli.main(["deliver", str(tmp_path / sheet_here), "--dry-run"]) == cli.EXIT_OK
    assert "only runs on this machine" in capsys.readouterr().err


def _delivered(**overrides):
    from kaleidophone.render.deliver import Attempt, Delivered

    fields = {
        "out": "SONG_story.mp4", "frames_expected": 384, "gain_db": -2.5, "source_lufs": -8.81,
        "attempts": [Attempt(-1.5, None, -0.4), Attempt(-2.5, None, -1.2), Attempt(-2.5, None, -2.2)],
        "frames": 384, "duration": 16.0, "lufs": -13.9, "true_peak": -2.2, "size_mb": 3.1,
        "ceiling_dbtp": -2.0, "mode": "auto",
    }
    fields.update(overrides)
    return Delivered(**fields)


def test_deliver_prints_what_it_wrote_and_the_check_table(sheet_here, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: seen.update(path=path, **kw) or [_delivered()])
    assert cli.main(["deliver", sheet_here, "-o", "renders"]) == cli.EXIT_OK
    assert seen["path"] == sheet_here and seen["out_dir"] == "renders"
    out = capsys.readouterr().out
    assert "wrote SONG_story.mp4 (384 frames, gain -2.50 dB on a -8.8 LUFS master, after 3 encodes)" in out
    assert "384/384" in out and "-2.2" in out and "!peak" not in out


def test_deliver_says_what_the_masters_gain_and_limiter_were(sheet_here, monkeypatch, capsys):
    measured = _delivered(gain_db=-5.19, limiter_dbfs=-2.0, attempts=[], mode="loudness", ceiling_dbtp=-1.0)
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: [measured])
    assert cli.main(["deliver", sheet_here]) == cli.EXIT_OK
    assert "(384 frames, gain -5.19 dB, limiter -2.00 dBFS on a -8.8 LUFS master)" in capsys.readouterr().out


def test_deliver_says_which_cut_is_silent(sheet_here, monkeypatch, capsys):
    canvas = _delivered(out="SONG_canvas.mp4", has_audio=False, mode="none", attempts=[], lufs=None, true_peak=None)
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: [canvas])
    assert cli.main(["deliver", sheet_here]) == cli.EXIT_OK
    assert "wrote SONG_canvas.mp4 (384 frames, no audio)" in capsys.readouterr().out


def test_deliver_fails_loudly_when_the_true_peak_guard_ran_out_of_steps(sheet_here, monkeypatch, capsys):
    failed = _delivered(true_peak=-0.4, guard_failed=True)
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: [failed])
    assert cli.main(["deliver", sheet_here]) == cli.EXIT_ERROR
    captured = capsys.readouterr()
    assert "!peak" in captured.out  # the table still shows what was written
    assert "ran out of steps for SONG_story.mp4 (-0.4 dBTP at -2.50 dB)" in captured.err
    assert "over the -2 dBTP ceiling" in captured.err and "gain.start_db" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("mode", "fix"),
    [("fixed", "at the fixed gain. The files are written; lower gain.db, or use mode: auto"),
     ("loudness", "raise gain.max_steps or lower gain.limiter_dbfs")],
)
def test_a_file_over_the_ceiling_names_the_fix_for_its_mode(sheet_here, monkeypatch, capsys, mode, fix):
    over = _delivered(true_peak=-0.4, guard_failed=True, mode=mode, attempts=[])
    monkeypatch.setattr(cli, "deliver", lambda path, **kw: [over])
    assert cli.main(["deliver", sheet_here]) == cli.EXIT_ERROR
    assert fix in capsys.readouterr().err


def test_bad_usage_exits_2_as_the_module_docstring_says():
    """argparse exits 2 on a usage error before any command runs; the
    docstring used to promise 1."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["deliver"])  # the sheet is missing
    assert exc.value.code == 2 == cli.EXIT_ERROR
    assert "bad usage (argparse's own exit code)" in " ".join(cli.__doc__.split())


def test_an_invalid_sheet_says_sheet_not_brief(tmp_path, capsys):
    bad = tmp_path / "deliver.yaml"
    bad.write_text("silent: s.mp4\naudio: a.wav\ncuts:\n  - {out: ../escape.mp4, t0: 0, dur: 5}\n")
    assert cli.main(["deliver", str(bad), "--dry-run"]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "is not a valid delivery sheet" in err and "valid brief" not in err
    assert "inside the output directory" in err
