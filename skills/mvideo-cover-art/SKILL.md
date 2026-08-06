---
name: mvideo-cover-art
description: Generate procedural cover art for an mvideo project from the song's own audio analysis. Use when finishing a brief's output config, when a cover looks flat or doesn't match the song's energy, or when considering the AI-assisted cover extension point.
---

# mvideo: cover art

`src/mvideo/cover/generate.py` renders a square "frequency stack" cover —
horizontal bands, one per time-slice of the song, sized and colored by that
slice's loudness, in one station's palette — directly from the same
`AudioAnalysis` the video uses. No AI model call; see
`docs/decisions/0002-deterministic-edit-engine.md` for why (and where an
AI-assisted option is planned instead of retrofitted here).

## Run it

```bash
mvideo cover brief.yaml -o cover.jpg
```

Also generated automatically by `mvideo run` / `mvideo auto` as
`cover.jpg` in the output directory.

## Which station drives the cover

`OutputConfig.cover_station` — if unset, `cover/generate.py`'s
`pick_cover_station()` uses the station of whichever section contains the
song's single loudest instant. That's a deliberate, cheap, explainable
proxy for "the station that represents this song," not a claim of taste —
override it explicitly in the brief if a different station (e.g. the one
tied to the song's emotional core rather than its loudest moment) is a
better fit.

## Tuning the look

- `bands` (default 96, `generate_cover()`'s parameter, not currently
  brief-exposed — pass it directly if calling the function rather than the
  CLI) controls how fine-grained the "stack" reads; fewer bands reads more
  like bold stripes, more bands reads more like a smooth gradient.
- The chosen station's `duotone` (if set) directly becomes the cover's
  shadow-to-highlight gradient — a station with no duotone falls back to a
  hue derived from `temperature`, which reads flatter. If a cover looks
  washed out, that station is missing a `duotone` — same lever as in the
  `mvideo-asset-curation` skill.
- `station.grain` and `station.vignette` apply to the cover the same way
  they apply to video cuts from that station — a cover and its video should
  usually feel like the same object because they share these parameters.

## The AI-assisted extension point

Not built yet (`docs/ROADMAP.md`, Phase 3). When it lands, it's a second,
opt-in backend behind the same `generate_cover()` call — a single image is
one generation call, which is a different cost story than per-frame video
generation (see ADR-0002). The deterministic renderer here stays the
default with no API key required either way.
