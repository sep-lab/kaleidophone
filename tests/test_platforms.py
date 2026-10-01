"""render/platforms.py: what each platform asks for, the checks that hold a
file to it, and `kaleidophone platforms`.

The registry is data from research (sources, confidence, the date it was
checked), so these tests pin its shape and the numbers that were disputed --
where the safe value went, and that the note says why -- not every figure.
docs/PLATFORMS.md is generated from it; a test fails when the two disagree.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from kaleidophone import cli
from kaleidophone.render import platforms as pf

DOC = Path(__file__).resolve().parent.parent / "docs" / "PLATFORMS.md"

IDS = [
    "instagram-reel", "instagram-reel-cover", "instagram-grid-thumbnail", "instagram-story",
    "instagram-carousel-image", "instagram-carousel-video", "tiktok", "youtube-video", "youtube-short",
    "youtube-thumbnail", "youtube-short-thumbnail", "spotify-canvas", "spotify-cover", "distributor-cover",
    "apple-music-cover", "apple-music-motion-square", "apple-music-motion-tall",
    "soundcloud-artwork", "soundcloud-header", "soundcloud-profile-image",
]


def kinds(findings):
    return [(f.level, f.rule) for f in findings]


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------
def test_the_registry_holds_the_20_researched_deliverables_in_order():
    assert list(pf.PLATFORMS) == IDS
    assert [p.id for p in pf.of_kind("video")] == [
        "instagram-reel", "instagram-story", "instagram-carousel-video", "tiktok", "youtube-video",
        "youtube-short", "spotify-canvas", "apple-music-motion-square", "apple-music-motion-tall",
    ]
    assert len(pf.of_kind("image")) == 11



# Each distributor's published bounds for a cover, px a side (None: it publishes none), from the
# pages in distributor-cover's sources, checked 2026-10-01.
DISTRIBUTORS = {
    "distrokid": (1000, None),
    "tunecore": (1600, 3000),
    "cd-baby": (1400, 3000),
    "amuse": (1400, 6000),
    "landr": (1500, 6000),
    "unitedmasters": (3000, 6000),
    "soundcloud-distribution": (3000, None),
}


def test_one_distributor_cover_is_the_one_size_every_distributor_takes():
    p = pf.get("distributor-cover")
    assert all(pf.get(name) is p for name in DISTRIBUTORS) and pf.get("distributor") is p
    smallest = max(least for least, _ in DISTRIBUTORS.values())
    largest = min(most for _, most in DISTRIBUTORS.values() if most is not None)
    assert smallest == largest == p.width == p.height == p.min_width == p.max_width == 3000
    assert len(p.sources) == len(DISTRIBUTORS) and p.formats == ("jpg",) and p.max_file_mb == 10  # DistroKid, TuneCore
    assert kinds(pf.check_image(p, 3000, 3000, 9.9)) == []
    assert kinds(pf.check_image(p, 2400, 2400, 1.0)) == [("refuse", "size"), ("refuse", "size")]

@pytest.mark.parametrize("pid", IDS)
def test_every_entry_says_what_it_rests_on(pid):
    p = pf.get(pid)
    assert p.sources and all(url.startswith("https://") for url in p.sources)
    assert p.confidence in ("official", "third-party")
    assert date(2026, 9, 30) <= date.fromisoformat(p.checked) <= date(2026, 10, 1)
    assert p.notes and p.codec_notes and p.name and p.brand
    assert p.width > 0 and p.height > 0 and p.width % 2 == 0 and p.height % 2 == 0
    assert p.audio == "none" or p.kind == "video"
    assert pf.same_aspect(p.size, p.size)
    if p.recommended_max_seconds is not None:
        assert p.recommended_why and (p.max_seconds is None or p.recommended_max_seconds < p.max_seconds)
    if p.recommended_max_file_mb is not None:
        assert p.recommended_file_why
    if p.loudness_lufs is not None:
        assert p.loudness_source
    if p.audio == "none":  # a picture with no audio plays at no level of its own
        assert (p.loudness_lufs, p.true_peak_dbtp, p.loudness_source, p.loudness_down_only) == (None, None, None, False)


@pytest.mark.parametrize(
    ("pid", "level", "cited"),
    [
        ("spotify-canvas", "-14 LUFS by default (Loud -11, Quiet -19), from a master at or below -1 dBTP",
         "loudness-normalization"),
        ("spotify-cover", "Spotify normalises to -14 LUFS by default (Loud -11, Quiet -19", "loudness-normalization"),
        ("apple-music-cover", "The track plays with Sound Check, at ~-16 LUFS as third parties measure it",
         "apple-switch-to-lufs"),
        ("apple-music-motion-square", "Silent: the track plays with Sound Check, at ~-16 LUFS", "apple-switch-to-lufs"),
        ("apple-music-motion-tall", "Silent: the track plays with Sound Check, at ~-16 LUFS", "apple-switch-to-lufs"),
        ("soundcloud-artwork", "It recommends masters at -14 LUFS integrated and at or below -1 dBTP",
         "play-my-track-at-the-level"),
    ],
)
def test_the_level_a_silent_entrys_track_plays_at_is_in_its_notes(pid, level, cited):
    """Not in the loudness fields: a Canvas, motion art and a cover have no audio to be at a level."""
    p = pf.get(pid)
    assert level in p.notes and p.loudness_lufs is None
    assert any(cited in url for url in p.sources)


def test_a_disputed_number_keeps_the_safe_value_and_the_note_says_why():
    reel = pf.get("instagram-reel")
    assert (reel.max_seconds, reel.recommended_max_seconds) == (900, 180)  # 15 min allowed, 3 min for reach
    assert "20 min" in reel.notes and "20 min" in reel.recommended_why and reel.max_file_mb == 300
    tiktok = pf.get("tiktok")
    assert (tiktok.max_seconds, tiktok.recommended_max_seconds) == (600, 180)
    assert (tiktok.max_file_mb, tiktok.recommended_max_file_mb) == (4096, 72)
    short = pf.get("youtube-short")
    assert (short.max_seconds, short.recommended_max_seconds) == (180, 60)
    assert "Content ID" in short.recommended_why and "8 Dec 2025" in short.notes
    thumbnail = pf.get("youtube-thumbnail")
    assert thumbnail.size == (3840, 2160) and (thumbnail.max_file_mb, thumbnail.recommended_max_file_mb) == (50, 2)
    assert pf.get("instagram-grid-thumbnail").size == (1080, 1440)
    artwork = pf.get("soundcloud-artwork")
    assert (artwork.min_width, artwork.max_file_mb) == (800, 2)
    canvas = pf.get("spotify-canvas")
    assert canvas.audio == "none" and (canvas.min_seconds, canvas.max_seconds) == (3, 8)
    assert "short edge" in canvas.notes and (canvas.min_width, canvas.max_width) == (720, 1080)
    assert pf.get("youtube-video").loudness_down_only and "third parties" in pf.get("youtube-video").loudness_source


def test_ids_and_aliases_are_unique_lowercase_and_never_shadow_each_other():
    assert len(pf.ALIASES) == sum(len(p.aliases) for p in pf.PLATFORMS.values())
    assert not set(pf.ALIASES) & set(pf.PLATFORMS)
    for name in [*pf.PLATFORMS, *pf.ALIASES]:
        assert name == name.lower() and name.strip() == name


def test_a_platform_is_found_by_its_id_or_an_alias_in_any_case():
    assert pf.get("ig-reel") is pf.get("instagram-reel") is pf.get(" Instagram-Reel ")
    assert pf.get("tt").id == "tiktok" and pf.get("canvas").id == "spotify-canvas"
    assert pf.get("youtube") is pf.get("yt") is pf.get("youtube-video")


def test_an_unknown_platform_says_what_it_might_have_meant():
    with pytest.raises(pf.UnknownPlatform, match=r"unknown platform 'ig-reels' -- did you mean ig-reel or ig-reel-cover\?"):
        pf.get("ig-reels")
    with pytest.raises(ValueError, match=r"^unknown platform 'zzz' \(`kaleidophone platforms` lists them\)$"):
        pf.get("zzz")


def test_an_entry_as_data_is_json_ready():
    data = pf.get("youtube-video").to_dict()
    assert data["sizes"] == [[2560, 1440], [1920, 1080], [1280, 720]] and data["fps_common"] == [24, 25, 30, 48, 50, 60]
    assert pf.get("instagram-reel").to_dict()["safe_area"] == {"top": 269, "bottom": 672, "left": 65, "right": 65}
    assert json.loads(json.dumps(data))["id"] == "youtube-video"
    assert set(data) == {f.name for f in dataclasses.fields(pf.Platform)}


# --------------------------------------------------------------------------
# frames
# --------------------------------------------------------------------------
def test_two_frames_have_one_shape_to_one_percent():
    assert pf.same_aspect((608, 1080), (1080, 1920))  # 0.09 % off 9:16
    assert pf.same_aspect((2160, 3840), (1080, 1920))
    assert not pf.same_aspect((1080, 1080), (1080, 1920))
    assert not pf.same_aspect((1080, 1350), (1080, 1440))  # 4:5 isn't 3:4


@pytest.mark.parametrize(
    ("source", "frame", "fit", "cover"),
    [
        ((1080, 1920), (3840, 2160), (1216, 2160), (3840, 6828)),
        ((3000, 3000), (3840, 2160), (2160, 2160), (3840, 3840)),
        ((3000, 3000), (1080, 1920), (1080, 1080), (1920, 1920)),
        ((1920, 1080), (1080, 1920), (1080, 608), (3414, 1920)),
        ((1080, 1920), (1080, 1920), (1080, 1920), (1080, 1920)),
    ],
)
def test_a_picture_fits_inside_or_covers_a_frame_in_even_pixels(source, frame, fit, cover):
    assert pf.fit_size(source, frame) == fit
    assert pf.cover_size(source, frame) == cover
    assert fit[0] <= frame[0] and fit[1] <= frame[1] and cover[0] >= frame[0] and cover[1] >= frame[1]


def test_pad_blur_blurs_in_a_frame_eight_times_smaller():
    assert pf.blur_frame((3840, 2160)) == (480, 270)
    assert pf.blur_frame((1080, 1920)) == (134, 240)
    assert pf.blur_frame((10, 10)) == (2, 2)


@pytest.mark.parametrize(
    ("frame", "sigma"), [((3840, 2160), 28.8), ((1920, 1080), 14.4), ((1080, 1920), 14.4), ((2048, 2732), 20.5)]
)
def test_pad_blurs_sigma_is_six_percent_of_the_frame_not_a_number_of_pixels(frame, sigma):
    """At full size, 6 % of the longer side -- of a 16:9 frame's width. The fixed 6 px it was
    (48 px at full size) was 1.25 % of a 4K frame's width: a title on the cover stayed readable
    in a YouTube thumbnail's sides."""
    assert pf.blur_sigma(frame) == sigma
    assert pf.blur_sigma(frame) * pf.PAD_BLUR_SHRINK >= 0.06 * max(frame) - 0.5
    assert (pf.PAD_BLUR_BRIGHTNESS, pf.PAD_BLUR_SATURATION) == (-0.12, 0.5)  # darkened, half the colour


