"""
Synthetic inputs for the benchmark suites: masters, pictures, photos, loops.

Everything here is generated, like examples/demo/generate_fixtures.py, and
written into the run's work folder -- never into the repository (AGENTS.md:
no media is ever committed, not as a fixture either). Every generator is a
pure function of its arguments and a seed, so two runs, or two machines,
benchmark the same bytes going in.

What they stand in for, and how far:

- write_master(): a mastered song -- a beat grid of kick, snare and hats over
  a pad, louder and quieter sections, soft-clipped and band-limited like a
  limited master: about -13 LUFS, its sample peak just under the ceiling,
  and through AAC its true peak half a dB to two over 0 dBTP, as a hot real
  master's is (deliver.py's docstring) -- which is what makes the delivery's
  true-peak guard step. Written in 10 s blocks, so a 23-minute one costs a
  block of memory, not the song.
- write_picture() / write_looped_picture(): a silent render, from ffmpeg's
  testsrc2 with temporal noise, so it costs bits like a real picture; the
  long one is a short clip stream-copied over and over, a 23-minute film in
  seconds.
- write_parts(): a body and its endings with one encoder setting, as
  `render.mjs --endings` writes them, for a delivery with endings.
- write_photos(): 24-megapixel JPEGs (6000x4000), as a camera writes them --
  a gradient, soft shapes and sensor-like noise, so they decode like photos.
- write_loop(): a loop for the seam check: seamless, drifting, cut, or
  cross-faded.

None of this is representative of a real song's analysis (examples/demo/
says the same of its fixtures); it is representative of the work a render
and a delivery do per second of material, which is what is being timed.
"""

from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path

import numpy as np

BLOCK_S = 10.0  # write_master's block: part of what makes its output a function of its arguments alone


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------
def master_block(index: int, *, sr: int, seconds: float, bpm: float, seed: int, peak_dbfs: float) -> np.ndarray:
    """Block `index` (BLOCK_S long, the last one shorter) of a synthetic
    master, stereo float32. A pure function of its arguments: the blocks of
    a 23-minute master are the blocks of a 3-minute one, as far as it goes."""
    start = index * BLOCK_S
    keep = round(min(BLOCK_S, seconds - start) * sr)
    if keep <= 0:
        return np.zeros((0, 2), np.float32)
    # Always the whole block, cut afterwards: the noise drawn depends on how
    # much is drawn, and the last block of a short master must be the same
    # samples as that block of a long one.
    n = round(BLOCK_S * sr)
    t = start + np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng([seed, index])
    beat = 60.0 / bpm
    bar = 4 * beat
    # Sections of 16 bars, alternating quiet and loud, the way a song breathes.
    section = np.floor(t / (16 * bar)).astype(np.int64)
    level = np.where(section % 2 == 0, 0.45, 0.95)

    pad = 0.18 * (np.sin(2 * np.pi * 110.0 * t) + 0.6 * np.sin(2 * np.pi * 164.81 * t + 0.3))
    pad *= 0.75 + 0.25 * np.sin(2 * np.pi * t / (8 * bar))

    in_beat = np.mod(t, beat)
    beat_no = np.floor(t / beat).astype(np.int64)
    kick = 0.9 * np.exp(-in_beat / 0.09) * np.sin(2 * np.pi * (55.0 + 90.0 * np.exp(-in_beat / 0.02)) * in_beat)
    snare_on = (beat_no % 4 == 1) | (beat_no % 4 == 3)
    # Noise band-limited like a recording's, well under Nyquist: full-band
    # noise, clipped, puts peaks between the samples no master has.
    noise = _lowpass(rng.standard_normal((n, 2)), 9000.0 / sr)
    snare = (0.9 * snare_on * np.exp(-in_beat / 0.07))[:, None] * noise
    in_eighth = np.mod(t, beat / 2)
    hats = (0.25 * np.exp(-in_eighth / 0.015))[:, None] * _lowpass(rng.standard_normal((n, 2)), 15000.0 / sr)

    mono = (pad + kick) * level
    x = mono[:, None] + (snare + hats) * level[:, None]
    x[:, 1] += 0.03 * np.sin(2 * np.pi * 220.0 * t)  # a little difference between the sides
    # A soft clip, as a limiter leaves a master: the loud sections lean on the
    # ceiling, and the clip's own harmonics, filtered, overshoot it a little
    # between samples -- which is what makes the delivery's guard step.
    drive = 1.3
    y = np.tanh(drive * np.clip(x, -1.5, 1.5)) / math.tanh(drive * 1.5)
    y = _lowpass(y, 18000.0 / sr)
    return (10 ** (peak_dbfs / 20.0) * _CLIP_HEADROOM * y[:keep]).astype(np.float32)


# What the final low-pass can add to the soft clip's peak, held back so the
# sample peak stays under the ceiling.
_CLIP_HEADROOM = 0.85


