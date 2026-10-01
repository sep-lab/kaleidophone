"""Generate the release copy pack from a brief plus its audio analysis."""

from __future__ import annotations

from kaleidophone.audio.analysis import AudioAnalysis
from kaleidophone.timeline.schema import CreativeBrief, ReleaseConfig

# Roughly how many characters each surface will show before truncating. Used
# to warn, never to cut: silently trimming someone's caption is worse than
# telling them it is long.
# A "moment" in the first few seconds is the track starting, not a switch.
# Suggesting `the switch is at 0:00` is worse than suggesting nothing: it reads
# as the tool not listening.
MIN_PINNED_COMMENT_TIME = 15.0

# A pinned comment also needs somewhere to point *back* from -- on a very short
# piece every timestamp is "near the start".
MIN_DURATION_FOR_PINNED_COMMENT = 45.0


def generate_release_pack(
    brief: CreativeBrief, analysis: AudioAnalysis, drafts: list[str] | None = None
) -> str:
    """The pack as markdown. ``drafts`` -- already-rendered lines, e.g. a local model's caption
    drafts (`kaleidophone.release.local_llm`) -- goes after the posting order, before the notes."""
    rel = brief.release or ReleaseConfig()
    out: list[str] = []
    w = out.append

    title = brief.song.title
    artist = brief.song.artist
    w(f"# {title} — release pack")
    w("")
    meta = [f"**Duration:** {fmt_time(analysis.duration)}", f"**BPM:** {analysis.bpm:.1f}"]
    if artist:
        meta.insert(0, f"**Artist:** {artist}")
    if rel.date:
        meta.append(f"**Date:** {rel.date}")
    w(" · ".join(meta))
    w("")
    w("> Generated from the brief and the audio analysis. Every timestamp, chapter")
    w("> and credit here is derived, so the facts are right. **The voice is not** —")
    w("> this is a scaffold to rewrite, not copy to paste. See the notes at the end")
    w("> for what it could not know.")
    w("")

    if rel.concept:
        w("## The line everything is written around")
        w("")
        w(f"> {rel.concept}")
        w("")

    for platform in rel.platforms:
        out.extend(_PLATFORM_BLOCKS[platform](brief, analysis, rel))

    out.extend(_timed_comments(brief, analysis))
    out.extend(_posting_order(rel))
    if drafts:
        out.extend(drafts)
    out.extend(_notes_for_you(brief, analysis, rel))
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
# per-platform blocks
# --------------------------------------------------------------------------
def _soundcloud(brief: CreativeBrief, analysis: AudioAnalysis, rel: ReleaseConfig) -> list[str]:
    o = ["## SoundCloud", "", "**Title**", "", "```", brief.song.title, "```", ""]
    o += ["**Description**", "", "```"]
    if rel.concept:
        o += [rel.concept, ""]
    o += [_mood_line(brief), ""]
    o += _credit_lines(rel)
    o += ["```", ""]
    if rel.secondary_language:
        o += [
            f"**Description — {rel.secondary_language}**",
            "",
            "> Write this as a *mirror*, not a translation: the same image, said the",
            "> way it would be said in this language. A translated caption reads",
            "> translated.",
            "",
            "```",
            "",
            "```",
            "",
        ]
    o += ["**Shorter alternate**", "", "```", _short_caption(brief, rel), "```", ""]
    if rel.tags:
        o += ["**Tags**", "", "```", ", ".join(rel.tags), "```", ""]
    return o


def _youtube(brief: CreativeBrief, analysis: AudioAnalysis, rel: ReleaseConfig) -> list[str]:
    o = ["## YouTube", "", "**Title**", "", "```"]
    who = f"{brief.song.artist} — " if brief.song.artist else ""
    o += [f"{who}{brief.song.title}", "```", "", "**Description**", "", "```"]
    if rel.concept:
        o += [rel.concept, ""]
    o += ["CHAPTERS"]
    for section in brief.sections:
        o.append(f"{fmt_time(section.start)} {section.name}")
    o.append("")
    o += _credit_lines(rel)
    o += ["```", ""]

    jump = _strongest_jump(analysis)
    if jump is not None:
        o += [
            "**Pinned comment**",
            "",
            "```",
            f"the switch is at {fmt_time(jump)}",
            "```",
            "",
            f"_Derived from the strongest detected energy jump ({jump:.2f}s). Rename it"
            " to whatever that moment is actually called._",
            "",
        ]
    return o


