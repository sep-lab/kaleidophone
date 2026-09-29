"""render/_ffmpeg_util.py: the subprocess wrappers, with subprocess stubbed.

The distinction under test is which helpers are allowed to fail: the render
path calls require_ffmpeg() and must hard-fail with an actionable message,
while the diagnostics (probe_duration, first_frame_png) degrade to None so a
missing ffprobe or one unreadable clip can't abort a scan of a whole folder.

And two promises the module makes about every subprocess in the package:
each one lives here (checked on the package's source), and none of them
reads the caller's stdin unless it is feeding ffmpeg itself -- checked with a
stand-in "ffmpeg" (a two-line sh script) that tries to read a line.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import kaleidophone
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

    def fake(cmd, **kwargs):
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


def test_run_measure_keeps_the_info_log_and_returns_it(monkeypatch):
    seen = {}

    def fake(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Proc(stderr="[Parsed_ebur128_0 @ 0x1] Summary:\n")

    monkeypatch.setattr(subprocess, "run", fake)
    log = fu.run_measure("/fake/ffmpeg", ["-i", "a.mp4", "-af", "ebur128=peak=true", "-f", "null", "-"])
    assert "Summary:" in log
    assert "-nostats" in seen["cmd"] and "-loglevel" not in seen["cmd"]


def test_run_measure_raises_with_the_tail_of_the_log(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, "", "No such filter: 'ebur129'"))
    with pytest.raises(RuntimeError, match="ebur129"):
        fu.run_measure("/fake/ffmpeg", ["-i", "a.mp4"])


# --- nobody reads the terminal ---------------------------------------------


@pytest.fixture
def recorded(monkeypatch, tmp_path):
    """subprocess.run stubbed to record every call's argv and keywords."""
    calls = []

    def fake(cmd, **kwargs):
        calls.append((cmd, kwargs))
        text = kwargs.get("text")
        return _Proc(stdout="1.0\n" if text else b"\x89PNG", stderr="" if text else b"")

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(fu.shutil, "which", lambda name: f"/usr/bin/{name}")
    fu.filter_options.cache_clear()
    (tmp_path / "a.wav").write_bytes(b"placeholder")
    return calls, str(tmp_path / "a.wav")


