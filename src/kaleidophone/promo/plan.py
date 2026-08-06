"""
Generate a promo pack (chapters + teaser cadence + a pinned-comment prompt)
from a brief and its audio analysis -- the same shape as the reference case
study's captions-and-promo doc, generalized. Text only; posting is still a
human's job.
"""

from __future__ import annotations

from kaleidophone.audio.analysis import AudioAnalysis
from kaleidophone.timeline.schema import CreativeBrief


def generate_promo_pack(brief: CreativeBrief, analysis: AudioAnalysis) -> str:
    lines = [f"# {brief.song.title} — Promo Pack", ""]
    if brief.song.artist:
        lines.append(f"**Artist:** {brief.song.artist}  ")
    lines.append(f"**Duration:** {_fmt_time(analysis.duration)} · **BPM:** {analysis.bpm:.1f}  ")
    lines.append("")

    lines.append("## Suggested caption")
    lines.append("")
    lines.append(_suggest_caption(brief))
    lines.append("")

    lines.append("## Chapters (for a YouTube Premiere description)")
    lines.append("")
    for section in brief.sections:
        lines.append(f"- `{_fmt_time(section.start)}` — {section.name}")
    lines.append("")

    if brief.promo:
        lines.append("## Teaser cadence")
        lines.append("")
        for day in sorted(brief.promo.teaser_cadence_days):
            lines.append(f"- **T{day:+d}** — teaser drop")
        lines.append("")

        if brief.promo.handles:
            lines.append("## Collaborators to tag")
            lines.append("")
            lines.append(", ".join(brief.promo.handles))
            lines.append("")

    highlight = max(analysis.energy_jumps, key=lambda j: j.z_score, default=None)
    if highlight:
        lines.append("## Suggested pinned comment")
        lines.append("")
        lines.append(f'"the switch is at {_fmt_time(highlight.time)}"')
        lines.append("")

    return "\n".join(lines)


def _suggest_caption(brief: CreativeBrief) -> str:
    """A short, templated social caption -- a starting draft to rewrite, not
    a final copy. Station descriptions double as mood words here, which is
    the point of writing them as prose in the brief rather than just a name."""
    mood_words = [
        s.description.split(",")[0].split(" -- ")[0].strip(". ") for s in brief.stations if s.description
    ]
    mood = ", ".join(w.lower() for w in mood_words[:3]) if mood_words else "a journey"
    who = f" — {brief.song.artist}" if brief.song.artist else ""
    return f'"{brief.song.title}"{who}. {mood}. out now.'


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
