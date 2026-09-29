---
name: kaleidophone-footage-effects
description: Build per-pixel, stateful effects over real footage with kaleidophone.frames (memory canvas, generation loss, slit-scan, red-thread grade, feedback, mean face), rendered by resumable, checkpointed workers. Use when footage needs an effect an ffmpeg filter graph can't express, when a long frame render has to survive per-call time limits, or when deciding which engine a footage effect belongs in.
---

# kaleidophone: effects over footage (frame programs)

`kaleidophone.frames` is the second engine
(`docs/decisions/0007-three-engines-one-contract.md`): a Python function sees
every decoded frame as float32 RGB and returns the output frame, ffmpeg still
decodes and encodes, and a render stops and resumes. Two releases hand-built
it before it was code — AHANGE AROOSI and MIKONAMET — and their effects are
its effects. `#N` is a technique in `docs/TECHNIQUES.md`; the module
docstrings in `src/kaleidophone/frames/` carry the measurements.

## First: is this the right engine?

| The picture needs | Engine |
|---|---|
| your photos and clips cut on the beat, graded, zoomed, strobed, mirrored — anything ffmpeg's filter language can say | filter graphs: the brief and `render/effects.py`. Fastest, and a broken cut is a one-line error |
| per-pixel decisions, or memory of earlier frames, over footage | **frame programs** (this skill) |
| no footage — the picture is drawn | canvas (`kaleidophone-canvas-piece`) |

Frame programs are slow — ~8.7 fps per worker at 1080p on a 4-core ARM VM,
~13 fps with three workers, measured on MIKONAMET — so they are for the
passages that need them, not the default.

## The effects

All take and return float32 RGB `(H, W, 3)` in 0..1. Sizes quoted "at 1080p"
scale with the frame's long side, so a 640×360 proxy previews the
full-resolution look.