HELPERS = {
    "run": lambda path: fu.run("/usr/bin/ffmpeg", ["-i", path, "out.mp4"]),
    "run_measure": lambda path: fu.run_measure("/usr/bin/ffmpeg", ["-i", path, "-f", "null", "-"]),
    "decode_f32le": lambda path: fu.decode_f32le(path, sample_rate=48000, channels=2),
    "first_frame_png": lambda path: fu.first_frame_png(path),
    "probe_duration": lambda path: fu.probe_duration(path),
    "probe_stream": lambda path: fu.probe_stream(path, "a:0", "channels"),
    "probe_keyframes": lambda path: fu.probe_keyframes(path),
    "filter_options": lambda path: fu.filter_options("/usr/bin/ffmpeg", "alimiter"),
}


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_no_helper_lets_ffmpeg_read_the_callers_stdin(recorded, helper):
    """`printf 'first\\nsecond\\n' | while read x; do kaleidophone deliver ...; done`
    got "econd" on its second turn: ffmpeg had read the loop's stdin."""
    calls, path = recorded
    HELPERS[helper](path)
    ((cmd, kwargs),) = calls
    assert kwargs.get("stdin") is subprocess.DEVNULL
    if os.path.basename(cmd[0]) == "ffmpeg":
        assert "-nostdin" in cmd  # and ffmpeg is told not to look, too


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh for the stand-in ffmpeg")
@pytest.mark.parametrize("helper", ["run", "run_measure", "decode_f32le", "probe_duration"])
def test_a_shell_loop_around_a_helper_keeps_all_of_its_input(tmp_path, helper):
    """The regression itself, with a real process: a stand-in ffmpeg (and
    ffprobe) that reads a line of stdin if it can. The Python process's stdin
    holds two lines; after the helper ran, both must still be there."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        (bin_dir / name).write_text("#!/bin/sh\nread line || true\necho 1\n")
        (bin_dir / name).chmod(0o755)
    (tmp_path / "a.wav").write_bytes(b"placeholder")
    code = textwrap.dedent(
        f"""
        import sys
        from kaleidophone.render import _ffmpeg_util as fu
        path, ffmpeg = {str(tmp_path / "a.wav")!r}, {str(bin_dir / "ffmpeg")!r}
        calls = {{
            "run": lambda: fu.run(ffmpeg, ["-i", path, "out.mp4"]),
            "run_measure": lambda: fu.run_measure(ffmpeg, ["-i", path, "-f", "null", "-"]),
            "decode_f32le": lambda: fu.decode_f32le(path, sample_rate=48000, channels=2),
            "probe_duration": lambda: fu.probe_duration(path),
        }}
        calls[{helper!r}]()
        sys.stdout.write(sys.stdin.read())
        """
    )
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    proc = subprocess.run(
        [sys.executable, "-c", code], input="first\nsecond\n", capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "first\nsecond\n"


# --- spawn -----------------------------------------------------------------


def test_spawn_gives_ffmpeg_devnull_unless_the_caller_pipes(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append((argv, kw)) or "proc")
    assert fu.spawn(["/usr/bin/ffmpeg", "-i", "a.mp4", "-"], read_stdout=True) == "proc"
    fu.spawn(["/usr/bin/ffmpeg", "-i", "-", "b.mp4"], feed_stdin=True, stderr="log")
    fu.spawn(["/usr/bin/ffmpeg", "-version"])
    (_, decoder), (_, encoder), (_, quiet) = seen
    assert (decoder["stdin"], decoder["stdout"], decoder["stderr"]) == (
        subprocess.DEVNULL, subprocess.PIPE, subprocess.DEVNULL
    )
    assert (encoder["stdin"], encoder["stdout"], encoder["stderr"]) == (subprocess.PIPE, subprocess.DEVNULL, "log")
    assert quiet["stdin"] is subprocess.DEVNULL and quiet["stdout"] is subprocess.DEVNULL


def test_spawn_refuses_a_shell_string():
    with pytest.raises(TypeError, match="never a shell string"):
        fu.spawn("ffmpeg -i a.mp4 -f null -")


def test_nothing_else_in_the_package_starts_a_process():
    """The module docstring's promise, checked on the source of every module:
    subprocess (or os.system, os.popen, os.exec*/spawn*, pty, asyncio's
    subprocesses) appears in _ffmpeg_util.py and nowhere else."""
    root = Path(kaleidophone.__file__).parent
    allowed = root / "render" / "_ffmpeg_util.py"
    process_modules = {"subprocess", "pty", "pexpect"}
    os_calls = {"system", "popen", "posix_spawn", "posix_spawnp", "fork", "forkpty"}
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        where = path.relative_to(root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{where}: import {a.name}" for a in node.names if a.name.split(".")[0] in process_modules]
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in process_modules:
                    offenders.append(f"{where}: from {node.module} import ...")
                if module == "os":
                    names = [a.name for a in node.names]
                    offenders += [f"{where}: from os import {n}" for n in names if n in os_calls or n.startswith(("exec", "spawn"))]
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                owner, name = node.value.id, node.attr
                if owner == "os" and (name in os_calls or name.startswith(("exec", "spawn"))):
                    offenders.append(f"{where}:{node.lineno}: os.{name}")
                if name.startswith("create_subprocess"):
                    offenders.append(f"{where}:{node.lineno}: {owner}.{name}")
    assert offenders == []


# --- filter_options ----------------------------------------------------------

ALIMITER_61 = """\
Filter alimiter
  Audio lookahead limiter.
    Inputs:
       #0: main (audio)
    Outputs:
       #0: default (audio)
alimiter AVOptions:
   level_in          <double>     ..F.A....T. set input level (from 0.015625 to 64) (default 1)
   limit             <double>     ..F.A....T. set limit (from 0.0625 to 1) (default 1)
   release           <double>     ..F.A....T. set release (from 1 to 8000) (default 50)
   latency           <boolean>    ..F.A....T. compensate delay (default false)

