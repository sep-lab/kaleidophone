"""
`kaleidophone doctor`: is this machine ready to render, and quiet enough to
benchmark?

    kaleidophone doctor [-o DIR] [--wav FILE ...] [--json] [--bench-gate]

Every engine shells out to tools it doesn't ship -- ffmpeg, node, a
Chromium -- and on an Apple Silicon Mac each of them can quietly be the
wrong build. The machine this project's numbers were measured on ran ffmpeg,
node and Python as x86_64 under Rosetta 2 for months, and nothing said so;
the Intel Homebrew at /usr/local also sits ahead of a native one at
/opt/homebrew on the default PATH, so installing the native tools changes
nothing until the PATH does. The doctor says which build each tool is, what
it runs as, and what to do about it:

- the host: chip, cores (performance and efficiency), memory, OS;
- python, ffmpeg, ffprobe and node: version, the CPU architecture in the
  binary's own header (Mach-O or ELF, read here, not guessed from a name),
  whether it runs translated, and which install it comes from -- by prefix
  (/opt/homebrew, /usr/local, ...), never by full path;
- the PATH order of /usr/local/bin and /opt/homebrew/bin, and every copy of
  each tool on it;
- the encoders a delivery uses: libx264 and aac (required), aac_at (macOS's
  AudioToolbox AAC, which benchmarks/ compares against aac);
- the canvas engine's Chromium: the revision the installed playwright-core
  launches, whether it is there, its architecture, and canvas/node_modules;
- the output folder: free space, a write-and-unlink test, whether a file
  name may contain "?" (a release title ended in one; exFAT and some network
  shares refuse it);
- with --wav, that a master is finished: its size holds still for
  --wav-wait seconds and matches what its RIFF/RF64/AIFF header declares (a
  bounce or a sync still in progress fails here, not halfway through a
  delivery);
- AC power and the 1-minute load average.

`--bench-gate` turns the last two into a refusal: exit 8 unless the 1-minute
load is at most 1, the machine is not on battery, and no check failed. The
benchmark harness (benchmarks/run.py) calls it first, so a number recorded in
docs/BENCHMARKS.md was measured on a quiet machine on AC power, or says that
it wasn't.

Exit codes: 0 ready (warnings allowed), 2 a check failed, 8 the bench gate
refused. `--json` prints the same report as JSON, and holds no path, host
name or user name: the WAVs are numbered, the tools named by prefix, the
output folder not named at all.

Everything the doctor asks the machine goes through one Host object, so the
checks are tested against a fake one (an M1 under Rosetta, a native one, a
Linux runner) without the machine under test being any of them. Processes
are started through render/_ffmpeg_util.py, like every other in the package.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

from kaleidophone import __version__
from kaleidophone.render import _ffmpeg_util

# The bench gate: a 1-minute load average above this means something else is
# running, and a benchmark taken now measures that too.
BENCH_MAX_LOAD = 1.0
EXIT_OK = 0
EXIT_FAILED = 2
EXIT_GATE_REFUSED = 8

LOW_DISK_GB = 20.0  # warn: a full film, its parts and a delivery need room
CRITICAL_DISK_GB = 5.0  # fail
WRITE_TEST_BYTES = 4 * 1024 * 1024
NODE_MIN_MAJOR = 20  # canvas/package.json's engines
DEFAULT_WAV_WAIT = 2.0

STATUSES = ("ok", "info", "skip", "warn", "fail")

# CPU types in a Mach-O header (mach/machine.h) and an ELF one (e_machine).
_MACHO_CPU = {
    7: "i386",
    0x01000007: "x86_64",
    12: "arm",
    0x0100000C: "arm64",
    0x0200000C: "arm64_32",
    18: "ppc",
    0x01000012: "ppc64",
}
_ELF_MACHINE = {0x03: "i386", 0x3E: "x86_64", 0x28: "arm", 0xB7: "arm64"}
_MACHINE_ALIASES = {"aarch64": "arm64", "amd64": "x86_64", "x64": "x86_64", "i686": "i386", "i386": "i386"}

# Where a tool comes from, named by prefix: the label is what a person needs
# ("the Intel Homebrew"), and never carries a user name or a folder of theirs.
_PREFIXES = (
    ("/opt/homebrew/", "/opt/homebrew"),
    ("/usr/local/", "/usr/local"),
    ("/opt/pw-browsers/", "/opt/pw-browsers"),
    ("/Library/Frameworks/Python.framework/", "python.org"),
    ("/Applications/Xcode", "Xcode"),
    ("/Library/Developer/CommandLineTools/", "Command Line Tools"),
    ("/nix/", "/nix"),
    ("/usr/", "/usr"),
    ("/bin/", "/bin"),
)

# The executables a Playwright Chromium download holds, by layout and era.
_CHROMIUM_BINARIES = {"Chromium", "Google Chrome for Testing", "chrome", "headless_shell", "chrome-headless-shell"}


# --------------------------------------------------------------------------
# what the machine says
# --------------------------------------------------------------------------
class Host:
    """Everything the doctor asks the machine, in one place a test replaces."""

    def __init__(self) -> None:
        self.platform = sys.platform
        self.home = os.path.expanduser("~")

    def environ(self) -> Mapping[str, str]:
        return os.environ

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def which_all(self, name: str) -> list[str]:
        """Every executable `name` on PATH, in PATH order (`which -a`)."""
        found = []
        for entry in self.environ().get("PATH", "").split(os.pathsep):
            candidate = os.path.join(entry, name)
            if entry and os.path.isfile(candidate) and os.access(candidate, os.X_OK) and candidate not in found:
                found.append(candidate)
        return found

    def realpath(self, path: str) -> str:
        return os.path.realpath(path)

    def read_head(self, path: str, size: int = 4096) -> bytes | None:
        try:
            with open(path, "rb") as fh:
                return fh.read(size)
        except OSError:
            return None

    def sysctl(self, name: str) -> bytes | None:
        """A macOS sysctl's raw value, asked through libc rather than a process."""
        if self.platform != "darwin":
            return None
        try:
            fn = ctypes.CDLL(None).sysctlbyname
        except (OSError, AttributeError):
            return None
        fn.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
        fn.restype = ctypes.c_int
        size = ctypes.c_size_t(0)
        if fn(name.encode(), None, ctypes.byref(size), None, 0) != 0 or size.value == 0:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if fn(name.encode(), buf, ctypes.byref(size), None, 0) != 0:
            return None
        return buf.raw[: size.value]

    def capture(self, argv: list[str]) -> tuple[int, str, str] | None:
        return _ffmpeg_util.capture(argv)

    def encoders(self, ffmpeg: str) -> frozenset[str]:
        return _ffmpeg_util.encoders(ffmpeg)

    def loadavg(self) -> float | None:
        try:
            return os.getloadavg()[0]
        except (AttributeError, OSError):
            return None

    def disk_free(self, path: str) -> int | None:
        try:
            return shutil.disk_usage(path).free
        except OSError:
            return None

    def cpu_count(self) -> int | None:
        return os.cpu_count()

    def memory_bytes(self) -> int | None:
        raw = self.sysctl("hw.memsize")
        if raw:
            return int.from_bytes(raw, "little")
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (AttributeError, ValueError, OSError):
            return None

    def machine(self) -> str:
        return platform.machine()

    def python(self) -> dict:
        return {
            "version": platform.python_version(),
            "machine": platform.machine(),
            "executable": sys.executable,
            "venv": sys.prefix != sys.base_prefix,
        }

    def os_name(self) -> str:
        if self.platform == "darwin":
            version = _text(self.sysctl("kern.osproductversion")) or platform.mac_ver()[0]
            return f"macOS {version}" if version else "macOS"
        if self.platform.startswith("linux"):
            with contextlib.suppress(OSError, AttributeError):
                pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
                if pretty:
                    return pretty
            return f"Linux {platform.release()}"
        return platform.system() or self.platform

    def cpu_model(self) -> str | None:
        brand = _text(self.sysctl("machdep.cpu.brand_string"))
        if brand:
            return brand
        with contextlib.suppress(OSError):
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        return None

    def power(self) -> str | None:
        """'ac', 'battery', 'ups', or None when the machine doesn't say."""
        if self.platform == "darwin":
            pmset = self.which("pmset") or "/usr/bin/pmset"
            got = self.capture([pmset, "-g", "ps"])
            return parse_pmset(got[1]) if got and got[0] == 0 else None
        return linux_power(Path("/sys/class/power_supply"))

    def size(self, path: str) -> int | None:
        try:
            return os.stat(path).st_size
        except OSError:
            return None

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _text(raw: bytes | None) -> str | None:
    if not raw:
        return None
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip() or None


