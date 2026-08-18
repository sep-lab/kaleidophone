"""
The creative brief: the one file a person authors by hand.

Everything else in kaleidophone -- the audio analysis, the curated asset list, the
edit-decision-list, the rendered MP4 -- is derived from (song, stations,
sections, output) plus the actual media sitting on disk. That is the whole
point: see docs/decisions/0001-version-the-brief-not-the-render.md. If you
catch yourself hand-tweaking a rendered video, you're editing a cache; put
the change in the brief instead and re-render.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# A station's duotone colors are interpolated straight into an ffmpeg
# `curves=` filter string (render/effects.py::_duotone_filter). SECURITY.md
# names filter-graph injection as in-scope, so the brief -- which is the
# untrusted input here, since briefs are meant to be shared and reused -- is
# where the shape gets enforced, not somewhere downstream.
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_BITRATE_RE = re.compile(r"^\d+(\.\d+)?[kKmM]?$")

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
    # NB: there is deliberately no "duotone" effect. Duotone is a property of
    # a *station* (StationConfig.duotone), applied by color_grade() to every
    # cut in that station. It was briefly listed here too, where it built an
    # empty filter string -- so putting it in a section's `effects` did
    # nothing at all, silently. Better to reject the name than to accept it
    # and ignore it.
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

    @field_validator("duotone")
    @classmethod
    def _duotone_is_a_pair_of_hex_colors(cls, v: tuple[str, str] | None) -> tuple[str, str] | None:
        if v is None:
            return v
        for color in v:
            if not _HEX_COLOR_RE.match(color):
                raise ValueError(
                    f"duotone color {color!r} must be a 6-digit hex color like '#1a0f06'. "
                    f"These are interpolated into an ffmpeg filter string, so the format is "
                    f"enforced here rather than trusted -- see SECURITY.md."
                )
        return v


class FramingConfig(BaseModel):
    """How a source frame is fitted into the output frame.

    Only interesting when the output aspect differs from the source's. Pulling
    a 9:16 frame out of 16:9 footage throws away two thirds of the width, and
    *which* two thirds is a creative decision -- the subject is rarely in the
    middle. There is no computation that gets this right, so it is a field.
    """

    mode: Literal["fill", "crop", "window"] = Field(
        default="fill",
        description="fill: scale-to-cover and centre-crop (the default, and what "
        "kaleidophone did before framing existed). crop: take a full-height slice "
        "at `x`. window: shrink the whole frame to `width` and pad it into the "
        "output on black.",
    )
    x: int | None = Field(
        default=None,
        ge=0,
        description="mode=crop: left edge of the slice, in *source* pixels.",
    )
    width: int | None = Field(
        default=None,
        gt=0,
        description="mode=window: width of the inset, in output pixels.",
    )
    y_center: int | None = Field(
        default=None,
        ge=0,
        description="mode=window: vertical centre of the inset, in output pixels. "
        "Defaults to the middle of the frame.",
    )

    @model_validator(mode="after")
    def _required_fields_per_mode(self) -> "FramingConfig":
        if self.mode == "crop" and self.x is None:
            raise ValueError("framing mode 'crop' needs an `x` (left edge, in source pixels)")
        if self.mode == "window" and self.width is None:
            raise ValueError("framing mode 'window' needs a `width` (inset width, in output pixels)")
        return self


class SectionConfig(BaseModel):
    """One structural stretch of the song -- Love's PENDULUM / HUSH / THE SWITCH / ..."""

    name: str
    start: float = Field(description="Seconds from the top of the track.")
    end: float
    station: str = Field(description="Must match a StationConfig.name.")
    cut_density: CutDensity = "every_beat"
    effects: list[EffectName] = Field(default_factory=list)
    framing: FramingConfig = Field(
        default_factory=FramingConfig,
        description="How source frames are fitted into the output frame. Only "
        "meaningful when output.aspect differs from the source material's.",
    )
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


