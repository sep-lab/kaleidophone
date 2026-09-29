"""frames/engine.py: argv construction, checkpoint/resume, workers -- no ffmpeg.

Same rule as tests/test_ffmpeg_pipeline.py: pytest never invokes ffmpeg. The
command lines are asserted on directly; the render loop runs against a fake
decoder (synthetic frames computed from their index) and a fake encoder (which
saves the raw frames it was given), so "resume is bit-identical" can be checked
exactly, frame by frame. The ffmpeg-backed source and sink are exercised
against a stubbed subprocess.Popen.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os

import numpy as np
import pytest

from kaleidophone.frames import (
    GrainBank,
    MemoryCanvas,
    RenderJob,
    concat_args,
    concat_parts,
    decode_argv,
    encode_argv,
    feedback_echo,
    job_parts,
    job_status,
    plan_workers,
    pulse,
    run_job,
    run_workers,
    split_frames,
    write_concat_list,
)
from kaleidophone.frames import engine as eng
from kaleidophone.render import _ffmpeg_util as fu

H, W = 16, 24
OPENED_AT: list[int] = []  # start frame of every FakeSource opened in this process


def synthetic_frame(i: int, h: int = H, w: int = W) -> np.ndarray:
    """Frame `i` of a synthetic clip -- a pattern computed from the index."""
    yy, xx = np.mgrid[0:h, 0:w]
    return np.stack(
        [(xx * 9 + i * 7) % 256, (yy * 13 + i * 3) % 256, ((xx + yy) * 5 + i * 11) % 256], axis=-1
    ).astype(np.uint8)


class FakeSource:
    """Stands in for the ffmpeg decoder: frames [start, start + count)."""

    def __init__(self, job: RenderJob, start: int, count: int):
        self.size = job.size
        self.start, self.count = start, count
        OPENED_AT.append(start)

    def __iter__(self):
        w, h = self.size
        for i in range(self.start, self.start + self.count):
            yield synthetic_frame(i, h, w)

    def close(self):
        pass


class ShortSource(FakeSource):
    """A clip that runs out three frames early."""

    def __iter__(self):
        frames = list(super().__iter__())
        yield from frames[:-3]


class FakeSink:
    """Stands in for the ffmpeg encoder: saves the raw frames it was handed."""

    def __init__(self, job: RenderJob, path: str):
        self.path = path
        self.size = job.size
        self.frames: list[np.ndarray] = []

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(np.array(frame, copy=True))

    def close(self) -> None:
        w, h = self.size
        stack = np.stack(self.frames) if self.frames else np.zeros((0, h, w, 3), np.uint8)
        with open(self.path, "wb") as fh:
            np.save(fh, stack)


class FrameClock:
    """A fake wall clock that advances one 'second' per rendered frame, so a
    budget in seconds is a budget in frames and a test knows exactly where a
    call stops."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def identity(frame, t, env, state):
    return frame


def make_effects_state():
    return {
        "memory": MemoryCanvas(W, H, refresh=0.3, pale=0.5, feather=3.0, seed=1),
        "grain": GrainBank(W, H, seed=2),
        "prev": None,
        "count": 0,
    }


def effects_program(frame, t, env, state):
    """A real stateful program: forgetting blocks, grain, feedback, a counter."""
    out = state["memory"](frame, t, beat=pulse(t, env["beats"]))
    out = state["grain"](out, 0.05)
    out = feedback_echo(state["prev"], out, zoom=1.0, mix=0.3)
    state["prev"] = out
    state["count"] += 1
    return out


def _job(tmp_path, **kw) -> RenderJob:
    fields = {
        "source": "synthetic://clip",
        "out_dir": str(tmp_path / "render"),
        "end_frame": 23,
        "size": (W, H),
        "checkpoint_every": 10,
    }
    fields.update(kw)
    return RenderJob(**fields)