def _int(raw: bytes | None) -> int | None:
    return int.from_bytes(raw, "little") if raw else None


# --------------------------------------------------------------------------
# readers, each a pure function of what a tool or a file said
# --------------------------------------------------------------------------
def binary_arches(head: bytes | None) -> list[str] | None:
    """The CPU architectures an executable's header says it holds: one for a
    thin Mach-O or ELF file, one per slice for a universal ("fat") Mach-O,
    None for anything else (a script, a shim, a missing file)."""
    if not head or len(head) < 8:
        return None
    little, big = int.from_bytes(head[:4], "little"), int.from_bytes(head[:4], "big")
    if little in (0xFEEDFACE, 0xFEEDFACF):
        return [_MACHO_CPU.get(int.from_bytes(head[4:8], "little"), "unknown")]
    if big in (0xFEEDFACE, 0xFEEDFACF):
        return [_MACHO_CPU.get(int.from_bytes(head[4:8], "big"), "unknown")]
    if big in (0xCAFEBABE, 0xCAFEBABF):
        count = int.from_bytes(head[4:8], "big")
        # 0xcafebabe is also a Java class file, whose next word is a version
        # number in the forties: a universal binary has a handful of slices.
        if not 0 < count < 16:
            return None
        entry = 20 if big == 0xCAFEBABE else 32
        arches = []
        for k in range(count):
            at = 8 + k * entry
            if at + 4 > len(head):
                break
            arches.append(_MACHO_CPU.get(int.from_bytes(head[at : at + 4], "big"), "unknown"))
        return arches or None
    if head[:4] == b"\x7fELF" and len(head) >= 20:
        order = "little" if head[5] == 1 else "big"
        return [_ELF_MACHINE.get(int.from_bytes(head[18:20], order), "unknown")]
    return None


