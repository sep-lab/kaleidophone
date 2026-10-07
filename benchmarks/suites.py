"""
The benchmark suites. Each is a function of the Bench (run.py) that records
cases; docs/BENCHMARKS.md says what each one answers and how to read it.

    canvas-knee    each frozen piece's synthetic twin and the template, 10 s
                   at 1080x1920, at 1..10 workers: fps, and peak RSS of the
                   whole tree (node, Chromium, ffmpeg) per worker
    footage        examples/demo's 37 cuts at 640x360 and 1280x720, the same
                   edit cut from 24-megapixel photos, and a frame program
                   over the 720p render at 1, 2 and 4 workers
    deliver        a synthetic master through 3 platforms x 2 endings
    aac-vs-aac_at  one delivery with ffmpeg's aac and with AudioToolbox's
                   aac_at: wall time, guard rounds, delivered LUFS and true
                   peak -- a synthetic master, and any --private-master
    loop-seam      SSIM between a loop's last frame and its first, against
                   its frame-to-frame SSIM, for synthetic loops (seamless,
                   drifting, cut, cross-faded) and any --private-reel
    long-form      a 23-minute synthetic master through `envelope` (wall,
                   RSS), a 60 s canvas render from its pack extrapolated to
                   the full length, and the delivery's guard loop at full length
    quick          every suite in miniature: under five minutes, a smoke test

Run as a script, this file is also the two small helpers the suites start as
processes of their own: `frames-job` (a frame program through
frames.engine.run_workers, whose workers need module-level functions) and
`deliver-codec` (`kaleidophone deliver` with its audio codec swapped).
"""

from __future__ import annotations

import functools
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import fixtures
import yaml

from kaleidophone.render._ffmpeg_util import probe_stream, run_measure

HERE = Path(__file__).resolve().parent
FROZEN = ("hamechi-manzor-dare", "minus", "same-as-you", "should-i")
PIECES = (*FROZEN, "template")
DEMO_STATIONS = {"amber-room": 0.08, "fire-leak": 0.02, "gold-hour": 0.12}
KNEE_SHARE = 0.95  # the knee: the fewest workers within 5% of the best fps
RESULT_MARK = "KP_BENCH_RESULT "  # the line a helper process answers on, whatever else it prints


def _ints(text: str | None, default: list[int]) -> list[int]:
    if not text:
        return default
    return sorted({int(x) for x in text.split(",") if x.strip()})


def _render_fps(output: str) -> float | None:
    """render.mjs's own rate, from its DONE line: frames over the time since Chromium started."""
    match = re.search(r"in \d+s \(([\d.]+) fps\)", output)
    return float(match.group(1)) if match else None


def _profile_split(profile: dict | None, codec: str = "aac") -> dict:
    """A deliver run's profile, as the numbers worth comparing: ms encoding
    audio, ms measuring, how many encodes."""
    profile = profile or {}
    encode = {k: v for k, v in profile.items() if f"a={codec}" in k.split("|")}
    measure = {k: v for k, v in profile.items() if "null" in k.split("|")}
    return {
        "audio_encodes": sum(v["calls"] for v in encode.values()),
        "audio_encode_ms": round(sum(v["ms"] for v in encode.values()), 1),
        "measure_ms": round(sum(v["ms"] for v in measure.values()), 1),
    }


def _manifest(out: Path) -> dict:
    found = sorted(out.glob("*.delivery.json"))
    return json.loads(found[0].read_text()) if found else {}


def _delivered(manifest: dict) -> dict:
    """The numbers a delivery measured on its own files: the worst true peak,
    the loudness range, the master's final gain."""
    measured = [a["measured"] for a in manifest.get("artifacts", []) if a.get("kind") == "video" and a.get("measured")]
    peaks = [m["true_peak_dbtp"] for m in measured if m.get("true_peak_dbtp") is not None]
    lufs = [m["lufs"] for m in measured if m.get("lufs") is not None]
    master = manifest.get("master") or {}
    out = {"files": len(measured)}
    if peaks:
        out["true_peak_dbtp_max"] = max(peaks)
    if lufs:
        out["lufs_mean"] = round(statistics.fmean(lufs), 2)
    if master.get("gain_db") is not None:
        out["gain_db"] = master["gain_db"]
    if master.get("lufs") is not None:
        out["master_lufs"] = master["lufs"]
    return out


