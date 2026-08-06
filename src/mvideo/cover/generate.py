"""
Procedural cover art: a square image built directly from the song's energy
envelope, in one station's palette -- an abstract "frequency stack" of
horizontal bands, one per time-slice, sized and colored by that slice's
loudness. Same AudioAnalysis the video uses; two different-looking outputs
from one source of truth, no AI model call.

This is a deliberately simple deterministic default, not a claim that it's
the best-looking cover mvideo could produce. Plugging in an actual image
model here (SDXL, a hosted API, whatever) is a real, documented next step --
see ROADMAP.md, "AI-assisted cover art" -- kept out of this file so the
default path never needs an API key or network access to produce something.
"""

from __future__ import annotations

import colorsys

import numpy as np
from PIL import Image

from mvideo.audio.analysis import AudioAnalysis
from mvideo.timeline.schema import StationConfig


def generate_cover(
    analysis: AudioAnalysis,
    station: StationConfig,
    out_path: str,
    *,
    size: int = 3000,
    bands: int = 96,
    seed: int = 0,
) -> str:
    levels = _band_levels(analysis, bands)
    rng = np.random.default_rng(seed)

    canvas = np.zeros((size, size, 3), dtype=np.float32)
    band_h = size / bands
    y = 0.0
    for level in levels:
        h = band_h * (0.5 + level)
        y0, y1 = int(max(0, size - min(y + h, size))), int(size - y)
        if y1 <= y0:
            break
        canvas[y0:y1, :, :] = _band_color(station, level)
        y += h

    canvas = _soften_seams(canvas)
    canvas = _apply_grain(canvas, station.grain, rng)
    canvas = _apply_vignette(canvas, station.vignette)

    img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")
    img.save(out_path, quality=95)
    return out_path


def pick_cover_station(brief, analysis: AudioAnalysis) -> StationConfig:
    """The station of whichever section contains the song's single loudest
    instant -- a cheap, honest proxy for 'the moment that represents this song'."""
    stations = {s.name: s for s in brief.stations}
    if brief.output.cover_station:
        return stations[brief.output.cover_station]

    if analysis.rms_db and analysis.rms_times:
        peak_idx = max(range(len(analysis.rms_db)), key=lambda i: analysis.rms_db[i])
        peak_t = analysis.rms_times[peak_idx]
        for section in brief.sections:
            if section.start <= peak_t < section.end:
                return stations[section.station]

    return stations[brief.sections[0].station]


def _band_levels(analysis: AudioAnalysis, bands: int) -> list[float]:
    rms = np.array(analysis.rms_db, dtype=np.float32)
    if len(rms) == 0:
        return [0.5] * bands
    lo, hi = float(rms.min()), float(rms.max())
    span = (hi - lo) or 1.0
    norm = (rms - lo) / span
    edges = np.linspace(0, len(norm), bands + 1).astype(int)
    levels = []
    for i in range(bands):
        chunk = norm[edges[i] : edges[i + 1]]
        levels.append(float(chunk.mean()) if len(chunk) else 0.0)
    return levels


def _band_color(station: StationConfig, level: float) -> tuple[float, float, float]:
    if station.duotone:
        shadow, highlight = (_hex_to_rgb(c) for c in station.duotone)
        return tuple(shadow[c] + (highlight[c] - shadow[c]) * level for c in range(3))
    hue = 0.08 if station.temperature >= 0 else 0.55  # warm amber vs. cool blue, no duotone configured
    r, g, b = colorsys.hsv_to_rgb(hue, min(1.0, station.saturation), 0.25 + 0.7 * level)
    return (r * 255, g * 255, b * 255)


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(float(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def _soften_seams(canvas: np.ndarray) -> np.ndarray:
    """A cheap vertical box blur (a few shifted sums) instead of a full
    Gaussian -- softens hard band edges without pulling in another dependency."""
    out = canvas.copy()
    for shift in (1, 2, 3):
        out[shift:] += canvas[:-shift]
        out[:-shift] += canvas[shift:]
    return out / 7.0


def _apply_grain(canvas: np.ndarray, amount: float, rng: np.random.Generator) -> np.ndarray:
    if amount <= 0:
        return canvas
    return canvas + rng.normal(0, amount * 30, canvas.shape).astype(np.float32)


def _apply_vignette(canvas: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return canvas
    size = canvas.shape[0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dist = np.sqrt((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size / 2 * 1.4142)
    falloff = 1.0 - amount * np.clip(dist, 0, 1) ** 2
    return canvas * falloff[..., None]
