# kaleidophone · canvas

The canvas engine: music videos with no footage, written as code.

A **piece** is one self-contained HTML file (vanilla canvas 2D, fonts inlined,
no network) that does three things off its URL:

| Mode | Query | What it does |
|---|---|---|
| live | *(none)* | Click it: a procedural pad and beat at the song's tempo. Or drop the track on it: a Web Audio analyser drives it, endlessly. |
| render | `?render=1&w=1080&h=1920` | Deterministic. `window.__frame(p)` draws one frame from time + envelope; `tools/render.mjs` drives it and pipes the frames to ffmpeg — silent. |
| cover | `?cover=1&size=3000` | `window.__cover(name)` draws a still. |

One draw function serves all three, so one file gives you the live piece, the
film, the reel, the stories and the covers
([TECHNIQUES #19](../docs/TECHNIQUES.md#19-three-mode-piece)). Why a second engine
at all: [ADR-0007](../docs/decisions/0007-three-engines-one-contract.md).

**See them:** [the gallery](https://sep-lab.github.io/kaleidophone/) — every piece
rendered in CI from its *synthetic* twin, plus the live pieces themselves.

## The pieces

All by Sep The Concept, 2026. Each folder is the piece as it shipped (comments
and one live-mode fix aside, below) plus a driver and a synthetic song.

| Piece | Medium | Case study |
|---|---|---|
| [HAMECHI MANZOR DARE](pieces/hamechi-manzor-dare/) | live-reactive paranoia piece: sprite fire, a pressure-ring swarm, a mask state machine | [→](../docs/case-studies/hamechi-manzor-dare.md) |
| [( - )](pieces/minus/) | ink-on-paper Flash cartoon; she is never drawn, only the paper where she'd be | [→](../docs/case-studies/minus.md) |
| [SAME AS YOU](pieces/same-as-you/) | the sequel: one page torn in two mirrored half-worlds; rig v2, chromatography, vector droste | [→](../docs/case-studies/same-as-you.md) |
| [SHOULD I ?](pieces/should-i/) | the whole film through his camera's viewfinder: 36 frames on 36 snares, a 37th | [→](../docs/case-studies/should-i.md) |
| [template](pieces/template/) | **start here**: the lib in one 8-bar loop — title write-on, a chair built from the body, a planted walk, a droste; a bulb that pops on the snare, a nod on the kick and the droste's turn on the chord change, from the song's events. Variants: three endings from bar 7, `droste` (the default), `lamp` and `exit` (`--variant ending=lamp`; live, `?variant=ending:lamp`) | — |

## Quick start

Node 20+ and ffmpeg. From this folder:

```bash
npm ci                                        # exact versions: fonts are inlined byte-for-byte from these packages
npx playwright-core install chromium          # once (skip in the cloud sandbox: it has /opt/pw-browsers/chromium)
npm test                                      # lib + tools unit tests (no browser)

node tools/build.mjs --all                    # every piece -> dist/<piece>.html, baked with its synthetic twin
open dist/should-i.html                       # live mode: click, or drop a track on it

# a silent, deterministic render from a song pack (synthetic here), and what it was: out/say_heart.mp4.json
node tools/render.mjs same-as-you --song out/songs/same-as-you.songpack.json \
     --t0 62.255 --dur 10 --out out/say_heart.mp4
node tools/still.mjs minus --song out/songs/minus.songpack.json --t 30,90 --w 540    # QA stills (PNG), in out/stills/
node tools/still.mjs should-i --song out/songs/should-i.songpack.json --cover all      # every cover
node tools/render.mjs template --song out/songs/template.songpack.json --t0 12 --dur 4 \
     --endings ending --out out/tpl.mp4     # a body + one file per ending, joinable by stream copy (Variants, below)
node tools/gallery.mjs --out ../site          # the whole gallery site, as CI builds it
node tools/render.mjs --help                  # every flag (still.mjs and build.mjs too)
```

`render.mjs` and `still.mjs` build the piece from its source with the `--song`
they are given before opening it (into `out/build/`, deleted when they finish);
`dist/` is for opening a piece in a browser. Flags take `--flag value` or
`--flag=value`, and each tool knows its own: a misspelled one (`--worker 2`)
stops the command with the list of valid flags instead of being ignored. A
request that can't be rendered — `--to` past the window, a size H.264 can't
encode, a key time off the frame grid — is refused in one line with exit status
2, before ffmpeg or Chromium start. A render works in a folder made for the run
next to its output (`<out stem>.parts-XXXXXX`, deleted when it ends) and deletes
nothing else; a failure exits 1 and leaves no work folder and no half-written
video behind. Stills go in `--out`, by default this folder's `out/stills/`, which
git ignores wherever the command is run from.

## The piece contract

```
pieces/<id>/
  piece.json       title, artist, medium, the grid, fonts, lib, cuts, keyframes, covers, gallery clip
  template.html    the page; /*__FONTS__*/ and /*__JS__*/ are filled by tools/build.mjs
  src/*.js         the piece, as plain script modules concatenated in name order
  driver.mjs       how the harness talks to it (only what differs from the default)
  synthetic.json   the synthetic twin of its song: tempo, downbeat, sections, rounded levels
```

What the page exposes in render mode:

| | |
|---|---|
| `window.__ready` | `true`, or a promise, once fonts are loaded |
| `window.__init(pack)` | optional: receive the whole song pack once |
| `window.__frame(p)` | draw one frame; `p = { t, bass, mid, high, air, rms, flux, bflux, hflux, cent, voc, …flags }` |
| `window.__cover(name, arg)` | draw a still (cover mode) |

The default driver samples the pack at `t` (linear, 100 Hz) and calls
`__frame`. A piece's `driver.mjs` overrides only what differs: SHOULD I ? takes
the whole pack through `__init` and draws `__frame(t, {cardT0})`; ( - ) turns
`--card` into its signature card; HAMECHI MANZOR DARE is the one **stateful**
piece (a seeded swarm, fire and masks that carry over), so its driver renders in
order from a 3 s warm-up, snaps `t0` to a beat and schedules the masks.

A pure function of time is the thing to aim for
([#30](../docs/TECHNIQUES.md#30-pure-function-of-time)): any window renders on its
own, workers split it freely, and a new master that keeps the grid is a
constants change.

### Events

A song pack's `events` are what the song *played*, as lists sorted by time:
`events.midi.<track>` = `[[t, velocity 0..1, duration, pitch], ...]` (a Session's MIDI
parts; a synthetic twin's drums, `midi.kick`, `.snare`, `.hat`, `.crash`),
`events.chords.<track>` = `[[t, 1, "Am"], ...]` (a synthetic twin plays a made-up progression
on its bar lines when its spec has `"chords"`: the template's droste turns on the change), and an older pack's onsets,
`events.<name>.<key>` = `[[t, s], ...]` (SHOULD I ?'s stutter). `core.js` reads any of them
by binary search, so a piece that reacts to a hit is still a pure function of time:

```js
const snare = evList(EV, 'midi.snare');      // [] when the song has none: never null
evPulse(snare, tq, 0, 0.1)                   // the hits as an envelope: velocity x attack/decay, the strongest recent one
evNth(snare, tq)                             // how many so far (SHOULD I ?'s frame counter); evLast: the index of the last
evSince(snare, tq)                           // seconds since the last (Infinity before the first)
evCount(snare, G.bt(3), G.bt(4))             // how many in bar 3: [t0, t1)
evChord(evList(EV, 'chords.keys'), tq)       // the chord sounding at tq, or null
envAt('stems.drums.rms', tq)                 // a stem's envelope reads like the master's
```

`EV` (`live.js`) holds the events in every mode: the pack's, from `window.__init` (render and
cover), and live the procedural fallback's own kicks, snares and hats, pushed into
`EV.events.midi.kick` / `.snare` / `.hat` as it schedules them — a piece that reacts to
`midi.kick` reacts when clicked, too. A dropped track has no MIDI: those lists stay empty, so
keep an envelope fallback (the template's lamp follows `env.hflux` then). Read them at the
drawing's time `tq`, like everything drawn on twos, and look a list up in `draw`: `__init`
replaces them.

### The gallery entry

`piece.json`'s `"gallery"` is what [the gallery](https://sep-lab.github.io/kaleidophone/)
shows of the piece: a clip rendered from its synthetic twin by `tools/gallery.mjs`
(in CI; nothing it writes is committed), a poster and a cover.

| Key | Default | |
|---|---|---|
| `t0` | *(required)* | where the clip starts in the song, in seconds (a stateful piece snaps it to a beat) |
| `dur`, `fps` | 6, 12 | the clip's length (s) and frame rate |
| `poster` | 60 % of `dur` | seconds into the clip for the poster: the still shown for reduced motion, and the piece's tile in the link preview |
| `alt` | the title | what the clip shows, in words: its alt text on the page and in the README. Describe the picture — never a lyric or a name |
| `quality` | 70 | the WebP's `q` (0–100); lower it for a clip whose every pixel moves (fire, grain) |
| `order` | after the ordered ones, by folder | its place on the page (the works go in release order) |
| `listen` | — | an `https://` link to the song, shown as "listen" when set |
| `cover` | — | the `covers` variant shown next to the clip |
| `mode`, `card` | — | passed to `render.mjs` as `--mode` and `--card` |
| `role` | `piece` | `template` shows it under "Start a piece from this" instead of in the grid |

The README's table of clips repeats each `alt`: change both together.

## Song packs: real ones stay private

A song pack is the analysed song as JSON: 100 Hz envelopes, the beat grid, and
any events a piece reads (SHOULD I ?'s vocal onsets).

```bash
kaleidophone envelope "Song.wav" -o songpack.json      # the Python package makes real ones
node tools/synth.mjs should-i                          # a synthetic one, from pieces/should-i/synthetic.json
node tools/synth.mjs --twin songpack.json --sections 0,32.26,42.26 > synthetic.json   # a twin's spec from a real pack
node tools/synth.mjs --twin songpack.json --piece should-i                            # re-measure a piece's twin in place
```

A **real** pack is derived from an unreleased master, so it is private like the
audio: keep it next to the release, never in this repository. The repository
only holds **synthetic twins** — the real tempo, first downbeat and section
boundaries, and each section's level per envelope as `[mean, p95, max]` rounded
to 0.05, with every hit generated (SHOULD I ?'s also keeps the hand-placed vocal
and stutter windows it needs). A twin can also play a chord progression on its
bar lines — `"chords": {"track": "keys", "progression": ["Am", "F", "C", "G"],
"every": "bar"}` writes `events.chords.keys` — made up like its drums, never the
song's own harmony (the template's droste turns on it). Enough to run, test and show a piece — the
biggest hit still lands where it should — and nothing about the sound
([ADR-0007](../docs/decisions/0007-three-engines-one-contract.md)). CI refuses any
tracked pack that isn't marked `"synthetic": true`.

To re-render a real release, render with the real pack: `node tools/render.mjs
<piece> --song private/songpack.json …` builds its own copy of the piece with that
pack's events baked in, so it can never pick up a twin left in `dist/`.

### Private pieces: `KALEIDOPHONE_PIECES`

A piece joins this repository only once its song is out, with a synthetic twin,
a gallery entry and a scrubbed case study. Until then it is private, like its
song pack, and lives in a folder of pieces outside the checkout, laid out like
`canvas/pieces/` (`<id>/piece.json`, `src/`, `driver.mjs`). Point the tools at
that folder and they work on it unchanged:

```bash
export KALEIDOPHONE_PIECES=/path/to/private/pieces     # a folder of pieces, outside the repository
node tools/build.mjs my-piece --song /path/to/private/songpack.json --out /path/to/private/my-piece.html
node tools/render.mjs my-piece --song /path/to/private/songpack.json --out /path/to/private/film.mp4
node tools/still.mjs my-piece --song /path/to/private/songpack.json --t 12 --out /path/to/private/stills
```

- **What it swaps:** where pieces are listed and loaded from. Every tool
  (`build`, `render`, `still`, `synth`, `gallery`) sees only that folder, so
  `build.mjs --all` builds the private pieces and none of the public ones.
- **What it keeps:** the lib, the fonts and the tools are this checkout's, so a
  private piece builds with exactly the code a public one does, and it lands
  later as a copy of the folder, not a port.
- **Where output goes:** without `--out`, a build lands in `canvas/dist/`,
  stills in `canvas/out/stills/` and a render in the folder you ran it from;
  the render tools' working builds always go to `canvas/out/build/`. Git
  ignores all of them, but they are inside the checkout, so pass `--out` and
  keep a private build next to its song.
- Unset it (or open a new shell) before working on the repository's own
  pieces. The tests use the same variable for throwaway fixture pieces
  (`canvas/test/render.test.mjs`).

The deny-list check ([CONTRIBUTING.md](../CONTRIBUTING.md#the-deny-list)) is
the backstop for a private name that does reach a commit.

## From render to release

Render the film once, silent, with keyframes forced at every cut you plan
([#41](../docs/TECHNIQUES.md#41-forced-keyframes)), then cut and mux where the WAV
lives:

```bash
node tools/render.mjs same-as-you --song private/songpack.json --t0 0 --dur 138.5 \
     --key-times 0,26.25,42.25,56.25,72.25,80.25,96.25 --workers 2 --out full_silent.mp4
kaleidophone deliver delivery.yaml          # stream-copied cuts, audio muxed, AAC true-peak guard, a report
kaleidophone deliver delivery.yaml --dry-run > mux.sh    # or: the same thing as a script for another machine
```

The render bakes the real pack's events into its own build of the piece, so it
can't pick up the synthetic twin that `build --all` and the gallery leave in
`dist/`; `--html file.html` renders a given file instead. `--key-times` takes
the cut points in song seconds — here the starts and ends of SAME AS YOU's
`cuts`, the same frames as `--keys 0,630,1014,1350,1734,1926,2310`. Each must
sit on the render's frame grid. The `-force_key_frames` list that `kaleidophone
deliver` prints is on the silent file's own clock: song time for a render from
`--t0 0`; for a window, add its `t0`.

Next to every render, `<out>.json` records what it is: the piece, `t0` as asked
and as snapped, `silent_start` (the song time of the file's first frame — the
delivery sheet's `silent_start`), frame rates and counts, every forced keyframe
as a frame and in seconds, size, workers, and the versions of the tool,
Chromium and ffmpeg. It names the song pack by file name only, never a path,
and says whether it was a synthetic twin.

A long render can be split or resumed by frame range: `--from N --to M` renders
frames [N, M) of the window, and the sidecar's `silent_start` is then the song
time of frame N. A stateful piece first replays every frame before N from its
warm-up, so a resumed window matches the whole one (measured on HAMECHI MANZOR
DARE, 1 s at 30 fps resumed at frame 15: 15 of 15 frames PNG-identical).

The delivery sheet format is in [docs/CONFIG-SCHEMA.md](../docs/CONFIG-SCHEMA.md).
A new master for an existing film: `kaleidophone master-check old.wav new.wav`
first — it says re-mux, offset (with the `silent_start` to use), re-render these bars, or new grid
([#49](../docs/TECHNIQUES.md#49-master-drop-in-check)).

### Variants

A piece that can end (or look) more than one way declares each choice as an axis in `piece.json`:

```json
"variants": {"ending": {"at": 14.0, "options": ["droste", "lamp", "exit"], "default": "droste", "note": "..."}}
```

`at` is the song time where the options start to differ (0 for an axis that changes the whole
piece); axis and option names are slugs, because they name files; `default` is one of the options.
`build.mjs` refuses a block the tools couldn't use, in one line naming the piece and the axis. The
page gets the choice on every frame as `p.variant = {ending: "lamp"}`, every axis in it (the
default where none was asked for); live mode reads `?variant=ending:lamp`. Before `at`, every
option must draw exactly the same frames: that is what lets one body serve every ending. (A driver
with its own `draw()` must pass `p.variant` on; the harness adds it after `frame()`.)

**Render one option** with `--variant axis=option` (repeat it, or comma-separate, for several axes;
an axis not given is its default). `still.mjs` takes it too, and puts it in the file name
(`template.ending-lamp_15.000.png`). The sidecar records the choice as `variant`. A piece without
`variants` refuses the flag, and an unknown axis or option is refused with the valid ones (exit 2).

**Render every ending at once** with `--endings <axis>`: the window's body once, with the default,
and one file per option from the join on, all with one encoder setting:

```bash
node tools/render.mjs template --song private/songpack.json --t0 0 --dur 16 --endings ending --out out/tpl.mp4
#   out/tpl.body.mp4            frames 0-335 (0-14 s): the body every ending shares
#   out/tpl.ending-droste.mp4   frames 336-383, one file per option, each starting on a keyframe
#   out/tpl.ending-lamp.mp4
#   out/tpl.ending-exit.mp4
#   out/tpl.variants.json       the manifest: the files, their frames, the join, the stream they share
```

The join is the first frame at or after `at`; the window must start before it and end after it.
`--keys` / `--key-times` are forced in whichever file they fall in, on its own clock; `--png-frames`
saves each file's own; every file gets its sidecar (`part`: body or ending). A stateful piece
renders every file from its warm-up, so an ending continues the body's state exactly. Nothing is
moved into place until the whole set checks out (with ffprobe, which comes with ffmpeg): every
option draws the frame before the join as the default does (a piece whose option starts early is
refused before anything renders, naming the frame), every file has the frames planned and starts
on a keyframe, all of them share one stream (codec, profile, level, pixel format, size, frame rate,
time base, SAR and the SPS/PPS), and body + each ending, joined by the concat demuxer, run one frame
apart with no gap. The manifest goes in last, and a set rendered again loses its old one before
anything renders: whatever a failed run leaves, no manifest sits beside parts that aren't its own.

A render of a piece with `variants` restarts its encoder at every join inside its window, so the
whole window rendered once is the same encodes as body + default ending. With the same flags
(`--workers` included) the two decode to identical frames: measured on the template, 16 s at 24 fps,
384 of 384 decoded frames, and CI checks it on every push.

**Delivery** joins them: a cut whose `endings:` names the manifest gets one file per ending,
`<out stem>.<option>.mp4`, the body and that ending stream-copied together (`-c copy`, no second
encode) and muxed from the manifest's `t0` (its `silent_start`) like any render. Next to them,
`<out stem>.endings.jpg` is the contact sheet: one row per ending, the last body frame and then six
frames of the ending, its first and last included, with a red mark at the join.

## Start a new piece

```bash
cp -r pieces/template pieces/my-piece      # rename it in piece.json and template.html, and set TITLE in src/main.js
node tools/synth.mjs my-piece && node tools/build.mjs my-piece --song out/songs/my-piece.songpack.json
node tools/still.mjs my-piece --song out/songs/my-piece.songpack.json --t 1,4,9 --qa   # into out/stills/
```

`piece.json` `"lib"` lists the reusable modules to inline ahead of your own, in order:

| Module | What it gives you |
|---|---|
| `core.js` | math and easing, keyframes (`kf`), deterministic hashes and noise, the grid (`makeGrid`: bars, beats, backbeats, on twos), the envelope sampler (`envAt`, stems too), the song's events (`evList`, `evLast`, `evNth`, `evCount`, `evSince`, `evPulse`, `evChord`: [Events](#events)), sprites and grain tiles, `strokeScale` |
| `live.js` | the stage (a 1080×1920 virtual frame) and `boot()`: the three modes; the live analyser, scaled per band from a pre-scan of the dropped track and delayed by the output latency so picture and sound agree; `voc` measured the way a song pack measures it; the procedural fallback (a just-tuned pad, half-time below 90 BPM); `EV`, the song's events in every mode (live, the fallback's own beat); variants: `boot({ variants })` checks what it is asked for and hands `draw` `flags.variant` (render: `p.variant`, an unknown option stops the render; live: `?variant=axis:option`, an unknown one warns and plays the default); `coverCrop`; the 9:16 safe frame drawn with `?qa=1` (`SAFE_FRAME`, x 65–940, y 269–1248: what Reels, TikTok and Shorts all leave clear, from their margins in `SAFE_MARGINS` — [docs/PLATFORMS.md](../docs/PLATFORMS.md)) |
| `ink.js` | the Flash look: boil on twos, the envelope held on twos (`heldEnv`), stroke-by-stroke draw-on (and erase), a sketchier hand, dry runs, the contact log for `?qa=1`, a hand-lettered alphabet with per-glyph widths and `wordFit` (a title fitted to the frame, one line or two), `glow` |
| `rig.js` | rig v2: two-bone IK, seated bodies built from the floor up, chairs built from the body, planted-feet walks |
| `recursion.js` | vector droste and vector kaleidoscope: recursion by redrawing, crisp at any depth |
| `viewfinder.js` | the viewfinder compositor: split-image focusing, microprism, meter, counter, mirror slap |

Everything else a piece can borrow is in the shipped pieces, indexed by technique in
[docs/TECHNIQUES.md](../docs/TECHNIQUES.md).

### Reserved names

A built piece is one `<script>`: the lib files it lists and its own modules
share one scope, so the lib's top-level names are reserved. Declare one again
(`const seed = 42;` in a copy of the template) and Chromium refuses the whole
script; give a function or `var` a lib function's name and it silently replaces
the lib's, for the lib's own callers too. `tools/build.mjs` compiles the
assembled script and refuses both, naming your file and line and the lib file
that owns the name. It also holds `"lib"` to its load order, each file after
what it needs (core → live → ink → rig → recursion → viewfinder): listed as
`["ink", "core"]`, the lib would die on load with "Cannot access 'TAU' before
initialization". The names, as `node tools/build.mjs --reserved` prints them
(`npm test` fails when this list falls behind the lib):

<!-- reserved names: generated by `node tools/build.mjs --reserved`; npm test checks this block -->
```text
158 top-level names in canvas/lib, by file (a piece that lists the file in "lib" must not declare them):
core.js (45): TAU rad clamp lerp invLerp remap fract ease easeIn easeOut easeInOut step smooth pulse kf hsh hash HS hash2 vnoise fbm mulberry32 makeGrid ENV envInit envAt envAvg evList evBisect evLast evNth evCount evSince evChord evPulse mkCanvas rrectPath curvePath rgba strokeScale SPR glowSprite drawSprite noiseTile overlayTile
live.js (38): Q MODE QA cv ctx MAINCTX withCtx W H S PXW PXH setSize base coverCrop ENV_KEYS envFrom EV variantParse variantResolve SAFE_MARGINS SAFE_FRAME drawSafeFrame afterDraw boot LIVE_FPS LIVE_FFT LIVE_SMOOTH LIVE_GAIN_KEYS LIVE_VOC liveMeasure liveVocPower liveVocContrast livePercentile LIVE_FFT_TABLES liveFFT livePrescan liveMode
ink.js (49): C seed amp ji J boilFrame heldEnv LW DRAWON revealU noDraw drawOn SKETCH DRY measure ink jit trace stroke poly circPts circ ellPts ell rectPts rect rrPts rrect flat arcPts capsulePts glow withAlpha INK_GRAINS paperGrain CONTACTS contact drawContacts contactReport E_ GLYPH GLYPH_TRACK GLYPH_SPACE GLYPH_NONE glyphSpan GLYPH_MISSING word wordW wordFit
rig.js (15): RG ik hairFrontCap hairBack face headSide hand figure item seated seatedLegs chairFor tableSide standPelvisY walkLegs
recursion.js (3): drosteRedraw KALEIDO_BUF kaleidoRedraw
viewfinder.js (8): VFCFG VFL vfLayers shootScene vfRectPath composeVF vfInfo vfTitle
```

## Verified against what shipped

The ports were checked two ways (measured 2026-09-29, Chromium 141):

- **The code.** Built from this folder before the fix below, SAME AS YOU was
  byte-identical to the HTML that shipped, and HAMECHI MANZOR DARE text-identical
  apart from comments. ( - ) was too, apart from comments and one fix (its paper
  grain is now seeded, below). SHOULD I ? had identifiers and comments scrubbed;
  20 of 20 test frames and 8 of 8 covers render PNG-identical to the shipped
  build. Every build now also opens with a credit comment per inlined font.
- **One live-mode fix, render mode untouched.** Clicked without a track, ( - ) and
  SAME AS YOU played one kick and then only the drone, and ( - ), SAME AS YOU and
  SHOULD I ? kept their fallback pad droning under a dropped track. The fix
  touches only live-mode code (11, 13 and 5 changed lines). Rendered before and
  after, 29 of 29 frames and covers across the three pieces are PNG-identical,
  and all 29 differ from one another, so the check isn't trivial. HAMECHI MANZOR
  DARE didn't have either bug and is unchanged.
- **The drivers.** Against frames decoded from the delivered films (H.264, so
  never bit-exact): ( - ) 37.4 / 42.2 / 44.0 dB PSNR at three timestamps (the
  adjacent drawing scores 21.1 dB), SAME AS YOU 38.5 dB (adjacent frame 24.5 dB),
  SHOULD I ? 37.0 dB.
- **Not reproduced:** HAMECHI MANZOR DARE's released reel. The piece is stateful
  and seeded, and the one-off harness that rendered the release wasn't kept; the
  driver here is the generalised harness written right after it. It renders the
  same piece — same mask at frame 60 (28.3 dB) — but by frame 450 the mask
  schedule has diverged.
- ( - )'s paper grain used `Math.random()`, so no two renders matched; it is now
  seeded. Everything else was already deterministic.
- Deterministic on one machine is not the same across machines: HAMECHI MANZOR
  DARE draws its credit line in the system `ui-monospace` font, not an inlined
  one, and switching that font from DejaVu Sans Mono to Liberation Mono changed
  454 pixels of a 1080×1920 frame, all in that line
  ([case study](../docs/case-studies/hamechi-manzor-dare.md#the-port-in-this-repository)).

## Gotchas that cost time

- In the cloud sandbox Chromium is preinstalled at `/opt/pw-browsers/chromium` —
  the tools find it; never run `playwright install` there. Elsewhere, set
  `KALEIDOPHONE_CHROMIUM` or install Playwright's once.
- JPEG capture (`toDataURL('image/jpeg', 0.92)`) is 1.7–3.8× faster than PNG
  across the five pieces at 1080×1920 (measured over two runs, Chromium 141);
  the harness uses it for video and PNG only for stills.
- A file name with `?` or `#` in it must be opened through `pathToFileURL()`, or
  the `?` starts the query string (the tools do; `npm test` checks `?`, `#`,
  spaces and quotes).
- A page error fails the run: an uncaught exception, a failed request, or any
  request that isn't `file:`, `data:` or `blob:` (those are blocked as well)
  stops the render with exit status 1 and the error. A script Chromium refuses to
  parse used to show up as a 30 s timeout. `--allow-page-errors` renders anyway.
- Stateful pieces render in one worker, and every window, a resumed one too,
  replays its history from the warm-up first; `still.mjs` gives each time its
  own fresh page, so `--t 60,70` and `--t 70` agree. Mux the audio at the
  **snapped** `t0` the harness prints (the sidecar's `silent_start`).
- Before 0 s and after the song pack's last frame, the default driver holds the
  first and last envelope values. It used to carry the edge slope on, so a frame
  past the end could read values far outside 0–1.
- Multiply every line width and font size by `strokeScale()` or a 3000 px cover
  goes hairline.
