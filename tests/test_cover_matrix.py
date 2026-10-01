"""cover/matrix.py: one square master (and a portrait) to every platform's cover.

Every image here is drawn in code into tmp_path -- gradients and noise, never
a photo (AGENTS.md) -- and Pillow is the only thing that runs, so the suite
needs no ffmpeg.
"""

from __future__ import annotations

import dataclasses
import io
import sys
import zlib

import numpy as np
import PIL
import pytest
from PIL import Image, ImageCms

from kaleidophone.cover import matrix
from kaleidophone.render import platforms as pf


def picture(width: int, height: int, *, mode: str = "RGB", grain: float = 0.0, seed: int = 0) -> Image.Image:
    """A synthetic picture: a diagonal gradient with a bright disc in the
    middle, so a crop or a scale shows; grain makes it hard to compress."""
    y, x = np.mgrid[0:height, 0:width]
    base = np.stack([x / max(width - 1, 1), y / max(height - 1, 1), 0.5 + 0 * x], axis=-1) * 200
    disc = (x - width / 2) ** 2 + (y - height / 2) ** 2 < (min(width, height) / 6) ** 2
    base[disc] = 250
    if grain:
        base = base + np.random.default_rng(seed).normal(0, grain, base.shape)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    return img if mode == "RGB" else img.convert(mode)


def blank(width: int, height: int) -> Image.Image:
    """A flat picture, for the tests where only the size matters."""
    return Image.new("RGB", (width, height), (90, 60, 120))


def save(img: Image.Image, path, **params) -> str:
    if str(path).endswith(".png"):
        params.setdefault("compress_level", 1)
    img.save(path, **params)
    return str(path)


def name_for(pid: str) -> str:
    return f"song.cover.{pid}.jpg"


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------
def test_every_cover_is_planned_from_the_master_or_the_portrait():
    plans = matrix.plan_covers(
        ["spotify-cover", "soundcloud-header", "youtube-thumbnail", "instagram-reel-cover", "instagram-carousel-image"],
        name_for, portrait=False,
    )
    assert [(p.platform.id, p.source, p.method, p.drawn) for p in plans] == [
        ("spotify-cover", "master", "scale", 3000),
        ("soundcloud-header", "master", "centre band", 2480),
        ("youtube-thumbnail", "master", "pad-blur", 2160),
        ("instagram-reel-cover", "master", "pad-blur", 1080),
        ("instagram-grid-thumbnail", "instagram-reel-cover", "grid crop", 1080),  # its preview, next to it
        ("instagram-carousel-image", "master", "pad-blur", 1080),
    ]
    assert plans[0].out == "song.cover.spotify-cover.jpg" and plans[4].preview and not plans[3].preview


def test_with_a_portrait_the_9_16_covers_are_drawn_from_it():
    plans = matrix.plan_covers(["youtube-short-thumbnail", "instagram-grid-thumbnail", "instagram-reel-cover"],
                               name_for, portrait=True)
    assert [(p.platform.id, p.source, p.method, p.drawn) for p in plans] == [
        ("youtube-short-thumbnail", "portrait", "scale", None),
        ("instagram-grid-thumbnail", "instagram-reel-cover", "grid crop", None),  # asked for: not added twice
        ("instagram-reel-cover", "portrait", "scale", None),
    ]


def test_a_plan_says_what_it_will_make():
    plans = matrix.plan_covers(["spotify-cover", "youtube-thumbnail", "soundcloud-header", "instagram-reel-cover"],
                               name_for, portrait=True)
    assert [p.describe() for p in plans] == [
        "song.cover.spotify-cover.jpg: 3000x3000, the master, scaled",
        "song.cover.youtube-thumbnail.jpg: 3840x2160, the master centred over a blurred copy of itself",
        "song.cover.soundcloud-header.jpg: 2480x520, the centre band of the master",
        "song.cover.instagram-reel-cover.jpg: 1080x1920, the portrait, scaled",
        "song.cover.instagram-grid-thumbnail.jpg: 1080x1440, what the profile grid shows of the instagram-reel-cover",
    ]


