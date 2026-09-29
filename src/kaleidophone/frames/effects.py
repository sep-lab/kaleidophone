"""
Per-pixel, stateful effects for the frame-program engine.

Every effect here takes float32 RGB frames shaped (H, W, 3), values 0..1, and
returns the same. They exist because two real releases needed effects that
ffmpeg's filter language can't express -- a picture that keeps some blocks and
forgets others, a smear assembled from a ring buffer of past frames, a grade
that decides per pixel whether a colour survives -- and each release hand-built
them in numpy. This module is those techniques, parameterised, with the
defaults the releases shipped with (and a note wherever a default is a
starting point rather than a recovered value). See kaleidophone/frames/__init__.py
for when to reach for this engine at all.

Conventions that are load-bearing, not style:

- Randomness comes from a seeded numpy Generator that each effect owns (or
  builds from an explicit seed) -- never numpy's global state, and never one
  stream shared between effects. With a shared stream, adding a grain pass
  would re-roll which blocks the memory canvas forgets.
- Stateful effects are callable objects (MemoryCanvas, SlitScan, GrainBank)
  or accumulators (MeanFace) with state_dict() / load_state_dict(), so the
  engine can checkpoint a render under a wall-clock limit and resume it
  bit-identically. A state_dict holds numpy arrays and plain scalars/strings
  only: checkpoints are loaded without pickle, so a checkpoint is data, never
  code. Configuration (schedules, sizes, seeds) is not state -- a resume
  rebuilds the effect with the same arguments and then loads the state.
- Sizes quoted "at 1080p" scale with the frame's long side / 1920, the factor
  both releases used, so a 640x360 proxy render previews the same look as the
  full-resolution one.
- No OpenCV. The releases resized, warped and blurred with cv2; here that is
  numpy, scipy.ndimage and Pillow, which kaleidophone already depends on
  (pyproject.toml records why OpenCV was removed).
"""

from __future__ import annotations

import functools
import io
import json
import math
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Union

import numpy as np
from PIL import Image
from scipy import ndimage

__all__ = [
    "GrainBank",
    "KaleidoBloom",
    "Keyframes",
    "MeanFace",
    "MemoryCanvas",
    "SlitScan",
    "ellipse_mask",
    "feedback_echo",
    "generation_loss",
    "kaleido_index_map",
    "mean_face",
    "pulse",
    "punch_zoom",
    "red_thread_grade",
    "smoothstep",
]

# Rec. 709 luma weights -- what "paler" and "brighter" are measured against.
_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

# Half of one 8-bit code value. A change smaller than this cannot survive the
# encoder's quantisation, so there is no point paying for it.
_INVISIBLE = 0.5 / 255.0

# A value, a callable of time, or keyframes -- anything _as_schedule accepts.
ScheduleLike = Union[float, Callable[[float], float], Sequence[tuple[float, float]]]


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------


def _scale(width: int, height: int) -> float:
    """Long side / 1920: the factor both releases scaled every pixel size by."""
    return max(int(width), int(height)) / 1920.0


def _rgb(img: Any, shape: tuple[int, int] | None = None) -> np.ndarray:
    """Validate an (H, W, 3) float frame and return it as float32 (no copy if it
    already is one)."""
    arr = np.asarray(img)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"expected an RGB frame shaped (H, W, 3), got {arr.shape}")
    if not np.issubdtype(arr.dtype, np.floating):
        raise TypeError(
            f"expected float RGB in 0..1, got {arr.dtype} -- divide 8-bit frames by 255 first"
        )
    if shape is not None and arr.shape[:2] != tuple(shape):
        raise ValueError(f"frame is {arr.shape[1]}x{arr.shape[0]}, this effect was built for {shape[1]}x{shape[0]}")
    return arr.astype(np.float32, copy=False)


def _luma(img: np.ndarray) -> np.ndarray:
    return img @ _LUMA


def _lerp(a: np.ndarray, b: np.ndarray, w: Any) -> np.ndarray:
    """a*(1-w) + b*w, written so that w == 0 gives exactly a and w == 1 exactly b.

    The shorter a + (b - a)*w is not exact at w == 1 in floating point, and a
    fully live region should be the live frame, not a value one ulp away from
    it -- the tests compare frames exactly, and so does any resume check.
    """
    return a * (1.0 - w) + b * w


def _rng_state(rng: np.random.Generator) -> str:
    return json.dumps(rng.bit_generator.state)


def _set_rng_state(rng: np.random.Generator, state: Any) -> None:
    rng.bit_generator.state = json.loads(str(state))


def smoothstep(edge0: float, edge1: float, x: Any) -> Any:
    """Hermite ease: 0 below edge0, 1 above edge1, an S-curve between.

    Every ramp in both releases eased this way rather than linearly. Works on
    scalars and arrays; edges may be given high-to-low for a falling ramp, and
    equal edges make a step.
    """
    arr = np.asarray(x)
    if not np.issubdtype(arr.dtype, np.floating):
        arr = arr.astype(np.float64)
    if edge0 == edge1:
        step = (arr >= edge1).astype(arr.dtype)
        return step if arr.ndim else float(step)
    t = np.clip((arr - edge0) / (edge1 - edge0), 0.0, 1.0)
    out = t * t * (3.0 - 2.0 * t)
    return out if arr.ndim else float(out)