# --------------------------------------------------------------------------
# check_video / check_image
# --------------------------------------------------------------------------
def test_a_video_at_the_platforms_own_spec_has_nothing_to_say():
    assert pf.check_video("instagram-reel", 1080, 1920, 30, 30.0, True, 40.0) == []
    assert pf.check_video("spotify-canvas", 1080, 1920, 24, 8.0, False, 5.0) == []
    assert pf.check_video("youtube-video", 1920, 1080, 25, 200.0, True, 300.0) == []  # 1080p is a size it lists


def test_nothing_unknown_is_checked():
    assert pf.check_video("spotify-canvas", None, None, None, None, None, None) == []
    assert pf.check_image("soundcloud-artwork", None, 800, None) == []


@pytest.mark.parametrize(
    ("args", "expected", "text"),
    [
        (("spotify-canvas", 1080, 1920, 24, 30.0, False, None), [("refuse", "length")],
         "30.000 s is longer than 8 s: Spotify Canvas takes 3 s to 8 s"),
        (("spotify-canvas", 1080, 1920, 24, 2.0, False, None), [("refuse", "length")],
         "2.000 s is shorter than 3 s"),
        (("instagram-reel", 1080, 1920, 30, 200.0, True, None), [("warn", "length")],
         "200.000 s is over 3 min: Instagram recommends Reels under 3 min"),
        (("instagram-reel", 1080, 1920, 30, 1000.0, True, None), [("refuse", "length")], "longer than 15 min"),
        (("instagram-reel", 1080, 1920, 30, 900.0005, True, None), [("warn", "length")], "over 3 min"),
        (("tiktok", 1080, 1920, 12, 30.0, True, None), [("refuse", "frame rate")],
         "12 fps is outside the 23-60 fps TikTok takes"),
        (("apple-music-motion-square", 3840, 3840, 60, 10.0, False, None), [("refuse", "frame rate")],
         "60 fps isn't a rate Apple Music motion art, square takes (23.976, 24, 25, 29.97 or 30)"),
        (("apple-music-motion-tall", 2048, 2732, 29.97, 10.0, False, None), [], ""),
        (("youtube-video", 3840, 2160, 23.976, 60.0, True, None), [("info", "frame rate")],
         "23.976 fps isn't one YouTube lists as common (24, 25, 30, 48, 50 or 60); others are accepted"),
        (("spotify-canvas", 1080, 1920, 24, 8.0, True, None), [("refuse", "audio")],
         "it has an audio stream, and Spotify Canvas takes the picture alone"),
        (("instagram-story", 1080, 1920, 30, 59.0, True, 120.0), [("refuse", "file size")],
         "120.00 MB is over the 100 MB Instagram Story takes"),
        (("instagram-reel", 1080, 1920, 30, 20.0, True, 100.0), [("warn", "bitrate")],
         "40.0 Mbps on average is over the 25 Mbps Instagram Reel takes"),
        (("apple-music-motion-square", 3840, 3840, 24, 10.0, False, 20.0), [("warn", "bitrate")],
         "16.0 Mbps on average is under the 45 Mbps Apple Music motion art, square asks for"),
        (("apple-music-motion-square", 3840, 3840, 24, 10.0, False, 90.0), [], ""),
        (("instagram-reel", 1080, 1920, 30, 0.0, True, 100.0), [("refuse", "length")], "0.000 s is shorter than 3 s"),
        (("tiktok", 1080, 1920, 30, 15.0, True, 80.0), [("warn", "file size")],
         "80.00 MB is over 72 MB: third parties report ~72 MB as the Android app's cap"),
        (("tiktok", 1080, 1920, 30, 15.0, True, 5000.0), [("refuse", "file size")], "over the 4096 MB TikTok takes"),
    ],
)
def test_each_rule_of_a_video_names_itself_and_its_level(args, expected, text):
    found = pf.check_video(*args)
    assert kinds(found) == expected
    assert all(f.platform == pf.get(args[0]).id for f in found)
    if text:
        assert text in found[0].message