class EncodeConfig(BaseModel):
    """x264/AAC delivery settings.

    Every default here reproduces exactly what kaleidophone encoded before this
    block existed, so adding `encode:` to a brief is opt-in and leaving it out
    changes nothing.

    The values that matter for delivery and had no way to be set: a bitrate
    ceiling (platforms re-encode whatever you hand them, and an unbounded CRF
    stream can spike well past what they will accept), and colour tags. An
    untagged h264 stream gets *guessed* at by players -- usually as bt709, which
    is why it mostly looks fine, and why the failure is confusing when it isn't.
    """

    crf: int = Field(default=20, ge=0, le=51, description="Lower is better quality and bigger.")
    preset: Literal[
        "ultrafast", "superfast", "veryfast", "faster", "fast",
        "medium", "slow", "slower", "veryslow",
    ] = "veryfast"
    maxrate: str | None = Field(
        default=None,
        description="Bitrate ceiling, e.g. '4500k'. Requires bufsize to do anything.",
    )
    bufsize: str | None = Field(default=None, description="Rate-control buffer, e.g. '9M'.")
    color: Literal["bt709", "bt601", "bt2020"] | None = Field(
        default=None,
        description="Tag the stream's colourspace/primaries/transfer. Untagged is "
        "the historical default; bt709 is correct for ordinary HD delivery.",
    )
    audio_bitrate: str = "192k"
    audio_rate: int | None = Field(
        default=None,
        description="Output audio sample rate, e.g. 48000. None keeps the source's.",
    )

    @field_validator("maxrate", "bufsize", "audio_bitrate")
    @classmethod
    def _is_a_bitrate(cls, v: str | None) -> str | None:
        # These go into an ffmpeg argv, and a brief is meant to be shared and
        # reused -- same reasoning as the duotone hex check above.
        if v is None:
            return v
        if not _BITRATE_RE.match(v):
            raise ValueError(
                f"{v!r} is not a bitrate. Use a number with an optional k/M suffix, "
                f"like '4500k', '9M' or '192k'."
            )
        return v

    @model_validator(mode="after")
    def _maxrate_needs_bufsize(self) -> "EncodeConfig":
        if (self.maxrate is None) != (self.bufsize is None):
            raise ValueError(
                "maxrate and bufsize must be set together -- x264 ignores a "
                "maxrate with no buffer to rate-control against, which looks "
                "like the ceiling silently not working."
            )
        return self


# Canonical pixel sizes per aspect. These are what the platforms actually
# want, so `aspect: "9:16"` alone is enough for a correct vertical delivery.
ASPECT_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

Aspect = Literal["16:9", "9:16", "1:1", "4:5"]


class OutputConfig(BaseModel):
    resolution: tuple[int, int] = (1280, 720)
    fps: int = 24
    aspect: Aspect | None = Field(
        default=None,
        description="Target frame shape. Setting this alone picks the canonical "
        "resolution for it (9:16 -> 1080x1920). Set `resolution` too only if you "
        "want a different size at the same shape.",
    )
    window: tuple[float, float] | None = Field(
        default=None,
        description="Render only [start, end] seconds of the song. Section times "
        "are rebased so the output starts at 0. This is how one brief produces "
        "both the full master and a cutdown, instead of two briefs that drift.",
    )
    encode: EncodeConfig = Field(default_factory=EncodeConfig)
    teasers: list[TeaserConfig] = Field(default_factory=list)
    thumbnail_count: int = 3
    cover_size: int = 3000
    cover_station: str | None = Field(
        default=None,
        description="Which station's palette drives the cover art. Defaults to "
        "whichever section contains the song's loudest moment.",
    )

    @field_validator("window")
    @classmethod
    def _window_is_ordered(cls, v: tuple[float, float] | None) -> tuple[float, float] | None:
        if v is None:
            return v
        start, end = v
        if start < 0:
            raise ValueError(f"output.window start ({start}) cannot be negative")
        if end <= start:
            raise ValueError(f"output.window end ({end}) must be after start ({start})")
        return v

    @model_validator(mode="after")
    def _aspect_and_resolution_agree(self) -> "OutputConfig":
        """`aspect` sets `resolution` unless the brief set one explicitly.

        Pydantic does not tell us which fields were explicitly provided from a
        plain default, so `model_fields_set` is the check: it holds exactly the
        keys present in the YAML.
        """
        if self.aspect is None:
            return self
        canonical = ASPECT_RESOLUTIONS[self.aspect]
        if "resolution" not in self.model_fields_set:
            self.resolution = canonical
            return self
        w, h = self.resolution
        want_w, want_h = canonical
        # Same shape at a different size is fine (a 4K vertical master, say);
        # a contradiction is not, and silently picking a winner would be worse.
        if abs(w / h - want_w / want_h) > 0.01:
            raise ValueError(
                f"output.aspect is {self.aspect!r} but output.resolution is "
                f"{w}x{h}, which is {w / h:.3f}:1 rather than "
                f"{want_w / want_h:.3f}:1. Set one or the other, not both."
            )
        return self


