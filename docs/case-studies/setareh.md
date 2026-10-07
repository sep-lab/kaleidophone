# Case study: SETAREH

**SETAREH** · Sep The Concept · October 2026 · 3:38 · canvas 2D long-exposure
photography, no source footage

The thirteenth release in the series and the fifth canvas piece. Each 60-second
cut is one long-exposure photograph, developing live: the sky turns one step on
every snare, 32 snares close the star trails into rings on the beat the shutter
closes, and everything that moves leaves only its light. It was built with this
repository's own v0.4.0 tools (its render sidecars name kaleidophone-canvas
0.4.0, Chromium 141 and two workers) and delivered as two cuts and eighteen
covers. Its source is at `canvas/pieces/setareh/`.

What it proves for the framework: a counted rule works again
([#47](../TECHNIQUES.md#47-grid-arithmetic)), this time as geometry (32 steps of
11.25° make one turn) instead of a counter. The canvas engine holds a
photographic medium — a picture that is the *integral* of light over time —
with only `core.js` and `live.js` of the lib. And the harness's sidecar makes a
release landable: the piece came into the repository as a copy of its folder
(the [`KALEIDOPHONE_PIECES` route](../../canvas/README.md#private-pieces-kaleidophone_pieces)),
not a port, and rebuilt the HTML that shipped byte for byte.

**What's scrubbed and why:** no lyrics, and nothing sung is quoted or
paraphrased; no credits beyond the artist's; the story the picture was made for
is not told. `piece.json` and this page say what the picture does (the two
silhouettes are "the figure on the left" and "the figure on the right"); the
source's comments still call them him and her, as SHOULD I ?'s do, and describe
the silhouettes' drawn hair and clothes, but say nothing of who they are or why.
No stems, no audio, no real song pack: the
repository's copy runs on a synthetic twin. Numbers are **measured on the
release** unless marked; those marked **measured on the port** were taken on
the code in `canvas/pieces/setareh/`, which you can run.

## The rule: one exposure

Everything that moves leaves only its light; only what stays, stays.

1. **Every star moves except one.** The pole star never draws a trail, and
   because its light piles up in one place it is the only star that keeps
   getting brighter: halation, a glow and four diffraction spikes that grow
   with the light so far.
2. **The count closes the circle.** The sky turns one step on every snare;
   32 snares × 11.25° = 360°, so the trails close into rings exactly when the
   shutter closes on the 32nd snare
   ([#57](../TECHNIQUES.md#57-the-count-closes-the-circle)). Each step is fast
   at the snare and slow after it, so a ring comes out as 32 dashes, like the
   centre line of an empty road.
3. **Every sung line is a shooting star, and it stays.** Together they radiate
   from the pole star as rays
   ([#60](../TECHNIQUES.md#60-a-meteor-per-sung-line)).
4. **Cars leave only their light.** The valley's three highways are polylines
   on a ground plane; cars run along them at a steady ground speed (so on
   screen they rush near and crawl at the range) and only their trails are
   recorded: the roads look empty. Likewise a plane's two navigation lights and
   its strobe on every beat, and the moon's broad trail.
5. **A figure is kept as much as it stayed.** Two silhouettes sit in armchairs,
   seen from behind. The one on the left never moves, so the exposure keeps all
   of it. The one on the right is drawn as the poses it held, each as opaque as
   the share of the sky's light it blocked while it held it
   ([#58](../TECHNIQUES.md#58-occupancy-ghost)): in the night cut it leans and
   stays; in the dawn cut it gets up and goes, and the dawn coming up behind it
   washes it out.

## The track

218 s. The envelope pass detected 128 BPM and noted that the other octave, 64
BPM, scores 0.87 of it; the piece counts at 64 (a snare every two beats). It
placed bar 1 at 0.010 s with a confidence of 0.55 and a warning ("nothing in
the audio marks the bar clearly"); the grid fits within 4 ms in all 13 sections
that have a pulse (all measured, from the pass's log). The piece doesn't depend
on bar 1: it counts snares, and falls back to the grid's backbeats.

What the base pack doesn't have, the piece reads from an events pack
(`events.setareh`) added by hand: **116 snares** over the song, **32 line
onsets** (16 in each cut), four cue times (the moon's rise, the dawn, the
leaving, and a lean that nothing reads: the night pose is fixed in the code) and a
vocal-stem envelope, `vstem`, that breathes the pole
star by 6 % (counts measured from the pack). Within a cut the 32 snares fall
1.865–1.921 s apart (night) and 1.866–1.886 s apart (dawn): two beats at 64
BPM, with a human's spread. The pass that produced the events pack was not kept,
so a new master can't re-derive it; the cue times also live in the source as
constants, as fallbacks.

| Cut | Opens | Closes (the 32nd snare) | Cues |
|---|---|---|---|
| night | 13.75 s | 72.181 s | the moon begins to rise behind the figures, 63.70 s |
| dawn | 89.99 s | 149.051 s | the dawn light lifts the sky, 131.14 s; the figure on the right leaves, 138.45 s |

Each cut is 1439 frames at 24 fps, 59.958 s: just inside the 60 s a story
allows. They are two separate renders, not slices of one
([#61](../TECHNIQUES.md#61-cut-aware-piece)). No full-length film was made.

## How it was built

`canvas/pieces/setareh/src/` holds eight modules, 56,071 bytes of source:

| Module | Role |
|---|---|
| `00_data.js` | the rule, the grid, the two cuts and their cues, the palette, 950 seeded stars, the land and the people's constants |
| `10_expo.js` | `expo(open)`: the 32 steps of the sky, the light integrals, the sky buffer, the meteors |
| `20_lights.js` | star trails and their cache, the pole star, meteors, the moon, a plane, the city and its cars |
| `30_land.js` | the range, the cone and its snow, the valley floor, the hill |
| `40_people.js` | the silhouettes and chairs, the occupancy ghost, the rim light, each era's lights with the figure cut out |
| `50_film.js` | grain that settles, the vignette, the shutter curtain |
| `60_covers.js` | six cover variants in three formats |
| `90_main.js` | the frame, and the three modes |

**The exposure** ([#56](../TECHNIQUES.md#56-exposure-as-an-integral)). The
moon and the dawn are tabulated at 100 Hz as running sums, so the light that
arrived over any span is two lookups; the sky is a 108×192 buffer in linear
light, tone-mapped with 1 − exp(−2.7 v) and scaled up.

**The trails** ([#59](../TECHNIQUES.md#59-deterministic-accumulation-cache)). A
finished step of the sky never changes, so each era keeps a bitmap of its
finished steps, extended one step at a time: an accumulating look that is still
a pure function of time, and splits across workers.

**The film** ([#62](../TECHNIQUES.md#62-settling-grain-and-the-shutter-curtain)).
Grain runs 0.26 → 0.10 as light gathers and freezes at 0.085 when the shutter
closes; the shutter is a two-frame curtain.

**The driver.** `driver.mjs` hands the whole pack to the page once
(`window.__init`: the events, the `vstem` envelope) and asks for any *t*;
`--flags '{"open":13.75}'` is the exposure's opening. The piece has no
signature card: its source has none, so `render.mjs --card` does nothing here,
and the cuts open on the exposure itself.

**Render settings** (the sidecars, measured): 1080×1920, 24 fps, two workers,
JPEG capture at q0.92, libx264 CRF 17 with `tune film`. The release's own render
time was not recorded. **On the port** (measured, an Apple M1 Pro with Node and
ffmpeg running as x86_64 under Rosetta): 96 frames at 1080×1920 from the start of the
night cut, two workers, at 11.6 fps (8.3 s); the same count at the end of the
cut, including the cold start of the trail cache, at 12.5 fps (7.7 s). A whole cut
is about two minutes at that rate (inferred).

**Covers.** Six variants — *night*, *dawn*, *before* (the moment before the
shutter opens), *rays* (only the sung lines), *close*, *written* (the title
written in light) — in three formats: 3000×3000, 1080×1920 and 1080×1350, 18
files. Each format is composed on its own (`coverView` sets a stage point and a
zoom per format) rather than cropped from the square. `tools/still.mjs` draws
the square only, since it doesn't pass a format on;
`canvas/pieces/setareh/covers.mjs` draws all 18 in one browser session, a fresh
page for each cover (31 s on the port, measured).

## Delivery

| Cut | Song window | Frames | Delivered (ebur128, true peak) |
|---|---|---|---|
| night, the story | 13.75 → 73.71 s | 1439 | −13.0 LUFS / −3.0 dBTP · 83.9 MB · 11.2 Mb/s |
| dawn, the reel | 89.99 → 149.95 s | 1439 | −12.9 / −3.0 · 84.8 MB · 11.3 Mb/s |

Both are H.264 High with no B-frames, AAC-LC 48 kHz stereo at 256 kb/s, and
59.969 s long when edit lists are ignored (measured on the delivered files).

They were made with a hand-written `mux.sh`, not `kaleidophone deliver`, which
stream-copies the render and encodes AAC with ffmpeg's own encoder. The script
re-encoded the picture (CRF 19, no B-frames, capped at 11 Mb/s with a 22 Mb
buffer) because the CRF-17 silent renders were already 101.8 MB (dawn) and
97.4 MB (night) before any audio (measured), against Instagram Stories' 100 MB;
with the cap, each file is under it and under 60 s even where edit lists are
ignored (both cited from the script's comments). It used
AudioToolbox's AAC at one gain of −3 dB, because ffmpeg's own encoder overshot to
+0.9 dBTP on this master at −3 dB where the other measured −3.0 (both cited from
the script's comments), and cut the audio one frame short of the picture so the
encoder's priming fits in that frame
([#50](../TECHNIQUES.md#50-aac-guard-per-master) says why the guard is measured
per master). Everything the script did that `deliver` can't yet is on
[the roadmap](../ROADMAP.md) (M3, deliver v2).

## What went wrong

- **A sprite cache key used for two colours.** `glowSprite` memoises by key, and
  the pole star's halation and the moon's halo both ask for `'hal'`, in
  different colours ((255, 120, 70) and (255, 130, 80)). Whichever a page draws
  first decides both: a page whose first frame is after the moon's cue
  (63.70 s in the night cut) gives both halos the moon's colour, one that starts
  earlier gives both the pole star's, so the same frame comes out differently
  depending on what the page drew before it. Measured on the port, the frame at
  71.667 s drawn alone and drawn after three earlier frames differs in 14,587 of
  2,073,600 pixels by at most 2 of 255, all in the two halos (x 442–1000,
  y 424–1066). Each order is self-consistent (a frame drawn alone twice, and the
  same four frames twice in order, are byte-identical), and giving the moon's halo
  a key of its own makes alone and in-order identical (measured, in a scratch
  copy). The delivered film is not affected: a render worker starts before the
  moon, so the first sprite is always the pole star's (inferred from how
  `render.mjs` splits a window: the second of two workers starts at 43.7 s). In a
  fresh page, the covers that draw the moon (*night* and *written*) give both halos
  its colour and the other four the pole star's, and the gallery clip and CI's
  one-second render, which start after the moon's cue, carry the moon's. The piece
  is frozen, so the fix is not applied. Anything that renders frames of it for a
  hash (the golden frames) must fix the order or open a fresh page per frame, as
  `covers.mjs` and `still.mjs` do, and a module built from this code should give
  every sprite a key of its own.
- **A twin that thins at random.** The synthetic twin's event windows thin a
  16th grid at random, so one window per cut at the backbeat rate gives 23–47
  snares, 0.1–12.6 s apart (measured over 20 seeds). In 11 of the 20 a window
  held fewer than 32, and the piece then ignores them all; in the rest the
  night cut's 32nd snare fell between 53.9 s and 72.8 s against the real
  72.181 s, so the shutter closed up to 18 s early. The twin therefore has no
  snare events, and the piece counts the grid's backbeats: closes at 72.1975 s and 149.0725 s, 16.5 ms and 21.5 ms after the
  real ones (measured on the port). It has line windows (15 and 17 meteors in the
  two cuts, against 16 and 16) but no `vstem`, so the pole star's breath reads 0.
- **A cover renderer that only worked in one sandbox.** `covers.mjs` had the
  cloud's Chromium path hard-coded, listed a variant that doesn't exist and left
  out two that do; in this repository it uses the tools' own launcher and lists
  the six real ones.
- **The events pass wasn't kept**, and bar 1 is a guess (confidence 0.55). A new
  master can be checked with `kaleidophone master-check`
  ([#49](../TECHNIQUES.md#49-master-drop-in-check)), but its events would have to
  be found again by hand.
- **The grain sets the bit rate.** Both delivered cuts sit at the 11 Mb/s cap:
  they are rate-limited, not CRF-limited
  ([#62](../TECHNIQUES.md#62-settling-grain-and-the-shutter-curtain)).

## The port in this repository

**Measured on the port** (2026-10-07, Chromium 141, the real events pack kept
private):

- **The code.** Built with the real pack from the release's own source, with the
  fonts pinned below, the page was byte-identical to the HTML that shipped
  (188,124 bytes, sha256 `7698e6c0…`). The copy in the repository differs from
  that in 14 comment lines, which say what the picture does instead of what it was
  made for; the code before any `//` on every changed line is identical. 12 of 12
  test frames and 6 of 6 square covers render PNG-identical to the shipped build.
- **The fonts.** `@fontsource/cormorant-garamond` and
  `@fontsource/mrs-saint-delafield` 5.3.0, pinned in `canvas/package.json` with
  Barlow Condensed: their woff2 files are byte-identical to the ones in the
  shipped page. Older versions are not (checked: Cormorant Garamond 5.2.7, Mrs
  Saint Delafield 5.2.5). Their SIL OFL licences are published with the gallery,
  like every inlined font's.
- **The driver.** Against frames decoded from the delivered films (H.264, so
  never bit-exact): 35.2–44.8 dB PSNR over 12 frames, 7 of the night cut and 5 of
  the dawn. The piece changes slowly, so a neighbouring frame scores only about a
  dB lower and PSNR can't pin the offset; the shutter curtain can: its two frames
  (night 1403 and 1404) match their own delivered frames at 44.8 and 38.2 dB and
  their neighbours at 13–21 dB. All 18 covers: 38.2–47.9 dB against the delivered
  JPEGs (q93).
- **The twin.** `canvas/pieces/setareh/synthetic.json` has the real tempo, first
  downbeat and five section boundaries, levels as [mean, p95, max] to 0.05
  (`synth.mjs --twin`, which re-measures to the same file), and eight windows in
  which generated line onsets are born. CI renders one second of it at
  `gallery.t0`, and the gallery shows six seconds from 67.7 s: the last rings
  closing, the shutter, and the held photograph (a 2.3 MB WebP at q50; the grain
  keeps it large). Its sha256 is pinned in `canvas/test/synth.test.mjs`.
- **The contract.** The page built from the twin (186,304 bytes) and the twin
  itself are pinned in `canvas/test/contract.test.mjs`, with `"libVersion":
  "0.4.0"`: the lib it was built with, which the build reproduces byte for byte.
  Eight golden stills (six frames and two covers, recorded on Linux CI) hold its
  pixels. The frames are the first at 17.9 s, the plane's at 36.3 s, the moon's at
  66.0 s, the shutter curtain's at 72.208 s, the finished photograph at 73.083 s
  and the figure leaving at 139.958 s: all inside the two cuts, drawn in that
  order on one page, which the sprite flaw above makes part of the recording.

## What it contributed

New:

- [#56 Exposure as an integral](../TECHNIQUES.md#56-exposure-as-an-integral)
- [#57 The count closes the circle](../TECHNIQUES.md#57-the-count-closes-the-circle)
- [#58 Occupancy ghost](../TECHNIQUES.md#58-occupancy-ghost)
- [#59 Deterministic accumulation cache](../TECHNIQUES.md#59-deterministic-accumulation-cache)
- [#60 A meteor per sung line](../TECHNIQUES.md#60-a-meteor-per-sung-line)
- [#61 Cut-aware piece](../TECHNIQUES.md#61-cut-aware-piece)
- [#62 Settling grain and the shutter curtain](../TECHNIQUES.md#62-settling-grain-and-the-shutter-curtain)

Re-derived, not new: the
[three-mode piece](../TECHNIQUES.md#19-three-mode-piece), the
[pure function of time](../TECHNIQUES.md#30-pure-function-of-time), the
[deterministic render harness](../TECHNIQUES.md#21-deterministic-render-harness),
the [cover family](../TECHNIQUES.md#54-cover-variant-family) (every cover is a
frame of the piece), and the AAC guard measured per master.
