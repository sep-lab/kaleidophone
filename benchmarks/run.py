#!/usr/bin/env python3
"""
The benchmark harness: run a suite, take the median of N runs, write one
`kp-bench/1` JSON file.

    python benchmarks/run.py --suite quick
    python benchmarks/run.py --suite all --runs 3
    python benchmarks/run.py --suite canvas-knee --workers 1,2,4,6,8,10
    python benchmarks/run.py --suite aac-vs-aac_at --private-master ~/masters

Suites (benchmarks/suites.py; docs/BENCHMARKS.md says what each one answers):
canvas-knee, footage, deliver, aac-vs-aac_at, loop-seam, long-form, and
quick -- every suite in miniature, under five minutes, a smoke test and
never a baseline. `all` runs every suite but quick.

Before anything runs, `kaleidophone doctor --bench-gate` is asked whether the
machine is quiet (1-minute load at most 1), on AC power, and has nothing
failing; it refuses otherwise, and so does this. `--ungated` runs anyway and
says so in the result, which then backs no number in docs/BENCHMARKS.md.

The result names no host, no user and no path: the toolchain is described
by version, architecture and install prefix (doctor's own report), private
inputs by number, and a check over every string in the file refuses to write
it otherwise (hygiene_problems below; tests/test_benchmarks.py tests it).
Fixtures are generated into a work folder outside the repository (--work,
default a temporary folder) and removed afterwards unless --keep.

The code under test is this checkout's: child processes run with its src/
first on PYTHONPATH and its canvas/ tools.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import getpass
import json
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# This checkout's code, in this process as in its children (Bench.env), whatever is installed.
sys.path[:0] = [str(HERE), str(REPO / "src")]

import suites  # noqa: E402  (after the path: benchmarks/ is a folder of scripts, not a package)

SCHEMA = "kp-bench/1"
EXIT_GATE_REFUSED = 8
EXIT_HYGIENE = 3
DEFAULT_RUNS = 3

# Install prefixes doctor names a tool's origin by: generic, never personal.
ALLOWED_PREFIXES = frozenset({"/opt/homebrew", "/usr/local", "/usr", "/bin", "/nix", "/opt/pw-browsers"})
_PATHLIKE = re.compile(
    r"(?:^|[^\w.-])/[^/\s]+/"  # an absolute path
    r"|^/[^/\s]+$"  # an absolute path one folder deep
    r"|^~/|\\|^[A-Za-z]:[\\/]"  # under home; anything Windows
    r"|[^\s/]+/[^\s/]+/"  # a relative path two folders deep ("kp-bench/1" is one)
)
# A media, data or sheet file's name, which can be a song's.
_FILENAME = re.compile(
    r"[^\s/\\]+\.(?:wav|aiff?|flac|mp3|m4a|ogg|opus|mp4|m4v|mov|mkv|webm|jpe?g|png|tiff?|heic|json|ya?ml)\b",
    re.IGNORECASE,
)
# The RSS sampler's period. `ps -A` costs about 26 ms of CPU a sample on the
# reference Mac (measured): 4 Hz took a tenth of a core from what was being
# measured, 1 Hz takes about a fortieth; the process's own kernel-counted
# peak is the floor either way (Bench.measure).
SAMPLE_EVERY_S = 1.0
GATE_POLL_S = 60.0


# --------------------------------------------------------------------------
# hygiene: no host, user or path in a result
# --------------------------------------------------------------------------
def private_tokens() -> list[str]:
    """Strings this machine would leak: its host names, the user, the home folder."""
    tokens = set()
    with contextlib.suppress(OSError):
        host = socket.gethostname()
        tokens.update({host, host.split(".")[0]})
    with contextlib.suppress(Exception):
        tokens.add(getpass.getuser())
    tokens.add(os.path.expanduser("~"))
    return sorted(t for t in tokens if t and len(t) >= 3 and t not in ("localhost", "root"))


def hygiene_problems(doc: object, tokens: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Where `doc` holds something a published result mustn't: a path, or
    one of `tokens` (host and user names). Returns JSON paths with the reason
    -- never the offending text itself."""
    problems: list[str] = []
    lowered = [t.lower() for t in tokens]

    def text(where: str, value: str) -> None:
        if value not in ALLOWED_PREFIXES and _PATHLIKE.search(value):
            problems.append(f"{where}: looks like a path")
        elif _FILENAME.search(value):
            problems.append(f"{where}: names a file")
        low = value.lower()
        for k, token in enumerate(lowered):
            if token in low:
                problems.append(f"{where}: holds private token #{k + 1}")

    def walk(where: str, value: object) -> None:
        if isinstance(value, str):
            text(where, value)
        elif isinstance(value, dict):
            for k, (key, item) in enumerate(value.items()):
                # A key is checked like a value; one that leaks is named by position only.
                before = len(problems)
                text(f"{where}{{key #{k + 1}}}", str(key))
                walk(f"{where}.{key}" if len(problems) == before else f"{where}{{#{k + 1}}}", item)
        elif isinstance(value, (list, tuple)):
            for k, item in enumerate(value):
                walk(f"{where}[{k}]", item)

    walk("$", doc)
    return problems


