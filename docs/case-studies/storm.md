# Case study: ⛈️

**⛈️** · Sep The Concept · October 2026 · 5:37 · a top-down pixel city at
night, drawn at a third of the resolution and dithered to 5 bits a channel;
canvas 2D, no source footage

The fourteenth release in the tally, and a canvas piece. Its title is the
emoji; where a word is needed, the delivered files say STORM, and so does this
document. It is the first release built from start to finish with this
repository's own tools while it was still private. The piece lived in a folder
outside the repository, and `build.mjs`, `render.mjs` and `still.mjs` worked on
it there through `KALEIDOPHONE_PIECES`. It landed as a copy of that folder, not
a port. Its source is at `canvas/pieces/storm/`.

What it proves for the framework: the private-piece route works end to end.
A piece written against the repository's lib and harness, but outside it, can
join it later with nothing changed but a scrub. Built from its private song
pack, the folder as it shipped is the shipped HTML byte for byte. It is also
the biggest break so far from the house look of the canvas pieces: a
top-down camera, colourful albedos under a light map, and an ordered dither
in place of grain.

**What's scrubbed and why:** the city the grid is drawn after is not named, here
or in the source. Two comments in the shipped piece named a real city and
district, and the port rewords them. One helper function was renamed in the
same pass. No audio and no song pack: the repository's copy runs on a
synthetic twin. The intro's melody, whose pitches colour the sax player's
notes, is the song's own, so the twin invents its notes and their pitches
instead. Numbers are **measured on the release** (on the delivered files, or
read from the shipped source) unless marked cited or inferred.

## The rule: at 0:33 the rain stops for everyone but him