def _lowpass(x: np.ndarray, cutoff: float, taps: int = 63) -> np.ndarray:
    """A windowed-sinc low-pass, `cutoff` in cycles per sample, along axis 0."""
    k = np.arange(taps) - (taps - 1) / 2
    kernel = 2 * cutoff * np.sinc(2 * cutoff * k) * np.hamming(taps)
    kernel /= kernel.sum()
    return np.stack([np.convolve(x[:, c], kernel, mode="same") for c in range(x.shape[1])], axis=1) if x.ndim == 2 \
        else np.convolve(x, kernel, mode="same")


def write_master(
    path: Path,
    seconds: float,
    *,
    sr: int = 48000,
    subtype: str = "PCM_24",
    bpm: float = 120.0,
    seed: int = 0,
    peak_dbfs: float = -0.3,
) -> Path:
    """A synthetic master, written block by block (see master_block)."""
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = math.ceil(seconds / BLOCK_S)
    with sf.SoundFile(str(path), "w", samplerate=sr, channels=2, subtype=subtype) as fh:
        for k in range(blocks):
            fh.write(master_block(k, sr=sr, seconds=seconds, bpm=bpm, seed=seed, peak_dbfs=peak_dbfs))
    return path


# --------------------------------------------------------------------------
# pictures
# --------------------------------------------------------------------------
def _ffmpeg(ffmpeg: str, args: list[str]) -> None:
    from kaleidophone.render._ffmpeg_util import run

    run(ffmpeg, ["-y", *args])


def _encode(fps: float, crf: int, gop: int) -> list[str]:
    """One encoder setting for every picture fixture: parts made with it join by stream copy."""
    return [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-r", f"{fps:g}", "-an",
    ]


def write_picture(
    ffmpeg: str,
    path: Path,
    seconds: float,
    *,
    size: tuple[int, int] = (1080, 1920),
    fps: float = 24,
    crf: int = 20,
    hue: float = 0.0,
    noise: int = 8,
) -> Path:
    """A silent picture: testsrc2, turned `hue` degrees, with temporal noise
    so it costs bits like a real one; a keyframe every second."""
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    source = f"testsrc2=size={w}x{h}:rate={fps:g}:duration={seconds:g},hue=h={hue:g},noise=alls={noise}:allf=t"
    _ffmpeg(ffmpeg, ["-f", "lavfi", "-i", source, *_encode(fps, crf, max(1, round(fps))), str(path)])
    return path


def write_looped_picture(ffmpeg: str, path: Path, seconds: float, clip: Path, clip_seconds: float) -> Path:
    """`seconds` of picture or a little more, by stream-copying `clip` over
    and over: a film-length silent render in the time it takes to copy it."""
    loops = max(0, math.ceil(seconds / clip_seconds) - 1)
    _ffmpeg(ffmpeg, ["-stream_loop", str(loops), "-i", str(clip), "-c", "copy", str(path)])
    return path


