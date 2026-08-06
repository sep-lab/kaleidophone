"""
Synthetic test fixtures -- pure Python, no real photos/audio/video, ever.

Same rule as examples/demo/generate_fixtures.py (see CLAUDE.md), applied at
unit-test scale: every AudioAnalysis, MediaAsset, and CreativeBrief built
here comes directly from numbers, not from decoding a file. No librosa
decode, no ffmpeg call, nothing to gitignore -- the whole suite runs in a
fraction of a second with only the package's own dependencies.
"""

from __future__ import annotations

from kaleidophone.assets.curation import MediaAsset
from kaleidophone.audio.analysis import AudioAnalysis, EnergyJump, QuietPassage
from kaleidophone.timeline.schema import (
    CreativeBrief,
    SectionConfig,
    SongConfig,
    StationConfig,
)

__all__ = [
    "make_analysis",
    "make_beats",
    "make_brief",
    "make_media_asset",
    "make_section",
    "make_song",
    "make_station",
]


def make_beats(count: int, *, interval: float = 0.5, offset: float = 0.0) -> tuple[float, ...]:
    """`count` beats, `interval` seconds apart, starting at `offset` -- a clean click track."""
    return tuple(round(offset + i * interval, 6) for i in range(count))


def make_analysis(
    *,
    path: str = "synthetic://song",
    duration: float = 30.0,
    sr: int = 22050,
    bpm: float = 120.0,
    beat_times: tuple[float, ...] | None = None,
    onset_times: tuple[float, ...] = (),
    onset_env: tuple[float, ...] = (),
    onset_env_times: tuple[float, ...] = (),
    rms_db: tuple[float, ...] = (),
    rms_times: tuple[float, ...] = (),
    quiet_passages: tuple[QuietPassage, ...] = (),
    energy_jumps: tuple[EnergyJump, ...] = (),
) -> AudioAnalysis:
    """An AudioAnalysis built directly from numbers -- no audio decode.

    Defaults to one beat every 0.5s (120 BPM) spanning the full duration
    unless an explicit `beat_times` is given.
    """
    if beat_times is None:
        beat_times = make_beats(int(duration / 0.5) + 1, interval=0.5)
    return AudioAnalysis(
        path=path,
        duration=duration,
        sr=sr,
        bpm=bpm,
        beat_times=beat_times,
        onset_times=onset_times,
        onset_env=onset_env,
        onset_env_times=onset_env_times,
        rms_db=rms_db,
        rms_times=rms_times,
        quiet_passages=quiet_passages,
        energy_jumps=energy_jumps,
    )


def make_media_asset(
    path: str,
    *,
    kind: str = "image",
    hue: float = 15.0,
    saturation: float = 0.5,
    brightness: float = 0.5,
) -> MediaAsset:
    return MediaAsset(
        path=path, kind=kind, mean_hue=hue, mean_saturation=saturation, mean_brightness=brightness
    )


def make_station(name: str = "test-station", **overrides) -> StationConfig:
    fields = {
        "name": name,
        "description": f"{name} test station",
        "temperature": 0.5,
        "duotone": ("#100800", "#f2b25c"),
    }
    fields.update(overrides)
    return StationConfig(**fields)


def make_song(**overrides) -> SongConfig:
    fields = {"title": "Test Song", "audio_path": "synthetic://song.wav"}
    fields.update(overrides)
    return SongConfig(**fields)


def make_section(**overrides) -> SectionConfig:
    fields = {"name": "SECTION_1", "start": 0.0, "end": 10.0, "station": "test-station"}
    fields.update(overrides)
    return SectionConfig(**fields)


def make_brief(
    *,
    stations: list[StationConfig] | None = None,
    sections: list[SectionConfig] | None = None,
    **overrides,
) -> CreativeBrief:
    """A minimal valid CreativeBrief: one station, one section pointed at it,
    unless overridden. `**overrides` passes straight through to CreativeBrief
    (e.g. `promo=PromoConfig(...)`, `output=OutputConfig(...)`)."""
    stations = stations if stations is not None else [make_station()]
    sections = sections if sections is not None else [make_section(station=stations[0].name)]
    fields = {"song": make_song(), "stations": stations, "sections": sections}
    fields.update(overrides)
    return CreativeBrief(**fields)