def _sheet(path: Path, sheet: dict) -> Path:
    path.write_text(yaml.safe_dump(sheet, sort_keys=False))
    return path


# --------------------------------------------------------------------------
# canvas-knee
# --------------------------------------------------------------------------
def _song_pack(b, piece: str) -> Path:
    """The piece's synthetic twin as a song pack (canvas/out/songs/, where synth.mjs writes it)."""
    subprocess.run([b.node, "tools/synth.mjs", piece], cwd=b.canvas, check=True, capture_output=True, env=b.env)
    return b.canvas / "out" / "songs" / f"{piece}.songpack.json"


def _window(b, piece: str, dur: float) -> tuple[float, float]:
    """(t0, fps): the gallery's t0, moved back if the twin ends within `dur` of it."""
    spec = json.loads((b.canvas / "pieces" / piece / "piece.json").read_text())
    twin = json.loads((b.canvas / "pieces" / piece / "synthetic.json").read_text())
    t0 = float((spec.get("gallery") or {}).get("t0") or 0.0)
    end = float(twin.get("dur") or t0 + dur)
    return max(0.0, min(t0, end - dur - 1.0)), float((spec.get("render") or {}).get("fps") or 24)


def _render(b, piece: str, pack: Path, out: Path, *, t0: float, dur: float, workers: int, size=(1080, 1920)) -> dict:
    """One silent render with --profile: wall, fps, peak RSS of the tree, the per-frame split."""
    argv = [
        b.node, "tools/render.mjs", piece, "--song", str(pack), "--t0", f"{t0:g}", "--dur", f"{dur:g}",
        "--w", str(size[0]), "--h", str(size[1]), "--workers", str(workers), "--profile", "--out", str(out),
    ]
    m = b.measure(argv, cwd=b.canvas, tree_rss=True)
    sidecar = json.loads(Path(f"{out}.json").read_text())
    frames = sidecar["frames"]["rendered"]
    summary = (sidecar.get("profile") or {}).get("summary") or {}
    used = sidecar.get("workers") or workers
    run = {
        "wall_s": m["wall_s"],
        "fps": round(frames / m["wall_s"], 3),
        "fps_render": _render_fps(m["output"]),
        "peak_rss_mb": m.get("peak_rss_mb"),
        "rss_per_worker_mb": round(m["peak_rss_mb"] / used, 1) if m.get("peak_rss_mb") else None,
        "workers_used": used,
        "frames": frames,
        "draw_ms": (summary.get("draw") or {}).get("mean"),
        "capture_ms": (summary.get("capture") or {}).get("mean"),
        "sink_wait_ms": (summary.get("sink_wait") or {}).get("mean"),
        "stateful": bool(sidecar.get("stateful")),
        "chromium": (sidecar.get("tools") or {}).get("chromium"),
    }
    for f in (out, Path(f"{out}.json")):
        f.unlink(missing_ok=True)
    return run


def canvas_knee(b) -> None:
    suite = "canvas-knee"
    pieces = b.args.pieces.split(",") if b.args.pieces else (["template"] if b.quick else list(PIECES))
    problem = b.canvas_problem()
    if problem:
        for piece in pieces:
            b.skip(suite, piece, problem)
        return
    counts = _ints(b.args.workers, [1, 2] if b.quick else list(range(1, 11)))
    dur = 2.0 if b.quick else 10.0
    folder = b.work / "knee"
    folder.mkdir(parents=True, exist_ok=True)
    for piece in pieces:
        try:
            pack = _song_pack(b, piece)
            t0, fps = _window(b, piece, dur)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            b.fail(suite, piece, exc)
            continue
        runs: dict[int, list[dict]] = {w: [] for w in counts}
        stateful = False
        # Runs outermost: drift over the night (heat, a backup waking up) falls on every count alike.
        for k in range(b.runs):
            for w in counts:
                if stateful and w > 1:
                    continue
                try:
                    run = _render(b, piece, pack, folder / f"{piece}-w{w}.mp4", t0=t0, dur=dur, workers=w)
                except Exception as exc:
                    b.fail(suite, f"{piece} w{w} run {k + 1}", exc)
                    continue
                stateful = stateful or run["stateful"]
                runs[w].append(run)
        best = []
        for w in counts:
            if not runs[w]:
                continue
            chromium = runs[w][0].pop("chromium", None)
            for r in runs[w][1:]:
                r.pop("chromium", None)
            params = {"piece": piece, "workers": w, "dur_s": dur, "size": "1080x1920", "fps": fps, "t0": t0,
                      "song": "synthetic twin", "stateful": runs[w][0]["stateful"], "chromium": chromium}
            entry = b.case(suite, f"{piece} w{w}", params, runs[w])
            best.append((w, entry["median"].get("fps", 0.0)))
        if stateful and len(counts) > 1:
            b.skip(suite, f"{piece} w>1", "stateful: it renders in one worker whatever --workers says")
        if len(best) > 1:
            top = max(fps for _, fps in best)
            knee = min(w for w, fps in best if fps >= KNEE_SHARE * top)
            b.case(suite, f"{piece} knee", {"piece": piece, "share_of_best": KNEE_SHARE}, [], label="derived",
                   derived={"knee_workers": knee, "best_fps": top, "fps_by_workers": dict(best)},
                   notes=["the fewest workers within 5% of the best median fps, from the cases above"])


