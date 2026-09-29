# Case study: AHANGE AROOSI

**AHANGE AROOSI** (آهنگ عروسی, "wedding song") · Sep The Concept · August
2026 · 5:03 · found wedding footage, a python frame engine

The seventh release in the series. It is an ambient/electronic song about
the sadness of weddings, not their celebration, built on found footage: two
short clips of a farewell at a wedding, reposted online with burned-in
captions, a drifting watermark and a date tag. Every effect is driven by the
song's own envelope, through a python per-frame engine.

What it proves for the framework: found footage is the case kaleidophone's
own pipeline was least ready for. The source had to be *cleaned* before it
could be graded, and cleaning a watermark that moves is a tracking problem.
And the grade does more than set a mood: it carries the concept.

**What's scrubbed and why:** this footage shows real people who never agreed
to appear in a music video. So this write-up carries technique only. There
are no frames. Nothing describes who is on the tape or what they do beyond
"a farewell at a wedding". No account names, and no story behind the song.
What's kept is the cleanup method, the grade, the engine, the structure and
the measured numbers. Numbers are **measured on the release** unless marked
otherwise.

## The rule: red is the only color that survives

The grade is the concept ([#6](../TECHNIQUES.md#6-red-thread-grade)). The
world drains toward a two-tone memory, indigo shadows and bone highlights,
while one protected hue band survives: red, computed per pixel from its
redness. Around it is VHS memory-rot: feedback ghosts, tape tears, a
slit-scan time-smear, and kaleidoscope blooms only at musical peaks. The
title pairs Persian set in Vazirmatn Light with Latin set in a grotesk and a
typewriter face, over a red underline bar.

## Cleaning the source: a tracked-overlay inpaint

The two clips were 720×900, with burned-in caption boxes above and below the
picture, a watermark that moves, and a colored date tag
([#9](../TECHNIQUES.md#9-tracked-overlay-inpaint)):

1. **Crop what can be cropped.** The caption boxes and black bands go. The
   footage band y 248–654 leaves 720×406, about 16:9.
2. **Avoid what can be avoided.** The date tag sits over the bottom of the
   picture only in the first 3.5 s of one clip, so the edit never uses those
   frames (its opening shots start at t ≥ 10.6).
3. **Track what moves.** A high-pass, text-density box detector, sampled
   over time, found the watermark's path in three phases. For t < 22 it sits
   in the top black band, which is cropped away anyway. From t = 22 to 40 it
   drifts diagonally; a piecewise-linear path through a few knots follows
   it, and a feathered median-filter patch fills it on each frame. From t =
   40.5 it is parked at about x 545–715, y 480–522.
4. **Verify by eye.** The detector's first pass put the parked phase at x =
   440, which was wrong. Raw-vs-clean crops at several timestamps caught it,
   and a wider box fixed it. **The detector lies where the texture is busy.
   Check the inpaint visually at three or more timestamps.**
5. **Judge by persistence, not position.** One colored object looked like a
   moving sticker only because the camera moved; it was part of the scene,
   and it stayed. A real sticker blip (t ≈ 38.5–40.2) was patched. Static
   scene objects and moving overlays are told apart by persistence plus
   awareness of camera motion.

## The track

302.9 s (5:02.9), 48 kHz / 24-bit. Tempo is a soft estimate of ~99.4 BPM,
and 423 detected beats were used to snap cuts. The envelope pack holds bass,
mid, high and rms at 100 Hz plus beats and onsets, and it drives every
effect. Label nothing, react to everything.

| t (s) | Section |
|---|---|
| 0–45 | quiet intro |
| 50–65 | lift |
| 65–125 | high |
| 155 | the peak (global maximum) |
| 170–220 | easing |
| 225–235 | the second peak |
| 240–265 | valley |
| 270–295 | the final swell |
| → 302.9 | fade |

## The engine

A float RGB pipeline (numpy) renders each frame from the envelope at that
frame:

- `grade_red_thread`: selective survival of red
  ([#6](../TECHNIQUES.md#6-red-thread-grade)).
- Chroma shift and tape tears.
- Feedback: ghosts of the previous frame, slightly zoomed.
- **Slit-scan** ([#7](../TECHNIQUES.md#7-slit-scan-smear)): a ring buffer of
  past frames with a per-column (or per-row) time offset. Eased mappings
  make time pull the subject away. It also made a cover, with a held region
  kept sharp while the rest smears.
- **Kaleidoscope** ([#8](../TECHNIQUES.md#8-kaleido-bloom)): polar-mirror
  index maps cached by size, fold count and center, mixed in only at musical
  peaks. The canvas pieces later replaced this bitmap approach with a vector
  redraw per wedge ([#39](../TECHNIQUES.md#39-vector-kaleidoscope)).
- Posterize, with red re-injected afterward, and a punch-zoom on beats.
- **A grain bank** ([#10](../TECHNIQUES.md#10-grain-bank)): a handful of
  pre-generated full-resolution grain tiles, rolled at random per frame.
  Per-frame `rng.normal` at 1080×1920 had been the single hottest operation
  in the engine.
- A cached vignette.

Per-shot EDLs have beat-snapped boundaries. Two stride-parallel workers
render independent segment files, which are concatenated and then given one
finish pass. **Measured:** ~0.4 s per frame on 2 cores, so 60 s of video
took about 7 minutes with two workers.

Persian text is set with PIL + libraqm (`direction='rtl', language='fa'`)
and the real Vazirmatn. Never use `arabic_reshaper`, which double-reverses
the text.

## Delivery

| Cut | Format | Structure |
|---|---|---|
| film, 5:03 | 1920×1080, CRF 23, maxrate 7M, 270 MB | four movements. **M1** 0–50: near-mono, slow. **M2** 50–125: slit-scan and feedback rising. **M3** 125–240, both peaks: kaleidoscope, posterize, invert, the tape burning. **M4** 240–294.9: the clean raw footage as a coda, riding the final swell; the memory intact, and the contrast is the point. Then a bilingual end card on the fade |
| reel, 60 s | 9:16 | it opens on the raw tape with the tape's own sound, then the track from 35 to 87 s (the lift lands ~15 s in), a melt, and the kaleidoscope peak. At 47 s a 5 s crossfade goes into the track's real outro (289.9 s → end), and it resolves back to raw. It loops, because the end scene is the opening scene |
| story, 60 s | 9:16 | a different cut, from the second clip, with the track from 195 to 255 s. The second peak falls ~30 s in, and it ends in the valley, dark. It loops |
| covers | 5 × 3000², texted + textless | a slit-scan with a held region, a two-ink screen print, a ghost bloom, a negative (a magenta/green invert), an archive strip |

**The outro splice** ([#11](../TECHNIQUES.md#11-outro-splice)). A 60 s cut
from the middle of a 5-minute track would normally just stop. Instead, the
main window fades over 5 s into the track's real last ~13 s, so the cut ends
on the song's true ending. In an ambient track the crossfade is seamless,
and it reads as intentional.

**Audio.** An `amix` builder layers the track with the tape's own sound at
the reel's opening (−2 dB, with a 3 s fade) and at its close (−8 dB). Gain
comes from a measured `loudnorm` pass to ≈ −14 LUFS, then `alimiter`.

**Grain against x264, measured.** CRF 17 intermediates ballooned: 60 s came
to 1.1 GB, and the film to 5.5 GB. Delivery at CRF 23 with a 7M maxrate came
to ~54 MB per 60 s and 270 MB for the film. It's the same tradeoff
[love.md](love.md) measured at 720p: grain is nearly incompressible.

## What went wrong

- **Slow motion, done backwards.** Slowing a clip down means decoding at fps
  ÷ speed and letting the `fps` filter duplicate frames, not fps × speed.
  The wrong version shipped segments 1.1 s short until it was caught.
- **The detector mislocated the parked watermark** (see step 4 above). Only
  visual raw-vs-clean checks caught it.
- **The verticals are soft by nature.** The source is a 720-pixel strip; the
  grain and the dream grade absorb most of it.
- **The reel and story are ~59.3 s.** One source clip ran out 0.3 s early,
  which was still inside the spec.
- **Some passages go fully abstract.** A few M3 passages in the film go
  fully abstract between kaleidoscope blooms. That is texture, not signal:
  intentional, but worth a full watch before calling it done.
- **Cover details.** On the covers, the red underline grazes a descender of
  the Persian title. It reads as intent, and it can be moved. One of the
  five covers is clearly the weakest.

## What it contributed

New:

- [#6 Red-thread grade](../TECHNIQUES.md#6-red-thread-grade)
- [#7 Slit-scan smear](../TECHNIQUES.md#7-slit-scan-smear)
- [#8 Kaleido bloom](../TECHNIQUES.md#8-kaleido-bloom)
- [#9 Tracked-overlay inpaint](../TECHNIQUES.md#9-tracked-overlay-inpaint)
- [#10 Grain bank](../TECHNIQUES.md#10-grain-bank)
- [#11 Outro splice](../TECHNIQUES.md#11-outro-splice)

Re-derived, not new: envelope-driven effects, beat-snapped per-shot EDLs,
segment renders joined by concatenation then a finish pass, check-frame QA
boards, and "label nothing, react to everything". The stride workers writing
independent segment files were the fourth distinct route to
segment-then-concat (see the [index](README.md)).