def normalise_arch(machine: str) -> str:
    return _MACHINE_ALIASES.get(machine.lower(), machine.lower())


def runs_as(arches: list[str] | None, host_arch: str) -> tuple[str | None, bool]:
    """(the architecture a binary runs as on this host, whether it is
    translated). A universal binary runs as the host's own slice."""
    if not arches:
        return None, False
    if host_arch in arches:
        return host_arch, False
    if host_arch == "arm64" and "x86_64" in arches:
        return "x86_64", True
    return arches[0], False


def where(path: str | None, home: str | None = None) -> str | None:
    """Which install a tool comes from, by prefix -- never the path itself."""
    if not path:
        return None
    for prefix, label in _PREFIXES:
        if path.startswith(prefix):
            return label
    if home and (path == home or path.startswith(home.rstrip("/") + "/")):
        return "home folder"
    return "elsewhere"


def parse_ffmpeg_version(text: str) -> str | None:
    match = re.search(r"\b(?:ffmpeg|ffprobe) version (\S+)", text)
    return match.group(1) if match else None


def parse_node_version(text: str) -> str | None:
    match = re.match(r"\s*v?(\d+\.\d+\.\d+\S*)", text)
    return match.group(1) if match else None


def parse_pmset(text: str) -> str | None:
    """`pmset -g ps`'s first line: "Now drawing from 'AC Power'"."""
    match = re.search(r"drawing from '([^']+)'", text)
    if not match:
        return None
    source = match.group(1).lower()
    if source.startswith("ac"):
        return "ac"
    if "ups" in source:
        return "ups"
    if "battery" in source:
        return "battery"
    return None


def linux_power(root: Path) -> str | None:
    """AC, battery or None from /sys/class/power_supply: mains online is AC;
    a discharging battery with no mains is battery; nothing at all (a VM, a
    desktop that doesn't report) is None."""
    try:
        supplies = sorted(root.iterdir())
    except OSError:
        return None
    mains = battery = False
    for supply in supplies:
        try:
            kind = (supply / "type").read_text().strip().lower()
        except OSError:
            continue
        if kind == "mains":
            with contextlib.suppress(OSError):
                mains = mains or (supply / "online").read_text().strip() == "1"
        elif kind == "battery":
            with contextlib.suppress(OSError):
                battery = battery or (supply / "status").read_text().strip().lower() == "discharging"
    if mains:
        return "ac"
    return "battery" if battery else None


def path_order(path_env: str) -> dict:
    """Where /usr/local/bin and /opt/homebrew/bin sit on PATH (None: absent)."""
    entries = [os.path.normpath(p) for p in path_env.split(os.pathsep) if p]

    def index(directory: str) -> int | None:
        return entries.index(directory) if directory in entries else None

    return {"usr_local_bin": index("/usr/local/bin"), "opt_homebrew_bin": index("/opt/homebrew/bin")}


def declared_size(head: bytes) -> tuple[str, int | None] | None:
    """(container, the file size its header declares) for a RIFF/WAVE, RF64
    or BW64, or AIFF/AIFC header; None for anything else. The size is None
    when the header holds a placeholder -- what a writer puts there until it
    finishes."""
    if len(head) < 12:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        riff = int.from_bytes(head[4:8], "little")
        return "wav", None if riff in (0, 0xFFFFFFFF) else riff + 8
    if head[:4] in (b"RF64", b"BW64") and head[8:12] == b"WAVE":
        if len(head) >= 28 and head[12:16] == b"ds64":
            riff = int.from_bytes(head[20:28], "little")
            return "rf64", riff + 8 if riff else None
        return "rf64", None
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        form = int.from_bytes(head[4:8], "big")
        return "aiff", form + 8 if form else None
    return None


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------
@dataclass
class Check:
    id: str
    status: str  # one of STATUSES
    summary: str
    fix: str | None = None
    data: dict = field(default_factory=dict)