# --------------------------------------------------------------------------
# before anything is made: never enlarged
# --------------------------------------------------------------------------
def test_a_master_as_large_as_the_largest_cover_is_enough(tmp_path):
    master = save(blank(3000, 3000), tmp_path / "m.png")
    plans = matrix.plan_covers(["spotify-cover", "youtube-thumbnail", "soundcloud-header"], name_for, portrait=False)
    assert matrix.check_sources(plans, master, None) == []


def test_a_master_smaller_than_a_cover_drawn_from_it_is_refused_and_says_which(tmp_path):
    master = save(blank(2400, 2400), tmp_path / "m.png")
    plans = matrix.plan_covers(["spotify-cover", "soundcloud-header", "soundcloud-artwork"], name_for, portrait=False)
    (problem,) = matrix.check_sources(plans, master, None)
    assert problem == (
        "covers.master is 2400x2400; soundcloud-header, spotify-cover draw it at 3000x3000 or less, and a cover is "
        "never enlarged (Spotify: no upscaling) -- export the master at 3000 px or more, or leave them out"
    )
    one = matrix.plan_covers(["distributor-cover"], name_for, portrait=False)
    assert "distributor-cover draws it at 3000x3000 or less" in matrix.check_sources(one, master, None)[0]
    assert "leave it out" in matrix.check_sources(one, master, None)[0]


def test_a_master_that_isnt_square_is_refused(tmp_path):
    master = save(blank(3000, 2990), tmp_path / "m.png")
    plans = matrix.plan_covers(["soundcloud-artwork"], name_for, portrait=False)
    assert matrix.check_sources(plans, master, None) == ["covers.master is 3000x2990: it has to be square"]


def test_a_portrait_has_to_be_9_16_and_as_large_as_its_largest_cover(tmp_path):
    master = save(blank(3000, 3000), tmp_path / "m.png")
    plans = matrix.plan_covers(["instagram-reel-cover", "youtube-short-thumbnail"], name_for, portrait=True)
    small = save(blank(1080, 1920), tmp_path / "small.png")
    (problem,) = matrix.check_sources(plans, master, small)
    assert problem.startswith("covers.portrait is 1080x1920; youtube-short-thumbnail is 2160x3840, and a cover is never")
    assert "leave `portrait` out" in problem
    wide = save(blank(1080, 1080), tmp_path / "wide.png")
    assert matrix.check_sources(plans, master, wide) == ["covers.portrait is 1080x1080: it has to be 9:16"]
    big = save(blank(2160, 3840), tmp_path / "big.png")
    assert matrix.check_sources(plans, master, big) == []


def test_an_images_size_is_as_it_is_seen(tmp_path):
    """EXIF orientation 6 is a 90 degree turn: a 1920x1080 file is seen 1080x1920."""
    exif = Image.Exif()
    exif[0x0112] = 6
    turned = save(picture(1920, 1080), tmp_path / "t.jpg", exif=exif)
    assert matrix.image_size(turned) == (1080, 1920)
    assert matrix.image_size(save(picture(64, 32), tmp_path / "p.png")) == (64, 32)


def test_a_file_that_isnt_an_image_is_said_so(tmp_path):
    bogus = tmp_path / "cover.png"
    bogus.write_bytes(b"not a picture")
    with pytest.raises(ValueError, match="is not an image Pillow can read"):
        matrix.image_size(str(bogus))
    with pytest.raises(ValueError, match="is not an image Pillow can read"):
        matrix.load_image(str(bogus))


def huge_png(path, width: int, height: int) -> str:
    """A PNG whose header says `width`x`height` -- 1x1 underneath, drawn in code: what Pillow
    sees of a decompression bomb before it decodes a byte of it."""
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, "PNG")
    data = bytearray(buffer.getvalue())
    data[16:24] = width.to_bytes(4, "big") + height.to_bytes(4, "big")  # IHDR
    data[29:33] = zlib.crc32(bytes(data[12:29])).to_bytes(4, "big")
    path.write_bytes(bytes(data))
    return str(path)


