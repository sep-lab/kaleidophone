"""
ffmpeg filter-graph fragments for each effect name in
kaleidophone.timeline.schema.EffectName.

Two kinds, because ffmpeg's filter language has two shapes:

- LINEAR_EFFECT_BUILDERS -- ordinary single-in/single-out filters. These join
  into one comma-separated `-vf` chain alongside the station's color grade.
- GRAPH_EFFECT_BUILDERS -- filters that split the frame into multiple pads
  (kaleidoscope, halation). Each needs its own `-filter_complex` pass; see
  render.ffmpeg_pipeline._render_segment for how they're chained.

Kept as small, composable string builders rather than one giant templated
graph, so a new effect is one function, not a rewrite.
"""

from __future__ import annotations

from kaleidophone.timeline.schema import StationConfig


def color_grade(station: StationConfig) -> str:
    """Temperature/saturation/contrast/vignette/grain/duotone -> one filter chain."""
    parts = []

    # Temperature: push red vs. blue via colorbalance's midtones. -1..1 -> a gentle -0.3..0.3 shift.
    t = max(-1.0, min(1.0, station.temperature)) * 0.3
    parts.append(f"colorbalance=rm={t:.3f}:bm={-t:.3f}")

    parts.append(f"eq=contrast={station.contrast:.3f}:saturation={station.saturation:.3f}")

    if station.duotone:
        parts.append(_duotone_filter(*station.duotone))

    if station.vignette > 0:
        angle = 0.63 + station.vignette * 0.6  # radians; ffmpeg's own default is ~0.63 (PI/5)
        parts.append(f"vignette=angle={angle:.3f}")

    if station.grain > 0:
        strength = int(5 + station.grain * 35)
        parts.append(f"noise=alls={strength}:allf=t")

    return ",".join(parts)


def _duotone_filter(shadow_hex: str, highlight_hex: str) -> str:
    """Approximate duotone: desaturate, then remap each channel through a
    2-point curve from the shadow color to the highlight color."""
    sr, sg, sb = _hex_to_unit(shadow_hex)
    hr, hg, hb = _hex_to_unit(highlight_hex)
    return f"hue=s=0,curves=r='0/{sr:.3f} 1/{hr:.3f}':g='0/{sg:.3f} 1/{hg:.3f}':b='0/{sb:.3f} 1/{hb:.3f}'"


def _hex_to_unit(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


def strobe(rate_hz: float = 8.0) -> str:
    """Brightness pulse at roughly `rate_hz` flashes/sec. No frames are
    dropped or added, so segment duration and audio sync stay exact."""
    return f"eq=eval=frame:brightness='0.35*sin(2*PI*t*{rate_hz})':contrast=1.1"


def invert_flash() -> str:
    return "negate"


def freeze_on_peak() -> str:
    """Hold a single frame for the whole segment. Photos rendered via `-loop 1`
    already are one; this matters for video-sourced cuts, where it flattens
    motion into a held beat -- the reference case study's 'hero freezes'."""
    return "loop=loop=-1:size=1:start=0"


def scanlines() -> str:
    """A thin dark line every 3rd row via drawgrid -- cheap and avoids the
    escaping hazards of a per-pixel geq expression."""
    return "drawgrid=w=iw:h=3:t=1:c=black@0.4"


def zoom_breathe(duration: float, fps: int, w: int, h: int) -> str:
    frames = max(1, int(duration * fps))
    return f"zoompan=z='min(zoom+0.0015,1.08)':d={frames}:s={w}x{h}"


def static_noise() -> str:
    return "noise=alls=60:allf=t+u,eq=saturation=0"


def kaleidoscope() -> str:
    """Cheap 4-way mirror tile: crop each quadrant, mirror three of them, and
    stack back together. Real kaleidoscope optics don't matter here -- the
    repeating symmetry is the whole effect."""
    return (
        "[0:v]split=4[a][b][c][d];"
        "[a]crop=iw/2:ih/2:0:0[tl];"
        "[b]crop=iw/2:ih/2:0:0,hflip[tr];"
        "[c]crop=iw/2:ih/2:0:0,vflip[bl];"
        "[d]crop=iw/2:ih/2:0:0,hflip,vflip[br];"
        "[tl][tr]hstack[top];[bl][br]hstack[bot];[top][bot]vstack"
    )


def halation() -> str:
    """Blown-highlight bleed: blur a copy of the frame and screen-blend it
    back over the original."""
    return (
        "[0:v]split[base][glow];"
        "[glow]gblur=sigma=12,eq=brightness=0.1[glowb];"
        "[base][glowb]blend=all_mode=screen:all_opacity=0.35"
    )


LINEAR_EFFECT_BUILDERS = {
    "strobe": lambda **kw: strobe(),
    "invert_flash": lambda **kw: invert_flash(),
    "freeze_on_peak": lambda **kw: freeze_on_peak(),
    "grain": lambda **kw: "noise=alls=20:allf=t",
    "scanlines": lambda **kw: scanlines(),
    "vignette": lambda **kw: "vignette",
    "zoom_breathe": lambda **kw: zoom_breathe(kw["duration"], kw["fps"], kw["w"], kw["h"]),
    "static_noise": lambda **kw: static_noise(),
    "duotone": lambda **kw: "",  # handled via station.duotone inside color_grade, not per-cut
}

GRAPH_EFFECT_BUILDERS = {
    "kaleidoscope": lambda **kw: kaleidoscope(),
    "halation": lambda **kw: halation(),
}