@pytest.mark.parametrize(
    ("platform", "size", "expected", "text"),
    [
        ("youtube-short", (1920, 1080), [("refuse", "aspect")],
         "1920x1080 isn't 9:16 (or 1080x1080), and YouTube Short takes no other shape"),
        ("instagram-reel", (1920, 1080), [("warn", "aspect")], "1920x1080 isn't 9:16: Instagram crops or pads it"),
        ("instagram-reel", (720, 1280), [("warn", "size")], "720x1280 is under 1080x1920: Instagram enlarges it"),
        ("youtube-video", (7680, 4320), [("info", "size")], "7680x4320 is over 3840x2160: YouTube scales it down"),
        ("instagram-reel", (2160, 3840), [("refuse", "size")], "2160x3840 is 2160 px wide; Instagram Reel takes at most 1920 px"),
        ("tiktok", (300, 533), [("refuse", "size")], "300x533 is 300 px wide; TikTok takes at least 360 px"),
        ("tiktok", (200, 356), [("refuse", "size"), ("refuse", "size")], "200x356 is 200 px wide"),
        ("tiktok", (720, 1280), [], ""),  # inside the bounds TikTok publishes
        ("spotify-canvas", (608, 1080), [("refuse", "size")], "608 px wide; Spotify Canvas takes at least 720 px"),
        ("youtube-short", (1080, 1080), [], ""),
        ("youtube-short", (2160, 2160), [("info", "size")], "2160x2160 is over 1080x1080"),
    ],
)
def test_size_and_shape(platform, size, expected, text):
    found = pf.check_video(platform, *size, None, None, None, None)
    assert kinds(found) == expected
    if text:
        assert text in found[0].message