1. **The storm comes for him.** Light before sound: every thunder in the
   intro's field recording is preceded by its flash, and the gap is the
   distance at 343 m a second. The gaps shrink as the storm walks toward him,
   and at 0:33, when the beat lands, the gap is zero
   ([#66](../TECHNIQUES.md#66-light-before-sound)).
2. **There the city's rain gathers into one small cloud over one man**, the
   emoji, and follows him through a city that is drying out. Umbrellas close.
   From then on its thunder is the beat: it flickers on the snares (bright)
   and the kicks (dim), and strikes the street beside him wherever the song
   changes room.
3. **Game time: a second is a minute.** The song is one sleepless night,
   02:00 → 07:36 ([#69](../TECHNIQUES.md#69-game-time-hud)). The city wakes up
   around him, and his storm leaves a wet trail that is, by dawn, the night's
   route ([#71](../TECHNIQUES.md#71-puddle-sky-and-drying-trail)).
4. **He never stops**: a step on every beat
   ([#68](../TECHNIQUES.md#68-landmark-pinned-path)). At 5:36.02 the music
   stops dead and the game pauses. The streetlights go out for dawn, the rain
   hangs in the air, a bolt hangs over the crossing, and the only thing still
   moving is him. He looks up, at us
   ([#67](../TECHNIQUES.md#67-split-clocks)).

The look is a console game's: the city drawn at 360 × 640 and scaled up three
times with no smoothing, colour quantised to 5 bits a channel through a 4 × 4
ordered dither ([#63](../TECHNIQUES.md#63-console-pixel-pipeline)), and lit
the way a game engine lights a scene
([#64](../TECHNIQUES.md#64-deferred-2d-lighting)).

## The track

80 BPM, a 3.0 s bar, first downbeat at 0.02 s, 5:37.30 long. `kaleidophone
envelope` found the grid with a downbeat confidence of 0.68 and no warnings,
and every 8-bar section it could check (bars 9–104) sat within 11 ms of it.
The intro, up to 33.02 s, is rain and thunder with keys under it. The beat
comes in at 33.02 s, and the music stops dead at 336.02 s; the master is
silent after about 5:36.5 (cited from the release's mux notes).

What the piece reads is `events.storm` in its private pack, written by a
private script from the master and the envelope pack:

| Key | What | How it was found |
|---|---|---|
| `thunder` | 8 claps in the intro | 25–250 Hz bursts more than 6 dB above a 6 s running median and at least 0.12 s long, as candidates; then curated by ear |
| `melody` | 99 onsets of the keys under the rain, each with its loudest constant-Q bin from C3 | harmonic onsets: HPSS, then spectral flux in 150–2000 Hz |
| `kick`, `snare` | 414 and 200 | onsets in 35–130 Hz and 1.5–6 kHz, kept only within 60 ms of the 8th-note grid (kicks) or of beats 2 and 4 (snares) |
| `rooms` | 18 section changes, each with a strength | curated |
| `beat_in`, `stop`, `rain_fade` | 33.02 s, 336.02 s, 31.5–34.0 s | curated |

The curated lists (thunder, rooms, beat-in, stop) are also constants in the
piece (`STORM_DEFAULT` in `00_rule.js`), and kicks and snares fall back to the
grid. So the piece always has a storm, whatever pack it is given: that is how
the twin runs it. The script itself is not in the repository. A general
`kaleidophone events` is milestone M8's job
([ROADMAP.md](../ROADMAP.md), Phase 2e).

## What the film shows

| t (s) | |
|---|---|
| 0–1.9 | the signature card: the weather icon in the middle of the frame, then flying into the HUD's corner as the clock starts at 02:00 |
| 0–31.5 | rain on the whole city. He walks north into the storm, past the sax player in a doorway (he flicks a coin into the case at 13.35) and a couple dancing under one red umbrella; the flashes come closer |
| 31.5–36 | the rain's edge closes in on him from every side |
| **33.02** | **the beat**: the rain gathers into his cloud |
| 34 | he steps off the kerb onto the first zebra; behind him the couple's umbrella closes (33.9–35.4), and they keep dancing |
| 37–45 | the camera rises to 245 m: the first look at the map |
| 45.02 → 324.02 | his cloud strikes the street beside him at every change of room (17 of them) |
| 293.27 | under the dawn café's awning, the only dry metres his storm allows him, he lights a cigarette on a snare |
| 300.02 | pigeons burst into the air on the finale's strike |
| 304–312.5 | the camera rises to 430 m: the city has dried, except the dark line of the night's route |
| **336.02** | **the stop**: the world pauses. The lamps go out, the rain hangs, the last bolt is held, the frame's edges dim |
| 336.4–338.94 | his hood falls back and he looks up; the clock blinks 07:36 |

## How it was built

`canvas/pieces/storm/src/` holds 16 modules, 141 KB of source: the largest
piece so far. It uses only `core` and `live` from the lib, and draws its own
glyphs, light and dither.

| Module | Role |
|---|---|
| `00_rule.js` | the rule, the grid, the storm's events with their defaults, game time and dawn, the palette |
| `10_city.js` | the city: chamfered blocks, lots, courtyards and street segments, memoised ([#70](../TECHNIQUES.md#70-world-anchored-procedural-city)) |
| `20_walk.js` | the route, its two landmarks, and where he is at any `t` |
| `30_view.js` | the camera: straight down, with perspective; its height keyframes |
| `40_ground.js` | asphalt, kerbs, markings, wear, leaves, the wet trail |
| `45_build.js` | buildings in painter's order, windows, shops and their hours |
| `48_street.js` | street furniture, lamps, cars, the cafés' terraces |
| `50_people.js` | people from above, half as big again as life so they read at a third of the resolution |
| `52_cast.js` | the sax player, the couple, the cat, the pigeons |
| `55_him.js` | him |
| `58_details.js` | steam, a pharmacy cross, washing on the roofs, gulls, a sheet of newspaper |
| `60_sky.js` | the thunder and its flashes, his strikes, the rain, his cloud |
| `65_puddles.js` | puddles: the only sky there is |
| `70_light.js` | the light map, the lit layers, the tone curve and the dither |
| `80_hud.js` | the clock, the weather icon, the card |
| `90_main.js` | the frame, the covers, the three modes |

**A pure function of time and the pack.** `90_main.js` resets every context at
the start of every frame, and there is no `Math.random()` or `Date.now()` in
the piece, so any frame renders on its own and windows split across workers
([#30](../TECHNIQUES.md#30-pure-function-of-time)). The driver hands the whole
song pack to the page once (`window.__init`), and `--flags '{"cardT0": …}'`
opens a cut on the card. Each 1439-frame cut took 4 to 6 minutes on two cores,
about 4.5 to 6.5 fps (cited from the release's working notes).

**Built and rendered as a private piece.** Until it was released, the piece
was not in the repository, and the repository's tools ran on it in place:

```bash
export KALEIDOPHONE_PIECES=/path/to/private/pieces     # holds storm/: piece.json, src/, driver.mjs
node tools/build.mjs storm --song /path/to/private/storm.events.songpack.json --out /path/to/private/storm.html
node tools/render.mjs storm --song /path/to/private/storm.events.songpack.json --t0 0 --dur 59.958333 \
     --flags '{"cardT0":0}' --crf 17 --out /path/to/private/rain_silent.mp4
```

Because the lib, the fonts and the harness were this repository's, landing it
was a copy of the folder. The private-piece workflow is in
[canvas/README.md](../../canvas/README.md#private-pieces-kaleidophone_pieces).

## Delivery

Two vertical cuts, each its own render, opening on the card. Both were cut,
muxed and measured by a hand-written script, not `kaleidophone deliver`. It
re-encoded the picture as H.264 High at CRF 19, capped at 11 Mb/s, with no
B-frames, so a 1439-frame cut is 59.958 s even where a player ignores the
edit list (the Stories cap is 60 s). The audio was the master's window at one
gain for the whole song, through a 4×-oversampled limiter, AAC at 256 kb/s,
one frame shorter than the picture. Its targets were −1.0 dBTP or lower for a
cut quieter than −14 LUFS, and −2.0 dBTP or lower for a louder one (all cited
from the mux notes).

| Cut | Window (s) | Frames | Delivered |
|---|---|---|---|
| rain | 0 → 59.958 | 1439 | −17.3 LUFS / −2.5 dBTP · 79.0 MB · 10.5 Mb/s |
| stop | 278.978 → 338.937 | 1439 | −13.7 LUFS / −2.3 dBTP · 82.4 MB · 11.0 Mb/s |

Both: H.264 High with no B-frames, 24 fps, 59.958 s with the edit list read or
ignored, AAC-LC at 48 kHz (measured on the delivered files). The rain cut fades
over its last 2.9 s, from the phrase's end and the strike at 57.02. The stop
cut starts one frame before the 4:39.02 downbeat, so that bar's kick keeps its
attack, and holds the pause for 2.92 s after the stop at its frame 1369 (cited
from the mux notes).

**It shipped from an MP3.** The song pack and both cuts' audio came from a
160 kb/s, 48 kHz MP3, the only master in the project folder (measured: no WAV
there). An MP3 decoder adds a delay: [#49](../TECHNIQUES.md#49-master-drop-in-check)
measured −0.023 s at 48 kHz on synthetic masters. So the picture is timed to
the MP3, and a re-delivery from the WAV starts with `kaleidophone master-check`.
Expect an offset of about that size (exit 5, with the `silent_start` to use),
not a re-render (inferred).

**Covers.** Six variants (map, pause, couple, sax, night, icon) in three
formats: 3000 × 3000, 1080 × 1350 and 1080 × 1920. Each is a frame of the game
at the size asked, with the credit in the game's own letters, and the icon
variant is the title. One browser session rendered all 18; they were delivered
as JPG at quality 93, 4:4:4, 300 dpi (cited from the working notes). A cover at
2000 px or wider draws with a 6-pixel game pixel, so the square keeps the
console's chunk. `coverDraw` records where the focus, the HUD, the icon and the
credit landed (`LAST_COVER`), so their placement can be checked as numbers.

## What went wrong

- **`deliver` couldn't ship it.** The mux script re-implemented `deliver`'s
  limiter, because `deliver` writes `-c:a aac` only, stream-copies the render,
  can't fit a cut under the Stories cap, and doesn't check the duration with
  the edit list ignored. Milestone M3 (deliver v2) is that list.
- **The covers needed their own script**, because `still.mjs` takes one size
  and writes PNG only. The JPG conversion was a separate step.
- **`grep -q` under `pipefail` says "not there".** Checking ffmpeg's encoder
  list with `ffmpeg -encoders | grep -q aac_at` under `set -o pipefail` can
  fail even when the encoder is there: grep exits on the first match, ffmpeg
  dies on the broken pipe, and the pipeline reports the failure. Read the list
  into a variable first (cited from the mux script).
- **The camera jumped at every corner.** It followed the route segments'
  directions, which switch in one frame. It now follows a chord from 3 m
  behind him to 6 m ahead, and corners are arcs.
- **Two 60 s cuts, and no film.** The piece covers the whole song (the route
  runs from 0 to the stop, and the camera keys run to 342 s), so the full film
  is one render, about 8,100 frames, 21 to 30 minutes on two cores at the
  release's speed (inferred). It was never made; it is milestone M3's exit.
- **The events script is outside the repository.** A new master means
  re-running a private script, and curating the thunder and rooms again.

## The port in this repository

**Measured on the port** (2026-10-07, Chromium 141.0.7390.37, ffmpeg 7.1,
node 24.19):

- Built from its private song pack, the folder as it shipped is byte-identical
  to the shipped HTML (193,794 B). After the scrub it differs only in the
  scrubbed lines: applying the same substitutions to the shipped file gives
  the port's build byte for byte.
- 9 of 9 test frames (5 from the rain cut, 4 from the stop cut, including the
  stop frame and the pause, through `render.mjs --png-frames`) and 18 of 18
  covers render PNG-identical from the shipped HTML and from the port.
- Against frames decoded from the delivered cuts, the port scores 34.3–36.5 dB
  PSNR at the matching frame and 25.5–33.3 dB at the frame after it, so it
  matches the frame, not just the scene. The covers score 38.0–43.0 dB against
  the delivered JPGs.
- **The synthetic twin.** Its sections start at the beat-in and at every room,
  with levels measured by `synth.mjs --twin`. The intro's keys are invented
  onsets with invented pitches (`events.storm.melody` as `[t, s, bin]`, the
  first use of `synth.mjs`'s pitch column), so the sax player's notes always
  have a colour. Thunder, rooms and drums are left to the piece's own
  constants and its grid.
- **Frozen.** The page built from the twin (retitled, as the gallery and the
  release zip ship it), the twin and its pack are pinned in
  `canvas/test/contract.test.mjs`, and its golden frames in
  `canvas/test/golden/storm.sha256`. It builds on the lib as v0.4.0 had it
  (`"libVersion": "0.4.0"`); pinned or not, the private build is the same bytes.
- The gallery clip starts at 32 s: two seconds of rain over the whole city,
  then it gathers into his cloud.

## What it contributed

New:

- [#63 Console pixel pipeline](../TECHNIQUES.md#63-console-pixel-pipeline)
- [#64 Deferred 2D lighting](../TECHNIQUES.md#64-deferred-2d-lighting)
- [#65 Screen-door alpha](../TECHNIQUES.md#65-screen-door-alpha)
- [#66 Light before sound](../TECHNIQUES.md#66-light-before-sound)
- [#67 Split clocks](../TECHNIQUES.md#67-split-clocks)
- [#68 Landmark-pinned path](../TECHNIQUES.md#68-landmark-pinned-path)
- [#69 Game-time HUD](../TECHNIQUES.md#69-game-time-hud)
- [#70 World-anchored procedural city](../TECHNIQUES.md#70-world-anchored-procedural-city)
- [#71 Puddle sky and drying trail](../TECHNIQUES.md#71-puddle-sky-and-drying-trail)

Re-derived, not new: the [three-mode piece](../TECHNIQUES.md#19-three-mode-piece),
the [pure function of time](../TECHNIQUES.md#30-pure-function-of-time), the
[signature card](../TECHNIQUES.md#16-signature-card) (here as the game would
do it), the [deterministic render harness](../TECHNIQUES.md#21-deterministic-render-harness),
and the [AAC true-peak guard](../TECHNIQUES.md#18-aac-true-peak-guard), checked
on every delivered file.
