"""
The covers matrix (#27): one square master -- and, if there is one, a 9:16
still -- to every cover a platform asks for, each at its size, with Pillow.

    covers:                            # in a delivery sheet (docs/CONFIG-SCHEMA.md)
      master: _work/cover_3000.png     # square, as large as the largest cover drawn from it
      portrait: _work/cover_9x16.png   # optional: the 9:16 covers
      platforms: [spotify-cover, soundcloud-artwork, youtube-thumbnail, instagram-reel-cover]

Each cover is:

- drawn from the master at its own size with Lanczos, and never enlarged:
  Spotify asks for no upscaling, so a master smaller than the largest size
  it is drawn at is refused before anything is written;
- square for a square platform. Another shape is the master centred over a
  scaled copy of itself, blurred, darkened and desaturated (pad-blur, as
  `deliver` fits a video: render/platforms.py) -- a 16:9 YouTube thumbnail
  of a square cover -- except the 9:16 covers when there is a portrait
  (scaled), and a banner (SoundCloud's 2480x520 header), which is the
  centre band of the master scaled to its width: SoundCloud crops it
  further on smaller screens, so it comes with a warning to check it;
- sRGB, 8 bits a channel, with no embedded profile and no EXIF: Spotify's
  rule ("the colour profile applied", no orientation metadata), and harmless
  everywhere else. A master with a profile is converted to sRGB; its EXIF
  orientation is applied to the pixels first; real transparency is
  flattened onto white (or `covers.background`), and an alpha channel that
  is opaque everywhere is dropped without a word;
- a JPEG (4:4:4) at the platform's quality -- 95, or 100 where it asks for
  lossless or 100 % -- stepped down by 5 until it is under the platform's
  file limit (SoundCloud's 2 MB), and refused, though written, if quality 50
  isn't.

An Instagram Reel cover also gets a preview of what the profile grid shows
of it, the centre 3:4 (`instagram-grid-thumbnail`): a display crop, not an
upload.
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from PIL import Image, ImageColor, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

from kaleidophone.render import platforms as pf

QUALITY_STEP = 5
MIN_QUALITY = 50
REEL_COVER = "instagram-reel-cover"
GRID_PREVIEW = "instagram-grid-thumbnail"
PORTRAIT_SHAPE = (9, 16)
BANNER = 3  # a frame at least this many times as wide as tall is a banner: its centre band
_ORIENTATION = 0x0112  # EXIF
WHITE = "#ffffff"  # what real transparency is flattened onto, unless the sheet says (covers.background)
_COLOUR_NAMES = {"#ffffff": "white", "#000000": "black"}
_MODES = ("1", "L", "LA", "P", "PA", "RGB", "RGBA", "RGBX", "CMYK", "YCbCr")
_LANCZOS = Image.Resampling.LANCZOS


@dataclass(frozen=True)
class CoverPlan:
    """One cover, before it is made: where it comes from and how."""

    platform: pf.Platform
    out: str  # the file, relative to the output directory
    source: str  # "master", "portrait", or the cover it is a preview of
    method: str  # "scale", "pad-blur", "centre band" or "grid crop"
    drawn: int | None  # the side the square master is drawn at; None when it isn't drawn from it

    @property
    def preview(self) -> bool:
        """A display crop, not an upload."""
        return self.platform.id == GRID_PREVIEW

    def describe(self) -> str:
        p = self.platform
        how = {
            "scale": f"the {self.source}, scaled",
            "pad-blur": "the master centred over a blurred copy of itself",
            "centre band": "the centre band of the master",
            "grid crop": f"what the profile grid shows of the {self.source}",
        }[self.method]
        return f"{self.out}: {p.width}x{p.height}, {how}"


def plan_covers(platforms: list[str], name: Callable[[str], str], portrait: bool) -> list[CoverPlan]:
    """Every cover the sheet asks for, in its order -- a Reel cover followed
    by its grid preview -- each named `name(platform id)`."""
    ids = list(platforms)
    if REEL_COVER in ids and GRID_PREVIEW not in ids:
        ids.insert(ids.index(REEL_COVER) + 1, GRID_PREVIEW)
    return [_plan(pf.get(pid), name(pid), portrait) for pid in ids]


def _plan(p: pf.Platform, out: str, portrait: bool) -> CoverPlan:
    w, h = p.size
    if p.id == GRID_PREVIEW:
        return CoverPlan(p, out, REEL_COVER, "grid crop", _plan(pf.get(REEL_COVER), out, portrait).drawn)
    if w == h:
        return CoverPlan(p, out, "master", "scale", w)
    if portrait and pf.same_aspect((w, h), PORTRAIT_SHAPE):
        return CoverPlan(p, out, "portrait", "scale", None)
    if w >= BANNER * h:
        return CoverPlan(p, out, "master", "centre band", w)
    return CoverPlan(p, out, "master", "pad-blur", min(w, h))


# --------------------------------------------------------------------------
# before anything is made
# --------------------------------------------------------------------------
def _open(path: str) -> Image.Image:
    """`path`, opened -- Pillow reads the header; the pixels wait for
    load() -- or a ValueError that says why it can't be."""
    try:
        return Image.open(path)
    except UnidentifiedImageError:
        raise ValueError(f"{path} is not an image Pillow can read") from None
    except Image.DecompressionBombError:
        # Raised over twice Image.MAX_IMAGE_PIXELS, so that is never None here.
        raise ValueError(
            f"{path} has more than {2 * (Image.MAX_IMAGE_PIXELS or 0):,} pixels, more than Pillow will open "
            f"(an image that large could be a decompression bomb) -- export it smaller: 3000x3000 is enough "
            f"for every cover"
        ) from None


