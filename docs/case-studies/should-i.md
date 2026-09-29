# Case study: SHOULD I ?

**SHOULD I ?** · Sep The Concept, with a second vocalist on the first vocal
part · September 2026 · 3:02 · canvas 2D photography through a film camera's
viewfinder, no source footage

The twelfth release in the series and the fourth canvas piece. It is also a
new medium inside the canvas one: the whole film is seen through the
viewfinder of his 35 mm camera, in silhouettes and rim light rather than
ink. It went from brief to a full kit in one sitting. Then two new masters
arrived the same night: one needed only a re-mux, and one added a spoken
passage and a last vocal line, which gave the film a 37th frame. Its source
is at `canvas/pieces/should-i/`. With the other three canvas pieces it
closes [#42](https://github.com/sep-lab/kaleidophone/issues/42) ("a fully
procedural video with no source footage").

What it proves for the framework: the concept came out of the grid, not the
other way around. It also shows both halves of the master-swap problem: a
check that proves nothing moved
([#49](../TECHNIQUES.md#49-master-drop-in-check)), and one that finds
exactly what did ([#52](../TECHNIQUES.md#52-what-the-new-master-added)).

**What's scrubbed and why:** no lyrics. Nothing sung or spoken is quoted or
paraphrased; this document says "the hook", "the first vocal part" and "the
last vocal line". The second vocalist is not named, and the words of the
spoken passage are not given. No stems, no audio: the repository's copy of
the piece runs on synthetic onsets. Numbers are **measured on the release**
unless marked otherwise.

## The rule: count the grid before inventing anything

The song is 80 BPM with a 3.0 s bar. Count the snares from the drop (54.0 s)
to the bar where the hook asks its question, and there are **exactly 36**:
one 35 mm roll ([#47](../TECHNIQUES.md#47-grid-arithmetic)). So:

- the shutter fires on every snare, and the roll runs out on the hook's bar;
- the rewind is 36 frames at 12 fps, exactly one bar (126–129 s);
- the darkroom develops the contact sheet at one frame per beat, 36 beats
  again (129–156 s);
- and a roll has only 36 frames, so on the last vocal line (179.64 s) the
  counter rolls "?" → 37 ([#53](../TECHNIQUES.md#53-one-past-the-count)).

The numbers the music already contains were the strongest sync available.
The rest of the rules follow from the camera:

1. **We only ever see through his viewfinder** until the roll is rewound. He
   is never drawn, except his hands.
2. **Focusing is deciding.** The split-image circle cuts her in two. It
   hunts through the first vocal part and snaps into focus after each shot.
   Every vocal onset of the hook tears it apart, and the circle grows from
   118 to 250 px until the tear covers her. It locks on the song's strongest
   onset (125.25 s) with a white flash, and once more on the last vocal
   line.
3. **The shutter is the snare, and the meter needle is the music.** The
   counter tells the story: 0 → 1…36 → "36" blinking → "?" → 37.
4. **Dark silhouettes and rim light.** Her blue eye is the only detailed
   thing he ever sees. Red is rationed. Before the darkroom it only passes
   through: a light leak late in her long take, and small accents on four
   frames of the roll (5, 20, 32 and 33: a seal, a runner, a light leak, a
   glow). In the darkroom the safelight turns everything red, and the grease
   pencil is red.

## The track

Final master (v3): 183.775 s, 24-bit, −10.1 LUFS / −0.3 dBTP. It is 80.000
BPM with bar 0 at t = 0 and a 3.0 s bar. Snares and claps sit on beats 2 and
4 (3b + 0.75 s and 3b + 2.25 s), and the percussive onsets land on the 16th
grid within ±20 ms.

| t (s) | Section |
|---|---|
| 0–6 | intro |
| 6–52.5 | the first vocal part (the second vocalist) |
| 54.0 | the drop |
| 54–129 | the artist's part and the hook |
| 129–156 | darkroom. The final master adds a spoken voice message over it (132.5–153) |
| 140–174 | a 16th-note guitar arpeggio, which thins out when the drums drop at 168 |
| 156–168 | instrumental |
| 168–174 | the last bass hits |
| 174–179 | a ringing tail: a D / A / C♯ chord from 176 |
| 179.64 | the last vocal line, after near-silence, with delay echoes at about 180.25, 180.55 and 180.9 |

**A lyric map from the stem**
([#48](../TECHNIQUES.md#48-lyric-map-from-stem)). The vocal was separated
with `audio-separator` and the `Kim_Vocal_2` model (~4 min on 2 cores).
sherpa-onnx Whisper turbo (int8) then transcribed it on 4-, 2- and 1-bar
windows, which gave a clean bar-by-bar map. The onsets are log-spectral-flux
peaks at 200 Hz on the stem. `piece.json`'s `"bake"` turns them into
`const __STUTTER__` at build time, so the live mode has them too. The F0
median per half-bar told the two singers apart (≈280 Hz vs ≈140 Hz). A vocal
envelope (10 ms RMS → clip((dB + 45) / 35)) drives the darkroom's ripples
and safelight.

## What the viewfinder shows

| t (s) | |
|---|---|
| 0–6 | black → title → the viewfinder fades in, far out of focus |
| 6–48 | her long take at a snowy window: her face in the split circle, breath fogging the glass with the vocal, a turn to the lens, a slow push-in |
| 48.2–53.9 | the camera tips and drops into darkness |
| **54.0** | **the drop**: a white flash, and the door, in focus for the first time |
| 54.75 + 1.5(k − 1) | shutter k = 1…36, on the snares |
| 107.25 | shutter 36. The roll is out |
| 107.9–125.25 | the hook: her eye, a message typed and deleted on a phone, a pause, the call screen. The third stutter escalates |
| **125.246** | the halves lock, a white flash, and the counter reads "?" |
| 126–129 | **the rewind**: 36 negatives at 12 fps |
| 129–156 | **the darkroom**: the sheet develops one frame per beat. The red safelight breathes with the voice message (fast attack, 0.35 s release) |
| 156–168 | a red grease pencil hovers over frames 1, 6, 13, 23, 29 and 36, circles 36, and writes SHOULD I ? in the margin |
| 168–176.6 | into frame 36 → her living eye → the aperture closes on the bass hits → black |
| 176.6–179.6 | the counter reads "?" in the dark while the chord rings |
| **179.64–182** | **frame 37**: the viewfinder opens on a doorway lit warm from the room beyond, her face in the split circle. The counter rolls "?" → 37 and focus locks. The last click at 180.08, then a fade from 181.1 to 182.0 |

## How it was built

`canvas/pieces/should-i/src/` holds nine modules:

| Module | Role |
|---|---|
| `00_core.js` | the grid and the shot times, envelope lookup, noise, sprites |
| `10_her.js` | the silhouette rig and the eye |
| `20_props.js` | door, phone, window, snow, rain, skies |
| `30_expo.js` | the 36 exposures (`expoTime(k) = 54.75 + 1.5(k − 1)`), her long take, the doorway of frame 37 (`drawDoorway()`) |
| `40_vf.js` | the viewfinder compositor: `shootScene()`, `composeVF()`, `drawInfo()` |
| `50_film.js` | the rewind, the contact sheet, the darkroom, the grease pencil, the aperture, frame 37 (`drawFinalFrame()`) |
| `60_covers.js` | the cover family (`drawCoverVariant()`) |
| `80_timeline.js` | `vfPlan(t)`: what the lens sees and what the viewfinder shows. Also `jolts()`, `mirrorSlap()` and `renderFrame()` |
| `90_main.js` | the three modes |

**The viewfinder compositor**
([#44](../TECHNIQUES.md#44-viewfinder-compositor)). `shootScene()` draws the
scene through a camera transform (zoom, rotation, handheld shake from
layered noise) and mixes in a quarter-res `filter: blur()` copy according to
the focus error. `composeVF()` puts the result in a 2:3 rect (900×1350
inside the 1080×1920 frame) with ground-glass noise, faint fresnel rings, a
vignette and eyepiece falloff. Above it is an info strip: shutter speed, a
match-needle driven by the RMS or the vocal, and the frame counter. It reads
as "being him" without ever drawing him.

**Split-image sync** ([#45](../TECHNIQUES.md#45-split-image-sync)). The
circle is two clipped half-draws of the scene, shifted ±split. The split is
the focus error plus alternating-sign jolts on the stem's onsets. `jolts()`
gives each onset a pulse with a 16 ms attack and a 100 ms decay, worth 62 px
× onset strength. The third stutter escalates from ×1 to ×2.3, capped at 230
px.

**Mirror slap** ([#46](../TECHNIQUES.md#46-mirror-slap)). `mirrorSlap()`
blacks out only the viewfinder rect, for 55 ms plus a 60 ms return. The info
strip stays lit, and the counter digit slides up. It was verified on the
delivered file with ffmpeg's `signalstats`: YAVG at the snare frame reads
16, which is black.

**Contact sheet = cover** ([#51](../TECHNIQUES.md#51-contact-sheet-cover)).
Each exposure is rendered once, at its capture moment, into a cached 360×540
thumbnail (`expoPhoto()`). The same bitmaps feed the rewind negatives
(`negativeOf()`: difference-invert, an orange multiply, sprockets) and the
six-strip contact sheet. A red grease-pencil circle, plus the title written
in the margin in a marker font, makes the cover.

**The driver.** `driver.mjs` hands the whole song pack to the page once
(`window.__init`), then asks for any *t* (`window.__frame(t, {cardT0})`).
The piece is a pure function of time
([#30](../TECHNIQUES.md#30-pure-function-of-time)), so windows render in
parallel. Covers go through `window.__draw(name, arg)`. With
`render.mjs --card`, the piece holds the title over the viewfinder for the
window's first 1.2 s. **Performance** (2 cloud cores, two workers): 90–140 s
took 256 s and 140–182 s took 285 s. The darkroom is the heaviest part, at
~3 fps per worker.

## Three masters, one night

**First bounce → final master: prove nothing moved**
([#49](../TECHNIQUES.md#49-master-drop-in-check)). Before re-rendering
anything, the new WAV was compared with the one that had been analyzed.
Log-envelope cross-correlation in 8 s windows, every 4 s, gave a local lag
of 0.00 s everywhere: the same grid. The 350–3400 Hz envelope correlation
per section at lag 0 was 0.65–0.95: the same vocal takes, so the
onset-driven choreography still held. That was true even though the
arrangement after the drop had changed (full-mix correlation 0.2–0.6). The
result was a re-mux only. It is a working prototype of the landmark-drift
guard on [the roadmap](../ROADMAP.md). This master (−9.3 LUFS, −0.3 dBTP)
still delivered −0.2 dBTP at −2.5 dB of gain, and −3.5 dB brought every cut
to ≤ −1.4 dBTP ([#50](../TECHNIQUES.md#50-aac-guard-per-master)).

**Final → final-final: find what was added**
([#52](../TECHNIQUES.md#52-what-the-new-master-added)). The old and new
vocal-stem envelopes were compared bar by bar using two numbers: the mean
absolute difference, and a "new voice" fraction (new > 0.35 while old <
0.15). ASR then ran only on the bars that changed. That found the spoken
message over the darkroom (132.5–153), ad-libs removed at 156–159, and the
last vocal line at 179.64. The instrumental stem was checked the same way
(HPSS, onsets per 16th slot, chroma per beat), which is how the outro's
guitar arpeggio showed up. ASR was unreliable on the message, and none of it
went on screen. The film grew from 180 to 182 s, and the safelight now
breathes with the voice. Part A (0–90 s) was reused as it was, because a
keyframe had been forced at 90 s. Part B was re-rendered and concatenated,
giving 4368 frames and 182.000 s.

## Delivery (v3)

Keyframes were forced at 0, 53, 90 and 114 s (`keyframes` in `piece.json`),
so every cut is a `-c:v copy` on the machine that holds the audio. The
reel's signature card is its own 48-frame segment (51–53 s),
stream-concatenated in front of the film from the keyframe at 53 s. That way
the full film never carries a mid-film title.

| Cut | Window (s) | Frames | Delivered (ebur128, true peak) |
|---|---|---|---|
| full, 3:02 | 0 → 182 | 4368 | −13.1 LUFS / −1.9 dBTP · 90.6 MB |
| reel, 2:11 | 51 → 182: card + film from 53 | 3144 (48 + 3096) | −12.4 / −2.4 · 77.9 MB |
| story 1, 55.5 s | 0 → 55.5, the first vocal part | — | −16.1 / −3.2 |
| story 2, 15 s | 114 → 129 | — | −12.2 / −2.2 |

**The AAC guard was measured again.** v3 is quieter than the master before
it: a plain AAC encode gave −2.3 dBTP at −3.5 dB and −1.9 dBTP at −3.0 dB,
so it shipped at −3.0 dB. **Sync:** the delivered audio was cross-correlated
against the WAV. The full film and the reel came out at 0.0 ms. Story 2 came
out at +21 ms, the AAC encoder's 1024-sample priming, which
`-avoid_negative_ts make_zero` left in on a cut that already started on a
keyframe. It is imperceptible; drop the flag.

**Covers** ([#54](../TECHNIQUES.md#54-cover-variant-family)). The main cover
is the contact sheet, with a circle on 36 (the eye) and the title in the
margin. The others come from one draw function,
`drawCoverVariant({v, k, ks, keep})`. They circle a different frame (29, 27,
33), draw three circles each with a "?", cross out most frames and keep one,
or lay a print of frame 37 on the sheet with the title on its border. One
browser session rendered them all at ~3 s per 3000² PNG; in this repository
that is `still.mjs --cover all`.

**QA frames checked** on the delivered film: 139.1 · 156.5 · 163 · 171 ·
177.8 · 179.8 ("37" in focus) · 180.1 (the click) · 181.0 · 181.9.

## What went wrong

- **Glyphs on a stroke merge into it.** A "?" placed on a circle's stroke
  disappears into it. Glyphs go outside the stroke.
- **Big microprism tiles read as a glitch.** 15 px tiles looked digital; 9
  px tiles plus a 6 px dot lattice read as glass.
- **A "?" in the file name breaks file URLs.** It starts a query string
  unless the URL is built with `pathToFileURL()`. `pieceUrl()` in
  `canvas/tools/lib/common.mjs` keeps the note.
- **The master kept changing.** There were three masters in one night. The
  answer was not a faster render but two cheap checks run before any render.

## The port in this repository

**Measured on the port:**

- SHOULD I ? renders 20/20 test frames and 8/8 covers PNG-identical to the
  shipped build.
- Against frames decoded from the delivered film, the repository driver
  reproduces it at 37.0 dB PSNR.
- The synthetic twin places generated vocal windows and stutter onsets where
  the real ones fall (`voc` and `events.stutter` in `synthetic.json`), so
  the split-image jolts land in the right bars without the real stem.

## What it contributed

New:

- [#44 Viewfinder compositor](../TECHNIQUES.md#44-viewfinder-compositor)
- [#45 Split-image sync](../TECHNIQUES.md#45-split-image-sync)
- [#46 Mirror slap](../TECHNIQUES.md#46-mirror-slap)
- [#47 Grid arithmetic](../TECHNIQUES.md#47-grid-arithmetic)
- [#48 Lyric map from stem](../TECHNIQUES.md#48-lyric-map-from-stem)
- [#49 Master drop-in check](../TECHNIQUES.md#49-master-drop-in-check)
- [#50 AAC guard per master](../TECHNIQUES.md#50-aac-guard-per-master)
- [#51 Contact sheet cover](../TECHNIQUES.md#51-contact-sheet-cover)
- [#52 What the new master added](../TECHNIQUES.md#52-what-the-new-master-added)
- [#53 One past the count](../TECHNIQUES.md#53-one-past-the-count)
- [#54 Cover variant family](../TECHNIQUES.md#54-cover-variant-family)

Re-derived, not new: the
[three-mode piece](../TECHNIQUES.md#19-three-mode-piece), the
[deterministic render harness](../TECHNIQUES.md#21-deterministic-render-harness),
[forced keyframes](../TECHNIQUES.md#41-forced-keyframes) with cuts and mux
where the audio lives, and the
[signature card](../TECHNIQUES.md#16-signature-card), here as a separate
segment.