class Keyframes:
    """A value over time from (time, value) keyframes, eased between neighbours.

    The memory canvas's refresh schedule was exactly this shape in the real
    release -- fully live for the first half, easing to 0.15 across the second
    verse, 0.02 for the outro -- written as a hand-tuned ladder of `if t < ...`
    branches. As keyframes it is data a brief can carry. Before the first
    keyframe the value holds at the first; after the last, at the last. Two
    keyframes at the same time make a jump (a schedule snapping back to 1.0
    on a cut).
    """

    def __init__(self, points: Iterable[tuple[float, float]]):
        pts = sorted(((float(t), float(v)) for t, v in points), key=lambda p: p[0])
        if not pts:
            raise ValueError("Keyframes needs at least one (time, value) point")
        self._t = np.array([p[0] for p in pts])
        self._v = np.array([p[1] for p in pts])

    def __call__(self, t: float) -> float:
        i = int(np.searchsorted(self._t, t, side="right"))
        if i == 0:
            return float(self._v[0])
        if i == len(self._t):
            return float(self._v[-1])
        t0, t1 = self._t[i - 1], self._t[i]
        v0, v1 = self._v[i - 1], self._v[i]
        return float(v0 + (v1 - v0) * smoothstep(t0, t1, t))

    def __repr__(self) -> str:
        return f"Keyframes({list(zip(self._t.tolist(), self._v.tolist()))})"


class _Constant:
    """A schedule that ignores time. A class rather than a lambda so an effect
    holding one can still cross a process boundary."""

    def __init__(self, value: float):
        self.value = float(value)

    def __call__(self, t: float) -> float:
        return self.value


def _as_schedule(value: ScheduleLike) -> Callable[[float], float]:
    if callable(value):
        return value
    if isinstance(value, (int, float, np.number)):
        return _Constant(float(value))
    return Keyframes(value)


def pulse(t: float, events: Any, tau: float = 0.12, lead: float = 0.04) -> float:
    """1.0 on an event (a beat, an onset), decaying as exp(-dt / tau) after it.

    tau=0.12 s for beats and 0.10 s for onsets are the real release's values --
    a hit that is gone within about a quarter second. `lead` lets an event up
    to one 25 fps frame in the future count as now, so the frame that is on
    screen when the beat lands is the one that carries it. `events` must be
    sorted ascending (AudioAnalysis.beat_times already is); pass a numpy array
    to avoid a conversion per call.
    """
    ev = np.asarray(events, dtype=np.float64)
    if ev.size == 0:
        return 0.0
    i = int(np.searchsorted(ev, t + lead, side="right")) - 1
    if i < 0:
        return 0.0
    return float(math.exp(-max(t - float(ev[i]), 0.0) / tau))


def ellipse_mask(
    height: int,
    width: int,
    center: tuple[float, float],
    radii: tuple[float, float],
    feather: float = 0.0,
) -> np.ndarray:
    """A (H, W) float32 mask: 1 inside the ellipse, 0 outside.

    Coordinates are pixels, x rightward and y downward, with pixel (i, j)
    covering [i, i+1) x [j, j+1) -- the same convention as Pillow's affine
    transforms, so an eye point from a tracker lands where you'd expect.
    `feather` is the soft edge as a fraction of the radius (0.15 -> the mask
    fades from 1 to 0 between 0.85 and 1.15 radii).
    """
    cx, cy = center
    rx, ry = radii
    if rx <= 0 or ry <= 0:
        return np.zeros((height, width), np.float32)
    ys = (np.arange(height, dtype=np.float32) + 0.5 - cy) / ry
    xs = (np.arange(width, dtype=np.float32) + 0.5 - cx) / rx
    d = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2)
    if feather <= 0:
        return (d < 1.0).astype(np.float32)
    return (1.0 - smoothstep(1.0 - feather, 1.0 + feather, d)).astype(np.float32)


def _zoom(img: np.ndarray, factor: float, center: tuple[float, float] | None = None) -> np.ndarray:
    """Scale the frame up by `factor` (>= 1) about `center`, keeping its size.

    A crop-and-resize through Pillow's float ("F") mode, one channel at a time:
    float precision throughout (no 8-bit round trip mid-chain), and the
    fastest float-precise option measured while writing this -- numpy
    gather-based bilinear and scipy.ndimage.affine_transform were both slower.
    """
    if factor < 1.0:
        raise ValueError(f"zoom factor must be >= 1 (zooming in), got {factor}")
    h, w = img.shape[:2]
    if center is None:
        cx, cy = w / 2.0, h / 2.0
    else:
        cx = min(max(float(center[0]), 0.0), float(w))
        cy = min(max(float(center[1]), 0.0), float(h))
    box = (cx - cx / factor, cy - cy / factor, cx + (w - cx) / factor, cy + (h - cy) / factor)
    out = np.empty((h, w, 3), np.float32)
    for c in range(3):
        channel = Image.fromarray(np.ascontiguousarray(img[..., c], dtype=np.float32))
        out[..., c] = np.asarray(channel.resize((w, h), Image.Resampling.BILINEAR, box=box))
    return out


# --------------------------------------------------------------------------
# MemoryCanvas -- "the video forgets its own footage"
# --------------------------------------------------------------------------