def image_size(path: str) -> tuple[int, int]:
    """An image's size as it is seen: its EXIF orientation applied. Reads
    the header, not the pixels."""
    with _open(path) as img:
        width, height = img.size
        turned = img.getexif().get(_ORIENTATION, 1) in (5, 6, 7, 8)
    return (height, width) if turned else (width, height)


def check_sources(plans: list[CoverPlan], master: str, portrait: str | None) -> list[str]:
    """What stops the covers being made, one line each: a master that isn't
    square or is smaller than a cover drawn from it, a portrait that isn't
    9:16 or is smaller than a 9:16 cover. Nothing is enlarged."""
    problems = []
    mw, mh = image_size(master)
    if mw != mh:
        problems.append(f"covers.master is {mw}x{mh}: it has to be square")
    need = max((plan.drawn for plan in plans if plan.drawn is not None), default=0)
    if need > min(mw, mh):
        short = sorted({plan.platform.id for plan in plans if plan.drawn is not None and plan.drawn > min(mw, mh)})
        problems.append(
            f"covers.master is {mw}x{mh}; {', '.join(short)} {'draws' if len(short) == 1 else 'draw'} it at "
            f"{need}x{need} or less, and a cover is never enlarged (Spotify: no upscaling) -- export the master "
            f"at {need} px or more, or leave {'it' if len(short) == 1 else 'them'} out"
        )
    tall = [plan for plan in plans if plan.source == "portrait"]
    if tall and portrait is not None:
        pw, ph = image_size(portrait)
        widest = max(tall, key=lambda plan: plan.platform.width).platform
        if not pf.same_aspect((pw, ph), PORTRAIT_SHAPE):
            problems.append(f"covers.portrait is {pw}x{ph}: it has to be 9:16")
        elif pw < widest.width:
            problems.append(
                f"covers.portrait is {pw}x{ph}; {widest.id} is {widest.width}x{widest.height}, and a cover is "
                f"never enlarged -- export the portrait at {widest.width}x{widest.height}, or leave `portrait` "
                f"out and the 9:16 covers are the master centred over a blurred copy of itself"
            )
    return problems


