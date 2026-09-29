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
silent: _work/full_silent.mp4    # required -- the ONE silent render every cut comes from.
                                 #   t0, dur and video_from below are on its clock
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
check: true                      # count frames, duration and size of what was written (default true)
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
- `audio` is required unless every cut is `audio: none`; `silent_start` is
  any finite number; `ceiling_dbtp` is `auto` or a number at or under 0;
  `audio_bitrate` must look like a bitrate, and there must be at least one
  cut.

When `deliver` runs, before any encoding, reporting every problem at once:

- every input exists (the master only if a cut has audio);
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
  keyframe forced at the end too makes it exact.

Without ffprobe these checks are best-effort.

### What it writes

- A line for the master first: its loudness and true peak, the gain every
  cut gets, and the ceiling. Then each `out`, under `-o DIR` (default: the
  sheet's own directory): the picture stream-copied and bounded by
  `-frames:v`, never `-t`; the audio windowed, gained (limited), faded and
  encoded to AAC; and on every file,
  `-dn -sn -map_metadata -1 -map_chapters -1 -movflags +faststart`. A cut with
  `audio: none` has no audio stream. Card cuts' intermediates go in
  `.kaleidophone-cache/deliver/` under it and are removed afterwards.
- With `check: true`, a table measured on the files themselves: frames counted
  against frames expected, duration, integrated LUFS, true peak, size and the
  gain (and limiter) used. `!frames` and `!peak` flag a row. The true peak is
  guarded whatever `check` says.
- With `--dry-run`, nothing is run: the same delivery is printed as a POSIX sh
  script — the master measured once, the guard's rounds, the ceiling worked
  out the same way, and the limiter's delay taken back whichever ffmpeg it
  finds — with the `-force_key_frames` list in its header. Run where the
  master is, it writes the same files as `deliver` (byte-identical, measured
  with ffmpeg 6.1 and 4.2.2 on synthetic masters). It needs neither the render
  nor the WAV to print, so it is also how to plan a render's keyframes. From
  a relative sheet path the script holds no absolute paths; run it from the
  directory kaleidophone ran in. No path in the sheet can expand or run
  anything in it, and no ffmpeg in it reads the terminal (`-nostdin`), so it
  can run inside a `while read` loop.

## Song packs (`kaleidophone envelope`, canvas/)

A song pack is the song analysed once into 100 Hz envelopes and a beat grid.
Canvas pieces and frame programs react to it, never to the audio stream, so
every render agrees about where the beats are
([ADR-0007](decisions/0007-three-engines-one-contract.md)).
`src/kaleidophone/audio/envelope.py` writes it; `load_songpack()` reads one
back and refuses anything without the format tag.

```
kaleidophone envelope Song.wav -o songpack.json [--bpm-range 60 200] [--downbeat 0.255] [--beats-per-bar 4]
```

`--bpm-range LO HI` (default 60 200) bounds the tempos the grid may take:
narrow it when the grid comes back at double or half time. The pack names
the octave it didn't choose and its score (`grid_check.octave`), and a close
call prints the range that selects the other one — `60 90` for a 70 BPM
ballad that came back at 140, `135 200` for drum and bass that came back
at 87. `--downbeat SECONDS` is bar 1 when you know it; left out, it is
estimated and `grid_check` says how sure. `--beats-per-bar N` (default 4;
3 for a waltz) says which beats can be bar 1 and how long the bars are
that `loudest` snaps to.

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
| `voc` | 0..1, per frame | stereo input only (absent for mono): centre-panned 250–3500 Hz energy — how far the band's centre stands out from its sides, which rises when a centred voice comes in. A vocal proxy, not a voice detector: a doubled vocal panned hard left and right reads low, and a synth lead parked in the centre reads high. All zeros for a dual-mono file |
| `loudest` | `{start, len}`, s | the loudest 60 s, starting on the bar line nearest it (bars counted from `downbeat`) — a default reel window that opens where a phrase does. A song of 60 s or less gets `{start: 0, len: dur}` |
| `grid_check` | object | what the analysis is unsure of — see below. Not an envelope; pieces don't read it |

`grid_check` is the grid's own report, for a person or an agent to read
before cutting to it (`kaleidophone envelope` prints it too):

| Key | What it is |
|---|---|
| `beats_per_bar` | the bar length the downbeat and `loudest` used |
| `octave` | `{bpm, score}`: the half- or double-time grid the tempo search weighed and didn't choose, and its score over the chosen one's (the 120 BPM prior included). Near 1 is a coin toss; above 1, off-beat evidence overruled the prior. `null` when neither octave is inside `--bpm-range` |
| `downbeat` | `{source: "given"}`, or `{source: "estimated", confidence, runner_up}`: the share of 4-bar blocks whose own evidence picks the same beat, and the first beat of the next-best choice |
| `sections` | one entry per 8 bars from bar 1 (bars before it are one pickup entry): `bars`, `start`, `end`, and where the music's pulse sits against the fixed grid — `offset_ms` at the section's middle beat (> 0: the music is late), `max_ms` at its worst beat, `bpm` the section's own tempo, `off` how many of its `beats` are more than 21 ms (half a frame at 24 fps) from the grid. All `null` where the section has no pulse to measure (a beatless intro) |
| `warnings` | sentences: a close octave call (with the `--bpm-range` that selects the other), a tempo that drifts off the fixed grid (with the share of beats off, the worst section and its own tempo), a guessed bar 1, a given downbeat that sits off the grid |

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
stutters — reads them from `events`, which `kaleidophone envelope` doesn't
write: `{name: {key: [[t, strength], ...]}}`, added from a separate analysis
([TECHNIQUES #48](TECHNIQUES.md#48-lyric-map-from-stem)) and baked into the
piece at build time through `piece.json`'s `bake`
(`"__STUTTER__": "events.stutter"`).

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
| `events` | none | `{name: {key: [[from, to, rate_hz, strength], ...]}}` (defaults 6 and 0.9) → onsets `[[t, s], ...]` on the song's 16th grid, humanised by at most 20 ms; a rate above the grid's adds a 32nd to some steps, one below it rests on some |
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
