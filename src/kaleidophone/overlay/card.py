"""
Render an OverlayConfig to an RGBA PNG the render pipeline can composite.

Sizes and positions are *fractions of the output frame height*, never pixels.
A card designed against a 1080x1920 delivery has to still be right when the
same brief is re-rendered at 2160x3840, and a pixel size silently would not
be -- it would come out half as large, which is the kind of bug you only catch
by putting the two files side by side.
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

from kaleidophone.overlay.typography import draw_text, load_font, with_shadow
from kaleidophone.timeline.schema import OverlayConfig, OverlayLine


def _rgba(hex_color: str, opacity: float) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, max(0, min(255, round(255 * opacity))))


def render_card(overlay: OverlayConfig, w: int, h: int, out_path: str) -> str:
    """Draw one overlay's lines onto a transparent `w`x`h` frame."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    sizes = [max(1, round(line.size * h)) for line in overlay.lines]
    gaps = [round(overlay.line_gap * h)] * max(0, len(overlay.lines) - 1)
    block_height = sum(sizes) + sum(gaps)

    x = {"left": 0.08, "center": 0.5, "right": 0.92}[overlay.align] * w
    anchor_x = {"left": "l", "center": "m", "right": "r"}[overlay.align]

    # `y` is the vertical centre of the whole block, so adding a line to a card
    # grows it symmetrically instead of pushing everything downwards.
    cursor = overlay.y * h - block_height / 2

    for line, size in zip(overlay.lines, sizes):
        _draw_line(draw, line, x, cursor + size / 2, size, anchor_x, h)
        _warn_if_wider_than_frame(draw, line, size, w, h, overlay.id)
        cursor += size + (gaps.pop(0) if gaps else 0)

    if overlay.shadow:
        layer = with_shadow(layer)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    layer.save(out_path)
    return out_path


# Cards are drawn blind -- nothing renders a preview of one before the video
# is encoded, so a line that runs off the edge is discovered by watching the
# finished render. Measure it here instead.
_SAFE_WIDTH = 0.92


def _warn_if_wider_than_frame(
    draw: ImageDraw.ImageDraw,
    line: OverlayLine,
    size_px: int,
    w: int,
    h: int,
    overlay_id: str,
) -> None:
    font = load_font(line.font, size_px)
    width = draw.textlength(line.text, font=font) + line.tracking * h * max(0, len(line.text) - 1)
    if width <= w * _SAFE_WIDTH:
        return
    suggested = line.size * (w * _SAFE_WIDTH) / width
    print(
        f"warning: overlay {overlay_id!r} line {line.text[:40]!r} is {width:.0f}px wide "
        f"in a {w}px frame -- it will run off the edge. "
        f"Try size: {suggested:.3f} (currently {line.size}), or shorten the line.",
        file=sys.stderr,
    )


def _draw_line(
    draw: ImageDraw.ImageDraw,
    line: OverlayLine,
    x: float,
    y: float,
    size_px: int,
    anchor_x: str,
    frame_h: int,
) -> None:
    draw_text(
        draw,
        (x, y),
        line.text,
        load_font(line.font, size_px),
        _rgba(line.color, line.opacity),
        anchor=f"{anchor_x}m",
        rtl=line.rtl,
        tracking=line.tracking * frame_h,
    )


def render_overlay_cards(
    overlays: list[OverlayConfig], w: int, h: int, out_dir: str
) -> list[tuple[OverlayConfig, str]]:
    """Render every overlay in a brief. Returns (overlay, png_path) pairs in
    brief order, which is also the order they are composited -- a later overlay
    draws on top of an earlier one where their time ranges intersect."""
    return [
        (ov, render_card(ov, w, h, os.path.join(out_dir, f"overlay_{i:02d}_{ov.id}.png")))
        for i, ov in enumerate(overlays)
    ]