This filter has support for timeline through the 'enable' option.
"""


def test_filter_options_reads_the_help_once_per_binary(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _Proc(stdout=ALIMITER_61))
    fu.filter_options.cache_clear()
    assert fu.filter_options("/usr/bin/ffmpeg", "alimiter") == {"level_in", "limit", "release", "latency"}
    fu.filter_options("/usr/bin/ffmpeg", "alimiter")
    assert calls == [["/usr/bin/ffmpeg", "-hide_banner", "-nostdin", "-h", "filter=alimiter"]]
    fu.filter_options.cache_clear()


@pytest.mark.parametrize("failure", [_Proc(returncode=1, stdout=""), OSError("no such file")])
def test_filter_options_is_empty_when_it_cant_ask(monkeypatch, failure):
    def fake(cmd, **kw):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(subprocess, "run", fake)
    fu.filter_options.cache_clear()
    assert fu.filter_options("/nope/ffmpeg", "alimiter") == frozenset()
    fu.filter_options.cache_clear()


# --- concat_quote and BITRATE_RE ---------------------------------------------


def test_concat_quote_leaves_an_ordinary_path_alone():
    assert fu.concat_quote("/media/plain.mp4") == "'/media/plain.mp4'"


def test_concat_quote_escapes_every_apostrophe():
    assert fu.concat_quote("/a'b'c") == "'/a'\\''b'\\''c'"


@pytest.mark.parametrize(("value", "ok"), [("256k", True), ("4500k", True), ("9M", True), ("1.5M", True),
                                           ("192", True), ("loud", False), ("256 k", False), ("-1k", False)])
def test_bitrate_re_takes_a_number_with_an_optional_suffix(value, ok):
    assert bool(fu.BITRATE_RE.match(value)) is ok


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


# --- probe_keyframes, probe_stream -------------------------------------------


def test_probe_keyframes_reads_packet_flags(monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffprobe")
    listing = "0.000000,K__\n0.041667,___\n26.250000,K__\nN/A,K__\n13.000000,K_\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(stdout=listing))
    assert fu.probe_keyframes("silent.mp4") == [0.0, 13.0, 26.25]


@pytest.mark.parametrize(("which", "proc"), [(None, _Proc()), ("/usr/bin/ffprobe", _Proc(1))])
def test_probe_keyframes_degrades_to_none(monkeypatch, which, proc):
    monkeypatch.setattr(fu.shutil, "which", lambda name: which)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    assert fu.probe_keyframes("silent.mp4") is None


def test_probe_stream_can_count_packets(monkeypatch):
    seen = {}
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffprobe")

    def fake(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Proc(stdout="1734\n")

    monkeypatch.setattr(subprocess, "run", fake)
    assert fu.probe_stream("reel.mp4", "v:0", "nb_read_packets", count_packets=True) == "1734"
    assert "-count_packets" in seen["cmd"]


# --- decode_f32le ------------------------------------------------------------


def test_decode_f32le_can_decode_a_window(monkeypatch, tmp_path):
    seen = {}
    (tmp_path / "a.wav").write_bytes(b"placeholder")
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd) or _Proc(stdout=b"\0" * 8))
    fu.decode_f32le(str(tmp_path / "a.wav"), sample_rate=48000, channels=2, start=42.24, duration=0.01)
    cmd = seen["cmd"]
    # An input seek (before -i): sample-exact for PCM, and no decode of what comes before.
    assert cmd[cmd.index("-ss") + 1] == "42.240000" and cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-t") + 1] == "0.010000" and cmd.index("-t") < cmd.index("-i")
    fu.decode_f32le(str(tmp_path / "a.wav"), sample_rate=48000, channels=2)
    assert "-ss" not in seen["cmd"] and "-t" not in seen["cmd"]


def test_decode_f32le_raises_with_ffmpegs_own_words(monkeypatch, tmp_path):
    (tmp_path / "a.wav").write_bytes(b"placeholder")
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, b"", b"Invalid data found"))
    with pytest.raises(RuntimeError, match="Invalid data found"):
        fu.decode_f32le(str(tmp_path / "a.wav"), sample_rate=48000, channels=1)


def test_decode_f32le_reports_a_missing_file_before_looking_for_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(fu.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        fu.decode_f32le(str(tmp_path / "missing.wav"), sample_rate=48000, channels=1)


@pytest.mark.parametrize(
    ("which", "proc"),
    [(None, _Proc(stdout="2")), ("/usr/bin/ffprobe", _Proc(1, "")), ("/usr/bin/ffprobe", _Proc(0, ""))],
)
def test_probe_stream_degrades_to_none(monkeypatch, which, proc):
    monkeypatch.setattr(fu.shutil, "which", lambda name: which)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: proc)
    assert fu.probe_stream("song.wav", "a:0", "channels") is None


# --- first_frame_png -----------------------------------------------------


def test_first_frame_png_returns_the_encoded_bytes(monkeypatch):
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(stdout=b"\x89PNG\r\n"))
    assert fu.first_frame_png("clip.mp4") == b"\x89PNG\r\n"


def test_first_frame_png_asks_for_exactly_one_frame_on_a_pipe(monkeypatch):
    seen = {}
    monkeypatch.setattr(fu.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    def fake(cmd, **kwargs):
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