def _ticking(program, clock: FrameClock):
    def wrapped(frame, t, env, state):
        clock.now += 1.0
        return program(frame, t, env, state)

    return wrapped


def _run(job, program=identity, **kw):
    kw.setdefault("open_source", FakeSource)
    kw.setdefault("open_sink", FakeSink)
    return run_job(job, program, **kw)


def _frames_in(parts) -> np.ndarray:
    return np.concatenate([np.load(p) for p in parts])


@pytest.fixture(autouse=True)
def _reset_opened():
    OPENED_AT.clear()


# --- the job --------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"size": (W + 1, H)},  # odd: yuv420p can't hold it
        {"size": (0, H)},
        {"end_frame": -1},
        {"start_frame": 5, "end_frame": 4},
        {"fps": 0},
        {"speed": 0},
        {"speed": -0.5},
        {"tag": "a/b"},
        {"tag": ""},
        {"checkpoint_every": 0},
    ],
)
def test_render_job_refuses_settings_that_cannot_render(tmp_path, kw):
    with pytest.raises(ValueError):
        _job(tmp_path, **kw)


def test_frame_numbers_map_to_timeline_and_source_time(tmp_path):
    job = _job(tmp_path, fps=25.0, t0=100.0, source_start=10.0, speed=0.5)
    assert job.time_at(50) == pytest.approx(102.0)
    assert job.source_time_at(50) == pytest.approx(11.0)  # half speed: 2 s on screen, 1 s of source
    assert job.keyframe_interval == 50  # a 2 s GOP, as in the real release


# --- ffmpeg command lines -------------------------------------------------


def test_decode_argv_seeks_before_the_input_and_reads_raw_rgb_frames():
    argv = decode_argv("clip.mp4", start_s=12.5, fps=25, size=(1920, 1080), frames=100)
    assert argv.index("-ss") < argv.index("-i")  # seek once, before -i, then read sequentially
    assert argv[argv.index("-ss") + 1] == "12.500000"
    assert argv[argv.index("-frames:v") + 1] == "100"
    assert argv[argv.index("-f") + 1] == "rawvideo"
    assert argv[argv.index("-pix_fmt") + 1] == "rgb24"
    assert argv[-1] == "-"  # frames on stdout
    assert "-an" in argv
    vf = argv[argv.index("-vf") + 1]
    assert "fps=25" in vf and "scale=1920:1080" in vf and "crop=1920:1080" in vf


def test_decode_argv_samples_slow_motion_at_fps_over_speed():
    # Half speed at 25 fps needs 50 source frames per source second -- one per
    # output frame. fps * speed (12.5) is the bug that ships short segments.
    vf = decode_argv("clip.mp4", start_s=0, fps=25, size=(640, 360), speed=0.5)
    assert "fps=50" in vf[vf.index("-vf") + 1]


def test_decode_argv_omits_a_zero_seek_and_puts_the_pre_filter_first():
    argv = decode_argv("clip.mp4", start_s=0.0, fps=25, size=(608, 1080), pre_filter="crop=608:1080:656:0")
    assert "-ss" not in argv
    assert argv[argv.index("-vf") + 1].startswith("crop=608:1080:656:0,fps=25")


def test_decode_argv_makes_the_source_absolute_so_a_dash_is_not_a_flag():
    argv = decode_argv("-weird.mp4", start_s=0, fps=25, size=(64, 36))
    assert argv[argv.index("-i") + 1].startswith("/")


def test_decode_argv_refuses_reverse_or_zero_speed():
    with pytest.raises(ValueError):
        decode_argv("clip.mp4", start_s=0, fps=25, size=(64, 36), speed=0)


