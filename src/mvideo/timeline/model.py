"""
The edit-decision-list (EDL): what `compose()` produces and `render()` consumes.

Nobody hand-authors this. It's the fully-resolved timeline -- every cut, which
asset fills it, which station's grade applies, which effects fire on it --
derived from a CreativeBrief plus the real audio analysis plus the real files
on disk. Treat it as a build artifact: regenerate it, don't hand-edit it. See
docs/decisions/0001-version-the-brief-not-the-render.md.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True)
class Cut:
    """One shot in the timeline."""

    index: int
    start: float  # seconds, on the master timeline
    end: float
    source_path: str  # the actual photo/clip file this cut shows
    station: str
    section: str
    effects: tuple[str, ...] = ()
    is_beat_aligned: bool = True

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class EDL:
    """A fully-resolved timeline, ready to render."""

    song_title: str
    audio_path: str
    duration: float
    fps: int
    resolution: tuple[int, int]
    cuts: tuple[Cut, ...] = ()

    def __post_init__(self) -> None:
        # A render is only as trustworthy as the ordering of what it renders.
        for a, b in itertools.pairwise(self.cuts):
            if b.start < a.end - 1e-6:
                raise ValueError(
                    f"cuts overlap: cut {a.index} ends {a.end:.3f}, cut {b.index} starts {b.start:.3f}"
                )

    def to_dict(self) -> dict:
        return {
            "song_title": self.song_title,
            "audio_path": self.audio_path,
            "duration": self.duration,
            "fps": self.fps,
            "resolution": list(self.resolution),
            "cuts": [
                {
                    "index": c.index,
                    "start": c.start,
                    "end": c.end,
                    "source_path": c.source_path,
                    "station": c.station,
                    "section": c.section,
                    "effects": list(c.effects),
                    "is_beat_aligned": c.is_beat_aligned,
                }
                for c in self.cuts
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EDL":
        cuts = tuple(
            Cut(
                index=c["index"],
                start=c["start"],
                end=c["end"],
                source_path=c["source_path"],
                station=c["station"],
                section=c["section"],
                effects=tuple(c.get("effects", ())),
                is_beat_aligned=c.get("is_beat_aligned", True),
            )
            for c in data["cuts"]
        )
        return cls(
            song_title=data["song_title"],
            audio_path=data["audio_path"],
            duration=data["duration"],
            fps=data["fps"],
            resolution=tuple(data["resolution"]),
            cuts=cuts,
        )
