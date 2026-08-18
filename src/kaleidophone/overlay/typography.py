"""
Font resolution, script direction, and the two text-drawing primitives.

Everything here is Pillow-only -- no ffmpeg. A card is rendered to an RGBA PNG
and handed to the render pipeline as an ordinary overlay input.
"""

from __future__ import annotations

import functools
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# Roles rather than filenames, so a brief says what a line *is* and the
# typographic decision lives in one place. `path:/some/font.ttf` is the escape
# hatch for anything not bundled.
FONT_ROLES: dict[str, tuple[str, int | None]] = {
    # role            file                          default variable weight
    "mono": ("SpaceMono-Regular.ttf", None),
    "mono-bold": ("SpaceMono-Bold.ttf", None),
    "typewriter": ("CourierPrime-Regular.ttf", None),
    "display": ("SpaceGrotesk-Variable.ttf", 300),
    "display-medium": ("SpaceGrotesk-Variable.ttf", 500),
    "persian": ("Vazirmatn-Variable.ttf", 400),
    "persian-bold": ("Vazirmatn-Variable.ttf", 700),
}


class RaqmUnavailable(RuntimeError):
    """Pillow was built without libraqm, so complex scripts cannot be shaped."""


def require_raqm() -> None:
    """Refuse to render RTL text without real shaping.

    Failing loudly here is the whole point. Pillow will happily draw an
    unshaped Arabic string -- disconnected letterforms in visual order -- and
    the result *looks* like text, so nothing downstream catches it. A person
    who reads the script sees immediately that it is broken; a person who does
    not, ships it.
    """
    if not features.check("raqm"):
        raise RaqmUnavailable(
            "This text needs right-to-left shaping, but Pillow was built without "
            "libraqm.\n"
            "Fix: pip install --upgrade --force-reinstall Pillow  (the official "
            "wheels bundle libraqm), or build Pillow against libraqm/harfbuzz/fribidi.\n"
            "Do NOT work around this with arabic-reshaper or python-bidi: they "
            "reorder characters instead of shaping them, which produces broken "
            "letterforms that look fine if you cannot read the script."
        )


# Unicode blocks whose scripts run right to left. Checked by codepoint rather
# than by asking the caller to set a flag -- a brief author writing a Persian
# line should not also have to remember to say it is Persian.
_RTL_RANGES = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic (includes Persian)
    (0x0700, 0x074F),  # Syriac
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB1D, 0xFDFF),  # Hebrew/Arabic presentation forms
    (0xFE70, 0xFEFF),  # Arabic presentation forms-B
)


def is_rtl(text: str) -> bool:
    """True if `text` contains any right-to-left script."""
    return any(any(lo <= ord(ch) <= hi for lo, hi in _RTL_RANGES) for ch in text)


def shape_direction(text: str, override: bool | None = None) -> str | None:
    """The `direction=` Pillow should shape with, or None to leave it alone."""
    rtl = is_rtl(text) if override is None else override
    return "rtl" if rtl else None


@functools.lru_cache(maxsize=64)
def load_font(role: str, size_px: int) -> ImageFont.FreeTypeFont:
    """Resolve a role name (or `path:/abs/font.ttf`) to a sized font.

    Cached because a card re-renders the same handful of (role, size) pairs for
    every overlay in a brief, and opening a variable font is not free.
    """
    size_px = max(1, int(size_px))

    if role.startswith("path:"):
        path = role[len("path:"):]
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"font {path!r} does not exist. Use one of the bundled roles "
                f"({', '.join(sorted(FONT_ROLES))}) or an absolute path to a .ttf/.otf."
            )
        return ImageFont.truetype(path, size_px)

    try:
        filename, weight = FONT_ROLES[role]
    except KeyError:
        raise KeyError(
            f"unknown font role {role!r}. Bundled roles: "
            f"{', '.join(sorted(FONT_ROLES))}. For anything else use "
            f"'path:/absolute/path/to/font.ttf'."
        ) from None

    font = ImageFont.truetype(os.path.join(FONTS_DIR, filename), size_px)
    if weight is not None:
        # Variable fonts: one file covers the whole weight axis, so the role
        # carries the weight instead of the repository carrying nine files.
        font.set_variation_by_axes([weight])
    return font


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    *,
    anchor: str = "mm",
    rtl: bool | None = None,
    tracking: float = 0.0,
) -> None:
    """One line of text, shaped correctly, optionally letter-spaced."""
    direction = shape_direction(text, rtl)
    if direction == "rtl":
        require_raqm()

    if tracking:
        _draw_tracked(draw, xy, text, font, fill, anchor=anchor, tracking=tracking)
        return

    kwargs = {"font": font, "fill": fill, "anchor": anchor}
    if direction:
        # `language` matters: it selects locale-specific shaping rules, and for
        # Persian it is what gives the correct forms of the Arabic-script
        # letters Persian uses differently (notably heh and kaf).
        kwargs["direction"] = direction
        kwargs["language"] = "fa" if _is_persian(text) else "ar"
    draw.text(xy, text, **kwargs)


def _is_persian(text: str) -> bool:
    """Persian-specific codepoints that Arabic does not use."""
    return any(ch in "پچژگکی" for ch in text)


def _draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    *,
    anchor: str,
    tracking: float,
) -> None:
    """Letter-spaced text, drawn glyph by glyph.

    Pillow has no tracking parameter, and letterspaced monospace caps are the
    single most recognisable element of this house style, so it is worth the
    manual loop.

    Deliberately refuses to track RTL text: spacing a shaped run character by
    character breaks the joins between letters, which is precisely the failure
    `require_raqm` exists to prevent.
    """
    if is_rtl(text):
        raise ValueError(
            "tracking cannot be applied to right-to-left text: drawing a shaped "
            "run glyph by glyph breaks the joins between letters. Set tracking "
            "to 0 for this line, or use a wider font."
        )

    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)

    x, y = xy
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total

    vertical = anchor[1] if len(anchor) > 1 else "a"
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, anchor=f"l{vertical}")
        x += w + tracking


def with_shadow(
    layer: Image.Image,
    *,
    blur: float = 6.0,
    offset: tuple[int, int] = (3, 4),
    alpha: int = 160,
) -> Image.Image:
    """Composite a blurred black copy of `layer` behind itself.

    Text over moving footage is unreadable without this -- a light frame passes
    under a light glyph and the line simply vanishes for a few seconds. The
    defaults are the ones this house style has settled on.
    """
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    black = Image.new("RGBA", layer.size, (0, 0, 0, alpha))
    shadow.paste(black, (0, 0), layer.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))

    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, offset)
    out.alpha_composite(layer)
    return out