@pytest.mark.parametrize(
    ("platform", "size", "mb", "expected", "text"),
    [
        ("spotify-cover", (3000, 3000), 8.0, [], ""),
        ("spotify-cover", (2400, 2400), None, [], ""),  # inside Spotify's 640..10000
        ("spotify-cover", (12000, 12000), None, [("refuse", "size"), ("refuse", "size")], "at most 10000 px"),
        ("spotify-cover", (3000, 2000), None, [("refuse", "aspect")], "isn't 1:1, and Spotify cover takes no other shape"),
        ("soundcloud-artwork", (3000, 3000), 1.5, [("info", "size")], "3000x3000 is over 800x800: SoundCloud scales it down"),
        ("soundcloud-artwork", (800, 800), 2.5, [("refuse", "file size")], "2.50 MB is over the 2 MB SoundCloud artwork takes"),
        ("youtube-thumbnail", (3840, 2160), 3.0, [("warn", "file size")], "uploads from mobile are still limited to 2 MB"),
        ("youtube-thumbnail", (3840, 2160), 60.0, [("refuse", "file size")], "over the 50 MB"),
        ("youtube-thumbnail", (1280, 720), None, [], ""),
        ("youtube-thumbnail", (600, 338), None, [("refuse", "size")], "600 px wide; YouTube thumbnail takes at least 640 px"),
        ("instagram-carousel-image", (1080, 1350), None, [], ""),  # 4:5, a size it documents
        ("instagram-carousel-image", (1080, 1200), None, [("warn", "aspect")], "(or 1080x1350, 1080x1080, 1080x566)"),
        ("soundcloud-header", (2000, 420), None, [("refuse", "size"), ("refuse", "size")], "at least 2480 px"),
    ],
)
def test_an_image_is_held_to_its_size_shape_and_file_limit(platform, size, mb, expected, text):
    found = pf.check_image(platform, *size, mb)
    assert kinds(found) == expected
    if text:
        assert text in found[0].message


