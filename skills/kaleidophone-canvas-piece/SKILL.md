---
name: kaleidophone-canvas-piece
description: Make a new procedural canvas piece for a song (no footage; the picture is drawn by code), from the concept to QA stills, a keyframed silent render and covers. Use when the artist has a song but no footage or wants the picture drawn, when starting from canvas/pieces/template, or when a piece needs QA, a render, covers or a synthetic twin.
---

# kaleidophone: a canvas piece

The canvas engine is for releases with no footage. A piece is one
self-contained HTML file that plays live, renders its own film frame by frame
in headless Chromium, and draws its own covers — one draw function for all
three (`docs/decisions/0007-three-engines-one-contract.md`, `canvas/README.md`).
Four releases shipped this way: HAMECHI MANZOR DARE, ( - ), SAME AS YOU and
SHOULD I ?. Their source is in `canvas/pieces/`; start from them and from
`canvas/pieces/template`, never from a blank file. `#N` below is a technique
in `docs/TECHNIQUES.md`.

Everything runs from `canvas/`. Private files — the real song pack, renders,
stills — go in `private/`, which git ignores at any depth.

## 1. Find the rule before you draw anything

The concept is not a storyboard. It is **a rule the renderer obeys**, and the
film falls out of it:

| Piece | The rule |
|---|---|
| ( - ) | She is never drawn. Her silhouette is filled with paper, last, so anything that enters it stops (#28). |
| SAME AS YOU | One page torn in two: his half-world left, hers right, mirrored, differing only in the people. The gap is the distance (#36). |
| SHOULD I ? | Everything is seen through his camera's viewfinder. He is never drawn, except his hands (#44). |
| HAMECHI MANZOR DARE | The walls close in: a swarm whose ring shrinks as the track builds and never lets go (#24). |

A rule makes a hundred small decisions for you, survives a new master, and
reads as intent where a sequence of nice scenes reads as a slideshow. Get the
one line about what the song is from the artist — never invent it — then
propose the rule, two to four rules that hang off it, and what the viewer
sees at the drop and at the end. The rest of the concept lessons are in
`kaleidophone-creative-direction`.

## 2. Count the grid before inventing anything (#47)

```bash
kaleidophone envelope Song.wav -o private/songpack.json
```

It prints the tempo, the first downbeat, the beat count and the loudest 60 s,
and writes the song pack (every key: `docs/CONFIG-SCHEMA.md`, "Song packs").
Then count: bars from the drop to the hook, snares in a passage, bars per
scene. SHOULD I ? has exactly 36 snares from the drop to the bar where the
hook asks its question — one 35 mm roll, a shutter on every snare — and that
count became the whole film. ( - ) is one scene per 8-bar phrase (19.2 s at
100 BPM). The numbers the music already contains make the sync that reads as
magic.

- A grid at double or half time: re-run with `--bpm-range` bracketing the real
  tempo (`--bpm-range 60 100` for a ballad).
- `downbeat` is a guess — the beat phase with the most bass. With a kick on
  every beat it can't tell; put bar 1 where the sections change, as SAME AS
  YOU did, and confirm it by ear.
- `loudest` is the default reel window.
- Vocal onsets for lyric sync come from a separated stem (#48); on fast
  Persian vocals the transcription failed, so ask for the lyric text. Onsets
  are data the piece reads; the words never enter the repository.

### Session in: the MIDI and the stems (#55)

If the artist can export the session, take the grid and the hits from it
instead of guessing them from the master:

```bash
kaleidophone envelope Song.wav --midi Song.mid --stem vocals=stems/Vocals.wav \
     --stem drums=stems/Drums.wav -o private/song.songpack.json
```

- **Ask for** the MIDI as a Standard MIDI File (.mid) with the tempo map, and
  stems bounced over one range, not normalised. Each stem is lined up with the
  master — its band levels and onsets against the master's, within ±2 s — so a
  master trimmed or padded at the head is fine; a stem that can't be lined up
  (a swell with no attack, a part from another song) is refused until you pass
  `--stem-offset NAME=S`, and the refusal says the lag the other stems agree on. Name the tracks as the piece will read them — `kick`,
  `snare`, `hat`, `keys` — before exporting: a kit on one track arrives as one
  list, its pads told apart only by `pitch`. A stem named `vocals`, `vocal`,
  `vox` or `voice` becomes `voc`; for any other name, `--voc-stem NAME`.
- **Commit the groove before exporting.** A DAW's swing and groove templates
  are usually applied on playback, not written into the notes: export without
  committing them, and the events are straight while the bounce swings — every
  swung note off by its swing.
- **Logic Pro** *(menu names inferred, Logic Pro 10–11; check the artist's
  version)*: apply each region's Quantize and Q-Swing to the notes first
  (the region inspector's settings, made permanent: MIDI › Region Parameters ›
  Apply Quantization Settings Permanently, or Normalize Region Parameters);
  then select every MIDI region, File › Export › Selection as MIDI File;
  stems with File › Export › All Tracks as Audio Files over the master's range.
- **Ableton Live** *(inferred, Live 11–12)*: commit any groove from the groove
  pool first (the clip's Groove › Commit); export each MIDI clip with
  right-click › Export MIDI Clip (consolidate a track's clips over the song
  first, so its 0 s is the song's); stems with File › Export Audio/Video,
  Rendered Track: All Individual Tracks, over the master's range. A clip
  carries the set's tempo, not its tempo automation: a song whose tempo moves
  needs the moves checked against the print's tempo map.
- **FL Studio** *(inferred, FL Studio 20–21)*: File › Export › MIDI file from
  the song (Song mode, not a pattern); stems with File › Export › WAV file and
  "Split mixer tracks" ticked.
- **MPC** *(inferred; the menus differ between models and software versions)*:
  a song (a list of sequences) doesn't export as one MIDI file — convert it to
  a sequence first (Song mode's Convert to Sequence), then export that
  sequence as a MIDI file and its tracks as separate audio files from its
  start. A drum program is one track with a note per pad, and the pad notes
  are the program's, not General MIDI's drum numbers (36 is not a kick there
  unless the program says so): name the tracks, or split the kit's pads onto
  tracks named for what they play, before exporting.
- **A clip that starts on a pickup**: its tick 0 isn't bar 1. Pass
  `--downbeat S` with `--midi` (S: bar 1 on the master, in seconds) and the bars
  follow the MIDI's time signatures from there.
- **Read the print.** `offset` is where the MIDI's 0 s falls on the master
  (+ pre-roll, − a bounce that starts later), found from the audio. If the pack
  calls it a guess, check one event by ear and pass `--midi-offset`. `stem lag`
  is where each stem's 0 s falls on the master (− for a master trimmed at the
  head); the stems of one bounce share one. Across a tempo change, read `beats` or
  `midi.tempo_map`, not `makeGrid({ bpm })`. In 6/8 or 12/8, `beats` are
  quarter notes and the felt beat is `pulses` (dotted quarters): a 6/8 groove
  is choreographed to `pulses`, two to the bar.
- The MIDI, the stems and the pack made from them are as private as the
  master: `private/`, never the repository.

## 3. Start from the template

```bash
cp -r pieces/template pieces/<id>        # then rename the title in piece.json and template.html
```

Set the grid in `src/main.js` (`makeGrid({ bpm, downbeat })`, `DUR`) and in
`piece.json` (`grid`), and list the lib modules you use under `lib`. In
`piece.json`, `grid`, `cuts` and `keyframes` are the record of what shipped —
the render tool doesn't read them, so pass keyframes to it yourself. Then:

```bash
node tools/build.mjs <id> --song private/songpack.json      # -> dist/<id>.html; bakes what piece.json `bake` names from this pack
node tools/still.mjs <id> --song private/songpack.json --t 1,4,9 --qa --out private/stills
```

A build from the real pack is as private as the pack.

## 4. The contract: three modes, one draw function (#19)

End the last module with `boot({ bpm, dur, draw(t, env, flags), cover(name, arg) })`
(`canvas/lib/live.js`). No query is **live**: click for a procedural pad and
beat at the tempo (#20), or drop the track on it. `?render=1` is **render**:
the harness calls `window.__frame`. `?cover=1` is **cover**: `window.__cover(name)`.
`driver.mjs` states only what differs from the default driver in
`canvas/tools/lib/common.mjs` — which envelope keys to sample, how a cover or
a card is asked for.

**Make it a pure function of time (#30).** Nothing carried from frame to
frame; every "random" choice hashed from the time or drawing number and an
index (`hsh`, `HS`, `mulberry32` in `core.js`), never `Math.random()`. Then
any window renders on its own and in parallel, a new master on the same grid
is a constants change — ( - ) went from a 1:46 demo to the 2:58 master in one
evening — and a signature card is a flag. The template's driver also hands
the piece the whole pack through `__init`, so `envAt(name, t + d)` can look
ahead: anticipation stays deterministic.

State is the expensive alternative. HAMECHI MANZOR DARE, the one stateful
piece, renders in one worker, in order, from a 3 s warm-up with a
harness-planned mask schedule — and because the harness that rendered the
release wasn't kept, its released reel can't be reproduced frame for frame. If
a concept really needs state, set `stateful: true` in the driver and keep the
harness with the release.

## 5. The lib: which module when

| Module | Reach for it when |
|---|---|
| `core.js` | always: the grid (`makeGrid`: `bt`, `barOf`, `beatOf`, `sinceBeat`, `isBackbeat`, `onTwos`), `envAt`, `kf` keyframes, hashes and noise, sprites and grain tiles, `strokeScale` |
| `live.js` | always: the stage (a 1080×1920 virtual frame, `base()`), `boot()`, `coverCrop` |
| `ink.js` | the picture is drawn: boil on twos, stroke-by-stroke draw-on and erase (#43), paper grain, the contact log (#35), hand-lettered titles (`word`) |
| `rig.js` | there are people: two-bone IK, seated bodies built from the floor up with chairs built from the body, planted-feet walks (#33, #34) |
| `recursion.js` | a droste or a kaleidoscope: recursion by redrawing, crisp at any depth (#38, #39) |
| `viewfinder.js` | the film is someone looking through a camera: split-image focus, microprism, meter, counter, mirror slap (#44–#46) |

Everything else is in the four pieces, indexed in `docs/TECHNIQUES.md`
("Canvas: drawing", "Canvas: compositing", "Covers"): the paper cut-out (#28),
sprite fire (#23), the torn-page mirror (#36), chromatography (#37),
loop-continuity clocks (#40), the contact-sheet cover (#51). Copy what you
borrow into the new piece. The shipped pieces stay as they shipped (ADR-0007);
a technique that proves general belongs in `canvas/lib/`.

## 6. If it's drawn: on twos, and boil (#29)

Twelve drawings a second (`boilFrame(t, rms)` once per frame, `G.onTwos(t)`
for motion), every point of every polyline jittered, round caps, flat fills,
three greys + paper + one accent. The crudeness reads as intent, and it is
cheap. Only the drawing needs to be on twos — SAME AS YOU's rain and camera
run on ones. Render at 24 fps and let the piece hold each drawing for two
frames. `render.mjs --fps 12 --out-fps 24` works too, and ( - ) shipped that
way, but it re-encodes and refuses `--keys`: no stream-copied cuts later.

## 7. QA stills before any long render

A still costs seconds; a film costs minutes — SAME AS YOU's 3244 frames took
541 s at 1080p on 2 cloud cores, where 540p drafts ran at 17 fps against 6.0.
Look first, and show the artist stills, not a description, before the long
render.

- Take stills at every scene start, every planned hit, the card, the last
  frame, and both sides of the seam of a looping reel (#40).
- **Contacts (#35).** Declare every body↔furniture contact
  (`contact(name, a, b, tol)`); `--qa` draws them and prints
  `{n, worst, d, failing}` per still. Get `failing` to 0 — SAME AS YOU passed
  every contact at 0 px. Seat people with `seated()` and `chairFor()` and
  "the chair doesn't fit" can't happen (#33).
- **Check a primitive with a still before trusting it (#32).** ( - )'s first
  capsule drew every torso as an S-shaped blob.
- **Stroke scaling (#22).** A piece tuned at 1080 goes hairline on a 3000 px
  cover. Draw in the virtual frame's units (`base()`, `LW()`) so widths scale
  with the output; multiply anything drawn in device pixels (an offscreen
  layer, a sprite) or at another subject size by `strokeScale(subjectSize)`.
  Render one cover at full size before trusting the others.

## 8. Render once, silent, keyframed at every planned cut (#41)

Plan the deliverables first (`kaleidophone-release-kit`). The delivery sheet
knows every point a cut starts, resumes or ends at, and
`kaleidophone deliver delivery.yaml --dry-run` prints them before the render
exists (`-force_key_frames …`, in seconds). `--keys` takes frame numbers of
the render window: seconds × fps, counted from `--t0`. SAME AS YOU's, at 24
fps: `0,630,1014,1350,1734,1926,2310` for cuts at 0, 26.25, 42.25, 56.25,
72.25, 80.25 and 96.25 s.

```bash
node tools/render.mjs <id> --song private/songpack.json --t0 0 --dur <film length> \
     --keys <frame numbers> --workers 2 --out private/full_silent.mp4
```

- **Silent, always,** and from `--t0 0`: `kaleidophone deliver` cuts the
  picture and the master at the same `t0`, so the render's clock has to be
  the song's. The audio goes on where the master lives, never here.
- `--card` draws the piece's signature card over the window's first frames
  (pieces that have one). The reel gets its card as a separate short render,
  concatenated in front at delivery, so the full film never carries a
  mid-film title (#16).
- `--from N --to M` renders frames [N, M) of the window: to resume, to split
  across machines, or to redo only the bars a new master changed
  (`kaleidophone-master-swap`).
- `--png-frames 60,450` also saves lossless frames of the real render for QA.
- A stateful piece renders in one worker from a warm-up and snaps `t0` to a
  beat (unless `--snap false`); the audio must use the value it prints (#21).

## 9. Covers from the piece's own draw code (#31, #51, #54)

List them under `covers` in `piece.json` (`size`, `variants`) and render the
whole family in one browser session:

```bash
node tools/still.mjs <id> --song private/songpack.json --cover all --size 3000 --out private/covers
```

- A square cover is a crop of the portrait composition (`coverCrop(top)`),
  so the stroke weight stays the portrait's (#31).
- One draw function, many variants (#54): SHOULD I ?'s family renders at
  ~3 s per 3000² PNG. Keep glyphs off strokes — a "?" on a circle's stroke
  merges into it.
- The frame the concept can't contain is often the cover: SHOULD I ?'s roll
  has 36 frames, and its 37th ends the film and prints on a cover (#53).
- Covers are deliverables: PNG, which is what `still.mjs` writes.

## 10. The synthetic twin: how the piece lives in the repository

A real song pack is derived from an unreleased master, so it is private like
the audio (ADR-0003, ADR-0007). The repository holds a **synthetic twin**: the
real tempo, first downbeat and section boundaries, and each section's level
per envelope as `[mean, p95, max]` rounded to 0.05, with every hit generated
(plus, where a piece reads them, hand-placed timing windows such as SHOULD I ?'s
vocal and stutter windows).

```bash
node tools/synth.mjs --twin private/songpack.json --sections 0,32.26,42.26,72.25 \
     --downbeat 0.255 > pieces/<id>/synthetic.json
node tools/synth.mjs <id>        # -> out/songs/<id>.songpack.json, what CI and the gallery run on
```

- Pass `--downbeat` when you know bar 1. Without it the twin takes the pack's
  `downbeat` (or its `beat0`, the first grid beat, for a pack without one) —
  an estimate: read the pack's `grid_check.downbeat.confidence`, and check the
  bar by ear.
- `--twin` measures levels only (`--twin real.json --piece <id>` re-measures a
  piece's spec in place and keeps everything written by hand). Add each
  section's `kick` (`all`, `1-3`, `none`), `snare`, `hats` and `crash` by ear, and `voc` windows and `events` wherever
  the piece reads them, placed where the real ones fall (the spec:
  `docs/CONFIG-SCHEMA.md`, "Song packs").
- Add a `gallery` entry (`t0`, `dur`, `fps`, `cover`) to `piece.json`: CI
  renders the gallery from the twin on every push to `main`. Take stills on
  the twin too — the gallery shows what the twin makes.
- `npm test` checks that every twin synthesizes and that its length is close
  to the piece's `grid.dur`.

## Privacy: what never enters the repository

The real song pack, the WAV and any stem, lyrics or a lyric map, renders and
stills, collaborators' names. Git ignores media, `private/` and
`canvas/out/`, and CI refuses media and personal paths — but the words are on
you: a lyric never goes into a piece's source, its `piece.json` summary or a
commit message. Onsets are data, baked into the build from whichever pack you
pass (`bake` in `piece.json`). A piece's own design words (HAMECHI MANZOR
DARE's swarm) are fine; the song's are not.

## Start from what shipped

`pieces/template` (the lib in one 8-bar loop) · `pieces/minus` (the cut-out,
on twos, a card flag) · `pieces/same-as-you` (rig v2, the torn page, a reel
that loops on its own first frame) · `pieces/should-i` (the viewfinder, grid
arithmetic, the cover family, the card as its own segment) ·
`pieces/hamechi-manzor-dare` (the stateful one — read its driver before
writing another). Their case studies are in `docs/case-studies/`.
