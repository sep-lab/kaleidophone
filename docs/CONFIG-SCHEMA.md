# The creative brief: field reference

The full schema lives in `src/kaleidophone/timeline/schema.py` (pydantic — it's
the actual validator, this doc is a guide to it, not a duplicate source of
truth). `examples/love/brief.yaml` and `examples/demo/generate_fixtures.py`
are worked examples.

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