def test_a_check_of_the_wrong_kind_says_which_to_use():
    with pytest.raises(ValueError, match="spotify-cover is an image: check it with check_image"):
        pf.check_video("spotify-cover", 3000, 3000, None, None, None, None)
    with pytest.raises(ValueError, match="tiktok is a video: check it with check_video"):
        pf.check_image(pf.get("tiktok"), 1080, 1920, None)


@pytest.mark.parametrize(
    ("lufs", "text"),
    [
        (-9.0, "YouTube will turn this down by ~5.0 dB: delivered at -9.0 LUFS, it plays at -14 LUFS (measured by third parties"),
        (-14.3, "delivered at -14.3 LUFS, within half a dB of YouTube's -14 LUFS"),
        (-18.0, "YouTube won't turn this up: delivered at -18.0 LUFS, it plays 4.0 dB under the -14 LUFS"),
    ],
)
def test_the_delivered_loudness_is_compared_with_the_level_the_platform_plays_at(lufs, text):
    (finding,) = pf.check_video("youtube-video", 3840, 2160, 24, 60.0, True, None, lufs=lufs)
    assert (finding.level, finding.rule) == ("info", "loudness") and text in finding.message


def test_a_platform_that_turns_quiet_audio_up_says_it_may():
    both_ways = dataclasses.replace(pf.get("youtube-video"), loudness_down_only=False, brand="Somewhere")
    (finding,) = pf.check_video(both_ways, 3840, 2160, 24, 60.0, True, None, lufs=-18.0)
    assert "Somewhere normalises to -14 LUFS" in finding.message and "may turn this up by ~4.0 dB" in finding.message


