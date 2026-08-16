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