def write_parts(
    ffmpeg: str,
    folder: Path,
    *,
    body_s: float,
    ending_s: float,
    endings: tuple[str, ...] = ("a", "b"),
    size: tuple[int, int] = (1080, 1920),
    fps: float = 24,
) -> dict:
    """A body and one file per ending, one encoder setting for all of them,
    each starting on a keyframe -- what `render.mjs --endings` hands a
    delivery. Returns the file names, relative to `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    write_picture(ffmpeg, folder / "body.mp4", body_s, size=size, fps=fps)
    files = {}
    for k, name in enumerate(endings, start=1):
        files[name] = f"ending-{name}.mp4"
        write_picture(ffmpeg, folder / files[name], ending_s, size=size, fps=fps, hue=60.0 * k)
    return {"body": "body.mp4", "endings": files}


# --------------------------------------------------------------------------
# photos
# --------------------------------------------------------------------------
def photo_pixels(width: int, height: int, *, hue: float, seed: int, strip: int = 500) -> np.ndarray:
    """A camera-sized frame: a vertical gradient in `hue`, a few soft
    shapes, and per-pixel noise -- the noise is what makes a JPEG of it as
    large, and as slow to decode, as a photo. uint8 (height, width, 3)."""
    import colorsys

    rng = np.random.default_rng(seed)
    out = np.empty((height, width, 3), np.uint8)
    top = np.array(colorsys.hsv_to_rgb(hue % 1.0, 0.55, 0.25)) * 255.0
    bottom = np.array(colorsys.hsv_to_rgb((hue + 0.04) % 1.0, 0.7, 0.92)) * 255.0
    blobs = [(rng.uniform(0, width), rng.uniform(0, height), rng.uniform(0.05, 0.2) * width, rng.uniform(-60, 60))
             for _ in range(6)]
    xs = np.arange(width, dtype=np.float32)
    for y0 in range(0, height, strip):
        y1 = min(height, y0 + strip)
        ys = np.arange(y0, y1, dtype=np.float32)[:, None]
        mix = (ys / height)[..., None]
        base = top * (1.0 - mix) + bottom * mix  # (rows, 1, 3)
        shade = np.zeros((y1 - y0, width), np.float32)
        for cx, cy, r, gain in blobs:
            shade += gain * np.exp(-(((xs[None, :] - cx) ** 2 + (ys - cy) ** 2) / (2 * r * r)))
        grain = rng.normal(0.0, 9.0, (y1 - y0, width)).astype(np.float32)
        out[y0:y1] = np.clip(base + (shade + grain)[..., None], 0, 255).astype(np.uint8)
    return out


def write_photos(folder: Path, stations: dict[str, float], count: int, *, size=(6000, 4000), seed: int = 0) -> dict:
    """`count` photos per station, `size` pixels, each hue-tinted per its
    station. Returns {station: folder}."""
    from PIL import Image

    made = {}
    for s, (name, hue) in enumerate(sorted(stations.items())):
        where = folder / name
        where.mkdir(parents=True, exist_ok=True)
        for k in range(count):
            target = where / f"{k:03d}.jpg"
            if not target.exists():
                pixels = photo_pixels(*size, hue=hue, seed=seed * 1000 + s * 100 + k)
                Image.fromarray(pixels).save(target, quality=90)
        made[name] = where
    return made


# --------------------------------------------------------------------------
# loops
# --------------------------------------------------------------------------
LOOP_KINDS = ("seamless", "drift", "cut", "xfade")


def loop_frame(phase: float, index: int, *, width: int, height: int, scene: int = 0, seed: int = 0) -> np.ndarray:
    """One frame of a periodic animation (period 1 in `phase`): bands that
    travel, a disc that orbits, and grain drawn fresh for every frame index,
    as a real loop's would be. uint8 (height, width, 3)."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    turn = 2 * np.pi * phase
    bands = 0.5 + 0.5 * np.sin(2 * np.pi * (xs / width * 3 + ys / height * 2) - turn)
    cx = width * (0.5 + 0.3 * math.cos(turn))
    cy = height * (0.5 + 0.3 * math.sin(turn))
    disc = np.exp(-(((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * (0.12 * width) ** 2)))
    tint = (np.array([0.9, 0.5, 0.3]) if scene == 0 else np.array([0.2, 0.6, 0.9]))[None, None, :]
    img = (0.6 * bands[..., None] * tint + 0.5 * disc[..., None]) * 255.0
    img += np.random.default_rng([seed, index]).normal(0.0, 4.0, (height, width))[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def loop_frames(kind: str, frames: int, *, width: int, height: int, seed: int = 0):
    """The frames of a loop of `kind`:

    seamless  the animation's period is exactly the loop: the frame after
              the last is the first.
    drift     the period is 3% longer than the loop: the seam jumps back
              3% of a cycle -- the error a loop cut by ear makes.
    cut       the second half is another scene: the seam is a hard cut.
    xfade     drift, with its last 12 frames cross-faded into the frames
              just before the first: the usual repair.
    """
    if kind not in LOOP_KINDS:
        raise ValueError(f"loop kind {kind!r} is not one of {', '.join(LOOP_KINDS)}")
    period = frames * (1.03 if kind in ("drift", "xfade") else 1.0)
    fade = min(12, frames // 4)
    for i in range(frames):
        scene = 1 if kind == "cut" and i >= frames // 2 else 0
        frame = loop_frame(i / period, i, width=width, height=height, scene=scene, seed=seed)
        if kind == "xfade" and i >= frames - fade:
            j = i - (frames - fade)  # 0..fade-1
            towards = loop_frame((j - fade) / period, i, width=width, height=height, seed=seed)
            w = (j + 1) / (fade + 1)
            frame = np.clip(frame * (1 - w) + towards * w, 0, 255).astype(np.uint8)
        yield frame


def write_loop(
    ffmpeg: str, path: Path, kind: str, *, frames: int, size=(720, 1280), fps: float = 24, seed: int = 0
) -> Path:
    """A loop of `kind` (see loop_frames), encoded with x264 like a canvas loop."""
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    proc = subprocess.Popen(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for frame in loop_frames(kind, frames, width=w, height=h, seed=seed):
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", errors="replace")
        proc.stderr.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg could not encode the {kind} loop: {err.strip().splitlines()[-1:]}")
    return path


# --------------------------------------------------------------------------
# the demo
# --------------------------------------------------------------------------
def demo_fixtures(python: str, repo: Path, folder: Path) -> Path:
    """examples/demo's synthetic song, photos and brief, in `folder`. Its
    photo seeds come from hash(), which Python salts per process unless
    PYTHONHASHSEED is set: set here, so every run benchmarks the same photos."""
    folder.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        [python, str(repo / "examples" / "demo" / "generate_fixtures.py"), "--out", str(folder)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"examples/demo/generate_fixtures.py failed: {proc.stderr.strip().splitlines()[-1:]}")
    return folder / "brief.yaml"
