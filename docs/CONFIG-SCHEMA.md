# The creative brief: field reference

The full schema lives in `src/kaleidophone/timeline/schema.py` (pydantic — it's
the actual validator, this doc is a guide to it, not a duplicate source of
truth). `examples/love/brief.yaml` and `examples/demo/generate_fixtures.py`
are worked examples.

```yaml
song:
  title: "Song Title"
  artist: "Artist Name"        # optional
  audio_path: "/path/to/song.wav"   # local -- never commit this file, see AGENTS.md
  bpm: 129.0                   # optional -- override if librosa's auto-detect is wrong

stations:
  - name: amber-room           # referenced by name from sections[].station -- must be unique
    description: "Warm interiors, lamplight..."   # prose; also used as caption mood words, see promo/plan.py
    media_dir: "/path/to/photos"     # local folder -- never commit, see AGENTS.md
    temperature: 0.55          # -1 (cool) .. 1 (warm) -- also the curation heuristic's primary signal
    saturation: 1.05           # 0 .. 2
    contrast: 1.05             # 0 .. 2
    grain: 0.18                # 0 .. 1
    vignette: 0.28             # 0 .. 1
    duotone: ["#1a0f06", "#f2b25c"]   # optional [shadow, highlight] -- also sets the curation target hue

sections:
  - name: PENDULUM
    start: 0.0                 # seconds
    end: 61.0
    station: amber-room        # must match a stations[].name
    cut_density: every_2_beats # every_beat | every_2_beats | every_4_beats |
                                # every_bar | every_2_bars | every_4_bars | static
    effects: [grain, vignette] # see docs/CREATIVE-GUIDE.md for what each does
    seed: 0                    # asset-shuffle seed -- same seed, same edit, every re-render

output:
  resolution: [1280, 720]      # see docs/ARCHITECTURE.md, "Why 1280x720 by default"
  fps: 24
  thumbnail_count: 3
  cover_size: 3000              # cover art is square, cover_size x cover_size
  cover_station: null           # optional -- defaults to the station of the section
                                 # containing the song's single loudest instant
  teasers:
    - name: teaser_drop
      duration: 15.0
      aspect: "9:16"             # 9:16 | 1:1 | 16:9
      source_start: 205.0        # optional -- defaults to the middle of the track

promo:                          # optional -- omit to skip promo-pack generation content that needs it
  handles: ["@collaborator1", "@collaborator2"]   # scrub before committing any brief, see AGENTS.md
  teaser_cadence_days: [-7, -3, -1]   # T-7 / T-3 / T-1, relative to release
```

## Validation

- Every `sections[].station` must match a `stations[].name` — `CreativeBrief`
  refuses to construct otherwise (a clear `ValueError`, not a silent
  fallback).
- Every `sections[].end` must be after its `start`.
- `compose()` separately refuses (also loudly) to build an EDL for a section
  whose station received zero curated assets — see
  [ADR-0004](decisions/0004-default-mode-and-auto-curation.md) for why
  that's the right place for this check to live.

## Where a brief comes from

Two paths, same schema:

- **Hand-authored** — write the YAML above directly. Full control.
- **`kaleidophone auto <song> <media_dir>`** — generates one (`generated_brief.yaml`)
  from audio analysis and heuristic curation, no manual authoring. Edit the
  output and re-run with `kaleidophone run` for anything auto-mode didn't get
  right — see
  [ADR-0004](decisions/0004-default-mode-and-auto-curation.md) and
  `docs/CREATIVE-GUIDE.md`, "Default mode vs. authored briefs".

## What never belongs in a committed brief

`audio_path`, `media_dir`, and `promo.handles` are the three fields most
likely to leak something private (a local path with your username in it, or
a real collaborator's handle). `examples/` briefs either point at
`examples/demo/`'s generated fixtures or have those fields genericized —
see [ADR-0003](decisions/0003-public-framework-private-assets.md) and
`docs/case-studies/love.md`'s notes on what was scrubbed from the real one.