def test_an_image_too_large_to_open_is_refused_in_a_line_not_a_traceback(tmp_path):
    """Pillow raises DecompressionBombError, not an OSError, over 178,956,970 pixels."""
    bomb = huge_png(tmp_path / "bomb.png", 20000, 20000)
    says = r"bomb\.png has more than 178,956,970 pixels, more than Pillow will open .* 3000x3000 is enough"
    with pytest.raises(ValueError, match=says):
        matrix.image_size(bomb)
    with pytest.raises(ValueError, match=says):
        matrix.load_image(bomb)
    plans = matrix.plan_covers(["spotify-cover"], name_for, portrait=False)
    with pytest.raises(ValueError, match=says):
        matrix.check_sources(plans, bomb, None)


# --------------------------------------------------------------------------
# loading: upright, sRGB, 8-bit RGB, nothing embedded
# --------------------------------------------------------------------------
def test_a_plain_rgb_master_loads_as_it_is(tmp_path):
    img, notes = matrix.load_image(save(picture(40, 40), tmp_path / "m.png"))
    assert img.mode == "RGB" and img.info == {} and notes == []


def test_real_transparency_is_flattened_onto_white_or_the_background_given(tmp_path):
    rgba = picture(40, 40, mode="RGBA")
    alpha = Image.new("L", (40, 40), 255)
    alpha.paste(0, (0, 0, 20, 40))  # the left half transparent
    alpha.paste(128, (20, 0, 40, 10))  # a band half transparent
    rgba.putalpha(alpha)
    path = save(rgba, tmp_path / "m.png")
    img, notes = matrix.load_image(path)
    assert img.getpixel((5, 5)) == (255, 255, 255) and notes == ["its transparency flattened onto white"]
    assert img.getpixel((30, 30)) == picture(40, 40).getpixel((30, 30))  # opaque: as it was
    half = picture(40, 40).getpixel((30, 5))
    assert all(abs(v - (c * 128 + 255 * 127) / 255) <= 1 for v, c in zip(img.getpixel((30, 5)), half))
    img, notes = matrix.load_image(path, "#102030")
    assert img.getpixel((5, 5)) == (16, 32, 48) and notes == ["its transparency flattened onto #102030"]
    assert matrix.load_image(path, "#000000")[1] == ["its transparency flattened onto black"]
    palette = picture(40, 40).convert("P")
    used = palette.getpixel((0, 0))
    assert matrix.load_image(save(palette, tmp_path / "p.png", transparency=used))[1] == [
        "its transparency flattened onto white"
    ]


def test_an_alpha_channel_that_is_opaque_everywhere_is_dropped_without_a_word(tmp_path):
    """Every canvas piece's cover is RGBA and opaque: nothing in it is transparent, so nothing
    is flattened, and the report doesn't say it was."""
    rgba = picture(40, 40, mode="RGBA")
    img, notes = matrix.load_image(save(rgba, tmp_path / "m.png"))
    assert img.mode == "RGB" and notes == [] and img.tobytes() == picture(40, 40).tobytes()
    grey = picture(40, 40, mode="LA")
    assert matrix.load_image(save(grey, tmp_path / "la.png"))[1] == []
    palette = picture(40, 40).convert("P")
    unused = palette.histogram().index(0)  # an index no pixel uses
    img, notes = matrix.load_image(save(palette, tmp_path / "p.png", transparency=unused))
    assert notes == [] and img.mode == "RGB"


@pytest.mark.parametrize("mode", ["L", "1", "P"])
def test_greyscale_and_palette_masters_become_rgb(tmp_path, mode):
    img, notes = matrix.load_image(save(picture(40, 40, mode=mode), tmp_path / "m.png"))
    assert img.mode == "RGB" and notes == []


def test_cmyk_without_a_profile_is_converted_and_flagged(tmp_path):
    img, notes = matrix.load_image(save(picture(40, 40, mode="CMYK"), tmp_path / "m.jpg"))
    assert img.mode == "RGB" and notes == ["CMYK with no colour profile, converted without one: check its colours"]


def test_an_embedded_profile_is_applied_and_removed(tmp_path):
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    path = save(picture(40, 40), tmp_path / "m.png", icc_profile=srgb)
    img, notes = matrix.load_image(path)
    assert img.mode == "RGB" and "icc_profile" not in img.info
    assert len(notes) == 1 and notes[0].startswith("converted from its embedded profile (") and "to sRGB" in notes[0]
    out = io.BytesIO()
    img.save(out, "JPEG")
    assert "icc_profile" not in Image.open(io.BytesIO(out.getvalue())).info


