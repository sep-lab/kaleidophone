"""
Render a wave map: an RMS envelope with structural markers, the same idea as
the reference case study's wave-map image. Drawn with Pillow rather than
matplotlib -- one fewer dependency for a single bar chart (see
docs/decisions/0002-deterministic-edit-engine.md, "keep it minimal"). Default
palette follows docs/CREATIVE-GUIDE.md's amber/cool/red vocabulary.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from kaleidophone.audio.analysis import AudioAnalysis

BG = (13, 12, 15)
WAVE = (255, 176, 61)  # amber -- the warm "room" station in the reference case study
GRID = (54, 50, 46)
MARKER_QUIET = (110, 168, 255)  # cool blue for hush / quiet passages
MARKER_JUMP = (255, 79, 79)  # red for detected drops / switches
TEXT = (230, 230, 230)


def render_wavemap(
    analysis: AudioAnalysis,
    out_path: str,
    *,
    width: int = 1600,
    height: int = 360,
    section_markers: list[tuple[float, str]] | None = None,
) -> str:
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if analysis.duration <= 0:
        img.save(out_path)
        return out_path

    # Faint beat grid: every 4th beat, so tempo reads visually without 600+ solid lines.
    for i, t in enumerate(analysis.beat_times):
        if i % 4:
            continue
        x = int(t / analysis.duration * width)
        draw.line([(x, 0), (x, height)], fill=GRID, width=1)

    # RMS envelope as a centered bar chart, dB range normalized to [0, 1].
    rms, times = analysis.rms_db, analysis.rms_times
    if rms:
        lo, hi = min(rms), max(rms)
        span = (hi - lo) or 1.0
        mid = height // 2
        step = max(1, len(rms) // width)
        for i in range(0, len(rms), step):
            level = (rms[i] - lo) / span
            bar_h = int(level * (height * 0.42))
            x = int(times[i] / analysis.duration * width)
            draw.line([(x, mid - bar_h), (x, mid + bar_h)], fill=WAVE, width=1)

    # Mark detected quiet passages ("the hush") and energy jumps ("the switch").
    for q in analysis.quiet_passages:
        x0 = int(q.start / analysis.duration * width)
        x1 = int(q.end / analysis.duration * width)
        draw.rectangle([x0, 0, x1, 6], fill=MARKER_QUIET)
    for j in analysis.energy_jumps:
        x = int(j.time / analysis.duration * width)
        draw.line([(x, 0), (x, height)], fill=MARKER_JUMP, width=2)

    # Named section markers, if the brief supplied any.
    for t, label in section_markers or []:
        x = int(t / analysis.duration * width)
        draw.line([(x, 0), (x, height)], fill=TEXT, width=1)
        draw.text((x + 4, 4), label, fill=TEXT)

    img.save(out_path)
    return out_path