def scrub(message: str) -> str:
    """A failure message fit for a result: every path-like word and file name replaced."""
    words = []
    for word in str(message).split():
        words.append("<path>" if _PATHLIKE.search(word) else "<file>" if _FILENAME.search(word) else word)
    text = " ".join(words)
    for token in private_tokens():
        text = re.sub(re.escape(token), "<private>", text, flags=re.IGNORECASE)
    return text[:300]


# --------------------------------------------------------------------------
# measuring a process
# --------------------------------------------------------------------------
def tree_rss_kib(root: int) -> int | None:
    """Resident memory of `root` and every process under it, in KiB (ps)."""
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,ppid=,rss="], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    children: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            continue
        pid, ppid, kib = map(int, parts)
        children.setdefault(ppid, []).append(pid)
        rss[pid] = kib
    if root not in rss:
        return None
    total, stack = 0, [root]
    while stack:
        pid = stack.pop()
        total += rss.get(pid, 0)
        stack += children.get(pid, [])
    return total


class _Sampler(threading.Thread):
    """Samples a process tree's resident memory until stopped; keeps the peak."""

    def __init__(self, pid: int, every: float = SAMPLE_EVERY_S):
        super().__init__(daemon=True)
        self.pid, self.every, self.peak_kib = pid, every, 0
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            kib = tree_rss_kib(self.pid)
            if kib:
                self.peak_kib = max(self.peak_kib, kib)
            self._halt.wait(self.every)

    def stop(self) -> int:
        self._halt.set()
        self.join()
        return self.peak_kib


def summarize_profile(path: Path) -> dict:
    """A KALEIDOPHONE_PROFILE file, by call kind: how many calls, how many ms in all."""
    kinds: dict[str, dict] = {}
    with contextlib.suppress(OSError):
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            entry = kinds.setdefault(row.get("kind", "other"), {"calls": 0, "ms": 0.0})
            entry["calls"] += 1
            entry["ms"] = round(entry["ms"] + float(row.get("wall_ms") or 0.0), 1)
    return dict(sorted(kinds.items(), key=lambda kv: -kv[1]["ms"]))


class CaseFailed(RuntimeError):
    pass


def median_of(runs: list[dict]) -> dict:
    """The median of every number the runs share (bools and nested values aside)."""
    keys = [k for k, v in runs[0].items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    out = {}
    for key in keys:
        values = [r[key] for r in runs if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)]
        if len(values) == len(runs):
            out[key] = round(statistics.median(values), 4)
    return out