def test_no_loudness_without_audio_a_target_or_a_number():
    assert pf.check_video("youtube-video", 3840, 2160, 24, 60.0, False, None, lufs=-9.0) == []
    assert pf.check_video("tiktok", 1080, 1920, 24, 60.0, True, None, lufs=-9.0) == []  # TikTok publishes none
    assert pf.check_video("youtube-video", 3840, 2160, 24, 60.0, True, None, lufs=float("-inf")) == []


def test_a_finding_is_one_line_and_data():
    finding = pf.Finding("warn", "tiktok", "length", "a line")
    assert str(finding) == "warn: tiktok: a line"
    assert finding.to_dict() == {"level": "warn", "platform": "tiktok", "rule": "length", "message": "a line"}


# --------------------------------------------------------------------------
# kaleidophone platforms
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("seconds", "text"),
    [(8, "8 s"), (3.5, "3.5 s"), (60, "1 min"), (90, "90 s"), (180, "3 min"), (7200, "2 h"), (43200, "12 h")],
)
def test_a_limit_reads_as_a_person_says_it(seconds, text):
    assert pf.duration_text(seconds) == text


def test_a_length_reads_both_ends_one_or_none():
    canvas = pf.get("spotify-canvas")
    assert pf.length_text(canvas) == "3 s to 8 s"
    assert pf.length_text(pf.get("tiktok")) == "up to 10 min"
    assert pf.length_text(dataclasses.replace(canvas, max_seconds=None)) == "at least 3 s"
    assert pf.length_text(dataclasses.replace(canvas, min_seconds=None, max_seconds=None)) == "any length"


def test_the_table_has_a_row_per_platform_and_says_what_its_brackets_mean():
    table = pf.platform_table()
    lines = table.splitlines()
    assert lines[0].split() == ["id", "kind", "size", "aspect", "length", "audio", "file", "limit", "loudness",
                                "confidence", "checked"]
    rows = {line.split()[0]: line for line in lines[1 : 1 + len(IDS)]}
    assert list(rows) == IDS
    assert "up to 10 min (3 min)" in rows["tiktok"] and "4096 MB (72 MB)" in rows["tiktok"]
    assert "3 s to 15 min (3 min)" in rows["instagram-reel"] and "third-party" in rows["instagram-reel"]
    assert pf._cells(pf.get("spotify-canvas"))[7] == "-" and "50 MB (2 MB)" in rows["youtube-thumbnail"]
    assert pf._cells(pf.get("youtube-video"))[7] == "-14 LUFS"
    peaked = dataclasses.replace(pf.get("youtube-video"), true_peak_dbtp=-1)
    assert "-14 LUFS, -1 dBTP" in pf.platform_table([peaked])
    assert "in brackets" in table and "where kaleidophone starts warning" in table
    only_soft = dataclasses.replace(pf.get("youtube-thumbnail"), max_file_mb=None)
    assert "  (2 MB)  " in pf.platform_table([only_soft])