@dataclass
class Gate:
    passed: bool
    reasons: list[str]
    load_1m: float | None
    power: str | None
    max_load: float = BENCH_MAX_LOAD


@dataclass
class Report:
    checks: list[Check]
    toolchain: dict
    gate: Gate | None = None

    @property
    def status(self) -> str:
        found = {c.status for c in self.checks}
        return "fail" if "fail" in found else "warn" if "warn" in found else "ok"

    @property
    def exit_code(self) -> int:
        if self.gate is not None and not self.gate.passed:
            return EXIT_GATE_REFUSED
        return EXIT_FAILED if self.status == "fail" else EXIT_OK

    def to_dict(self) -> dict:
        return {
            "kaleidophone": "doctor/1",
            "version": __version__,
            "status": self.status,
            "toolchain": self.toolchain,
            "checks": [asdict(c) for c in self.checks],
            "gate": asdict(self.gate) if self.gate is not None else None,
        }


def format_report(report: Report) -> str:
    lines = [f"kaleidophone doctor -- {__version__}", ""]
    width = max((len(c.id) for c in report.checks), default=8)
    said: set[str] = set()
    for c in report.checks:
        lines.append(f"  {c.status:<5} {c.id:<{width}}  {c.summary}")
        if c.fix and c.status in ("warn", "fail", "info"):
            # One fix for several checks (every translated tool) is said once.
            lines.append(f"  {'':<5} {'':<{width}}  -> {c.fix if c.fix not in said else 'the same fix as above'}")
            said.add(c.fix)
    lines.append("")
    if report.gate is not None:
        g = report.gate
        if g.passed:
            lines.append(f"bench gate: open -- 1-min load {g.load_1m:.2f}, power {g.power or 'unknown'}")
        else:
            lines.append("bench gate: refused -- " + "; ".join(g.reasons))
    lines.append(
        {"ok": "ready.", "warn": "ready, with the warnings above.", "fail": "not ready: fix what failed above."}[
            report.status
        ]
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------
def host_arch(host: Host) -> str:
    """The machine's own architecture. platform.machine() says x86_64 inside
    a translated process on Apple Silicon; hw.optional.arm64 doesn't."""
    if _int(host.sysctl("hw.optional.arm64")) == 1:
        return "arm64"
    return normalise_arch(host.machine())


def _host_check(host: Host, arch: str) -> tuple[Check, dict]:
    perf, eff = _int(host.sysctl("hw.perflevel0.physicalcpu")), _int(host.sysctl("hw.perflevel1.physicalcpu"))
    memory = host.memory_bytes()
    info = {
        "arch": arch,
        "cpu": host.cpu_model(),
        "model": _text(host.sysctl("hw.model")),
        "cores": {"logical": host.cpu_count(), "performance": perf, "efficiency": eff},
        "memory_gb": round(memory / 2**30, 1) if memory else None,
        "os": host.os_name(),
    }
    cores = f"{perf}P+{eff}E cores" if perf and eff else f"{info['cores']['logical']} cores"
    memory_text = f", {info['memory_gb']:g} GB" if info["memory_gb"] else ""
    summary = f"{info['cpu'] or 'unknown CPU'}, {arch}, {cores}{memory_text}, {info['os']}"
    return Check("host", "info", summary, data=info), info


def _translated_fix(arch: str) -> str | None:
    if arch != "arm64":
        return None
    return (
        "install native Homebrew at /opt/homebrew, then `brew install ffmpeg node python@3.11`, put "
        "/opt/homebrew/bin first on PATH and rebuild .venv -- docs/BENCHMARKS.md says why"
    )


def _python_check(host: Host, arch: str) -> tuple[Check, dict]:
    py = host.python()
    translated = _int(host.sysctl("sysctl.proc_translated")) == 1
    runs = normalise_arch(py["machine"])
    info = {
        "version": py["version"],
        "arch": runs,
        "translated": translated,
        "where": where(host.realpath(py["executable"]), host.home),
        "venv": py["venv"],
    }
    origin = f" ({info['where']}{', a venv' if info['venv'] else ''})"
    if translated:
        return (
            Check("python", "warn", f"{py['version']}, {runs} translated by Rosetta 2{origin}", _translated_fix(arch), info),
            info,
        )
    return Check("python", "ok", f"{py['version']}, {runs}{origin}", data=info), info


def _tool(host: Host, name: str, arch: str) -> dict:
    """A tool on PATH: where it resolves, what its header says, what it runs as."""
    found = host.which(name)
    if not found:
        return {"found": False}
    real = host.realpath(found)
    arches = binary_arches(host.read_head(real))
    runs, translated = runs_as(arches, arch)
    return {
        "found": True,
        "binary": found,
        "arch": runs,
        "binary_arches": arches,
        "translated": translated,
        "where": where(real, host.home),
    }


def _public(tool: dict) -> dict:
    return {k: v for k, v in tool.items() if k != "binary"}


def _arch_text(tool: dict) -> str:
    if tool["arch"] is None:
        return "architecture unknown (not a Mach-O or ELF binary: a script or a shim?)"
    if tool["translated"]:
        return f"{tool['arch']} translated by Rosetta 2"
    slices = tool.get("binary_arches") or []
    return f"{tool['arch']}{' (universal)' if len(slices) > 1 else ''}"


def _ffmpeg_checks(host: Host, arch: str) -> tuple[list[Check], dict, str | None]:
    checks = []
    info: dict = {}
    for name in ("ffmpeg", "ffprobe"):
        tool = _tool(host, name, arch)
        if not tool["found"]:
            status = "fail" if name == "ffmpeg" else "warn"
            why = "every render and delivery runs through it" if name == "ffmpeg" else "deliver probes every file with it"
            checks.append(Check(name, status, f"{name} is not on PATH: {why}", "brew install ffmpeg", {"found": False}))
            info[name] = {"found": False}
            continue
        # ffprobe has no -nostdin (and reads no stdin); ffmpeg is told not to look.
        quiet = ["-nostdin"] if name == "ffmpeg" else []
        got = host.capture([tool["binary"], "-hide_banner", *quiet, "-version"])
        tool["version"] = parse_ffmpeg_version(got[1]) if got and got[0] == 0 else None
        summary = f"{tool['version'] or 'version unknown'}, {_arch_text(tool)} ({tool['where']})"
        status = "warn" if tool["translated"] else "ok"
        checks.append(Check(name, status, summary, _translated_fix(arch) if tool["translated"] else None, _public(tool)))
        info[name] = _public(tool)
    ffmpeg = host.which("ffmpeg") if info["ffmpeg"].get("found") else None
    return checks, info, ffmpeg


def _encoders_check(host: Host, ffmpeg: str | None, info: dict) -> Check:
    if ffmpeg is None:
        return Check("encoders", "skip", "no ffmpeg to ask")
    have = host.encoders(ffmpeg)
    wanted = ("libx264", "aac", "aac_at", "h264_videotoolbox")
    found = {name: name in have for name in wanted}
    info["ffmpeg"]["encoders"] = found
    missing = [name for name in ("libx264", "aac") if not found[name]]
    listed = ", ".join(f"{name} {'yes' if ok else 'no'}" for name, ok in found.items())
    if not have:
        return Check("encoders", "fail", "ffmpeg -encoders said nothing", "reinstall ffmpeg", found)
    if missing:
        return Check(
            "encoders",
            "fail",
            f"{' and '.join(missing)} missing ({listed})",
            "install an ffmpeg built with libx264 (Homebrew's is)",
            found,
        )
    note = "" if found["aac_at"] else " -- no aac_at: the aac-vs-aac_at benchmark will skip it"
    return Check("encoders", "ok", f"{listed}{note}", data=found)


def _node_check(host: Host, arch: str) -> tuple[Check, dict]:
    tool = _tool(host, "node", arch)
    if not tool["found"]:
        return (
            Check("node", "warn", f"node is not on PATH: the canvas engine needs node {NODE_MIN_MAJOR} or later",
                  "brew install node", {"found": False}),
            {"found": False},
        )
    got = host.capture([tool["binary"], "--version"])
    tool["version"] = parse_node_version(got[1]) if got and got[0] == 0 else None
    info = _public(tool)
    summary = f"{tool['version'] or 'version unknown'}, {_arch_text(tool)} ({tool['where']})"
    major = int(tool["version"].split(".")[0]) if tool["version"] else None
    if major is not None and major < NODE_MIN_MAJOR:
        return Check("node", "warn", f"{summary}: the canvas engine needs {NODE_MIN_MAJOR}+", "brew install node", info), info
    if tool["translated"]:
        return Check("node", "warn", summary, _translated_fix(arch), info), info
    return Check("node", "ok", summary, data=info), info


def _path_check(host: Host, arch: str) -> Check:
    if host.platform != "darwin":
        return Check("path", "skip", "one Homebrew prefix on this OS: nothing to shadow")
    env = host.environ()
    order = path_order(env.get("PATH", ""))
    copies = {name: [where(host.realpath(p), host.home) for p in host.which_all(name)] for name in ("ffmpeg", "node", "python3")}
    data = {**order, "copies": copies}
    usr_local, native = order["usr_local_bin"], order["opt_homebrew_bin"]
    shadowed = [name for name, found in copies.items() if "/opt/homebrew" in found and found[0] != "/opt/homebrew"]
    if native is None:
        if arch == "arm64":
            return Check(
                "path",
                "info",
                "/opt/homebrew/bin is not on PATH: no native Homebrew in use",
                "after installing it, put `eval \"$(/opt/homebrew/bin/brew shellenv)\"` at the end of ~/.zprofile",
                data,
            )
        return Check("path", "ok", "no /opt/homebrew/bin (not an Apple Silicon Mac)", data=data)
    if usr_local is not None and usr_local < native:
        names = f": {', '.join(shadowed)} resolve to /usr/local" if shadowed else ""
        return Check(
            "path",
            "warn",
            f"/usr/local/bin comes before /opt/homebrew/bin, so the Intel tools win{names}",
            "move `eval \"$(/opt/homebrew/bin/brew shellenv)\"` after anything that adds /usr/local/bin, and open "
            "a new terminal",
            data,
        )
    return Check("path", "ok", "/opt/homebrew/bin comes first", data=data)


def find_canvas(given: str | None = None, cwd: str | None = None) -> Path | None:
    """The canvas/ folder of a kaleidophone checkout: the one given, else the
    checkout `cwd` is in, else the one next to this package (an editable
    install). The folder you're in comes first: an editable install from one
    checkout, run inside another (a worktree), must report the one you're in."""

    def is_canvas(folder: Path) -> bool:
        package = folder / "package.json"
        try:
            return '"kaleidophone-canvas"' in package.read_text(encoding="utf-8")
        except OSError:
            return False

    if given:
        folder = Path(given)
        return folder if is_canvas(folder) else None
    here = Path(cwd or os.getcwd()).resolve()
    candidates = [here, *(d / "canvas" for d in (here, *here.parents))]
    candidates.append(Path(__file__).resolve().parents[2] / "canvas")
    for folder in candidates:
        if is_canvas(folder):
            return folder
    return None


def playwright_cache(host: Host) -> Path | None:
    """Where playwright-core keeps its browsers (its own registry's rules)."""
    env = host.environ()
    given = env.get("PLAYWRIGHT_BROWSERS_PATH")
    if given and given != "0":
        return Path(given)
    if host.platform == "darwin":
        return Path(host.home) / "Library" / "Caches" / "ms-playwright"
    if host.platform.startswith("win"):
        local = env.get("LOCALAPPDATA")
        return Path(local) / "ms-playwright" if local else None
    return Path(env.get("XDG_CACHE_HOME") or Path(host.home) / ".cache") / "ms-playwright"


def _chromium_binary(folder: Path) -> Path | None:
    for root, dirs, files in os.walk(folder):
        # A Chromium.app's frameworks hold hundreds of files and no launcher.
        dirs[:] = [d for d in dirs if not d.endswith((".framework", ".xpc", ".bundle"))]
        if len(Path(root).relative_to(folder).parts) > 5:
            dirs[:] = []
            continue
        for name in files:
            if name in _CHROMIUM_BINARIES:
                return Path(root) / name
    return None


def _json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _chromium_check(host: Host, arch: str, canvas: Path | None) -> tuple[list[Check], dict]:
    if canvas is None:
        skip = Check("chromium", "skip", "not in a kaleidophone checkout (no canvas/ found): pass --canvas DIR")
        return [skip], {}
    checks = []
    modules = canvas / "node_modules"
    core = _json(modules / "playwright-core" / "package.json")
    if core is None:
        checks.append(
            Check("node_modules", "warn", "canvas/node_modules is not installed: the canvas engine can't run",
                  "cd canvas && npm ci", {"installed": False})
        )
        return checks, {"node_modules": False}
    checks.append(Check("node_modules", "ok", f"installed (playwright-core {core.get('version')})",
                        data={"installed": True, "playwright_core": core.get("version")}))
    registry = _json(modules / "playwright-core" / "browsers.json") or {}
    expected = {
        b["name"]: str(b["revision"])
        for b in registry.get("browsers", [])
        if b.get("name") in ("chromium", "chromium-headless-shell")
    }
    info: dict = {"playwright_core": core.get("version"), "expected": expected, "override": None}
    env = host.environ()
    override = env.get("KALEIDOPHONE_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    if override:
        real = host.realpath(override)
        runs, translated = runs_as(binary_arches(host.read_head(real)), arch)
        info.update(override="KALEIDOPHONE_CHROMIUM" if env.get("KALEIDOPHONE_CHROMIUM") else "/opt/pw-browsers", arch=runs)
        exists = host.size(real) is not None
        status = "ok" if exists else "fail"
        what = "KALEIDOPHONE_CHROMIUM" if env.get("KALEIDOPHONE_CHROMIUM") else "the cloud sandbox's Chromium"
        summary = f"{what} is set: {runs or 'architecture unknown'}" if exists else f"{what} is set, and is not there"
        checks.append(Check("chromium", status, summary, None if exists else "unset it, or point it at a Chromium", info))
        return checks, info
    cache = playwright_cache(host)
    installed: dict[str, list[str]] = {"chromium": [], "chromium-headless-shell": []}
    if cache is not None and cache.is_dir():
        for entry in sorted(cache.iterdir()):
            for name in installed:
                prefix = name.replace("-", "_") + "-"
                if entry.name.startswith(prefix) and entry.name[len(prefix) :].isdigit():
                    installed[name].append(entry.name[len(prefix) :])
    info["installed"] = installed
    # A headless launch (every render, every still) uses the headless shell.
    shell = expected.get("chromium-headless-shell") or expected.get("chromium")
    kind = "chromium-headless-shell" if "chromium-headless-shell" in expected else "chromium"
    if shell is None:
        checks.append(Check("chromium", "warn", "playwright-core names no Chromium revision", "cd canvas && npm ci", info))
        return checks, info
    folder = cache / f"{kind.replace('-', '_')}-{shell}" if cache is not None else None
    binary = _chromium_binary(folder) if folder is not None and folder.is_dir() else None
    if binary is None:
        others = ", ".join(installed[kind]) or "none"
        checks.append(
            Check(
                "chromium",
                "warn",
                f"playwright-core {core.get('version')} launches {kind} {shell}, which isn't installed "
                f"(installed: {others}): canvas renders won't start",
                "cd canvas && npx playwright-core install chromium",
                info,
            )
        )
        return checks, info
    runs, translated = runs_as(binary_arches(host.read_head(str(binary))), arch)
    info.update(revision=shell, arch=runs, translated=translated)
    summary = f"{kind} {shell}, {runs or 'architecture unknown'}{' translated by Rosetta 2' if translated else ''}"
    checks.append(Check("chromium", "warn" if translated else "ok", summary, data=info))
    return checks, info


def _disk_checks(host: Host, out: str) -> list[Check]:
    checks = []
    if not os.path.isdir(out):
        return [Check("disk", "fail", "the output folder doesn't exist", "create it, or pass -o DIR")]
    free = host.disk_free(out)
    if free is None:
        checks.append(Check("disk", "warn", "free space can't be read here"))
    else:
        gb = free / 1e9
        data = {"free_gb": round(gb, 1)}
        if gb < CRITICAL_DISK_GB:
            checks.append(Check("disk", "fail", f"{gb:.1f} GB free in the output folder", "free some space", data))
        elif gb < LOW_DISK_GB:
            checks.append(Check("disk", "warn", f"{gb:.1f} GB free: a full film, its parts and a delivery need more",
                                "free some space", data))
        else:
            checks.append(Check("disk", "ok", f"{gb:.0f} GB free in the output folder", data=data))
    checks.append(_write_check(out))
    checks.append(_question_mark_check(out))
    return checks


def _write_check(out: str) -> Check:
    path = None
    try:
        fd, path = tempfile.mkstemp(prefix=".kp-doctor-", suffix=".tmp", dir=out)
        started = time.perf_counter()
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"\0" * WRITE_TEST_BYTES)
            fh.flush()
            os.fsync(fh.fileno())
        took = time.perf_counter() - started
        os.unlink(path)
        if os.path.exists(path):
            return Check("write", "fail", "a test file was written and couldn't be removed")
    except OSError as exc:
        if path is not None:
            with contextlib.suppress(OSError):
                os.unlink(path)
        return Check("write", "fail", f"can't write into the output folder ({exc.strerror or exc})", "check its permissions")
    rate = WRITE_TEST_BYTES / 1e6 / took if took > 0 else None
    data = {"mb_per_s": round(rate) if rate else None}
    return Check("write", "ok", "write, fsync and unlink work" + (f" ({rate:.0f} MB/s for 4 MiB)" if rate else ""), data=data)


def _question_mark_check(out: str) -> Check:
    name = f".kp-doctor-?-{os.getpid()}.tmp"
    path = os.path.join(out, name)
    try:
        with open(path, "x"):
            pass
        kept = name in os.listdir(out)
        os.unlink(path)
    except OSError:
        return Check(
            "filenames",
            "warn",
            "this disk refuses '?' in a file name (exFAT? a network share?)",
            "render to an APFS or ext4 disk, or give the delivery sheet a `slug` without one",
            {"question_mark": False},
        )
    if not kept:
        return Check("filenames", "warn", "this disk renames a file with '?' in it", "render to an APFS or ext4 disk",
                     {"question_mark": False})
    return Check("filenames", "ok", "'?' is allowed in file names", data={"question_mark": True})


def _wav_check(host: Host, number: int, path: str, wait: float) -> Check:
    label = f"wav #{number}"
    before = host.size(path)
    if before is None:
        return Check(label, "fail", "no such file", "check the path you gave --wav")
    host.sleep(wait)
    after = host.size(path)
    data: dict = {"bytes": after, "waited_s": wait}
    if after is None:
        return Check(label, "fail", f"disappeared while being watched ({wait:g} s)", data=data)
    if after != before:
        return Check(
            label,
            "fail",
            f"still being written: {after - before:+d} bytes in {wait:g} s",
            "wait for the bounce, the copy or the sync to finish",
            data,
        )
    if after == 0:
        return Check(label, "fail", "empty", data=data)
    header = declared_size(host.read_head(path, 64) or b"")
    if header is None:
        return Check(label, "ok", f"{after / 1e6:.1f} MB, size stable for {wait:g} s (not a WAV/AIFF: header not checked)",
                     data=data)
    container, declared = header
    data.update(container=container, declared_bytes=declared)
    if declared is None:
        return Check(label, "warn", f"its {container} header holds a placeholder size: the writer may not have finished",
                     "re-export it, or wait for the bounce to finish", data)
    if declared > after:
        return Check(
            label, "fail", f"truncated: its header declares {declared} bytes and the file has {after}",
            "copy or bounce it again", data,
        )
    if declared < after:
        return Check(label, "warn", f"{after - declared} bytes past what its header declares (trailing data?)", data=data)
    return Check(label, "ok", f"{after / 1e6:.1f} MB, size stable for {wait:g} s and matches its {container} header",
                 data=data)


def _power_check(power: str | None) -> Check:
    if power is None:
        return Check("power", "info", "the power source isn't reported here", data={"source": None})
    if power in ("battery", "ups"):
        return Check("power", "warn", f"on {power} power: renders slow down, and benchmarks are refused",
                     "plug in", {"source": power})
    return Check("power", "ok", "on AC power", data={"source": power})


def _load_check(load: float | None, cores: int | None) -> Check:
    if load is None:
        return Check("load", "info", "the load average isn't available here", data={"load_1m": None})
    data = {"load_1m": round(load, 2), "cores": cores}
    if load > BENCH_MAX_LOAD:
        return Check(
            "load",
            "warn",
            f"1-min load {load:.2f}{f' on {cores} cores' if cores else ''}: fine to render, too busy to benchmark",
            "close what's running and wait a minute before a benchmark",
            data,
        )
    return Check("load", "ok", f"1-min load {load:.2f}: quiet", data=data)


def bench_gate(load: float | None, power: str | None, checks: list[Check]) -> Gate:
    """Whether this machine may be benchmarked now. It fails closed: a load
    average that can't be read refuses, like a busy one."""
    reasons = []
    if load is None:
        reasons.append("the 1-min load average can't be read here, so a quiet machine can't be confirmed")
    elif load > BENCH_MAX_LOAD:
        reasons.append(f"1-min load {load:.2f} is over {BENCH_MAX_LOAD:g}: close what's running and wait a minute")
    if power in ("battery", "ups"):
        reasons.append(f"on {power} power: plug in")
    failed = [c.id for c in checks if c.status == "fail"]
    if failed:
        reasons.append(f"failing checks: {', '.join(failed)}")
    return Gate(passed=not reasons, reasons=reasons, load_1m=None if load is None else round(load, 2), power=power)


def diagnose(
    host: Host | None = None,
    *,
    out: str = ".",
    wavs: list[str] | tuple[str, ...] = (),
    wav_wait: float = DEFAULT_WAV_WAIT,
    canvas: str | None = None,
    gate: bool = False,
    find: Callable[[str | None], Path | None] | None = None,
) -> Report:
    """Run every check and return the report (and, with `gate`, the bench gate)."""
    host = host or Host()
    # The load first: the checks below start processes of their own.
    load = host.loadavg()
    power = host.power()
    arch = host_arch(host)
    checks: list[Check] = []
    toolchain: dict = {}

    check, toolchain["host"] = _host_check(host, arch)
    checks.append(check)
    check, toolchain["python"] = _python_check(host, arch)
    checks.append(check)
    ff_checks, ff_info, ffmpeg = _ffmpeg_checks(host, arch)
    checks += ff_checks
    toolchain.update(ff_info)
    checks.append(_encoders_check(host, ffmpeg, toolchain))
    check, toolchain["node"] = _node_check(host, arch)
    checks.append(check)
    checks.append(_path_check(host, arch))
    chromium_checks, toolchain["chromium"] = _chromium_check(host, arch, (find or find_canvas)(canvas))
    checks += chromium_checks
    checks += _disk_checks(host, out)
    checks += [_wav_check(host, k, path, wav_wait) for k, path in enumerate(wavs, start=1)]
    checks.append(_power_check(power))
    checks.append(_load_check(load, toolchain["host"]["cores"]["logical"]))
    return Report(checks, toolchain, bench_gate(load, power, checks) if gate else None)