# --------------------------------------------------------------------------
# making them
# --------------------------------------------------------------------------
def load_image(path: str, background: str = WHITE) -> tuple[Image.Image, list[str]]:
    """An image as covers are drawn from it -- upright, sRGB, 8-bit RGB,
    nothing embedded -- and what had to be done to it, one line each. An
    alpha channel that is opaque everywhere (a canvas piece's cover is RGBA
    and has one) is dropped; real transparency is flattened onto
    `background`, '#rrggbb'."""
    notes = []
    with _open(path) as opened:
        opened.load()
        if opened.getexif().get(_ORIENTATION, 1) != 1:
            notes.append("its EXIF orientation applied to the pixels")
        img = ImageOps.exif_transpose(opened)
    if img.mode not in _MODES:
        raise ValueError(f"{path} is a {img.mode} image: covers are drawn from 8-bit RGB, greyscale, palette or CMYK")
    icc = img.info.get("icc_profile")
    if img.mode in ("LA", "PA", "RGBA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema()[0] == 255:  # opaque: nothing to flatten
            img = rgba.convert("RGB")
        else:
            img = Image.new("RGB", rgba.size, ImageColor.getrgb(background))
            img.paste(rgba, mask=alpha)
            notes.append(f"its transparency flattened onto {_COLOUR_NAMES.get(background.lower(), background.lower())}")
    if icc:
        img, note = _to_srgb(img, icc, path)
        notes.append(note)
    elif img.mode == "CMYK":
        notes.append("CMYK with no colour profile, converted without one: check its colours")
    img = img.convert("RGB")
    img.info = {}
    return img, notes


def _to_srgb(img: Image.Image, icc: bytes, path: str) -> tuple[Image.Image, str]:
    """The image converted from its embedded profile to sRGB. Imported here:
    Pillow's wheels ship littlecms, but a build without it should still make
    covers from masters that need no conversion."""
    try:
        from PIL import ImageCms
    except ImportError:
        raise ValueError(
            f"{path} has a colour profile, and this Pillow can't convert one (it has no littlecms) -- "
            f"export it as sRGB"
        ) from None
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        name = ImageCms.getProfileDescription(profile).strip() or "unnamed"
        mode = img.mode if img.mode in ("RGB", "CMYK", "L") else "RGB"
        converted = ImageCms.profileToProfile(
            img.convert(mode), profile, ImageCms.createProfile("sRGB"), outputMode="RGB"
        )
    except (ImageCms.PyCMSError, OSError, ValueError) as exc:
        raise ValueError(f"{path}: its colour profile can't be applied ({exc}) -- export it as sRGB") from None
    return converted, f"converted from its embedded profile ({name}) to sRGB, the profile removed"


def pad_blur(img: Image.Image, frame: tuple[int, int]) -> Image.Image:
    """The picture, whole, centred over a scaled copy of itself that fills
    `frame`, blurred, darkened and desaturated -- platforms.py's pad-blur,
    in Pillow, as `deliver` draws it with ffmpeg."""
    tw, th = frame
    fw, fh = pf.fit_size(img.size, frame)
    bw, bh = pf.blur_frame(frame)
    cw, ch = pf.cover_size(img.size, (bw, bh))
    x, y = (cw - bw) // 2, (ch - bh) // 2
    small = img.resize((cw, ch), _LANCZOS).crop((x, y, x + bw, y + bh))
    blurred = dim(small.filter(ImageFilter.GaussianBlur(pf.blur_sigma(frame))))
    out = blurred.resize((tw, th), Image.Resampling.BICUBIC)
    out.paste(img.resize((fw, fh), _LANCZOS), ((tw - fw) // 2, (th - fh) // 2))
    return out


def dim(img: Image.Image) -> Image.Image:
    """pad-blur's background darkened and desaturated as ffmpeg's eq does
    it to a video: PAD_BLUR_SATURATION of its colour kept (the rest is its
    own grey), then the same level taken off every channel -- off the luma,
    the colour left as it is. eq adds PAD_BLUR_BRIGHTNESS to a video's
    8-bit luma, whose black-to-white is 219 levels (16..235): -0.12 there is
    31 of them, 36 of a picture's 255. Measured on three of the canvas
    template's frames padded to 3840x2160 both ways: the sides' mean colour
    within 6 of 255 levels of the video's, per channel."""
    toned = ImageEnhance.Color(img).enhance(pf.PAD_BLUR_SATURATION)
    drop = round(-pf.PAD_BLUR_BRIGHTNESS * 256 * 255 / 219)
    return toned.point([max(0, v - drop) for v in range(256)] * len(toned.getbands()))


def grid_crop(cover: Image.Image, shape: tuple[int, int]) -> Image.Image:
    """What a grid of `shape` tiles shows of `cover`: its centre, the full
    width (a 9:16 Reel cover in Instagram's 3:4 grid: the middle 1080x1440)."""
    cw, ch = cover.size
    w, h = shape
    gh = min(ch, round(cw * h / w))
    top = (ch - gh) // 2
    crop = cover.crop((0, top, cw, top + gh))
    return crop if crop.size == shape else crop.resize(shape, _LANCZOS)


def render(plan: CoverPlan, master: Image.Image, portrait: Image.Image | None, made: dict[str, Image.Image]) -> Image.Image:
    """One cover's pixels. `made` holds the covers made so far, by platform:
    a grid preview is cut from its Reel cover."""
    w, h = plan.platform.size
    if plan.method == "grid crop":
        reel = made.get(REEL_COVER)
        if reel is None:
            reel = render(_plan(pf.get(REEL_COVER), "", portrait is not None), master, portrait, made)
        return grid_crop(reel, (w, h))
    if plan.method == "scale":
        return (portrait if plan.source == "portrait" else master).resize((w, h), _LANCZOS)
    if plan.method == "centre band":
        top = (w - h) // 2
        return master.resize((w, w), _LANCZOS).crop((0, top, w, top + h))
    return pad_blur(master, (w, h))


def encode_jpeg(img: Image.Image, quality: int, limit_bytes: int | None) -> tuple[bytes, int]:
    """JPEG bytes at `quality`, stepped down by QUALITY_STEP until they are
    under `limit_bytes` -- or MIN_QUALITY is reached -- and the quality used.
    4:4:4, nothing embedded. The JFIF header says 300 dpi: a number
    distributors ask for (SoundCloud's 3000 px "at 300 dpi"; TuneCore and CD
    Baby "300 dpi is best") that changes no pixel. Not `optimize=True`: Pillow
    then encodes the whole image into one buffer sized from its pixel count,
    and a grainy cover at quality 95 or more can overflow it."""
    while True:
        buffer = io.BytesIO()
        img.save(buffer, "JPEG", quality=quality, subsampling=0, dpi=(300, 300))
        data = buffer.getvalue()
        if limit_bytes is None or len(data) <= limit_bytes or quality - QUALITY_STEP < MIN_QUALITY:
            return data, quality
        quality -= QUALITY_STEP


@dataclass
class Cover:
    """One cover as written, and what it was held to."""

    out: str  # the file, as the caller named it
    platform: str
    source: str
    method: str
    preview: bool
    width: int
    height: int
    size_bytes: int
    quality: int
    findings: list[pf.Finding] = field(default_factory=list)

    @property
    def file_mb(self) -> float:
        return self.size_bytes / pf.MB

    def describe(self) -> str:
        kind = "a preview, not an upload" if self.preview else self.platform
        return f"{self.out} ({self.width}x{self.height}, {self.file_mb:.2f} MB, JPEG quality {self.quality}; {kind})"


def _findings(plan: CoverPlan, cover: Cover, made: dict[str, str]) -> list[pf.Finding]:
    p = plan.platform
    found = pf.check_image(p, cover.width, cover.height, cover.file_mb)
    if cover.quality < p.jpeg_quality:
        fits = cover.file_mb <= p.max_file_mb
        found.append(pf.Finding(
            "info", p.id, "file size",
            f"JPEG quality {cover.quality} (from {p.jpeg_quality}) "
            + (f"to stay under its {p.max_file_mb:g} MB" if fits else
               f"-- the lowest it goes, and still over {p.max_file_mb:g} MB: grain and fine detail cost the most"),
        ))
    if plan.method == "centre band":
        found.append(pf.Finding(
            "warn", p.id, "crop",
            f"the centre band of the square cover, {p.width}x{p.height} of {p.width}x{p.width}: check the crop -- "
            f"{p.brand} crops it further on smaller screens, so keep text out of it",
        ))
    if plan.method == "grid crop":
        reel = pf.get(REEL_COVER)
        lost = reel.height - round(reel.width * p.height / p.width)
        found.append(pf.Finding(
            "info", p.id, "crop",
            f"what the profile grid shows of {os.path.basename(made.get(REEL_COVER, REEL_COVER))}: its centre "
            f"{p.width}x{p.height}, {lost // 2} px off the top and the bottom ('Adjust preview' moves it after "
            f"posting)",
        ))
    return found


def make_covers(
    plans: list[CoverPlan],
    master: str,
    portrait: str | None,
    out: Callable[[str], str],
    log: Callable[[str], None] | None = None,
    background: str = WHITE,
) -> list[Cover]:
    """Make and write every planned cover; `out(name)` is where each file
    goes, `background` what real transparency is flattened onto."""
    say = log or (lambda _msg: None)
    master_img, notes = load_image(master, background)
    for note in notes:
        say(f"covers.master: {note}")
    portrait_img = None
    if portrait is not None and any(plan.source == "portrait" for plan in plans):
        portrait_img, notes = load_image(portrait, background)
        for note in notes:
            say(f"covers.portrait: {note}")
    images: dict[str, Image.Image] = {}
    files: dict[str, str] = {}
    covers = []
    for plan in plans:
        p = plan.platform
        img = render(plan, master_img, portrait_img, images)
        images[p.id] = img
        limit = None if p.max_file_mb is None else int(p.max_file_mb * pf.MB)
        data, quality = encode_jpeg(img, p.jpeg_quality, limit)
        path = out(plan.out)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        files[p.id] = path
        cover = Cover(path, p.id, plan.source, plan.method, plan.preview, img.width, img.height, len(data), quality)
        cover.findings = _findings(plan, cover, files)
        covers.append(cover)
    return covers
