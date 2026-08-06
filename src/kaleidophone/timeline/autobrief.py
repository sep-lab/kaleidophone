"""
Default mode: one song + one folder of media -> a full CreativeBrief, with
zero manual authoring.

The point isn't that these choices are the best possible edit -- it's that
nobody has to answer a wall of setup questions to see a first result. Every
choice this makes is a normal field in the brief.yaml it writes out, so
"customize everything" is always one edit and a re-run away; see
docs/CREATIVE-GUIDE.md, "Default mode vs. authored briefs", and
`kaleidophone auto --help`.
"""

from __future__ import annotations

import itertools
import os

from kaleidophone.assets.curation import MediaAsset, scan_media, suggest_stations
from kaleidophone.assets.stations import PRESETS
from kaleidophone.audio.analysis import AudioAnalysis, analyze
from kaleidophone.timeline.schema import CreativeBrief, OutputConfig, SectionConfig, SongConfig

DEFAULT_STATION_CYCLE = ["amber-room", "noir-crush", "gold-hour", "fire-leak"]
MIN_SECTIONS = 3
MAX_SECTIONS = 6


def build_default_brief(
    audio_path: str,
    media_dir: str,
    *,
    title: str | None = None,
    artist: str | None = None,
) -> tuple[CreativeBrief, dict[str, list[MediaAsset]]]:
    """Returns (brief, station_assets). station_assets is the actual curated
    split of media_dir's contents, computed once here with the same heuristic
    `kaleidophone curate` exposes standalone -- callers should use it directly
    rather than re-scanning each station's (identical, shared) media_dir."""
    analysis = analyze(audio_path)
    boundaries = _propose_section_boundaries(analysis)
    n_sections = len(boundaries) - 1

    candidates = [PRESETS[name].model_copy(deep=True) for name in DEFAULT_STATION_CYCLE[:n_sections]]
    for s in candidates:
        s.media_dir = media_dir  # documentation of provenance; see note above on station_assets

    assets = scan_media(media_dir)
    if not assets:
        raise ValueError(f"no photos or clips found under {media_dir!r}")

    curated = suggest_stations(assets, candidates)
    # Curation is a heuristic and can leave a station empty (e.g. every photo
    # skews warm and two warm stations tie). Rather than hand compose() a
    # brief this function itself made inconsistent, only ever cycle sections
    # through stations that actually received something -- see
    # docs/decisions/0002-deterministic-edit-engine.md and
    # assets/curation.py's _target_hue() for the scoring side of this fix.
    stations = [s for s in candidates if curated.get(s.name)]
    if not stations:
        stations = candidates[:1]
        curated[stations[0].name] = assets
    station_assets = {s.name: curated[s.name] for s in stations}

    sections = []
    for i, (start, end) in enumerate(itertools.pairwise(boundaries)):
        station = stations[i % len(stations)]
        loud = _section_loudness(analysis, start, end)
        sections.append(
            SectionConfig(
                name=f"SECTION_{i + 1}",
                start=start,
                end=end,
                station=station.name,
                cut_density="every_2_beats" if loud < 0.6 else "every_beat",
                effects=["grain", "vignette"] if loud < 0.6 else ["grain", "strobe", "vignette"],
            )
        )

    brief = CreativeBrief(
        song=SongConfig(title=title or _guess_title(audio_path), artist=artist, audio_path=audio_path),
        stations=stations,
        sections=sections,
        output=OutputConfig(),
    )
    return brief, station_assets


def _propose_section_boundaries(analysis: AudioAnalysis) -> list[float]:
    """Quiet passages and energy jumps are natural cut points -- a hush before
    a drop, the drop itself. Falls back to even slicing when the song doesn't
    hand back enough of either (e.g. a dynamically flat track), and also when
    it hands back *too many* -- picking the most "important" subset of many
    candidate boundaries is real work this v0.1 doesn't attempt; see
    ROADMAP.md, "Smarter auto-sectioning"."""
    candidates = {0.0, round(analysis.duration, 2)}
    for q in analysis.quiet_passages:
        candidates.add(round(q.start, 2))
        candidates.add(round(q.end, 2))
    for j in analysis.energy_jumps:
        candidates.add(round(j.time, 2))

    boundaries = _drop_short_gaps(sorted(candidates), min_gap=max(4.0, analysis.duration * 0.05))
    n_sections = len(boundaries) - 1

    if n_sections < MIN_SECTIONS or n_sections > MAX_SECTIONS:
        n = MIN_SECTIONS if n_sections < MIN_SECTIONS else MAX_SECTIONS
        boundaries = [round(analysis.duration * i / n, 2) for i in range(n + 1)]

    return boundaries


def _drop_short_gaps(boundaries: list[float], min_gap: float) -> list[float]:
    cleaned = [boundaries[0]]
    for b in boundaries[1:]:
        if b - cleaned[-1] >= min_gap:
            cleaned.append(b)
    if cleaned[-1] != boundaries[-1]:
        cleaned[-1] = boundaries[-1]
    return cleaned


def _section_loudness(analysis: AudioAnalysis, start: float, end: float) -> float:
    """0..1, this section's mean RMS relative to the song's own dB range.
    Only used to nudge cut_density/effects toward something livelier for
    louder sections -- not a precise measurement of anything."""
    if not analysis.rms_db:
        return 0.5
    values = [db for t, db in zip(analysis.rms_times, analysis.rms_db) if start <= t < end]
    if not values:
        return 0.5
    lo, hi = min(analysis.rms_db), max(analysis.rms_db)
    span = (hi - lo) or 1.0
    return (sum(values) / len(values) - lo) / span


def _guess_title(audio_path: str) -> str:
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled"
