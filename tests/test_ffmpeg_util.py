"""render/_ffmpeg_util.py: the subprocess wrappers, with subprocess stubbed.

The distinction under test is which helpers are allowed to fail: the render
path calls require_ffmpeg() and must hard-fail with an actionable message,
while the diagnostics (probe_duration, first_frame_png) degrade to None so a
missing ffprobe or one unreadable clip can't abort a scan of a whole folder.
"""

from __future__ import annotations

import subprocess

import pytest

from kaleidophone.render import _ffmpeg_util as fu


class _Proc:
    def __init__(self, returncode=0, stdout=b"", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- require_ffmpeg ------------------------------------------------------


def test_require_ffmpeg_returns_the_resolved_binary(monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/local/bin/ffmpeg")
    assert fu.require_ffmpeg() == "/usr/local/bin/ffmpeg"


def test_require_ffmpeg_explains_how_to_install_it(monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: None)
    with pytest.raises(fu.FfmpegNotFound, match="brew install ffmpeg"):
        fu.require_ffmpeg()


# --- run -----------------------------------------------------------------


def test_run_passes_args_through_as_a_list_never_a_shell_string(monkeypatch):
    """SECURITY.md is explicit that nothing may reach subprocess as a shell
    string. Pin the argv form directly."""
    seen = {}

    def fake(cmd, capture_output, text):
        seen["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(subprocess, "run", fake)
    fu.run("/fake/ffmpeg", ["-i", "in.mp4", "out.mp4"])

    assert isinstance(seen["cmd"], list)
    assert seen["cmd"][0] == "/fake/ffmpeg"
    assert seen["cmd"][-3:] == ["-i", "in.mp4", "out.mp4"]


def test_run_raises_with_the_tail_of_stderr_on_failure(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(returncode=1, stderr="boom: bad filter"))
    with pytest.raises(RuntimeError, match="boom: bad filter"):
        fu.run("/fake/ffmpeg", ["-i", "in.mp4", "out.mp4"])


# --- probe_duration ------------------------------------------------------


def test_probe_duration_parses_seconds(monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(stdout="123.456\n"))
    assert fu.probe_duration("x.mp4") == pytest.approx(123.456)


@pytest.mark.parametrize(
    ("which", "proc"),
    [
        (None, _Proc(stdout="1.0")),          # ffprobe not installed
        ("/usr/bin/ffprobe", _Proc(1, "")),   # ffprobe failed
        ("/usr/bin/ffprobe", _Proc(0, "N/A")),  # unparseable
    ],
)
def test_probe_duration_degrades_to_none_rather_than_raising(monkeypatch, which, proc):
    monkeypatch.setattr(fu.shutil, "which", lambda name: which)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    assert fu.probe_duration("x.mp4") is None


# --- first_frame_png -----------------------------------------------------


def test_first_frame_png_returns_the_encoded_bytes(monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(stdout=b"\x89PNG\r\n"))
    assert fu.first_frame_png("clip.mp4") == b"\x89PNG\r\n"


def test_first_frame_png_asks_for_exactly_one_frame_on_a_pipe(monkeypatch):
    seen = {}
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    def fake(cmd, capture_output):
        seen["cmd"] = cmd
        return _Proc(stdout=b"png")

    monkeypatch.setattr(subprocess, "run", fake)
    fu.first_frame_png("clip.mp4")

    cmd = seen["cmd"]
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert "image2pipe" in cmd
    assert cmd[-1] == "-"


@pytest.mark.parametrize(
    ("which", "proc"),
    [
        (None, _Proc(stdout=b"png")),        # ffmpeg not installed
        ("/usr/bin/ffmpeg", _Proc(1, b"")),  # decode failed
        ("/usr/bin/ffmpeg", _Proc(0, b"")),  # produced nothing
    ],
)
def test_first_frame_png_degrades_to_none_for_an_unreadable_clip(monkeypatch, which, proc):
    monkeypatch.setattr(fu.shutil, "which", lambda name: which)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    assert fu.first_frame_png("clip.mp4") is None
