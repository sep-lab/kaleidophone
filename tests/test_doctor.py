"""kaleidophone doctor: every check against a fake machine.

The doctor asks the machine everything through one Host object; FakeHost
answers instead, so the checks are tested on the three machines that matter
-- an M1 running the whole toolchain under Rosetta (this project's measured
state), the same M1 native, and a Linux CI runner -- whatever runs the tests.
File-level checks (the write test, '?' in names, a WAV's header, Chromium's
folder) use real files under tmp_path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from kaleidophone import cli, doctor

# --- binaries, as their headers begin -----------------------------------


def macho(cpu: int) -> bytes:
    return (0xFEEDFACF).to_bytes(4, "little") + cpu.to_bytes(4, "little") + bytes(24)


def fat(*cpus: int) -> bytes:
    head = (0xCAFEBABE).to_bytes(4, "big") + len(cpus).to_bytes(4, "big")
    for cpu in cpus:
        head += cpu.to_bytes(4, "big") + bytes(16)
    return head


def elf(machine: int) -> bytes:
    return b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8) + (2).to_bytes(2, "little") + machine.to_bytes(2, "little")


X86_64, ARM64 = 0x01000007, 0x0100000C


def i32(value: int) -> bytes:
    return value.to_bytes(4, "little")


class FakeHost(doctor.Host):
    def __init__(
        self,
        *,
        platform="darwin",
        machine="x86_64",
        translated=True,
        apple_silicon=True,
        tools=None,
        heads=None,
        versions=None,
        encoders=frozenset({"libx264", "aac", "aac_at", "h264_videotoolbox"}),
        load=0.4,
        power="ac",
        env=None,
        free=500e9,
        sizes=None,
        python_executable="/usr/local/Cellar/python@3.11/bin/python3.11",
        copies=None,
    ):
        super().__init__()
        self.platform = platform
        self.home = "/Users/someone"
        self._machine = machine
        self._sysctls = {}
        if platform == "darwin":
            self._sysctls = {
                "hw.optional.arm64": i32(1 if apple_silicon else 0),
                "sysctl.proc_translated": i32(1 if translated else 0),
                "hw.perflevel0.physicalcpu": i32(8),
                "hw.perflevel1.physicalcpu": i32(2),
                "hw.memsize": (16 * 2**30).to_bytes(8, "little"),
                "machdep.cpu.brand_string": b"Apple M1 Pro\0",
                "hw.model": b"MacBookPro18,3\0",
            }
        self._tools = tools if tools is not None else {
            "ffmpeg": "/usr/local/bin/ffmpeg", "ffprobe": "/usr/local/bin/ffprobe", "node": "/usr/local/bin/node",
        }
        self._heads = heads if heads is not None else {path: macho(X86_64) for path in self._tools.values()}
        self._versions = versions or {
            "ffmpeg": "ffmpeg version 7.1 Copyright (c) 2000-2024 the FFmpeg developers\n",
            "ffprobe": "ffprobe version 7.1 Copyright (c) 2007-2024 the FFmpeg developers\n",
            "node": "v24.19.0\n",
        }
        self._encoders = encoders
        self._load = load
        self._power = power
        self._env = env if env is not None else {"PATH": "/usr/local/bin:/usr/bin:/bin"}
        self._free = free
        self._sizes = list(sizes) if sizes is not None else None
        self._python_executable = python_executable
        self._copies = copies or {}
        self.slept = []
        self.calls = []

    def environ(self):
        return self._env

    def which(self, name):
        return self._tools.get(name)

    def which_all(self, name):
        return self._copies.get(name, [self._tools[name]] if name in self._tools else [])

    def realpath(self, path):
        return path

    def read_head(self, path, size=4096):
        if path in self._heads:
            return self._heads[path]
        return super().read_head(path, size)

    def sysctl(self, name):
        return self._sysctls.get(name)

    def capture(self, argv):
        self.calls.append(argv)
        name = os.path.basename(argv[0])
        return (0, self._versions[name], "") if name in self._versions else None

    def encoders(self, ffmpeg):
        return self._encoders

    def loadavg(self):
        return self._load

    def disk_free(self, path):
        return self._free

    def cpu_count(self):
        return 10

    def memory_bytes(self):
        return 16 * 2**30

    def machine(self):
        return self._machine

    def python(self):
        return {"version": "3.11.10", "machine": self._machine, "executable": self._python_executable, "venv": True}

    def os_name(self):
        return "macOS 15.7" if self.platform == "darwin" else "Ubuntu 24.04 LTS"

    def cpu_model(self):
        return "Apple M1 Pro" if self.platform == "darwin" else "AMD EPYC"

    def power(self):
        return self._power

    def size(self, path):
        if self._sizes is not None:
            return self._sizes.pop(0) if len(self._sizes) > 1 else self._sizes[0]
        return super().size(path)

    def sleep(self, seconds):
        self.slept.append(seconds)


def native_host(**kw) -> FakeHost:
    tools = {"ffmpeg": "/opt/homebrew/bin/ffmpeg", "ffprobe": "/opt/homebrew/bin/ffprobe", "node": "/opt/homebrew/bin/node"}
    defaults = {
        "machine": "arm64",
        "translated": False,
        "tools": tools,
        "heads": {path: macho(ARM64) for path in tools.values()},
        "env": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
        "python_executable": "/opt/homebrew/Cellar/python@3.11/bin/python3.11",
    }
    return FakeHost(**{**defaults, **kw})


def run(host, tmp_path, **kw) -> doctor.Report:
    kw.setdefault("find", lambda given: None)
    return doctor.diagnose(host, out=str(tmp_path), **kw)


def by_id(report: doctor.Report) -> dict[str, doctor.Check]:
    return {c.id: c for c in report.checks}


# --- the three machines --------------------------------------------------


def test_an_m1_under_rosetta_says_every_tool_is_translated(tmp_path):
    report = run(FakeHost(), tmp_path)
    checks = by_id(report)
    assert checks["host"].summary.startswith("Apple M1 Pro, arm64, 8P+2E cores, 16 GB")
    for name in ("python", "ffmpeg", "ffprobe", "node"):
        assert checks[name].status == "warn", name
        assert "x86_64 translated by Rosetta 2" in checks[name].summary
        assert "/opt/homebrew" in checks[name].fix
    assert "(/usr/local" in checks["ffmpeg"].summary and checks["ffmpeg"].summary.startswith("7.1")
    assert checks["path"].status == "info" and "no native Homebrew" in checks["path"].summary
    tc = report.toolchain
    assert tc["host"]["arch"] == "arm64"
    assert tc["python"] == {"version": "3.11.10", "arch": "x86_64", "translated": True, "where": "/usr/local", "venv": True}
    assert tc["ffmpeg"]["translated"] and tc["ffmpeg"]["binary_arches"] == ["x86_64"]
    assert tc["ffmpeg"]["encoders"]["aac_at"] is True
    assert report.status == "warn" and report.exit_code == 0


def test_the_same_m1_native_is_all_ok(tmp_path):
    report = run(native_host(), tmp_path)
    checks = by_id(report)
    for name in ("python", "ffmpeg", "ffprobe", "node", "path", "encoders"):
        assert checks[name].status == "ok", (name, checks[name].summary)
    assert checks["ffmpeg"].summary == "7.1, arm64 (/opt/homebrew)"
    assert report.toolchain["node"]["translated"] is False
    assert report.exit_code == 0


def test_a_linux_runner(tmp_path):
    tools = {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe", "node": "/usr/bin/node"}
    host = FakeHost(platform="linux", tools=tools, heads={p: elf(0x3E) for p in tools.values()}, power=None,
                    python_executable="/usr/bin/python3")
    report = run(host, tmp_path)
    checks = by_id(report)
    assert checks["host"].summary == "AMD EPYC, x86_64, 10 cores, 16 GB, Ubuntu 24.04 LTS"
    assert checks["ffmpeg"].status == "ok" and checks["ffmpeg"].summary == "7.1, x86_64 (/usr)"
    assert checks["path"].status == "skip"
    assert checks["power"].status == "info"
    assert report.exit_code == 0


def test_a_universal_binary_runs_as_the_hosts_own_slice(tmp_path):
    host = native_host(heads={p: fat(X86_64, ARM64) for p in ("/opt/homebrew/bin/ffmpeg", "/opt/homebrew/bin/ffprobe",
                                                              "/opt/homebrew/bin/node")})
    checks = by_id(run(host, tmp_path))
    assert checks["ffmpeg"].summary == "7.1, arm64 (universal) (/opt/homebrew)"


def test_a_shim_has_no_architecture_to_report(tmp_path):
    host = native_host(heads={"/opt/homebrew/bin/node": b"#!/bin/sh\nexec node \"$@\"\n"})
    checks = by_id(run(host, tmp_path))
    assert "architecture unknown" in checks["node"].summary


# --- PATH ------------------------------------------------------------------


def test_usr_local_ahead_of_opt_homebrew_is_a_warning_naming_what_it_shadows(tmp_path):
    host = native_host(
        env={"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin"},
        copies={"ffmpeg": ["/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"], "node": ["/opt/homebrew/bin/node"]},
    )
    path = by_id(run(host, tmp_path))["path"]
    assert path.status == "warn"
    assert "ffmpeg resolve to /usr/local" in path.summary and "node" not in path.summary
    assert path.data["copies"]["ffmpeg"] == ["/usr/local", "/opt/homebrew"]
    assert path.data["usr_local_bin"] == 0 and path.data["opt_homebrew_bin"] == 1


def test_an_intel_mac_has_no_opt_homebrew_to_miss(tmp_path):
    host = FakeHost(machine="x86_64", translated=False, apple_silicon=False)
    checks = by_id(run(host, tmp_path))
    assert checks["path"].status == "ok"
    assert checks["ffmpeg"].status == "ok" and "translated" not in checks["ffmpeg"].summary


def test_path_order_reads_both_prefixes():
    assert doctor.path_order("/opt/homebrew/bin:/usr/local/bin/") == {"usr_local_bin": 1, "opt_homebrew_bin": 0}
    assert doctor.path_order("/usr/bin") == {"usr_local_bin": None, "opt_homebrew_bin": None}


# --- missing and broken tools ---------------------------------------------


def test_no_ffmpeg_fails_and_the_encoders_are_not_asked(tmp_path):
    host = FakeHost(tools={"node": "/usr/local/bin/node"})
    report = run(host, tmp_path)
    checks = by_id(report)
    assert checks["ffmpeg"].status == "fail" and checks["ffprobe"].status == "warn"
    assert checks["encoders"].status == "skip"
    assert report.exit_code == doctor.EXIT_FAILED


def test_an_ffmpeg_without_libx264_fails(tmp_path):
    checks = by_id(run(FakeHost(encoders=frozenset({"aac"})), tmp_path))
    assert checks["encoders"].status == "fail" and checks["encoders"].summary.startswith("libx264 missing")


def test_an_ffmpeg_that_lists_no_encoders_fails(tmp_path):
    assert by_id(run(FakeHost(encoders=frozenset()), tmp_path))["encoders"].status == "fail"


def test_no_aac_at_is_said_but_not_a_warning(tmp_path):
    check = by_id(run(FakeHost(encoders=frozenset({"libx264", "aac"})), tmp_path))["encoders"]
    assert check.status == "ok" and "no aac_at" in check.summary


def test_node_missing_or_old_is_a_warning(tmp_path):
    missing = by_id(run(FakeHost(tools={"ffmpeg": "/usr/local/bin/ffmpeg"}), tmp_path))["node"]
    assert missing.status == "warn" and "not on PATH" in missing.summary
    old = native_host(versions={"ffmpeg": "ffmpeg version 7.1", "ffprobe": "ffprobe version 7.1", "node": "v18.20.1"})
    check = by_id(run(old, tmp_path))["node"]
    assert check.status == "warn" and "needs 20+" in check.summary


def test_ffprobe_is_not_given_nostdin_which_it_doesnt_take(tmp_path):
    host = FakeHost()
    run(host, tmp_path)
    by_tool = {os.path.basename(argv[0]): argv for argv in host.calls}
    assert "-nostdin" in by_tool["ffmpeg"] and "-nostdin" not in by_tool["ffprobe"]


# --- the bench gate --------------------------------------------------------


@pytest.mark.parametrize(
    ("load", "power", "passed", "reason"),
    [
        (0.4, "ac", True, None),
        (1.0, "ac", True, None),
        (0.4, None, True, None),
        (1.6, "ac", False, "1-min load 1.60 is over 1"),
        (0.4, "battery", False, "on battery power"),
        (0.4, "ups", False, "on ups power"),
        (None, "ac", False, "can't be read"),
    ],
)
def test_the_bench_gate(tmp_path, load, power, passed, reason):
    report = run(native_host(load=load, power=power), tmp_path, gate=True)
    assert report.gate.passed is passed
    assert report.exit_code == (0 if passed else doctor.EXIT_GATE_REFUSED)
    if reason:
        assert any(reason in r for r in report.gate.reasons)


def test_the_gate_refuses_a_machine_with_a_failing_check(tmp_path):
    report = run(native_host(tools={}), tmp_path, gate=True)
    assert not report.gate.passed and any("failing checks: ffmpeg" in r for r in report.gate.reasons)
    assert report.exit_code == doctor.EXIT_GATE_REFUSED


def test_the_load_is_read_before_the_checks_start_processes(tmp_path):
    order = []

    class Watching(FakeHost):
        def loadavg(self):
            order.append("load")
            return 0.2

        def capture(self, argv):
            order.append("process")
            return super().capture(argv)

    run(Watching(), tmp_path, gate=True)
    assert order[0] == "load"


def test_load_and_power_checks():
    assert doctor._load_check(3.2, 10).status == "warn"
    assert doctor._load_check(None, 10).status == "info"
    assert doctor._power_check("battery").status == "warn"
    assert doctor._power_check(None).status == "info"


# --- the output folder -----------------------------------------------------


def test_the_output_folder_is_written_to_and_left_clean(tmp_path):
    checks = by_id(run(native_host(), tmp_path))
    assert checks["write"].status == "ok" and checks["filenames"].status == "ok"
    assert checks["disk"].status == "ok"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(("free", "status"), [(3e9, "fail"), (12e9, "warn"), (None, "warn")])
def test_low_disk(tmp_path, free, status):
    assert by_id(run(native_host(free=free), tmp_path))["disk"].status == status


def test_a_missing_output_folder_fails(tmp_path):
    report = doctor.diagnose(native_host(), out=str(tmp_path / "nope"), find=lambda given: None)
    assert by_id(report)["disk"].status == "fail" and report.exit_code == doctor.EXIT_FAILED


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs a folder its owner can't write")
def test_a_folder_that_refuses_writes_fails_the_write_test(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        assert doctor._write_check(str(locked)).status == "fail"
        assert doctor._question_mark_check(str(locked)).status == "warn"
    finally:
        locked.chmod(0o700)


def test_a_disk_that_renames_a_question_mark_is_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.os, "listdir", lambda path: ["renamed.tmp"])
    check = doctor._question_mark_check(str(tmp_path))
    assert check.status == "warn" and "renames" in check.summary


# --- a master that's still being written ----------------------------------


def wav_header(data_bytes: int, riff: int | None = None) -> bytes:
    riff = 36 + data_bytes if riff is None else riff
    fmt = (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (2).to_bytes(2, "little")
    fmt += (48000).to_bytes(4, "little") + (192000).to_bytes(4, "little") + (4).to_bytes(2, "little")
    fmt += (16).to_bytes(2, "little")
    return b"RIFF" + riff.to_bytes(4, "little") + b"WAVE" + b"fmt " + fmt + b"data" + data_bytes.to_bytes(4, "little")


def write_wav(path: Path, data_bytes: int, riff: int | None = None) -> Path:
    path.write_bytes(wav_header(data_bytes, riff) + bytes(data_bytes))
    return path


def test_a_finished_wav_is_ok_and_named_only_by_number(tmp_path):
    wav = write_wav(tmp_path / "Unreleased Song Title (final).wav", 4000)
    host = native_host()
    report = run(host, tmp_path, wavs=[str(wav)], wav_wait=1.5)
    check = by_id(report)["wav #1"]
    assert check.status == "ok" and "matches its wav header" in check.summary
    assert host.slept == [1.5]
    assert "Unreleased" not in json.dumps(report.to_dict()) and "Unreleased" not in doctor.format_report(report)


def test_a_wav_that_is_still_growing_fails(tmp_path):
    wav = write_wav(tmp_path / "m.wav", 4000)
    check = doctor._wav_check(native_host(sizes=[1000, 5000]), 1, str(wav), 2.0)
    assert check.status == "fail" and "still being written: +4000 bytes in 2 s" in check.summary


def test_a_truncated_wav_fails(tmp_path):
    wav = tmp_path / "m.wav"
    wav.write_bytes(wav_header(4000) + bytes(1000))
    check = doctor._wav_check(native_host(), 1, str(wav), 0)
    assert check.status == "fail" and "truncated" in check.summary


def test_a_wav_with_a_placeholder_header_is_a_warning(tmp_path):
    wav = write_wav(tmp_path / "m.wav", 4000, riff=0xFFFFFFFF)
    assert doctor._wav_check(native_host(), 1, str(wav), 0).status == "warn"


def test_trailing_bytes_past_the_header_are_a_warning(tmp_path):
    wav = tmp_path / "m.wav"
    wav.write_bytes(wav_header(4000) + bytes(4000) + b"junk")
    check = doctor._wav_check(native_host(), 1, str(wav), 0)
    assert check.status == "warn" and "4 bytes past" in check.summary


def test_wav_check_edge_cases(tmp_path):
    host = native_host()
    assert doctor._wav_check(host, 1, str(tmp_path / "missing.wav"), 0).status == "fail"
    (tmp_path / "empty.wav").write_bytes(b"")
    assert doctor._wav_check(host, 2, str(tmp_path / "empty.wav"), 0).status == "fail"
    (tmp_path / "notes.txt").write_bytes(b"not audio at all")
    assert "header not checked" in doctor._wav_check(host, 3, str(tmp_path / "notes.txt"), 0).summary
    gone = native_host(sizes=[100, None])
    assert "disappeared" in doctor._wav_check(gone, 4, str(tmp_path / "notes.txt"), 0).summary


def test_declared_size_reads_wav_rf64_and_aiff():
    assert doctor.declared_size(wav_header(100)) == ("wav", 144)
    assert doctor.declared_size(wav_header(100, riff=0)) == ("wav", None)
    ds64 = b"RF64" + (0xFFFFFFFF).to_bytes(4, "little") + b"WAVE" + b"ds64" + (28).to_bytes(4, "little")
    assert doctor.declared_size(ds64 + (5_000_000_000).to_bytes(8, "little")) == ("rf64", 5_000_000_008)
    assert doctor.declared_size(b"RF64" + bytes(4) + b"WAVE" + b"JUNK") == ("rf64", None)
    assert doctor.declared_size(b"FORM" + (1000).to_bytes(4, "big") + b"AIFF") == ("aiff", 1008)
    assert doctor.declared_size(b"OggS" + bytes(20)) is None
    assert doctor.declared_size(b"RIFF") is None


# --- Chromium and node_modules ---------------------------------------------


def make_canvas(tmp_path: Path, *, installed: bool = True, revision: str = "1194") -> Path:
    canvas = tmp_path / "canvas"
    canvas.mkdir()
    (canvas / "package.json").write_text('{"name": "kaleidophone-canvas"}')
    if installed:
        core = canvas / "node_modules" / "playwright-core"
        core.mkdir(parents=True)
        (core / "package.json").write_text('{"version": "1.56.1"}')
        browsers = [{"name": "chromium", "revision": revision}, {"name": "chromium-headless-shell", "revision": revision},
                    {"name": "firefox", "revision": "1495"}]
        (core / "browsers.json").write_text(json.dumps({"browsers": browsers}))
    return canvas


def make_cache(tmp_path: Path, revisions=("1194",), cpu=ARM64) -> Path:
    cache = tmp_path / "ms-playwright"
    for rev in revisions:
        app = cache / f"chromium_headless_shell-{rev}" / "chrome-headless-shell-mac-arm64"
        app.mkdir(parents=True)
        (app / "chrome-headless-shell").write_bytes(macho(cpu))
        (cache / f"chromium-{rev}").mkdir()
    return cache


def chromium(tmp_path, host, canvas):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    report = doctor.diagnose(host, out=str(out), canvas=str(canvas), find=doctor.find_canvas)
    return by_id(report), report.toolchain["chromium"]


def test_the_chromium_playwright_launches_is_found_with_its_arch(tmp_path):
    cache = make_cache(tmp_path)
    host = native_host(env={"PATH": "/opt/homebrew/bin", "PLAYWRIGHT_BROWSERS_PATH": str(cache)})
    checks, info = chromium(tmp_path, host, make_canvas(tmp_path))
    assert checks["node_modules"].status == "ok"
    assert checks["chromium"].status == "ok" and checks["chromium"].summary == "chromium-headless-shell 1194, arm64"
    assert info["revision"] == "1194" and info["expected"] == {"chromium": "1194", "chromium-headless-shell": "1194"}


def test_the_wrong_chromium_revision_is_a_warning_listing_what_is_there(tmp_path):
    cache = make_cache(tmp_path, revisions=("1228", "1243"))
    host = native_host(env={"PATH": "/opt/homebrew/bin", "PLAYWRIGHT_BROWSERS_PATH": str(cache)})
    checks, info = chromium(tmp_path, host, make_canvas(tmp_path))
    assert checks["chromium"].status == "warn"
    assert "chromium-headless-shell 1194, which isn't installed (installed: 1228, 1243)" in checks["chromium"].summary
    assert checks["chromium"].fix == "cd canvas && npx playwright-core install chromium"
    assert info["installed"]["chromium"] == ["1228", "1243"]


def test_a_translated_chromium_is_a_warning(tmp_path):
    cache = make_cache(tmp_path, cpu=X86_64)
    host = native_host(env={"PATH": "/opt/homebrew/bin", "PLAYWRIGHT_BROWSERS_PATH": str(cache)})
    checks, _ = chromium(tmp_path, host, make_canvas(tmp_path))
    assert checks["chromium"].status == "warn" and "translated" in checks["chromium"].summary


def test_node_modules_not_installed(tmp_path):
    checks, info = chromium(tmp_path, native_host(), make_canvas(tmp_path, installed=False))
    assert checks["node_modules"].status == "warn" and checks["node_modules"].fix == "cd canvas && npm ci"
    assert "chromium" not in checks and info == {"node_modules": False}


def test_kaleidophone_chromium_overrides_the_cache(tmp_path):
    binary = tmp_path / "chrome"
    binary.write_bytes(macho(ARM64))
    host = native_host(env={"PATH": "/opt/homebrew/bin", "KALEIDOPHONE_CHROMIUM": str(binary)})
    checks, info = chromium(tmp_path, host, make_canvas(tmp_path))
    assert checks["chromium"].status == "ok" and info["override"] == "KALEIDOPHONE_CHROMIUM" and info["arch"] == "arm64"
    other = tmp_path / "other"
    other.mkdir()
    host = native_host(env={"PATH": "/opt/homebrew/bin", "KALEIDOPHONE_CHROMIUM": str(tmp_path / "gone")})
    checks, _ = chromium(other, host, make_canvas(other))
    assert checks["chromium"].status == "fail"


def test_no_checkout_skips_chromium(tmp_path):
    assert by_id(run(native_host(), tmp_path))["chromium"].status == "skip"


def test_find_canvas(tmp_path):
    canvas = make_canvas(tmp_path, installed=False)
    assert doctor.find_canvas(str(canvas)) == canvas
    assert doctor.find_canvas(str(tmp_path)) is None
    nested = canvas / "pieces" / "x"
    nested.mkdir(parents=True)
    # From inside a checkout, that checkout's canvas/ -- before the one an editable install points at.
    assert doctor.find_canvas(None, cwd=str(nested)) == canvas
    assert doctor.find_canvas(None, cwd=str(canvas)) == canvas
    assert doctor.find_canvas(None, cwd=str(tmp_path)) == canvas


def test_playwright_cache_follows_playwrights_rules():
    mac = native_host(env={})
    assert doctor.playwright_cache(mac) == Path("/Users/someone/Library/Caches/ms-playwright")
    linux = FakeHost(platform="linux", env={"XDG_CACHE_HOME": "/tmp/xdg"})
    assert doctor.playwright_cache(linux) == Path("/tmp/xdg/ms-playwright")
    assert doctor.playwright_cache(FakeHost(platform="linux", env={})) == Path("/Users/someone/.cache/ms-playwright")
    win = FakeHost(platform="win32", env={"LOCALAPPDATA": "C:\\Users\\someone\\AppData\\Local"})
    assert doctor.playwright_cache(win).name == "ms-playwright"
    assert doctor.playwright_cache(FakeHost(platform="win32", env={})) is None
    assert doctor.playwright_cache(native_host(env={"PLAYWRIGHT_BROWSERS_PATH": "/b"})) == Path("/b")


# --- readers ---------------------------------------------------------------


def test_binary_arches():
    assert doctor.binary_arches(macho(X86_64)) == ["x86_64"]
    assert doctor.binary_arches(macho(ARM64)) == ["arm64"]
    assert doctor.binary_arches(fat(X86_64, ARM64)) == ["x86_64", "arm64"]
    assert doctor.binary_arches(elf(0x3E)) == ["x86_64"] and doctor.binary_arches(elf(0xB7)) == ["arm64"]
    big_endian = (0xFEEDFACE).to_bytes(4, "big") + (18).to_bytes(4, "big")
    assert doctor.binary_arches(big_endian) == ["ppc"]
    java = (0xCAFEBABE).to_bytes(4, "big") + (52).to_bytes(4, "big")
    assert doctor.binary_arches(java) is None
    assert doctor.binary_arches(b"#!/bin/sh\n") is None and doctor.binary_arches(None) is None
    assert doctor.binary_arches(macho(999)) == ["unknown"]
    assert doctor.binary_arches(fat(X86_64)[:8] + bytes(2)) is None  # a slice table cut short


def test_runs_as():
    assert doctor.runs_as(["x86_64"], "arm64") == ("x86_64", True)
    assert doctor.runs_as(["x86_64", "arm64"], "arm64") == ("arm64", False)
    assert doctor.runs_as(["arm64"], "x86_64") == ("arm64", False)
    assert doctor.runs_as(None, "arm64") == (None, False)


def test_where_names_a_prefix_never_a_path():
    assert doctor.where("/opt/homebrew/Cellar/ffmpeg/7.1/bin/ffmpeg") == "/opt/homebrew"
    assert doctor.where("/usr/local/Cellar/node/24/bin/node") == "/usr/local"
    assert doctor.where("/usr/bin/python3") == "/usr"
    assert doctor.where("/Users/someone/.pyenv/versions/3.11/bin/python", "/Users/someone") == "home folder"
    assert doctor.where("/srv/tools/ffmpeg", "/Users/someone") == "elsewhere"
    assert doctor.where(None) is None


@pytest.mark.parametrize(
    ("text", "source"),
    [
        ("Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged", "ac"),
        ("Now drawing from 'Battery Power'\n -InternalBattery-0\t80%; discharging", "battery"),
        ("Now drawing from 'UPS Power'", "ups"),
        ("Now drawing from 'Something Else'", None),
        ("", None),
    ],
)
def test_parse_pmset(text, source):
    assert doctor.parse_pmset(text) == source


def test_linux_power(tmp_path):
    def supply(name, kind, **files):
        folder = tmp_path / name
        folder.mkdir(parents=True)
        (folder / "type").write_text(kind + "\n")
        for key, value in files.items():
            (folder / key).write_text(value + "\n")

    assert doctor.linux_power(tmp_path / "none") is None
    supply("BAT0", "Battery", status="Discharging")
    assert doctor.linux_power(tmp_path) == "battery"
    supply("AC", "Mains", online="1")
    assert doctor.linux_power(tmp_path) == "ac"
    (tmp_path / "junk").mkdir()
    assert doctor.linux_power(tmp_path) == "ac"


def test_version_parsers():
    assert doctor.parse_ffmpeg_version("ffmpeg version n7.1-3-gabc Copyright") == "n7.1-3-gabc"
    assert doctor.parse_ffmpeg_version("nothing") is None
    assert doctor.parse_node_version("v24.19.0\n") == "24.19.0" and doctor.parse_node_version("?") is None


def test_normalise_arch():
    assert doctor.normalise_arch("aarch64") == "arm64" and doctor.normalise_arch("AMD64") == "x86_64"


# --- the report ------------------------------------------------------------


def test_the_json_report_names_no_path_and_no_home(tmp_path):
    host = FakeHost(python_executable="/Users/someone/project/.venv/bin/python")
    report = run(host, tmp_path, gate=True)
    text = json.dumps(report.to_dict())
    assert "/Users/" not in text and "someone" not in text and "binary\"" not in text
    assert report.toolchain["python"]["where"] == "home folder"
    doc = report.to_dict()
    assert doc["kaleidophone"] == "doctor/1" and doc["gate"]["passed"] is True


def test_format_report_says_a_shared_fix_once(tmp_path):
    text = doctor.format_report(run(FakeHost(), tmp_path, gate=True))
    assert text.count("install native Homebrew at /opt/homebrew") == 1
    assert text.count("the same fix as above") == 3
    assert "bench gate: open -- 1-min load 0.40, power ac" in text
    assert text.endswith("ready, with the warnings above.")
    refused = doctor.format_report(run(FakeHost(load=4.0), tmp_path, gate=True))
    assert "bench gate: refused -- 1-min load 4.00 is over 1" in refused
    failed = doctor.format_report(run(FakeHost(tools={}), tmp_path))
    assert failed.endswith("not ready: fix what failed above.")
    assert doctor.format_report(run(native_host(), tmp_path)).endswith("ready.")


# --- the real machine, whatever it is ---------------------------------------


def test_the_real_host_answers_without_crashing(tmp_path):
    """No fakes: whatever runs the tests (CI runs them with no ffmpeg on PATH).
    The report must be JSON, and hold no path."""
    report = doctor.diagnose(out=str(tmp_path), gate=True)
    text = json.dumps(report.to_dict())
    assert os.path.expanduser("~") not in text
    assert {c.status for c in report.checks} <= set(doctor.STATUSES)
    assert report.exit_code in (0, doctor.EXIT_FAILED, doctor.EXIT_GATE_REFUSED)


def test_real_host_methods(tmp_path):
    host = doctor.Host()
    (tmp_path / "f").write_bytes(b"abc")
    assert host.read_head(str(tmp_path / "f")) == b"abc" and host.read_head(str(tmp_path / "nope")) is None
    assert host.size(str(tmp_path / "f")) == 3 and host.size(str(tmp_path / "nope")) is None
    assert host.disk_free(str(tmp_path)) > 0 and host.disk_free(str(tmp_path / "nope")) is None
    assert host.memory_bytes() is None or host.memory_bytes() > 0
    assert isinstance(host.os_name(), str) and host.python()["version"]
    (tmp_path / "bin").mkdir()
    tool = tmp_path / "bin" / "kp-tool"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)

    class OnPath(doctor.Host):
        def environ(self):
            return {"PATH": f"{tmp_path / 'bin'}{os.pathsep}{tmp_path / 'bin'}"}

    assert OnPath().which_all("kp-tool") == [str(tool)]
    host.sleep(0)
    if host.platform == "darwin":
        assert doctor._int(host.sysctl("hw.memsize")) > 0
        assert host.sysctl("no.such.sysctl") is None
        assert host.power() in ("ac", "battery", "ups", None)
    else:
        assert host.sysctl("hw.memsize") is None


# --- the command -------------------------------------------------------------


def test_cli_doctor_passes_the_reports_exit_code_through(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return doctor.Report([doctor.Check("load", "warn", "busy")], {}, doctor.Gate(False, ["busy"], 3.0, "ac"))

    monkeypatch.setattr(doctor, "diagnose", fake)
    code = cli.main(["doctor", "--json", "--bench-gate", "-o", str(tmp_path), "--wav", "a.wav", "--wav-wait", "0.5"])
    assert code == doctor.EXIT_GATE_REFUSED
    assert json.loads(capsys.readouterr().out)["gate"]["passed"] is False
    assert seen == {"out": str(tmp_path), "wavs": ["a.wav"], "wav_wait": 0.5, "canvas": None, "gate": True}
    assert cli.main(["doctor", "-o", str(tmp_path)]) == doctor.EXIT_GATE_REFUSED
    assert "bench gate: refused -- busy" in capsys.readouterr().out


def test_cli_doctor_refuses_a_negative_wait(capsys):
    assert cli.main(["doctor", "--wav-wait", "-1"]) == 2
    assert "--wav-wait" in capsys.readouterr().err
