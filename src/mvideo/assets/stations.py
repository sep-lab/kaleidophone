"""
Station presets: named visual/color-grade treatments, generalized from the
reference case study's ROOM / CITY / SUN / FIRE. A station is a *look*
(temperature, grain, duotone...) that any brief can point at its own media --
see docs/CREATIVE-GUIDE.md for the design language these encode, and
docs/case-studies/love.md for where they came from.
"""

from __future__ import annotations

from mvideo.timeline.schema import StationConfig

PRESETS: dict[str, StationConfig] = {
    "amber-room": StationConfig(
        name="amber-room",
        description="Warm interiors, lamplight, instruments -- an intimate, home-recorded feeling.",
        temperature=0.55,
        saturation=1.05,
        contrast=1.05,
        grain=0.18,
        vignette=0.28,
        duotone=("#1a0f06", "#f2b25c"),
    ),
    "noir-crush": StationConfig(
        name="noir-crush",
        description="Black & white, crushed blacks, heavy grain and scanlines -- street/documentary energy.",
        temperature=0.0,
        saturation=0.0,
        contrast=1.35,
        grain=0.4,
        vignette=0.35,
        duotone=("#050505", "#e8e8e8"),
    ),
    "gold-hour": StationConfig(
        name="gold-hour",
        description="Golden hour, backlit, slow -- for a song's quiet or held moments.",
        temperature=0.7,
        saturation=0.9,
        contrast=0.9,
        grain=0.1,
        vignette=0.15,
        duotone=("#241505", "#ffd27a"),
    ),
    "fire-leak": StationConfig(
        name="fire-leak",
        description="Boosted native color, light-leak energy -- for the loudest, most saturated moment of the song.",
        temperature=0.4,
        saturation=1.6,
        contrast=1.2,
        grain=0.25,
        vignette=0.1,
        # A hot red-orange, not another amber -- without its own duotone this
        # preset fell back to _target_hue()'s coarse warm guess (15.0), which
        # sits within ~2-5 hue units of amber-room's and gold-hour's actual
        # duotone hues and starved it in curation. Found via
        # tests/test_stations.py, not a real render -- see CHANGELOG.md.
        duotone=("#1c0500", "#ff5a36"),
    ),
}


def preset(name: str) -> StationConfig:
    """A deep copy of a named preset, ready to attach a media_dir to."""
    try:
        return PRESETS[name].model_copy(deep=True)
    except KeyError as exc:
        raise KeyError(f"no station preset {name!r}; available: {sorted(PRESETS)}") from exc
