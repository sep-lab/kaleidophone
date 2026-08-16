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
import sys

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
    fps = brief.output.fps
    cuts: list[Cut] = []
    index = 0
    for section in brief.sections:
        section_cuts = _compose_section(
            section, analysis, station_assets.get(section.station, []), index, fps
        )
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
    fps: int,
) -> list[Cut]:
    if not assets:
        raise ValueError(
            f"section {section.name!r} needs media assigned to station {section.station!r}, "
            f"but no assets were curated for it -- point that station's media_dir at some photos/clips."
        )

    boundaries = _cut_boundaries(section, analysis, fps)
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


def _tempo_grid(section: SectionConfig, analysis: AudioAnalysis) -> list[float]:
    """A beat grid synthesized from the detected BPM, for a section the beat
    tracker returned nothing inside.

    librosa's beat tracker locks onto the strongest rhythmic region of a track
    and can return *no* beats at all for a quiet intro or a near-silent hush --
    on this repo's own demo song it finds none before 11s of 24. The old
    behaviour there was to silently produce a single cut spanning the entire
    section: a brief that asked for `every_2_beats` got one 8-second still, with
    nothing said about it. That contradicts the documented meaning of
    cut_density, so fall back to the tempo grid, which is exactly what
    "every 2 beats" means when you know the tempo.

    Still a fallback, not a fix for tempo tracking: set SongConfig.bpm when the
    detected tempo is wrong, and section boundaries by hand when it matters.
    """
    if analysis.bpm <= 0:
        return []
    interval = 60.0 / analysis.bpm
    grid, t = [], section.start
    while t < section.end:
        grid.append(t)
        t += interval
    print(
        f"note: no beats detected inside section {section.name!r} "
        f"({section.start:.2f}s-{section.end:.2f}s) -- falling back to a {analysis.bpm:.1f} BPM grid "
        f"({len(grid)} beats). Beat tracking often finds nothing in a quiet passage; set "
        f"song.bpm in the brief if that tempo is wrong.",
        file=sys.stderr,
    )
    return grid


def snap_to_frame(t: float, fps: int) -> float:
    """The nearest whole-frame instant at `fps`. See _cut_boundaries()."""
    return round(t * fps) / fps


def _cut_boundaries(section: SectionConfig, analysis: AudioAnalysis, fps: int) -> list[float]:
    """Every boundary lands on a whole frame at `fps`.

    This is load-bearing for audio sync, not a tidiness preference.
    render_silent() renders each cut as its own clip and concatenates them, so
    a cut's real position on the timeline is the cumulative sum of *rendered*
    durations -- and ffmpeg can only emit whole frames, so it truncates any
    fractional one. An un-snapped beat grid loses a fraction of a frame on
    every single cut, always in the same direction, and the video drifts
    steadily ahead of the audio.

    Measured on a 300s/129 BPM synthetic track before this snapping existed:
    640 cuts, every one off the grid, the render finishing 3.25s (78 frames)
    short of the audio -- see docs/ARCHITECTURE.md, "Frame-accurate cuts".
    Snapping first makes every cut an exact integer frame count, so the
    concatenated total is exact by construction.
    """
    start = snap_to_frame(section.start, fps)
    end = snap_to_frame(section.end, fps)
    if end <= start:
        raise ValueError(
            f"section {section.name!r} ({section.start}s..{section.end}s) is shorter than one "
            f"frame at {fps}fps and would render to nothing -- widen it, or raise output.fps."
        )

    divisor = _BEAT_DIVISORS[section.cut_density]
    if divisor is None:
        return [start, end]

    beats = [t for t in analysis.beat_times if section.start <= t <= section.end]
    if not beats:
        beats = _tempo_grid(section, analysis)
    if not beats or beats[0] > section.start:
        beats = [section.start, *beats]
    if beats[-1] < section.end:
        beats = [*beats, section.end]

    boundaries = beats[::divisor]
    if boundaries[-1] != section.end:
        boundaries.append(section.end)

    # Snap first, then de-duplicate. Two beats closer together than one frame
    # snap onto the same instant, so this subsumes the old explicit
    # "collapse anything shorter than one frame" pass -- any two *distinct*
    # points on the frame grid are at least one frame apart by construction.
    cleaned = [snap_to_frame(boundaries[0], fps)]
    for b in boundaries[1:]:
        snapped = snap_to_frame(b, fps)
        if snapped > cleaned[-1]:
            cleaned.append(snapped)

    # The de-duplication above can eat the section's true end if the last real
    # beat snaps onto the same frame as the previous boundary (found via
    # tests/test_compose.py, not a real-world render -- see CHANGELOG.md).
    # Snap back onto it rather than silently truncating the section.
    if cleaned[-1] != end:
        if len(cleaned) == 1:
            cleaned.append(end)
        else:
            cleaned[-1] = end
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
