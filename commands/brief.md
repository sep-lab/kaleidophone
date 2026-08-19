---
description: Create or edit a CreativeBrief without the interview — for when you already know the shape.
argument-hint: "[song file] [media folder] or [existing brief.yaml]"
---

# Write a brief

Non-interactive counterpart to `/kaleido:direct`. Use when the artist has
already said what they want, or when editing an existing brief.

Arguments: `$ARGUMENTS`.

## Starting from nothing

```
kaleidophone auto <song> <media_dir> -o out/ --preview-only
```

This writes `out/generated_brief.yaml` — a completely normal, fully editable
brief, not a black box (`docs/decisions/0004-default-mode-and-auto-curation.md`).
Add `--aspect 9:16` for a vertical delivery.

Then edit it. Auto-sectioning falls back to even slicing more often than it
should, so check the section boundaries against the real quiet passages and
energy jumps in `analysis.json` before accepting them.

## Editing an existing brief

`docs/CONFIG-SCHEMA.md` is the field reference. Two things people get wrong:

- **Sections must tile the song end to end.** The renderer concatenates, so a
  gap does not render as a gap — it slides every later cut off the beat. The
  EDL refuses such a timeline rather than rendering it.
- **Overlay `size` is a fraction of frame height, not pixels**, so a card
  survives a resolution change.

## Always validate

```
kaleidophone compose brief.yaml -o /tmp/edl.json
```

Pure logic, no ffmpeg, under a second. It catches every schema and timeline
error before anything expensive happens.
