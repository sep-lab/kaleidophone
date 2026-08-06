#!/usr/bin/env python3
"""
Zero-input demo fixtures: a synthetic song + synthetic "photos", so the whole
pipeline can be run ten seconds after cloning -- no real music, no real
photos, nothing personal, nothing to ask permission for.

WHAT THIS GENERATES
    _fixtures/song.wav          ~24s, ~120 BPM, three sections: a moderate
                                 intro, a near-silent hush (8-11s), then a
                                 loud "switch" and drop (11-24s) -- built from
                                 sine pads + percussive clicks on the beat
                                 grid, not sampled from anything.
    _fixtures/photos/<station>/ a few dozen procedurally generated gradient
                                 images per station (amber/gold/fire hues),
                                 standing in for curated photos.
    _fixtures/brief.yaml        a CreativeBrief pointing at the above.

Nothing here is faked *as a demo of the pipeline*: the generated song is a
real WAV file, the generated images are real JPGs, and `mvideo run` on the
resulting brief goes through the exact same analyze/compose/render code path
real material does. What's fake is the material itself, on purpose -- see
docs/CREATIVE-GUIDE.md and AGENTS.md, "Rules for handling user data".

WHAT THIS DOES NOT HANDLE
    The synthetic song is rhythmically simple (one steady click pattern) so
    beat-tracking has an easy target. It is not representative of how well
    analysis.py tracks tempo on a real, dynamically-performed recording --
    that can only be measured on real material, by you, locally (never
    committed -- see .gitignore).

USAGE
    python3 examples/demo/generate_fixtures.py
    python3 examples/demo/generate_fixtures.py --out /tmp/mvideo_demo
"""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw

SR = 22050
DURATION = 24.0
BPM = 120.0
HERE = Path(__file__).resolve().parent