def test_a_profile_that_cant_be_applied_is_refused(tmp_path):
    path = save(picture(40, 40), tmp_path / "m.png", icc_profile=b"definitely not an icc profile")
    with pytest.raises(ValueError, match=r"its colour profile can't be applied .* export it as sRGB"):
        matrix.load_image(path)


def test_a_pillow_without_littlecms_says_so(tmp_path, monkeypatch):
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    path = save(picture(40, 40), tmp_path / "m.png", icc_profile=srgb)
    # `from PIL import ImageCms` now fails, as on a Pillow built without littlecms.
    monkeypatch.delattr(PIL, "ImageCms")
    monkeypatch.setitem(sys.modules, "PIL.ImageCms", None)
    with pytest.raises(ValueError, match="this Pillow can't convert one"):
        matrix.load_image(path)


def test_the_exif_orientation_is_applied_to_the_pixels(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6
    img, notes = matrix.load_image(save(picture(60, 30), tmp_path / "t.jpg", exif=exif))
    assert img.size == (30, 60) and notes == ["its EXIF orientation applied to the pixels"]
    assert not img.getexif()


def test_a_mode_covers_arent_drawn_from_is_refused(tmp_path):
    deep = Image.fromarray(np.full((8, 8), 40000, dtype=np.uint16))
    with pytest.raises(ValueError, match=r"is an? I(;16)? image"):
        matrix.load_image(save(deep, tmp_path / "deep.png"))


# --------------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------------
def test_pad_blur_centres_the_picture_whole_over_a_blurred_copy():
    square = picture(300, 300)
    out = matrix.pad_blur(square, (640, 360))
    assert out.size == (640, 360)
    centre = out.crop((140, 0, 500, 360))
    assert centre.tobytes() == square.resize((360, 360), Image.Resampling.LANCZOS).tobytes()
    sides = np.asarray(out.crop((0, 0, 140, 360)), dtype=float)
    assert sides.std(axis=1).mean() < 25  # blurred: little left of the disc's edge


def stripes(size: int, period: int) -> Image.Image:
    """Black and white vertical stripes -- detail as fine as a title's letters."""
    x = np.arange(size)
    row = np.where((x // (period // 2)) % 2 == 0, 255, 0).astype(np.uint8)
    return Image.fromarray(np.tile(row, (size, 1)), "L").convert("RGB")


def test_pad_blur_leaves_nothing_readable_at_4k():
    """The copy behind a square in a 3840x2160 thumbnail is the picture enlarged 1.78x: stripes
    80 px a pair in the square are 142 px a pair there. Blurred by 6 % of the width (230 px)
    they are gone -- what is left varies by a level or so across a pair (21 levels with the
    fixed 48 px it was) -- and only the light of the picture's edge remains."""
    square = stripes(2160, 80)
    sides = np.asarray(matrix.pad_blur(square, (3840, 2160)).crop((0, 400, 800, 1760)).convert("L"), dtype=float)
    row = sides.mean(axis=0)  # vertical stripes: every row alike
    pair = round(80 * 3840 / 2160)
    trend = np.convolve(row, np.ones(pair) / pair, mode="valid")  # the light, the stripes averaged out
    assert np.abs(row[pair // 2 : pair // 2 + len(trend)] - trend).max() < 3
    assert row.max() < 160  # and darkened: white and black stripes average 127, less 36


def test_pad_blurs_copy_is_darkened_and_desaturated():
    """ffmpeg's eq=brightness=-0.12:saturation=0.5, in Pillow: half the colour kept, and the
    31 levels eq takes off a video's 219-level luma are 36 of a picture's 255."""
    red = Image.new("RGB", (300, 300), (200, 60, 60))
    out = matrix.pad_blur(red, (640, 360))
    grey = (200 * 299 + 60 * 587 + 60 * 114) / 1000  # the colour's own grey (ITU-R 601 luma)
    expected = [(c + grey) / 2 - 36 for c in (200, 60, 60)]
    assert all(abs(v - e) <= 2 for v, e in zip(out.getpixel((40, 180)), expected))
    assert out.getpixel((320, 180)) == (200, 60, 60)  # the picture itself untouched
    assert matrix.dim(Image.new("RGB", (2, 2), (10, 10, 10))).getpixel((0, 0)) == (0, 0, 0)  # floored at black


def test_the_grid_shows_the_centre_of_a_reel_cover():
    reel = picture(1080, 1920)
    grid = matrix.grid_crop(reel, (1080, 1440))
    assert grid.tobytes() == reel.crop((0, 240, 1080, 1680)).tobytes()
    small = matrix.grid_crop(picture(540, 960), (1080, 1440))
    assert small.size == (1080, 1440)


def test_each_method_draws_at_the_platforms_size():
    master, portrait = picture(3000, 3000), picture(1080, 1920)
    plans = {p.platform.id: p for p in matrix.plan_covers(
        ["soundcloud-artwork", "soundcloud-header", "instagram-reel-cover"], name_for, portrait=True)}
    made: dict = {}
    artwork = matrix.render(plans["soundcloud-artwork"], master, None, made)
    assert artwork.size == (800, 800)
    band = matrix.render(plans["soundcloud-header"], master, None, made)
    assert band.size == (2480, 520)
    assert band.tobytes() == master.resize((2480, 2480), Image.Resampling.LANCZOS).crop((0, 980, 2480, 1500)).tobytes()
    reel = matrix.render(plans["instagram-reel-cover"], master, portrait, made)
    assert reel.tobytes() == portrait.tobytes()  # already 1080x1920
    grid = matrix.render(plans["instagram-grid-thumbnail"], master, portrait, {"instagram-reel-cover": reel})
    assert grid.tobytes() == reel.crop((0, 240, 1080, 1680)).tobytes()
    unmade = matrix.render(plans["instagram-grid-thumbnail"], master, portrait, {})  # the Reel cover made for it
    assert unmade.tobytes() == grid.tobytes()


def test_jpeg_quality_steps_down_until_the_file_is_under_its_limit():
    noisy = picture(400, 400, grain=40)
    data, quality = matrix.encode_jpeg(noisy, 95, None)
    assert quality == 95 and data[:2] == b"\xff\xd8"
    full = len(data)
    data, quality = matrix.encode_jpeg(noisy, 95, int(full * 0.6))
    assert quality < 95 and len(data) <= full * 0.6 and (95 - quality) % matrix.QUALITY_STEP == 0
    data, quality = matrix.encode_jpeg(noisy, 95, 10)
    assert quality == matrix.MIN_QUALITY and len(data) > 10  # as low as it goes, still over: the caller says so
    loaded = Image.open(io.BytesIO(data))
    assert loaded.mode == "RGB" and "icc_profile" not in loaded.info and not loaded.getexif()


def test_a_cover_jpeg_says_300_dpi_and_nothing_else():
    noisy = picture(400, 400, grain=40)
    data, _ = matrix.encode_jpeg(noisy, 100, None)  # grain at quality 100: the most bytes a cover takes
    plain = io.BytesIO()
    noisy.save(plain, "JPEG", quality=100, subsampling=0)
    loaded = Image.open(io.BytesIO(data))
    assert loaded.tobytes() == Image.open(plain).tobytes()  # the header changes no pixel
    assert loaded.info["dpi"] == (300, 300) and "icc_profile" not in loaded.info and not loaded.getexif()


# --------------------------------------------------------------------------
# making them
# --------------------------------------------------------------------------
def test_every_cover_is_written_at_its_size_in_srgb_with_nothing_embedded(tmp_path):
    master = save(picture(3000, 3000, grain=6), tmp_path / "master.png")
    plans = matrix.plan_covers(
        ["soundcloud-artwork", "soundcloud-header", "instagram-reel-cover", "youtube-thumbnail"], name_for, portrait=False
    )
    logged: list[str] = []
    covers = matrix.make_covers(plans, master, None, lambda name: str(tmp_path / "out" / name), logged.append)
    assert [(c.platform, c.width, c.height) for c in covers] == [
        ("soundcloud-artwork", 800, 800), ("soundcloud-header", 2480, 520), ("instagram-reel-cover", 1080, 1920),
        ("instagram-grid-thumbnail", 1080, 1440), ("youtube-thumbnail", 3840, 2160),
    ]
    for cover in covers:
        written = Image.open(cover.out)
        assert written.size == (cover.width, cover.height) and written.format == "JPEG" and written.mode == "RGB"
        assert "icc_profile" not in written.info and not written.getexif()
        assert cover.size_bytes == (tmp_path / "out" / f"song.cover.{cover.platform}.jpg").stat().st_size
    assert logged == []  # nothing to say about a plain sRGB master
    header, grid = covers[1], covers[3]
    assert [(f.level, f.rule) for f in header.findings] == [("warn", "crop")]
    assert "the centre band of the square cover, 2480x520 of 2480x2480: check the crop" in header.findings[0].message
    assert grid.preview and [(f.level, f.rule) for f in grid.findings] == [("info", "crop")]
    assert "what the profile grid shows of song.cover.instagram-reel-cover.jpg: its centre 1080x1440, 240 px off" \
        in grid.findings[0].message
    assert covers[0].describe().endswith("song.cover.soundcloud-artwork.jpg (800x800, %.2f MB, JPEG quality 95; "
                                         "soundcloud-artwork)" % covers[0].file_mb)
    assert grid.describe().endswith("; a preview, not an upload)")


def test_a_cover_stepped_down_says_so_and_one_still_over_is_refused(tmp_path):
    master = save(picture(1000, 1000, grain=40), tmp_path / "master.png")
    tight = dataclasses.replace(pf.get("soundcloud-artwork"), max_file_mb=0.3)
    impossible = dataclasses.replace(pf.get("soundcloud-profile-image"), max_file_mb=0.001)
    plans = [matrix.CoverPlan(tight, "a.jpg", "master", "scale", 800),
             matrix.CoverPlan(impossible, "b.jpg", "master", "scale", 800)]
    stepped, over = matrix.make_covers(plans, master, None, lambda name: str(tmp_path / name))
    assert matrix.MIN_QUALITY < stepped.quality < 95 and stepped.file_mb <= 0.3
    assert [(f.level, f.rule) for f in stepped.findings] == [("info", "file size")]
    assert stepped.findings[0].message == f"JPEG quality {stepped.quality} (from 95) to stay under its 0.3 MB"
    assert over.quality == matrix.MIN_QUALITY
    assert [(f.level, f.rule) for f in over.findings] == [("refuse", "file size"), ("info", "file size")]
    assert "the lowest it goes, and still over 0.001 MB" in over.findings[1].message


def test_what_was_done_to_the_master_and_the_portrait_is_logged(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6
    rgba = picture(1200, 1200, mode="RGBA")
    rgba.putpixel((0, 0), (0, 0, 0, 0))  # one transparent pixel is transparency
    master = save(rgba, tmp_path / "master.png")
    portrait = save(picture(1920, 1080), tmp_path / "portrait.jpg", exif=exif)  # seen 1080x1920
    plans = matrix.plan_covers(["instagram-reel-cover", "soundcloud-artwork"], name_for, portrait=True)
    assert matrix.check_sources(plans, master, portrait) == []
    logged: list[str] = []
    covers = matrix.make_covers(plans, master, portrait, lambda name: str(tmp_path / name), logged.append)
    assert logged == [
        "covers.master: its transparency flattened onto white",
        "covers.portrait: its EXIF orientation applied to the pixels",
    ]
    assert covers[0].source == "portrait" and (covers[0].width, covers[0].height) == (1080, 1920)


def test_a_portrait_nothing_is_drawn_from_isnt_opened(tmp_path):
    master = save(picture(900, 900), tmp_path / "master.png")
    plans = matrix.plan_covers(["soundcloud-artwork"], name_for, portrait=False)
    (cover,) = matrix.make_covers(plans, master, str(tmp_path / "missing.png"), lambda name: str(tmp_path / name))
    assert cover.width == 800
