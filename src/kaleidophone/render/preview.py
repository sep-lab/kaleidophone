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

import io
import os
import tempfile

from PIL import Image, ImageDraw

from kaleidophone.overlay.card import render_card
from kaleidophone.render._ffmpeg_util import first_frame_png
from kaleidophone.timeline.model import EDL
from kaleidophone.timeline.schema import OverlayConfig

CELL = 160
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Overlay proofs get their own sheet at a size where you can actually read the
# text. A 160px contact-sheet cell shows you *when* a card appears; it cannot
# show you whether the type is too big, sitting in the wrong third, or running
# off the edge -- which is most of what goes wrong with text.
PROOF_H = 380


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
    png = first_frame_png(path)
    if png is None:
        return Image.new("RGB", (CELL, CELL), (60, 20, 20))
    return Image.open(io.BytesIO(png)).convert("RGB")


def generate_overlay_proof(
    overlays: list[OverlayConfig],
    edl: EDL,
    out_path: str,
    resolution: tuple[int, int],
    *,
    columns: int = 4,
) -> str:
    """One panel per overlay: the rendered card over a frame it will actually
    cover, at the output's aspect ratio.

    Cards are otherwise drawn blind -- the only way to see whether a lyric line
    is the right size and in the right third is to pay for a full render, which
    defeats the point of previewing at all. See the render skill's "always
    preview before rendering".
    """
    if not overlays:
        raise ValueError("no overlays to proof")

    w, h = resolution
    panel_w = max(1, round(PROOF_H * w / h))
    rows = -(-len(overlays) // columns)
    sheet = Image.new("RGB", (columns * panel_w, rows * (PROOF_H + 22)), (18, 17, 20))
    draw = ImageDraw.Draw(sheet)

    with tempfile.TemporaryDirectory(prefix="kaleidophone_proof_") as tmp:
        for i, ov in enumerate(overlays):
            x = (i % columns) * panel_w
            y = (i // columns) * (PROOF_H + 22)

            backdrop = _backdrop_for(ov, edl, panel_w, PROOF_H)
            card_path = render_card(ov, panel_w, PROOF_H, os.path.join(tmp, f"{i}.png"))
            backdrop.alpha_composite(Image.open(card_path).convert("RGBA"))
            sheet.paste(backdrop.convert("RGB"), (x, y))

            draw.rectangle((x, y, x + panel_w - 1, y + PROOF_H - 1), outline=(70, 70, 78))
            start, end = ov.at
            draw.text((x + 4, y + PROOF_H + 3), f"{ov.id}  {start:.2f}-{end:.2f}s", fill=(220, 220, 220))
            draw.text(
                (x + 4, y + PROOF_H + 13),
                f"{len(ov.lines)} line(s)  y={ov.y}  {ov.align}",
                fill=(255, 176, 61),
            )

    sheet.save(out_path, quality=90)
    return out_path


def _backdrop_for(overlay: OverlayConfig, edl: EDL, w: int, h: int) -> Image.Image:
    """A frame from a cut this overlay actually covers, fitted to the output aspect.

    Deliberately the *ungraded* source. Applying the station's colour grade
    here would mean reimplementing `render/effects.py::color_grade` in Pillow,
    and two implementations of one look drift -- the preview would slowly stop
    predicting the render, which is worse than not predicting the grade at all.

    So this proof answers size, placement, alignment and overflow, all of which
    are grade-independent. It does not answer contrast against the final grade;
    that still needs a render.
    """
    start, end = overlay.at
    covered = [c for c in edl.cuts if c.start < end and c.end > start]
    source = covered[len(covered) // 2].source_path if covered else None

    base = Image.new("RGBA", (w, h), (26, 25, 29, 255))
    if source is None:
        return base
    try:
        img = _load_full(source)
    except Exception:
        return base
    # Scale to cover, then centre-crop -- the same shape as the `fill` framing
    # mode, so the proof is honest about what a default render would show.
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
    left, top = (img.width - w) // 2, (img.height - h) // 2
    base.paste(img.crop((left, top, left + w, top + h)).convert("RGB"), (0, 0))
    return base


def _load_full(source_path: str) -> Image.Image:
    if os.path.splitext(source_path)[1].lower() in VIDEO_EXTS:
        return _video_first_frame(source_path)
    return Image.open(source_path).convert("RGB")
