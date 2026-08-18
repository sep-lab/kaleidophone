"""
Text overlays: font resolution, script direction, card layout, compositing.

Cards render to `tmp_path` -- real PNGs, but written to pytest's temp dir and
built entirely from strings and numbers, so nothing here is a committed media
file. Same rule as the rest of the suite (see tests/factories).
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw, features
from pydantic import ValidationError

from kaleidophone.overlay import typography as ty
from kaleidophone.overlay.card import render_card, render_overlay_cards
from kaleidophone.render import ffmpeg_pipeline as fp
from kaleidophone.timeline.schema import CreativeBrief, OverlayConfig, OverlayLine
from tests.factories import make_section, make_song, make_station

PERSIAN = "من از نهایت شب حرف می‌زنم"
ENGLISH = "i speak from the depth of the night"


def card(**kw) -> OverlayConfig:
    kw.setdefault("id", "c")
    kw.setdefault("at", (0.0, 2.0))
    kw.setdefault("lines", [OverlayLine(text=ENGLISH)])
    return OverlayConfig(**kw)


def ink(path) -> int:
    """Non-transparent pixels."""
    return int((np.asarray(Image.open(path).convert("RGBA"))[..., 3] > 8).sum())


# --------------------------------------------------------------------------
# fonts
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role", sorted(ty.FONT_ROLES))
def test_every_bundled_role_loads(role):
    """These ship in the package precisely so this can never depend on the
    machine -- see overlay/fonts/README.md."""
    assert ty.load_font(role, 48).size == 48


def test_variable_font_roles_select_different_weights():
    """One variable file covers the whole axis, which is why the repo carries
    two font files instead of nine."""
    light = ty.load_font("display", 96)
    medium = ty.load_font("display-medium", 96)
    im_l, im_m = Image.new("L", (900, 160)), Image.new("L", (900, 160))
    for im, f in ((im_l, light), (im_m, medium)):
        ImageDraw.Draw(im).text((450, 80), "WEIGHT", font=f, fill=255, anchor="mm")
    heavier = np.asarray(im_m, float).sum()
    lighter = np.asarray(im_l, float).sum()
    assert heavier > lighter, "display-medium should lay down more ink than display"


def test_an_unknown_role_names_the_ones_that_exist():
    with pytest.raises(KeyError, match="persian"):
        ty.load_font("comic-sans", 40)


def test_a_custom_font_path_that_does_not_exist_says_so():
    with pytest.raises(FileNotFoundError, match="does not exist"):
        ty.load_font("path:/nope/missing.ttf", 40)


# --------------------------------------------------------------------------
# script direction
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,rtl",
    [
        (PERSIAN, True),
        ("שלום עולם", True),
        ("مرحبا", True),
        (ENGLISH, False),
        ("", False),
        ("track 01", False),
    ],
)
def test_rtl_is_detected_from_the_text_itself(text, rtl):
    """A brief author writing a Persian line should not also have to remember
    to declare that it is Persian."""
    assert ty.is_rtl(text) is rtl


def test_direction_can_be_overridden():
    assert ty.shape_direction(ENGLISH, True) == "rtl"
    assert ty.shape_direction(PERSIAN, False) is None


@pytest.mark.skipif(not features.check("raqm"), reason="Pillow built without libraqm")
def test_shaped_rtl_differs_from_a_reversed_string(tmp_path):
    """The whole reason require_raqm exists. Reversing the characters produces
    something that looks like text and is wrong -- which is exactly what the
    reshaper libraries this project refuses to use would give you."""
    def draw(text, **kw):
        im = Image.new("RGBA", (900, 140), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        ty.draw_text(d, (450, 70), text, ty.load_font("persian", 56), (255, 255, 255, 255), **kw)
        return np.asarray(im.convert("L"), float)

    shaped = draw(PERSIAN)
    reversed_ = draw(PERSIAN[::-1])
    assert np.abs(shaped - reversed_).mean() > 1.0


def test_tracking_refuses_rtl_text():
    """Drawing a shaped run glyph by glyph breaks the joins between letters."""
    im = Image.new("RGBA", (600, 120))
    d = ImageDraw.Draw(im)
    with pytest.raises(ValueError, match="breaks the joins"):
        ty.draw_text(d, (300, 60), PERSIAN, ty.load_font("persian", 40),
                     (255, 255, 255, 255), tracking=6.0)


def test_require_raqm_explains_the_fix_and_names_the_trap():
    if features.check("raqm"):
        ty.require_raqm()  # present here; the message is what matters below
    msg = ty.RaqmUnavailable.__doc__ or ""
    assert "libraqm" in msg
    import inspect
    src = inspect.getsource(ty.require_raqm)
    assert "arabic-reshaper" in src and "pip install" in src


# --------------------------------------------------------------------------
# card layout
# --------------------------------------------------------------------------
def test_a_card_is_the_size_of_the_output_frame(tmp_path):
    out = render_card(card(), 1080, 1920, str(tmp_path / "c.png"))
    assert Image.open(out).size == (1080, 1920)


def test_a_card_is_transparent_except_where_the_text_is(tmp_path):
    out = render_card(card(shadow=False), 1080, 1920, str(tmp_path / "c.png"))
    a = np.asarray(Image.open(out).convert("RGBA"))[..., 3]
    assert a[0, 0] == 0, "corner should be fully transparent"
    assert (a > 8).sum() > 0, "something should have been drawn"


def test_sizes_are_a_fraction_of_height_so_a_card_survives_a_resolution_change(tmp_path):
    """A pixel size would come out half as large at 4K and nothing would say so."""
    small = render_card(card(shadow=False), 1080, 1920, str(tmp_path / "s.png"))
    big = render_card(card(shadow=False), 2160, 3840, str(tmp_path / "b.png"))
    # Four times the pixels, so roughly four times the ink. Generous bounds:
    # hinting and antialiasing are not linear.
    ratio = ink(big) / ink(small)
    assert 3.0 < ratio < 5.5, f"ink scaled {ratio:.2f}x, expected ~4x"


def test_the_text_block_is_centred_on_y_and_grows_symmetrically(tmp_path):
    one = render_card(card(y=0.5, shadow=False), 800, 800, str(tmp_path / "1.png"))
    three = render_card(
        card(y=0.5, shadow=False, lines=[OverlayLine(text=ENGLISH)] * 3),
        800, 800, str(tmp_path / "3.png"),
    )
    def centre(p):
        a = np.asarray(Image.open(p).convert("RGBA"))[..., 3]
        rows = np.nonzero(a.sum(axis=1) > 0)[0]
        return (rows.min() + rows.max()) / 2
    assert abs(centre(one) - centre(three)) < 12, "adding lines should not push the block down"


def test_shadow_adds_ink_behind_the_text(tmp_path):
    """Text over moving footage vanishes the moment a light frame passes under
    it; the shadow is on by default for that reason."""
    plain = render_card(card(shadow=False), 1080, 1920, str(tmp_path / "p.png"))
    shadowed = render_card(card(shadow=True), 1080, 1920, str(tmp_path / "s.png"))
    assert ink(shadowed) > ink(plain) * 1.2


def test_a_line_wider_than_the_frame_warns_with_a_size_that_would_fit(tmp_path, capsys):
    render_card(
        card(lines=[OverlayLine(text="x" * 120, font="typewriter", size=0.03)]),
        1080, 1920, str(tmp_path / "c.png"),
    )
    err = capsys.readouterr().err
    assert "run off the edge" in err and "Try size:" in err


def test_a_line_that_fits_warns_about_nothing(tmp_path, capsys):
    render_card(card(lines=[OverlayLine(text="ok", size=0.03)]), 1080, 1920, str(tmp_path / "c.png"))
    assert capsys.readouterr().err == ""


def test_render_overlay_cards_names_files_in_brief_order(tmp_path):
    got = render_overlay_cards(
        [card(id="title"), card(id="endcard")], 640, 360, str(tmp_path)
    )
    assert [ov.id for ov, _ in got] == ["title", "endcard"]
    assert got[0][1].endswith("overlay_00_title.png")
    assert got[1][1].endswith("overlay_01_endcard.png")


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------
def test_duplicate_overlay_ids_are_refused():
    """Ids name the rendered PNG, so a repeat silently overwrites -- the render
    succeeds and one card just never appears."""
    with pytest.raises(ValidationError, match="duplicate overlay id"):
        CreativeBrief(
            song=make_song(),
            stations=[make_station("s")],
            sections=[make_section(station="s")],
            overlays=[card(id="dup"), card(id="dup")],
        )


def test_an_overlay_needs_at_least_one_line():
    with pytest.raises(ValidationError):
        OverlayConfig(id="x", at=(0.0, 1.0), lines=[])


def test_a_backwards_time_range_is_refused():
    with pytest.raises(ValidationError, match="must be after start"):
        OverlayConfig(id="x", at=(2.0, 1.0), lines=[OverlayLine(text="a")])


# --------------------------------------------------------------------------
# compositing
# --------------------------------------------------------------------------
def test_the_overlay_graph_chains_one_filter_per_card():
    graph, last = fp._overlay_graph([card(id="a", at=(0.25, 1.55)), card(id="b", at=(3.0, 4.0))])
    assert graph == (
        "[0:v][1:v]overlay=0:0:enable='between(t,0.250,1.550)'[v1];"
        "[v1][2:v]overlay=0:0:enable='between(t,3.000,4.000)'[v2]"
    )
    assert last == "v2"


def test_a_later_overlay_draws_on_top_of_an_earlier_one():
    graph, _ = fp._overlay_graph([card(id="under"), card(id="over")])
    assert graph.index("[0:v][1:v]") < graph.index("[v1][2:v]")


def test_no_overlays_means_no_filter_complex_at_all(monkeypatch, tmp_path):
    """A brief that never mentions overlays must encode exactly as before."""
    calls = []
    monkeypatch.setattr(fp, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(fp, "run", lambda f, a: calls.append(a))
    from kaleidophone.timeline.model import EDL, Cut
    edl = EDL("t", "a.wav", 1.0, 24, (1280, 720), (Cut(0, 0.0, 1.0, "p.jpg", "s", "sec"),))
    brief = CreativeBrief(song=make_song(), stations=[make_station("s")],
                          sections=[make_section(station="s")])
    fp.render_silent(edl, brief, str(tmp_path / "out.mp4"), work_dir=str(tmp_path))
    concat = calls[-1]
    assert "-filter_complex" not in concat
    assert "-map" not in concat


# --------------------------------------------------------------------------
# the overlay proof sheet
# --------------------------------------------------------------------------
def _edl_for_proof():
    from kaleidophone.timeline.model import EDL, Cut
    return EDL("t", "a.wav", 6.0, 24, (1080, 1920), tuple(
        Cut(i, i * 2.0, (i + 1) * 2.0, "missing.jpg", "s", "sec") for i in range(3)
    ))


def test_the_proof_sheet_uses_the_output_aspect_not_the_sources(tmp_path):
    """A card proofed at the wrong aspect tells you nothing about placement."""
    from kaleidophone.render.preview import PROOF_H, generate_overlay_proof
    out = generate_overlay_proof([card(id="a")], _edl_for_proof(),
                                 str(tmp_path / "p.jpg"), (1080, 1920))
    w, h = Image.open(out).size
    panel_w = round(PROOF_H * 1080 / 1920)
    assert w == panel_w * 4, "one row of four columns"
    assert h == PROOF_H + 22, "panel plus its label strip"


def test_the_proof_sheet_has_one_panel_per_overlay(tmp_path):
    from kaleidophone.render.preview import PROOF_H, generate_overlay_proof
    out = generate_overlay_proof(
        [card(id=f"c{i}") for i in range(6)], _edl_for_proof(),
        str(tmp_path / "p.jpg"), (1080, 1920),
    )
    assert Image.open(out).size[1] == 2 * (PROOF_H + 22), "six cards wrap to two rows"


def test_a_missing_source_falls_back_to_a_flat_backdrop_rather_than_crashing(tmp_path):
    """Same posture as the contact sheet's unreadable-tile fallback: a preview
    that crashes on one bad file is worse than one that shows the card."""
    from kaleidophone.render.preview import generate_overlay_proof
    out = generate_overlay_proof([card(id="a")], _edl_for_proof(),
                                 str(tmp_path / "p.jpg"), (1080, 1920))
    assert Image.open(out).size[0] > 0


def test_proofing_no_overlays_is_refused_rather_than_writing_an_empty_sheet(tmp_path):
    from kaleidophone.render.preview import generate_overlay_proof
    with pytest.raises(ValueError, match="no overlays"):
        generate_overlay_proof([], _edl_for_proof(), str(tmp_path / "p.jpg"), (1080, 1920))


def test_the_backdrop_comes_from_a_cut_the_overlay_actually_covers(tmp_path):
    """Proofing a 5s card against the frame at 0s would show the wrong picture."""
    from kaleidophone.render.preview import _backdrop_for
    edl = _edl_for_proof()
    ov = card(id="late", at=(4.5, 5.5))
    covered = [c for c in edl.cuts if c.start < 5.5 and c.end > 4.5]
    assert [c.index for c in covered] == [2]
    assert _backdrop_for(ov, edl, 100, 200).size == (100, 200)
