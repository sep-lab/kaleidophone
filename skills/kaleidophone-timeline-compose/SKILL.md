---
name: kaleidophone-timeline-compose
description: Write or generate an kaleidophone CreativeBrief and turn it into an EDL. Use when starting a new kaleidophone project end to end, when authoring or editing a brief.yaml by hand, or when deciding between kaleidophone auto and hand-authoring.
---

# kaleidophone: brief authoring and timeline composition

The `CreativeBrief` (`docs/CONFIG-SCHEMA.md` is the full field reference) is
the one file a person authors by hand and the source of truth for
everything else — see `docs/decisions/0001-version-the-brief-not-the-render.md`.
This skill is about getting a good one, by whichever path fits the project.

## Path A: zero-config default mode

```bash
kaleidophone auto /path/to/song.mp3 /path/to/photos -o out/ --preview-only
```

Generates a complete `CreativeBrief` (`out/generated_brief.yaml`) from audio
analysis and heuristic curation, and a contact-sheet preview
(`out/preview_contact_sheet.jpg`) — no rendering yet. **Always look at the
contact sheet before dropping `--preview-only`** — see the `kaleidophone-render`
skill for what to check.

Good starting point for: a new project, a first look at whether a song/photo
set works at all, or a template to hand-edit from (it's a completely normal
brief once written — see `docs/decisions/0004-default-mode-and-auto-curation.md`).

## Path B: hand-authored

Write the YAML directly (`docs/CONFIG-SCHEMA.md`, or copy
`examples/love/brief.yaml` as a fully-worked structural template). Use this
when:

- The song has a specific structure you can hear but the auto-sectioner
  won't reliably find (see the `kaleidophone-audio-analysis` skill).
- You want station design and section-to-station mapping under full manual
  control (see `docs/CREATIVE-GUIDE.md`).
- You're refining a brief `kaleidophone auto` generated — same file, same schema,
  just edited by hand from here on.

Validate without rendering:

```bash
python3 -c "from kaleidophone.timeline.schema import CreativeBrief; CreativeBrief.from_yaml('brief.yaml')"
```

Raises a clear `ValueError` (bad station reference, `end` before `start`,
etc.) rather than failing silently.

## Composing the EDL

```bash
kaleidophone compose brief.yaml -o edl.json
```

Pure logic, no `ffmpeg` — fast, safe to run repeatedly while iterating on a
brief. `compose()` is deterministic given the same brief, analysis, and
curated assets (each section has its own `seed` — same seed, same shuffle,
same edit every time), which is what makes cheap re-renders possible at all.

**If this fails with "needs media assigned to station X, but no assets were
curated for it"** — a section points at a station whose `media_dir` is
empty, missing, or (if using `kaleidophone curate`'s auto-sort) got zero assets
from the heuristic. This is `compose()` refusing to guess rather than
silently producing a broken edit — fix the station's media, don't work
around the error. See the `kaleidophone-asset-curation` skill.

## Next step

Once you have an EDL you're not immediately rendering, go to the
`kaleidophone-render` skill for the preview-before-you-render workflow.
