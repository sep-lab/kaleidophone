"""
kaleidophone.frames -- the frame-program engine: per-pixel, stateful effects
over real footage.

kaleidophone has three ways to make a picture. Pick by what the effect needs:

- render/effects.py, the default engine: ffmpeg filter-graph fragments applied
  per cut. Use it whenever an effect can be said in ffmpeg's filter language --
  grades, zooms, strobes, grain, mirrors. It is the fastest path, a broken cut
  is a one-line error, and everything a brief does today goes through it.

- kaleidophone.frames (this package): a Python function sees every decoded
  frame as a float32 array and returns the output frame. Use it when an effect
  is per-pixel AND stateful over footage -- it remembers earlier frames (a
  canvas that forgets block by block, a slit-scan ring buffer, video
  feedback) or decides per pixel in a way a filter can't (one hue surviving a
  drained grade). It is far slower than filters -- measured on a real
  release, ~8.7 fps per worker at 1080p on a 4-core ARM VM, ~13 fps with three
  workers -- so it is for the passages or pieces that need it, and it is
  resumable because renders that slow have to be (engine.py explains how).

- canvas/ at the repository root: fully procedural pieces drawn in a browser
  canvas. If nothing in the frame comes from a camera, it belongs there, not
  here.

This is still ADR-0002's kind of engine: deterministic (every random draw
comes from a seeded Generator), working on your own footage, with no
model-generated pixels.

A program is a function of (frame, t, env, state); its effects live in the
state dict so a checkpoint can carry them:

    from kaleidophone.frames import (
        GrainBank, MemoryCanvas, RenderJob, concat_parts, job_parts, pulse, run_job,
    )

    W, H = 1920, 1080

    def make_state():
        return {
            "memory": MemoryCanvas(W, H, refresh=[(0, 1.0), (30, 0.15), (60, 0.02)]),
            "grain": GrainBank(W, H),
        }

    def program(frame, t, env, state):
        frame = state["memory"](frame, t, beat=pulse(t, env["beats"]))
        return state["grain"](frame)

    job = RenderJob(source="clip.mp4", out_dir="render", end_frame=1500, size=(W, H))
    result = run_job(job, program, make_state=make_state, env={"beats": beats}, budget_s=150)
    # ...call again until result.done, then:
    concat_parts(job_parts(job), "render/silent.mp4")

and render.ffmpeg_pipeline.mux_audio() puts the song back on. `env` is
whatever the program reads but never writes; in practice, the song pack from
audio/envelope.py, whose beat grid and 100 Hz envelopes are what a program
reacts to.
"""

from __future__ import annotations

from kaleidophone.frames.effects import (
    GrainBank,
    KaleidoBloom,
    Keyframes,
    MeanFace,
    MemoryCanvas,
    SlitScan,
    ellipse_mask,
    feedback_echo,
    generation_loss,
    kaleido_index_map,
    mean_face,
    pulse,
    punch_zoom,
    red_thread_grade,
    smoothstep,
)
from kaleidophone.frames.engine import (
    FfmpegSink,
    FfmpegSource,
    FrameSink,
    FrameSource,
    Program,
    RenderJob,
    RenderResult,
    checkpoint_path,
    concat_args,
    concat_parts,
    decode_argv,
    encode_argv,
    ffmpeg_sink,
    ffmpeg_source,
    job_parts,
    job_status,
    part_path,
    plan_workers,
    run_job,
    run_workers,
    split_frames,
    write_concat_list,
)

__all__ = [
    "FfmpegSink",
    "FfmpegSource",
    "FrameSink",
    "FrameSource",
    "GrainBank",
    "KaleidoBloom",
    "Keyframes",
    "MeanFace",
    "MemoryCanvas",
    "Program",
    "RenderJob",
    "RenderResult",
    "SlitScan",
    "checkpoint_path",
    "concat_args",
    "concat_parts",
    "decode_argv",
    "ellipse_mask",
    "encode_argv",
    "feedback_echo",
    "ffmpeg_sink",
    "ffmpeg_source",
    "generation_loss",
    "job_parts",
    "job_status",
    "kaleido_index_map",
    "mean_face",
    "part_path",
    "plan_workers",
    "pulse",
    "punch_zoom",
    "red_thread_grade",
    "run_job",
    "run_workers",
    "smoothstep",
    "split_frames",
    "write_concat_list",
]
