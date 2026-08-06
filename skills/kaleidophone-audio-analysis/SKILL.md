---
name: kaleidophone-audio-analysis
description: Analyze a song for an kaleidophone project -- BPM, beat grid, and the structural moments ("the hush", "the switch") that sections and effects get built around. Use at the start of any new kaleidophone project, when auto-detected BPM looks wrong, or when deciding where a brief's section boundaries should go.
---

# kaleidophone: audio analysis

`src/kaleidophone/audio/analysis.py`'s `analyze()` is the first step of every
kaleidophone pipeline and the thing every other stage is derived from — see
`docs/ARCHITECTURE.md`. This skill is about using it well, not just calling
it.

## Run it

```bash
kaleidophone analyze /path/to/song.mp3 -o analysis_out/
```

Writes `analysis_out/analysis.json` (BPM, beat/onset times, quiet passages,
energy jumps) and `analysis_out/wavemap.png` (a visual RMS envelope with
those moments marked — open it before doing anything else; it's faster to
read than the JSON).

## What to look for

- **BPM.** `librosa.beat.beat_track` is good but not infallible — octave
  errors (reporting half or double the real tempo) happen, especially on
  songs with a weak or syncopated beat. Sanity-check the reported BPM
  against a tap-tempo guess. If it's wrong, set `song.bpm` explicitly in the
  brief (`SongConfig.bpm`) rather than trying to fix the detector.
- **Quiet passages** (`quiet_passages` in the JSON) — contiguous stretches
  at least 1.5s long, RMS below -35dB by default. These are natural
  candidates for a `static` or slow-cutting section, a station change, or
  the start of a buildup. See `docs/case-studies/love.md`'s "the hush"
  (3:10-3:28) for the worked example this heuristic was built to catch.
- **Energy jumps** (`energy_jumps`) — a frame-to-frame onset-strength spike
  more than 2 standard deviations above the mean. These are candidates for
  a hard section break — a station change, `invert_flash`, `strobe`
  starting immediately. See "the switch" (3:28.3) in the same case study.
- Both thresholds (`quiet_db_threshold`, `jump_z_threshold` in
  `analyze()`'s signature) are tunable per song if the defaults miss
  something obvious in the wave map — don't force a song's real structure
  to fit the defaults.

## Turning this into section boundaries

Two ways, same underlying analysis:

- **By hand:** read the wave map, pick section `start`/`end` times that
  land on the quiet passages and energy jumps you actually want to build
  around, write them into the brief directly.
- **Automatically:** `timeline/autobrief.py`'s `_propose_section_boundaries()`
  does this — uses every quiet-passage/energy-jump timestamp as a candidate
  boundary, falls back to even slicing if there are too few or too many (see
  its docstring, and `docs/decisions/0004-default-mode-and-auto-curation.md`
  for why it doesn't yet do better than that in the "too many" case). Run via
  `kaleidophone auto`, then hand-edit `generated_brief.yaml`'s section boundaries
  if the automatic picks miss something you can see clearly in the wave map.

## What this doesn't do

No genre, mood, or lyric analysis — it's signal-level (loudness, onsets,
beats) only. It also doesn't know "the chorus" from "a loud verse"; that
distinction, if it matters for a project, is a human judgment call applied
on top of what this surfaces, not something to expect the heuristics to
infer.
