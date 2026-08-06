---
name: kaleidophone-promo-pack
description: Generate chapters, a suggested caption, and a teaser-cadence release plan for an kaleidophone project. Use when preparing a release, writing a YouTube/social description, or planning a teaser schedule.
---

# kaleidophone: promo pack

`src/kaleidophone/promo/plan.py`'s `generate_promo_pack()` turns a brief plus its
audio analysis into a markdown promo pack — chapters, a starting caption,
teaser cadence, collaborators to tag, and a suggested pinned comment. It's
templated from structured facts, not free-form generated text — see
`docs/decisions/0002-deterministic-edit-engine.md`.

## Run it

```bash
kaleidophone promo brief.yaml -o promo_pack.md
```

Also generated automatically by `kaleidophone run` / `kaleidophone auto`.

## What it produces, and where each piece comes from

- **Chapters** — one line per `sections[].name`/`start`, formatted for a
  YouTube Premiere description. Directly from the brief; name your sections
  the way you'd want them to read publicly (or don't — the promo pack is a
  first draft to edit, not the final copy).
- **Suggested caption** — templates the song title/artist with the first
  clause of each station's `description` as mood words
  (`_suggest_caption()`). This is why writing station descriptions as short
  evocative prose (`docs/CREATIVE-GUIDE.md`'s table) pays off twice — once
  for your own reference, once here.
- **Teaser cadence** — from `promo.teaser_cadence_days` (e.g. `[-7, -3,
  -1]` for T-7/T-3/T-1). Pair with `output.teasers` so the cadence and the
  actual rendered clips line up.
- **Suggested pinned comment** — points at the song's single strongest
  detected energy jump (`analysis.energy_jumps`, same signal used for "the
  switch" in `docs/case-studies/love.md`). If the song doesn't have one
  standout moment, this section is simply omitted — it's not forced.

## Before publishing anything from this file

`promo.handles` and anything else naming real collaborators must never be
committed to this repository if you're working from a copy of it — see
`AGENTS.md` and `docs/decisions/0003-public-framework-private-assets.md`.
The generated file itself lives in your own output directory, outside
version control, same as the rendered video.