# --------------------------------------------------------------------------
# footage
# --------------------------------------------------------------------------
def _brief_at(source: Path, target: Path, size: tuple[int, int], photos: dict | None = None) -> Path:
    data = yaml.safe_load(source.read_text())
    data["output"]["resolution"] = list(size)
    if photos:
        for station in data["stations"]:
            station["media_dir"] = str(photos[station["name"]])
    target.write_text(yaml.safe_dump(data, sort_keys=False))
    return target


def _silent_case(b, suite: str, name: str, brief: Path, tag: str, params: dict, notes=None) -> Path | None:
    folder = brief.parent
    edl, out = folder / f"edl-{tag}.json", folder / f"silent-{tag}.mp4"
    try:
        b.measure(b.cli("compose", str(brief), "-o", str(edl)))
        cuts = len(json.loads(edl.read_text())["cuts"])

        def once(k: int) -> dict:
            m = b.measure(b.cli("silent", str(edl), str(brief), "-o", str(out)), tree_rss=True, profile=True)
            return {**m, "mb": round(out.stat().st_size / 1e6, 1)}

        runs = b.repeat(once)
    except Exception as exc:
        b.fail(suite, name, exc)
        return None
    if cuts != 37 and "demo" in name:
        notes = [*(notes or []), f"{cuts} cuts: the README's figures were measured on 37"]
    b.case(suite, name, {**params, "cuts": cuts}, runs, notes=notes)
    return out


def footage(b) -> None:
    suite = "footage"
    folder = b.work / "demo"
    try:
        brief = fixtures.demo_fixtures(b.python, b.repo, folder)
    except Exception as exc:
        b.fail(suite, "fixtures", exc)
        return
    sizes = [(640, 360)] if b.quick else [(640, 360), (1280, 720)]
    renders = {}
    for w, h in sizes:
        target = _brief_at(brief, folder / f"brief-{h}p.yaml", (w, h))
        renders[h] = _silent_case(b, suite, f"demo {h}p silent", target, f"{h}p",
                                  {"resolution": f"{w}x{h}", "photos": "examples/demo (320x240)"})
    count = 1 if b.quick else 4
    try:
        photos = fixtures.write_photos(b.work / "photos24", DEMO_STATIONS, count)
    except Exception as exc:
        b.fail(suite, "24 MP photos", exc)
        photos = None
    if photos:
        w, h = sizes[-1]
        target = _brief_at(brief, folder / f"brief-24mp-{h}p.yaml", (w, h), photos)
        _silent_case(b, suite, f"24 MP photos {h}p silent", target, f"24mp-{h}p",
                     {"resolution": f"{w}x{h}", "photos": f"{count * len(DEMO_STATIONS)} procedural 6000x4000 JPEGs"},
                     notes=["the demo's edit, every photo a 24-megapixel JPEG: what decoding camera files costs"])
    h = sizes[-1][1]
    source = renders.get(h)
    if source is None:
        b.skip(suite, "frames", "no silent render to run a frame program over")
        return
    frames = 48 if b.quick else 240
    for workers in [1] if b.quick else [1, 2, 4]:
        name = f"frames {h}p w{workers}"
        out = b.work / "frames" / f"w{workers}"
        argv = [b.python, str(HERE / "suites.py"), "frames-job", str(source), str(out), str(sizes[-1][0]), str(h),
                "24", str(frames), str(workers)]

        def once(k: int, argv=argv, out=out) -> dict:
            shutil.rmtree(out, ignore_errors=True)
            m = b.measure(argv, tree_rss=True)
            marked = [line for line in m["output"].splitlines() if line.startswith(RESULT_MARK)]
            if not marked:
                raise RuntimeError("the frames job printed no result")
            inner = json.loads(marked[-1][len(RESULT_MARK) :])
            return {**{k: v for k, v in m.items() if k != "output"}, **inner}

        try:
            runs = b.repeat(once)
        except Exception as exc:
            b.fail(suite, name, exc)
            continue
        b.case(suite, name, {"resolution": f"{sizes[-1][0]}x{h}", "frames": frames, "workers": workers,
                             "program": "MemoryCanvas + GrainBank + feedback_echo", "encoder": "x264 medium, 2 threads"},
               runs)