# --------------------------------------------------------------------------
# the bench
# --------------------------------------------------------------------------
class Bench:
    """What a suite gets: where to work, how to run a command and time it,
    and where to put what it found."""

    def __init__(self, args: argparse.Namespace, work: Path, toolchain: dict):
        self.args = args
        self.quick = args.suite == "quick"
        self.runs = args.runs if args.runs is not None else (1 if self.quick else DEFAULT_RUNS)
        self.work = work
        self.repo = REPO
        self.canvas = REPO / "canvas"
        self.python = sys.executable
        self.ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self.node = shutil.which("node")
        self.toolchain = toolchain
        self.cases: list[dict] = []
        self.skipped: list[dict] = []
        self.failed: list[dict] = []
        self.env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO / "src"), os.environ.get("PYTHONPATH")]))}
        self.env.pop("KALEIDOPHONE_PROFILE", None)
        self._profiles = 0

    # ---- what a suite can ask
    def log(self, message: str) -> None:
        print(f"[bench] {message}", flush=True)

    def cli(self, *args: str) -> list[str]:
        return [self.python, "-m", "kaleidophone.cli", *args]

    def canvas_problem(self) -> str | None:
        """Why the canvas engine can't run here, or None."""
        if not self.node:
            return "node is not on PATH"
        if not (self.canvas / "node_modules" / "playwright-core").is_dir():
            return "canvas/node_modules is not installed (cd canvas && npm ci)"
        chromium = self.toolchain.get("chromium") or {}
        if not chromium.get("override") and not chromium.get("revision"):
            return "the Chromium revision playwright-core launches is not installed (cd canvas && npx playwright-core install chromium)"
        return None

    def measure(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
        env: dict | None = None,
        tree_rss: bool = False,
        profile: bool = False,
    ) -> dict:
        """Run `argv` to completion and time it: wall seconds, exit code, the
        process's own peak RSS (the kernel's count), and, with `tree_rss`, the
        sampled peak of it and every process under it (Chromium's included). With `profile`, the run's
        KALEIDOPHONE_PROFILE, summarised by call kind. Raises CaseFailed on a
        non-zero exit, with the end of its output, paths scrubbed."""
        env = dict(env or self.env)
        prof = None
        if profile:
            self._profiles += 1
            prof = self.work / "profiles" / f"{self._profiles:05d}.jsonl"
            prof.parent.mkdir(parents=True, exist_ok=True)
            env["KALEIDOPHONE_PROFILE"] = str(prof)
        log = tempfile.TemporaryFile()
        started = time.perf_counter()
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        sampler = _Sampler(proc.pid) if tree_rss else None
        if sampler:
            sampler.start()
        _, status, usage = os.wait4(proc.pid, 0)
        wall = time.perf_counter() - started
        proc.returncode = os.waitstatus_to_exitcode(status)
        peak_tree = sampler.stop() if sampler else None
        log.seek(0)
        output = log.read().decode("utf-8", errors="replace")
        log.close()
        # ru_maxrss: bytes on macOS, KiB on Linux.
        self_mb = usage.ru_maxrss / (2**20 if sys.platform == "darwin" else 2**10)
        if proc.returncode != 0:
            tail = " | ".join(output.strip().splitlines()[-3:])
            raise CaseFailed(f"exit {proc.returncode}: {scrub(tail)}")
        result = {"wall_s": round(wall, 3), "max_rss_mb": round(self_mb, 1), "output": output}
        if tree_rss:
            # Sampled once a second, the tree can miss a short peak the kernel
            # counted exactly for the process itself: never report less.
            result["peak_rss_mb"] = round(max((peak_tree or 0) / 1024, self_mb), 1)
        if prof is not None:
            result["profile"] = summarize_profile(prof)
        return result

    def repeat(self, run: Callable[[int], dict], n: int | None = None) -> list[dict]:
        """`run(k)` for k in 0..n-1 (default: --runs), each returning a run's numbers."""
        return [run(k) for k in range(n or self.runs)]

    def case(
        self,
        suite: str,
        name: str,
        params: dict,
        runs: list[dict],
        *,
        label: str = "measured",
        derived: dict | None = None,
        notes: list[str] | None = None,
    ) -> dict:
        """Record a case: its parameters, every run (minus their raw output),
        the median of each number, and anything derived from them, labelled."""
        runs = [{k: v for k, v in r.items() if k != "output"} for r in runs]
        middle = sorted(runs, key=lambda r: r.get("wall_s", 0.0))[len(runs) // 2] if runs else {}
        entry = {
            "suite": suite,
            "case": name,
            "label": label,
            "params": params,
            "runs": [{k: v for k, v in r.items() if k != "profile"} for r in runs],
            "median": median_of(runs) if runs else {},
        }
        if middle.get("profile"):
            entry["profile_of_median_run"] = middle["profile"]
        if derived:
            entry["derived"] = derived
        if notes:
            entry["notes"] = notes
        self.cases.append(entry)
        shown = ", ".join(f"{k} {v:g}" for k, v in entry["median"].items() if k in ("wall_s", "fps", "peak_rss_mb"))
        self.log(f"{suite} / {name}: {shown or 'recorded'}")
        return entry

    def skip(self, suite: str, name: str, reason: str) -> None:
        self.skipped.append({"suite": suite, "case": name, "reason": scrub(reason)})
        self.log(f"{suite} / {name}: skipped -- {reason}")

    def fail(self, suite: str, name: str, error: Exception) -> None:
        self.failed.append({"suite": suite, "case": name, "error": scrub(str(error))})
        self.log(f"{suite} / {name}: FAILED -- {scrub(str(error))}")


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def ask_doctor(env: dict, work: Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "kaleidophone.cli", "doctor", "--json", "--bench-gate", "-o", str(work),
         "--canvas", str(REPO / "canvas")],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except ValueError:
        raise SystemExit(f"kaleidophone doctor did not answer in JSON (exit {proc.returncode}):\n{proc.stderr[-2000:]}") from None


def git_state() -> dict:
    def git(*args: str) -> str | None:
        try:
            proc = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return proc.stdout.strip() if proc.returncode == 0 else None

    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": git("rev-parse", "--short=12", "HEAD"), "dirty": bool(status) if status is not None else None}


def toolchain_tag(toolchain: dict) -> str:
    """'rosetta' when any tool runs translated, else the host's architecture."""
    tools = [toolchain.get(name) or {} for name in ("python", "ffmpeg", "node")]
    if any(t.get("translated") for t in tools):
        return "rosetta"
    return (toolchain.get("host") or {}).get("arch") or "unknown"


def build_document(bench: Bench, *, suite: str, gate: dict, overridden: bool, started: float, version: str) -> dict:
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return {
        "schema": SCHEMA,
        "suite": suite,
        "created_utc": created.isoformat().replace("+00:00", "Z"),
        "label": "measured" if gate.get("passed") and not overridden else "measured, ungated: not a baseline",
        "statistic": "median",
        "runs_per_case": bench.runs,
        "kaleidophone": {"version": version, **git_state()},
        "toolchain_tag": toolchain_tag(bench.toolchain),
        "toolchain": bench.toolchain,
        "gate": {**gate, "overridden": overridden},
        "cases": bench.cases,
        "skipped": bench.skipped,
        "failed": bench.failed,
        "wall_s": round(time.perf_counter() - started, 1),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", required=True, choices=[*suites.SUITES, "all"])
    ap.add_argument("--runs", type=int, help=f"Runs per case; the median is reported (default {DEFAULT_RUNS}, quick 1).")
    ap.add_argument("--out", help="The result file, or a folder for it (default benchmarks/results/; with "
                    "--ungated, the system's temporary folder).")
    ap.add_argument("--work", help="Where fixtures and renders go (default: a temporary folder).")
    ap.add_argument("--keep", action="store_true", help="Keep the work folder afterwards.")
    ap.add_argument("--ungated", action="store_true", help="Run even when doctor's bench gate refuses; the result says so.")
    ap.add_argument("--wait-quiet", type=float, default=0.0, metavar="MINUTES",
                    help="When the gate refuses for load or battery, ask again every minute for up to this long "
                         "(an unattended start, right after closing everything else).")
    ap.add_argument("--workers", help="canvas-knee: worker counts, e.g. 1,2,4,8 (default 1..10).")
    ap.add_argument("--pieces", help="canvas-knee: which pieces (default every frozen piece and the template).")
    ap.add_argument("--private-master", action="append", default=[], metavar="DIR",
                    help="aac-vs-aac_at: a folder of private masters (WAV/AIFF); results keep numbers only.")
    ap.add_argument("--private-reel", action="append", default=[], metavar="FILE",
                    help="loop-seam: a private looping reel; results keep numbers only.")
    args = ap.parse_args(argv)
    if args.runs is not None and args.runs < 1:
        ap.error("--runs must be at least 1")
    # Checked now, not hours into a run: a typo here would cost the night.
    for folder in args.private_master:
        if not Path(folder).expanduser().is_dir():
            ap.error(f"--private-master {folder}: not a folder")
    for reel in args.private_reel:
        if not Path(reel).expanduser().is_file():
            ap.error(f"--private-reel {reel}: not a file")
    return args


def wait_for_gate(env: dict, work: Path, minutes: float) -> dict:
    """Doctor's report, asked again every GATE_POLL_S while the gate refuses
    for load or power, for up to `minutes`. A failing check isn't waited on:
    it won't fix itself."""
    deadline = time.monotonic() + max(0.0, minutes) * 60.0
    while True:
        _, report = ask_doctor(env, work)
        gate = report.get("gate") or {}
        reasons = gate.get("reasons") or []
        if gate.get("passed") or time.monotonic() >= deadline or any(r.startswith("failing checks") for r in reasons):
            return report
        print(f"[bench] waiting for a quiet Mac: {'; '.join(reasons)}", flush=True)
        time.sleep(GATE_POLL_S)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="kp-bench-"))
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO / "src"), os.environ.get("PYTHONPATH")]))}
    try:
        report = wait_for_gate(env, work, args.wait_quiet)
        gate = report.get("gate") or {"passed": False, "reasons": ["doctor gave no gate"]}
        if not gate.get("passed"):
            print("kaleidophone doctor --bench-gate refused: " + "; ".join(gate.get("reasons") or []), file=sys.stderr)
            if not args.ungated:
                print("Not benchmarking. Re-run when the machine is quiet, or pass --ungated for a smoke test "
                      "(its result says it is not a baseline).", file=sys.stderr)
                return EXIT_GATE_REFUSED
            print("--ungated: running anyway; the result is labelled as not a baseline.", file=sys.stderr)
        bench = Bench(args, work, report.get("toolchain") or {})
        names = [s for s in suites.SUITES if s != "quick"] if args.suite == "all" else [args.suite]
        for name in names:
            bench.log(f"suite {name} ({bench.runs} run{'s' if bench.runs != 1 else ''} a case)")
            # One suite going wrong costs that suite, never the cases the others recorded.
            try:
                suites.SUITES[name](bench)
            except KeyboardInterrupt:
                bench.fail(name, "suite", RuntimeError("interrupted: the cases before this are what was measured"))
                break
            except Exception as exc:
                bench.fail(name, "suite", exc)
        doc = build_document(bench, suite=args.suite, gate=gate, overridden=not gate.get("passed"),
                             started=started, version=report.get("version") or "unknown")
        problems = hygiene_problems(doc, private_tokens())
        if problems:
            # A night's numbers aren't thrown away: they wait in the work folder, which is kept.
            refused = work / "refused-result.json"
            refused.write_text(json.dumps(doc, indent=2) + "\n")
            args.keep = True
            print("refusing to write the result: it names a path or this machine:\n  " + "\n  ".join(problems)
                  + f"\nIt is in {refused} -- fix the field, then copy it by hand.", file=sys.stderr)
            return EXIT_HYGIENE
        # A smoke test (--ungated) backs nothing, so by default it isn't put where baselines go.
        default = HERE / "results" if gate.get("passed") else Path(tempfile.gettempdir()) / "kp-bench"
        out = Path(args.out) if args.out else default
        if out.suffix != ".json":
            stamp = doc["created_utc"].replace(":", "").replace("-", "")
            out = out / f"{args.suite}-{stamp}-{doc['toolchain_tag']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2) + "\n")
        bench.log(f"{len(bench.cases)} cases, {len(bench.skipped)} skipped, {len(bench.failed)} failed, "
                  f"{doc['wall_s']:.0f} s -> {out.name}")
        print(str(out))
        return 1 if bench.failed else 0
    finally:
        if not args.keep and not args.work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
