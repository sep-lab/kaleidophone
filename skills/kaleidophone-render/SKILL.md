---
name: kaleidophone-render
description: Render an kaleidophone EDL to a real video, including the cheap-preview-first workflow and re-syncing audio without a full re-render. Use before running any expensive render, when iterating on effects/color grade, or when a draft mp3 needs to be swapped for a mastered one.
---

# kaleidophone: rendering

Rendering is the expensive stage in the pipeline (see
`docs/ARCHITECTURE.md`) — this skill exists so you pay that cost once per
real decision, not once per tweak.

## Always preview before rendering

```bash
kaleidophone preview edl.json -o contact_sheet.jpg
```

No `ffmpeg` call, under a second even for hundreds of cuts. One thumbnail
per cut, labeled with its section, timestamp, and effects. Check:

- Right photo/clip in the right section (a curation problem — see the
  `kaleidophone-asset-curation` skill, not a render problem).
- Effects landing where expected (`strobe`/`freeze_on_peak` only appear on
  cuts containing a real onset/energy-jump — see
  `docs/CREATIVE-GUIDE.md` — so their absence on most cuts in a section is
  correct, not a bug).
- Enough visual variety within a station — if the same handful of photos
  repeat obviously, that station's `media_dir` may be too small for the
  section's cut density.

`kaleidophone run` and `kaleidophone auto` both generate this automatically and support
`--preview-only` to stop right there.

## Render, the cheap-vs-expensive split

```bash
kaleidophone silent edl.json brief.yaml -o silent.mp4     # expensive: one+ ffmpeg call per cut
kaleidophone remux silent.mp4 song.mp3 -o master.mp4      # cheap: ~20-70x faster, measured (docs/ARCHITECTURE.md)
```

Use this split — not `kaleidophone render`'s all-in-one convenience wrapper —
whenever you expect to touch the audio again after the edit is approved:
a draft mp3 confirmed, then swapped for the mastered wave; a different mix;
a shortened radio edit. `render_silent()`'s output is the expensive part;
`mux_audio()` never re-touches a single effect. See
`docs/decisions/0001-version-the-brief-not-the-render.md`.

If you're rendering once and don't expect to re-sync audio, `kaleidophone render`
(or `kaleidophone run`'s full pipeline) is simpler — it does both steps and
cleans up the intermediate silent file.

## Iterating on look

Color grade and most effects live on the **station** (`temperature`,
`saturation`, `grain`, `vignette`, `duotone` — see `docs/CONFIG-SCHEMA.md`),
not baked into the EDL. Changing a station's grade and re-running `kaleidophone
silent` re-renders every cut using that station — there's no way around
paying the render cost for a grade change, but there's also no need to
touch the compose step; the EDL's cut boundaries don't change.

## If a render fails

`render/effects.py`'s docstring explains the linear-vs-graph-filter split
(most effects join one `-vf` chain; `kaleidoscope`/`halation` need their
own `-filter_complex` pass). An ffmpeg error names the exact command that
failed (see `docs/ARCHITECTURE.md`, "Why segment-then-concat") — it's
almost always one bad filter string from one effect on one cut, not a
systemic problem. Reproduce it standalone by re-running the printed ffmpeg
command directly before assuming the pipeline logic is wrong.