def frames_job(source: str, out_dir: str, width: str, height: str, fps: str, frames: str, workers: str) -> dict:
    """A frame program over `source` through run_workers: the engine's own
    read / program / write split, summed over workers, per frame."""
    from kaleidophone.frames.engine import RenderJob, run_workers

    w, h, n = int(width), int(height), int(frames)
    job = RenderJob(source=source, out_dir=out_dir, end_frame=n, size=(w, h), fps=float(fps), tag="bench")
    beats = [i * 0.5 for i in range(int(n / float(fps) / 0.5) + 2)]
    started = time.perf_counter()
    results = run_workers(job, _program, int(workers), make_state=functools.partial(_make_state, w, h),
                          env={"beats": beats})
    took = time.perf_counter() - started
    done = sum(r.frames for r in results)
    return {
        "render_s": round(took, 3),
        "fps_render": round(done / took, 3),
        "read_ms": round(1000 * sum(r.read_s for r in results) / done, 2),
        "program_ms": round(1000 * sum(r.program_s for r in results) / done, 2),
        "write_ms": round(1000 * sum(r.write_s for r in results) / done, 2),
    }


def _make_state(width: int, height: int) -> dict:
    from kaleidophone.frames.effects import GrainBank, MemoryCanvas

    return {
        "memory": MemoryCanvas(width, height, refresh=0.3, pale=0.5, feather=3.0, seed=1),
        "grain": GrainBank(width, height, seed=2),
        "prev": None,
    }


def _program(frame, t, env, state):
    from kaleidophone.frames.effects import feedback_echo, pulse

    out = state["memory"](frame, t, beat=pulse(t, env["beats"]))
    out = state["grain"](out, 0.05)
    out = feedback_echo(state["prev"], out, zoom=1.0, mix=0.3)
    state["prev"] = out
    return out