def test_encode_argv_reads_raw_rgb_on_stdin_and_writes_h264():
    argv = encode_argv("out/part.mp4", size=(1920, 1080), fps=25, crf=20, preset="medium", threads=2, gop=50)
    head = argv[argv.index("-f") : argv.index("-i") + 2]
    assert head == ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "25", "-i", "-"]
    assert argv[argv.index("-c:v") + 1] == "libx264"
    assert argv[argv.index("-crf") + 1] == "20"
    assert argv[argv.index("-preset") + 1] == "medium"
    assert argv[argv.index("-threads") + 1] == "2"
    assert argv[argv.index("-g") + 1] == "50"
    last_pix_fmt = max(i for i, a in enumerate(argv) if a == "-pix_fmt")
    assert argv[last_pix_fmt + 1] == "yuv420p"  # the output side; the input side is rgb24
    assert argv[-1].endswith("out/part.mp4") and argv[-1].startswith("/")


def test_encode_argv_caps_the_rate_only_with_both_maxrate_and_bufsize():
    assert "-maxrate" not in encode_argv("p.mp4", size=(64, 36), fps=25, maxrate="12M")
    argv = encode_argv("p.mp4", size=(64, 36), fps=25, maxrate="12M", bufsize="24M")
    assert argv[argv.index("-maxrate") + 1] == "12M" and argv[argv.index("-bufsize") + 1] == "24M"


@pytest.mark.parametrize(("fps", "arg"), [(25, "25"), (25.0, "25"), (12.5, "25/2"), (30000 / 1001, "30000/1001")])
def test_frame_rates_are_passed_exactly(fps, arg):
    assert eng._fps_arg(fps) == arg


def test_concat_args_stream_copy_the_video():
    args = concat_args("list.txt", "out.mp4")
    assert args[args.index("-f") + 1] == "concat"
    assert args[args.index("-safe") + 1] == "0"
    assert args[args.index("-c:v") + 1] == "copy"  # no re-encode: parts are the final encode
    assert args[-1] == "out.mp4"


def test_concat_list_escapes_apostrophes(tmp_path):
    listing = tmp_path / "list.txt"
    part = str(tmp_path / "Dad's parts" / "a_part000.mp4")
    write_concat_list([part], str(listing))
    text = listing.read_text()
    assert text.startswith("file '/") and "'\\''" in text
    # The package's one concat quoting, shared with the render and deliver.
    assert text == f"file {fu.concat_quote(part)}\n"


