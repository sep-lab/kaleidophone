# The creative brief: field reference

The full schema lives in `src/kaleidophone/timeline/schema.py` (pydantic — it's
the actual validator, this doc is a guide to it, not a duplicate source of
truth). `examples/love/brief.yaml` and `examples/demo/generate_fixtures.py`
are worked examples.

Two more files kaleidophone reads have their own sections at the end:
[the delivery sheet](#the-delivery-sheet-kaleidophone-deliver), which cuts
every deliverable out of one silent render, and
[song packs](#song-packs-kaleidophone-envelope-canvas), the analysed song
that canvas pieces and frame programs react to.

```yaml
song:
  title: "Song Title"
  artist: "Artist Name"        # optional
  audio_path: "/path/to/song.wav"   # local -- never commit this file, see AGENTS.md
  bpm: 129.0                   # optional -- override if librosa's auto-detect is wrong

stations:
  - name: amber-room           # referenced by name from sections[].station -- must be unique
    description: "Warm interiors, lamplight..."   # prose; also used as caption mood words, see promo/plan.py
    media_dir: "/path/to/photos"     # local folder -- never commit, see AGENTS.md
    temperature: 0.55          # -1 (cool) .. 1 (warm) -- also the curation heuristic's primary signal
    saturation: 1.05           # 0 .. 2
    contrast: 1.05             # 0 .. 2
    grain: 0.18                # 0 .. 1
    vignette: 0.28             # 0 .. 1
    duotone: ["#1a0f06", "#f2b25c"]   # optional [shadow, highlight] -- also sets the curation target hue

sections:
  - name: PENDULUM
    start: 0.0                 # seconds
    end: 61.0
    station: amber-room        # must match a stations[].name
    cut_density: every_2_beats # every_beat | every_2_beats | every_4_beats |
                                # every_bar | every_2_bars | every_4_bars | static
    effects: [grain, vignette] # kaleidoscope | strobe | invert_flash |
                                # freeze_on_peak | grain | scanlines | halation |
                                # vignette | zoom_breathe | static_noise
                                # (duotone is a station property, not an effect)
                                # see docs/CREATIVE-GUIDE.md for what each does
    seed: 0                    # asset-shuffle seed -- same seed, same edit, every re-render
    framing:                   # optional -- only matters when output.aspect differs
      mode: crop               #   from the source material's shape
      x: 700                   # fill (default) | crop (needs x) | window (needs width)

output:
  resolution: [1280, 720]      # see docs/ARCHITECTURE.md, "Why 1280x720 by default"
  fps: 24
  aspect: "9:16"               # optional -- 16:9 | 9:16 | 1:1 | 4:5. Setting this alone
                                # picks the canonical size (9:16 -> 1080x1920)
  window: [161.0, 219.7]       # optional -- render only this stretch of the song,
                                # rebased to start at 0. One brief -> master AND cutdown
  encode:                      # optional -- every default reproduces the previous
    crf: 22                    #   hardcoded behaviour, so omitting this changes nothing
    preset: medium             # ultrafast .. veryslow
    maxrate: "4500k"           # bitrate ceiling; must be set together with bufsize
    bufsize: "9M"
    color: bt709               # optional -- tags colourspace/primaries/trc together
    audio_bitrate: "192k"
    audio_rate: 48000          # optional -- output sample rate
  thumbnail_count: 3
  cover_size: 3000              # cover art is square, cover_size x cover_size
  cover_station: null           # optional -- defaults to the station of the section
                                 # containing the song's single loudest instant
  teasers:
    - name: teaser_drop
      duration: 15.0
      aspect: "9:16"             # 9:16 | 1:1 | 16:9
      source_start: 205.0        # optional -- defaults to the middle of the track

overlays:                       # optional -- timed text cards burned into the render
  - id: title                   # unique within the brief; also names the rendered PNG
    at: [0.25, 1.55]            # [start, end] in seconds, on the OUTPUT timeline
    y: 0.845                    # vertical centre of the block, fraction of frame height
    align: center               # left | center | right
    line_gap: 0.012             # fraction of frame height
    shadow: true                # blurred black copy behind the text (default on)
    lines:
      - text: "[the night track talks]"
        font: typewriter        # mono | mono-bold | typewriter | display |
                                 # display-medium | persian | persian-bold |
                                 # path:/abs/font.ttf
        size: 0.028             # FRACTION OF FRAME HEIGHT, not pixels
        color: "#eeeeea"
        opacity: 1.0
        tracking: 0.0           # letter-spacing, fraction of frame height
        rtl: null               # leave unset -- direction is detected from the script

promo:                          # optional -- omit to skip promo-pack generation content that needs it
  handles: ["@collaborator1", "@collaborator2"]   # scrub before committing any brief, see AGENTS.md
  teaser_cadence_days: [-7, -3, -1]   # T-7 / T-3 / T-1, relative to release
```

## Validation

- Every `sections[].station` must match a `stations[].name` — `CreativeBrief`
  refuses to construct otherwise (a clear `ValueError`, not a silent
  fallback).
- Every `sections[].end` must be after its `start`.
- `compose()` separately refuses (also loudly) to build an EDL for a section
  whose station received zero curated assets — see
  [ADR-0004](decisions/0004-default-mode-and-auto-curation.md) for why
  that's the right place for this check to live.
- Each `duotone` entry must be a 6-digit hex color (`#1a0f06`). These are
  interpolated into an ffmpeg filter string, so the format is enforced rather
  than trusted — see [SECURITY.md](../SECURITY.md).
- Sections must **tile the song end to end**: the first starts at `0.0`, and
  each subsequent `start` equals the previous `end`. The renderer
  concatenates cuts, so a gap doesn't render as a gap — it slides every later
  cut off the beat. `EDL` refuses such a timeline rather than rendering it.
- Every cut boundary is snapped to the `1/fps` grid, so a section shorter
  than one frame is refused too. See
  [docs/ARCHITECTURE.md](ARCHITECTURE.md), "Frame-accurate cuts".
- `output.aspect` and `output.resolution` must agree. Setting `aspect` alone
  picks the canonical resolution; setting both at the *same shape* (a 4K
  vertical master, say) is fine; setting both at different shapes is refused
  rather than silently picking a winner.
- `output.window` must be ordered and non-negative, and must contain at least
  one cut. It is snapped to the frame grid *before* the timeline is rebased,
  so a windowed edit stays exactly as frame-accurate as a full one.
- `encode.maxrate` and `encode.bufsize` must be set together — x264 ignores a
  ceiling with no buffer to rate-control against, which looks like the setting
  silently not working.
- Bitrate fields must look like bitrates (`4500k`, `9M`, `192k`). Like
  `duotone`, these are interpolated into an ffmpeg argv.
- `framing.mode: crop` requires `x`; `framing.mode: window` requires `width`.
- Overlay ids must be unique. They name the rendered card file, so a repeat
  would silently overwrite the earlier one — the render would succeed and one
  card would simply never appear.
- Every `overlays[].at` must be ordered and non-negative, and each overlay
  needs at least one line.
- Overlay colours must be 6-digit hex, same as `duotone`.
- `tracking` cannot be combined with right-to-left text: drawing a shaped run
  glyph by glyph breaks the joins between letters.

## Framing: fitting a source frame into a different-shaped output

Only relevant when `output.aspect` differs from the source material's shape.
Pulling a 9:16 frame out of 16:9 footage discards two thirds of the width, and
*which* two thirds is a creative decision — the subject is rarely centred.
There is no computation that gets this right, which is why it's a field.

| mode | What it does | Needs |
|---|---|---|
| `fill` | Scale to cover, centre-crop. The default, and what kaleidophone did before framing existed. | — |
| `crop` | A full-height slice of the source starting at `x` source pixels. | `x` |
| `window` | Shrink the whole frame to `width` output pixels and pad it onto black at `y_center`. Reads completely differently from a full-bleed crop. | `width` |

`crop`'s width is computed by ffmpeg from the real input height, so one brief
works across sources of different resolutions.

## Overlays: text burned into the picture

Two things about this are deliberate and worth knowing before you write a card.

**Sizes are fractions of the frame height, never pixels.** A card designed
against a 1080×1920 delivery has to still be right when the same brief renders
at 2160×3840. A pixel size would come out half as large and nothing would say
so. `size: 0.028` is ~54px at 1920 tall.

**Right-to-left text is shaped, not reversed.** Direction is detected from the
text's own script, so a Persian line needs no flag. Under the hood Pillow
delegates to libraqm/HarfBuzz. If you are tempted to reach for
`arabic-reshaper` or `python-bidi`: don't. They reorder characters rather than
shaping them, which produces broken letterforms that look fine to anyone who
cannot read the script and are obviously wrong to anyone who can. kaleidophone
refuses to render RTL text without real shaping rather than emitting that
quietly.

Fonts ship with the package (`src/kaleidophone/overlay/fonts/`, all SIL OFL) for
the same reason: a font resolved from a system path renders differently on
every machine, which breaks the promise that a brief reproduces.

A line wider than the frame prints a warning naming a `size` that would fit —
cards are drawn blind, so otherwise you find it by watching the finished render.

## Where a brief comes from

Two paths, same schema:

- **Hand-authored** — write the YAML above directly. Full control.
- **`kaleidophone auto <song> <media_dir>`** — generates one (`generated_brief.yaml`)
  from audio analysis and heuristic curation, no manual authoring. Edit the
  output and re-run with `kaleidophone run` for anything auto-mode didn't get
  right — see
  [ADR-0004](decisions/0004-default-mode-and-auto-curation.md) and
  `docs/CREATIVE-GUIDE.md`, "Default mode vs. authored briefs".

## What never belongs in a committed brief

`audio_path`, `media_dir`, and `promo.handles` are the three fields most
likely to leak something private (a local path with your username in it, or
a real collaborator's handle). `examples/` briefs either point at
`examples/demo/`'s generated fixtures or have those fields genericized —
see [ADR-0003](decisions/0003-public-framework-private-assets.md) and
`docs/case-studies/love.md`'s notes on what was scrubbed from the real one.

## The delivery sheet (`kaleidophone deliver`)

A delivery sheet cuts every deliverable of a release out of **one silent
render** and muxes the master under each: the picture is stream-copied, so
every cut is frame-identical to the film, and the audio gets **one gain for
the whole master**, so every cut keeps the song's own dynamics, with its
true peak measured on the delivered file. It is its own file rather than a
block in the brief because it describes cuts of a *finished* render that may
not have come from a brief at all — a canvas piece, a frame program — and
because it usually runs on a different machine: the one that holds the master
([ADR-0007](decisions/0007-three-engines-one-contract.md)). The validator is
`src/kaleidophone/render/deliver.py` (pydantic); its module docstring has the
measurements behind each rule.

```
kaleidophone deliver sheet.yaml [-o DIR] [--dry-run]
```

```yaml
silent: _work/full_silent.mp4    # the ONE silent render every cut comes from -- required unless every
                                 #   cut has `endings`. t0, dur, video_from and at are on its clock
audio: Song.wav                  # the master -- required unless every cut is `audio: none`. Relative
                                 #   silent/audio/card paths resolve against this sheet's own directory
silent_start: 0                  # song time (s) of the render's first frame (default 0; may be negative)
fps: 24                          # the silent render's frame rate (default 24; > 0, <= 240)
defaults:                        # optional -- shown here with its defaults
  audio_bitrate: 256k            # AAC bitrate: a number with an optional k/M suffix
  sample_rate: 48000             # output sample rate, 8000 .. 192000
  ceiling_dbtp: auto             # true-peak ceiling for every delivered file: auto, or a number <= 0
gain: {mode: loudness, target_lufs: -14, limiter_dbfs: -2.0}
                                 # see "Gain" below. Default: {mode: fixed, db: 0}
cuts:                            # at least one
  - out: SONG_reel_1080x1920.mp4 # required -- a relative path inside the output directory,
                                 #   ending in .mp4, .m4v or .mov
    t0: 0                        # required -- seconds, >= 0, on the fps frame grid
    dur: 72.25                   # required -- seconds, > 0; the picture is round(dur * fps) frames
    fade_in: 0.005               # audio fade-in, seconds (default 0.005; 0 for none)
    fade_out: 0.06               # audio fade-out, seconds (default 0.015; 0 for none)
  - {out: SONG_story_16s.mp4, t0: 26.25, dur: 16, fade_in: 0.25, fade_out: 1.2}
  - out: SONG_reel_card.mp4
    t0: 51
    dur: 131
    card: _work/card_silent.mp4  # optional -- a separately rendered card covering t0 .. video_from
    video_from: 53               # required with card -- the film resumes from its keyframe here
  - {out: SONG_canvas.mp4, t0: 51, dur: 8, audio: none}   # no audio stream: a Spotify Canvas
  - {out: SONG_reel_e.mp4, t0: 51, dur: 16, endings: _work/reel.variants.json}
                                 # one file per ending: SONG_reel_e.<ending>.mp4 -- see "Endings"
check: true                      # count frames, duration and size of what was written (default true)
```

A sheet that delivers to platforms says so per cut, and names its files from
the release's `title` -- see "Platforms", "Names", "Covers" and "The
manifest" below:

```yaml
title: Same As You               # names the manifest, the covers and every cut without `out`
slug: same-as-you                # optional: the title as file names start (default: the title,
                                 #   lowercased, hyphens for everything but letters and digits)
size: 1080x1920                  # the silent render's frame size, WxH -- required with platform(s)
silent: _work/full_silent.mp4
audio: Song.wav
cuts:
  - name: loop                   # with the title, names the files: same-as-you.loop.<platform>.mp4
    t0: 51
    dur: 8
    platforms: [ig-reel, tiktok, youtube-short, canvas]   # one file per platform; ids or aliases
  - {name: film, t0: 0, dur: 182, platform: youtube-video, reframe: pad-blur}
                                 # reframe: pad-blur | pad-color (+ pad_color: '#rrggbb') | crop --
                                 #   required when the platform's shape isn't the render's
covers:                          # optional
  master: _work/cover_3000.png   # a square image, as large as the largest cover drawn from it
  portrait: _work/cover_9x16.png # optional: the 9:16 covers come from it
  background: '#ffffff'          # optional: what real transparency is flattened onto (default white)
  platforms: [distributor-cover, spotify-cover, apple-music-cover, soundcloud-artwork,
              soundcloud-header, youtube-thumbnail, instagram-reel-cover]
```

A render that doesn't start at the top of the song says where it does, and
every cut's audio — card cuts included — is read from `silent_start + t0`:

```yaml
silent_start: 43.89                          # the reel's frame 0 is song time 43.89 s
cuts: [{out: SONG_reel.mp4, t0: 0, dur: 60}] # picture from frame 0, audio from 43.89 s
```

`silent_start` is negative for a render that starts *before* the song — as
when `kaleidophone master-check` finds that a new master sits earlier than
the one the picture was cut to (its head trimmed): its `offset` verdict
prints the `silent_start` that absorbs the shift, either way. The audio's
head is then padded with silence until the song begins: with `silent_start: -0.5`, a cut at `t0: 0` opens on
half a second of silence and then the song from its first sample. A cut whose
audio would lie entirely before the song is refused (`audio: none` delivers
it silent).

### Gain: one per master, three ways

The master is measured once, whole (loudnorm's measuring pass: integrated
loudness and true peak), and every cut is encoded with the same gain — and,
in `loudness` mode, the same limiter. A story cut from a sparse intro keeps
the level it has in the song instead of being pushed up to the target on its
own. The whole master rather than the film cut: it is what a streaming service
measures, it doesn't change when a cut is added to the sheet, and a render
that starts partway into the song gets the song's gain.

| `mode` | Fields (default; range) | For | What it does |
|---|---|---|---|
| `fixed` | `db` (0; −60 .. 24) | a master whose gain you already know | clean gain, no limiter: a second limiter on a finished master is a second master. Nothing to step, so a delivered file over the ceiling is an error |
| `loudness` | `target_lufs` (−14; −40 .. 0), `limiter_dbfs` (−2.0; −24 .. 0), `step_db` (0.5; > 0 .. 6), `max_steps` (12; 0 .. 40) | an unlimited pre-master, including a 32-bit float file that sits above 0 dBFS | gains the master's integrated loudness to `target_lufs` (the loudness *before* the limiter: a limiter working hard takes some off), then limits at `limiter_dbfs`, oversampled 4× (at 192 kHz) so it sees the peaks between samples, with a 200 ms release and its 4 ms lookahead delay compensated ([TECHNIQUES #42](TECHNIQUES.md#42-float-pre-master-check)). The guard steps the limiter down, never the gain |
| `auto` | `start_db` (0; −60 .. 24), `step_db` (0.5; > 0 .. 6), `max_steps` (12; 0 .. 40) | a finished, limited master | clean gain from `start_db`; the guard steps the gain down ([#18](TECHNIQUES.md#18-aac-true-peak-guard), [#50](TECHNIQUES.md#50-aac-guard-per-master)) |

### The true-peak guard, in every mode

Every delivered file is measured (`ebur128=peak=true`, on the AAC as
written). While one is over the ceiling, the master's setting steps down by
that file's overshoot — in whole `step_db` steps, one at least and 3 dB at
most in one round, `max_steps` in all — and **every** cut is encoded again,
so they keep sharing one setting. `deliver` exits with an error naming the
files (which are written) when a `fixed` delivery is over the ceiling or the
guard runs out of steps.

`defaults.ceiling_dbtp: auto` is −1 dBTP, or −2 dBTP when the delivery is
planned louder than −14 LUFS: the master's loudness plus `db` or `start_db`,
or `target_lufs` in `loudness` mode. The numbers are Spotify's: it normalises
to −14 LUFS, asks for a true peak under −1 dBTP, and under −2 dBTP for masters
louder than −14 LUFS, because "louder tracks are more susceptible to extra
distortion when encoded for streaming"
([cited](https://support.spotify.com/us/artists/article/loudness-normalization/)).
Instagram and TikTok document no loudness normalisation (nothing in their
help centres as of September 2026), so a loud master stays loud there. A
number instead of `auto` is used as given, with a warning if it is above −2
on a delivery louder than −14 LUFS.

### Fades

Every cut with audio fades in over 5 ms and out over 15 ms unless the sheet
says otherwise: click guards, not fades anyone hears. `0` is allowed, and then
`deliver` reads the master at that edge and warns unless it is near silence
(under −60 dBFS, gain included, within 10 ms of the edge) — an unfaded edge
clicks, and on a platform that loops the cut it clicks every loop.

### The card

With `card`, the picture is the card segment followed by the film from its
keyframe at `video_from`, while the audio runs from `t0` — so a reel opens on
a title card and the full film never carries one
([TECHNIQUES #16](TECHNIQUES.md#16-signature-card)). The card is a render of
its own, made with the film's encoder settings so the two concatenate without
a re-encode, and it must be exactly `round((video_from − t0) × fps)` frames:
48 for the example above at 24 fps. Only the picture is concatenated; the
audio runs on unbroken underneath.

### Endings

A cut with `endings` delivers one finished file per ending instead of one
file: the body and that ending joined by stream copy (the concat demuxer, as
the card is), the master muxed over the whole cut at the master's one gain,
measured on every file. The artist chooses — or posts them all as trial reels
and keeps the one people watch to the end. The picture comes from the
endings, not from `silent`; `card` and `video_from` still put a card in
front, the body resuming from its keyframe at `video_from`.

```yaml
# from render.mjs <piece> --endings <axis> (preferred): its manifest names the body and every ending
- {out: SONG_reel.mp4, t0: 51, dur: 16, endings: _work/reel.variants.json}
# or listed by hand: the body runs t0..at, every ending at..t0+dur
- out: SONG_reel.mp4
  t0: 51
  dur: 16
  body: _work/reel.body.mp4
  at: 61                         # on the render's clock, on the frame grid
  endings:
    - {name: rain, file: _work/reel.ending-rain.mp4}
    - {name: door, file: _work/reel.ending-door.mp4}
```

Each ending is written as `<out stem>.<name><suffix>` (`SONG_reel.rain.mp4`),
and the cut's contact sheet as `<out stem>.endings.jpg`: one row per ending,
top to bottom — the last body frame, a mark at the join, then 6 frames spread
over the ending, its first and last included — labelled with the names where
ffmpeg's `drawtext` works; where it doesn't, the sheet is unlabelled and the
report says so. A manifest's `t0` and `at` are song seconds, so its `t0` must
be the cut's song time (`silent_start + t0`, within half a frame), its `dur`
the cut's, its `fps` the sheet's, its body `round((at − t0) × fps)` frames and
every ending the rest of the cut; its files are names next to it, and keys
beyond these (its `stream` block included) are ignored.

### Platforms

`platform: <id>` on a cut delivers it to that platform's spec;
`platforms: [<id>, ...]` delivers one file per platform. The ids, their
aliases (`ig-reel` for `instagram-reel`, `canvas` for `spotify-canvas`) and
every number behind them are in [PLATFORMS.md](PLATFORMS.md), generated
from `src/kaleidophone/render/platforms.py` -- `kaleidophone platforms`
prints the table, `kaleidophone platforms <id>` one in full, with its
sources, how sure they are and when they were checked. Each platform's file:

- **The picture.** Stream-copied when the render (`size`) is a size the
  platform documents -- 1080x1920 for a Reel, any of 2160p to 720p for a
  YouTube video. Otherwise scaled once, with Lanczos, to the platform's size
  in the render's shape (a square render to a 1080x1080 Short) and encoded
  with x264 at CRF 18 under the platform's ceiling (Instagram's 25 Mbps;
  YouTube gets its closed GOP of half the frame rate and two B-frames;
  Apple's motion art, which asks for 45-100 Mbps, an average of 72.5 with no VBV
  buffer, because x264 with one didn't repeat its bytes at 3840x3840) -- into
  an intermediate that every round of the true-peak guard stream-copies, so
  the picture is encoded once however many rounds the audio takes. A
  platform of another shape needs `reframe`:

  | `reframe` | the picture |
  |---|---|
  | `pad-blur` | whole, centred over a copy of itself that fills the frame -- the common "blurred sides" -- blurred by 6 % of the frame's longer side, darkened and half desaturated, so it reads as the picture's light around it rather than a second picture |
  | `pad-color` | whole, on bars of `pad_color` (default `#000000`) |
  | `crop` | scaled to cover the frame, the centre kept -- the report says how much of the render that is |

  Without it the cut is refused, with the three to choose from; with it and
  nothing to fit, too. A picture drawn larger than it was rendered is a
  warning: a 1080x1920 render padded into YouTube's 3840x2160 is drawn
  1216x2160, enlarged 1.13x.
- **The length**, its frames at the sheet's `fps`, against the platform's
  limits: past the most it takes (a Spotify Canvas, 8 s) or under the least
  (3 s) is refused; past a softer limit it is delivered with a warning that
  says why -- Instagram recommends only Reels under 3 min to non-followers
  (it takes 15), YouTube blocks a Short over 1 min with an active Content ID
  claim.
- **The frame rate**, against the range the platform takes (Instagram and
  TikTok: 23-60) or the rates (Apple's motion art: 23.976 to 30): refused
  outside them; a rate YouTube doesn't list as common is noted.
- **The audio.** A platform that takes none (`spotify-canvas`, Apple's motion
  art) gets a file with no audio stream, whatever the cut says; the cut's
  other platforms keep the master. Still one gain per master: every file
  with audio shares it.
- **After it is written**, the file itself is held to the platform: its size,
  length, frame rate and audio as ffprobe reads them, its size on disk
  against the platform's limit (refused over it -- the file is written and
  `deliver` exits with an error; warned over a softer one, like the ~72 MB
  third parties report for TikTok's Android app), its average bitrate
  against the range the platform's codec notes give (a warning: Instagram's
  25 Mbps, which a stream-copied render can exceed; Apple's 45 Mbps floor),
  and its loudness against the level the platform plays at: "YouTube will
  turn this down by ~5.0 dB". That last is information, not a gain.

Every finding is one line -- `refuse`, `warn` or `info`, the file, the
platform, the rule -- in the report and in the manifest.

### Names

A cut with `out` keeps it: with `platform`, the file is `out`; with a list
of `platforms`, `<out stem>.<platform><suffix>` for each; an ending adds
`.<ending>` after either. A cut without `out` gives `name`, and its files
are `<title>.<name>[.<platform>][.<ending>].mp4` -- `same-as-you.loop.tiktok.mp4`
-- with the title made a file name: lowercased, every run of anything but a
letter or a digit one hyphen (a Persian title keeps its letters). A title
with no letter or digit in it, `( - )`, needs `slug`.

### Covers

`covers` makes every cover in `platforms` from one square `master`, with
Pillow -- no ffmpeg, so a sheet of covers alone (`title` and `covers`, no
cuts) needs neither a render nor a master WAV:

- each at its platform's size (`kaleidophone platforms <id>`), downscaled
  with Lanczos and never enlarged: a master smaller than the largest size
  it is drawn at is refused before anything is written (Spotify's rule: no
  upscaling) -- 3000 px is enough for every cover in the registry;
- a square platform's from the master; another shape's is the master
  centred over a copy of itself, blurred, darkened and desaturated as
  `reframe: pad-blur` does a video (a 16:9 YouTube thumbnail, a 9:16
  Reel cover, a 3:4 carousel image) -- or, for the 9:16 covers, the
  `portrait` scaled, when there is one (9:16, as large as its largest
  cover); SoundCloud's 2480x520 header is the master's centre band, with a
  warning to check the crop (SoundCloud crops it again on small screens);
- sRGB, 8 bits a channel, with no embedded profile and no EXIF (Spotify's
  rule): a profile is applied and removed, an EXIF orientation applied to
  the pixels, real transparency flattened onto `background` (white unless
  the sheet says) -- each said in the report. An alpha channel that is
  opaque everywhere, as a canvas piece's cover has, is dropped without a
  word: there is nothing to flatten;
- a JPEG, 4:4:4, at quality 95 (100 for Spotify and Apple, which ask for
  lossless or 100 %), stepped down by 5 until it is under the platform's
  file limit (SoundCloud's 2 MB); still over it at quality 50, it is written
  and refused.

`<title>.cover.<platform>.jpg` each. An Instagram Reel cover brings
`<title>.cover.instagram-grid-thumbnail.jpg` with it: what the 3:4 profile
grid shows of it, the centre 1080x1440 -- a preview, not an upload.

### The manifest

Every delivery writes `<title>.delivery.json` (`delivery.json` with no
title) next to its files: every artifact -- its file, cut, platform, ending,
how its picture was made, what was planned (size, fps, frames, seconds,
audio) and what was measured on the file (size, fps, frames, seconds,
duration, audio, LUFS, dBTP, bytes; a cover's size, bytes and JPEG
quality), and its findings -- the master's loudness, true peak, gain and
ceiling, a count of the findings by level, and every platform's spec once,
by id. `--dry-run`'s script writes it as planned, nothing measured.

### Validation

When the sheet is read, before anything runs:

- Unknown keys are errors, at every level. A typo such as `fadeout:` for
  `fade_out:` would otherwise ship a story with a click at its end.
- `out` must be a relative path inside the output directory — no absolute
  path, no `..` — ending in `.mp4`, `.m4v` or `.mov`, and no two cuts may write
  the same file (`x.mp4` and `./x.mp4` are the same file).
- `silent`, `audio`, `card` and `out` can't contain control characters: they
  reach argv, a concat list and `--dry-run`'s shell script.
- `fade_in + fade_out` can't be longer than `dur`; a cut with `audio: none`
  can't have fades (it has no audio to fade).
- `card` and `video_from` go together, and `video_from` must fall inside the
  cut: `t0 < video_from < t0 + dur`.
- `t0` and `video_from` must be on the `fps` frame grid (within 0.01 of a
  frame); the error names the two nearest frames. A stream-copied cut can
  only start on a frame — and on a keyframe at that.
- `endings` is a manifest path or a non-empty list of `{name, file}`; a list
  needs `body` and `at` (`t0 < at < t0 + dur`, on the frame grid, after a
  card's `video_from`), a manifest takes neither. A name is a plain name — no
  `/` or `\`, no leading `.`, no surrounding spaces — and no two endings of a
  cut may differ only by case. No ending's file or contact sheet may be one
  another cut writes.
- `silent` is required unless every cut has `endings`;
  `audio` is required unless every cut is `audio: none` or goes only to
  platforms that take no audio; `silent_start` is
  any finite number; `ceiling_dbtp` is `auto` or a number at or under 0;
  `audio_bitrate` must look like a bitrate, and there must be at least one
  cut -- or `covers`.
- A cut has `out` or `name` (a plain name, as an ending's); `title` is
  required when a cut has no `out` or there are `covers`, and `slug` when the
  title has no letter or digit to start a file name with.
- `platform` and `platforms` don't go together; each id or alias is a video
  platform the registry has (an unknown one is refused with the nearest, an
  image one pointed at `covers`), listed once. `size` (`WxH`) is required
  when a cut goes to a platform. `reframe` needs a platform, and `pad_color`
  (`#rrggbb`) needs `reframe: pad-color`; fades on a cut whose platforms
  take no audio are refused, as they are with `audio: none`.
- `covers.platforms` are image platforms, listed once; `portrait` needs a
  9:16 one among them; `background` is `#rrggbb`.
- Then every file is held to its platform as planned, and all that one won't
  take is refused at once: a shape with no `reframe` (or a `reframe` with
  nothing to fit), a length past its limits, a frame rate it doesn't take.
  `--dry-run` refuses the same.

When `deliver` runs, before any encoding, reporting every problem at once:

- every input exists (the master only if a cut has audio; the covers' master
  and portrait);
- the silent render, a card and an ending's body are the sheet's `size`, when
  it gives one;
- the covers' master is square and as large as the largest cover drawn from
  it, and the portrait 9:16 and as large as its largest cover -- and each is
  an image Pillow opens: one over its 178,956,970-pixel limit (where it
  suspects a decompression bomb) is refused in a line, like a file that
  isn't an image;
- no cut ends past the end of the silent render (by more than a frame), no
  cut's audio — at `silent_start + t0 + dur` — past the end of the master (by
  more than 0.05 s), and no cut's audio lies entirely before the song;
- the silent render has a keyframe where each cut's film starts — `t0`, or
  `video_from` for a card cut. If one is missing the sheet is refused, with
  the `-force_key_frames` list to re-render with;
- each card has the frame count its window needs; a wrong one would land the
  film off its audio;
- a cut that ends between keyframes is delivered with a warning: `-frames:v`
  counts packets in decode order, so its last frame can come out of order. A
  keyframe forced at the end too makes it exact;
- a cut's endings fit it: a manifest that disagrees with its cut is refused,
  one line per mismatch (frame rate, song time, length, the join, any part's
  frame count), and so is a part whose file has the wrong number of frames,
  doesn't start on a keyframe (nor the body at `video_from`, behind a card),
  or isn't the same encode as the rest — codec, profile, level, pixel format,
  size, frame rate, time base, aspect — or isn't at the sheet's `fps`. Parts
  whose stream headers differ (another encoder setting, an x264 CRF) are
  joined with a warning: ffmpeg decodes the join, a strict player may not.

Without ffprobe these checks are best-effort.

### What it writes

- A line for the master first: its loudness and true peak, the gain every
  cut gets, and the ceiling. Then each `out`, under `-o DIR` (default: the
  sheet's own directory): the picture stream-copied and bounded by
  `-frames:v`, never `-t`; the audio windowed, gained (limited), faded and
  encoded to AAC; and on every file,
  `-dn -sn -map_metadata -1 -map_chapters -1 -movflags +faststart`. A cut with
  `audio: none` has no audio stream. A cut with endings writes each ending
  and its contact sheet instead; a cut with platforms, a file per platform
  (per ending) -- the contact sheet from its first platform's. Card, endings
  and reframed-picture intermediates go in
  `.kaleidophone-cache/deliver/` under it and are removed afterwards.
- Each cover, `wrote <file> (<size>, <MB>, JPEG quality <q>; <platform>)`.
- With `check: true`, a table measured on the files themselves: frames counted
  against frames expected, duration, integrated LUFS, true peak, size and the
  gain (and limiter) used — a row per ending, then a line per contact sheet.
  `!frames` and `!peak` flag a row. The true peak is guarded whatever `check`
  says. Then every finding, `<level>: <file> (<platform>): <what>`; a file a
  platform won't take as written (`refuse`) makes `deliver` exit with an
  error after writing everything, the way a peak over the ceiling does.
- The manifest, `<title>.delivery.json` (above), last.
- With `--dry-run`, nothing is run: the same delivery is printed as a POSIX sh
  script — the master measured once, the guard's rounds, the ceiling worked
  out the same way, and the limiter's delay taken back whichever ffmpeg it
  finds — with the `-force_key_frames` list in its header. Run where the
  master is, it writes the same files as `deliver` (byte-identical, measured
  with ffmpeg 6.1 and 4.2.2 on synthetic masters). It needs neither the render
  nor the WAV to print, so it is also how to plan a render's keyframes — but
  a cut with endings reads its variants manifest (not the render). From
  a relative sheet path the script holds no absolute paths; run it from the
  directory kaleidophone ran in. No path in the sheet can expand or run
  anything in it, and no ffmpeg in it reads the terminal (`-nostdin`), so it
  can run inside a `while read` loop. A platform's reframed picture is the
  same x264 command line in both (measured with ffmpeg 6.1 on a synthetic
  render: a 4K pad-blur YouTube cut and four stream-copied platform files,
  byte-identical to `deliver`'s). The script writes the planned manifest
  (a quoted here-document: nothing in it expands) and checks each file
  against its platform's file limit; the covers are Pillow's work, so it
  lists them in the manifest and leaves them to `kaleidophone deliver` -- a
  sheet of covers alone needs neither the render nor the master.

## Song packs (`kaleidophone envelope`, canvas/)

A song pack is the song analysed once into 100 Hz envelopes and a beat grid.
Canvas pieces and frame programs react to it, never to the audio stream, so
every render agrees about where the beats are
([ADR-0007](decisions/0007-three-engines-one-contract.md)).
`src/kaleidophone/audio/envelope.py` writes it; `load_songpack()` reads one
back and refuses anything without the format tag.

```
kaleidophone envelope Song.wav -o songpack.json [--bpm-range 60 200] [--downbeat 0.255] [--beats-per-bar 4]
kaleidophone envelope Song.wav --midi Song.mid [--midi-offset S] [--downbeat S] \
    [--stem NAME=path ...] [--stem-offset NAME=S ...] [--voc-stem NAME] -o song.songpack.json
```

`--bpm-range LO HI` (default 60 200) bounds the tempos the grid may take:
narrow it when the grid comes back at double or half time. The pack names
the octave it didn't choose and its score (`grid_check.octave`), and a close
call prints the range that selects the other one — `60 90` for a 70 BPM
ballad that came back at 140, `135 200` for drum and bass that came back
at 87. `--downbeat SECONDS` is bar 1 when you know it; left out, it is
estimated and `grid_check` says how sure. `--beats-per-bar N` (default 4;
3 for a waltz) says which beats can be bar 1 and how long the bars are
that `loudest` snaps to. Given the session's MIDI (`--midi`), the grid is the
session's instead, and its notes, chords and stems join the pack — see
[Session in](#session-in-midi-and-stems---midi---stem) below. Every time and
tempo on the command line must be a finite number: `inf` and `nan` are usage
errors.

**A real song pack is private**, exactly like the master it was derived from.
Keep it next to the release — a `private/` folder is gitignored — never in
this repository. The repository holds synthetic twins, below.

| Key | Unit | What it is |
|---|---|---|
| `kaleidophone` | `"songpack/1"` | the format tag — checked, not trusted: the older hand-rolled envelope files look almost identical with a different frame convention |
| `fps` | Hz | envelope frames per second: 100 |
| `dur` | s | the song's length |
| `bpm` | BPM | the grid's tempo |
| `beat0` | s | the grid's first beat |
| `period` | s | one beat: `60 / bpm` |
| `beats` | s, a list | every grid beat in [0, `dur`): `beat0 + k × period` — a fixed grid, extrapolated through intros and fades, not detected beats one by one |
| `downbeat` | s | bar 1: `--downbeat` exactly as given, or estimated — the beat of the bar where bass-band onsets are strongest *and* the harmony changes (chords and bass notes change on the bar line), weighed across every bar of the song. Its confidence and runner-up are in `grid_check.downbeat`; with nothing in the audio to mark the bar (a kick on every beat and no harmony) the confidence is low and the pack says bar 1 is a guess |
| `bass`, `lowmid`, `mid`, `high`, `air` | 0..1, per frame | band levels over 20–150, 150–400, 400–2000, 2000–6000 and 6000–16000 Hz: dB floored at −100, then each envelope normalised on its own (5th percentile → 0, 99.5th → 1) |
| `rms` | 0..1, per frame | the overall level, normalised the same way |
| `rmsdb` | dB, per frame | the overall level, un-normalised, floored at −100 |
| `flux`, `bflux`, `hflux` | 0..1.5, per frame | spectral flux (the rise in log magnitude) over 20–16000, 20–150 and 2000–16000 Hz, divided by its own 99.5th percentile and clipped at 1.5, so the biggest hit still stands out from an ordinary strong one |
| `cent` | 0..1, per frame | the spectral centroid / 8000 Hz; 0 on silent frames |
| `voc` | 0..1, per frame | stereo input only (absent for mono): centre-panned 250–3500 Hz energy — how far the band's centre stands out from its sides, which rises when a centred voice comes in. A vocal proxy, not a voice detector: a doubled vocal panned hard left and right reads low, and a synth lead parked in the centre reads high. All zeros for a dual-mono file. With a vocal stem (`--stem vocals=…`), that stem's level instead, for mono input too |
| `voc_source` | `"mid-side proxy"` or `"stem"` | where `voc` came from; present whenever `voc` is |
| `loudest` | `{start, len}`, s | the loudest 60 s, starting on the bar line nearest it (bars counted from `downbeat`) — a default reel window that opens where a phrase does. A song of 60 s or less gets `{start: 0, len: dur}` |
| `grid_check` | object | what the analysis is unsure of — see below. Not an envelope; pieces don't read it |

`grid_check` is the grid's own report, for a person or an agent to read
before cutting to it (`kaleidophone envelope` prints it too):

| Key | What it is |
|---|---|
| `beats_per_bar` | the bar length the downbeat and `loudest` used |
| `octave` | `{bpm, score}`: the half- or double-time grid the tempo search weighed and didn't choose, and its score over the chosen one's (the 120 BPM prior included). Near 1 is a coin toss; above 1, off-beat evidence overruled the prior. `null` when neither octave is inside `--bpm-range` |
| `downbeat` | `{source: "given"}`, or `{source: "estimated", confidence, runner_up}`: the share of 4-bar blocks whose own evidence picks the same beat, and the first beat of the next-best choice. With `--midi`, `{source: "midi", confidence: 1, runner_up: null, session_bar}`: bar 1 is a bar line of the MIDI's, `session_bar` its number in the session — or `{source: "given"}` when `--downbeat` put it elsewhere |
| `sections` | one entry per 8 bars from bar 1 (bars before it are one pickup entry): `bars`, `start`, `end`, and where the music's pulse sits against the fixed grid — `offset_ms` at the section's middle beat (> 0: the music is late), `max_ms` at its worst beat, `bpm` the section's own tempo, `off` how many of its `beats` are more than 21 ms (half a frame at 24 fps) from the grid. All `null` where the section has no pulse to measure (a beatless intro) |
| `warnings` | sentences: a close octave call (with the `--bpm-range` that selects the other), a tempo that drifts off the fixed grid (with the share of beats off, the worst section and its own tempo), a guessed bar 1, a given downbeat that sits off the grid. With `--midi`: an offset that is a guess, a given offset away from where the notes fit near it, a given downbeat off the MIDI's 16th notes, a tempo or time-signature change inside the song, the master's pulse off the MIDI's beats, every note outside the song. With `--stem`: a given `--stem-offset` away from where the stem plainly fits |

A fixed grid can't follow a tempo that moves. On a synthetic click track
gliding from 88 to 92 BPM over a minute (`tempo_ramp` in
`tests/test_envelope.py`), 68 of its 88 beats sit more than 21 ms from the
best single grid (90.91 BPM), and the sections' own tempos read 88.91,
90.23 and 91.37 (measured). That is when to cut to a tempo map — the beats
tracked one by one, as `kaleidophone analyze` does — or to analyse the song
in parts.

Frames are centred: frame *i* is the analysis window centred on *i* / 100 s,
and every per-frame array has `floor(dur × 100) + 1` of them. Read one at
`t × 100` — the nearest frame, or interpolated between two as the canvas
harness does (`sampleLinear` in `canvas/tools/lib/common.mjs`, `envAt` in
`canvas/lib/core.js`).

**Events.** A piece that reacts to specific onsets — SHOULD I ?'s vocal
stutters — reads them from `events`: `{name: {key: [[t, strength, ...], ...]}}`,
every entry opening with its time in seconds and a strength, each list sorted
by time. `kaleidophone envelope --midi` writes two of them, `events.midi` and
`events.chords` (below); any other comes from a separate analysis
([TECHNIQUES #48](TECHNIQUES.md#48-lyric-map-from-stem)) and is baked into the
piece at build time through `piece.json`'s `bake`
(`"__STUTTER__": "events.stutter"`).

### Session in: MIDI and stems (`--midi`, `--stem`)

The session knows what the master can only be guessed from
([TECHNIQUES #55](TECHNIQUES.md#55-session-in-midi-and-stems)). `--midi` takes
the session's MIDI export, a Standard MIDI File of format 0 or 1
(`src/kaleidophone/audio/midi.py` reads it); `--stem NAME=path`, once per
stem, takes a stem bounced over one range with the others, which is lined up
with the master (below). Both are as private as the master, and so is a pack
made from them: `midi.tracks` holds the session's track names.

**The offset.** A DAW's MIDI export starts at the session's start; the bounce
may not — pre-roll, a trimmed head, a bounce from bar 5. Master time = MIDI
time + `offset`. Left out, the offset is found: the notes become an onset train
(weighted by velocity; drum tracks — MIDI channel 10, or a name such as kick,
snare, hats or drums — counted double; a chord counted once) that is
cross-correlated with the master's onset envelope over ±30 s and refined below
a frame. Only notes that can reach the song somewhere in that window are in the
train, so a note parked far down the session's timeline costs nothing.
`--midi-offset S` sets it instead: positive for pre-roll (0.5 when the
bounce opens with half a second before the session's start), negative for a
bounce that starts later (−8 for one from bar 5 at 120 BPM in 4/4). A found
offset is called a guess, in the warnings, when its correlation `r` is under
0.25 — the notes hardly match — or within 0.05 of the runner-up, the best
alignment more than 50 ms away — the song repeats itself, and the offset could
be a beat or a bar out. A given offset is used as given: the notes are only
checked within ±0.5 s of it, and a warning says where they fit best there if
that is more than 21 ms off. Measured on the tests' synthetic 16-bar session
and a master rendered from it (`tests/test_envelope.py`; not representative of
real mixes): found within +1.4 ms with 0.5 s of pre-roll and +1.3 ms with the
first 1.25 s trimmed (r 0.94 and 0.93, margins 0.087 and 0.090); one bar looped
sixteen times still lines up right, but only 0.02–0.04 over a runner-up a beat
or a bar away — a warning; the MIDI at 117 BPM against a 120 BPM master reads
r 0.08 — a warning.

What no song holds is refused as a corrupt file, with the reason: a tempo
outside 10–1000 BPM, a file over 64 MB, a last event more than a day past the
song's end, and a grid of more than 100,000 bars, beats or pulses inside the
song (a bar of 1/64 at a tempo no one plays).

**The grid comes from the MIDI.** `beats` is every quarter note of its tempo
map inside the song (the quarter note is what MIDI's tempo and every DAW's
tempo display count), counted from each bar line, so a tempo change is followed
exactly and a 3/8 bar in a 4/4 song leaves the next bar starting on a beat
(counted from the file's start instead, every bar after it sat half a beat off
the beats); the grid runs on into pre-roll at the first tempo and past the
MIDI's last event at the last. `pulses` is the felt beat, from each bar line
too: the time signature's metronome click when it divides the bar (its
default of a quarter note says nothing, and is ignored), else the dotted
quarter in 6/8, 9/8 and 12/8 (and 6/16, 12/16 ...), else the denominator's
note — the quarter in 4/4, so `pulses` is `beats` there; the eighth in 7/8 and
3/8; the half in 2/2. `bpm` and `period` are the tempo at `downbeat`, `beat0`
the first beat, and `downbeat` the first bar line of the MIDI's at or after
0 s: the session's bar 1 for a bounce with pre-roll, bar 2 for one trimmed into
bar 1. Bars follow the time signatures — 4/4 until the first; a 6/8 bar is
three beats and two pulses, a 7/8 bar three and a half beats (the last an
eighth) and seven pulses — and `--beats-per-bar N` stands in, as N/4, only for
a file that has none. `--downbeat S` puts bar 1 at S s on the master when the
MIDI's tick 0 isn't a bar line — a clip exported from a pickup — and the bars
follow the MIDI's time signatures from there, with a warning if S is more than
21 ms from the MIDI's nearest 16th note. `loudest` snaps to those bar lines. In
`grid_check`, `octave` is `null`, `beats_per_bar` is the quarter notes in bar
1's bar, `downbeat` is `{source: "given"}` when `--downbeat` set it, and
`sections` measures how well the master's pulse sits on the MIDI's beats —
off, the MIDI isn't this bounce's: another version, a time-stretched bounce,
or a wrong offset. A tempo change inside the song is warned about with where a
piece that assumes one BPM falls more than 21 ms off the beats; a
time-signature change, with where the bars change length.

**The notes.** Every note is an event, its duration as it sounded: a note
released while its track's channel holds the sustain pedal down (CC64 at 64 or
more) sounds until the pedal comes up or the key is struck again, so a
pedalled arpeggio of short notes is the chord it sounds like, in
`events.midi` and `events.chords` alike.

**The stems are lined up.** A mastered bounce is often trimmed or padded at the
head, and the stems aren't: a master with 0.30 s cut from its head put the
vocal stem's `voc` 300 ms late (the 0.4 review's case). Each stem's lag on the
master (master time = stem time + lag) is found by correlating its levels and
onsets in 1/6-octave bands with the master's over ±2 s, refined below a frame
and kept to the millisecond; the stem is moved by it, then measured. A lag is
trusted when its correlation `r` is 0.2 or more and beats the best other lag
more than 50 ms away by 0.05. A stem that repeats itself — a loop fits about as
well a beat or a bar away — takes its own best lag near the lag most trusted
stems agree on (stems bounced together share one); a stem that can't be
trusted, or that surely lines up somewhere the others don't, is refused,
naming the lag the other stems agree on, until `--stem-offset NAME=S` gives
its lag. A stem with nothing to line up by (silence, a drone) stays where it
starts. Once lined up, a stem must end where the master does to within 0.5 s;
within that its tail is padded or trimmed. Measured on synthetic stems in a
synthetic mix (`tests/test_envelope.py`; not representative of real mixes):
drums, bass, keys and voices lined up within 3 ms with the master trimmed
0.3 s, padded 0.4 s, or trimmed 1.234 s and soft-clipped, r 0.37–1.0, the voice
10 dB down included; a stem from elsewhere scored 0.08–0.12 with margins under
0.03, a pad swelling in over 1.5 s 0.16–0.23 with margins under 0.01 where it
reached 0.2, and a strict click loop 0.95 with margins of 0.024–0.026 — 500 ms
out on its own, right with the other stems. The review's case lines up at
−0.300 s (r 0.99), and `voc` rises at 3.73 s where the master's voice comes in
(3.70), not 4.03. Why levels and onsets both, and how they combine, is in
`envelope.py`'s `_align_stems`. Nothing checks a stem for drift: one from
another version at another tempo can line up where its start does.

| Key | What it is |
|---|---|
| `pulses` | s, a list: every felt beat (above) in [0, `dur`), from each bar line — dotted quarters in 6/8, so two a bar where `beats` has three; `beats` itself in 4/4. Only with `--midi`: without it, the tempo search's beat is the pulse |
| `pulses_per_bar` | how many pulses fill the bar `downbeat` opens: 2 in 6/8, 4 in 12/8, 7 in 7/8, 4 in 4/4 |
| `midi` | `{file, ppq, offset, offset_source, confidence, tempo_map, time_signatures, tracks, dropped}`: the MIDI file's basename; ticks per quarter note (`null` for a file in SMPTE time); the offset in s; `"auto"` or `"given"`; `{r, margin, runner_up}` — the correlation at the offset, its margin over the runner-up and the runner-up's offset in s (`margin` and `runner_up` are `null` for a given offset, and the whole object for a file with no notes); `[[t, bpm], ...]`, the tempo at 0 s and every change inside the song; `[[t, num, den], ...]`, the same for time signatures; the tracks with notes, by name (`track-<n>` for an unnamed one), in the order of `events.midi`; how many notes fell outside the song and were dropped |
| `events.midi.<track>` | `[[t, velocity, duration, pitch], ...]`: every note of the track inside the song, `t` and `duration` in s on the master's clock (the duration as the sustain pedal holds it), `velocity` 0..1 (the MIDI velocity / 127), `pitch` a MIDI note number (60 is middle C). The key is the track's name slugged — lowercase a–z, 0–9 and `-` (`Hi Hat` → `hi-hat`); `track-<n>` for a track with no name, or none in Latin letters (n is its place among the file's tracks); `-2`, `-3` on a repeat. A format-0 file is split by channel: `channel-1`, `channel-10` |
| `events.chords.<track>` | `[[t, 1, "Am"], ...]` for each track that plays chords (not a drum track, and at least a fifth of its onsets sound three or more pitch classes or a power chord): an event where the pitch classes sounding change and then hold for an 8th note or more, so a passing chord doesn't count; the chord already sounding at 0 s opens the list at 0 s. Named by pitch class over the lowest note: triads (`C`, `Am`, `Bdim`, `Caug`, `Dsus4`, `Gsus2`), power chords (`E5`), sevenths (`G7`, `Cmaj7`, `Am7`, `Bm7b5`, `Bdim7`, `CmMaj7`, `G7sus4`, and the first three without their fifth), `6`, `m6`, `add9`, `madd9`, `9`, `m9`, `maj9`, `6/9`, `m11`, `maj7#11`, `7#9`; `"?"` for a chord outside that list. When the lowest note isn't the root it follows a slash: an inversion is the chord over it (`C/E`, `G7/B`), and a chord over a bass note of its own is that chord over it — `F/G`, not `Fadd9`; `C/B`, not `Cmaj7` — unless the bass has its own third and fifth in the set, when it is the root. Where one set has two names (C6 and Am7, Dsus4 and Gsus2) the one rooted on the lowest note wins. Notes are spelled for the file's key signature: with flats in a flat key; in a sharp key with its own sharps and a chart's usual spelling otherwise (`Bb` in G major, not `A#`); without one, C# Eb F# Ab Bb |
| `stems.<name>` | per stem, the master's envelopes — `bass`, `lowmid`, `mid`, `high`, `air`, `rms`, `rmsdb`, `flux`, `bflux`, `hflux`, `cent` — measured with the stem lined up (`stems_alignment`), at the master's length and frame rate, normalised as the master's are except that the stem's digital silence stays out of the percentiles and reads 0. A piece reads one as `envAt('stems.drums.rms', t)` |
| `stems_alignment.<name>` | `{lag, r, source}`: where the stem's 0 s falls on the master, in s to the millisecond (− for a master trimmed at the head); its correlation with the master there (`null` for a stem with nothing to line up by); `"auto"`, `"given"` (`--stem-offset`) or `"none"` (silence, a drone: left at 0). `kaleidophone envelope` prints it as `stem lag` |
| `voc`, `voc_source` | with a stem named `vocals`, `vocal`, `vox` or `voice` (any case), or the one `--voc-stem NAME` names, `voc` is that stem's `rms` and `voc_source` is `"stem"`, for a mono master too; otherwise both are as above |

Abridged, from the tests' session with its first 1.25 s trimmed, and its keys
rendered from the session's start as a stem:

```json
{
  "bpm": 120.0, "beat0": 0.2513, "period": 0.5, "beats": [0.2513, 0.7513, 1.2513], "downbeat": 0.7513,
  "pulses": [0.2513, 0.7513, 1.2513], "pulses_per_bar": 4,
  "midi": {"file": "Song.mid", "ppq": 480, "offset": -1.2487, "offset_source": "auto",
           "confidence": {"r": 0.934, "margin": 0.09, "runner_up": -0.75},
           "tempo_map": [[0.0, 120.0]], "time_signatures": [[0.0, 4, 4]],
           "tracks": ["Kick", "Snare", "Hats", "Keys"], "dropped": 3},
  "events": {"midi": {"kick": [[0.7513, 0.929, 0.0625, 36], [1.5013, 0.984, 0.0625, 36]],
                      "keys": [[0.7513, 0.63, 1.9896, 53], [0.7513, 0.63, 1.9896, 57]]},
             "chords": {"keys": [[0.0, 1, "Am"], [0.7513, 1, "F"], [2.7513, 1, "C"]]}},
  "stems": {"keys": {"rms": [0.0, 0.0, 0.0]}},
  "stems_alignment": {"keys": {"lag": -1.25, "r": 0.351, "source": "auto"}},
  "grid_check": {"downbeat": {"source": "midi", "confidence": 1.0, "runner_up": null, "session_bar": 2}}
}
```

A 0.3 reader reads this pack unchanged: every earlier key keeps its meaning,
and the grid is still `beats`, `bpm` and `downbeat` — only now `beats` can
follow a tempo change that `bpm` alone can't.

### Synthetic twins (`canvas/tools/synth.mjs`)

What the repository holds instead of a real pack: the song's tempo, first
downbeat, section boundaries and each section's level per envelope — a number
(the mean) or `[mean, p95, max]` rounded to 0.05 — with every hit and wobble
generated from a seed. Enough to run, test and show a piece; nothing about the
sound. The spec
is `canvas/pieces/<id>/synthetic.json` — this one abridged from SHOULD I ?'s:

```json
{
  "seed": 7,
  "fps": 100,
  "dur": 183.775,
  "bpm": 80,
  "downbeat": 0,
  "keys": ["bass", "lowmid", "mid", "high", "air", "rms", "flux", "bflux", "hflux", "cent", "voc"],
  "voc": [[6, 48.2, 0.8], [54, 107.25, 0.7]],
  "events": {"stutter": {"s1": [[107.956, 111.2, 5.6, 0.9]]}},
  "sections": [
    {"from": 0, "kick": "none", "snare": false, "hats": false, "bass": [0.15, 0.3, 0.3], "mid": [0.4, 0.65, 0.75], "rms": [0.2, 0.35, 0.45]},
    {"from": 54, "kick": "1-3", "bass": 0.85, "mid": 0.55, "rms": 0.8}
  ]
}
```

| Key | Default | What it does |
|---|---|---|
| `seed` | 7 | seeds the generator (mulberry32, one stream per part): the same spec gives the same pack on every machine |
| `fps` | 100 | envelope frames per second |
| `dur` | required | seconds |
| `bpm` | required | the real tempo: kicks, snares and hats land on its grid |
| `downbeat` | 0 | bar 1, in seconds: where the grid starts |
| `beatGrid` | the `bpm`/`downbeat` grid | `{bpm, downbeat}` for the pack's `beats` alone, when a driver follows another pulse (HAMECHI MANZOR DARE's tracked the half-time) |
| `keys` | all twelve | which arrays to write: `bass`, `lowmid`, `mid`, `high`, `air`, `rms`, `rmsdb`, `flux`, `bflux`, `hflux`, `cent`, `voc` |
| `quantize` | off | store `round(v × quantize)` integers instead of floats rounded to 0.001 (255, like the toolkit-era packs) |
| `voc` | none | `[[from, to, amp], ...]` (`amp` default 0.8): windows of syllable-like bursts, 4–7 a second, in `voc` and the mid band |
| `events` | none | `{name: {key: [[from, to, rate_hz, strength], ...]}}` (defaults 6 and 0.9) → onsets `[[t, s], ...]` on the song's 16th grid, humanised by at most 20 ms; a rate above the grid's adds a 32nd to some steps, one below it rests on some. A group can't be named `midi`: that is the drums' (below) |
| `stems` | off | `true`: the pack gets `stems.drums`, `.bass`, `.vocals` and `.other` too, as the Session engine writes a real pack's (above) — below |
| `sections` | one section at `rms` 0.5 | the song's shape, each entry owning its frames from its `from` until the next one's |

Each `sections[]` entry:

| Key | Default | What it does |
|---|---|---|
| `from` | required | seconds; the section starts on its first frame, with no crossfade before it (a drop is not anticipated) |
| an envelope | its `rms` mean | `bass`, `lowmid`, `mid`, `high`, `air`, `rms`, `flux`, `bflux`, `hflux`, `cent` or `voc`: a number (the section's mean) or `[mean, p95, max]` (its distribution — the biggest hit reaches the max, 5 % of its frames sit at or above the p95, the rest average to the mean). A mean alone gets the peaks real sections with that mean have. `energy` is the old name of the `rms` mean |
| `kick` | `"all"` | `"all"` (every beat, with the odd syncopated one), `"1-3"` (beats 1 and 3) or `"none"` |
| `snare` | `true` | snares on beats 2 and 4, with ghost notes |
| `hats` | `true` | hats on the 8ths with accented off-beats, pickups, drop-outs and an open hat into the bar |
| `crash` | see note | a crash (a high/air/flux spike) on the section's first frame; by default every section after the first that has a kick or a snare opens on one |

Each envelope is generated raw (beds that move on the bar, hits on the grid,
a swell per phrase), then mapped onto its section's level by an
order-keeping map: the biggest hit stays the biggest. `rms`, `flux`, `bflux`,
`hflux` and `cent` are derived from the generated bands, then mapped the same
way; the three fluxes run to 1.5, like a real pack's. Every array has
`ceil(dur × fps) + 1` frames. A twin pack carries the `songpack/1` marker,
`synthetic: true` (CI refuses any tracked pack without it), the grid
(`bpm`, `beat0`, `period`, `beats`, `downbeat`) and `loudest` — the loudest
60 s, snapped to a bar line as `kaleidophone envelope` snaps it — plus the
arrays in `keys` and any `events`. Pieces take their own grid from their code
(`makeGrid`), not from the pack.

**The drums, as MIDI.** Every twin pack also carries the hits its envelopes
were built from, the way a Session pack carries a MIDI part:
`events.midi.kick`, `.snare`, `.hat` and `.crash`, each `[[t, velocity, 0.05,
pitch], ...]` sorted by time — `t` rounded to 0.1 ms like `beats`, `velocity`
0..1 (ghost notes and off-beat hats softer), General MIDI's kick 36, snare 38,
closed hat 42 and open hat 46 (both in `hat`) and crash 49. So a piece that
reacts to `midi.kick` runs on its twin in CI and in the gallery. They are
written for every spec; nothing else in a pack changed with them, byte for
byte — `npm test` holds each piece's twin to its 0.3 hashes.

**Stems** (`"stems": true`) are the master's envelopes per part, as a real
pack's are: the arrays in `keys` (`voc` aside) for each of `drums`, `bass`,
`vocals` and `other`, each normalised on its own — its 5th percentile → 0 and
99.5th → 1, the fluxes divided by their 99.5th and clipped at 1.5 — with
digital silence kept out of the percentiles and read as 0; `rmsdb` is in dB,
never above the master's. Where they come from: the generator knows what made
every frame of every band (the drums' hits, the bassline, the chords and the
bed under them, the syllables), so before it is normalised a stem's band is the
master's band times that part's share of it — loud where the master is loud and
the part is playing, and silent where it doesn't play: a spec with no `voc`
windows has silent vocals. A piece reads one as `envAt('stems.drums.rms', t)`.

```bash
node tools/synth.mjs --twin private/songpack.json --sections 0,32.26,42.26,72.25 \
     [--bpm B] [--downbeat D] > pieces/<id>/synthetic.json
node tools/synth.mjs --twin private/songpack.json --piece <id>   # re-measure an existing twin in place
node tools/synth.mjs <id>        # -> out/songs/<id>.songpack.json (gitignored)
```

`--twin` measures a real pack per section — `[mean, p95, max]` of every
envelope, rounded to 0.05 — and that spec is the only thing that crosses from
private to public: coarse numbers, nothing per hit. It reads byte packs,
centroids stored in Hz and packs not at 100 fps. With `--piece`, it keeps the
piece's grid, its section boundaries and everything written by hand (patterns,
`voc` windows, `events`, `beatGrid`, `keys`, `quantize`) and replaces only the
levels. Two things it leaves to you: without `--downbeat` the twin's
`downbeat` is the pack's `downbeat` — `kaleidophone envelope`'s estimate of
bar 1, or `beat0`, the first grid beat, for a pack without one — which is
only as good as the pack's `grid_check.downbeat.confidence` says; and it
writes no `kick`, `snare`, `hats`, `crash`, `voc` or `events` for a new spec,
so every section starts with a kick on every beat until you say otherwise.
`npm test` in `canvas/` checks that every piece's twin synthesizes, that its
`dur` is within 6 s of the piece's `grid.dur`, and that a committed spec holds
only rounded levels and no per-hit lists.