def _instagram(brief: CreativeBrief, analysis: AudioAnalysis, rel: ReleaseConfig) -> list[str]:
    o = ["## Instagram (feed / reel)", "", "**Caption**", "", "```"]
    if rel.concept:
        o += [rel.concept, ""]
    o += [_short_caption(brief, rel)]
    if rel.links:
        o += ["", "link in bio"]
    o += ["```", ""]
    if rel.tags:
        o += ["**Hashtags**", "", "```", " ".join(f"#{t.replace(' ', '')}" for t in rel.tags), "```", ""]
    return o


def _story(brief: CreativeBrief, analysis: AudioAnalysis, rel: ReleaseConfig) -> list[str]:
    """A story is a layout, not a caption -- so this emits a spec, not copy."""
    o = ["## Story", "", "**Sticker text**", "", "```", f"{brief.song.title} · OUT NOW", "```", ""]
    o += ["**Placement**", ""]
    o += [
        "- Sticker text small, top third — the bottom third is where the link sticker goes",
        "- Link sticker bottom-centre" + (f" → {next(iter(rel.links.values()))}" if rel.links else ""),
        "- Keep the middle third clear: it is where the eye lands and where any burned-in",
        "  card from the video already sits",
        "",
    ]
    return o


_PLATFORM_BLOCKS = {
    "soundcloud": _soundcloud,
    "youtube": _youtube,
    "instagram": _instagram,
    "story": _story,
}


# --------------------------------------------------------------------------
# derived sections
# --------------------------------------------------------------------------
def _timed_comments(brief: CreativeBrief, analysis: AudioAnalysis) -> list[str]:
    """SoundCloud timed comments, from the structure the analysis already found.

    This is the highest-leverage manual step in a release and it is pure
    derivation -- the interesting timestamps are the section boundaries and the
    detected energy jumps.
    """
    if len(brief.sections) < 2:
        return []
    o = ["## Timed comments", "", "One per structural moment. Text is yours; the times are not.", ""]
    for section in brief.sections[1:]:
        o.append(f"- `{fmt_time(section.start)}` — {section.name}")
    o.append("")
    return o


def _posting_order(rel: ReleaseConfig) -> list[str]:
    """Order matters and is easy to get wrong under time pressure: the link has
    to be live before the post that points at it."""
    if not rel.platforms:
        return []
    order = [p for p in ("soundcloud", "youtube", "instagram", "story") if p in rel.platforms]
    o = ["## Posting order", ""]
    reasons = {
        "soundcloud": "the streaming link has to exist before anything points at it",
        "youtube": "upload, then pin the comment above",
        "instagram": "update the bio link first, then post the reel",
        "story": "link sticker last — it needs a live destination",
    }
    for i, p in enumerate(order, 1):
        o.append(f"{i}. **{p}** — {reasons[p]}")
    o.append("")
    return o


