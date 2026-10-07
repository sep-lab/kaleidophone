---
description: Make a canvas piece for this song — no footage, the picture drawn by code — from the concept to QA stills, a keyframed silent render and covers.
argument-hint: "[song file] [piece id]"
model: best
---

# Make a canvas piece

The artist has a song and no footage, or wants the picture drawn. You are
directing one self-contained HTML file that plays live, renders its own film
and draws its own covers, all from the song's envelope. Arguments:
`$ARGUMENTS` (a song file, and optionally a piece id; ask for the song if it's
missing). Read `skills/kaleidophone-canvas-piece/SKILL.md` first — this is
its short form; `#N` is a technique in `docs/TECHNIQUES.md`.

Work from `canvas/`. Everything derived from the song — the song pack,
renders, stills, a build with the real pack — goes in `private/`, which git
ignores.

## 1. Listen: count the grid

```
kaleidophone envelope <song> -o private/songpack.json
```

Say what you found in musical terms before proposing anything: the tempo,
where bar 1 is, the drop, the loudest minute, how many bars each passage
runs, what repeats. Then count — snares from the drop to the hook, bars per
scene (#47). A grid at double or half time: re-run with `--bpm-range`. A kick
on every beat: confirm bar 1 by ear.

## 2. Ask, at most three things

- What is the song about, in one line? The concept is built from it; never
  invent it.
- Is there a moment the piece should be built around?
- Where is it going: a full film, a reel, stories, all of them?

## 3. Propose a rule, not a storyboard

One rendering rule the whole film obeys — "she is never drawn", "everything
through his viewfinder", "one page torn in two" — two to four rules that hang
off it, and a scene timeline in bars: what happens at the drop, how it ends.
Make the calls and say you made them. **Wait for a yes.**

## 4. Build it from the template

```
cp -r pieces/template pieces/<id>      # then the title, and the grid in src/main.js and piece.json
node tools/build.mjs <id> --song private/songpack.json
node tools/still.mjs <id> --song private/songpack.json --t <scene starts, the drop, the end> --qa --out private/stills
```

A pure function of time (#30), one draw function for live, render and cover
(#19), the lib before anything new. Show the artist the stills — every scene
start, the drop, the card, the ending, with every contact passing (#35) — and
**wait for a yes before the long render.**

## 5. Plan the cuts, render once, draw the covers

Write the delivery sheet first (`/kaleidophone:deliver`): the header of
`kaleidophone deliver <sheet> --dry-run` lists every keyframe the render
needs, in seconds; `--keys` takes them as frame numbers (seconds × fps).

```
node tools/render.mjs <id> --song private/songpack.json --t0 0 --dur <length> --keys <frames> --workers 2 --out private/full_silent.mp4
node tools/still.mjs <id> --song private/songpack.json --cover all --size 3000 --out private/covers
```

Silent, from song time 0. The audio goes on where the master lives, in
`/kaleidophone:deliver`.

## 6. Hand it over

The live piece (`dist/<id>.html`: open it, drop the track on it), the silent
film, the covers, the QA stills, and what's next — the kit and the captions.
If the piece is going into the repository, give it a synthetic twin
(`node tools/synth.mjs --twin …`, see the skill), and commit nothing derived
from the audio or the words: no song pack, stem, lyric, render or still.
