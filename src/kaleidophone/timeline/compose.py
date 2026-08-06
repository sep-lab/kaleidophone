"""
compose(): turn a CreativeBrief + AudioAnalysis + curated assets into an EDL.

This is the one function that plays "director". It's deliberately simple and
deterministic (seeded) rather than clever: same brief + same assets + same
seed -> the same edit, every time, so tweaking one section re-renders fast and
predictably. See docs/decisions/0001-version-the-brief-not-the-render.md.
"""

from __future__ import annotations

import itertools
import random

from kaleidophone.assets.curation import MediaAsset
from kaleidophone.audio.analysis import AudioAnalysis
from kaleidophone.timeline.model import EDL, Cut
from kaleidophone.timeline.schema import CreativeBrief, SectionConfig

_BEAT_DIVISORS: dict[str, int | None] = {
    "every_beat": 1,
    "every_2_beats": 2,
    "every_4_beats": 4,
    "every_bar": 4,  # assumes 4/4 time -- override with an explicit cut_density if that's wrong
    "every_2_bars": 8,
    "every_4_bars": 16,
    "static": None,
}


def compose(
    brief: CreativeBrief,
    analysis: AudioAnalysis,
    station_assets: dict[str, list[MediaAsset]],
) -> EDL:
    cuts: list[Cut] = []
    index = 0
    for section in brief.sections:
        section_cuts = _compose_section(section, analysis, station_assets.get(section.station, []), index)
        cuts.extend(section_cuts)
        index += len(section_cuts)

    return EDL(
        song_title=brief.song.title,
        audio_path=brief.song.audio_path,
        duration=analysis.duration,
        fps=brief.output.fps,
        resolution=brief.output.resolution,
        cuts=tuple(cuts),
    )


def _compose_section(
    section: SectionConfig,
    analysis: AudioAnalysis,
    assets: list[MediaAsset],
    start_index: int,
) -> list[Cut]:
    if not assets:
        raise ValueError(
            f"section {section.name!r} needs media assigned to station {section.station!r}, "
            f"but no assets were curated for it -- point that station's media_dir at some photos/clips."
        )

    boundaries = _cut_boundaries(section, analysis)
    rng = random.Random(section.seed)
    pool = assets.copy()
    rng.shuffle(pool)

    cuts = []
    for i, (start, end) in enumerate(itertools.pairwise(boundaries)):
        asset = pool[i % len(pool)]
        effects = _effects_for_cut(section, i, analysis, start, end)
        cuts.append(
            Cut(
                index=start_index + i,
                start=start,
                end=end,
                source_path=asset.path,
                station=section.station,
                section=section.name,
                effects=tuple(effects),
                is_beat_aligned=section.cut_density != "static",
            )
        )
    return cuts


def _cut_boundaries(section: SectionConfig, analysis: AudioAnalysis) -> list[float]:
    divisor = _BEAT_DIVISORS[section.cut_density]
    if divisor is None:
        return [section.start, section.end]

    beats = [t for t in analysis.beat_times if section.start <= t <= section.end]
    if not beats or beats[0] > section.start:
        beats = [section.start, *beats]
    if beats[-1] < section.end:
        beats = [*beats, section.end]

    boundaries = beats[::divisor]
    if boundaries[-1] != section.end:
        boundaries.append(section.end)

    # Beat-tracking can occasionally place two boundaries within a hair of each
    # other; collapse anything shorter than one video frame at 24fps.
    cleaned = [boundaries[0]]
    for b in boundaries[1:]:
        if b - cleaned[-1] >= (1 / 24):
            cleaned.append(b)

    # The collapse above can eat the section's true end if the last real beat
    # lands within one frame of it (found via tests/test_compose.py, not a
    # real-world render -- see CHANGELOG.md). Snap back onto it rather than
    # silently truncating the section by a fraction of a frame.
    if cleaned[-1] != boundaries[-1]:
        cleaned[-1] = boundaries[-1]
    return cleaned


def _effects_for_cut(
    section: SectionConfig,
    cut_i: int,
    analysis: AudioAnalysis,
    start: float,
    end: float,
) -> list[str]:
    effects = []
    for eff in section.effects:
        if eff == "kaleidoscope":
            if cut_i > 0 and cut_i % 7 == 0:  # every 7th cut, matching the PENDULUM reference section
                effects.append(eff)
        elif eff == "freeze_on_peak":
            if any(start <= j.time < end for j in analysis.energy_jumps):
                effects.append(eff)
        elif eff == "strobe":
            if any(start <= o < end for o in analysis.onset_times):
                effects.append(eff)
        else:
            effects.append(eff)  # section-wide look (grain/scanlines/halation/vignette/...): every cut
    return effects