def _notes_for_you(brief: CreativeBrief, analysis: AudioAnalysis, rel: ReleaseConfig) -> list[str]:
    """What the generator could not know, stated plainly.

    A pack that only produced confident-looking output would be worse than one
    that says where it is guessing -- the gaps are exactly where a person's
    attention is worth most.
    """
    notes = []
    if not rel.concept:
        notes.append(
            "**No `release.concept` set.** Every caption above is missing its spine. "
            "One line saying what the record *is* changes all of them."
        )
    if not rel.credits:
        notes.append("No credits in the brief — nobody is named or tagged anywhere above.")
    if not rel.tags:
        notes.append("No tags set, so the tag and hashtag blocks are missing.")
    if not rel.links:
        notes.append("No links set: 'link in bio' and the story sticker point at nothing.")
    if rel.secondary_language:
        notes.append(
            f"The {rel.secondary_language} block is intentionally blank. It should be "
            f"written, not translated."
        )
    if not brief.song.artist:
        notes.append("`song.artist` is unset, so titles are bare.")
    if _strongest_jump(analysis) is None:
        notes.append(
            f"No suggested pinned comment: either no energy jump was detected after "
            f"{MIN_PINNED_COMMENT_TIME:.0f}s, or the track is under "
            f"{MIN_DURATION_FOR_PINNED_COMMENT:.0f}s. A jump in the opening seconds is "
            f"the song starting, not a moment worth pointing at."
        )
    notes.append(
        "Genre and mood tags are platform fields nobody can derive from an energy "
        "envelope — set them by hand on each upload."
    )
    return ["## Notes for you (not for the caption)", "", *[f"- {n}" for n in notes], ""]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _credit_lines(rel: ReleaseConfig) -> list[str]:
    o = []
    for c in rel.credits:
        handle = f" ({c.handle})" if c.handle else ""
        o.append(f"{c.role}: {c.name}{handle}")
    if rel.label:
        o.append(f"label: {rel.label}")
    return o


def _mood_line(brief: CreativeBrief) -> str:
    """Station descriptions double as mood words, which is why writing them as
    short evocative prose in the brief pays off twice."""
    words = [
        s.description.split(",")[0].split(" -- ")[0].strip(". ")
        for s in brief.stations
        if s.description
    ]
    return ", ".join(w.lower() for w in words[:3]) if words else ""


mood_line = _mood_line  # public: the CLI hands it to a local model as mood words


def _short_caption(brief: CreativeBrief, rel: ReleaseConfig) -> str:
    who = f" — {brief.song.artist}" if brief.song.artist else ""
    mood = _mood_line(brief)
    tail = f" {mood}." if mood else ""
    return f'"{brief.song.title}"{who}.{tail} out now.'


def _strongest_jump(analysis: AudioAnalysis) -> float | None:
    """The song's single most interesting timestamp, or None if it hasn't got one.

    Filtered rather than just `max()`: a jump inside the first seconds is the
    track beginning, and on a very short piece nothing is far enough in to be
    worth pointing at. Both cases produce a suggestion that reads as the tool
    not having listened, which costs more trust than an absent section.
    """
    if analysis.duration < MIN_DURATION_FOR_PINNED_COMMENT:
        return None
    candidates = [j for j in analysis.energy_jumps if j.time >= MIN_PINNED_COMMENT_TIME]
    jump = max(candidates, key=lambda j: j.z_score, default=None)
    return jump.time if jump else None


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def minimal_brief(
    audio_path: str,
    title: str,
    duration: float,
    *,
    artist: str | None = None,
    concept: str | None = None,
    primary_language: str = "en",
    secondary_language: str | None = None,
) -> CreativeBrief:
    """A brief for a release that has no footage brief -- a canvas piece's, say -- so `kit` can
    write its pack from the song alone: one station, one section covering the song."""
    return CreativeBrief(
        song={"title": title, "artist": artist, "audio_path": audio_path},
        stations=[{"name": "song"}],
        sections=[{"name": "the song", "start": 0.0, "end": max(duration, 0.1), "station": "song"}],
        release={
            "concept": concept,
            "primary_language": primary_language,
            "secondary_language": secondary_language,
        },
    )


def release_facts(brief: CreativeBrief, analysis: AudioAnalysis) -> list[str]:
    """What the tool knows for certain about the release, in words a caption writer can use:
    the biggest change, the chapters, the date. Not the length or the tempo -- true, and an
    invitation to a filler line ("three minutes at 96 BPM")."""
    rel = brief.release or ReleaseConfig()
    facts = []
    jump = _strongest_jump(analysis)
    if jump is not None:
        facts.append(f"the biggest change in the song comes at {fmt_time(jump)}")
    if len(brief.sections) > 1:
        facts.append("chapters: " + ", ".join(f"{fmt_time(s.start)} {s.name}" for s in brief.sections))
    if rel.date:
        facts.append(f"release date {rel.date}")
    return facts

