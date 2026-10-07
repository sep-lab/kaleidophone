# Techniques

Everything below was learned on a real release, then written down so the next
one starts from it instead of re-deriving it. They are numbered in the order
they were learned (the same numbers the release notes and the
[case studies](case-studies/README.md) use), so a gap in a range is not a
missing technique.

Each entry says **where it came from**, **what it is**, **why**, and **where it
lives in this repository**:

- `canvas/lib/…` — reusable, documented, tested: start new pieces here;
- `canvas/pieces/<id>/…` — the piece that introduced it, kept exactly as it
  shipped (verified against the delivered films; see [canvas/README.md](../canvas/README.md));
- `src/kaleidophone/…` — the Python package (the filter-graph engine, the
  frame-program engine, and the `envelope` / `master-check` / `deliver` commands);
- *documented only* — a lesson with no code to own, or code that would not
  generalise yet.

Numbers are measured on the release named unless marked otherwise, per
[AGENTS.md](../AGENTS.md), "Rules for claims and numbers".

**By kind**

| | |
|---|---|
| The grid and the song | [3](#3-bar-fit) · [11](#11-outro-splice) · [16](#16-signature-card) · [30](#30-pure-function-of-time) · [40](#40-loop-continuity-clocks) · [47](#47-grid-arithmetic) · [48](#48-lyric-map-from-stem) · [49](#49-master-drop-in-check) · [52](#52-what-the-new-master-added) · [53](#53-one-past-the-count) · [55](#55-session-in-midi-and-stems) · [57](#57-the-count-closes-the-circle) · [60](#60-a-meteor-per-sung-line) |
| Rendering and delivery | [5](#5-on-device-rendering) · [10](#10-grain-bank) · [18](#18-aac-true-peak-guard) · [21](#21-deterministic-render-harness) · [27](#27-jpeg-capture) · [41](#41-forced-keyframes) · [42](#42-float-pre-master-check) · [50](#50-aac-guard-per-master) |
| Canvas: the piece | [19](#19-three-mode-piece) · [20](#20-live-web-audio-fallback) · [22](#22-stroke-scaling) · [26](#26-canvas-rtl) · [31](#31-square-cover-crop) · [59](#59-deterministic-accumulation-cache) · [61](#61-cut-aware-piece) |
| Canvas: drawing | [23](#23-sprite-fire) · [24](#24-pressure-ring-swarm) · [25](#25-mask-state-machine) · [28](#28-paper-cut-out) · [29](#29-on-twos-and-boil) · [32](#32-rig-primitives) · [33](#33-floor-up-seating) · [34](#34-sill-up-poses) · [35](#35-contact-qa) · [56](#56-exposure-as-an-integral) · [58](#58-occupancy-ghost) |
| Canvas: compositing | [36](#36-torn-page-mirror) · [37](#37-chromatography-bloom) · [38](#38-vector-droste) · [39](#39-vector-kaleidoscope) · [43](#43-inhale-erase-splash) · [44](#44-viewfinder-compositor) · [45](#45-split-image-sync) · [46](#46-mirror-slap) · [62](#62-settling-grain-and-the-shutter-curtain) |
| Covers | [31](#31-square-cover-crop) · [51](#51-contact-sheet-cover) · [54](#54-cover-variant-family) |
| Footage (frame programs) | [6](#6-red-thread-grade) · [7](#7-slit-scan-smear) · [8](#8-kaleido-bloom) · [9](#9-tracked-overlay-inpaint) · [12](#12-memory-canvas) · [13](#13-generation-loss) · [14](#14-mean-face) · [17](#17-lip-sync-test) |
| Framing and text | [1](#1-window-reveal) · [2](#2-audio-timed-subtitles) · [4](#4-crop-drift) · [15](#15-rtl-title-erosion) |

Three more came from the reference project before this numbering started —
`scope_overlay`, `feedback_echo` and `punch_zoom` ([love.md](case-studies/love.md),
"Iteration 2"). `feedback_echo` and `punch_zoom` now exist as frame-program
effects (`kaleidophone.frames`); all three are still open as filter-graph
effects ([#15](https://github.com/sep-lab/kaleidophone/issues/15),
[#16](https://github.com/sep-lab/kaleidophone/issues/16),
[#17](https://github.com/sep-lab/kaleidophone/issues/17)).

---

## Framing and text

### 1. Window reveal
*From:* THE NIGHT TRACK TALKS. *Where:* `sections[].framing: {mode: window}` (since 0.2.0).
Shrink the frame and float it on black; low-energy passages play inside the
window and a hit cuts back to full frame. A windowed shot needs a gamma lift
(~1.3 against ~1.05 full-frame) or it reads as underexposed.

### 2. Audio-timed subtitles
*From:* THE NIGHT TRACK TALKS. *Where:* `overlays` (since 0.2.0).
Pre-rendered transparent cards composited in the finishing pass with
`enable='between(t,a,b)'`, timed against vocal-band energy. Persian is shaped
with libraqm and a real font — **never** `arabic_reshaper`, whose double
reversal burned three separate engines.

### 3. Bar fit
*From:* LONELINESS. *Where:* [case study](case-studies/loneliness.md); *documented only*.
Fitting an existing track to an existing, untouchable film: verify the tempo
with a comb filter, anchor the bar grid at the drop, and cut the track into
bar-aligned segments that land its events on the film's cuts, keeping the
film's own audio at reduced gain at both ends. The deliverable includes a
sync map — a table of bar → film event — so a re-render is a lookup.
The release joined its segments with 10 ms fades at the bar lines, and a
fade that short, to silence, chops whatever rings across the line — reverb,
a held note, a cymbal's tail. Next time *(the 0.3.0 review's advice, not
measured on the release)*: cut a few milliseconds before the downbeat, so its
attack stays whole, and join the segments with a 20–50 ms equal-power
crossfade — `acrossfade=d=0.03:c1=qsin:c2=qsin`, whose two gains' squares sum
to 1 across the fade (measured, ffmpeg 6.1). `kaleidophone deliver` has no
seam of this kind to join: a card cut concatenates only the picture, and the
audio runs on unbroken underneath it.

### 4. Crop drift
*From:* LONELINESS. *Where:* *documented only* (the static form is `framing: {mode: crop, x}`).
Per-frame crop expressions for 9:16 pulls from 16:9
(`crop=608:1080:x='clip(...)'`); nudge `between()` ends by −0.001 so adjacent
ranges don't double-count, and remember `t` restarts at 0 after an input `-ss`.

### 15. RTL title erosion
*From:* MIKONAMET YEROZI KHOB FARAMOOSH. *Where:* [case study](case-studies/mikonamet.md); *documented only*.
A Persian title that forgets itself: drop connected components smaller than 20 %
of the 80th-percentile stroke area first (the dots go first), then break strokes
by thresholded noise and erode. For "the title writes itself", use a right-to-left
soft wipe mask — never render prefixes of Persian text, the letterforms flicker
between medial and final shapes.

---

## The grid and the song

### 11. Outro splice
*From:* AHANGE AROOSI. *Where:* *documented only*.
A 60 s cut that ends on the track's real ending: crossfade (5 s) from the main
window into the song's last ~13 s. Seamless in an ambient track; it reads as intent.

### 16. Signature card
*From:* MIKONAMET. *Where:* `canvas/pieces/minus` (`card`), `canvas/pieces/should-i` (`cardT0`), `render.mjs --card`, `kaleidophone deliver` (`card:`).
Vertical cuts open on a short title card (1.6–2.4 s: the title writing itself
over the resting subject) instead of text over a face. Instagram takes the first
frame as the reel cover, so the card doubles as the cover. On a stream-copied
cut, render the card as its own short segment and concatenate it in front
([41](#41-forced-keyframes)), so the full film never carries a mid-film title.

### 30. Pure function of time
*From:* ( - ). *Where:* every canvas piece except HAMECHI MANZOR DARE; `canvas/pieces/template`.
A piece with no per-frame state is a function of `(t, envelope)`. That makes
everything cheap: any window renders on its own, in parallel, with no warm-up
or checkpoints; a new master that keeps the grid is a constants change; a card
is a flag. ( - ) went from a 1:46 demo to the 2:58 master in one evening because
of it. Prefer it over stateful effects whenever the concept allows.

### 40. Loop-continuity clocks
*From:* SAME AS YOU. *Where:* `canvas/pieces/same-as-you/src/20_world.js` (`rainClock`, `spotsAt`).
A reel that ends on its own first frame still jumps if the rain, the drops and
the ink spots don't match at the seam. Before bar 1, run those clocks on the
reel's end clock (`t + 72.255` for a 0–72.25 s reel). Measured on the delivered
reel: frame 0 ≡ frame 1733.

### 47. Grid arithmetic
*From:* SHOULD I ?. *Where:* `canvas/lib/core.js` (`makeGrid`); the concept of `canvas/pieces/should-i`.
Count the grid before inventing anything. In SHOULD I ? there are exactly 36
snares from the drop to the bar where the hook asks its question — one 35 mm
roll, a shutter on every snare, running out on that bar; a 36-frame rewind at
12 fps is exactly one bar; 36 beats of darkroom develop a 36-frame contact
sheet. The numbers the music already contains make the sync that reads as
magic.

### 48. Lyric map from stem
*From:* SHOULD I ?. *Where:* *documented only* (the onsets are data: `events.stutter` in a song pack).
Separate the vocal (`audio-separator` with `Kim_Vocal_2.onnx`, ~4 min on 2 cores),
transcribe it with sherpa-onnx whisper *turbo* on 4-, 2- and 1-bar windows, and
take vocal onsets as log-spectral-flux peaks on the stem. On English vocals this
gave a clean bar-by-bar map; on fast Persian it did not — ask for the lyric text.
Median F0 per half-bar separated the two singers (~280 Hz vs ~140 Hz). The onsets
are what the piece consumes; the words never enter the repository.

### 49. Master drop-in check
*From:* SHOULD I ?. *Where:* `kaleidophone master-check old.wav new.wav` (`src/kaleidophone/audio/mastercheck.py`).
Before re-rendering anything for a new master, compare it to the one the picture
was cut against. On the release, by hand: the local lag from log-envelope
cross-correlation in 8 s windows every 4 s read 0.00 s everywhere (the same
grid), and the 350–3400 Hz envelope correlated 0.65–0.95 per section at lag 0
even though the arrangement after the drop had changed (full-mix correlation
0.2–0.6) — a re-mux, zero re-render. That band is a proxy for the voice: the
tool reads it from the full mix, where it also hears guitars, keys and the
snare's body, so a low reading is a reason to listen, not proof of a new take.

The tool adds what the release didn't need. One alignment of the whole song
(a loop lines up with itself a bar later; a whole song doesn't), refined to
the millisecond, and a tolerance of half a frame at 24 fps (~21 ms,
`--tolerance-ms`) inside which a shift is the same grid. Beyond it, the same
material starting earlier or later is an **offset** (exit 5): the report
prints the delivery sheet's new `silent_start` — the current one
(`--silent-start`) plus the shift, negative when the new master starts
earlier — and nothing is re-rendered. New *music* before the old master's
first note is an insertion, and a new grid. Lags that grow with time are a
tempo change, and a master that is the same material a few percent faster
(a varispeed) is found by stretching one envelope against the other and said
as such. When the vocal band lines up clearly better at another shift than
the mix does, the vocal moved on an unchanged beat, and the report says by
how much. Measured on synthetic masters made for the 0.3 review (not in the
repository, not representative of real mixes; `tests/test_mastercheck.py`
pins each case on its own synthetic song): a 20 ms head trim and a
pitch-shifted master sitting 11 ms early read as remux; 0.35 s of new head
silence and an MP3 draft's
decoder delay (−0.023 s at 48 kHz, −0.025 s at 44.1 kHz, the draft being the
old master) as offsets; one and two bars inserted as new grids at +3.00 and
+6.00 s; a 1-semitone varispeed as "5.95% faster, 84.76 BPM against 80.00";
a bar added under a loop that carried on unchanged as "vocal moved +3.00 s
(r 0.94)". This is the remux landmark-drift guard the roadmap had carried
since the reference project ([#18](https://github.com/sep-lab/kaleidophone/issues/18)).

### 52. What the new master added
*From:* SHOULD I ? v3. *Where:* `kaleidophone master-check` (the per-bar report).
On the release, the old and new vocal *stems* were compared per bar: mean
|Δ|, and the "new voice" fraction (new > 0.35 while old < 0.15). ASR ran only
on the bars that changed. It found a spoken passage laid over the darkroom and
a new last line — exactly which bars to re-render and what the new story beat
was. The tool has no stems, so it compares what a piece reads instead: every
song-pack envelope (bass, lowmid, mid, high, air, rms, cent, voc and the flux
envelopes) per bar of the grid, the new master aligned first. Levels go on
the old master's scale — each band's overall gain difference taken out, both
through the old master's percentiles — so a louder, brighter or harder-limited
master reads as unchanged, and a bar changes when an envelope's mean |Δ|
(0.15) or its shape r (0.75) crosses a threshold. The flux envelopes are
compared as rhythm, onset energy per 16th (r 0.8). The "new voice" fraction
stays, on the mix's 350–3400 Hz band. The verdict names the bars, their times
and what changed: "rerender bars 13-14 (00:36.51-00:42.51): mid, voc, lowmid
changed". Measured on the 0.3 review's synthetic masters (not representative
of real mixes): a remaster, a 44.1 kHz bounce, the vocal ±3 dB, a −12 dB
reverb and a 1-semitone pitch shift stayed remux; a new take in bars 13–14
and an ad-lib in bar 3 flagged exactly those bars; removing every hi-hat
flagged every bar (air, hflux, cent) where a vocal-band check alone had said
remux — a piece sparkling on the hats would have sparkled to nothing. The
thresholds are starting points; `--envelopes` narrows the check to what the
piece actually reads (`voc,mid` for choreography cut to the voice, as SHOULD
I ?'s was).

### 53. One past the count
*From:* SHOULD I ? v3. *Where:* `canvas/pieces/should-i/src/50_film.js` (`drawFinalFrame`), `30_expo.js` (`drawDoorway`).
When the concept is a count, the strongest ending is the frame that can't exist:
a roll has 36 frames, so on the last vocal line the counter rolls "?" → 37 and
the door is open with her in it. Put it in the near-silence before the voice so
image and words arrive together. It doubles as a cover.

### 55. Session in: MIDI and stems
*From:* 0.4 ([#56](https://github.com/sep-lab/kaleidophone/issues/56)), after four canvas releases that read their hits off the mixed master — or, for SHOULD I ?'s voice, off a stem separated from it ([48](#48-lyric-map-from-stem)). *Where:* `kaleidophone envelope --midi Song.mid --stem NAME=path` (`src/kaleidophone/audio/midi.py`, `envelope.py`); the keys in [CONFIG-SCHEMA.md](CONFIG-SCHEMA.md#session-in-midi-and-stems---midi---stem).
Onsets guessed from a mixed master are the contract's weakest link: the kick,
the bass and a synth's attack land in the same bins, the grid is one tempo
extrapolated across the song, and bar 1 is a guess wherever nothing in the
audio marks the bar (a downbeat confidence of 0.0–0.4 on clicks, measured in
`envelope.py`). The artist's session already knows all of it. Export its MIDI
and stems, and the pack takes its grid from the tempo map and time signatures,
following a tempo change beat by beat and counting its beats from every bar
line, so an odd 3/8 bar doesn't throw the rest of the song half a beat off;
`pulses` is the felt beat beside them — the dotted quarter of a 6/8 groove,
from the time signature's metronome click or its meter. Every note becomes an
event with its velocity, length (as the sustain pedal holds it) and pitch
(`events.midi.<track>`), every harmonic track's chord changes are named over
their bass (`F/G`, `C/E`; `events.chords.<track>`), each stem gets the master's
envelopes, and the vocal stem's level replaces the mid-side `voc` proxy. What
is left to find is where the session sits on the bounce — pre-roll, a trimmed
head, a bounce from bar 5. The MIDI: its notes as an onset train,
cross-correlated with the master's onset envelope over ±30 s and refined below
a frame, with a confidence that calls a loop's offset a guess, because a song
that repeats itself fits nearly as well a bar away; a clip that opens on a
pickup takes `--downbeat` for its bar 1. The stems: each one's band levels and
onsets against the master's over ±2 s, because a mastered bounce is often
trimmed at the head and its stems aren't — the 0.4 review's master, 0.30 s
short at the head, had put its vocal stem's `voc` 300 ms late without a word.
A stem that can't be lined up is refused until `--stem-offset` gives its lag.
Measured on the tests' synthetic session and stems (not representative of
real mixes): the MIDI's offset within +1.4 ms with 0.5 s of pre-roll and
+1.3 ms with 1.25 s trimmed, a strict loop and a MIDI file at the wrong tempo
both warned about; every stem within 3 ms of its lag, and a stem from another
song, a pad with no attack and a click loop alone all refused. A drum kit on
one MIDI track stays one track: name the session's tracks the way the piece
will read them — `kick`, `snare`, `hat` — as the synthetic twins' events are
named, and commit the DAW's groove before exporting, or the notes are straight
where the bounce swings.

### 57. The count closes the circle
*From:* SETAREH (extends [47](#47-grid-arithmetic)). *Where:* `canvas/pieces/setareh/src/10_expo.js` (`stepProg`, `thetaAt`), `20_lights.js` (`drawTrails`).
32 snares × 11.25° = 360°: the sky turns one step on every snare, so the star
trails close into rings on the exact beat the shutter closes — the 32nd snare of
each cut, at 72.181 s and 149.051 s on the release (measured from the pack's
events). Each step eases out 55 % of its angle in its first 28 % of the time to
the next snare and sweeps the rest steadily, so 0.55 + 0.45 × 0.28 = 67.6 % of a
step is swept fast, which the trail records dimly (alpha 0.13), and the slow
remainder is drawn at full strength as a dash: 32 dashes round every ring, one
per snare, like the centre line of an empty road. The count is a fallback too:
with fewer than 32 snares after the opening (a dropped track, a synthetic
twin) the grid's backbeats stand in. Measured on the port: the twin, which has
no snare events, closes the same two cuts at 72.1975 s and 149.0725 s — 16.5 ms
and 21.5 ms after the real ones — because the real snares fall 1.865–1.921 s
apart within the cut, and the grid's are exactly 1.875 s.

### 60. A meteor per sung line
*From:* SETAREH (extends [48](#48-lyric-map-from-stem)). *Where:* `canvas/pieces/setareh/src/10_expo.js` (`meteorsFor`), `20_lights.js` (`drawMeteor`).
Every sung line is a shooting star, and it stays. Each line's onset
(`events.setareh.line`, one onset per sung line, the way [48](#48-lyric-map-from-stem)
makes a lyric map) launches a streak from near the pole star, aimed by the
golden angle (137.508° from a per-cut start) so any number of them spread
evenly and never clump, skipping directions within 42° of straight down, where
they would point at the figures; its length grows with the onset's strength
(200 + 250 × s px, capped by the distance to the land). Because the exposure
keeps everything that happened, the streaks pile up into rays round the pole
star, and the number of lines is the number of rays: 16 in each cut (measured
from the pack's events). There is no fallback — a pack without line events has
no meteors — so a synthetic twin writes line windows, and its rays are as many
but not in the same places (15 and 17 in the two cuts, measured). The pass that
found the release's onsets was not kept, so a new master can't re-derive them.

---

## Rendering and delivery

**Segment-then-concat** is not numbered because every release re-derived it:
render independent segments (per cut, per worker, per call) with identical codec
parameters and join them with the concat demuxer, instead of one growing filter
graph. Four different reasons forced it — iteration cost (the reference project),
an out-of-memory kill of a 10-branch graph (THE NIGHT TRACK TALKS), per-call time
limits on a small VM (LONELINESS), and stateful effects with checkpoints
(MIKONAMET). See [ARCHITECTURE.md](ARCHITECTURE.md), "Three engines".

**Silent render, mux on the device** is the other constant: render the picture
silent wherever the cores are, and mux the audio where the WAV lives, so the
master never crosses a slow link. `kaleidophone deliver` is that step.

### 5. On-device rendering
*From:* LONELINESS. *Where:* *documented only*; `kaleidophone.frames` (`run_job` budgets).
When the link to the machine holding the media is slow, render on that machine.
A 4-core ARM VM ran x264 at ~1.3× realtime; background processes died at the end
of each call, so every step fit in one call (≤45 s then, 180 s later) and wrote
its own segment.

### 10. Grain bank
*From:* AHANGE AROOSI. *Where:* `kaleidophone.frames.GrainBank`; `canvas/lib/core.js` (`noiseTile`).
Pre-generate a handful of full-resolution grain tiles once and roll them per
frame. Per-frame `rng.normal` at 1080×1920 was the single hottest operation in
that engine, and per-frame grain flicker costs bitrate for nothing.

### 18. AAC true-peak guard
*From:* MIKONAMET. *Where:* `kaleidophone deliver` (every gain mode; `gain: {mode: auto}` steps the gain).
A hot limited master (−9 LUFS, −0.3 dBFS *sample* peak) was delivered at
+1.7 dBTP through AAC. Not all of those 2 dB are the encoder's: −0.3 dBFS is
the peak of the samples, and the true peak — between the samples — is never
lower than that and on a limited master usually higher; it wasn't measured on
the WAV at the time, so how the 2 dB split between the two isn't known. Clean gain
before the encoder (−2.5 dB there, no limiter) fixed it — and the only true
peak that matters is the one measured on the **delivered** file
(`ebur128=peak=true`), not the WAV. `deliver` measures every delivered file,
after the limiter too: in the 0.3.0 review a window limited to −2.0 dBTP was
still delivered at −0.1 dBTP. For a delivery louder than −14 LUFS the ceiling
is −2 dBTP, not −1 — Spotify's figure for masters that loud
([cited](https://support.spotify.com/us/artists/article/loudness-normalization/)).

### 21. Deterministic render harness
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/tools/render.mjs`, `canvas/tools/still.mjs`.
Drive the piece frame by frame from the song pack in headless Chromium, capture
the canvas, pipe to ffmpeg. For a stateful piece, render ~3 s of warm-up frames
you don't write, so trails and fire are alive on frame 0, and snap the cut start
to the nearest detected beat — then use the **snapped** value for the audio.

### 27. JPEG capture
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/tools/render.mjs`.
`toDataURL('image/jpeg', 0.92)` piped as MJPEG is ~2× faster than PNG capture
(~9.5 vs ~4 fps at 1080×1920). PNG only for stills and covers.

### 41. Forced keyframes
*From:* SAME AS YOU. *Where:* `render.mjs --keys`, piece.json `keyframes`, `kaleidophone deliver`.
Render the film once, silent, with keyframes forced at every planned cut frame;
then the reel and the stories are cut on the device with `-c:v copy` — lossless,
frame-exact, no second encode. Cut with `-frames:v N`, not `-t` (a stream-copy cut
kept 2 extra frames even with keyframes at t0), and add
`-dn -sn -map_metadata -1 -map_chapters -1` (a WAV's chapter track otherwise
leaks into the MP4).

### 42. Float pre-master check
*From:* SAME AS YOU. *Where:* `kaleidophone deliver` (`gain: {mode: loudness}`).
A 32-bit float WAV can sit above 0 dBFS (−10.6 LUFS, +6.05 dBTP). Measure LUFS and
true peak before encoding; if over, gain-stage to −14 LUFS and run a 4×
oversampled limiter (~−2 dBFS) before AAC.

### 50. AAC guard per master
*From:* SHOULD I ?. *Where:* `kaleidophone deliver` (`gain: {mode: auto}`).
The right pre-AAC gain is a property of the master, not a constant: −2.5 dB was
enough for two masters; a busier one still delivered −0.2 dBTP at −2.5 and needed
−3.5 dB (every cut ≤ −1.4 dBTP); its successor needed −3.0. Measure every time.

---

## Canvas: the piece

### 19. Three-mode piece
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/lib/live.js` (`boot`); every piece's main module.
One self-contained HTML file behaves three ways off its URL query: **live**
(click → a procedural fallback, or drop the track → an AnalyserNode drives it,
endlessly), **render** (`?render=1` → `window.__frame(p)`, driven by the
harness), **cover** (`?cover=1` → `window.__cover(name)`). The same draw code
serves the live piece, the films and the covers.

### 20. Live Web Audio fallback
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/lib/live.js` (`procedural`).
Without a dropped file the live piece plays a scheduled procedural pad and beat
at the track's tempo through the same AnalyserNode, so it is never silent and
never waits for a file.

### 22. Stroke scaling
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/lib/core.js` (`strokeScale`).
Multiply every `lineWidth` and font size by `max(0.8, S/200)` (S = subject size).
A piece tuned at 1080p goes hairline on a 3000 px cover otherwise — the single
biggest cover-quality fix.

### 26. Canvas RTL
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/pieces/hamechi-manzor-dare`.
Isolated Persian words and a short title shape correctly with `fillText`, the real
Vazirmatn (base64-inlined) and `direction: rtl` — no reshaper needed (and still
never `arabic_reshaper`).

### 31. Square cover crop
*From:* ( - ). *Where:* `canvas/lib/live.js` (`coverCrop`); `canvas/pieces/minus` (`CROPS`).
Keep the piece's 1080×1920 virtual space and translate a per-variant band onto a
square canvas (`setTransform(k,0,0,k,0,-top*k)`): stroke weight stays the
portrait's, and the band of a vertical scene that matters is almost always square.

### 59. Deterministic accumulation cache
*From:* SETAREH (extends [30](#30-pure-function-of-time)). *Where:* `canvas/pieces/setareh/src/20_lights.js` (`trailBitmap`, `TCACHE`), `40_people.js` (`eraLights`).
An accumulating look — star trails piling up for a minute — is the textbook
stateful effect, and a stateful effect means a warm-up and one worker. This one
isn't, because a *finished* step of the sky never changes. Each era of the
exposure (the stretch in which a figure held one pose) keeps one bitmap of its
finished steps, extended one step at a time and in order — a partial first step
if the era opens mid-step — erasing whoever was in front after every step
(`destination-out` with that pose's paths); only the unfinished step is drawn
live. The same operations run whichever frame a worker starts on, so the bitmap
is a function of (exposure, era, steps done), the frame is still a function of
time, and a window renders on its own, splits across workers, or resumes. The
bitmap is rebuilt from step 0 if the page's transform changes or the angle asked
for goes backwards. Measured on the port: in a copy of the piece with the sprite
flaw below fixed, the frame at 71.667 s drawn alone and drawn after frames at
17.9, 42.9 and 59.6 s in the same page are byte-identical PNGs; in the piece as
shipped they differ by at most 2 of 255 in 14,587 of 2,073,600 pixels, all in
the halos of the pole star and the moon
([case study](case-studies/setareh.md#what-went-wrong)).

### 61. Cut-aware piece
*From:* SETAREH. *Where:* `canvas/pieces/setareh/src/00_data.js` (`CUTS`, `cutFor`, `defaultOpen`), `driver.mjs`; `render.mjs --flags '{"open":13.75}'`.
When the idea is *one exposure*, a cut is not a slice of a longer film: each cut
is its own exposure, opening at `flags.open` (the cut's `t0`), closing on the
32nd snare after it, with everything that accumulated starting from nothing. So
the two cuts are two renders — 1439 frames, 59.958 s each, `flags {open: 13.75}`
and `{open: 89.99}` in their sidecars (measured) — not pieces stream-copied out of
one film. A page without the flag (live mode, the gallery, a render that doesn't
know) opens the cut that contains `t`, and outside both a generic exposure that
opens at the last minute mark, so a gallery clip has to sit inside one cut or its
last frames jump to another exposure. A whole-song film is a different problem:
the song has 116 snares, 3.6 turns of the sky, and would need an exposure
schedule. None exists (inferred).

---

## Canvas: drawing

### 23. Sprite fire
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/lib/core.js` (`glowSprite`); the piece's `spawnFlames`.
Bake one or two radial-gradient sprites and draw many with `lighter` blending
over a base glow. Stroked paths read as dotted twigs; sprites read as flame.

### 24. Pressure-ring swarm
*From:* HAMECHI MANZOR DARE. *Where:* `canvas/pieces/hamechi-manzor-dare` (`buildSwarm`, `drawSwarm`, `ringScale`).
A field of small marks (eyes, whispering mouths, pointed words) orbiting the
subject; the ring's radius shrinks as intensity climbs and ratchets permanently
inward. Walls closing in, as a number.

### 25. Mask state machine
*From:* HAMECHI MANZOR DARE. *Where:* the piece's `wearMask` / `addCrack` / `dropMask`; its `driver.mjs` schedules it.
`off → on → falling`: a mask slams on in calm phrases, cracks on bass hits, tears
off on the loudest phrase. For renders the harness schedules it (calm 8-beat
phrases wear a mask; the loudest phrases and the single biggest hit go raw) so a
render is repeatable.

### 28. Paper cut-out
*From:* ( - ). *Where:* `canvas/pieces/minus/src/00_piece.js` (`fig({ sil: true })`).
Draw the whole scene, then the absent person as a paper-filled silhouette,
**last**. One rule makes the concept: anything that enters the cut-out — a hand,
a flower, an arm on a sofa, a blanket — stops at it. The silhouette is much wider
than its rig (2.6× strokes plus hanging arms); measure before staging a reach.

### 29. On twos, and boil
*From:* ( - ). *Where:* `canvas/lib/ink.js` (`boilFrame`, `stroke`, `poly`), `canvas/lib/core.js` (`makeGrid().onTwos`).
Quantise the drawing's time to 12 drawings a second; seed a per-drawing hash and
jitter every point of every polyline (~1.4 px at 1080, more when louder). Round
caps, flat fills, three greys + paper + one accent. Put on twos what the style
wants there, and render at the delivery rate (24 fps; `render.fps` in
`piece.json`). Each drawing is then held for two frames, and whatever runs on
ones still moves every frame. SAME AS YOU's characters are on twos and its rain
and camera on ones, so it renders at 24. Rendering 12 and doubling to 24
(`render.mjs --fps 12 --out-fps 24`) is exact only when everything in the frame
is on twos. That was true of ( - ), whose release shipped that way, but the
doubling re-encodes and refuses `--keys`.

### 32. Rig primitives
*From:* ( - ). *Where:* `canvas/pieces/minus` (`fig`, `walk`); superseded by [33](#33-floor-up-seating)–[35](#35-contact-qa).
Side / front / back views from one angle-driven limb model, a walk from a phase,
items in the near hand. Check the capsule primitive with a still before trusting
it: the first one drew its end caps on the wrong sides and every torso was an
S-shaped blob.

### 33. Floor-up seating
*From:* SAME AS YOU. *Where:* `canvas/lib/rig.js` (`seated`, `seatedLegs`, `chairFor`).
Seat a figure from the floor up — ankle on the floor, vertical shin, horizontal
thigh, pill bottom exactly on the seat — then build the chair **from** the body:
seat top at the pill bottom, front edge at the knee, back post against the
torso, legs to the floor. Body and chair can't disagree. The direct answer to
"the chair doesn't fit" on ( - ).

### 34. Sill-up poses
*From:* SAME AS YOU. *Where:* `canvas/pieces/same-as-you/src/30_window.js`; `canvas/lib/rig.js` (`ik`, `walkLegs`).
Solve a lean from its support up: elbow on the sill at exact upper-arm length,
forearm at exact length toward the jaw, then set the head down on the hands. With
two-bone IK (pole hints) and planted-feet walks (stance centred on the beat, no
sliding).

### 35. Contact QA
*From:* SAME AS YOU. *Where:* `canvas/lib/ink.js` (`contact`, `drawContacts`, `contactReport`); `still.mjs --qa`.
Declare every contact in code — `contact(name, a, b, tol)` logs the distance —
and `?qa=1` draws them on the frame. "Is the chair fitted?" becomes a number;
SAME AS YOU passed every contact at 0 px.

### 56. Exposure as an integral
*From:* SETAREH. *Where:* `canvas/pieces/setareh/src/10_expo.js` (`tabulateLight`, `integ`, `develop`, `tone`, `skyLightBehind`).
A long exposure is the sum of the light that reached the film, so draw it as one.
Each slow light (the moon's, the dawn's) is tabulated at 100 Hz as a running sum
the first time its exposure is needed; the light that arrived between any two
moments is two lookups and a lerp, and the picture stays a pure function of time
([30](#30-pure-function-of-time)) with no accumulated buffer. The display is a
tone curve on that integral, `tone(v) = 1 − exp(−2.7 v)`, over a base exposure
that develops (`0.62 + 0.38 √u`, u the share of the exposure elapsed): the
photograph is dim and noisy at the opening and clears as light gathers. The sky
itself is one 108×192 buffer evaluated per pixel in linear light and scaled up
(it is smooth, and the grain dithers it). The same integral answers how much
light was behind a point over a span, which is what a figure sitting there
blocked ([58](#58-occupancy-ghost)).

### 58. Occupancy ghost
*From:* SETAREH. *Where:* `canvas/pieces/setareh/src/40_people.js` (`herEras`, `drawHerGhost`, `drawHerRim`, `eraLights`).
What moves leaves only its light, and what stays stays in proportion to how long,
in light, it stayed. A figure's opacity is the share of the light behind it that
it blocked while it held a pose, over all the light that reached the film behind
its head so far. Each pose era's paths are filled white at that alpha, summed
with `lighter` (where two poses overlap it was there all along), then inked: what
a mean stack of the exposure would give, computed from the integral
([56](#56-exposure-as-an-integral)) instead of from frames. The lights recorded
in each era are drawn with the figure cut out, because it was in front of them —
through a clip that leaves it out only where a trail can pass behind it. A
figure that never moves is opaque, kept whole. As the sky brightens towards the
dawn the later eras weigh more, so a figure who leaves is washed out by the
light it stood in front of.

---

## Canvas: compositing

### 36. Torn-page mirror
*From:* SAME AS YOU. *Where:* `canvas/pieces/same-as-you/src/20_world.js` (`TEAR`, `PIECE`, `tearEdge`), `90_main.js` (`drawPiece`).
One page in two clipped pieces along a torn edge: his half-world left, hers
right, mirrored, differing only in the people. The gap is one animated number:
distance. Anything mirrored across the seam reads as a Rorschach.

### 37. Chromatography bloom
*From:* SAME AS YOU. *Where:* `canvas/pieces/same-as-you/src/70_fx.js` (`spotsPass`, `RINGS`).
Rain bleeds black ink into blue → magenta → yellow rings: three ring sprites →
two accumulators at quarter resolution → three full-resolution blends (multiply
bleed / colour / screen), restricted to the wet bounding box: ~180 → ~70 ms a
frame. The spots are a pure function of time, seam-biased so mirrored pairs merge
into butterflies, kept off faces.

### 38. Vector droste
*From:* SAME AS YOU. *Where:* `canvas/lib/recursion.js` (`drosteRedraw`); the template's bar 7.
Recurse by redrawing, not resampling: each level draws the whole scene again
inside its own portal, so every level stays crisp. The image-based first try went
blurry at depth. For an exact droste, zoom about the fixed point of the
frame→portal map.

### 39. Vector kaleidoscope
*From:* SAME AS YOU. *Where:* `canvas/lib/recursion.js` (`kaleidoRedraw`).
Each wedge is a full redraw under its own clip and transform, not a copied slice;
the fold count can animate (6 → 8 over four bars). Supersedes [8](#8-kaleido-bloom)
for canvas pieces.

### 43. Inhale-erase splash
*From:* SAME AS YOU (final master). *Where:* `canvas/lib/ink.js` (`drawOn`); `canvas/pieces/same-as-you/src/70_fx.js` (`splashMask`).
For a breath in the music, run the stroke-by-stroke draw-on backwards so the
drawing un-draws itself under a paper veil; on the downbeat, reveal the next scene
through an ink-splat hole in a paper layer (`destination-out`, radius ∝ p², flung
drops) in ~0.3 s. A white flash is invisible on white paper; the splat reads.

### 44. Viewfinder compositor
*From:* SHOULD I ?. *Where:* `canvas/lib/viewfinder.js` (`shootScene`, `composeVF`).
Shoot the scene through a camera transform into its own layer, mix a
quarter-resolution blurred copy by focus error, and composite into a 2:3 finder
with ground glass, fresnel rings, vignette and eyepiece falloff, under an info
strip (shutter speed, match-needle meter, frame counter). It reads as being him
without ever drawing him.

### 45. Split-image sync
*From:* SHOULD I ?. *Where:* `canvas/lib/viewfinder.js` (`split`); `canvas/pieces/should-i/src/80_timeline.js` (`jolts`).
Two clipped half-draws of the scene shifted ±split. Split = focus error (hunts,
then snaps into focus after each shot) plus alternating-sign jolts on vocal-stem
onsets (16 ms attack, 100 ms decay, escalating ×1 → ×2.3 across the stutter; the
circle grows 118 → 250 px so the tear covers the subject). It locks on the
strongest onset in the song.

### 46. Mirror slap
*From:* SHOULD I ?. *Where:* `canvas/lib/viewfinder.js` (`black`); `canvas/pieces/should-i/src/80_timeline.js` (`mirrorSlap`).
On the snare, black only the finder window for 55 ms and return over 60 ms; the
strip stays lit and the counter digit rolls up. Verify on the delivered file:
`signalstats` YAVG at the snare frame = 16. Microprism tiles at 9 px with a 6 px
dot lattice (15 px tiles read as a digital glitch).

### 62. Settling grain and the shutter curtain
*From:* SETAREH. *Where:* `canvas/pieces/setareh/src/50_film.js` (`drawGrain`, `drawShutter`).
A live exposure is noisy at the start and cleaner the more light it has (noise
∝ 1/√light), so the grain amount runs 0.26 → 0.10 over √(share elapsed), and the
moment the shutter closes the photograph is done: the grain freezes at 0.085, on
one fixed tile offset. The close is a two-frame curtain on the 32nd snare — black
at alpha 0.78 for the first frame, 0.30 for the second — and then the finished
picture holds. Measured on the delivered night cut: those two frames (1403 and
1404) match the port's at 44.8 and 38.2 dB PSNR, and their neighbours at
13–21 dB, so the curtain falls on the right frames. The grain is also why the
delivered cuts are rate-limited, not CRF-limited: 11.2 and 11.3 Mb/s with the
audio, against a video cap of 11 Mb/s (measured on the delivered files).

---

## Covers

### 51. Contact-sheet cover
*From:* SHOULD I ?. *Where:* `canvas/pieces/should-i/src/50_film.js` (`drawSheetFinal`, `greaseText`).
Render each exposure once at its capture moment into a cached thumbnail; the same
bitmaps feed the rewind negatives and the contact sheet. A red grease-pencil
circle and the title written in the margin (a marker font with
`destination-out` speckle) make the cover; the square crop is four rows + title.

### 54. Cover variant family
*From:* SHOULD I ? v3. *Where:* `canvas/pieces/should-i/src/60_covers.js` (`drawCoverVariant`); `still.mjs --cover all`.
One draw function, four modes: circle a different frame; three circles with a "?"
each; cross out most frames and keep one; lay a print of an off-roll frame on the
sheet. One browser session renders them all (~3 s per 3000² PNG). A "?" placed on
a circle's stroke merges into it — keep glyphs outside the stroke.

---

## Footage (frame programs)

These run in `kaleidophone.frames` — per-pixel, stateful effects on real footage,
rendered by resumable workers ([ADR-0007](decisions/0007-three-engines-one-contract.md)).

### 6. Red-thread grade
*From:* AHANGE AROOSI. *Where:* `kaleidophone.frames.red_thread_grade`.
Selective survival: drain the world toward two tones (indigo shadows, bone
highlights) except one protected hue band, computed from per-pixel redness. The
grade is the concept: one colour refuses to leave.

### 7. Slit-scan smear
*From:* AHANGE AROOSI. *Where:* `kaleidophone.frames.SlitScan`.
A ring buffer of past frames and a per-column (or per-row) time offset: time pulls
the subject away. A hold region keeps a face sharp on a cover while the rest smears.

### 8. Kaleido bloom
*From:* AHANGE AROOSI. *Where:* `kaleidophone.frames.KaleidoBloom`.
Polar-mirror index maps, cached by size / fold / centre, mixed in only at musical
peaks. (Canvas pieces use [39](#39-vector-kaleidoscope) instead.)

### 9. Tracked overlay inpaint
*From:* AHANGE AROOSI. *Where:* *documented only* ([case study](case-studies/ahange-aroosi.md)).
Removing a burned-in watermark that drifts: sample frames, detect (high-pass text
density, or saturation for coloured stickers), build a time → box path, patch each
frame with a feathered median. The detector lies over busy texture — verify raw
against clean crops at several timestamps. Tell static scene objects from moving
stickers by persistence and camera motion, not position.

### 12. Memory canvas
*From:* MIKONAMET. *Where:* `kaleidophone.frames.MemoryCanvas`.
"The video forgets its own footage": a block grid (48×45 px at 1080p) where each
block refreshes with a scheduled probability (plus bursts on beats and onsets),
an optional live ellipse around the tracked face that shrinks to nothing, and
stale blocks paling toward paper with age. Stateful, so it checkpoints.

### 13. Generation loss
*From:* MIKONAMET. *Where:* `kaleidophone.frames.generation_loss`.
A photocopy of a photocopy: JPEG quality 60 → 14, sub-pixel drift, blur, 10 %
desaturation, contrast ×1.028 and brightness +0.011 per copy, toner speckle after
generation 8, paper tint. Copies must get **paler** — the first version got darker
and read as a burnt negative.

### 14. Mean face
*From:* MIKONAMET. *Where:* `kaleidophone.frames.mean_face`, `MeanFace`.
The eye-aligned average of every frame the subject appears in — the film's last
image and a cover. Means of different takes differ in character (direct gaze vs a
soft smile): compute several, pick by story.

### 17. Lip-sync test
*From:* MIKONAMET. *Where:* *documented only*.
Does a performance take sync at all? Mouth openness (face mesh, 1–8 Hz band)
against vocal-stem RMS, judged by consistency across 10 s windows — one global
correlation peak (z ≈ 4) is noise. It said no, so the film became a 2× slow-motion
piece instead of a lip-synced one.