def test_one_platform_in_full():
    text = pf.describe(pf.get("ig-reel"))
    lines = text.splitlines()
    assert lines[0] == "instagram-reel -- Instagram Reel (video)"
    assert lines[1] == "aliases     ig-reel"
    assert "size        1080x1920 (9:16); at most 1920 px wide" in text
    assert "length      3 s to 15 min; warns over 3 min: Instagram recommends" in text
    assert "safe area   keep clear of top 269, bottom 672, left 65, right 65 px" in text
    assert "confidence  third-party, checked 2026-09-30" in text
    assert lines[-1] == "  https://www.solidlabs.com/social-safe-zones"
    assert "non-\n" not in text  # words aren't broken at their hyphens
    cover = pf.describe(pf.get("spotify-cover"))
    assert "3000x3000 (1:1); each side 640 to 10000 px; no other shape" in cover
    assert "\nloudness" not in cover and "length" not in cover  # a cover has no audio to be at a level
    assert "Spotify normalises to -14 LUFS" in cover  # the track's, in the notes
    peaked = dataclasses.replace(pf.get("youtube-video"), true_peak_dbtp=-1)
    assert "loudness    -14 LUFS, true peak -1 dBTP (measured by third parties" in pf.describe(peaked)
    assert "at least 2480 px wide, at least 520 px tall" in pf.describe(pf.get("soundcloud-header"))
    assert "each side at least 800 px" in pf.describe(pf.get("soundcloud-artwork"))
    assert "formats     none: not an upload" in pf.describe(pf.get("instagram-grid-thumbnail"))
    assert "frame rate  not published" in pf.describe(pf.get("spotify-canvas"))
    assert "also 2560x1440, 1920x1080, 1280x720" in pf.describe(pf.get("youtube-video"))
    assert "warns over 2 MB: uploads from mobile" in pf.describe(pf.get("youtube-thumbnail"))
    capped = dataclasses.replace(pf.get("soundcloud-artwork"), min_width=None, min_height=None, max_width=900, max_height=900)
    assert "each side at most 900 px" in pf.describe(capped)
    assert "3000x3000 (1:1); each side exactly 3000 px; no other shape" in pf.describe(pf.get("distributor-cover"))
    assert "aliases" not in pf.describe(pf.get("spotify-cover"))


def test_the_registry_as_json():
    data = json.loads(pf.to_json())
    assert [entry["id"] for entry in data] == IDS
    assert json.loads(pf.to_json(pf.get("tt")))["id"] == "tiktok"
    assert len(json.loads(pf.to_json([pf.get("tt")]))) == 1


def test_the_markdown_is_the_table_then_every_platform():
    md = pf.platforms_markdown()
    assert md.startswith("# Platforms\n\n<!-- Generated by `kaleidophone platforms --markdown`")
    assert "| [instagram-reel](#instagram-reel) | video | 1080x1920 | 9:16 |" in md
    assert md.count("\n## ") == 20 and md.endswith("\n")
    assert "- <https://support.spotify.com/us/artists/article/canvas-guidelines/>" in md
    assert pf.entry_markdown(pf.get("tiktok")).startswith("## tiktok\n\n**TikTok** (video); also `tt`\n")
    assert pf._md("a|b") == "a\\|b"


def test_docs_platforms_md_is_the_registry():
    """Regenerate it with `kaleidophone platforms --markdown > docs/PLATFORMS.md`."""
    assert DOC.read_text(encoding="utf-8") == pf.platforms_markdown(), (
        "docs/PLATFORMS.md is out of date with render/platforms.py -- run "
        "`kaleidophone platforms --markdown > docs/PLATFORMS.md`"
    )


def test_the_command_prints_the_table_one_platform_json_or_markdown(capsys):
    assert cli.main(["platforms"]) == cli.EXIT_OK
    assert capsys.readouterr().out == pf.platform_table() + "\n"
    assert cli.main(["platforms", "ig-story"]) == cli.EXIT_OK
    assert capsys.readouterr().out.startswith("instagram-story -- Instagram Story (video)\n")
    assert cli.main(["platforms", "--json"]) == cli.EXIT_OK
    assert len(json.loads(capsys.readouterr().out)) == 20
    assert cli.main(["platforms", "tt", "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["id"] == "tiktok"
    assert cli.main(["platforms", "--markdown"]) == cli.EXIT_OK
    assert capsys.readouterr().out == pf.platforms_markdown()
    assert cli.main(["platforms", "canvas", "--markdown"]) == cli.EXIT_OK
    assert capsys.readouterr().out == pf.entry_markdown(pf.get("spotify-canvas"))


def test_the_command_on_an_unknown_platform_is_one_clean_line(capsys):
    assert cli.main(["platforms", "ig-reels"]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "unknown platform 'ig-reels' -- did you mean ig-reel" in err and "Traceback" not in err
    with pytest.raises(SystemExit):
        cli.main(["platforms", "--json", "--markdown"])
