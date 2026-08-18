"""
Text burned into the picture: title cards, lyric lines, credits, end cards.

Two rules this module exists to enforce, both learned the hard way:

1. **Fonts ship with the package.** A font resolved from a system path renders
   on one machine and silently renders *differently* on every other one, which
   breaks the promise that the same brief produces the same video every time.
   See `fonts/README.md`.
2. **Right-to-left text is shaped, never reversed.** Pillow delegates to libraqm
   (HarfBuzz) when given `direction=`; reversing the string by hand -- or
   reaching for a "reshaper" library -- produces text that looks plausible to
   someone who cannot read it and is wrong to someone who can. See
   `typography.py::shape_direction`.
"""

from kaleidophone.overlay.card import render_overlay_cards
from kaleidophone.overlay.typography import (
    FONT_ROLES,
    RaqmUnavailable,
    is_rtl,
    load_font,
    require_raqm,
)

__all__ = [
    "FONT_ROLES",
    "RaqmUnavailable",
    "is_rtl",
    "load_font",
    "render_overlay_cards",
    "require_raqm",
]