def _block_basis(n: int, size: int, count: int, sigma: float) -> np.ndarray:
    """(n, count) matrix whose column k is block k's indicator along one axis,
    Gaussian-blurred by `sigma` px.

    A block grid's pixel mask is separable -- row-block indicator times
    column-block indicator -- and so is a Gaussian blur of it. So the feathered
    full-frame mask of any per-block value grid V is By @ V @ Bx.T: two small
    matrix products instead of a full-frame blur per frame (measured while
    writing this, on a 2-core Linux VM at 1080p: ~1 ms against ~50 ms for
    scipy's gaussian_filter). With sigma 0 the columns are plain 0/1
    indicators and the product is an exact nearest-neighbour upsample.
    """
    basis = np.zeros((n, count), np.float32)
    basis[np.arange(n), np.arange(n) // size] = 1.0
    if sigma > 0:
        # "nearest" keeps the columns a partition of unity up to the frame edge,
        # so a fully refreshed region stays exactly live instead of darkening
        # toward the border.
        basis = ndimage.gaussian_filter1d(basis, sigma, axis=0, mode="nearest")
    return basis


class MemoryCanvas:
    """The video forgets its own footage.

    The frame is a grid of blocks. Each block keeps the last frame it was
    refreshed with and the time it was refreshed. Every frame, each block
    re-records itself with probability p(t) -- the `refresh` schedule --
    raised toward 1 by beat/onset bursts, so hits make the picture briefly
    remember. Blocks inside the protected ellipse (a tracked face) always
    refresh, until `protect_scale` shrinks it to zero and the face forgets
    too. A stale block pales toward `paper` with age. The effect is the
    concept; nothing on screen labels it.

    Why feathered: the real release's QA flagged the hard-edged block grid as
    reading as "glitch/pixelation" rather than memory, and named block size and
    feather as the dials. Here `feather` softens both the write of a refreshed
    block and the paling mask; feather=0 gives the hard grid back.

    Parameters (defaults are the real release's, at 1920x1080; pixel sizes
    scale with the long side):

    block: (48, 45) px blocks -- 40 x 24 of them at 1080p.
    refresh: p(t), as a constant, a callable, or (time, value) keyframes. The
        default 1.0 never forgets. The release: 1.0 through the first half,
        easing to 0.15 across the second verse, 0.02 for the outro, e.g.
        [(0, 1.0), (120, 1.0), (156, 0.15), (191, 0.02)].
    protect_scale: multiplier on the protected ellipse's radii over time
        (keyframes shrinking it to 0 over the release's closing seconds are
        what let the face go last).
    pale: how far a fully aged block moves toward paper (0.55; the release
        raised it to 0.8 for the ending -- pass keyframes to do the same).
    fade_seconds: age at which a block reaches full `pale` (22 s).
    paper: the colour stale blocks pale toward (0.86, 0.85, 0.83).
    feather: px at 1080p (3.0).
    burst_beat, burst_onset: how much a full beat / onset pulse raises the
        refresh probability toward 1 (0.35, 0.2).
    seed: the canvas owns its Generator; same seed + same inputs = same frames.

    Call it once per frame, in order: memory(frame, t, beat=..., onset=...,
    protect=(cx, cy, rx, ry)). `beat` and `onset` are 0..1 pulse values (see
    pulse()); `protect` is the ellipse in pixels, before protect_scale.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        block: tuple[int, int] = (48, 45),
        refresh: ScheduleLike = 1.0,
        protect_scale: ScheduleLike = 1.0,
        pale: ScheduleLike = 0.55,
        fade_seconds: float = 22.0,
        paper: tuple[float, float, float] = (0.86, 0.85, 0.83),
        feather: float = 3.0,
        burst_beat: float = 0.35,
        burst_onset: float = 0.2,
        seed: int = 0,
    ):
        self.width, self.height = int(width), int(height)
        s = _scale(self.width, self.height)
        self.block_w = max(4, round(block[0] * s))
        self.block_h = max(4, round(block[1] * s))
        self.cols = math.ceil(self.width / self.block_w)
        self.rows = math.ceil(self.height / self.block_h)
        sigma = feather * s
        self._by = _block_basis(self.height, self.block_h, self.rows, sigma)
        self._bx = _block_basis(self.width, self.block_w, self.cols, sigma)
        # Block centres, clipped to the frame so a partial edge block still
        # tests against where it actually is.
        self._centre_x = np.minimum((np.arange(self.cols) + 0.5) * self.block_w, self.width - 0.5)
        self._centre_y = np.minimum((np.arange(self.rows) + 0.5) * self.block_h, self.height - 0.5)
        self._refresh = _as_schedule(refresh)
        self._protect_scale = _as_schedule(protect_scale)
        self._pale = _as_schedule(pale)
        self.fade_seconds = float(fade_seconds)
        self._paper = np.asarray(paper, np.float32)
        self.burst_beat = float(burst_beat)
        self.burst_onset = float(burst_onset)
        self._rng = np.random.default_rng(seed)
        self.canvas: np.ndarray | None = None
        self.last_refresh = np.zeros((self.rows, self.cols), np.float64)

    def _upsample(self, per_block: np.ndarray) -> np.ndarray:
        return self._by @ (per_block.astype(np.float32) @ self._bx.T)

    def _protected_blocks(self, protect: tuple[float, float, float, float], t: float) -> np.ndarray:
        mask = np.zeros((self.rows, self.cols), bool)
        scale = float(self._protect_scale(t))
        if scale <= 0:
            return mask
        cx, cy, rx, ry = (float(v) for v in protect)
        if rx <= 0 or ry <= 0:
            return mask
        d = ((self._centre_x[None, :] - cx) / (rx * scale)) ** 2 + ((self._centre_y[:, None] - cy) / (ry * scale)) ** 2
        mask |= d < 1.0
        # An ellipse smaller than a block contains no block centre; without this
        # the face would stop being protected exactly when it is smallest.
        if 0 <= cx < self.width and 0 <= cy < self.height:
            mask[int(cy // self.block_h), int(cx // self.block_w)] = True
        return mask

    def _full_refresh(self, frame: np.ndarray, t: float) -> np.ndarray:
        self.canvas = frame.copy()
        self.last_refresh[:] = t
        return frame

    def __call__(
        self,
        frame: np.ndarray,
        t: float,
        *,
        beat: float = 0.0,
        onset: float = 0.0,
        protect: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        frame = _rgb(frame, (self.height, self.width))
        p = min(max(float(self._refresh(t)), 0.0), 1.0)
        if self.canvas is None or p >= 1.0:
            return self._full_refresh(frame, t)

        burst = min(1.0, max(0.0, beat) * self.burst_beat + max(0.0, onset) * self.burst_onset)
        prob = p + burst * (1.0 - p)
        mask = self._rng.random((self.rows, self.cols)) < prob
        if protect is not None:
            mask |= self._protected_blocks(protect, t)
        if mask.all():
            return self._full_refresh(frame, t)
        if mask.any():
            w = self._upsample(mask)[..., None]
            np.multiply(self.canvas, 1.0 - w, out=self.canvas)
            self.canvas += frame * w
            self.last_refresh[mask] = t

        age = np.maximum(t - self.last_refresh, 0.0)
        fade = np.clip(age / self.fade_seconds, 0.0, 1.0) * max(0.0, float(self._pale(t)))
        if fade.max() <= _INVISIBLE:
            # Never hand out the canvas itself: a later effect writing into the
            # returned frame in place would silently rewrite the memory.
            return self.canvas.copy()
        fm = self._upsample(fade)[..., None]
        return _lerp(self.canvas, self._paper, fm)

    def state_dict(self) -> dict[str, Any]:
        """Canvas, per-block refresh times and the Generator's exact state -- the
        three things the real engine's checkpoint had to carry to resume."""
        canvas = self.canvas if self.canvas is not None else np.zeros((0, 0, 3), np.float32)
        return {
            "canvas": canvas.copy(),
            "last_refresh": self.last_refresh.copy(),
            "rng": _rng_state(self._rng),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        canvas = np.asarray(state["canvas"], np.float32)
        last = np.asarray(state["last_refresh"], np.float64)
        if canvas.size and canvas.shape != (self.height, self.width, 3):
            raise ValueError(
                f"checkpointed canvas is {canvas.shape}, this MemoryCanvas is {(self.height, self.width, 3)}"
            )
        if last.shape != (self.rows, self.cols):
            raise ValueError(
                f"checkpointed block grid is {last.shape}, this MemoryCanvas has {(self.rows, self.cols)} -- "
                "rebuild it with the same size and block arguments as the run that wrote the checkpoint"
            )
        self.canvas = canvas.copy() if canvas.size else None
        self.last_refresh = last.copy()
        _set_rng_state(self._rng, state["rng"])


# --------------------------------------------------------------------------
# generation_loss -- a photocopy of a photocopy
# --------------------------------------------------------------------------

# Per-copy constants from the real release, at 1080p. Exposed as module
# constants rather than arguments: they are the character of the copier, and
# nobody tuned them per shot.
_QUALITY_STEP = 1.5  # JPEG quality lost per copy
_DRIFT_ROTATE_DEG = 0.06  # std of per-copy rotation
_DRIFT_SCALE = 0.0015  # std of per-copy scale error
_BLUR_PER_S = 0.45  # blur sigma = 0.45 * scale + 0.3 px
_BLUR_BASE = 0.3
_SPECKLE_STEP = 0.004  # speckle rate added per copy past `speckle_after`...
_SPECKLE_MAX = 0.01  # ...capped here -- see generation_loss's docstring
_SPECKLE_DARKEN = 0.35  # a toner speck keeps 35% of the value under it


def _jpeg(u8: np.ndarray, quality: int) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(u8).save(buf, format="JPEG", quality=int(quality))
    buf.seek(0)
    with Image.open(buf) as decoded:
        return np.asarray(decoded.convert("RGB"))


def _drift(u8: np.ndarray, rng: np.random.Generator, drift_px: float) -> np.ndarray:
    """Sub-pixel misregistration: a tiny rotation, scale error and shift about
    the centre, edge-replicated so the border never pulls in black.

    Black borders would be the burnt-negative failure again, one copy at a
    time: every generation would drag a darker frame edge further in.
    """
    h, w = u8.shape[:2]
    theta = math.radians(rng.normal(0.0, _DRIFT_ROTATE_DEG))
    zoom = 1.0 + rng.normal(0.0, _DRIFT_SCALE)
    dx, dy = rng.normal(0.0, drift_px, size=2)
    # Output -> input map (what Pillow wants): in = c + R(-theta)/zoom (out - c - d).
    cos, sin = math.cos(theta) / zoom, math.sin(theta) / zoom
    cx, cy = w / 2.0, h / 2.0
    ox, oy = cx + dx, cy + dy
    radius = math.hypot(w, h) / 2.0
    pad = math.ceil(abs(dx) + abs(dy) + (abs(theta) + abs(1.0 - 1.0 / zoom)) * radius) + 2
    padded = np.pad(u8, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    data = (
        cos, sin, cx - cos * ox - sin * oy + pad,
        -sin, cos, cy + sin * ox - cos * oy + pad,
    )
    moved = Image.fromarray(padded).transform((w, h), Image.Transform.AFFINE, data, resample=Image.Resampling.BILINEAR)
    return np.asarray(moved)


def generation_loss(
    img: np.ndarray,
    generations: int,
    seed: int = 0,
    *,
    start: int = 0,
    quality: tuple[int, int] = (60, 14),
    drift: float = 1.0,
    desaturate: float = 0.10,
    contrast: float = 1.028,
    lift: float = 0.011,
    speckle_after: int = 8,
    paper: tuple[float, float, float] = (1.0, 0.985, 0.955),
) -> np.ndarray:
    """A photocopy of a photocopy, `generations` times over.

    Each copy: a JPEG re-encode whose quality falls 1.5 per copy from 60 to a
    floor of 14 (Pillow); a sub-pixel drift (rotation, scale error, a ~`drift`
    px shift at 1080p); a slight blur; 10% desaturation; contrast x1.028 and
    brightness +0.011; toner speckle from the copy after generation
    `speckle_after`; a paper tint that reaches `paper` after ten copies.

    Copies must get PALER, not darker. The release's first version went dark
    with each generation and read as a burnt negative, not as memory wearing
    thin; the +0.011 lift is the fix, and everything else here is arranged not
    to undo it: frames are requantised with rounding (truncating to 8 bits
    would lose half a code value per copy, always downward), drift replicates
    the edge rather than pulling in black, and the speckle rate -- which in
    the release grew by 0.4% of pixels every copy, without limit -- is capped
    at 1% per copy. Measured on a synthetic 320x180 gradient (not a real
    frame), forty copies: uncapped, mean luminance peaks at generation 14 and
    is darker than the original from generation 24 on -- the burnt negative
    again, at the generations the release's late recall flashes used; capped,
    it rises through all forty.

    Each copy draws from its own (seed, generation) stream, so photocopying a
    held frame once per 0.3 s -- generation_loss(frame, 1, seed, start=k) for
    k = 0, 1, 2... -- gives exactly the frames one call with generations=k+1
    would. (The release's hold restarted the schedule on every call, so its
    quality never fell and its speckle never arrived.) A copy is a few full
    passes over the frame, so cache recalls by (frame, generations) rather than
    re-running forty generations per displayed frame.
    """
    frame = _rgb(img)
    if generations <= 0:
        return frame.copy()
    h, w = frame.shape[:2]
    s = _scale(w, h)
    q_hi, q_lo = quality
    blur = _BLUR_PER_S * s + _BLUR_BASE
    tint = np.asarray(paper, np.float32) ** np.float32(1.0 / 10.0)
    u8 = (np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    for k in range(start, start + generations):
        rng = np.random.default_rng([int(seed), k])
        u8 = _jpeg(u8, max(q_lo, round(q_hi - _QUALITY_STEP * k)))
        u8 = _drift(u8, rng, drift * s)
        f = u8.astype(np.float32) * np.float32(1.0 / 255.0)
        f = ndimage.gaussian_filter(f, (blur, blur, 0.0), mode="nearest")
        grey = f.mean(axis=2, keepdims=True)
        f = f * (1.0 - desaturate) + grey * desaturate
        f = (f - 0.5) * contrast + 0.5 + lift
        f *= tint
        if k >= speckle_after:
            rate = min(_SPECKLE_STEP * (k - speckle_after + 1), _SPECKLE_MAX)
            speck = rng.random((h, w)) < rate
            f[speck] *= _SPECKLE_DARKEN
        u8 = (np.clip(f, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return u8.astype(np.float32) * np.float32(1.0 / 255.0)


# --------------------------------------------------------------------------
# SlitScan -- time pulls the subject away
# --------------------------------------------------------------------------


class SlitScan:
    """A ring buffer of past frames, read back with a per-column (or per-row)
    time offset: near `anchor` the picture is live, and the further a column
    is from it the older the moment it shows.

    The delay across the frame follows an eased curve, delay = amount *
    (depth - 1) * u ** ease with u the distance from the anchor (0..1): with
    ease > 1 the region around the anchor stays close to live and the far edge
    is dragged back hardest, which is what reads as time pulling the subject
    away rather than as a uniform smear. `hold` keeps a region live on top of
    that -- the real release used it to keep a face sharp on a cover while
    the rest of the frame smeared.

    The engine that shipped this is lost; depth, anchor and ease are starting
    points, not recovered values. The buffer stores frames as uint8: 24 frames
    of 1080p float32 is ~600 MB per worker, uint8 a quarter of that. Columns at
    zero delay come from the exact float frame, so amount=0 returns the input
    untouched.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        depth: int = 24,
        axis: str = "x",
        anchor: float = 0.0,
        ease: float = 2.0,
    ):
        if axis not in ("x", "y"):
            raise ValueError(f"axis must be 'x' (per-column) or 'y' (per-row), got {axis!r}")
        if depth < 1:
            raise ValueError("depth must be at least 1 frame")
        self.width, self.height = int(width), int(height)
        self.depth = int(depth)
        self.axis = axis
        self.anchor = min(max(float(anchor), 0.0), 1.0)
        self.ease = float(ease)
        self._ring = np.zeros((self.depth, self.height, self.width, 3), np.uint8)
        self._head = -1
        self._count = 0

    def _push(self, frame: np.ndarray) -> None:
        self._head = (self._head + 1) % self.depth
        self._ring[self._head] = (np.clip(frame, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        self._count = min(self._count + 1, self.depth)

    def delays(self, amount: float = 1.0) -> np.ndarray:
        """Frames of delay for every column (axis 'x') or row (axis 'y')."""
        n = self.width if self.axis == "x" else self.height
        u = np.abs((np.arange(n) + 0.5) / n - self.anchor)
        far = max(self.anchor, 1.0 - self.anchor)
        u = u / far if far > 0 else u
        amount = min(max(float(amount), 0.0), 1.0)
        d = np.rint(amount * (self.depth - 1) * u**self.ease).astype(np.int64)
        return np.clip(d, 0, max(self._count - 1, 0))

    def __call__(self, frame: np.ndarray, amount: float = 1.0, *, hold: Any = None) -> np.ndarray:
        """Push `frame`, return the smeared view. `hold` is an (H, W) 0..1 mask or
        an ellipse (cx, cy, rx, ry) in pixels that stays live."""
        frame = _rgb(frame, (self.height, self.width))
        self._push(frame)
        delays = self.delays(amount)
        if not delays.any():
            return frame
        n = delays.size
        starts = np.concatenate(([0], np.flatnonzero(np.diff(delays)) + 1))
        ends = np.concatenate((starts[1:], [n]))
        out = np.empty_like(frame)
        for a, b in zip(starts.tolist(), ends.tolist()):
            d = int(delays[a])
            span = (slice(None), slice(a, b)) if self.axis == "x" else (slice(a, b),)
            if d == 0:
                out[span] = frame[span]
            else:
                old = self._ring[(self._head - d) % self.depth]
                np.multiply(old[span], np.float32(1.0 / 255.0), out=out[span])
        if hold is not None:
            if isinstance(hold, np.ndarray) and hold.ndim == 2:
                m = hold.astype(np.float32)
            else:
                cx, cy, rx, ry = hold
                m = ellipse_mask(self.height, self.width, (cx, cy), (rx, ry), feather=0.15)
            out = _lerp(out, frame, m[..., None])
        return out

    def state_dict(self) -> dict[str, Any]:
        """The ring buffer is the bulk of a checkpoint: depth x H x W x 3 bytes."""
        return {"ring": self._ring.copy(), "head": int(self._head), "count": int(self._count)}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        ring = np.asarray(state["ring"], np.uint8)
        if ring.shape != self._ring.shape:
            raise ValueError(f"checkpointed ring buffer is {ring.shape}, this SlitScan has {self._ring.shape}")
        self._ring = ring.copy()
        self._head = int(state["head"])
        self._count = int(state["count"])


# --------------------------------------------------------------------------
# red_thread_grade -- selective survival
# --------------------------------------------------------------------------


def red_thread_grade(
    img: np.ndarray,
    protect_hue: float = 0.0,
    *,
    band: float = 10.0,
    softness: float = 10.0,
    min_chroma: float = 0.2,
    shadow: tuple[float, float, float] = (0.10, 0.09, 0.24),
    highlight: tuple[float, float, float] = (0.93, 0.89, 0.80),
    amount: float = 1.0,
) -> np.ndarray:
    """Drain the world to two tones -- indigo shadows, bone highlights -- except
    one hue band, which survives untouched.

    The grade is the concept, not a look laid over it: in the release, red was
    the only colour that refused to say goodbye, so every pixel is asked how
    red it is and only the answer decides whether it keeps its colour.

    "How red" is per-pixel redness generalised to any hue: the pixel's chroma
    vector in opponent space (a = R - (G+B)/2, b = sqrt(3)/2 (G-B)) projected
    onto the protected hue's direction -- for red that projection is literally
    R - (G+B)/2. A pixel survives when its hue is within `band` degrees of
    `protect_hue` (fading out over another `softness` degrees) AND its chroma
    is above `min_chroma` (fading in up to twice that). The chroma gate is
    what keeps skin from glowing: skin sits ~20 degrees from red at modest
    chroma, a red tie or a flower near 0 degrees at high chroma, and the
    defaults are set on that gap. The engine that shipped this is lost; the
    band, chroma and the two tones here are chosen, not recovered.

    `amount` blends from the original (0) to the full grade (1), so the drain
    can arrive over a song.
    """
    frame = _rgb(img)
    r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
    opp_a = r - 0.5 * (g + b)
    opp_b = np.float32(math.sqrt(3.0) / 2.0) * (g - b)
    chroma = np.sqrt(opp_a * opp_a + opp_b * opp_b)
    hue = math.radians(protect_hue)
    along = opp_a * np.float32(math.cos(hue)) + opp_b * np.float32(math.sin(hue))
    cos_offset = along / np.maximum(chroma, 1e-6)
    near = smoothstep(math.cos(math.radians(band + softness)), math.cos(math.radians(band)), cos_offset)
    vivid = smoothstep(min_chroma, 2.0 * min_chroma, chroma)
    keep = (near * vivid).astype(np.float32)[..., None]
    lo = np.asarray(shadow, np.float32)
    hi = np.asarray(highlight, np.float32)
    tone = lo + (hi - lo) * _luma(frame)[..., None]
    graded = _lerp(tone, frame, keep)
    amount = min(max(float(amount), 0.0), 1.0)
    return graded if amount >= 1.0 else _lerp(frame, graded, amount)


# --------------------------------------------------------------------------
# KaleidoBloom -- a polar mirror, only at peaks
# --------------------------------------------------------------------------


def _reflect(v: np.ndarray, n: int) -> np.ndarray:
    period = 2 * n
    v = np.mod(v, period)
    return np.where(v >= n, period - 1 - v, v)


@functools.lru_cache(maxsize=8)
def kaleido_index_map(height: int, width: int, k: int, cx: int, cy: int, rotation: float = 0.0) -> np.ndarray:
    """Flat source-pixel index for every output pixel of a k-wedge polar mirror.

    Folding every angle into one mirrored wedge is a few full-frame
    trigonometric passes; applying a precomputed map is one gather. Cached by
    (size, k, centre, rotation) -- a map at 1080p is 16 MB, so eight of them
    is the ceiling. A centre that follows a tracked point changes the key
    every frame and never hits the cache: snap it to a coarse grid first.
    """
    if k < 1:
        raise ValueError("k must be at least 1 wedge")
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float64)
    dx = xx + 0.5 - cx
    dy = yy + 0.5 - cy
    radius = np.hypot(dx, dy)
    seg = 2.0 * math.pi / k
    theta = np.mod(np.arctan2(dy, dx), seg)
    theta = np.minimum(theta, seg - theta) + rotation
    sx = _reflect(np.rint(cx + radius * np.cos(theta) - 0.5).astype(np.int64), width)
    sy = _reflect(np.rint(cy + radius * np.sin(theta) - 0.5).astype(np.int64), height)
    index = (sy * width + sx).astype(np.intp).ravel()
    index.flags.writeable = False  # shared by every caller through the cache
    return index


class KaleidoBloom:
    """A polar-mirror kaleidoscope, mixed in only at musical peaks.

    One thin wedge of the frame is mirrored around `center` into k wedges.
    `amount` is the mix -- drive it from the song so the bloom exists only at
    peaks, e.g. amount = smoothstep(0.8, 0.95, energy). At amount 0 it costs
    nothing (no map is even built), which is what lets it sit in every frame's
    chain and wake only when the music does. The index maps are cached
    (kaleido_index_map) because they depend only on size, k and centre.

    `center` is in pixels, (x, y); None means the frame centre. It is rounded to
    whole pixels for the cache key. k=6 is a starting point -- the engine that
    shipped this is lost.
    """

    def __init__(self, k: int = 6, center: tuple[float, float] | None = None, rotation: float = 0.0):
        self.k = int(k)
        self.center = center
        self.rotation = float(rotation)

    def __call__(self, img: np.ndarray, amount: float, *, center: tuple[float, float] | None = None) -> np.ndarray:
        frame = _rgb(img)
        amount = min(max(float(amount), 0.0), 1.0)
        if amount <= 0.0:
            return frame
        h, w = frame.shape[:2]
        c = center if center is not None else self.center
        cx, cy = (w // 2, h // 2) if c is None else (round(c[0]), round(c[1]))
        index = kaleido_index_map(h, w, self.k, int(cx), int(cy), self.rotation)
        folded = frame.reshape(-1, 3)[index].reshape(h, w, 3)
        return folded if amount >= 1.0 else _lerp(frame, folded, amount)


# --------------------------------------------------------------------------
# GrainBank -- a performance pattern, not an effect
# --------------------------------------------------------------------------


class GrainBank:
    """Film grain from a bank of pre-generated full-resolution tiles.

    Measured on a real release: a fresh rng.normal() field per frame at
    1080x1920 was the single hottest operation in that engine. So the bank
    draws `tiles` Gaussian fields once, blurs each slightly (0.95 px at 1080p,
    as the release did) so the grain clumps like film rather than fizzing per
    pixel, and per frame picks one and rolls it by a random offset -- a copy,
    not a generation. Six tiles times every (x, y) offset is millions of
    placements, far more than a render has frames. Tiles are blurred with
    wrap-around edges, so a rolled tile has no seam.

    Tiles are a pure function of (size, seed): a checkpoint stores only the
    Generator that picks them, and a resume regenerates the bank. Grain is
    luminance-only and a touch stronger on darker frames, as in the release;
    `amount` 0.05 is its default strength, tuned at 1080p.
    """

    def __init__(self, width: int, height: int, *, tiles: int = 6, sigma: float = 0.95, seed: int = 7):
        if tiles < 1:
            raise ValueError("a GrainBank needs at least one tile")
        self.width, self.height = int(width), int(height)
        blur = max(0.6, sigma * _scale(self.width, self.height))
        bank = np.random.default_rng([int(seed), 0])
        self._tiles = [
            ndimage.gaussian_filter(
                bank.standard_normal((self.height, self.width), dtype=np.float32), blur, mode="wrap"
            )[..., None]
            for _ in range(int(tiles))
        ]
        # A separate stream for the picks, so the tiles never depend on how
        # many frames have been drawn.
        self._rng = np.random.default_rng([int(seed), 1])

    def sample(self) -> np.ndarray:
        """One frame of grain, (H, W, 1), zero-mean."""
        tile = self._tiles[int(self._rng.integers(len(self._tiles)))]
        dy = int(self._rng.integers(self.height))
        dx = int(self._rng.integers(self.width))
        return np.roll(tile, (dy, dx), axis=(0, 1))

    def __call__(self, img: np.ndarray, amount: float = 0.05) -> np.ndarray:
        frame = _rgb(img, (self.height, self.width))
        grain = self.sample()
        strength = amount * (0.6 + 0.4 * (1.0 - float(frame.mean())))
        return np.clip(frame + grain * np.float32(strength), 0.0, 1.0)

    def state_dict(self) -> dict[str, Any]:
        return {"rng": _rng_state(self._rng)}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        _set_rng_state(self._rng, state["rng"])


# --------------------------------------------------------------------------
# feedback_echo / punch_zoom -- field-proven in docs/case-studies/love.md
# --------------------------------------------------------------------------


def feedback_echo(
    prev: np.ndarray | None,
    cur: np.ndarray,
    zoom: float = 1.02,
    mix: float = 0.5,
    *,
    decay: float = 0.88,
    lighten: bool = False,
) -> np.ndarray:
    """Analog video feedback: blend a slightly zoomed copy of the previous
    OUTPUT frame into the current one.

    Cuts become morphs; at higher `mix` this was the cheapest "hypnosis" dial
    the reference case study found (docs/case-studies/love.md), run strong in
    quiet passages and low under strobes so hits stay sharp. `prev` is the
    previous OUTPUT -- what the program returned last frame, kept in its
    state -- not the previous source frame, or it is a crossfade, not feedback.

    lighten=True is the other release's ghost trail: max(cur, prev * decay),
    so only highlights leave trails. `decay` (0.88, from that release) applies
    only there: a plain mix already fades each echo by (1 - mix) per frame,
    while max() alone would hold a bright pixel forever. zoom=1.02 and mix=0.5
    are starting points; neither release recorded fixed values.
    """
    frame = _rgb(cur)
    if prev is None or mix <= 0.0:
        return frame
    ghost = _rgb(prev, frame.shape[:2])
    if zoom != 1.0:
        ghost = _zoom(ghost, zoom)
    if lighten:
        ghost = np.maximum(frame, ghost * np.float32(decay))
    return _lerp(frame, ghost, min(float(mix), 1.0))


def punch_zoom(img: np.ndarray, amount: float, *, center: tuple[float, float] | None = None) -> np.ndarray:
    """A beat-triggered zoom kick: scale the frame up by (1 + amount) about
    `center` (pixels; None = the frame centre).

    Drive `amount` with a decaying pulse -- amount = a * pulse(t, beats, tau) --
    which is the case study's scale += a * exp(-k * dt), fired on every beat in
    quiet sections and on strong onsets in loud ones. That is what "react to
    the waves" turned out to mean in practice (docs/case-studies/love.md).
    Amounts too small to move an edge pixel return the frame untouched.
    """
    frame = _rgb(img)
    if amount * max(frame.shape[:2]) / 2.0 < 0.05:
        return frame
    return _zoom(frame, 1.0 + float(amount), center)


# --------------------------------------------------------------------------
# mean_face -- the average of every frame you appear in
# --------------------------------------------------------------------------


def _similarity_to(src_l, src_r, dst_l, dst_r) -> tuple[float, ...]:
    """Pillow AFFINE data (output -> input) for the similarity transform that
    carries the source eyes onto the destination eyes."""
    vx, vy = src_r[0] - src_l[0], src_r[1] - src_l[1]
    tx, ty = dst_r[0] - dst_l[0], dst_r[1] - dst_l[1]
    scale = math.hypot(tx, ty) / math.hypot(vx, vy)
    angle = math.atan2(ty, tx) - math.atan2(vy, vx)
    # input = src_l + R(-angle)/scale (output - dst_l)
    a = math.cos(angle) / scale
    b = math.sin(angle) / scale
    return (
        a, b, src_l[0] - a * dst_l[0] - b * dst_l[1],
        -b, a, src_l[1] + b * dst_l[0] - a * dst_l[1],
    )


class MeanFace:
    """Resumable accumulator behind mean_face(): add frames one at a time,
    checkpoint the running sum, take the result() at the end.

    The release's version averaged every usable frame of the performance at
    1080p under a 180 s-per-call limit, decoding sequentially and
    checkpointing the running sum between calls; this is that loop's state,
    in the same state_dict() shape as the other effects.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        eyes: tuple[tuple[float, float], tuple[float, float]] = ((0.415, 0.40), (0.585, 0.40)),
        eye_range: tuple[float, float] = (0.028, 0.22),
    ):
        self.width, self.height = int(width), int(height)
        (lx, ly), (rx, ry) = eyes
        self._dst_l = (lx * self.width, ly * self.height)
        self._dst_r = (rx * self.width, ry * self.height)
        self.eye_range = eye_range
        self._sum = np.zeros((self.height, self.width, 3), np.float64)
        self._weight = np.zeros((self.height, self.width), np.float64)
        self._ones: dict[tuple[int, int], Image.Image] = {}
        self.count = 0
        self.rejected = 0

    def add(self, frame: np.ndarray, eye_points: Any) -> bool:
        """Warp `frame` so its eyes land on the target eyes and add it. Returns
        False (and counts a rejection) for a frame with no eye points or an
        implausible eye distance."""
        if eye_points is None:
            self.rejected += 1
            return False
        (lx, ly), (rx, ry) = eye_points
        arr = np.asarray(frame)
        h, w = arr.shape[:2]
        spacing = math.hypot(rx - lx, ry - ly) / w
        if not (self.eye_range[0] <= spacing <= self.eye_range[1]):
            self.rejected += 1
            return False
        u8 = arr if arr.dtype == np.uint8 else (np.clip(_rgb(arr), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        data = _similarity_to((lx, ly), (rx, ry), self._dst_l, self._dst_r)
        size = (self.width, self.height)
        warped = Image.fromarray(u8).transform(size, Image.Transform.AFFINE, data, resample=Image.Resampling.BILINEAR)
        if (w, h) not in self._ones:
            self._ones[(w, h)] = Image.new("F", (w, h), 1.0)
        cover = self._ones[(w, h)].transform(size, Image.Transform.AFFINE, data, resample=Image.Resampling.BILINEAR)
        # Pixels a frame doesn't cover add nothing and weigh nothing: warped
        # colour is already zero there, so sum/weight is a coverage-weighted
        # mean with no black borders dragged in from rotated frames.
        self._sum += np.asarray(warped, np.float64) * (1.0 / 255.0)
        self._weight += np.asarray(cover, np.float64)
        self.count += 1
        return True

    def result(self) -> np.ndarray:
        if self.count == 0:
            raise ValueError(
                f"no frame was accepted ({self.rejected} rejected) -- check the eye points and eye_range"
            )
        out = np.zeros_like(self._sum)
        np.divide(self._sum, self._weight[..., None], out=out, where=self._weight[..., None] > 1e-6)
        return np.clip(out, 0.0, 1.0).astype(np.float32)

    def state_dict(self) -> dict[str, Any]:
        return {
            "sum": self._sum.copy(),
            "weight": self._weight.copy(),
            "count": int(self.count),
            "rejected": int(self.rejected),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        total = np.asarray(state["sum"], np.float64)
        if total.shape != self._sum.shape:
            raise ValueError(f"checkpointed sum is {total.shape}, this MeanFace is {self._sum.shape}")
        self._sum = total.copy()
        self._weight = np.asarray(state["weight"], np.float64).copy()
        self.count = int(state["count"])
        self.rejected = int(state["rejected"])


def mean_face(
    frames: Iterable[np.ndarray],
    eye_points: Iterable[Any],
    *,
    size: tuple[int, int] | None = None,
    eyes: tuple[tuple[float, float], tuple[float, float]] = ((0.415, 0.40), (0.585, 0.40)),
    eye_range: tuple[float, float] = (0.028, 0.22),
) -> np.ndarray:
    """The eye-aligned average of every frame a face appears in.

    Each frame is carried onto the target eyes by the similarity transform
    (rotation, uniform scale, shift) that its two eye points define,
    accumulated, and divided -- the stable features (eyes, the face's outline)
    sharpen while everything that moved dissolves. `eye_points` gives one
    ((left_x, left_y), (right_x, right_y)) pair in pixels per frame, or None
    to skip a frame. Landmarks come from whatever tracker you run beforehand
    (the release used MediaPipe's iris points on proxies): this package takes
    points, not a detector dependency.

    `eyes` are the target positions as fractions of the output `size` (default:
    the first frame's size) -- the release's (0.415, 0.40) / (0.585, 0.40) for
    16:9; it used (0.36, 0.40) / (0.64, 0.40) for 9:16. `eye_range` rejects
    frames whose eye distance, as a fraction of frame width, is implausible: a
    detector glitch that puts the eyes a few pixels apart would otherwise blow
    that frame up many times over and smear it across the whole mean.

    Means of different takes differ in character -- one averaged over direct
    gaze, another over a soft smile; in the release the all-frames mean ended
    the film and one take's mean, with sharper eyes, became a cover -- so
    compute several and pick by story. For long clips under a time limit, use
    MeanFace directly and checkpoint it between calls.
    """
    acc: MeanFace | None = None
    for frame, eyes_in_frame in zip(frames, eye_points):
        if acc is None:
            h, w = np.asarray(frame).shape[:2]
            ow, oh = size if size is not None else (w, h)
            acc = MeanFace(ow, oh, eyes=eyes, eye_range=eye_range)
        acc.add(frame, eyes_in_frame)
    if acc is None:
        raise ValueError("mean_face() needs at least one frame")
    return acc.result()
