"""
What each platform asks for: the registry `kaleidophone deliver` delivers to
and `kaleidophone platforms` prints.

One entry per deliverable -- an Instagram Reel, a Spotify Canvas, a SoundCloud
header -- with the size, length, frame rate, audio, file size and loudness
the platform publishes for it. Every entry was researched from the platform's
own documentation where it has any, and carries what that rests on: its
`sources`, a `confidence` (`official` when the numbers come from the
platform's own pages or API reference; `third-party` when the platform
publishes none and they come from guides, press or measurement) and the date
they were `checked`. Platforms change these numbers without notice; the date
says how old they are. docs/PLATFORMS.md is generated from this file
(`kaleidophone platforms --markdown`) and a test fails when it is out of date.

Where the sources disagree, the entry keeps the safe value as the hard limit
and the rest as a softer one, with the dispute in its `notes`: an Instagram
Reel may run 15 min (`max_seconds`; the Graph API's figure, 20 min from the
app's camera since November 2025), and Instagram recommends under 3 min for
reach (`recommended_max_seconds`, with `recommended_why`). The same for file
sizes: TikTok's API takes 4096 MB; third parties report ~72 MB from the
Android app (`recommended_max_file_mb`). A sheet that asks for more than the
hard limit is refused; past the soft one it is delivered with a warning.

check_video() and check_image() hold a file -- planned or delivered -- to an
entry and return findings: `refuse` (the platform won't take it as it is),
`warn` (it will, but not as you'd want) or `info`, each one line naming the
rule. kaleidophone makes the files and stops there: nothing here talks to a
platform (ADR-0006).
"""

from __future__ import annotations

import difflib
import json
import math
import textwrap
from dataclasses import dataclass
from typing import Literal

Kind = Literal["video", "image"]
Audio = Literal["optional", "none"]
Confidence = Literal["official", "third-party"]
Level = Literal["refuse", "warn", "info"]

LEVELS: tuple[Level, ...] = ("refuse", "warn", "info")
# Two frames have one shape when their ratios differ by at most this much: a
# 608x1080 render is 9:16 to 0.09 %, and a 1 % stretch can't be seen.
ASPECT_TOLERANCE = 0.01
# A platform's "MB", read the safe way: 10^6 bytes. "2 MB" may mean 2 MiB;
# 2,000,000 bytes is under either.
MB = 1_000_000
# How far over a limit a time may come out before it counts: a delivered
# file's length is its frame count over its rate, exact to well under this.
_TIME_SLACK = 1e-3
_FPS_SLACK = 0.01


@dataclass(frozen=True)
class SafeArea:
    """Pixels to keep text and faces out of, from each edge, at the platform's size."""

    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class Platform:
    """One deliverable on one platform, as the platform publishes it.

    `width` x `height` is the size kaleidophone delivers at; `sizes` are
    other sizes the platform documents for it -- a render already at one of
    them is stream-copied instead of scaled. Bounds the platform publishes
    (`min_width`, `max_seconds`, `max_file_mb`, ...) refuse; the
    `recommended_*` ones warn, saying why. Times are seconds, file sizes MB
    (10^6 bytes), loudness LUFS, true peak dBTP. The `*_video_mbps`,
    `gop_seconds`, `b_frames` and `jpeg_quality` fields are how `deliver`
    encodes a picture it has to scale for this platform, taken from
    `codec_notes`.
    """

    id: str
    name: str
    brand: str
    kind: Kind
    width: int
    height: int
    aspect: str
    confidence: Confidence
    checked: str  # ISO date the numbers were checked
    sources: tuple[str, ...]
    notes: str
    codec_notes: str
    formats: tuple[str, ...]
    aspect_note: str | None = None
    aliases: tuple[str, ...] = ()
    sizes: tuple[tuple[int, int], ...] = ()
    aspect_fixed: bool = False  # True: another shape is refused, not just cropped or padded
    min_width: int | None = None
    min_height: int | None = None
    max_width: int | None = None
    max_height: int | None = None
    min_seconds: float | None = None
    max_seconds: float | None = None
    recommended_max_seconds: float | None = None
    recommended_why: str | None = None
    fps: str | None = None  # as published
    fps_range: tuple[float, float] | None = None
    fps_allowed: tuple[float, ...] = ()  # the only rates it takes
    fps_common: tuple[float, ...] = ()  # the rates it lists as common; others are accepted
    audio: Audio = "optional"
    max_file_mb: float | None = None
    recommended_max_file_mb: float | None = None
    recommended_file_why: str | None = None
    # The level it plays this file's audio at -- so None for a picture with no audio (a cover,
    # a Canvas, motion art): the level the track plays at under it is in the notes.
    loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    loudness_source: str | None = None
    loudness_down_only: bool = False  # it turns loud audio down and never quiet audio up
    safe_area: SafeArea | None = None
    max_video_mbps: float | None = None
    min_video_mbps: float | None = None
    gop_seconds: float | None = None
    b_frames: int | None = None
    jpeg_quality: int = 95

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def all_sizes(self) -> tuple[tuple[int, int], ...]:
        """Every size the platform documents for it, the delivery size first."""
        return (self.size, *self.sizes)

    def to_dict(self) -> dict:
        """The entry as JSON-ready data -- what `--json` prints and a delivery manifest records."""
        data = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, SafeArea):
                value = vars(value).copy()
            elif isinstance(value, tuple):
                value = [list(v) if isinstance(v, tuple) else v for v in value]
            data[name] = value
        return data


@dataclass(frozen=True)
class Finding:
    """One line about a file and a platform: `refuse` (it won't be taken as
    it is), `warn` (it will, not as you'd want) or `info`. `rule` names what
    was checked -- size, aspect, length, frame rate, audio, file size,
    bitrate, loudness, picture."""

    level: Level
    platform: str
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.platform}: {self.message}"

    def to_dict(self) -> dict:
        return {"level": self.level, "platform": self.platform, "rule": self.rule, "message": self.message}