def test_concat_parts_runs_ffmpeg_on_a_list_next_to_the_parts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(eng, "require_ffmpeg", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(eng, "run", lambda ffmpeg, args: calls.append(args))
    parts = [tmp_path / "x_part000.mp4", tmp_path / "x_part001.mp4"]
    for p in parts:
        p.write_bytes(b"")
    out = concat_parts([str(p) for p in parts], str(tmp_path / "silent.mp4"))
    assert out.endswith("silent.mp4")
    args = calls[0]
    listing = args[args.index("-i") + 1]
    assert os.path.dirname(listing) == str(tmp_path)  # never outside the render's own directory
    with open(listing, encoding="utf-8") as fh:
        assert fh.read().count("file ") == 2


def test_concat_parts_refuses_nothing_or_missing_parts(tmp_path):
    with pytest.raises(ValueError):
        concat_parts([], str(tmp_path / "o.mp4"))
    with pytest.raises(FileNotFoundError):
        concat_parts([str(tmp_path / "gone.mp4")], str(tmp_path / "o.mp4"))


# --- the render loop, with a fake decoder and encoder -----------------------


def test_identity_program_reproduces_decoded_frames_exactly_across_parts(tmp_path):
    job = _job(tmp_path)
    result = _run(job)
    assert result.done and result.frames == 23
    assert [os.path.basename(p) for p in result.parts] == ["frames_part000.mp4", "frames_part001.mp4", "frames_part002.mp4"]
    expected = np.stack([synthetic_frame(i) for i in range(23)])
    assert np.array_equal(_frames_in(result.parts), expected)  # u8 -> float -> u8 is lossless
    assert not list((tmp_path / "render").glob("*.partial.mp4"))


def test_the_program_sees_timeline_time(tmp_path):
    seen = []

    def spy(frame, t, env, state):
        seen.append(t)
        return frame

    _run(_job(tmp_path, end_frame=4, t0=100.0, fps=25.0), spy)
    assert seen == pytest.approx([100.0, 100.04, 100.08, 100.12])


def test_env_is_passed_through_to_every_frame(tmp_path):
    env = {"beats": np.array([0.0, 0.5])}
    seen = []
    _run(_job(tmp_path, end_frame=3), lambda f, t, e, s: (seen.append(e), f)[1], env=env)
    assert all(e is env for e in seen)


def test_budget_stop_then_resume_is_bit_identical_to_an_uninterrupted_run(tmp_path):
    env = {"beats": np.array([0.0, 0.24, 0.48, 0.72])}
    straight = _run(_job(tmp_path, tag="straight"), effects_program, make_state=make_effects_state, env=env)

    clock = FrameClock()
    job = _job(tmp_path, tag="resumed")
    first = _run(job, _ticking(effects_program, clock), make_state=make_effects_state, env=env, budget_s=7, clock=clock)
    assert not first.done and first.next_frame == 7 and first.frames == 7
    assert job_status(job).next_frame == 7

    second = _run(job, effects_program, make_state=make_effects_state, env=env)
    assert second.done and second.frames == 16
    assert OPENED_AT == [0, 0, 7]  # straight run, then the two calls; the resume re-opened at 7
    assert np.array_equal(_frames_in(job_parts(job)), _frames_in(straight.parts))


def test_a_finished_job_is_not_rendered_again(tmp_path):
    job = _job(tmp_path)
    _run(job)
    OPENED_AT.clear()
    again = _run(job)
    assert again.done and again.frames == 0 and not OPENED_AT


def test_resume_false_starts_over(tmp_path):
    clock = FrameClock()
    job = _job(tmp_path)
    _run(job, _ticking(identity, clock), budget_s=5, clock=clock)
    fresh = _run(job, resume=False)
    assert OPENED_AT == [0, 0]
    assert fresh.done and fresh.frames == 23


def test_resume_refuses_a_job_whose_settings_changed(tmp_path):
    clock = FrameClock()
    job = _job(tmp_path)
    _run(job, _ticking(identity, clock), budget_s=5, clock=clock)
    with pytest.raises(ValueError, match="crf"):
        _run(dataclasses.replace(job, crf=28))


def test_a_source_that_ends_early_raises_and_leaves_no_partial_part(tmp_path):
    job = _job(tmp_path)
    with pytest.raises(RuntimeError, match="runs past the end of the clip"):
        _run(job, open_source=ShortSource)
    render_dir = tmp_path / "render"
    assert not list(render_dir.glob("*.partial.mp4"))
    assert job_status(job).next_frame == 20  # the two finished parts still count


@pytest.mark.parametrize(
    ("bad", "error"),
    [
        (lambda f, t, e, s: f[:-1], ValueError),  # wrong shape
        (lambda f, t, e, s: (f * 255).astype(np.uint8), TypeError),  # 8-bit instead of 0..1
    ],
)
def test_the_program_must_return_float_rgb_at_the_frame_size(tmp_path, bad, error):
    with pytest.raises(error):
        _run(_job(tmp_path), bad)


def test_output_is_clipped_and_rounded_without_touching_the_programs_array(tmp_path):
    kept = {}

    def hot(frame, t, env, state):
        out = frame * 2.0 - 0.25  # out of range on both sides
        kept[t] = out
        return out

    result = _run(_job(tmp_path, end_frame=2), hot)
    got = _frames_in(result.parts)[0].astype(np.float32) / 255
    np.testing.assert_allclose(got, np.clip(synthetic_frame(0) / 255 * 2.0 - 0.25, 0, 1), atol=0.5 / 255 + 1e-6)
    assert kept[0.0].min() < 0.0  # the program's own array was never clipped in place


def test_state_a_checkpoint_cannot_hold_is_refused_with_advice(tmp_path):
    with pytest.raises(TypeError, match="state_dict"):
        _run(_job(tmp_path, end_frame=3), make_state=lambda: {"handle": object()})


def test_plain_state_values_round_trip_through_a_checkpoint(tmp_path):
    job = _job(tmp_path)
    path = str(tmp_path / "ck.npz")
    state = {
        "n": 7,
        "gain": np.float32(0.25),
        "label": "hold",
        "gone": None,
        "prev": np.arange(6, dtype=np.float32).reshape(2, 3),
    }
    eng._write_checkpoint(path, job, 5, 1, state)
    meta, arrays = eng._read_checkpoint(path)
    restored = eng._restore_state(meta, arrays, lambda: {"gone": 1})
    assert restored["n"] == 7 and restored["label"] == "hold" and restored["gone"] is None
    assert restored["gain"].dtype == np.float32  # dtype survives, so later maths is bit-identical
    assert np.array_equal(restored["prev"], state["prev"])


def test_resume_needs_make_state_to_rebuild_the_effects(tmp_path):
    clock = FrameClock()
    job = _job(tmp_path)
    env = {"beats": np.array([0.0])}
    _run(job, _ticking(effects_program, clock), make_state=make_effects_state, env=env, budget_s=4, clock=clock)
    with pytest.raises(ValueError, match="make_state"):
        _run(job, effects_program, make_state=dict, env=env)


def test_make_state_must_return_a_dict(tmp_path):
    with pytest.raises(TypeError):
        _run(_job(tmp_path), make_state=list)


def test_checkpoints_are_loaded_without_pickle(tmp_path):
    """A checkpoint is data, never code: an object array (which would need
    pickle to load) is refused rather than unpickled."""
    job = _job(tmp_path)
    os.makedirs(job.out_dir)
    with open(eng.checkpoint_path(job), "wb") as fh:
        np.savez(fh, meta=np.array([{"next_frame": 0}], dtype=object))
    with pytest.raises(ValueError, match="allow_pickle"):
        _run(job)


def test_an_old_checkpoint_format_is_refused(tmp_path):
    job = _job(tmp_path)
    os.makedirs(job.out_dir)
    with open(eng.checkpoint_path(job), "wb") as fh:
        np.savez(fh, meta=np.asarray(json.dumps({"version": 0})))
    with pytest.raises(ValueError, match="format"):
        _run(job)


def test_progress_is_logged_per_part(tmp_path):
    lines = []
    _run(_job(tmp_path), log=lines.append)
    assert len(lines) == 3 and "part 000" in lines[0] and "next frame 23 of 23" in lines[-1]


def test_result_reports_its_rate(tmp_path):
    clock = FrameClock()
    result = _run(_job(tmp_path, end_frame=10), _ticking(identity, clock), clock=clock)
    assert result.elapsed_s == 10.0 and result.fps == 1.0


# --- job_parts --------------------------------------------------------------


def test_job_parts_refuses_an_unfinished_or_unrendered_job(tmp_path):
    job = _job(tmp_path)
    with pytest.raises(RuntimeError, match="not been rendered"):
        job_parts(job)
    clock = FrameClock()
    _run(job, _ticking(identity, clock), budget_s=12, clock=clock)
    with pytest.raises(RuntimeError, match="unfinished"):
        job_parts(job)


def test_job_parts_refuses_jobs_with_a_gap_between_them(tmp_path):
    a = _job(tmp_path, tag="a", start_frame=0, end_frame=10)
    b = _job(tmp_path, tag="b", start_frame=12, end_frame=20)
    with pytest.raises(ValueError, match="no gap or overlap"):
        job_parts([a, b])


def test_job_parts_notices_a_deleted_part(tmp_path):
    job = _job(tmp_path)
    result = _run(job)
    os.remove(result.parts[1])
    with pytest.raises(FileNotFoundError):
        job_parts(job)


def test_an_empty_job_has_no_parts_and_is_done(tmp_path):
    job = _job(tmp_path, start_frame=5, end_frame=5)
    assert job_status(job).done
    assert job_parts(job) == []


# --- workers ----------------------------------------------------------------


def test_contiguous_split_gives_each_worker_one_even_range():
    assert split_frames(0, 100, 3) == [[(0, 33)], [(33, 67)], [(67, 100)]]
    assert split_frames(0, 2, 5) == [[(0, 1)], [(1, 2)]]  # never an empty worker
    assert split_frames(10, 10, 3) == []


def test_contiguous_boundaries_snap_to_nearby_cuts():
    # A stateful effect resets where a worker starts; at a cut nobody sees it.
    assert split_frames(0, 100, 2, snap_to=[10, 45, 90]) == [[(0, 45)], [(45, 100)]]
    # A cut further than half a share away is not worth the imbalance.
    assert split_frames(0, 100, 2, snap_to=[5]) == [[(0, 50)], [(50, 100)]]


def test_stride_split_deals_chunks_round_robin():
    assert split_frames(0, 50, 2, mode="stride", chunk=10) == [
        [(0, 10), (20, 30), (40, 50)],
        [(10, 20), (30, 40)],
    ]


def test_split_rejects_bad_arguments():
    with pytest.raises(ValueError):
        split_frames(0, 10, 0)
    with pytest.raises(ValueError):
        split_frames(0, 10, 2, mode="diagonal")
    with pytest.raises(ValueError):
        split_frames(0, 10, 2, mode="stride", chunk=0)


def test_plan_workers_names_sub_jobs_stably(tmp_path):
    job = _job(tmp_path, end_frame=40, tag="film")
    contiguous = plan_workers(job, 2)
    assert [[j.tag for j in w] for w in contiguous] == [["film_w00"], ["film_w01"]]
    assert contiguous[1][0].start_frame == 20 and contiguous[1][0].crf == job.crf
    stride = plan_workers(job, 2, mode="stride", chunk=15)
    assert [[j.tag for j in w] for w in stride] == [["film_c0000", "film_c0002"], ["film_c0001"]]
    assert plan_workers(job, 2) == contiguous  # pure: a later call finds the same checkpoints


def test_run_workers_makes_progress_across_calls_and_joins_in_order(tmp_path):
    job = _job(tmp_path, end_frame=30, checkpoint_every=4)
    clock = FrameClock()
    program = _ticking(identity, clock)
    kw = {"parallel": False, "open_source": FakeSource, "open_sink": FakeSink, "clock": clock}

    first = run_workers(job, program, 2, budget_s=6, **kw)
    assert [r.next_frame for r in first] == [6, 21]  # each worker got its 6 frames
    assert not any(r.done for r in first)
    calls = 1
    results = first
    while not all(r.done for r in results):
        results = run_workers(job, program, 2, budget_s=6, **kw)
        calls += 1
    assert calls == 3
    parts = job_parts([r.job for r in results])
    assert np.array_equal(_frames_in(parts), np.stack([synthetic_frame(i) for i in range(30)]))


def test_stride_workers_share_one_budget_across_their_chunks(tmp_path):
    job = _job(tmp_path, end_frame=30, checkpoint_every=5)
    clock = FrameClock()
    kw = {"mode": "stride", "chunk": 5, "parallel": False, "open_source": FakeSource, "open_sink": FakeSink, "clock": clock}
    results = run_workers(job, _ticking(identity, clock), 2, budget_s=7, **kw)
    # Worker 0 owns chunks 0, 2, 4: it finishes chunk 0, gets 2 frames into
    # chunk 2, and never reaches chunk 4 this call.
    by_tag = {r.job.tag: r for r in results}
    assert by_tag["frames_c0000"].done
    assert by_tag["frames_c0002"].next_frame == 12
    assert by_tag["frames_c0004"].next_frame == 20 and by_tag["frames_c0004"].frames == 0
    while not all(r.done for r in results):
        results = run_workers(job, _ticking(identity, clock), 2, budget_s=7, **kw)
    assert np.array_equal(_frames_in(job_parts([r.job for r in results])), np.stack([synthetic_frame(i) for i in range(30)]))


def test_contiguous_workers_reset_state_at_their_boundary(tmp_path):
    # Documented behaviour, pinned: worker 1 starts from make_state(), so its
    # first frame is what a fresh program makes of that frame.
    job = _job(tmp_path, end_frame=20)
    env = {"beats": np.array([0.0])}
    results = run_workers(
        job, effects_program, 2, make_state=make_effects_state, env=env,
        parallel=False, open_source=FakeSource, open_sink=FakeSink,
    )
    second = np.load(job_parts(results[1].job)[0])[0]
    decoded = synthetic_frame(10).astype(np.float32) * np.float32(1 / 255)  # as the engine converts
    fresh = effects_program(decoded, job.time_at(10), env, make_effects_state())
    assert np.array_equal(second, (np.clip(fresh, 0, 1) * 255 + 0.5).astype(np.uint8))


def test_run_workers_in_parallel_processes(tmp_path):
    """The real path: spawned worker processes. Everything handed to them is
    module-level, so it pickles."""
    job = _job(tmp_path, end_frame=12, checkpoint_every=4)
    results = run_workers(job, identity, 2, open_source=FakeSource, open_sink=FakeSink)
    assert not OPENED_AT  # every frame was decoded in a worker process, none in this one
    assert all(r.done for r in results) and len(results) == 2
    parts = job_parts([r.job for r in results])
    assert np.array_equal(_frames_in(parts), np.stack([synthetic_frame(i) for i in range(12)]))


# --- the ffmpeg-backed source and sink, with subprocess stubbed -------------


class _Stdin(io.BytesIO):
    def close(self):
        self.written = self.getvalue()
        super().close()


class _BrokenStdin:
    def write(self, data):
        raise BrokenPipeError

    def close(self):
        raise BrokenPipeError


class FakePopen:
    """Records argv and plays back canned stdout / stderr / exit code."""

    last: FakePopen | None = None
    stdout_bytes = b""
    stderr_bytes = b""
    returncode = 0
    broken_stdin = False

    def __init__(self, argv, stdin=None, stdout=None, stderr=None):
        FakePopen.last = self
        self.argv = argv
        self.stdin_arg, self.stdout_arg = stdin, stdout
        self.stdout = io.BytesIO(self.stdout_bytes)
        self.stdin = _BrokenStdin() if self.broken_stdin else _Stdin()
        self.killed = False
        self.finished = False
        if stderr is not None and hasattr(stderr, "write"):
            stderr.write(self.stderr_bytes)
        if "libx264" in argv:  # an encoder creates its output file as it starts
            open(argv[-1], "wb").close()

    def poll(self):
        return self.returncode if self.finished else None

    def wait(self):
        self.finished = True
        return self.returncode

    def kill(self):
        self.killed = True


@pytest.fixture
def popen(monkeypatch):
    monkeypatch.setattr(eng, "require_ffmpeg", lambda: "/fake/ffmpeg")
    # The engine starts ffmpeg through _ffmpeg_util.spawn(), the package's one
    # Popen -- so that is where the stub goes.
    monkeypatch.setattr(fu.subprocess, "Popen", FakePopen)
    for name, value in {"stdout_bytes": b"", "stderr_bytes": b"", "returncode": 0, "broken_stdin": False}.items():
        monkeypatch.setattr(FakePopen, name, value)
    return FakePopen


def test_ffmpeg_source_reads_whole_frames_from_the_pipe(tmp_path, popen):
    frames = [synthetic_frame(i) for i in range(2)]
    popen.stdout_bytes = b"".join(f.tobytes() for f in frames) + b"\x00" * 10  # plus a torn tail
    job = _job(tmp_path, source_start=4.0, fps=25.0)
    source = eng.ffmpeg_source(job, 50, 2)
    argv = popen.last.argv
    assert argv[0] == "/fake/ffmpeg"
    assert argv[argv.index("-ss") + 1] == "6.000000"  # 4 s + frame 50 at 25 fps
    assert argv[argv.index("-frames:v") + 1] == "2"
    got = list(source)
    assert len(got) == 2 and all(np.array_equal(a, b) for a, b in zip(got, frames))
    source.close()


def test_ffmpeg_source_reports_a_failed_decode_with_its_stderr(tmp_path, popen):
    popen.returncode = 1
    popen.stderr_bytes = b"moov atom not found"
    source = eng.ffmpeg_source(_job(tmp_path), 0, 5)
    with pytest.raises(RuntimeError, match="moov atom not found"):
        list(source)
    source.close()


def test_closing_a_running_decoder_kills_it(tmp_path, popen):
    source = eng.ffmpeg_source(_job(tmp_path), 0, 5)
    source.close()
    assert popen.last.killed


def test_ffmpeg_sink_writes_frames_and_builds_the_jobs_encode(tmp_path, popen):
    job = _job(tmp_path, crf=18, preset="slow")
    sink = eng.ffmpeg_sink(job, str(tmp_path / "p.partial.mp4"))
    argv = popen.last.argv
    assert argv[argv.index("-crf") + 1] == "18" and argv[argv.index("-preset") + 1] == "slow"
    assert argv[argv.index("-g") + 1] == "50"
    frame = synthetic_frame(3)
    sink.write(frame)
    sink.close()
    assert popen.last.stdin.written == frame.tobytes()


def test_the_decoder_and_encoder_never_read_the_terminal(tmp_path, popen):
    """The decoder's stdin is /dev/null (its frames come out of stdout); the
    encoder's stdin is the frame pipe and its stdout /dev/null. Neither
    inherits the terminal, which a shell loop around a render is reading."""
    eng.ffmpeg_source(_job(tmp_path), 0, 1).close()
    assert (popen.last.stdin_arg, popen.last.stdout_arg) == (fu.subprocess.DEVNULL, fu.subprocess.PIPE)
    assert "-nostdin" in popen.last.argv
    eng.ffmpeg_sink(_job(tmp_path), str(tmp_path / "p.mp4")).close()
    assert (popen.last.stdin_arg, popen.last.stdout_arg) == (fu.subprocess.PIPE, fu.subprocess.DEVNULL)


def test_ffmpeg_sink_reports_a_failed_encode(tmp_path, popen):
    popen.returncode = 1
    popen.stderr_bytes = b"Unknown encoder"
    sink = eng.ffmpeg_sink(_job(tmp_path), str(tmp_path / "p.mp4"))
    with pytest.raises(RuntimeError, match="Unknown encoder"):
        sink.close()


def test_ffmpeg_sink_reports_an_encoder_that_died_mid_render(tmp_path, popen):
    popen.broken_stdin = True
    popen.returncode = 1
    popen.stderr_bytes = b"killed"
    sink = eng.ffmpeg_sink(_job(tmp_path), str(tmp_path / "p.mp4"))
    with pytest.raises(RuntimeError, match="died"):
        sink.write(synthetic_frame(0))
    with pytest.raises(RuntimeError, match="killed"):
        sink.close()


def test_a_failing_program_closes_the_encoder_and_removes_the_partial_part(tmp_path, popen):
    popen.stdout_bytes = b"".join(synthetic_frame(i).tobytes() for i in range(3))

    def boom(frame, t, env, state):
        if t > 0.05:
            raise ZeroDivisionError("program bug")
        return frame

    job = _job(tmp_path, end_frame=3)
    with pytest.raises(ZeroDivisionError):
        run_job(job, boom)  # default ffmpeg source and sink, over the stubbed Popen
    assert not list((tmp_path / "render").glob("*.partial.mp4"))
