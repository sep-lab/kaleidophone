"""
A contact sheet: what an EDL will actually cut to, one thumbnail per cut,
with zero ffmpeg subprocess calls -- so you can sanity-check the *edit*
(right photo, right section, right effect) in about a second, before paying
for the full render. This is the "confirm before you render" half of the
workflow docs/CREATIVE-GUIDE.md describes; the other half is
render.ffmpeg_pipeline.mux_audio(), which re-syncs audio onto an
already-approved render without redoing it.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

from mvideo.timeline.model import EDL

CELL = 160
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def generate_contact_sheet(edl: EDL, out_path: str, *, columns: int = 8) -> str:
    cuts = edl.cuts
    if not cuts:
        raise ValueError("EDL has no cuts to preview")

    rows = -(-len(cuts) // columns)  # ceil division without importing math for one use
    sheet = Image.new("RGB", (columns * CELL, rows * (CELL + 24)), (18, 17, 20))
    draw = ImageDraw.Draw(sheet)

    for i, cut in enumerate(cuts):
        col, row = i % columns, i // columns
        x, y = col * CELL, row * (CELL + 24)
        thumb = _load_thumb(cut.source_path)
        sheet.paste(thumb, (x + (CELL - thumb.width) // 2, y + (CELL - thumb.height) // 2))
        draw.text((x + 4, y + CELL + 2), f"{cut.section[:10]} {cut.start:.1f}s", fill=(220, 220, 220))
        if cut.effects:
            draw.text((x + 4, y + CELL + 13), "+".join(cut.effects)[:22], fill=(255, 176, 61))

    sheet.save(out_path, quality=88)
    return out_path


def _load_thumb(source_path: str) -> Image.Image:
    try:
        if os.path.splitext(source_path)[1].lower() in VIDEO_EXTS:
            img = _video_first_frame(source_path)
        else:
            img = Image.open(source_path).convert("RGB")
    except Exception:
        img = Image.new(
            "RGB", (CELL, CELL), (60, 20, 20)
        )  # a visible "couldn't load this one" tile, not a crash
    img.thumbnail((CELL - 8, CELL - 8))
    return img


def _video_first_frame(path: str) -> Image.Image:
    import cv2

    cap = cv2.VideoCapture(path)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return Image.new("RGB", (CELL, CELL), (60, 20, 20))
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
