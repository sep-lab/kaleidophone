---
name: mvideo-asset-curation
description: Sort a folder of photos/clips into mvideo stations, either by hand or with the heuristic auto-sorter. Use when setting up media_dir for a brief's stations, when mvideo auto has visibly mis-sorted a photo library, or when designing new station presets.
---

# mvideo: asset curation

Stations (`StationConfig`) are a *look*; the actual photos/clips that fill
one live in a local folder (`media_dir`) that's never committed — see
`AGENTS.md`. This skill covers getting real media into the right stations.

## Three ways to assign media to stations

1. **Pre-sorted folders (most control).** Put each station's photos in
   their own folder, point `media_dir` at each. `mvideo compose` (via
   `assets/curation.py`'s `scan_media()`) scans each station's folder
   independently — full manual control, zero heuristics involved.

2. **One folder, heuristic auto-sort.**
   ```bash
   mvideo curate /path/to/all/photos brief.yaml -o curation_suggestion.json
   ```
   Scores every image/video's mean hue/saturation/brightness against each
   station's palette (`assets/curation.py`'s `score_for_station()`) and
   assigns each to its best-scoring station. **This is a sort order to
   skim, not a decision to trust blindly** — always eyeball
   `curation_suggestion.json` (or, better, the contact sheet after
   composing — see the `mvideo-render` skill) before rendering.

3. **`mvideo auto` (zero config).** Does the same heuristic sort
   internally, automatically, as part of generating a full brief — see the
   `mvideo-timeline-compose` skill.

## Why the heuristic sometimes gets it visibly wrong

The scorer's target hue for a station comes from its `duotone` highlight
color if one is set, or a coarse warm/cool guess from `temperature`
otherwise (`assets/curation.py`'s `_target_hue()`). **Two stations with
similar temperature and no distinct duotone will compete for the same
photos** — this collapsed an entire station to zero assets during this
project's own testing (see
`docs/decisions/0004-default-mode-and-auto-curation.md`). If curation looks
lopsided:

- Check whether the starved station has a `duotone` set. If not, give it
  one — it's the single strongest lever on curation quality, not just
  visual identity.
- Check whether two stations' `temperature` values are close enough to be
  functionally the same signal to the scorer.
- As a last resort, fall back to pre-sorted folders (option 1) for that
  project — the heuristic is a convenience, not a requirement.

## Designing a new station

Start from a preset in `assets/stations.py` (`preset("amber-room")` etc.)
and change what actually needs to change — see `docs/CREATIVE-GUIDE.md` for
what each parameter reads as. A station needs, at minimum, a `temperature`
and ideally a `duotone` that's genuinely distinct from every other station
in the same brief; everything else (`grain`, `vignette`, `contrast`) is
texture on top of that core identity.
