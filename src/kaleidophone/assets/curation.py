"""
Lightweight, deterministic asset curation: scan a media folder and, if asked,
score each photo against a station's color palette. No AI vision call -- this
is a fast heuristic (mean hue/saturation vs. the station's target), good
enough to pre-sort a few hundred photos into buckets a person then skims and
corrects. See docs/decisions/0002-deterministic-edit-engine.md for why.
"""

from __future__ import annotations

import colorsys
import os
from dataclasses import dataclass

import cv2
import numpy as np

from kaleidophone.timeline.schema import StationConfig

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


@dataclass(frozen=True)
class MediaAsset:
    path: str
    kind: str  # "image" | "video"
    mean_hue: float
    mean_saturation: float
    mean_brightness: float


def scan_media(directory: str) -> list[MediaAsset]:
    """Walk `directory` and score every image/video found. Order is
    deterministic (sorted) so the same folder always curates the same way."""
    assets = []
    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            path = os.path.join(root, fname)
            if ext in IMAGE_EXTS:
                assets.append(_score_image(path))
            elif ext in VIDEO_EXTS:
                assets.append(_score_video_first_frame(path))
    return sorted(assets, key=lambda a: a.path)


def _score_image(path: str) -> MediaAsset:
    img = cv2.imread(path)
    if img is None:
        return MediaAsset(path=path, kind="image", mean_hue=0.0, mean_saturation=0.0, mean_brightness=0.0)
    return _score_bgr(path, "image", img)


def _score_video_first_frame(path: str) -> MediaAsset:
    cap = cv2.VideoCapture(path)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return MediaAsset(path=path, kind="video", mean_hue=0.0, mean_saturation=0.0, mean_brightness=0.0)
    return _score_bgr(path, "video", frame)


def _score_bgr(path: str, kind: str, img: np.ndarray) -> MediaAsset:
    small = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(np.float32)
    return MediaAsset(
        path=path,
        kind=kind,
        mean_hue=float(hsv[..., 0].mean()),
        mean_saturation=float(hsv[..., 1].mean() / 255.0),
        mean_brightness=float(hsv[..., 2].mean() / 255.0),
    )


def score_for_station(asset: MediaAsset, station: StationConfig) -> float:
    """Higher is a better fit. Cheap and explainable, and wrong often enough
    that it's meant as a sort order to skim, not a decision to trust blindly."""
    hue_dist = min(
        abs(asset.mean_hue - _target_hue(station)), 180 - abs(asset.mean_hue - _target_hue(station))
    )
    hue_score = 1.0 - (hue_dist / 90.0)

    sat_target = max(0.0, min(1.0, 0.5 + station.saturation / 4.0))
    sat_score = 1.0 - abs(asset.mean_saturation - sat_target)

    bright_target = (
        0.35 if station.temperature < 0 else 0.55
    )  # noir-leaning stations skew toward darker source material
    bright_score = 1.0 - abs(asset.mean_brightness - bright_target)

    return 0.5 * hue_score + 0.3 * sat_score + 0.2 * bright_score


def _target_hue(station: StationConfig) -> float:
    """Prefer the station's own duotone highlight -- a real, per-station color
    -- over a coarse warm/cool guess from temperature alone. Without this,
    every warm-temperature station (amber-room, gold-hour, fire-leak, ...)
    scores photos almost identically and curation collapses onto whichever
    one wins the tie, starving the others."""
    if station.duotone:
        h = station.duotone[1].lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        hue, _sat, _val = colorsys.rgb_to_hsv(r, g, b)
        return hue * 180.0  # match OpenCV's 0..180 hue range
    return 15.0 if station.temperature >= 0 else 100.0


def suggest_stations(assets: list[MediaAsset], stations: list[StationConfig]) -> dict[str, list[MediaAsset]]:
    """Assign every asset to its best-scoring station -- a starting sort, not a final cut."""
    buckets: dict[str, list[MediaAsset]] = {s.name: [] for s in stations}
    for asset in assets:
        best = max(stations, key=lambda s: score_for_station(asset, s))
        buckets[best.name].append(asset)
    return buckets