| Effect | What it is | What the release learned |
|---|---|---|
| `MemoryCanvas` (#12) | the video forgets its own footage: blocks re-record with probability p(t), bursts on beats and onsets, a protected face ellipse that shrinks to nothing, stale blocks paling toward paper | feathered on purpose — the hard-edged block grid read as glitch, not memory. Stateful: it checkpoints |
| `generation_loss` (#13) | a photocopy of a photocopy | copies must get **paler**; the first version went dark and read as a burnt negative. Cache recalls by (frame, generations) |
| `SlitScan` (#7) | a ring buffer read back with a per-column (or per-row) delay: time pulls the subject away | `hold=` keeps a face sharp for a cover while the rest smears |
| `red_thread_grade` (#6) | the world drained to two tones except one hue band | the grade is the concept; the chroma gate keeps skin from glowing; `amount` lets the drain arrive over the song |
| `KaleidoBloom` (#8) | a polar mirror, mixed in only at peaks | drive `amount` from the song (`smoothstep(0.8, 0.95, energy)`); at 0 it costs nothing |
| `feedback_echo` | the previous **output** frame, slightly zoomed, blended in | keep the last output in `state`; the previous source frame gives a crossfade, not feedback |
| `punch_zoom` | a zoom kick | `amount = a * pulse(t, beats)`: on every beat in quiet sections, strong onsets in loud ones |
| `GrainBank` (#10) | grain from a few pre-made tiles, rolled per frame | a fresh `rng.normal` field per frame at 1080×1920 was the hottest line in the engine |
| `mean_face`, `MeanFace` (#14) | the eye-aligned average of every frame a face appears in — an ending, a cover | means of different takes differ in character: compute several, pick by story. Eye points come from your tracker |

Helpers: `pulse(t, events, tau)` is 1 on a beat or onset and decays (0.12 s
for beats, 0.10 s for onsets — the release's values). `Keyframes([(t, v), …])`
is any schedule an effect takes; MIKONAMET's refresh was 1.0 through the first
half, easing to 0.15 across the second verse and 0.02 for the outro.
Randomness is a seeded Generator per effect, never numpy's global state: with
a shared stream, adding grain would re-roll which blocks the canvas forgets.

## A program and its jobs

```python
import numpy as np
from kaleidophone.audio.envelope import load_songpack
from kaleidophone.frames import GrainBank, MemoryCanvas, RenderJob, concat_parts, job_parts, pulse, run_workers

W, H = 1920, 1080
CUT_FRAMES = [...]                       # the edit's cut frames: where a state reset is acceptable

def make_state():                        # configuration: rebuilt the same way on every resume
    return {"memory": MemoryCanvas(W, H, refresh=[(0, 1.0), (120, 1.0), (156, 0.15), (191, 0.02)]),
            "grain": GrainBank(W, H)}

def program(frame, t, env, state):       # t is song time; env is read-only
    frame = state["memory"](frame, t, beat=pulse(t, env["beats"]))
    return state["grain"](frame)

if __name__ == "__main__":               # workers are spawned processes
    pack = load_songpack("private/songpack.json")
    env = {"beats": np.asarray(pack["beats"])}
    job = RenderJob(source="take.mp4", out_dir="private/frames", end_frame=5900, size=(W, H), fps=25)
    results = run_workers(job, program, 3, budget_s=150, make_state=make_state, env=env, snap_to=CUT_FRAMES)
    if all(r.done for r in results):     # otherwise: run the script again, it resumes
        concat_parts(job_parts(r.job for r in results), "private/silent.mp4")
```

The song goes back on with `kaleidophone deliver` (`kaleidophone-release-kit`),
which also measures the true peak of what it delivers; `kaleidophone remux`
muxes too, with no gain and no measurement.

- **Call it again until it's done.** Each call stops at `budget_s`, closes
  its part, checkpoints the state and returns; the next call resumes there.
  MIKONAMET ran three workers per call with a 150 s budget under a 180 s
  limit — the encoder still has to flush after the last frame. `run_job()` is
  the same loop for one job in this process (`.done` says when it's
  finished; `concat_parts(job_parts(job), …)` then).
- **`make_state()` is configuration; the checkpoint is state.** A resume
  rebuilds the effects from code, then loads what they remembered: arrays,
  numbers and strings, never pickle. Change the job's timing or encode
  settings and the resume refuses (`resume=False` starts over).
- **Workers are processes.** `program`, `make_state` and `env` must be
  picklable: module-level functions, and the `__main__` guard.
- **Split where it cuts.** `mode="contiguous"` gives each worker one range,
  and a stateful effect starts fresh at each worker's first frame — so pass
  the edit's cut frames as `snap_to`, as MIKONAMET placed its worker ranges.
  `mode="stride"` spreads the expensive passages across workers but resets
  every chunk: stateless programs only.
- **One job per shot**, on one shared frame numbering, so `job_parts()` can
  prove they tile — a gap or an overlap would slide the picture against the
  audio.
- **Slow motion decodes at fps ÷ speed** (`speed=0.5` is half speed): every
  output frame gets its own source frame. AHANGE AROOSI's version did fps ×
  speed and shipped segments short.
- **Read forward.** The job seeks once, then reads sequentially; per-frame
  seeks into 50p H.264 ran at ~1.5 fps.
- **Keyframes for the kit.** Every part is its own encode and opens on a
  keyframe, so a job that starts at each point the release will be cut gives
  the joined film a keyframe there, and `deliver` can stream-copy the reel and
  stories out of it (it checks before encoding). A job boundary also resets a
  stateful effect, so plan the release's cut points on the edit's cuts.
- **9:16 from 16:9**: `pre_filter` is an ffmpeg chain applied before the frame
  is fitted — a crop that follows the face. It reaches ffmpeg verbatim; never
  build it from text you didn't write. A narrow crop scaled up is soft
  (MIKONAMET's 608-px windows at ×1.78); grain hides most of it.

Before the long render, look: run the same program at proxy size over a few
seconds of each passage and put the frames side by side — the check-frame
boards both releases QA'd on.

## Lessons with no code to own

- **Tracked-overlay inpaint (#9).** A burned-in watermark that drifts is a
  tracking problem: sample frames, detect, build a time → box path, patch with
  a feathered median. The detector lies over busy texture — compare raw
  against clean crops at three or more timestamps. Tell a scene object from a
  moving sticker by persistence and camera motion, not position.
- **Outro splice (#11).** A 60 s cut can end on the track's real ending: a 5 s
  crossfade from the main window into the song's last ~13 s. Seamless in an
  ambient track, where it reads as intent.
- **Lip-sync test (#17).** Before cutting a performance as sync, test it:
  mouth openness (1–8 Hz band) against the vocal stem's RMS, judged by
  consistency across 10 s windows — one global correlation peak (z ≈ 4) is
  noise. MIKONAMET's said no, and the film became a 2× slow-motion piece
  instead.
- **Render where the footage is (#5).** When the link to the machine that
  holds the footage is slow, bring the render to it; the budgets and
  checkpoints exist for that. MIKONAMET's 1.2 GB of 1080p50 source never left
  its machine — only proxies, keyframes and small previews did.

## Privacy

Footage is the most private material kaleidophone touches: the artist's own
face, or found footage of people who never agreed to be in a music video. No
frame, proxy, check board or mean face enters the repository, and a case
study about found footage carries technique only — no frames, no account
names, no description of the people (`docs/case-studies/ahange-aroosi.md`).
