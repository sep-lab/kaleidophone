# Case study: ( - )

**( - )** ("minus", the gap) · Sep The Concept · September 2026 · 2:58 ·
canvas 2D ink cartoon, no source footage

The tenth release in the series and the second canvas piece, after
[HAMECHI MANZOR DARE](hamechi-manzor-dare.md). It is a Flash-style cartoon,
ink on paper, drawn by code on an HTML canvas from the song's own envelope.
No photograph, clip or frame of anyone went into it. Its source is in this
repository at `canvas/pieces/minus/`. Together with the other three canvas
pieces it closes [#42](https://github.com/sep-lab/kaleidophone/issues/42)
("a fully procedural video with no source footage").

What it proves for the framework: it was built on a 1:46 demo and re-fitted
to the 2:58 final master the same night with zero re-architecture. The piece
is a pure function of time and envelope, so a new master on the same grid
cost one constants edit and one render. That is
[ADR-0001](../decisions/0001-version-the-brief-not-the-render.md)'s "version
the brief, not the render" taken literally.

**What's scrubbed and why:** the lyrics are the artist's unreleased writing.
They were never on screen and they are not quoted or paraphrased here. The
real envelope pack is derived from unreleased audio, so the repository ships
a synthetic twin instead: `canvas/pieces/minus/synthetic.json` keeps the
real grid and section levels and generates everything else
(`canvas/tools/synth.mjs`). What's kept is the grid, the scene timings, the
technique and the measured numbers. Numbers are **measured on the release**
unless marked otherwise. The audio is private, so they can't be re-run from
here.

## The rule that makes the film

The brief: a man's ordinary day, and the absence of his partner in every
scene of it, in "Flash quality". The answer is one rendering rule.

**She is never drawn.** Wherever she would be, the picture is cut back to
bare paper. Her rig is drawn last, as a paper-filled silhouette with no
outline, so anything that enters it stops: his hand at the crossing (to the
wrist), a flower head held out at a door, his arm along the sofa's backrest,
a blanket that ends where she begins.

In code it is one flag. `fig({ ..., sil: true, she: true })` in
`canvas/pieces/minus/src/00_piece.js` swaps the ink for the paper color,
widens every stroke 2.6× and fills the head and body. Each scene draws it
after everything it has to cut.

Four smaller rules hang off it:

1. The world comes in pairs, and he is the only "one". Couples pass behind
   him.
2. A gesture made out of habit is followed by a held frame, and then he
   notices.
3. The title's dash recurs everywhere.
4. It is one day, looped, and the moon and the sun are the same paper as
   her.

## The look: Flash, on purpose

- **On twos.** `stepT()` quantizes time to 12 drawings a second
  (`DRAW_FPS = 12`). The release rendered 12 drawings per second and let
  ffmpeg double them to 24 fps.
- **Boil.** Every point of every polyline is jittered by a hash seeded from
  the drawing number (`hsh()`, `J()`), about 1.4 px at 1080 wide. The
  amplitude follows the song (`amp = 1.1 + 1.4 × rms`), so the lines crawl
  twelve times a second and crawl harder when it's loud.
- **Flat.** Round caps and joins, flat fills, no gradients. Three grays,
  paper, ink and one red (the `C` palette).

It is cheap to render, and the crudeness reads as intentional.

## The track

The final master, analyzed with numpy into a 100 Hz envelope pack (17,792
frames):

| | |
|---|---|
| Length | 177.6 s (2:58), 48 kHz / 24-bit stereo, mastered hot (~−8.5 dB RMS) |
| Grid | 100 BPM 4/4, first downbeat 5.95 s, bar 2.4 s, 69 full bars |
| Phrase | 8 bars = 19.2 s, one scene each |
| Bass-heaviest stretch | bars 46–57 (116–143 s) |
| Loudest 60 s | starts at 77.95 s |
| Fade-out | from ~166.75 s to silence at 177.6 s |

The demo it was first built on had the same grid (100 BPM, first downbeat
5.95 s). That is the whole reason the re-fit was free: the day grew from
five scenes to eight plus a coda, and nothing else moved.

## Scene timeline

Scene *n* starts at 5.95 + 19.2·*n*. `drawFrame(t, env, card)` picks the
scene from `SCENES` by that arithmetic, and each scene function is a pure
function of its local time and the envelope.

| t (s) | Scene | What happens |
|---|---|---|
| 0–5.95 | title | "(", ")" and "-" drawn by hand |
| 5.95 | sunrise | a rooftop, from behind. He points, turns to her void, and his arm sinks |
| 25.15 | crossing | from the front. His open hand enters the void to the wrist while couples pass |
| 44.35 | umbrella | rain of short strokes, none under the canopy. At bar 2 he tilts the umbrella over her and the rain hits him |
| 63.55 | flower | an evening street, then a hall: the flower held into the void at the door |
| 82.75 | two plates | a lamp cone. A plate is pushed and pulled on the hits, and he carries it out at bar 7 |
| 101.95 | sofa | TV flicker from behind the camera and a framed photo of two on the wall. His arm runs along the backrest and vanishes into her shoulder. One blanket covers both laps |
| 121.15 | gallery | a bed from above, the phone the only light. Thumbnails land on the beats and she is paper in every photo. The phone locks at bar 7 |
| 140.35 | night window | the sunrise's rhyme: a paper moon, a street lamp that flickers and dims from bar 3, his palm on the glass at bar 4 |
| 159.55 | coda | the sunrise again at 1.6× speed with no pointing, fading to black from 171 to 177.2 |

## How it was built

**One file, three modes.** This is the
[three-mode piece](../TECHNIQUES.md#19-three-mode-piece) pattern from
[HAMECHI MANZOR DARE](hamechi-manzor-dare.md). The piece is `template.html`
plus one module, `src/00_piece.js`. `canvas/tools/build.mjs` inlines it into
`canvas/dist/minus.html`, a single file that makes no external requests.

- **live** (no query): click for a procedural pad with a sub hit on every
  bar (`procedural()`). Or drop the WAV on it, and an AnalyserNode drives
  bass/mid/high/rms/flux through a slow automatic gain. It loops forever.
- **render** (`?render=1&w=&h=`):
  `window.__frame({t, bass, mid, high, rms, flux, card})` draws exactly one
  frame.
- **cover** (`?cover=1&size=3000`): `window.__cover(variant)` draws one
  scene at a chosen moment onto a square canvas through
  `ctx.setTransform(k, 0, 0, k, 0, −top·k)`. `top` comes from a per-variant
  `CROPS` table (0.15–0.36 of the portrait height). The square cover is a
  crop of the portrait composition, so the stroke weight stays the
  portrait's ([#31](../TECHNIQUES.md#31-square-cover-crop)).

**The driver.** `canvas/pieces/minus/driver.mjs` is a few lines. The piece
takes the envelope per frame, so the default driver in
`canvas/tools/lib/common.mjs` is exact: it samples the 100 Hz pack by linear
interpolation. The driver only adds the cover mode. `piece.json` holds the
grid, the render settings (1080×1920, CRF 18, `-tune animation`) and the
delivered cut windows. The signature card is a per-frame `card` flag, which
the release harness set on the first 2.4 s of each cut.

To run it on the synthetic twin (needs Node 20+, ffmpeg and a Chromium;
these commands were run while writing this):

```bash
cd canvas && npm ci
node tools/synth.mjs minus      # out/songs/minus.songpack.json: the real grid, generated detail
node tools/build.mjs minus      # dist/minus.html
node tools/render.mjs minus --song out/songs/minus.songpack.json \
     --t0 77.95 --dur 62.4 --fps 12 --out-fps 24 --out reel_silent.mp4
node tools/still.mjs minus --song out/songs/minus.songpack.json --cover all
```

**Rendering.** The silent render ran on a 2-core cloud machine: the whole
track, 2131 drawings at 1080×1920, in 238 s. The envelope pack was computed
where the WAV lives, and the audio was muxed there too, so the WAV never
moved.

## Delivery

| Cut | Window (s) | Notes |
|---|---|---|
| reel, 62.4 s | 77.95 → 140.35 | the loudest minute plus a bar: a 2.4 s signature card over bar 30, then the flower's last bar → plates → sofa → gallery → the phone lock. Audio fades in over 0.4 s and out over 1.5 s. 17.8 MB |
| story, 58.85 s | 118.75 → 177.6 | card, then gallery → night window → coda. It ends on the song's real fade-out. 12.1 MB |
| full, 2:58 | 0 → 177.6 | vertical, the whole track. 43.8 MB |
| covers, 3000² | — | four square crops of portrait scenes. Plates is the main cover and the only one with red; sunrise and window are alternates; title is the avatar |

Audio was muxed with `loudnorm` to −14 LUFS / −1 dBTP into AAC.
`-dn -sn -map_metadata -1` on the mux drops the WAV's chapter/text track,
which otherwise turns up as a third data stream in the delivered file.

## What went wrong

- **A primitive lied.** The first `capsule()` drew its end caps on the wrong
  sides, so every torso was an S-shaped blob. A still caught it before any
  render, and the current `capsule()` comments say which cap goes where. The
  lesson: check a primitive with a still before trusting it
  ([#32](../TECHNIQUES.md#32-rig-primitives)).
- **The void is wider than the body.** The silhouette is 2.6× strokes plus
  hanging arms. A "reach in" staged without measuring swallowed a whole arm
  instead of a hand. Measure the cut-out before choreographing contact with
  it ([#28](../TECHNIQUES.md#28-paper-cut-out)).
- **The chairs don't fit.** This was the artist's one complaint: seated
  bodies and their chairs didn't agree. `fig()` is forward kinematics (joint
  angles from the hips, with the hips placed by hand), so nothing forces a
  body and its chair to touch. The fix needed a new rig, built for the
  sequel. See [SAME AS YOU](same-as-you.md), techniques #33–#35.
- **Not bit-reproducible, as shipped.** The paper-grain tiles were generated
  with `Math.random()` at page load (`makeGrain()`), so two renders of the same
  frame differed by a faint grain pattern. Measured on two 540×960 stills of the
  same *t*: a mean absolute difference of 1.4/255, max 8/255. The repository's
  copy seeds that generator (the one code change in the port), so its renders
  now repeat exactly, like SAME AS YOU's.

## The port in this repository

**Measured on the port:**

- The repository build of `canvas/pieces/minus/` is text-identical to the
  shipped HTML apart from comments and the seeded grain above.
- Against frames decoded from the delivered film, the repository driver
  reproduces ( - ) at 37.4 / 42.2 / 44.0 dB PSNR. An adjacent frame scores
  21.1 dB, so the port lands on the right drawing. *Inferred:* the remaining
  gap is the delivered file's compression plus the grain, which was random in
  the shipped render.

## What it contributed

New:

- [#28 Paper cut-out](../TECHNIQUES.md#28-paper-cut-out)
- [#29 On twos and boil](../TECHNIQUES.md#29-on-twos-and-boil)
- [#30 Pure function of time](../TECHNIQUES.md#30-pure-function-of-time)
- [#31 Square cover crop](../TECHNIQUES.md#31-square-cover-crop)
- [#32 Rig primitives](../TECHNIQUES.md#32-rig-primitives)

Re-derived, not new: the
[three-mode piece](../TECHNIQUES.md#19-three-mode-piece), the
[deterministic render harness](../TECHNIQUES.md#21-deterministic-render-harness)
(re-written from notes in about 90 lines),
[JPEG capture](../TECHNIQUES.md#27-jpeg-capture), the
[signature card](../TECHNIQUES.md#16-signature-card) as the reel's first
frame, and bar-snapped cut windows muxed with the audio where the WAV lives
([#5](../TECHNIQUES.md#5-on-device-rendering)).