class PromoConfig(BaseModel):
    handles: list[str] = Field(default_factory=list)
    teaser_cadence_days: list[int] = Field(
        default_factory=lambda: [-7, -3, -1],
        description="Days relative to release, e.g. T-7 / T-3 / T-1.",
    )


class OverlayLine(BaseModel):
    """One line of text on a card.

    `size` and `tracking` are fractions of the output frame *height*, not
    pixels, so a card designed against a 1080x1920 delivery is still right when
    the same brief renders at 2160x3840. A pixel size would come out half as
    large and nothing would say so.
    """

    text: str
    font: str = Field(
        default="mono",
        description="A bundled role (mono, mono-bold, typewriter, display, "
        "display-medium, persian, persian-bold) or 'path:/abs/font.ttf'.",
    )
    size: float = Field(default=0.03, gt=0.0, le=1.0, description="Fraction of frame height.")
    color: str = "#eeeeea"
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    tracking: float = Field(
        default=0.0,
        ge=0.0,
        description="Letter-spacing as a fraction of frame height. Pillow has no "
        "tracking parameter, so this is drawn glyph by glyph -- which is why it "
        "cannot be combined with right-to-left text.",
    )
    rtl: bool | None = Field(
        default=None,
        description="Leave unset: direction is detected from the text's own script. "
        "Set it only to override that detection.",
    )

    @field_validator("color")
    @classmethod
    def _is_a_hex_color(cls, v: str) -> str:
        if not _HEX_COLOR_RE.match(v):
            raise ValueError(f"colour {v!r} must be a 6-digit hex colour like '#eeeeea'")
        return v


class OverlayConfig(BaseModel):
    """A timed text card burned into the render.

    Times are on the *output* timeline, so they line up with what you watch --
    if `output.window` is set, an overlay at 0.25 is a quarter-second into the
    cutdown, not into the song.
    """

    id: str = Field(description="Unique within a brief; also names the rendered PNG.")
    at: tuple[float, float] = Field(description="[start, end] in seconds, on the output timeline.")
    lines: list[OverlayLine] = Field(min_length=1)
    align: Literal["left", "center", "right"] = "center"
    y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Vertical centre of the text block, as a fraction of frame height.",
    )
    line_gap: float = Field(
        default=0.012, ge=0.0, description="Space between lines, as a fraction of frame height."
    )
    shadow: bool = Field(
        default=True,
        description="Blurred black copy behind the text. On by default because text "
        "over moving footage vanishes the moment a light frame passes under it.",
    )

    @field_validator("at")
    @classmethod
    def _times_are_ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        start, end = v
        if start < 0:
            raise ValueError(f"overlay start ({start}) cannot be negative")
        if end <= start:
            raise ValueError(f"overlay end ({end}) must be after start ({start})")
        return v


class CreativeBrief(BaseModel):
    """Top-level document -- what `kaleidophone compose brief.yaml` reads."""

    song: SongConfig
    stations: list[StationConfig]
    sections: list[SectionConfig]
    output: OutputConfig = Field(default_factory=OutputConfig)
    overlays: list[OverlayConfig] = Field(default_factory=list)
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

    @field_validator("overlays")
    @classmethod
    def _overlay_ids_are_unique(cls, v: list[OverlayConfig]) -> list[OverlayConfig]:
        """Two overlays sharing an id would render to the same PNG path, and the
        second would silently overwrite the first -- the render would succeed
        and one card would simply never appear."""
        seen: set[str] = set()
        for ov in v:
            if ov.id in seen:
                raise ValueError(
                    f"duplicate overlay id {ov.id!r}. Ids name the rendered card "
                    f"file, so a repeat would silently overwrite the earlier one."
                )
            seen.add(ov.id)
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CreativeBrief":
        import yaml

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls.model_validate(data)
