---
description: Take a finished track all the way to a release — video, cover, and per-platform copy.
argument-hint: "[song file] [media folder]"
model: best
---

# Ship a release

The whole arc, checking in at each expensive step. Arguments: `$ARGUMENTS`.

This is the path for the artist's own photos and clips. With no footage — the
picture drawn in code — start with `/kaleido:piece`; for footage that needs
per-pixel, stateful effects, the `kaleidophone-footage-effects` skill. Either
way the files are cut from one silent render with `/kaleido:deliver`.

Work in the artist's project folder. Never copy their media anywhere.

## 1. The edit

Follow `/kaleido:direct`. Stop at the contact sheet and get a yes before
rendering.

## 2. Deliverables

One brief produces every cut. Use `output.window` rather than writing a second
brief — two briefs drift the moment either is edited.

| Deliverable | How |
|---|---|
| Master | `output.aspect: "16:9"`, no window |
| Reel | `aspect: "9:16"`, `window: [start, end]` on the strongest minute |
| Story | same, 15s, designed to loop |
| Thumbnails | emitted by `run` |

For vertical, set `sections[].framing` per shot. Centre-cropping 16:9 footage is
almost never where the subject is, and the tool cannot guess — look at the
contact sheet and pick `x` per section.

## 3. Cover

`kaleidophone cover brief.yaml`. The deterministic renderer draws from the
song's own energy envelope. If the artist has a photograph in mind, say plainly
that the typographic cover templates are not built yet and offer to design one
by hand instead — do not pretend the procedural cover is that.

## 4. Copy

```
kaleidophone kit brief.yaml -o release_pack.md
```

This generates the *facts*: chapters from the sections, the pinned-comment
timestamp from the strongest energy jump, credits and links from `release`.

**Now do the part it cannot.** Read the pack's "Notes for you" section, then:

- Rewrite the captions in the artist's voice. The generated ones are a scaffold
  and are meant to be replaced. Read anything they have written before — an
  earlier release, their bio — and match it rather than defaulting to
  music-marketing register.
- If `release.secondary_language` is set, the block is deliberately blank.
  Write it as a **mirror**: the same image, said the way it would be said in
  that language. Never translate the English line — a translated caption reads
  translated. If you are not confident in the language, say so and leave it.
- Never invent a credit, a handle, or a collaborator. If it is not in the
  brief, ask.

## 5. Hand it over

List what was produced and what still needs a human: genre and mood tags,
the second-language block if you left it, and anything the notes section
flagged. Do not post anything anywhere — kaleidophone generates files, and
that boundary is deliberate. See `docs/decisions/0006-the-release-pack.md`.