# --------------------------------------------------------------------------
# deliver
# --------------------------------------------------------------------------
def deliver(b) -> None:
    suite = "deliver"
    folder = b.work / "deliver"
    body_s, ending_s = (4.0, 2.0) if b.quick else (24.0, 6.0)
    total = body_s + ending_s
    platforms = ["instagram-reel"] if b.quick else ["instagram-reel", "tiktok", "youtube-short"]
    name = f"{len(platforms)} platform{'s' if len(platforms) > 1 else ''} x 2 endings"
    try:
        parts = fixtures.write_parts(b.ffmpeg, folder, body_s=body_s, ending_s=ending_s)
        fixtures.write_master(folder / "master.wav", total + 1.0, seed=1)
    except Exception as exc:
        b.fail(suite, name, exc)
        return
    sheet = _sheet(folder / "sheet.yaml", {
        "title": "kp bench", "size": "1080x1920", "audio": "master.wav", "fps": 24,
        "gain": {"mode": "auto"},
        "cuts": [{
            "name": "reel", "t0": 0, "dur": total, "platforms": platforms, "body": parts["body"], "at": body_s,
            "endings": [{"name": n, "file": f} for n, f in parts["endings"].items()],
        }],
    })

    def once(k: int) -> dict:
        out = folder / f"out-{k}"
        shutil.rmtree(out, ignore_errors=True)
        m = b.measure(b.cli("deliver", str(sheet), "-o", str(out)), profile=True)
        numbers = _delivered(_manifest(out))
        split = _profile_split(m.get("profile"))
        files = max(1, numbers.get("files", 1))
        shutil.rmtree(out, ignore_errors=True)
        return {**m, **numbers, **split, "guard_rounds": split["audio_encodes"] // files}

    try:
        runs = b.repeat(once)
    except Exception as exc:
        b.fail(suite, name, exc)
        return
    b.case(suite, name, {"platforms": platforms, "endings": 2, "seconds": total, "size": "1080x1920",
                         "gain": "auto", "master": "synthetic, 24-bit 48 kHz, -0.3 dBFS sample peak"}, runs)


# --------------------------------------------------------------------------
# aac-vs-aac_at
# --------------------------------------------------------------------------
AUDIO_SUFFIXES = (".wav", ".aif", ".aiff", ".flac")


def _private_masters(dirs: list[str]) -> list[Path]:
    found = []
    for d in dirs:
        found += sorted(p for p in Path(d).expanduser().iterdir() if p.suffix.lower() in AUDIO_SUFFIXES)
    return found


def _private_link(folder: Path, k: int, source: Path) -> Path:
    """A private input under a name of ours, `private-<k>.<ext>`: whatever a
    tool prints about it then names the number, never the song."""
    folder.mkdir(parents=True, exist_ok=True)
    link = folder / f"private-{k}{source.suffix.lower()}"
    link.unlink(missing_ok=True)
    link.symlink_to(Path(source).expanduser().resolve())
    return link


def _withheld(b, suite: str, name: str, exc: Exception) -> None:
    """A private case failed: the reason goes to the terminal, never into the result."""
    b.log(f"{suite} / {name}: {exc}")
    b.fail(suite, name, RuntimeError("failed on a private input; the reason was printed, not recorded"))


def aac_vs_aac_at(b) -> None:
    suite = "aac-vs-aac_at"
    import soundfile as sf

    encoders = ((b.toolchain.get("ffmpeg") or {}).get("encoders") or {})
    codecs = ["aac"] + (["aac_at"] if encoders.get("aac_at") else [])
    if len(codecs) == 1:
        b.skip(suite, "aac_at", "this ffmpeg has no aac_at (AudioToolbox is macOS only): aac alone is measured")
    folder = b.work / "aac"
    masters = []
    try:
        folder.mkdir(parents=True, exist_ok=True)
        masters.append(("synthetic", fixtures.write_master(folder / "synthetic.wav", 20.0 if b.quick else 180.0, seed=3)))
    except Exception as exc:
        b.fail(suite, "synthetic", exc)
    try:
        for k, source in enumerate(_private_masters(b.args.private_master), start=1):
            masters.append((f"private-{k}", _private_link(folder, k, source)))
    except Exception as exc:
        _withheld(b, suite, "private masters", exc)
    for label, master in masters:
        private = label.startswith("private-")
        try:
            seconds = sf.info(str(master)).duration
            cut = math.floor((seconds - 0.1) * 24) / 24
            picture = fixtures.write_picture(b.ffmpeg, folder / f"{label}-picture.mp4", cut + 1.0, size=(270, 480),
                                             crf=30, noise=0)
            sheet = _sheet(folder / f"{label}.yaml", {
                "title": "kp bench", "silent": picture.name, "audio": master.name, "fps": 24,
                "gain": {"mode": "auto"}, "cuts": [{"name": "film", "t0": 0, "dur": cut}],
            })
        except Exception as exc:
            if private:
                _withheld(b, suite, label, exc)
            else:
                b.fail(suite, label, exc)
            continue
        medians = {}
        for codec in codecs:

            def once(k: int, codec=codec, sheet=sheet) -> dict:
                out = folder / f"out-{k}"
                shutil.rmtree(out, ignore_errors=True)
                m = b.measure([b.python, str(HERE / "suites.py"), "deliver-codec", codec, str(sheet), str(out)],
                              profile=True)
                numbers = _delivered(_manifest(out))
                split = _profile_split(m.get("profile"), codec)
                shutil.rmtree(out, ignore_errors=True)
                return {**m, **numbers, **split, "guard_rounds": split["audio_encodes"]}

            try:
                runs = b.repeat(once)
            except Exception as exc:
                if private:
                    _withheld(b, suite, f"{label} {codec}", exc)
                else:
                    b.fail(suite, f"{label} {codec}", exc)
                continue
            entry = b.case(suite, f"{label} {codec}", {"master": label, "minutes": round(seconds / 60, 1),
                                                       "codec": codec, "bitrate": "256k", "gain": "auto"}, runs)
            medians[codec] = entry["median"]
        if len(medians) == 2:
            a, at = medians["aac"], medians["aac_at"]
            derived = {k: round(at[k] - a[k], 3) for k in ("lufs_mean", "true_peak_dbtp_max", "gain_db") if k in a and k in at}
            if a.get("audio_encode_ms") and at.get("audio_encode_ms"):
                derived["encode_time_ratio"] = round(at["audio_encode_ms"] / a["audio_encode_ms"], 3)
            b.case(suite, f"{label} aac_at - aac", {"master": label}, [], label="derived", derived=derived,
                   notes=["aac_at minus aac, from the medians above (the ratio is aac_at over aac)"])


def deliver_codec(codec: str, sheet: str, out: str) -> int:
    """`kaleidophone deliver` with the audio codec swapped -- for this
    benchmark only: deliver.py hard-codes aac until deliver v2 makes it a
    setting (docs/BENCHMARKS.md)."""
    from kaleidophone import cli
    from kaleidophone.render import deliver as d

    if codec != "aac":
        build = d._encode_argv

        def swapped(*args, **kwargs):
            argv = build(*args, **kwargs)
            i = argv.index("-c:a")
            if argv[i + 1] != "aac":
                raise RuntimeError(f"deliver's encode no longer reads -c:a aac (it reads {argv[i + 1]}): update the benchmark")
            return [*argv[: i + 1], codec, *argv[i + 2 :]]

        d._encode_argv = swapped
    return cli.main(["deliver", sheet, "-o", out])


# --------------------------------------------------------------------------
# loop-seam
# --------------------------------------------------------------------------
def ssim(ffmpeg: str, video: Path, a: int, b: int) -> float:
    """SSIM (all planes) between frames `a` and `b` of one video."""
    graph = (
        f"[0:v]select=eq(n\\,{a}),setpts=N/TB[a];"
        f"[1:v]select=eq(n\\,{b}),setpts=N/TB[b];"
        "[a][b]ssim"
    )
    log = run_measure(ffmpeg, ["-i", str(video), "-i", str(video), "-filter_complex", graph,
                               "-frames:v", "1", "-f", "null", "-"])
    match = re.search(r"All:([\d.]+)", log)
    if not match:
        raise RuntimeError("ffmpeg's ssim filter reported nothing")
    return float(match.group(1))


def frame_count(video: Path) -> int:
    count = probe_stream(str(video), "v:0", "nb_read_packets", count_packets=True)
    if count is None or not count.isdigit():
        raise RuntimeError("ffprobe could not count the video's frames")
    return int(count)


def seam_numbers(ffmpeg: str, video: Path, frames: int) -> dict:
    """The seam (last frame against the first) and three ordinary steps
    (frame k against k + 1, at a quarter, half and three quarters)."""
    seam = ssim(ffmpeg, video, frames - 1, 0)
    steps = [ssim(ffmpeg, video, k, k + 1) for k in (frames // 4, frames // 2, 3 * frames // 4)]
    interior = statistics.median(steps)
    return {"seam_ssim": round(seam, 5), "interior_ssim": round(interior, 5), "interior_min": round(min(steps), 5),
            "seam_over_interior": round(seam / interior, 5) if interior else None}


def loop_seam(b) -> None:
    suite = "loop-seam"
    size, frames = ((270, 480), 48) if b.quick else ((720, 1280), 192)
    kinds = ("seamless", "cut") if b.quick else fixtures.LOOP_KINDS
    for kind in kinds:
        try:
            video = fixtures.write_loop(b.ffmpeg, b.work / "loops" / f"{kind}.mp4", kind, frames=frames, size=size)
            numbers = seam_numbers(b.ffmpeg, video, frames)
        except Exception as exc:
            b.fail(suite, kind, exc)
            continue
        # Deterministic: one run says it all.
        b.case(suite, kind, {"size": f"{size[0]}x{size[1]}", "frames": frames, "fps": 24, "loop": kind}, [numbers])
    for k, reel in enumerate(b.args.private_reel, start=1):
        try:
            video = _private_link(b.work / "loops", k, Path(reel))
            n = frame_count(video)
            numbers = seam_numbers(b.ffmpeg, video, n)
        except Exception as exc:
            _withheld(b, suite, f"private-{k}", exc)
            continue
        b.case(suite, f"private-{k}", {"frames": n, "loop": "private reel"}, [numbers])


# --------------------------------------------------------------------------
# long-form
# --------------------------------------------------------------------------
def long_form(b) -> None:
    suite = "long-form"
    folder = b.work / "long"
    full = 120.0 if b.quick else 23 * 60.0
    minutes = round(full / 60, 1)
    try:
        wav = fixtures.write_master(folder / "long.wav", full, seed=2)
    except Exception as exc:
        b.fail(suite, "fixtures", exc)
        return
    pack = folder / "long.songpack.json"

    def envelope(k: int) -> dict:
        return b.measure(b.cli("envelope", str(wav), "-o", str(pack)), tree_rss=True, profile=True)

    try:
        runs = b.repeat(envelope)
        b.case(suite, f"envelope {minutes:g} min", {"minutes": minutes, "rate": 48000, "bits": 24, "channels": 2,
                                                    "master": "synthetic"}, runs)
    except Exception as exc:
        b.fail(suite, f"envelope {minutes:g} min", exc)
    problem = b.canvas_problem()
    if problem or not pack.exists():
        b.skip(suite, "render", problem or "no song pack: envelope failed")
    else:
        seg, t0 = (5.0, 30.0) if b.quick else (60.0, 600.0)
        workers = 2  # render.mjs's default today
        try:
            runs = b.repeat(lambda k: _render(b, "template", pack, folder / "render.mp4", t0=t0, dur=seg, workers=workers))
            for r in runs:
                r.pop("chromium", None)
            wall = statistics.median(r["wall_s"] for r in runs)
            b.case(suite, f"template {seg:g} s of {minutes:g} min", {"piece": "template", "dur_s": seg, "t0": t0,
                                                                     "workers": workers, "size": "1080x1920"}, runs,
                   derived={"full_length_s": round(wall * full / seg, 1), "label": "inferred",
                            "how": f"the median wall time x {full:g} / {seg:g}: a stateless piece scales with frames"})
        except Exception as exc:
            b.fail(suite, "render", exc)
    try:
        clip = fixtures.write_picture(b.ffmpeg, folder / "clip.mp4", 10.0)
        film = fixtures.write_looped_picture(b.ffmpeg, folder / "film.mp4", full + 1.0, clip, 10.0)
        sheet = _sheet(folder / "sheet.yaml", {
            "title": "kp bench", "silent": film.name, "audio": wav.name, "fps": 24, "gain": {"mode": "auto"},
            "cuts": [{"name": "film", "t0": 0, "dur": math.floor((full - 0.5) * 24) / 24}],
        })
    except Exception as exc:
        b.fail(suite, "deliver", exc)
        return

    def deliver_once(k: int) -> dict:
        out = folder / f"out-{k}"
        shutil.rmtree(out, ignore_errors=True)
        m = b.measure(b.cli("deliver", str(sheet), "-o", str(out)), profile=True)
        numbers = _delivered(_manifest(out))
        split = _profile_split(m.get("profile"))
        shutil.rmtree(out, ignore_errors=True)
        return {**m, **numbers, **split, "guard_rounds": split["audio_encodes"]}

    try:
        runs = b.repeat(deliver_once)
        b.case(suite, f"deliver guard {minutes:g} min", {"minutes": minutes, "size": "1080x1920", "gain": "auto",
                                                         "picture": "a 10 s clip stream-copied to length"}, runs)
    except Exception as exc:
        b.fail(suite, "deliver", exc)


# --------------------------------------------------------------------------
# quick, and the registry
# --------------------------------------------------------------------------
def quick(b) -> None:
    for suite in (canvas_knee, footage, deliver, aac_vs_aac_at, loop_seam, long_form):
        suite(b)


SUITES = {
    "canvas-knee": canvas_knee,
    "footage": footage,
    "deliver": deliver,
    "aac-vs-aac_at": aac_vs_aac_at,
    "loop-seam": loop_seam,
    "long-form": long_form,
    "quick": quick,
}


if __name__ == "__main__":
    command, *rest = sys.argv[1:]
    if command == "frames-job":
        print(RESULT_MARK + json.dumps(frames_job(*rest)), flush=True)
    elif command == "deliver-codec":
        raise SystemExit(deliver_codec(*rest))
    else:
        raise SystemExit(f"unknown command {command!r}")
