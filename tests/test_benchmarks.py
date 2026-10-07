"""benchmarks/: the harness's own logic, without running a benchmark.

What must hold whatever the numbers are: a result names no host, no user
and no path (the hygiene check finds them, and the harness refuses to write
a file that has one); the bench gate is honoured unless --ungated, and an
ungated result says it is not a baseline; medians are medians; and the
fixtures are pure functions of their arguments. None of this needs ffmpeg,
node or a Chromium -- CI runs it with none of them.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

BENCH = Path(__file__).resolve().parents[1] / "benchmarks"


def _load(name: str):
    if str(BENCH) not in sys.path:
        sys.path.insert(0, str(BENCH))
    spec = importlib.util.spec_from_file_location(f"kp_bench_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = _load("run")
suites = _load("suites")
fixtures = _load("fixtures")

TOOLCHAIN = {
    "host": {"arch": "arm64", "cpu": "Apple M1 Pro", "model": "MacBookPro18,3", "os": "macOS 15.7",
             "cores": {"logical": 10, "performance": 8, "efficiency": 2}, "memory_gb": 16.0},
    "python": {"version": "3.11.10", "arch": "x86_64", "translated": True, "where": "/usr/local", "venv": True},
    "ffmpeg": {"found": True, "version": "7.1", "arch": "x86_64", "translated": True, "where": "/usr/local",
               "binary_arches": ["x86_64"], "encoders": {"aac_at": True}},
    "node": {"found": True, "version": "24.19.0", "arch": "x86_64", "translated": True, "where": "/usr/local"},
    "chromium": {"playwright_core": "1.56.1", "expected": {"chromium-headless-shell": "1194"}, "override": None},
}


# --- hygiene -----------------------------------------------------------------


def test_a_clean_result_passes():
    doc = {"schema": "kp-bench/1", "toolchain": TOOLCHAIN, "cases": [{"case": "minus w4", "params": {"size": "1080x1920"},
           "profile_of_median_run": {"loop|vf|scale|v=libx264": {"calls": 37, "ms": 9000.0}}}]}
    assert run.hygiene_problems(doc, ["sepehr-laptop", "someone"]) == []


@pytest.mark.parametrize(
    "value",
    [
        "/Users/someone/Music/master.wav",
        "/home/someone/out",
        "/tmp",
        "relative/to/a/folder and /var/folders/xy/T/kp-bench-1/x.mp4",
        "~/masters",
        "C:\\Users\\someone\\master.wav",
        "C:/Users/someone",
        "exit 1: could not open \\\\server\\share",
        "out-0/bounces/reel.mp4 is missing",
    ],
)
def test_a_path_anywhere_is_found(value):
    problems = run.hygiene_problems({"cases": [{"notes": [value]}]})
    assert problems == ["$.cases[0].notes[0]: looks like a path"]


@pytest.mark.parametrize("value", ["Moonfield_final_master.wav: invalid data", "a song.AIFF", "x.songpack.json", "c.yaml"])
def test_a_file_name_is_found(value):
    assert run.hygiene_problems({"error": value}) == ["$.error: names a file"]


def test_one_slash_and_ordinary_words_are_not_paths():
    doc = {"schema": "kp-bench/1", "photos": "examples/demo (320x240)", "label": "measured, ungated: not a baseline",
           "chromium": "141.0.7390.37", "kind": "concat|v=copy|a=copy", "model": "MacBookPro18,3"}
    assert run.hygiene_problems(doc) == []


def test_install_prefixes_are_not_paths_but_anything_under_them_is():
    assert run.hygiene_problems({"where": "/opt/homebrew", "w": "/usr/local", "x": "/usr"}) == []
    assert run.hygiene_problems({"where": "/opt/homebrew/bin/ffmpeg"}) == ["$.where: looks like a path"]


def test_host_and_user_names_are_found_and_never_echoed():
    doc = {"toolchain": {"host": {"name": "Sepehrs-MacBook-Pro"}}, "notes": ["run by SomeOne"]}
    problems = run.hygiene_problems(doc, ["sepehrs-macbook-pro", "someone"])
    assert problems == ["$.toolchain.host.name: holds private token #1", "$.notes[0]: holds private token #2"]
    assert not any("epehr" in p.lower() or "someone" in p.lower() for p in problems)


def test_a_leaking_key_is_named_by_position():
    problems = run.hygiene_problems({"profile": {"/Users/someone/a.mp4": {"ms": 1}}})
    assert problems == ["$.profile{key #1}: looks like a path"]
    assert "someone" not in problems[0]


def test_private_tokens_are_this_machines():
    tokens = run.private_tokens()
    assert str(Path.home()) in tokens
    assert all(len(t) >= 3 for t in tokens)


def test_scrub_removes_paths_and_private_tokens(monkeypatch):
    monkeypatch.setattr(run, "private_tokens", lambda: ["someone"])
    text = run.scrub("exit 1: /Users/someone/a b.wav: No such file | SomeOne's mac | Moonfield.wav out/x/y")
    assert "/Users" not in text and "<path>" in text and "<private>'s mac" in text
    assert "Moonfield" not in text and "<file>" in text and "out/x/y" not in text


# --- medians, profiles ----------------------------------------------------------


def test_median_of_takes_numbers_the_runs_share():
    runs = [{"wall_s": 3.0, "fps": 10, "stateful": False, "profile": {}, "peak_rss_mb": 900.0},
            {"wall_s": 1.0, "fps": 30, "stateful": False, "profile": {}, "peak_rss_mb": None},
            {"wall_s": 2.0, "fps": 20, "stateful": False, "profile": {}}]
    assert run.median_of(runs) == {"wall_s": 2.0, "fps": 20}


def test_summarize_profile_totals_by_kind(tmp_path):
    prof = tmp_path / "p.jsonl"
    lines = [{"kind": "af|ebur128|v=none|null", "wall_ms": 100.0}, {"kind": "a=aac", "wall_ms": 300.5},
             {"kind": "a=aac", "wall_ms": 200.0}]
    prof.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    assert run.summarize_profile(prof) == {"a=aac": {"calls": 2, "ms": 500.5},
                                           "af|ebur128|v=none|null": {"calls": 1, "ms": 100.0}}
    assert run.summarize_profile(tmp_path / "missing.jsonl") == {}


def test_tree_rss_of_a_process_that_isnt_there():
    assert run.tree_rss_kib(2**22 + 12345) is None


# --- the document -----------------------------------------------------------------


def bench(tmp_path, **kw) -> run.Bench:
    args = run.parse_args(["--suite", kw.pop("suite", "quick"), *kw.pop("argv", [])])
    return run.Bench(args, tmp_path, TOOLCHAIN)


def test_a_document_is_kp_bench_1_and_clean(tmp_path):
    b = bench(tmp_path)
    b.case("footage", "demo 360p silent", {"resolution": "640x360", "cuts": 37},
           [{"wall_s": 11.0, "output": "/Users/someone/should-not-survive", "profile": {"concat|v=copy": {"calls": 1, "ms": 5}}}])
    b.skip("canvas-knee", "minus", "node is not on PATH")
    doc = run.build_document(b, suite="quick", gate={"passed": True, "reasons": []}, overridden=False,
                             started=0.0, version="0.4.0")
    assert doc["schema"] == "kp-bench/1" and doc["label"] == "measured" and doc["toolchain_tag"] == "rosetta"
    assert doc["runs_per_case"] == 1 and doc["statistic"] == "median"
    case = doc["cases"][0]
    assert "output" not in case["runs"][0] and case["median"] == {"wall_s": 11.0}
    assert case["profile_of_median_run"] == {"concat|v=copy": {"calls": 1, "ms": 5}}
    assert run.hygiene_problems(doc, run.private_tokens()) == []


def test_an_ungated_document_says_it_is_not_a_baseline(tmp_path):
    doc = run.build_document(bench(tmp_path), suite="quick", gate={"passed": False, "reasons": ["busy"]},
                             overridden=True, started=0.0, version="0.4.0")
    assert doc["label"] == "measured, ungated: not a baseline" and doc["gate"]["overridden"] is True


def test_toolchain_tag():
    assert run.toolchain_tag(TOOLCHAIN) == "rosetta"
    native = {"host": {"arch": "arm64"}, "python": {"translated": False}, "ffmpeg": {}, "node": {}}
    assert run.toolchain_tag(native) == "arm64"
    assert run.toolchain_tag({}) == "unknown"


def test_runs_default_to_three_and_one_for_quick(tmp_path):
    assert bench(tmp_path, suite="footage").runs == run.DEFAULT_RUNS
    assert bench(tmp_path).runs == 1
    assert bench(tmp_path, suite="footage", argv=["--runs", "5"]).runs == 5
    with pytest.raises(SystemExit):
        run.parse_args(["--suite", "quick", "--runs", "0"])


def test_canvas_problem_says_why(tmp_path, monkeypatch):
    b = bench(tmp_path)
    b.node = None
    assert "node" in b.canvas_problem()
    b.node, b.canvas = "/usr/bin/node", tmp_path
    assert "node_modules" in b.canvas_problem()
    (tmp_path / "node_modules" / "playwright-core").mkdir(parents=True)
    assert "Chromium" in b.canvas_problem()
    b.toolchain = {**TOOLCHAIN, "chromium": {"revision": "1194"}}
    assert b.canvas_problem() is None


# --- main: the gate and the file ----------------------------------------------------


def fake_doctor(passed: bool):
    gate = {"passed": passed, "reasons": [] if passed else ["1-min load 3.00 is over 1"], "load_1m": 3.0, "power": "ac"}
    return lambda env, work: (0 if passed else 8, {"version": "0.4.0", "toolchain": TOOLCHAIN, "gate": gate})


def recording_suite(note: str):
    def suite(b):
        b.case("footage", "demo 360p silent", {"resolution": "640x360"}, [{"wall_s": 1.0}, {"wall_s": 3.0}],
               notes=[note])

    return suite


def test_the_gate_refuses_and_nothing_is_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(False))
    monkeypatch.setattr(run.suites, "SUITES", {"quick": recording_suite("x")})
    code = run.main(["--suite", "quick", "--out", str(tmp_path / "out")])
    assert code == run.EXIT_GATE_REFUSED and not (tmp_path / "out").exists()
    assert "--ungated" in capsys.readouterr().err


def test_ungated_runs_and_writes_a_clean_labelled_file(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(False))
    monkeypatch.setattr(run.suites, "SUITES", {"quick": recording_suite("fine")})
    code = run.main(["--suite", "quick", "--ungated", "--out", str(tmp_path / "out")])
    assert code == 0
    (written,) = (tmp_path / "out").iterdir()
    assert written.name.startswith("quick-") and written.name.endswith("-rosetta.json")
    doc = json.loads(written.read_text())
    assert doc["label"].endswith("not a baseline") and doc["cases"][0]["median"] == {"wall_s": 2.0}
    assert run.hygiene_problems(doc, run.private_tokens()) == []


def test_a_result_that_names_a_path_is_refused_and_kept_aside(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(True))
    monkeypatch.setattr(run.suites, "SUITES", {"quick": recording_suite("/Users/someone/leak.wav")})
    work = tmp_path / "work"
    code = run.main(["--suite", "quick", "--out", str(tmp_path / "out.json"), "--work", str(work)])
    assert code == run.EXIT_HYGIENE
    assert not (tmp_path / "out.json").exists() and (work / "refused-result.json").exists()


def test_all_runs_every_suite_but_quick(tmp_path, monkeypatch):
    ran = []
    fake = {name: (lambda b, name=name: ran.append(name)) for name in ("footage", "deliver", "quick")}
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(True))
    monkeypatch.setattr(run.suites, "SUITES", fake)
    monkeypatch.setattr(run, "parse_args", lambda argv: argparse.Namespace(
        suite="all", runs=None, out=str(tmp_path / "o.json"), work=None, keep=False, ungated=False, wait_quiet=0.0))
    assert run.main([]) == 0 and ran == ["footage", "deliver"]


def test_a_suite_that_raises_costs_only_that_suite(tmp_path, monkeypatch):
    def broken(b):
        raise FileNotFoundError(2, "No such file or directory", "/Users/someone/masters")

    suites_ = {"deliver": broken, "footage": recording_suite("fine"), "quick": broken}
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(True))
    monkeypatch.setattr(run.suites, "SUITES", suites_)
    out = tmp_path / "o.json"
    assert run.main(["--suite", "all", "--out", str(out)]) == 1
    doc = json.loads(out.read_text())
    assert [c["case"] for c in doc["cases"]] == ["demo 360p silent"]
    assert doc["failed"] == [{"suite": "deliver", "case": "suite", "error": "[Errno 2] No such file or directory: <path>"}]


def test_ctrl_c_writes_what_was_measured(tmp_path, monkeypatch):
    def interrupted(b):
        raise KeyboardInterrupt

    ran = []
    suites_ = {"footage": recording_suite("fine"), "deliver": interrupted, "loop-seam": lambda b: ran.append(1),
               "quick": interrupted}
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(True))
    monkeypatch.setattr(run.suites, "SUITES", suites_)
    out = tmp_path / "o.json"
    assert run.main(["--suite", "all", "--out", str(out)]) == 1
    doc = json.loads(out.read_text())
    assert len(doc["cases"]) == 1 and "interrupted" in doc["failed"][0]["error"] and ran == []


def test_mistyped_private_inputs_are_refused_before_anything_runs(tmp_path):
    with pytest.raises(SystemExit):
        run.parse_args(["--suite", "aac-vs-aac_at", "--private-master", str(tmp_path / "masterz")])
    with pytest.raises(SystemExit):
        run.parse_args(["--suite", "loop-seam", "--private-reel", str(tmp_path)])
    assert run.parse_args(["--suite", "aac-vs-aac_at", "--private-master", str(tmp_path)]).private_master


def test_wait_quiet_asks_again_until_the_gate_opens(tmp_path, monkeypatch):
    answers = iter([fake_doctor(False)(None, None), fake_doctor(False)(None, None), fake_doctor(True)(None, None)])
    slept = []
    monkeypatch.setattr(run, "ask_doctor", lambda env, work: next(answers))
    monkeypatch.setattr(run.time, "sleep", slept.append)
    report = run.wait_for_gate({}, tmp_path, minutes=30)
    assert report["gate"]["passed"] and slept == [run.GATE_POLL_S, run.GATE_POLL_S]


def test_wait_quiet_gives_up_at_its_deadline_and_never_waits_on_a_failing_check(tmp_path, monkeypatch):
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    monkeypatch.setattr(run, "ask_doctor", fake_doctor(False))
    assert run.wait_for_gate({}, tmp_path, minutes=0)["gate"]["passed"] is False
    failing = {"version": "0.4.0", "toolchain": {}, "gate": {"passed": False, "reasons": ["failing checks: ffmpeg"]}}
    calls = []
    monkeypatch.setattr(run, "ask_doctor", lambda env, work: calls.append(1) or (8, failing))
    run.wait_for_gate({}, tmp_path, minutes=60)
    assert calls == [1]


# --- what the suites read ------------------------------------------------------------


def test_profile_split_counts_encodes_and_measurements():
    profile = {
        "af|alimiter|aresample|v=copy|a=aac": {"calls": 12, "ms": 6000.0},
        "af|ebur128|v=none|null": {"calls": 12, "ms": 3000.0},
        "af|loudnorm|v=none|null": {"calls": 1, "ms": 900.0},
        "concat|v=copy|a=copy": {"calls": 2, "ms": 50.0},
    }
    assert suites._profile_split(profile) == {"audio_encodes": 12, "audio_encode_ms": 6000.0, "measure_ms": 3900.0}
    assert suites._profile_split(profile, "aac_at")["audio_encodes"] == 0
    assert suites._profile_split(None) == {"audio_encodes": 0, "audio_encode_ms": 0, "measure_ms": 0}


def test_delivered_reads_the_manifests_numbers():
    manifest = {
        "master": {"gain_db": -1.5, "lufs": -9.2, "file": "a private name.wav"},
        "artifacts": [
            {"kind": "video", "measured": {"lufs": -10.0, "true_peak_dbtp": -1.2}},
            {"kind": "video", "measured": {"lufs": -11.0, "true_peak_dbtp": -1.05}},
            {"kind": "image", "measured": {"width": 3000}},
            {"kind": "video", "measured": None},
        ],
    }
    out = suites._delivered(manifest)
    assert out == {"files": 2, "true_peak_dbtp_max": -1.05, "lufs_mean": -10.5, "gain_db": -1.5, "master_lufs": -9.2}
    assert suites._delivered({}) == {"files": 0}


def test_render_fps_reads_the_done_line():
    line = "DONE /x/t.mp4  240 frames (t0 0.000, 10s @ 24 fps, ending=droste) in 31s (7.7 fps)  + t.mp4.json"
    assert suites._render_fps(line) == 7.7 and suites._render_fps("nothing") is None


def test_worker_lists():
    assert suites._ints("8,2,2,1", [9]) == [1, 2, 8] and suites._ints(None, [1, 2]) == [1, 2]


def test_private_inputs_are_linked_under_a_number(tmp_path):
    source = tmp_path / "An Unreleased Title.WAV"
    source.write_bytes(b"RIFF")
    link = suites._private_link(tmp_path / "work", 2, source)
    assert link.name == "private-2.wav" and link.resolve() == source.resolve()
    assert suites._private_link(tmp_path / "work", 2, source) == link  # again: replaced, not an error


def test_a_private_failure_is_recorded_without_its_reason(tmp_path, capsys):
    b = bench(tmp_path)
    suites._withheld(b, "aac-vs-aac_at", "private-1 aac", RuntimeError("Moonfield_final.wav: invalid data"))
    assert "Moonfield" not in json.dumps(b.failed) and b.failed[0]["case"] == "private-1 aac"
    assert "Moonfield" in capsys.readouterr().out  # the terminal still says what went wrong


# --- fixtures: pure functions of their arguments -------------------------------------------


def test_a_master_block_is_the_same_whatever_the_masters_length():
    short = fixtures.master_block(1, sr=8000, seconds=15.0, bpm=120, seed=4, peak_dbfs=-0.3)
    long = fixtures.master_block(1, sr=8000, seconds=600.0, bpm=120, seed=4, peak_dbfs=-0.3)
    assert short.shape == (5 * 8000, 2) and np.array_equal(short, long[: len(short)])
    assert np.array_equal(long, fixtures.master_block(1, sr=8000, seconds=600.0, bpm=120, seed=4, peak_dbfs=-0.3))
    assert fixtures.master_block(9, sr=8000, seconds=15.0, bpm=120, seed=4, peak_dbfs=-0.3).shape == (0, 2)


def test_a_master_stays_under_its_sample_ceiling_and_leans_on_it():
    block = fixtures.master_block(3, sr=48000, seconds=60.0, bpm=120, seed=0, peak_dbfs=-0.3)
    peak = float(np.max(np.abs(block)))
    assert 10 ** (-1.0 / 20) < peak <= 10 ** (-0.3 / 20)


def test_write_master_writes_the_blocks(tmp_path):
    import soundfile as sf

    path = fixtures.write_master(tmp_path / "m.wav", 12.5, sr=8000, seed=1)
    data, rate = sf.read(str(path), dtype="float32")
    assert rate == 8000 and data.shape == (100000, 2)
    expected = fixtures.master_block(1, sr=8000, seconds=12.5, bpm=120.0, seed=1, peak_dbfs=-0.3)
    assert np.allclose(data[80000:], expected, atol=2 / 2**23)


def test_photo_pixels_are_seeded():
    a = fixtures.photo_pixels(64, 48, hue=0.1, seed=3, strip=20)
    assert a.shape == (48, 64, 3) and a.dtype == np.uint8
    assert np.array_equal(a, fixtures.photo_pixels(64, 48, hue=0.1, seed=3, strip=20))
    assert not np.array_equal(a, fixtures.photo_pixels(64, 48, hue=0.1, seed=4, strip=20))


def test_write_photos(tmp_path):
    made = fixtures.write_photos(tmp_path, {"b": 0.1, "a": 0.5}, 2, size=(40, 30))
    assert sorted(made) == ["a", "b"] and len(list(made["a"].glob("*.jpg"))) == 2


def test_loops():
    seamless = list(fixtures.loop_frames("seamless", 8, width=16, height=8))
    again = fixtures.loop_frame(1.0, 0, width=16, height=8)  # one period on: the first frame's picture
    assert len(seamless) == 8 and seamless[0].shape == (8, 16, 3)
    assert np.abs(seamless[0].astype(int) - again.astype(int)).max() <= 1  # float rounding at most
    cut = list(fixtures.loop_frames("cut", 8, width=16, height=8))
    assert not np.array_equal(cut[3][..., 2], cut[4][..., 2])
    assert len(list(fixtures.loop_frames("xfade", 16, width=16, height=8))) == 16
    with pytest.raises(ValueError, match="loop kind"):
        list(fixtures.loop_frames("spiral", 4, width=4, height=4))


def test_suites_are_registered():
    assert set(suites.SUITES) == {"canvas-knee", "footage", "deliver", "aac-vs-aac_at", "loop-seam", "long-form", "quick"}