# (hue in [0,1], count) per station -- warm amber, golden, hot fire-red.
STATIONS = {
    "amber-room": {"hue": 0.08, "count": 16},
    "gold-hour": {"hue": 0.12, "count": 10},
    "fire-leak": {"hue": 0.02, "count": 16},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "_fixtures"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    song_path = out / "song.wav"
    _generate_song(song_path)
    print(f"wrote {song_path}")

    photo_dirs = {}
    for name, cfg in STATIONS.items():
        station_dir = out / "photos" / name
        _generate_station_photos(station_dir, count=cfg["count"], hue=cfg["hue"], seed=hash(name) % 10_000)
        photo_dirs[name] = station_dir
        print(f"wrote {cfg['count']} placeholder images -> {station_dir}")

    brief_path = out / "brief.yaml"
    _write_brief(brief_path, song_path, photo_dirs)
    print(f"wrote {brief_path}")
    print()
    print("Next: mvideo run", brief_path, "-o", out / "out")
    return 0


def _generate_song(path: Path) -> None:
    n = int(DURATION * SR)
    t = np.arange(n) / SR

    # Section envelope: moderate intro, near-silent hush, loud switch+drop.
    env = np.where(t < 8.0, 0.30, np.where(t < 11.0, 0.008, 0.70)).astype(np.float32)

    # A sustained two-tone pad, shaped by the section envelope.
    pad = (0.6 * np.sin(2 * np.pi * 110.0 * t) + 0.4 * np.sin(2 * np.pi * 164.8 * t)) * env
    y = pad.astype(np.float32)

    # Percussive clicks on the beat grid, also shaped by the envelope so a
    # click during the hush stays quiet rather than becoming a loud surprise.
    beat_interval = 60.0 / BPM
    beat_t, i = 0.0, 0
    while beat_t < DURATION:
        idx = min(int(beat_t * SR), n - 1)
        amp = float(env[idx]) * 1.3
        freq = 150.0 if i % 4 == 0 else 300.0
        _add_click(y, beat_t, amp, freq)
        i += 1
        beat_t += beat_interval

    y += np.random.default_rng(0).normal(0, 0.004, n).astype(np.float32)  # tiny floor, not digital silence
    y = np.clip(y, -1.0, 1.0).astype(np.float32)
    sf.write(str(path), y, SR)


def _add_click(
    y: np.ndarray, t: float, amp: float, freq: float, decay: float = 0.08, dur: float = 0.15
) -> None:
    start = int(t * SR)
    if start >= len(y):
        return
    end = min(len(y), start + int(dur * SR))
    tt = np.arange(end - start) / SR
    envelope = np.exp(-tt / decay)
    y[start:end] += (amp * np.sin(2 * np.pi * freq * tt) * envelope).astype(np.float32)


def _generate_station_photos(
    out_dir: Path, count: int, hue: float, seed: int, size: tuple[int, int] = (320, 240)
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    for i in range(count):
        h = (hue + rng.uniform(-0.03, 0.03)) % 1.0
        img = Image.new("RGB", size)
        draw = ImageDraw.Draw(img)
        for y in range(size[1]):
            v = 0.25 + 0.65 * (y / size[1])
            s = 0.45 + 0.35 * rng.random()
            draw.line([(0, y), (size[0], y)], fill=_hsv(h, s, v))
        for _ in range(6):
            cx, cy = int(rng.integers(0, size[0])), int(rng.integers(0, size[1]))
            r = int(rng.integers(12, 60))
            shade = _hsv((h + rng.uniform(-0.05, 0.05)) % 1.0, 0.35, float(rng.uniform(0.25, 0.9)))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade)
        img.save(out_dir / f"{i:03d}.jpg", quality=85)


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _write_brief(path: Path, song_path: Path, photo_dirs: dict[str, Path]) -> None:
    # Written by hand (not via yaml.dump) so the file reads the way a person
    # would author one -- this doubles as a worked example of the format.
    text = f"""\
# Auto-generated by examples/demo/generate_fixtures.py -- entirely synthetic,
# nothing here is a real song or a real photo. See docs/CONFIG-SCHEMA.md for
# what every field means.
song:
  title: "mvideo demo (synthetic)"
  audio_path: "{song_path}"
  # bpm left unset on purpose -- let analysis.py detect it, so this demo also
  # exercises the beat tracker, not just the render path.

stations:
  - name: amber-room
    description: "Warm synthetic gradients standing in for an intro station."
    media_dir: "{photo_dirs["amber-room"]}"
    temperature: 0.5
    saturation: 1.0
    contrast: 1.0
    grain: 0.15
    vignette: 0.2
    duotone: ["#1a0f06", "#f2b25c"]
  - name: gold-hour
    description: "Golden, slow -- for the hush."
    media_dir: "{photo_dirs["gold-hour"]}"
    temperature: 0.7
    saturation: 0.9
    contrast: 0.9
    grain: 0.1
    vignette: 0.15
  - name: fire-leak
    description: "Hot and saturated -- for the switch and drop."
    media_dir: "{photo_dirs["fire-leak"]}"
    temperature: 0.4
    saturation: 1.5
    contrast: 1.2
    grain: 0.25
    vignette: 0.1

sections:
  - name: INTRO
    start: 0.0
    end: 8.0
    station: amber-room
    cut_density: every_2_beats
    effects: [grain, vignette]
  - name: HUSH
    start: 8.0
    end: 11.0
    station: gold-hour
    cut_density: every_bar
    effects: [grain, halation]
  - name: SWITCH_AND_DROP
    start: 11.0
    end: 24.0
    station: fire-leak
    cut_density: every_beat
    effects: [grain, strobe, freeze_on_peak, kaleidoscope]

output:
  resolution: [640, 360]
  fps: 24
  thumbnail_count: 2
  cover_size: 800
  teasers:
    - name: teaser_drop
      duration: 6.0
      aspect: "9:16"
      source_start: 11.0

promo:
  teaser_cadence_days: [-3, -1]
"""
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
