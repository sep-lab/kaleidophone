# Case study: SAME AS YOU

**SAME AS YOU** · Sep The Concept · September 2026 · instrumental · 2:18 ·
canvas 2D ink cartoon, no source footage

The eleventh release in the series, the third canvas piece, and the sequel
to [( - )](minus.md). In ( - ) she was never drawn. Here she is, on the
other half of the same torn page, doing the same things at the same time. It
went from brief to a full kit in one day on a 32-bit float pre-master. The
final master arrived the same night and changed four passages; only those
bars changed in the picture. Its source is in this repository at
`canvas/pieces/same-as-you/`. With the other three canvas pieces it closes
[#42](https://github.com/sep-lab/kaleidophone/issues/42) ("a fully
procedural video with no source footage").

What it proves for the framework: it answers the one complaint about ( - )
with a rig whose contacts are measured, not eyeballed. It is also the
cleanest run of the pure-function-of-time idea: a reel that loops on its own
first frame, lossless cuts from one render, and a master swap that redrew
only what changed.

**What's scrubbed and why:** the track is instrumental, so there are no
lyrics to leave out. The brief's own words about the story are paraphrased.
The unreleased audio stays out, and the repository ships a synthetic twin of
its envelope (`synthetic.json`) instead. File hashes and posting plans are
omitted. Numbers are **measured on the release** unless marked otherwise.

## The rule: one page, torn down the middle

The brief: a follow-up to ( - ) with the same vibe, but more trippy. They've
broken up and are still looking for each other. It's raining, and both of
them are at the window. Each tries someone new who doesn't look the same,
and it feels like being ghosted. 120 BPM, about a minute of focus, and the
only text is the title, in English.

The answer: **his half-world on the left, hers on the right, mirrored,
differing only in the people.** Every scene is one thing torn in half: a
window, a café, a street, a bed. They never see it; only the viewer does.

1. **Mirror everything; differ only in the people.** His setar, her plant.
   The photo on the wall shows the other cut out as paper, which is the
   ( - ) rule, kept.
2. **Ghosted.** New partners are drawn by a shakier hand, with the ex's
   paper silhouette behind them. On the beat, they flicker into the ex for
   one drawing.
3. **Rain makes the ink bleed into its hidden colors.** Paper
   chromatography, mirrored across the tear like a Rorschach blot.
4. **The gap between the halves is the distance.** It snaps open, trembles
   with the bass, closes only for the heart and the palms, and rips at the
   street and the storm.
5. **The heart.** Each draws half of it on their own fogged glass. It turns
   red only when the halves meet.

In code, `drawPiece(side, st, t)` in `src/90_main.js` does all of this. It
clips to one torn half (`PIECE.L` or `PIECE.R`, built from the fixed `TEAR`
polyline in `src/20_world.js`), shifts it by ±gap/2, mirrors the right half,
and calls the same scene function with `'him'` or `'her'`
([#36](../TECHNIQUES.md#36-torn-page-mirror)).

## The track

The pre-master that kit v1 was built on: 135.162 s, 48 kHz stereo, **32-bit
float**. The grid is exactly 120.000 BPM, first downbeat 0.255 s, bar 2.0 s,
so t = 0.255 + 2·bar. There is a kick on every beat, so the downbeat was
chosen by bar-level novelty. Phase 0 wins because the novelty jumps at 32.26
s and 124.25 s both fall on its bar lines.

| Bars | From (s) | Section | Envelope | Scenes |
|---|---|---|---|---|
| 0–16 | 0 | intro | no bass, ~−14.5 dB RMS | card, window, phones, leaving |
| 16–21 | 32.26 | drop | bass on | café |
| 21–36 | 42.26 | melody | mid up | street, bed, heart (the reel ends) |
| 36–48 | 72.25 | airy | mid down, air and centroid up, a peak at bar 43 | dream |
| 48–62 | 96.25 | climax | loudest bar 49 (98.25 s), −5.9 dB RMS | storm |
| 62–end | 124.25 | outro | bass only, the highs vanish | after |

## Scene timeline (kit v1)

`timeline(t)` in `src/80_timeline.js` turns the bar number into scene state.
The characters are on twos (12 fps) with boil. The rain and the camera run
on ones, and the output is 24 fps.

| Bars | Scene | Beats |
|---|---|---|
| 0–1 | **card** | the heart red, the title, gap 0 |
| 1–8 | **window** | the gap snaps open at bar 1 · both look to the seam at bar 3 · a raindrop race at bar 4 · a breath at bar 5.5 · phone light at bars 6–8 |
| 8–12 | **two phones** | typing on 16ths · a "typing…" bubble · backspace · lock · a face in the reflection |
| 12–16 | **leaving** | they rise and leave · lights off · the rain builds · white flash |
| 16–21 | **café** (the drop) | back to back at the tear, new dates at the outer seats, ghost silhouettes behind them. The dates flicker into the ex at bars 17, 18, 18.5, 19.5, 20, 20.25, 20.5 and 20.75 |
| 21–27 | **street** | umbrellas, one step per beat (112.5 px). They pass at the seam at bar 23 (gap 0), stop, look back at 24.5, and the page rips at 25 (gap → 170) |
| 27–31 | **bed**, from above | hands slide to the torn edge at bars 28–29 (gap → 7 px) |
| 31–36 | **heart** | half a heart each on fogged glass. The page closes at 34, turns red at 34.5, the title comes up, and the reel ends at bar 36 on its own first frame |
| 36–48 | **dream** | the tear heals · the rain hangs (its clock slowed to 3.5 %) · a droste zoom into the heart at bars 40–44 · a kaleidoscope going from 6-fold to 8-fold at bars 43.6–47.8 |
| 48–62 | **storm** | the page rips at 48 and slams shut on the loudest bar · palms on glass · lightning shows the other's paper silhouette · memories on every beat of bars 56–60, one drawing each |
| 62–end | **after** | the rain stops · asleep at the windows · the halves drift apart (gap 40 → 480) · SAME \| AS YOU |

## How it was built

**Modules, modes, driver.** Eight ordered modules under
`canvas/pieces/same-as-you/src/` run from `00_core` (grid, primitives, the
contact log) to `90_main` (the frame and the modes).
`canvas/tools/build.mjs` concatenates them into one HTML file with the usual
three modes ([#19](../TECHNIQUES.md#19-three-mode-piece)). Covers are single
frames at 3000×5333 with the flash off, cropped square. Every frame depends
only on *t* and the envelope at *t*, so `driver.mjs` keeps the default 100
Hz sampling and any window renders on its own
([#30](../TECHNIQUES.md#30-pure-function-of-time)).

**Rig v2, the fix for ( - )'s floating chairs**
([#33](../TECHNIQUES.md#33-floor-up-seating)–[#35](../TECHNIQUES.md#35-contact-qa)).
( - )'s rig was forward kinematics, so nothing made a seated body agree with
its chair. `src/10_rig.js` builds each pose from its contacts instead:

- **Two-bone IK** with pole hints (`ik()`).
- **Seated from the floor up** (`seated()`): ankle on the floor, a vertical
  shin, a horizontal thigh, the pill bottom on the seat. **The chair is
  built from the body** (`chairFor()`): the seat at the pill bottom, the
  front edge at the knee, the back post against the torso. It is wood-toned,
  so the ink legs read on top.
- **At the window, from the sill up** (`windowFigure()`): the elbow on the
  sill at exact upper-arm length, the forearm reaching to the jaw, the head
  set down on the hands.
- **Planted feet** (`walkLegs()`): the stance is centered on the beat, with
  no sliding.
- **Contact QA.** `contact(name, a, b, tol)` logs every declared contact on
  every frame. `?qa=1` draws them in green or red, and
  `canvas/tools/still.mjs --qa` prints the worst. On the release every
  contact passed at 0 px error.

**Post FX.**

- **Chromatography at quarter resolution**
  ([#37](../TECHNIQUES.md#37-chromatography-bloom)). Three ring sprites feed
  two quarter-res accumulators, then three full-res blends (multiply bleed,
  color, screen), only inside the wet bounding box. That took it from ~180
  to ~70 ms per frame. The ink spots are a pure function of time
  (`spotsAt()`): 8th-note candidates with per-section odds, biased to the
  seam so mirrored pairs merge into butterflies, and kept off faces.
- **Vector droste and kaleidoscope**
  ([#38](../TECHNIQUES.md#38-vector-droste),
  [#39](../TECHNIQUES.md#39-vector-kaleidoscope)). Recursion is done by
  redrawing, not resampling. `drosteViews()` redraws both halves inside the
  heart at each level, and `kaleidoViews()` redraws the scene in every wedge
  under its own clip. The first, image-based versions went blurry at depth.
- **Loop-continuity clocks**
  ([#40](../TECHNIQUES.md#40-loop-continuity-clocks)). Before bar 1,
  `rainClock()` and `spotsAt()` run on *t* + 72.255, the reel's end clock,
  so the reel's last frame flows into its first. On the delivered reel,
  frame 0 ≡ frame 1733.

**Performance** (2 cloud cores): 540p drafts at 17 fps, and the 1080p final
at 6.0 fps (the full film, 3244 frames, in 541 s). x264 at CRF 18 with
`-tune animation` came to ≈ 7 Mbps. The paper grain is static, because a
per-frame grain flicker cost bitrate for nothing.

## Delivery: kit v1, on the pre-master

**One render, lossless cuts** ([#41](../TECHNIQUES.md#41-forced-keyframes)).
The film was rendered once, silent, with keyframes forced at frames 0, 630,
1014, 1350, 1734, 1926 and 2310. Those are 0, 26.25, 42.25, 56.25, 72.25,
80.25 and 96.25 s (`keyframes` in `piece.json`, `--keys` in `render.mjs`).
The reel and the stories were cut from it with `-c:v copy` where the audio
lives, and muxed there: one transfer, no re-encode.

**Loudness before AAC** ([#42](../TECHNIQUES.md#42-float-pre-master-check)).
The float pre-master measured −10.6 LUFS and **+6.05 dBTP**; a float file
can sit above 0 dBFS. Gain to −14 LUFS (−3.4 dB) still left ≈ +2.65 dBTP. So
every cut also went through a 4× oversampled limiter (~−2 dBFS) before AAC
256k, with the video stream-copied using `-frames:v`.

| Cut | Window (s) | Delivered (ebur128, true peak) |
|---|---|---|
| reel, 72 s | 0 → 72.25 (bars 0–36); loops | −14.3 LUFS / −1.4 dBTP · 51 MB |
| story "drop", 16 s | 26.25 → 42.25 | −15.0 / −1.7 |
| story "heart", 16 s | 56.25 → 72.25 | −14.0 / −2.6 |
| story "dream", 16 s | 80.25 → 96.25 | −13.7 / −2.7 |
| full, 2:15 | 0 → 135.16 | −14.0 / −1.7 · 123 MB |
| Spotify Canvas, 8 s | 608×1080, a crossfaded loop of a separate state (`canvasState()`) | 2.2 MB |

There were also seven covers at 3000 px (main, psychedelic, café, street,
bed, dream, drift), an avatar, reel and grid covers, and a seven-image
carousel.

## The final master, the same night

The final master replaced the pre-master in place: 140.245 s, 24-bit / 48
kHz, −10.5 LUFS, −0.3 dBTP. **The grid was unchanged**: the measured
downbeat was 0.250 s, and 0.255 was kept. Four passages differed in the
audio, and the picture changed only there. Every other frame came out
identical to v1, which is the pure-function-of-time re-fit again.

| Bars | t (s) | The audio | The picture |
|---|---|---|---|
| 16–17.75 | 32.26 | the drop now swells over 2 bars instead of landing | the café sketches itself in at half speed (3.5 s instead of 1.75), and the drop flash softens to 0.55 |
| 43.6–47.4 | 87.46 | — | the kaleidoscope folds away before the inhale, with no white flash |
| 47.5–48.5 | 95.26 | a new inhale: the bass drops out at 95.25, and the climax lands half a bar later | **the inhale**: the whole drawing un-draws itself stroke by stroke, under a paper veil. Rain and spots fade and the camera leans in 7 % |
| 48.5 | 97.26 | the climax | **the splash**: a mirrored ink splat throws the storm back onto the page in 0.28 s, with 11 fast blooms and a camera punch. The tear rips to 72 px, then slams shut on the loudest bar |
| 62–66.4 | 124.26 | the highs fade gradually | the rain thins with them |
| 67.5–68.4 | 135.26 | a last flourish, then a dead stop at 137.0 | the halves rush back together, the heart turns red, and their eyes open toward each other. Hard cut to black at 137.0 |

The inhale was the artist's idea: everything fades at the song's breath and
splashes back with the peak
([#43](../TECHNIQUES.md#43-inhale-erase-splash)). The erase is just the
draw-on run backwards, so it cost nothing. `splashMask()` in `src/70_fx.js`
cuts the reveal as `destination-out` holes in a paper layer: a noisy blob
that grows from the seam (r = 30 + 1650·p²), plus 22 flung drops with
streaks. Spots born before the splash are dropped (`spotMinBirth`), so the
storm starts clean.

Only the full film was re-rendered, because the final deliverable was the
whole film as a single Reel. It came to 3324 frames in 546 s (6.1 fps on 2
workers), and the delivered file is 2:18.5 and 127 MB. The mux used clean
gain with no second limiter. At −1.5 dB the AAC still hit −0.0 dBTP, because
the encoder overshoots this master's hats by ~1.8 dB. **At −2.5 dB it
delivered −13.0 LUFS, LRA 5.9, −1.3 dBTP**, the same answer MIKONAMET found
([#18](../TECHNIQUES.md#18-aac-true-peak-guard)).

## What went wrong

- **A white flash on white paper is invisible.** The splash was first marked
  by a flash that didn't show on bare paper. The ink-splat reveal replaced
  it.
- **Blooms over faces.** The ending's blooms first covered the faces. The
  fix was burst size 0.8 and glow 1.15.
- **Stream-copy cuts overshoot.** `-ss t0 -t dur -c:v copy` kept 2 extra
  frames per cut, even with keyframes forced at `t0` (B-frame reordering).
  Cut with `-frames:v N` instead. Also add `-map_chapters -1`, or every
  output keeps a dangling reference to the WAV's chapter track.
- **The WAV changed under the build.** During v1 the song file was replaced
  in place (51.9 → 68.6 MB), so the mux used a different file from the one
  analyzed. Re-probe the hash, size and modification time right before every
  mux.
- **The store bounced the release once.** The record-label field held the
  label's name in two languages plus decorative symbols, and the distributor
  read that as a side-by-side translation. The fix: one label name, one
  language, no symbols, identical on every release. It's a metadata lesson
  for [ADR-0006](../decisions/0006-the-release-pack.md)'s release pack.

## The port in this repository

**Measured on the port:**

- The repository build of `canvas/pieces/same-as-you/` is text-identical to
  the shipped HTML apart from comments. It is the final-master state
  (`DUR = 140.245`), and `piece.json`'s `full` cut is 0 → 138.5.
- Against frames decoded from the delivered film, the repository driver
  reproduces SAME AS YOU at 38.5 dB PSNR. An adjacent frame scores 24.5 dB.
- Renders are deterministic run to run. Two stills of the same *t*, rendered
  while writing this, were byte-identical PNGs.

## What it contributed

New:

- [#33 Floor-up seating](../TECHNIQUES.md#33-floor-up-seating)
- [#34 Sill-up poses](../TECHNIQUES.md#34-sill-up-poses)
- [#35 Contact QA](../TECHNIQUES.md#35-contact-qa)
- [#36 Torn-page mirror](../TECHNIQUES.md#36-torn-page-mirror)
- [#37 Chromatography bloom](../TECHNIQUES.md#37-chromatography-bloom)
- [#38 Vector droste](../TECHNIQUES.md#38-vector-droste)
- [#39 Vector kaleidoscope](../TECHNIQUES.md#39-vector-kaleidoscope)
- [#40 Loop-continuity clocks](../TECHNIQUES.md#40-loop-continuity-clocks)
- [#41 Forced keyframes](../TECHNIQUES.md#41-forced-keyframes)
- [#42 Float pre-master check](../TECHNIQUES.md#42-float-pre-master-check)
- [#43 Inhale erase, splash reveal](../TECHNIQUES.md#43-inhale-erase-splash)

Re-derived, not new: the
[three-mode piece](../TECHNIQUES.md#19-three-mode-piece),
[on twos and boil](../TECHNIQUES.md#29-on-twos-and-boil), the
[signature card](../TECHNIQUES.md#16-signature-card) as the reel's first
frame (bar 0 *is* the card), and the
[AAC true-peak guard](../TECHNIQUES.md#18-aac-true-peak-guard).