# --------------------------------------------------------------------------
# the registry -- researched 2026-09-30; see each entry's sources and notes
# --------------------------------------------------------------------------
_ENTRIES: tuple[Platform, ...] = (
    Platform(
        id="instagram-reel",
        name="Instagram Reel",
        brand="Instagram",
        kind="video",
        width=1080,
        height=1920,
        aspect="9:16",
        aliases=("ig-reel",),
        max_width=1920,
        min_seconds=3,
        max_seconds=900,
        recommended_max_seconds=180,
        recommended_why=(
            "Instagram recommends Reels under 3 min to reach non-followers; up to 15 min is allowed (20 "
            "min from the app's camera since Nov 2025)"
        ),
        fps="23-60 (Graph API range); 30 typical",
        fps_range=(23, 60),
        max_file_mb=300,
        formats=("mp4", "mov"),
        codec_notes=(
            "H.264 or HEVC, progressive, closed GOP, 4:2:0, VBR <=25 Mbps, <=1920 px wide; AAC <=48 kHz "
            "mono/stereo, 128 kbps; moov atom at front, no edit lists (Graph API reel spec)."
        ),
        safe_area=SafeArea(top=269, bottom=672, left=65, right=65),
        max_video_mbps=25,
        notes=(
            "Max length is disputed. Sep-2026 third-party guides and Instagram's own in-app camera update"
            " (Nov 2025) say 20 min. The help-centre meta description still says 'up to 3 minutes'. The "
            "Graph API allows 15 min / 300 MB. Instagram only recommends Reels under 3 min to "
            "non-followers. 300 MB is the API cap; the in-app cap is unpublished (Meta ads guide: 4 GB). "
            "Safe area is Meta ads-guide wording: 'at least 14% of the top, 35% of the bottom and 6% on "
            "each side' (read via a third-party quote because facebook.com is robots-blocked)."
        ),
        sources=(
            "https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/",
            "https://help.instagram.com/2720958398006062",
            "https://help.instagram.com/1038071743007909/",
            "https://www.socialmediatoday.com/news/instagram-update-reels-camera-with-improved-functions/806247/",
            "https://petapixel.com/2025/11/25/instagram-updates-camera-so-you-can-film-20-minute-reels/",
            "https://later.com/blog/instagram-reels/",
            "https://influencermarketinghub.com/instagram-video-size/",
            "https://www.facebook.com/business/ads-guide/update/video/instagram-reels",
            "https://www.solidlabs.com/social-safe-zones",
        ),
        confidence="third-party",
        checked="2026-09-30",
    ),
    Platform(
        id="instagram-reel-cover",
        name="Instagram Reel cover",
        brand="Instagram",
        kind="image",
        width=1080,
        height=1920,
        aspect="9:16",
        aliases=("ig-reel-cover",),
        audio="none",
        formats=("jpg",),
        codec_notes=(
            "sRGB JPEG. The Graph API cover_url sets the Reels-tab cover. API images are capped at 8 MB "
            "(assumed to apply to covers too)."
        ),
        safe_area=SafeArea(top=240, bottom=240, left=0, right=0),
        notes=(
            "Shown at full 9:16 in the Reels tab. The profile grid shows the centre 3:4 (1080x1440), so "
            "keep titles and faces inside the middle 1440 px. Since early 2026 you can reposition the "
            "grid crop after posting with 'Adjust preview'."
        ),
        sources=(
            "https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/",
            "https://later.com/blog/instagram-reels/",
            "https://influencermarketinghub.com/instagram-video-size/",
            "https://almcorp.com/blog/instagram-thumbnail-editing-profile-grid/",
        ),
        confidence="third-party",
        checked="2026-09-30",
    ),
    Platform(
        id="instagram-grid-thumbnail",
        name="Instagram profile grid tile",
        brand="Instagram",
        kind="image",
        width=1080,
        height=1440,
        aspect="3:4",
        aliases=("ig-grid", "ig-grid-thumbnail"),
        audio="none",
        formats=(),
        codec_notes="A display crop, not an upload.",
        notes=(
            "Grid tiles changed from 1:1 to 3:4 in Jan 2025 and are still 3:4 in Sep-2026 guides. "
            "Centre-crop maths: a 9:16 cover shows its middle 1080x1440 (240 px lost top and bottom); a "
            "4:5 post shows ~1012x1350 (34 px lost each side); a 1:1 post shows 810x1080 (135 px lost "
            "each side); a 3:4 post is uncropped. The crop can be adjusted per post with 'Adjust preview'"
            " (~Mar 2026)."
        ),
        sources=(
            "https://www.businesstoday.in/technology/news/story/instagram-head-announces-big-changes-3-minute-reels-and-new-look-for-profile-grid-461527-2025-01-21",
            "https://9to5mac.com/2025/05/29/instagram-changes-standard-photo-aspect-ratio/",
            "https://www.kapwing.com/resources/instagrams-new-grid-layout-size-and-dimensions-2025/",
            "https://blog.hootsuite.com/social-media-image-sizes-guide/",
            "https://almcorp.com/blog/instagram-thumbnail-editing-profile-grid/",
        ),
        confidence="third-party",
        checked="2026-09-30",
    ),
    Platform(
        id="instagram-story",
        name="Instagram Story",
        brand="Instagram",
        kind="video",
        width=1080,
        height=1920,
        aspect="9:16",
        aliases=("ig-story",),
        max_width=1920,
        min_seconds=3,
        max_seconds=60,
        fps="23-60",
        fps_range=(23, 60),
        max_file_mb=100,
        formats=("mp4", "mov", "jpg"),
        codec_notes=(
            "Same video rules as Reels (H.264/HEVC, AAC <=48 kHz, VBR <=25 Mbps, <=1920 px). Story "
            "images: JPEG <=8 MB, sRGB."
        ),
        safe_area=SafeArea(top=269, bottom=672, left=65, right=65),
        max_video_mbps=25,
        notes=(
            "60 s per story card, confirmed by Instagram in Sep 2022; third parties say longer uploads "
            "are split into cards. The safe area uses Meta's 9:16 guidance for Stories and Reels, which a"
            " third party reports was unified in Mar 2026. The older Stories-only guidance was ~14% top "
            "and ~20% (384 px) bottom. The safe area is third-party."
        ),
        sources=(
            "https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/",
            "https://www.socialmediatoday.com/news/Instagram-Announces-Videos-Under-60-Seconds-Stories-No-Longer-Split-Segments/632598/",
            "https://billo.app/blog/meta-ads-safe-zones/",
            "https://www.lucidmedia.co.nz/blog/instagram-facebook-ad-safe-zones-2026/",
            "https://www.solidlabs.com/social-safe-zones",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="instagram-carousel-image",
        name="Instagram carousel image",
        brand="Instagram",
        kind="image",
        width=1080,
        height=1440,
        aspect="3:4",
        aspect_note="allowed 1.91:1 to 3:4; 1:1 and 4:5 also common",
        aliases=("ig-carousel", "ig-carousel-image"),
        sizes=((1080, 1350), (1080, 1080), (1080, 566)),
        min_width=320,
        max_width=1440,
        audio="none",
        max_file_mb=8,
        formats=("jpg",),
        codec_notes=(
            "Graph API: JPEG only, sRGB, 320-1440 px wide, ratio 4:5 to 1.91:1 (the API has not added "
            "3:4). The app displays images 1080 px wide."
        ),
        notes=(
            "Up to 20 photos or videos per post in the app (was 10 until Aug 2024; the Graph API is still"
            " 10). 3:4 portrait has been allowed in the app since 29 May 2025 (the previous maximum was "
            "4:5, 1080x1350). Third parties say the first slide sets the frame, so design all slides at "
            "one ratio. Also applies to single-image feed posts."
        ),
        sources=(
            "https://help.instagram.com/269314186824048/",
            "https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/",
            "https://9to5mac.com/2025/05/29/instagram-changes-standard-photo-aspect-ratio/",
            "https://www.socialmediatoday.com/news/instagram-expands-carousels-to-20-frames/723792/",
            "https://storrito.com/resources/how-instagrams-20-slide-carousels-work-and-what-the-new-limits-are/",
        ),
        confidence="third-party",
        checked="2026-09-30",
    ),
    Platform(
        id="instagram-carousel-video",
        name="Instagram carousel video",
        brand="Instagram",
        kind="video",
        width=1080,
        height=1440,
        aspect="3:4",
        aspect_note="match the carousel ratio (1:1, 4:5 or 3:4)",
        aliases=("ig-carousel-video",),
        sizes=((1080, 1350), (1080, 1080)),
        min_seconds=3,
        max_seconds=60,
        fps="23-60",
        fps_range=(23, 60),
        formats=("mp4", "mov"),
        codec_notes="Assumed to follow the Reels rules (H.264/HEVC + AAC).",
        max_video_mbps=25,
        notes=(
            "The 60 s limit per video slide comes only from third parties; no official number was found. "
            "Each video counts toward the 20-item limit."
        ),
        sources=(
            "https://storrito.com/resources/how-instagrams-20-slide-carousels-work-and-what-the-new-limits-are/",
            "https://posteverywhere.ai/blog/how-many-photos-can-you-post-on-instagram",
            "https://influencermarketinghub.com/instagram-video-size/",
        ),
        confidence="third-party",
        checked="2026-09-30",
    ),
    Platform(
        id="tiktok",
        name="TikTok",
        brand="TikTok",
        kind="video",
        width=1080,
        height=1920,
        aspect="9:16",
        aliases=("tt",),
        min_width=360,
        min_height=360,
        max_width=4096,
        max_height=4096,
        max_seconds=600,
        recommended_max_seconds=180,
        recommended_why="every TikTok creator can post 3 min; only some can post 5 or 10",
        fps="23-60",
        fps_range=(23, 60),
        max_file_mb=4096,
        recommended_max_file_mb=72,
        recommended_file_why=(
            "third parties report ~72 MB as the Android app's cap (~287.6 MB on iOS); the API takes 4096 "
            "MB"
        ),
        formats=("mp4", "webm", "mov"),
        codec_notes=(
            "H.264 recommended (H.265, VP8 and VP9 accepted); each side 360-4096 px (Content Posting "
            "API)."
        ),
        safe_area=SafeArea(top=130, bottom=484, left=44, right=140),
        notes=(
            "TikTok's own doc: 'All TikTok creators can post 3-minute videos, while some have access to "
            "post 5-minute or 10-minute videos.' Only 180 s is guaranteed; the API maximum is 600 s. "
            "60-min web uploads were a limited 2024 test. 4 GB is the API cap. The in-app caps (~287.6 MB"
            " iOS, ~72 MB Android) and ~10 GB on web are third-party figures. In-feed ads need at least "
            "540x960, at most 500 MB and at least 516 kbps. The safe area was measured by third parties "
            "from TikTok Ads Manager overlay files, and the bottom margin grows with caption length."
        ),
        sources=(
            "https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide",
            "https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en",
            "https://cadenus.io/resources/blog/tiktok-safe-zone/",
            "https://filesize.org/limits/tiktok/",
            "https://techcrunch.com/2025/02/27/in-challenge-to-youtube-tiktok-revamps-its-desktop-platform/",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="youtube-video",
        name="YouTube video",
        brand="YouTube",
        kind="video",
        width=3840,
        height=2160,
        aspect="16:9",
        aliases=("youtube", "yt", "yt-video"),
        sizes=((2560, 1440), (1920, 1080), (1280, 720)),
        max_seconds=43200,
        recommended_max_seconds=900,
        recommended_why="unverified accounts are limited to 15 min (verified ones: 12 h)",
        fps="upload at the recorded rate: 24/25/30/48/50/60",
        fps_common=(24, 25, 30, 48, 50, 60),
        max_file_mb=262144,
        formats=("mp4",),
        codec_notes=(
            "MP4, no edit lists, moov atom at front. H.264 High Profile, progressive, 2 consecutive "
            "B-frames, closed GOP of half the frame rate, CABAC, VBR, 4:2:0, BT.709 SDR. SDR bitrates at "
            "24-30 fps / 48-60 fps: 2160p 35-45 / 53-68 Mbps; 1440p 16 / 24; 1080p 8 / 12; 720p 5 / 7.5. "
            "HDR: 2160p 44-56 / 66-85; 1440p 20 / 30; 1080p 10 / 15. Audio: AAC-LC, Opus or Eclipsa Audio"
            " at 48 kHz; stereo 384 kbps (mono 128, 5.1 512)."
        ),
        loudness_lufs=-14,
        loudness_source="measured by third parties; YouTube publishes no target",
        loudness_down_only=True,
        gop_seconds=0.5,
        b_frames=2,
        notes=(
            "Verified accounts can upload 256 GB or 12 h, whichever is less; unverified accounts are "
            "limited to 15 min. YouTube publishes no loudness target: ~-14 LUFS is measured by third "
            "parties, and YouTube only turns loud videos down."
        ),
        sources=(
            "https://support.google.com/youtube/answer/1722171?hl=en",
            "https://support.google.com/youtube/answer/71673?hl=en",
            "https://www.izotope.com/community/blog/mastering-for-streaming-platforms",
            "https://productionadvice.co.uk/stats-for-nerds/",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="youtube-short",
        name="YouTube Short",
        brand="YouTube",
        kind="video",
        width=1080,
        height=1920,
        aspect="9:16",
        aspect_note="1:1 also counts as a Short",
        aliases=("yt-short", "shorts"),
        sizes=((1080, 1080),),
        aspect_fixed=True,
        max_seconds=180,
        recommended_max_seconds=60,
        recommended_why=(
            "YouTube blocks a Short over 1 min with any active Content ID claim, worldwide -- and a "
            "distributed song can carry one (the likely fix, unverified: whitelist your channel with your"
            " distributor)"
        ),
        fps="same as youtube-video",
        fps_common=(24, 25, 30, 48, 50, 60),
        max_file_mb=262144,
        formats=("mp4",),
        codec_notes=(
            "Same encoding recommendations as youtube-video (1080p: 8 Mbps at 24-30 fps, 12 Mbps at 48-60"
            " fps)."
        ),
        loudness_lufs=-14,
        loudness_source="measured by third parties; YouTube publishes no target",
        loudness_down_only=True,
        safe_area=SafeArea(top=192, bottom=480, left=0, right=108),
        gop_seconds=0.5,
        b_frames=2,
        notes=(
            "Square or vertical uploads up to 3 min become Shorts (previously 60 s): from 15 Oct 2024, "
            "but for Official Artist Channels only from 8 Dec 2025. To keep a music video of 3 min or "
            "less as long-form, upload it at 16:9 (YouTube's advice). Any Short over 1 min with any "
            "active Content ID claim is blocked globally; likely fix (unverified): whitelist your own "
            "channel with your distributor. Most licensed songs can be used for up to 90 s in a Short "
            "(some only 60 or 30 s). The safe area follows Google's Shorts-ads guidance: avoid the top "
            "10%, bottom 25% and right 10%."
        ),
        sources=(
            "https://support.google.com/youtube/answer/15424877?hl=en",
            "https://support.google.com/youtube/answer/12779649?hl=en&co=GENIE.Platform%3DDesktop",
            "https://business.google.com/us/ad-solutions/youtube-ads/shorts-ads/",
            "https://support.google.com/youtube/answer/1722171?hl=en",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="youtube-thumbnail",
        name="YouTube thumbnail",
        brand="YouTube",
        kind="image",
        width=3840,
        height=2160,
        aspect="16:9",
        aliases=("yt-thumbnail",),
        min_width=640,
        audio="none",
        max_file_mb=50,
        recommended_max_file_mb=2,
        recommended_file_why="uploads from mobile are still limited to 2 MB",
        formats=("jpg", "png"),
        codec_notes="Minimum width 640 px.",
        notes=(
            "Changed from 1280x720 and 2 MB: the 50 MB limit was announced 30 Oct 2025 and live by ~Mar "
            "2026. Uploads from mobile are still limited to 2 MB. Requires a verified account. Vertical "
            "videos with a 16:9 custom thumbnail get an auto-generated 4:5 thumbnail on Home, Explore and"
            " Subscriptions. Third parties note the duration badge covers the bottom-right corner."
        ),
        sources=(
            "https://support.google.com/youtube/answer/72431?hl=en",
            "https://9to5google.com/2025/10/30/youtube-video-thumbnail-file-size-limits/",
            "https://www.ubergizmo.com/2026/03/youtube-increases-custom-thumbnail/",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="youtube-short-thumbnail",
        name="YouTube Short thumbnail",
        brand="YouTube",
        kind="image",
        width=2160,
        height=3840,
        aspect="9:16",
        aliases=("yt-short-thumbnail",),
        min_height=640,
        audio="none",
        max_file_mb=50,
        recommended_max_file_mb=2,
        recommended_file_why="uploads from mobile are limited to 2 MB",
        formats=("jpg", "png"),
        codec_notes="Minimum height 640 px.",
        notes="Custom Shorts thumbnails need a verified account. Uploads from mobile are limited to 2 MB.",
        sources=(
            "https://support.google.com/youtube/answer/72431?hl=en",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="spotify-canvas",
        name="Spotify Canvas",
        brand="Spotify",
        kind="video",
        width=1080,
        height=1920,
        aspect="9:16",
        aliases=("canvas",),
        sizes=((720, 1280),),
        aspect_fixed=True,
        min_width=720,
        max_width=1080,
        min_seconds=3,
        max_seconds=8,
        audio="none",
        formats=("mp4", "jpg"),
        codec_notes=(
            "H.264 MP4 with a video track only; third parties report embedded audio commonly causes "
            "upload failures. Spotify publishes no fps or file-size limit (the '8 MB' figure is "
            "third-party and unverified)."
        ),
        notes=(
            "Spotify's wording 'Between 720px - 1080px tall' does not work literally at 9:16. It is "
            "usually read as the short edge, i.e. 720x1280 to 1080x1920. The Canvas loops in Now Playing,"
            " phone screens may crop the edges, and UI covers the top and bottom (no pixel margins "
            "published). Avoid talking, singing or rapping, rapid cuts and intense flashing. Not allowed:"
            " URLs or ticket links, follow/like prompts, social handles, brand or Spotify logos, product "
            "promos, contests, or unrelated text. Explicit content must be marked. Upload through Spotify"
            " for Artists. The Canvas is silent: the track it loops over plays at Spotify's normalisation, "
            "-14 LUFS by default (Loud -11, Quiet -19), from a master at or below -1 dBTP."
        ),
        sources=(
            "https://support.spotify.com/us/artists/article/canvas-guidelines/",
            "https://support.spotify.com/us/artists/article/canvas-content-policy/",
            "https://support.spotify.com/us/artists/article/fix-spotify-canvas-upload-error/",
            "https://trackgleam.com/learn/how-to-make-a-spotify-canvas",
            "https://support.spotify.com/us/artists/article/loudness-normalization/",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="spotify-cover",
        name="Spotify cover",
        brand="Spotify",
        kind="image",
        width=3000,
        height=3000,
        aspect="1:1",
        aspect_fixed=True,
        min_width=640,
        min_height=640,
        max_width=10000,
        max_height=10000,
        audio="none",
        formats=("jpg", "png", "tiff"),
        codec_notes=(
            "Spotify: 640-10000 px per side, lossless-encoded TIFF/PNG/JPG, sRGB 24-bit with the colour "
            "profile applied (no embedded profile or orientation metadata), no upscaling."
        ),
        jpeg_quality=100,
        notes=(
            "Cover art reaches Spotify through a distributor, whose limits are stricter: 3000x3000 "
            "satisfies Spotify, Apple (3000 recommended) and every distributor in distributor-cover. "
            "Spotify normalises to -14 LUFS by default (Loud -11, Quiet -19; ITU-R "
            "BS.1770). Keep masters at or below -1 dBTP, or -2 dBTP if louder than -14 LUFS. Album "
            "playback keeps album gain; the limiter applies only in Loud mode."
        ),
        sources=(
            "https://support.spotify.com/us/artists/article/cover-art-requirements/",
            "https://support.spotify.com/us/artists/article/loudness-normalization/",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        # One entry for every distributor, not one per distributor: the file is the same, and the
        # stores (Spotify, Apple Music, ...) get their cover through whichever one you use.
        id="distributor-cover",
        name="Distributor cover",
        brand="your distributor",
        kind="image",
        width=3000,
        height=3000,
        aspect="1:1",
        aliases=(
            "distributor",
            "distrokid",
            "tunecore",
            "cd-baby",
            "amuse",
            "unitedmasters",
            "landr",
            "soundcloud-distribution",
        ),
        aspect_fixed=True,
        min_width=3000,
        min_height=3000,
        max_width=3000,
        max_height=3000,
        audio="none",
        formats=("jpg",),
        max_file_mb=10,
        codec_notes=(
            "A square RGB JPEG of exactly 3000x3000 px, under 10 MB, is the one file every distributor "
            "listed here takes: DistroKid 1000 px or more, JPG only, 3000 ideal; TuneCore 1600-3000, "
            "under 10 MB; CD Baby 1400-3000, under 25 MB; Amuse 1400-6000; LANDR 1500-6000; "
            "UnitedMasters 3000-6000; SoundCloud for Artists 3000 or more, at 300 dpi."
        ),
        notes=(
            "The cover a distributor sends to every store. Between them, they refuse: text other than "
            "the artist name and the title (some allow the label), and a title written twice, side by "
            "side in two languages (SoundCloud); URLs, QR codes, social handles, store or brand logos, "
            "prices, dates and references to a CD or other physical format; images you don't hold the "
            "rights to, stock photos and art reused across releases; blurry, pixelated, stretched, "
            "rotated or cropped art; a Parental Advisory label on a release not marked explicit. Read "
            "your own distributor's page before release day: they change."
        ),
        sources=(
            "https://support.distrokid.com/hc/en-us/articles/360013534334-What-Are-the-Requirements-for-Album-Artwork",
            "https://support.tunecore.com/hc/en-us/articles/115006685728-What-are-TuneCore-s-cover-art-formatting-requirements",
            "https://support.cdbaby.com/hc/en-us/articles/360037660592-Artwork-Requirements",
            "https://support.amuse.io/en/articles/107739-what-is-important-when-it-comes-to-artwork",
            "https://support.landr.com/hc/en-us/articles/115009568447-What-are-LANDR-s-cover-art-guidelines",
            "https://support.unitedmasters.com/hc/en-us/articles/29586138045459-How-do-I-size-my-cover-art-correctly",
            "https://help.soundcloud.com/hc/en-us/articles/40259650089243-Artwork-Guidelines-for-Digital-Distribution",
        ),
        confidence="official",
        checked="2026-10-01",
    ),
    Platform(
        id="apple-music-cover",
        name="Apple Music cover",
        brand="Apple Music",
        kind="image",
        width=3000,
        height=3000,
        aspect="1:1",
        aliases=("apple-cover",),
        aspect_fixed=True,
        min_width=1400,
        min_height=1400,
        audio="none",
        formats=("jpg", "png"),
        codec_notes="JPEG or PNG at 100% quality. 3000x3000 or larger recommended; 1400x1400 minimum.",
        jpeg_quality=100,
        notes=(
            "Delivered through a distributor. Not allowed: URLs, logos, QR codes, references to "
            "competitors, pricing or upselling, audio-format claims (Atmos, lossless, 24-bit), references"
            " to physical packaging or retailers, future release dates, misleading artist depictions, and"
            " low-quality, pixelated, misaligned or rotated art. The track plays with Sound Check, at ~-16 "
            "LUFS as third parties measure it; Apple publishes no number, and its only official figure is "
            "to 'leave at least 1 dB of headroom'."
        ),
        sources=(
            "https://itunespartner.apple.com/music/support/5215-digital-packaging-music",
            "https://help.apple.com/itc/musicstyleguide/en.lproj/static.html",
            "https://www.apple.com/apple-music/apple-digital-masters/docs/apple-digital-masters.pdf",
            "https://www.meterplugs.com/blog/2022/03/23/apple-switch-to-lufs.html",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="apple-music-motion-square",
        name="Apple Music motion art, square",
        brand="Apple Music",
        kind="video",
        width=3840,
        height=3840,
        aspect="1:1",
        aliases=("apple-motion-square",),
        aspect_fixed=True,
        min_seconds=8,
        max_seconds=35,
        fps="23.976, 24, 25, 29.97 or 30",
        fps_allowed=(23.976, 24, 25, 29.97, 30),
        audio="none",
        formats=("mov", "mp4"),
        codec_notes=(
            "Apple ProRes 4444, 422 HQ, 422 or 422 LT in .mov, or H.264 in .mp4 at 45-100 Mbps. Rec.709 "
            "or sRGB, square pixels. Deliver without an audio track."
        ),
        max_video_mbps=100,
        min_video_mbps=45,
        notes=(
            "Shown on Mac, iPad and TV. Must loop seamlessly, and the first frame must match the cover. "
            "Not allowed: drop or hold frames, multiple edits, frame borders, frenetic flashing, a "
            "Parental Advisory logo, or static stills. Can only be delivered by a distributor or "
            "Preferred Provider; Apple Music for Artists has no self-upload. Symphonic limits it to 8-20 "
            "s (at $50), and FUGA supports singles and albums only; ask yours before making one. "
            "Silent: the track plays with Sound Check, at ~-16 LUFS as third "
            "parties measure it (Apple publishes no number)."
        ),
        sources=(
            "https://help.apple.com/itc/albummotionguide/en.lproj/static.html",
            "https://help.apple.com/itc/musicstyleguide/en.lproj/static.html",
            "https://artists.apple.com/support/5544-create-motion-artwork",
            "https://itunespartner.apple.com/music/support/5499-create-deliver-motion-artwork",
            "https://support.symdistro.com/hc/en-us/articles/32428977235213-Motion-Art-on-Apple",
            "https://support.fuga.com/hc/en-us/articles/38908424969620-How-to-Add-Motion-Artwork-to-Your-Apple-Music-Release",
            "https://www.meterplugs.com/blog/2022/03/23/apple-switch-to-lufs.html",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="apple-music-motion-tall",
        name="Apple Music motion art, tall",
        brand="Apple Music",
        kind="video",
        width=2048,
        height=2732,
        aspect="3:4",
        aliases=("apple-motion-tall",),
        aspect_fixed=True,
        min_seconds=8,
        max_seconds=35,
        fps="23.976, 24, 25, 29.97 or 30",
        fps_allowed=(23.976, 24, 25, 29.97, 30),
        audio="none",
        formats=("mov", "mp4"),
        codec_notes="Same as apple-music-motion-square.",
        max_video_mbps=100,
        min_video_mbps=45,
        notes=(
            "Shown on iPhone and Android. Must be full-frame 3:4, not a scaled-down 1:1 image. Text and "
            "key art must stay in Apple's safe area, clear of the notch, UI text, buttons and the bottom "
            "gradient; Apple publishes no pixel margins. Symphonic requires both files to be the same "
            "length. Silent: the track plays with Sound Check, at ~-16 LUFS as third parties measure it "
            "(Apple publishes no number)."
        ),
        sources=(
            "https://help.apple.com/itc/albummotionguide/en.lproj/static.html",
            "https://help.apple.com/itc/musicstyleguide/en.lproj/static.html",
            "https://support.symdistro.com/hc/en-us/articles/32428977235213-Motion-Art-on-Apple",
            "https://www.meterplugs.com/blog/2022/03/23/apple-switch-to-lufs.html",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="soundcloud-artwork",
        name="SoundCloud artwork",
        brand="SoundCloud",
        kind="image",
        width=800,
        height=800,
        aspect="1:1",
        aliases=("sc-artwork",),
        aspect_fixed=True,
        min_width=800,
        min_height=800,
        audio="none",
        max_file_mb=2,
        formats=("jpg", "png"),
        codec_notes="At least 800x800 px and under 2 MB.",
        notes=(
            "800x800 is the minimum; a larger square works if it stays under 2 MB, so a 3000x3000 "
            "distribution master usually needs recompressing. SoundCloud says it applies loudness "
            "normalisation. It recommends masters at -14 LUFS integrated and at or below -1 dBTP (-2 dBTP"
            " if louder). It streams Ogg/Vorbis and AAC."
        ),
        sources=(
            "https://help.soundcloud.com/hc/en-us/articles/46022345620123-Edit-and-customize-your-tracks",
            "https://help.soundcloud.com/hc/en-us/articles/360053660014-Will-SoundCloud-play-my-track-at-the-level-it-s-mastered",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="soundcloud-header",
        name="SoundCloud header",
        brand="SoundCloud",
        kind="image",
        width=2480,
        height=520,
        aspect="62:13",
        aspect_note="~4.77:1",
        aliases=("sc-header",),
        min_width=2480,
        min_height=520,
        audio="none",
        max_file_mb=2,
        formats=("jpg", "png"),
        codec_notes="Minimum 2480x520 px.",
        notes=(
            "Avoid text in the header because 'it will be cropped on smaller screens'. Drag and zoom "
            "repositioning only works for images larger than 1240x260. No pixel safe area is published."
        ),
        sources=(
            "https://help.soundcloud.com/hc/en-us/articles/115003450007-Update-Your-Profile-Image-and-Header",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
    Platform(
        id="soundcloud-profile-image",
        name="SoundCloud profile image",
        brand="SoundCloud",
        kind="image",
        width=800,
        height=800,
        aspect="1:1",
        aliases=("sc-profile",),
        aspect_fixed=True,
        min_width=800,
        min_height=800,
        audio="none",
        max_file_mb=2,
        formats=("jpg", "png"),
        codec_notes="At least 800x800 px and 2 MB or less.",
        notes="Displayed as a circle. Can only be uploaded through the SoundCloud website.",
        sources=(
            "https://help.soundcloud.com/hc/en-us/articles/115003450007-Update-Your-Profile-Image-and-Header",
        ),
        confidence="official",
        checked="2026-09-30",
    ),
)

PLATFORMS: dict[str, Platform] = {p.id: p for p in _ENTRIES}
ALIASES: dict[str, str] = {alias: p.id for p in _ENTRIES for alias in p.aliases}


class UnknownPlatform(ValueError):
    """A platform id (or alias) the registry doesn't have."""

    def __init__(self, name: str) -> None:
        close = difflib.get_close_matches(name.strip().lower(), [*PLATFORMS, *ALIASES], n=2, cutoff=0.6)
        hint = f" -- did you mean {' or '.join(close)}?" if close else ""
        super().__init__(f"unknown platform {name!r}{hint} (`kaleidophone platforms` lists them)")


def get(name: str) -> Platform:
    """An entry by its id or an alias (`ig-reel` is instagram-reel), any case."""
    key = name.strip().lower()
    platform = PLATFORMS.get(ALIASES.get(key, key))
    if platform is None:
        raise UnknownPlatform(name)
    return platform


def of_kind(kind: Kind) -> list[Platform]:
    """Every video entry, or every image entry, in registry order."""
    return [p for p in _ENTRIES if p.kind == kind]


def _entry(platform: Platform | str, kind: Kind) -> Platform:
    entry = platform if isinstance(platform, Platform) else get(platform)
    if entry.kind != kind:
        other = "check_image" if entry.kind == "image" else "check_video"
        raise ValueError(f"{entry.id} is {'an image' if entry.kind == 'image' else 'a video'}: check it with {other}()")
    return entry


# --------------------------------------------------------------------------
# frames: one shape fitted into another
# --------------------------------------------------------------------------
# pad-blur, the "blurred sides" composition, for a video (deliver: ffmpeg's
# gblur and eq) and a cover (cover/matrix.py: Pillow) alike: the picture,
# whole, centred over a copy of itself that covers the frame -- scaled to a
# frame PAD_BLUR_SHRINK times smaller, blurred there and scaled back up (a
# strong, smooth blur for the cost of a small one), darkened and desaturated,
# so the copy reads as the picture's light and colour around it, not as a
# second picture. The copy is the picture enlarged 1.8-3.2x, so the blur is
# a share of the frame, not a number of pixels: a sigma of PAD_BLUR_SIGMA of
# the frame's longer side (6 % of a 16:9 frame's width). The fixed 48 px it
# was -- 1.25 % of a 4K frame's width -- left the copy readable: a title in a
# 9:16 render's sides at 16:9, a cover's drawing in a YouTube thumbnail's.
PAD_BLUR_SHRINK = 8
PAD_BLUR_SIGMA = 0.06  # of the frame's longer side
PAD_BLUR_BRIGHTNESS = -0.12  # added to the luma, on 0..1 (ffmpeg eq's brightness)
PAD_BLUR_SATURATION = 0.5  # the share of the colour kept (eq's saturation)


def blur_frame(frame: tuple[int, int]) -> tuple[int, int]:
    """The small frame pad-blur blurs in: `frame` PAD_BLUR_SHRINK times smaller, in even pixels."""
    return tuple(max(2, side // PAD_BLUR_SHRINK // 2 * 2) for side in frame)


def blur_sigma(frame: tuple[int, int]) -> float:
    """pad-blur's Gaussian for `frame`, in the small frame's pixels: PAD_BLUR_SIGMA of the
    frame's longer side, to a tenth of a pixel (28.8 for 3840x2160: 230 px at full size)."""
    return round(PAD_BLUR_SIGMA * max(frame) / PAD_BLUR_SHRINK, 1)


def same_aspect(a: tuple[int, int], b: tuple[int, int], tolerance: float = ASPECT_TOLERANCE) -> bool:
    """Whether two frames have one shape, to `tolerance` of the ratio."""
    (aw, ah), (bw, bh) = a, b
    return abs(aw * bh - ah * bw) <= tolerance * ah * bw


def _even(x: float) -> int:
    return max(2, 2 * round(x / 2))


def _even_up(x: float) -> int:
    return max(2, 2 * math.ceil(x / 2 - 1e-9))


def fit_size(source: tuple[int, int], frame: tuple[int, int]) -> tuple[int, int]:
    """The largest size of `source`'s shape inside `frame`, in even pixels:
    the picture whole, with bars (or a blurred copy) around it."""
    (sw, sh), (fw, fh) = source, frame
    if sw * fh >= sh * fw:  # as wide as the frame or wider: full width
        return fw, min(fh, _even(fw * sh / sw))
    return min(fw, _even(fh * sw / sh)), fh


def cover_size(source: tuple[int, int], frame: tuple[int, int]) -> tuple[int, int]:
    """The smallest size of `source`'s shape that covers `frame`, in even
    pixels: the picture cropped to the frame."""
    (sw, sh), (fw, fh) = source, frame
    if sw * fh >= sh * fw:  # wider: full height, the sides overflow
        return max(fw, _even_up(fh * sw / sh)), fh
    return fw, max(fh, _even_up(fw * sh / sw))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def check_video(
    platform: Platform | str,
    width: int | None,
    height: int | None,
    fps: float | None,
    seconds: float | None,
    has_audio: bool | None,
    file_mb: float | None,
    *,
    lufs: float | None = None,
) -> list[Finding]:
    """A video -- planned or delivered -- held to a platform's entry. A value
    that isn't known (None) isn't checked. `lufs`, the file's integrated
    loudness, is compared with the level the platform normalises to."""
    p = _entry(platform, "video")
    return [
        *_size_findings(p, width, height),
        *_length_findings(p, seconds),
        *_fps_findings(p, fps),
        *_audio_findings(p, has_audio),
        *_file_findings(p, file_mb),
        *_bitrate_findings(p, file_mb, seconds),
        *(_loudness_findings(p, lufs) if has_audio else []),
    ]


def check_image(platform: Platform | str, width: int | None, height: int | None, file_mb: float | None) -> list[Finding]:
    """An image -- planned or delivered -- held to a platform's entry."""
    p = _entry(platform, "image")
    return [*_size_findings(p, width, height), *_file_findings(p, file_mb)]


def _size_findings(p: Platform, width: int | None, height: int | None) -> list[Finding]:
    if width is None or height is None or (width, height) in p.all_sizes:
        return []
    size = f"{width}x{height}"
    found = []
    for limit, value, what, most in (
        (p.min_width, width, "wide", False),
        (p.min_height, height, "tall", False),
        (p.max_width, width, "wide", True),
        (p.max_height, height, "tall", True),
    ):
        if limit is not None and (value > limit if most else value < limit):
            found.append(Finding(
                "refuse", p.id, "size",
                f"{size} is {value} px {what}; {p.name} takes {'at most' if most else 'at least'} {limit} px",
            ))
    shapes = [s for s in p.all_sizes if same_aspect((width, height), s)]
    if not shapes:
        others = f" (or {', '.join(f'{w}x{h}' for w, h in p.sizes)})" if p.sizes else ""
        if p.aspect_fixed:
            found.append(Finding("refuse", p.id, "aspect", f"{size} isn't {p.aspect}{others}, and {p.name} takes no other shape"))
        else:
            found.append(Finding("warn", p.id, "aspect", f"{size} isn't {p.aspect}{others}: {p.brand} crops or pads it"))
    elif not found:
        # Inside the bounds a platform publishes, any size is its to take;
        # where it publishes none, its own size is the measure.
        w, h = shapes[0]
        if width * height < w * h and p.min_width is None and p.min_height is None:
            found.append(Finding("warn", p.id, "size", f"{size} is under {w}x{h}: {p.brand} enlarges it"))
        elif width * height > w * h and p.max_width is None and p.max_height is None:
            found.append(Finding("info", p.id, "size", f"{size} is over {w}x{h}: {p.brand} scales it down"))
    return found


def _length_findings(p: Platform, seconds: float | None) -> list[Finding]:
    if seconds is None:
        return []
    took = f"{p.name} takes {length_text(p)}"
    if p.min_seconds is not None and seconds < p.min_seconds - _TIME_SLACK:
        return [Finding("refuse", p.id, "length", f"{seconds:.3f} s is shorter than {duration_text(p.min_seconds)}: {took}")]
    if p.max_seconds is not None and seconds > p.max_seconds + _TIME_SLACK:
        return [Finding("refuse", p.id, "length", f"{seconds:.3f} s is longer than {duration_text(p.max_seconds)}: {took}")]
    if p.recommended_max_seconds is not None and seconds > p.recommended_max_seconds + _TIME_SLACK:
        return [Finding(
            "warn", p.id, "length",
            f"{seconds:.3f} s is over {duration_text(p.recommended_max_seconds)}: {p.recommended_why}",
        )]
    return []


def _rate_text(rate: float) -> str:
    return f"{rate:.3f}".rstrip("0").rstrip(".")


def _rates_text(rates: tuple[float, ...]) -> str:
    return ", ".join(_rate_text(r) for r in rates[:-1]) + f" or {_rate_text(rates[-1])}"


def _fps_findings(p: Platform, fps: float | None) -> list[Finding]:
    if fps is None:
        return []
    rate = _rate_text(fps)
    if p.fps_range is not None:
        low, high = p.fps_range
        if not low - _FPS_SLACK <= fps <= high + _FPS_SLACK:
            return [Finding("refuse", p.id, "frame rate", f"{rate} fps is outside the {low:g}-{high:g} fps {p.name} takes")]
    if p.fps_allowed and not any(abs(fps - r) < _FPS_SLACK for r in p.fps_allowed):
        return [Finding("refuse", p.id, "frame rate", f"{rate} fps isn't a rate {p.name} takes ({_rates_text(p.fps_allowed)})")]
    if p.fps_common and not any(abs(fps - r) < _FPS_SLACK for r in p.fps_common):
        return [Finding(
            "info", p.id, "frame rate",
            f"{rate} fps isn't one {p.brand} lists as common ({_rates_text(p.fps_common)}); others are accepted",
        )]
    return []


def _audio_findings(p: Platform, has_audio: bool | None) -> list[Finding]:
    if has_audio and p.audio == "none":
        return [Finding("refuse", p.id, "audio", f"it has an audio stream, and {p.name} takes the picture alone")]
    return []


def _file_findings(p: Platform, file_mb: float | None) -> list[Finding]:
    if file_mb is None:
        return []
    if p.max_file_mb is not None and file_mb > p.max_file_mb:
        return [Finding("refuse", p.id, "file size", f"{file_mb:.2f} MB is over the {p.max_file_mb:g} MB {p.name} takes")]
    if p.recommended_max_file_mb is not None and file_mb > p.recommended_max_file_mb:
        return [Finding(
            "warn", p.id, "file size", f"{file_mb:.2f} MB is over {p.recommended_max_file_mb:g} MB: {p.recommended_file_why}"
        )]
    return []


def _bitrate_findings(p: Platform, file_mb: float | None, seconds: float | None) -> list[Finding]:
    """The file's average bitrate -- its size over its length, the audio's
    few hundred kbps included -- against the video bitrates the platform's
    codec notes give. A warning either way: an encode can't always reach a
    floor, and a ceiling read from an API reference may not bind an upload
    from the app."""
    if file_mb is None or not seconds:
        return []
    mbps = file_mb * 8 / seconds
    if p.max_video_mbps is not None and mbps > p.max_video_mbps:
        return [Finding(
            "warn", p.id, "bitrate", f"{mbps:.1f} Mbps on average is over the {p.max_video_mbps:g} Mbps {p.name} takes"
        )]
    if p.min_video_mbps is not None and mbps < p.min_video_mbps:
        return [Finding(
            "warn", p.id, "bitrate", f"{mbps:.1f} Mbps on average is under the {p.min_video_mbps:g} Mbps {p.name} asks for"
        )]
    return []


def _loudness_findings(p: Platform, lufs: float | None) -> list[Finding]:
    if lufs is None or not math.isfinite(lufs) or p.loudness_lufs is None:
        return []
    target, delta = p.loudness_lufs, lufs - p.loudness_lufs
    reference = f"{target:g} LUFS ({p.loudness_source})"
    if abs(delta) < 0.5:
        text = f"delivered at {lufs:.1f} LUFS, within half a dB of {p.brand}'s {reference}: it plays as delivered"
    elif delta > 0:
        text = f"{p.brand} will turn this down by ~{delta:.1f} dB: delivered at {lufs:.1f} LUFS, it plays at {reference}"
    elif p.loudness_down_only:
        text = (
            f"{p.brand} won't turn this up: delivered at {lufs:.1f} LUFS, it plays {-delta:.1f} dB under "
            f"the {reference} it turns louder audio down to"
        )
    else:
        text = f"{p.brand} normalises to {reference}: delivered at {lufs:.1f} LUFS, it may turn this up by ~{-delta:.1f} dB"
    return [Finding("info", p.id, "loudness", text)]


# --------------------------------------------------------------------------
# kaleidophone platforms: the table, one entry in full, JSON, markdown
# --------------------------------------------------------------------------
COLUMNS = ("id", "kind", "size", "aspect", "length", "audio", "file limit", "loudness", "confidence", "checked")


def duration_text(seconds: float) -> str:
    """A limit as a person says it: 8 s, 3 min, 12 h."""
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds / 3600:g} h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds / 60:g} min"
    return f"{seconds:g} s"


def length_text(p: Platform) -> str:
    """The length a platform takes: `3 s to 15 min`, `up to 10 min`."""
    low, high = p.min_seconds, p.max_seconds
    if low is not None and high is not None:
        return f"{duration_text(low)} to {duration_text(high)}"
    if high is not None:
        return f"up to {duration_text(high)}"
    return "any length" if low is None else f"at least {duration_text(low)}"


def _cells(p: Platform) -> tuple[str, ...]:
    length = "-"
    if p.kind == "video":
        length = length_text(p)
        if p.recommended_max_seconds is not None:
            length += f" ({duration_text(p.recommended_max_seconds)})"
    file_limit = "-" if p.max_file_mb is None else f"{p.max_file_mb:g} MB"
    if p.recommended_max_file_mb is not None:
        file_limit = ("" if p.max_file_mb is None else f"{file_limit} ") + f"({p.recommended_max_file_mb:g} MB)"
    loudness = "-"
    if p.loudness_lufs is not None:
        loudness = f"{p.loudness_lufs:g} LUFS"
        if p.true_peak_dbtp is not None:
            loudness += f", {p.true_peak_dbtp:g} dBTP"
    return (
        p.id, p.kind, f"{p.width}x{p.height}", p.aspect, length, p.audio, file_limit, loudness, p.confidence, p.checked,
    )


LEGEND = (
    "length and file limit: the most the platform takes -- longer or bigger is refused; in brackets, "
    "where kaleidophone starts warning (`kaleidophone platforms ID` says why). loudness: the level the "
    "platform plays audio at."
)


def platform_table(entries: list[Platform] | None = None) -> str:
    """The registry as an aligned text table, then the legend."""
    rows = [COLUMNS, *(_cells(p) for p in (entries if entries is not None else _ENTRIES))]
    widths = [max(len(row[k]) for row in rows) for k in range(len(COLUMNS))]
    lines = ["  ".join(cell.ljust(widths[k]) for k, cell in enumerate(row)).rstrip() for row in rows]
    return "\n".join([*lines, "", *textwrap.wrap(LEGEND, 100)])


def _wrapped(label: str, text: str) -> list[str]:
    return textwrap.wrap(
        text, 100, initial_indent=f"{label:<12}", subsequent_indent=" " * 12, break_on_hyphens=False
    )


def _bounds_text(p: Platform) -> str | None:
    """The pixel bounds a platform publishes, in as few words as they take."""

    def span(low: int | None, high: int | None) -> str | None:
        if low is not None and low == high:
            return f"exactly {low} px"
        if low is not None and high is not None:
            return f"{low} to {high} px"
        if low is not None:
            return f"at least {low} px"
        return None if high is None else f"at most {high} px"

    if (p.min_width, p.max_width) == (p.min_height, p.max_height):
        both = span(p.min_width, p.max_width)
        return None if both is None else f"each side {both}"
    parts = ((span(p.min_width, p.max_width), "wide"), (span(p.min_height, p.max_height), "tall"))
    return ", ".join(f"{text} {what}" for text, what in parts if text)


def _spec_lines(p: Platform) -> list[tuple[str, str]]:
    """(label, text) for every spec field the entry has, in reading order."""
    size = f"{p.width}x{p.height} ({p.aspect}{'; ' + p.aspect_note if p.aspect_note else ''})"
    if p.sizes:
        size += "; also " + ", ".join(f"{w}x{h}" for w, h in p.sizes)
    bounds = _bounds_text(p)
    if bounds:
        size += f"; {bounds}"
    if p.aspect_fixed:
        size += "; no other shape"
    lines = [("size", size)]
    if p.kind == "video":
        length = length_text(p)
        if p.recommended_max_seconds is not None:
            length += f"; warns over {duration_text(p.recommended_max_seconds)}: {p.recommended_why}"
        lines += [("length", length), ("frame rate", p.fps or "not published")]
    lines.append(("audio", p.audio))
    file_limit = f"at most {p.max_file_mb:g} MB" if p.max_file_mb is not None else "no limit published"
    if p.recommended_max_file_mb is not None:
        file_limit += f"; warns over {p.recommended_max_file_mb:g} MB: {p.recommended_file_why}"
    lines.append(("file", file_limit))
    if p.loudness_lufs is not None:
        loudness = f"{p.loudness_lufs:g} LUFS"
        if p.true_peak_dbtp is not None:
            loudness += f", true peak {p.true_peak_dbtp:g} dBTP"
        lines.append(("loudness", f"{loudness} ({p.loudness_source})"))
    if p.safe_area is not None:
        a = p.safe_area
        lines.append(("safe area", f"keep clear of top {a.top}, bottom {a.bottom}, left {a.left}, right {a.right} px"))
    lines += [
        ("formats", ", ".join(p.formats) or "none: not an upload"),
        ("codec", p.codec_notes),
        ("notes", p.notes),
        ("confidence", f"{p.confidence}, checked {p.checked}"),
    ]
    return lines


def describe(p: Platform) -> str:
    """One entry in full: every spec field, the notes, the sources."""
    head = f"{p.id} -- {p.name} ({p.kind})"
    lines = [head, *(_wrapped("aliases", ", ".join(p.aliases)) if p.aliases else [])]
    for label, text in _spec_lines(p):
        lines += _wrapped(label, text)
    lines.append("sources")
    lines += [f"  {url}" for url in p.sources]
    return "\n".join(lines)


def to_json(entries: list[Platform] | Platform | None = None) -> str:
    """The registry (or one entry) as JSON."""
    if isinstance(entries, Platform):
        return json.dumps(entries.to_dict(), indent=2)
    return json.dumps([p.to_dict() for p in (entries if entries is not None else _ENTRIES)], indent=2)


MARKDOWN_HEAD = """\
# Platforms

<!-- Generated by `kaleidophone platforms --markdown` from src/kaleidophone/render/platforms.py.
     Don't edit it by hand: change the registry, then regenerate. tests/test_platforms.py fails
     when this file is out of date. -->

What each platform asks for, as `kaleidophone deliver` delivers to it and
`kaleidophone platforms` prints it. Every number is **cited**: each entry
lists its sources -- the platform's own documentation where it publishes
any -- its confidence (`official`: the platform's own pages or API reference;
`third-party`: guides, press or measurements, because the platform publishes
nothing) and the date it was checked. Platforms change these without notice:
check the date before you trust one.

Where the sources disagree, the safe value is the hard limit and the rest
is in the notes. **Length** and **file limit** are the most the platform
takes -- a delivery sheet that asks for more is refused; in brackets, where
`deliver` starts warning, and why is under the entry. **Loudness** is the
level the platform plays audio at; `deliver` reports how far each delivered
file sits from it.

kaleidophone makes the files and stops there: nothing here talks to a
platform ([ADR-0006](decisions/0006-the-release-pack.md)).
"""


def _md(text: str) -> str:
    """Text for a markdown table cell."""
    return text.replace("|", "\\|")


def entry_markdown(p: Platform) -> str:
    """One entry as a section of docs/PLATFORMS.md."""
    also = f"; also `{'`, `'.join(p.aliases)}`" if p.aliases else ""
    lines = [f"## {p.id}", "", f"**{p.name}** ({p.kind}){also}", ""]
    lines += [f"- **{label}:** {text}" for label, text in _spec_lines(p)]
    lines += ["", "Sources:", "", *(f"- <{url}>" for url in p.sources)]
    return "\n".join(lines) + "\n"


def platforms_markdown() -> str:
    """docs/PLATFORMS.md: the table, then every entry in full."""
    lines = [MARKDOWN_HEAD, "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(_md(cell) for cell in (f"[{p.id}](#{p.id})", *_cells(p)[1:])) + " |" for p in _ENTRIES]
    return "\n".join(lines) + "\n" + "".join(f"\n{entry_markdown(p)}" for p in _ENTRIES)
