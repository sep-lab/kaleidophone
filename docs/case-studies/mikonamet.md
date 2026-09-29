# Case study: MIKONAMET YEROZI KHOB FARAMOOSH

**MIKONAMET YEROZI KHOB FARAMOOSH** (Persian; roughly "one day I'll forget
you, for good") · Sep The Concept · September 2026 · 3:48 · the artist's own
camera footage, a python frame engine

The eighth release in the series: **a music video that forgets itself.** It
is built from footage the artist shot of himself, and delivered as a 16:9
film plus three 9:16 cuts, all rendered on the machine that holds the
footage. It closes [#41](https://github.com/sep-lab/kaleidophone/issues/41)
("a camera-sourced vertical release").

What it proves for the framework: the python frame engine moved onto the
artist's own machine, and 1.2 GB of 1080p50 source never left it. Its
signature effect is stateful, which made checkpointed, resumable workers
mandatory rather than a nice-to-have. It is also the first release that ran
a full v1 → QA → v2 loop on three of six segments without re-rendering the
other three.

**What's scrubbed and why:** the footage is the artist's own face. No frame
of it appears here, and the takes are described only as far as the
techniques need. No lyrics: none were on screen, and the lyric text never
arrived during the build, so the captions quote nothing. The mastering
service and all file hashes are omitted. None of this engine is in the
repository; this is the technique record. Numbers are **measured on the
release** unless marked otherwise.

## The rule: the video forgets its own footage

Three clips are three acts of one memory: *as it was*, *as it became*,
*after*. As the song goes on, the picture loses its own footage:

- Blocks of pixels stop re-recording and hold stale moments: the memory
  canvas.
- Colors leave one at a time, skin last.
- Recalled frames come back as photocopies of photocopies.
- The face is the last thing to go. It fragments block by block, then
  dissolves into the eye-aligned **mean of every frame it appears in** (2022
  frames at 1080p).
- The last clip has nobody in it. The picture whites out, then a hard stop
  to black.

The title writes itself right to left in the intro. On the end card it
forgets itself: first the dots, then the strokes, then a trace. One gesture
brackets the film: once at the drop in real time, and again as the last
shot, reversed and slowed. Beyond that, label nothing and react to
everything. Beats and onsets drive the memory canvas's refresh bursts, and
the cuts snap to the beat grid.

**There is no lip-sync, and that was a finding, not a style**
([#17](../TECHNIQUES.md#17-lip-sync-test)). It was checked two ways: the
camera's own audio against the master, by cross-correlation, and mouth
openness against the vocal stem. For the second, FaceMesh lip landmarks
13/14 over face height, band-passed to 1–8 Hz, were compared with the stem's
band-passed RMS, judged by their consistency across 10 s windows. A single
global correlation peak (z ≈ 4) turned out to be noise. The takes had been
performed freely, without playback. So the film runs at 2× slow motion
throughout (50p conformed to 25p), which is also its emotional register, and
nothing is presented as sync.

## The track

It is a 3:50 file with a hard stop at 3:48.0, ~80 BPM, D major/minor
ambiguous. The sung register is about G3–C4, with a low spoken register
(~118 Hz) at 1:50–2:00 and through the whole outro. Master: −9 LUFS, −0.3
dBFS sample peak.

| t (s) | Section |
|---|---|
| 0–19.5 | intro: sparse and wide, a pitched vocal |
| 19.5 | the drop |
| 25.9 | verse 1 |
| 36 | the hook (it returns at 71 and 83) |
| 95.8 | a vocal line repeated three times |
| 101.6–120.4 | breakdown, with a low spoken voice at 108–120 |
| 120.4 | verse 2 (a strong vocal to ~153) |
| 154–168 | a wordless vocalise |
| 168–191 | probably the title line (the transcription was unreliable) |
| 191–228 | spoken monologue |
| 228.0 | hard stop |

Speech recognition failed on this vocal. Stem separation plus Whisper
returned fragments, not lyrics: the processed vocal and the fast Persian
flow defeated it. That is the failure case recorded under
[#48](../TECHNIQUES.md#48-lyric-map-from-stem); the fix is to ask the artist
for the text.

## The edit

The times below are film seconds. The two performance takes run at 0.5×.

| t (s) | What the engine does |
|---|---|
| 0 | the third clip at 1×. The title writes itself from 3 to 14 s and fades at the drop |
| 25.9–101.6 | the first take, cut on the beat grid. The recall flashes begin |
| 101.6 | **HOLD**: the last frame photocopies itself, one generation per 0.3 s, for 8.7 s |
| 110.3 | the first take again, under the spoken voice |
| 120.4–204 | the second take. The memory canvas takes over; from 191 the face goes stale, and the live ellipse around it shrinks to zero by 203 |
| 204 | the mean face (a 4 s crossfade, a slow zoom) |
| 214 | the third clip, pale |
| 224.2 | the same clip reversed, at −0.5× |
| 228 | black |
| 228.5–236 | end card: the title erodes through levels 0 → 4 |

Recall flashes are photocopied earlier frames, 4–9 frames each and
beat-snapped. They land at 66.2, 88.4, 131, 144.9, 152.6, 160.9, 166.3, 174,
183.6, 188.9, 196.4 and 201.7 s, at generations rising from 2 to 40.

## How it was built

A python per-frame engine (numpy float RGB, OpenCV, PIL with raqm,
MediaPipe) renders from an EDL with beat-snapped boundaries and an envelope
pack computed from the WAV. The effects:

**The memory canvas** ([#12](../TECHNIQUES.md#12-memory-canvas)). The frame
is a grid of 48×45 px blocks at 1080p, and each block remembers when it was
last refreshed. A refresh-probability schedule p(t) falls from 1 to 0.15 to
0.02, with bursts on beats and onsets. A live ellipse around the tracked
face shrinks to zero. Stale blocks pale toward paper with age, through a
feathered age-fade mask. The effect is the concept, and it is stateful:
every frame depends on every frame before it.

**Generation loss** ([#13](../TECHNIQUES.md#13-generation-loss)). Each copy
applies JPEG quality falling from 60 to 14, a sub-pixel drift, a blur, 10 %
desaturation, contrast ×1.028 and brightness +0.011. Toner speckle starts
after generation 8, and the paper is tinted. Copies must get *paler*: the
first version went dark and read as a burnt negative.

**The mean face** ([#14](../TECHNIQUES.md#14-mean-face)). Every frame is
similarity-aligned on MediaPipe iris landmarks, tracked on 640×360 proxies
at 25 fps and scaled ×3. Frames are decoded sequentially, and the job is
resumable. The mean over all frames is the film's ending image. A single
take's mean has sharper eyes and made the better cover, and takes differ in
character, so compute both and pick by the story.

**Titles** ([#15](../TECHNIQUES.md#15-rtl-title-erosion),
[#16](../TECHNIQUES.md#16-signature-card)). They are set with PIL + raqm in
Vazirmatn Light. "The title writes itself" is a soft right-to-left wipe mask
computed in the engine. Never render growing prefixes of Persian text,
because the shaping flickers between medial and final letterforms. Erosion
first drops connected components smaller than 20 % of the 80th-percentile
stroke area (the dots), then breaks and erodes the strokes against a noise
threshold. The vertical cuts open on a 1.6 s **signature card** (the title
writing itself over the third clip) instead of laying text over the face.
The platform uses a reel's first frame as its cover, so the card doubles as
the cover.

**On-device, resumable rendering**
([#5](../TECHNIQUES.md#5-on-device-rendering)). The only render box that
could reach the footage without moving it was a local 4-core VM with ffmpeg,
python3, numpy, OpenCV and PIL (3.8 GB of RAM). Each command there had a 180
s budget, and background processes died when it returned. So every long job
was built to resume:

- A launcher spawns up to three workers per command, each with a 150 s
  budget.
- Each worker checkpoints the full effect state (the canvas, block ages,
  RNG, hold state and frame index) to a `.npz` file, and appends a new
  `_partNNN.mp4` per call.
- At the end, the concat demuxer joins the parts, with `-c:v copy`, and the
  audio is muxed.
- Worker ranges start at cuts, where resetting the memory canvas is
  acceptable.

**Measured:** ~8.7 fps for one worker and ~13 fps for three, at 1080p. 5900
frames plus 3 × 1540 more took about 12 minutes of wall time. Nothing but
360p proxies, keyframes and small previews ever left the machine. One more
fix: use `cv2.grab()` for small forward steps. Per-frame seeks in 50p H.264
ran at ~1.5 fps until it was fixed.

## Delivery

All files are 1080p25 with AAC audio.

| Cut | Frame | What it is |
|---|---|---|
| film | 1920×1080 | 3:56 (236 s, with the end card), 305 MB |
| reel A | 1080×1920 | 61.6 s: the 1.6 s signature card, then film 0:36 → 1:36 |
| reel B | 1080×1920 | card, then 2:00 → 3:00: the concept reel |
| story | 1080×1920 | card, then 2:24 → 3:24, the artist's chosen window |
| covers | 3000² | five, texted and textless, each an effect as a still: the memory canvas, the mean face (eroded-title and intact-title variants), a photocopy at generation 24, a single surviving color, a rotational smear. Plus a thumbnail and a contact sheet |

**The vertical part.** The 9:16 cuts are 608-pixel-wide windows of the
1920×1080 film. They follow the tracked face and are scaled up 1.78× to
1080×1920. Each opens on the signature card, never on text over the face.

**Loudness** ([#18](../TECHNIQUES.md#18-aac-true-peak-guard)). The master
(−9 LUFS, −0.3 dBFS sample peak) overshot to **+1.7 dBTP** after AAC on the
first mux. The fix was `volume=-2.5dB` before the encoder, with no limiter:
−0.7 to −1.5 dBTP at −11 LUFS. Measure `ebur128=peak=true` on the delivered
file, not on the WAV. The reels fade the audio out over 1.5 s, because the
platform loops them.

## QA: the honest list, as shipped

1. **No lip-sync, by design.** In 0:36–0:56 the singing mouth at half speed
   is visibly not the vocal. It reads as stylized; real sync would need a
   take performed to playback.
2. **The verticals are soft.** A 608-px crop scaled up 1.78× is softer than
   the film, though the grain hides most of it. Reel A's first second after
   the card crops too tight at the top.
3. **The HOLD can look like a frozen player.** It is an 8.7 s still that
   photocopies itself (1:41.6–1:50.3), and some viewers may think the player
   froze. Shortening it to ~5 s is an EDL change and a partial re-render.
4. **The stale-block grid is hard-edged.** It can read as glitch or
   pixelation rather than memory. It is the boldest choice in the piece, and
   block size and feather are parameters.
5. **The eroded title can look like a typo.** Once the dots are gone, it may
   just read as a mistake to anyone who doesn't get the concept. That's why
   there is an intact-title variant.
6. **Recall flashes are strobes**: twelve of them, 4–9 frames each, spaced
   at least 5 s apart. Mild, but worth a note.

The loop that proved the engine: v1 → QA boards → v2 on three of the six
segments, leaving the other three untouched.

## What it contributed

New:

- [#12 Memory canvas](../TECHNIQUES.md#12-memory-canvas)
- [#13 Generation loss](../TECHNIQUES.md#13-generation-loss)
- [#14 Mean face](../TECHNIQUES.md#14-mean-face)
- [#15 RTL title erosion](../TECHNIQUES.md#15-rtl-title-erosion)
- [#16 Signature card](../TECHNIQUES.md#16-signature-card)
- [#17 Lip-sync test](../TECHNIQUES.md#17-lip-sync-test)
- [#18 AAC true-peak guard](../TECHNIQUES.md#18-aac-true-peak-guard)

Re-derived, not new: envelope-driven effects, a beat-snapped EDL, segment
renders joined with the concat demuxer, check-frame QA boards, "label
nothing, react to everything", and
[on-device rendering](../TECHNIQUES.md#5-on-device-rendering). This time
on-device rendering was forced by a stateful effect under a per-command time
limit, the fifth distinct reason a release has arrived at
segment-then-concat (see the [index](README.md)).
