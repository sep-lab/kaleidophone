"""
The creative brief: the one file a person authors by hand.

Everything else in mvideo -- the audio analysis, the curated asset list, the
edit-decision-list, the rendered MP4 -- is derived from (song, stations,
sections, output) plus the actual media sitting on disk. That is the whole
point: see docs/decisions/0001-version-the-brief-not-the-render.md. If you
catch yourself hand-tweaking a rendered video, you're editing a cache; put
the change in the brief instead and re-render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CutDensity = Literal[
    "every_beat",
    "every_2_beats",
    "every_4_beats",
    "every_bar",
    "every_2_bars",
    "every_4_bars",
    "static",
]

EffectName = Literal[
    "kaleidoscope",
    "strobe",
    "invert_flash",
    "freeze_on_peak",
    "grain",
    "scanlines",
    "halation",
    "vignette",
    "zoom_breathe",
    "static_noise",
    "duotone",
]


class SongConfig(BaseModel):
    title: str
    artist: str | None = None
    audio_path: str = Field(description="Local path to the song file. Never committed -- see .gitignore.")
    bpm: float | None = Field(
        default=None,
        description="Override the auto-detected BPM if librosa's estimate is wrong.",
    )


class StationConfig(BaseModel):
    """
    One mood/visual-treatment bucket -- Love's ROOM / CITY / SUN / FIRE.

    A station is a *look*, not a folder of specific files, so briefs can be
    shared and reused without sharing anyone's media: point `media_dir` at
    your own photos. See docs/CREATIVE-GUIDE.md for the design language
    these parameters encode.
    """

    name: str
    description: str = ""
    media_dir: str | None = Field(
        default=None,
        description="Local folder of photos/clips for this station. Never committed.",
    )
    temperature: float = Field(default=0.0, ge=-1.0, le=1.0, description="-1 cool .. +1 warm")
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    contrast: float = Field(default=1.0, ge=0.0, le=2.0)
    grain: float = Field(default=0.15, ge=0.0, le=1.0)
    vignette: float = Field(default=0.2, ge=0.0, le=1.0)
    duotone: tuple[str, str] | None = Field(
        default=None,
        description="Optional (shadow_hex, highlight_hex), e.g. the reference case study's amber room.",
    )


class SectionConfig(BaseModel):
    """One structural stretch of the song -- Love's PENDULUM / HUSH / THE SWITCH / ..."""

    name: str
    start: float = Field(description="Seconds from the top of the track.")
    end: float
    station: str = Field(description="Must match a StationConfig.name.")
    cut_density: CutDensity = "every_beat"
    effects: list[EffectName] = Field(default_factory=list)
    seed: int = Field(
        default=0,
        description="Asset-shuffle seed -- same seed, same edit, every re-render.",
    )

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: float, info) -> float:
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError(f"section end ({v}) must be after start ({start})")
        return v


class TeaserConfig(BaseModel):
    name: str
    duration: float = 15.0
    aspect: Literal["9:16", "1:1", "16:9"] = "9:16"
    source_start: float | None = Field(
        default=None,
        description="Where in the master timeline to pull the teaser from. "
        "Defaults to the middle of the track if unset.",
    )


class OutputConfig(BaseModel):
    resolution: tuple[int, int] = (1280, 720)
    fps: int = 24
    teasers: list[TeaserConfig] = Field(default_factory=list)
    thumbnail_count: int = 3
    cover_size: int = 3000
    cover_station: str | None = Field(
        default=None,
        description="Which station's palette drives the cover art. Defaults to "
        "whichever section contains the song's loudest moment.",
    )


class PromoConfig(BaseModel):
    handles: list[str] = Field(default_factory=list)
    teaser_cadence_days: list[int] = Field(
        default_factory=lambda: [-7, -3, -1],
        description="Days relative to release, e.g. T-7 / T-3 / T-1.",
    )


class CreativeBrief(BaseModel):
    """Top-level document -- what `mvideo compose brief.yaml` reads."""

    song: SongConfig
    stations: list[StationConfig]
    sections: list[SectionConfig]
    output: OutputConfig = Field(default_factory=OutputConfig)
    promo: PromoConfig | None = None

    @field_validator("sections")
    @classmethod
    def _sections_reference_known_stations(cls, v: list[SectionConfig], info):
        stations = info.data.get("stations") or []
        names = {s.name for s in stations}
        for sec in v:
            if sec.station not in names:
                raise ValueError(
                    f"section {sec.name!r} references station {sec.station!r}, "
                    f"which is not in stations ({sorted(names)})"
                )
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CreativeBrief":
        import yaml

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls.model_validate(data)
