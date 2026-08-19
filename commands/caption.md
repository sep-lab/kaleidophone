---
description: Write the release copy — captions, chapters, timed comments — from an existing brief.
argument-hint: "[brief.yaml]"
---

# Release copy

Generate the pack, then do the writing it deliberately leaves undone.

```
kaleidophone kit $ARGUMENTS -o release_pack.md
```

Everything in the generated file is derived from the brief and the audio, so
the numbers are right. The voice is not — that is the job.

## Before you write

- Read the pack's **"Notes for you (not for the caption)"** section first. It
  names every gap: no concept line, no credits, no tags, no links.
- `release.concept` is the spine. If it is unset, ask the artist for one line
  about what the song is — do not invent it. An energy envelope does not know
  what a record is about, and neither do you until they tell you.
- Find their previous releases and match that voice. Register, capitalisation,
  whether they use emoji, how they credit people. A caption that sounds like a
  press release when the artist writes in lowercase fragments is worse than no
  caption.

## Rules

- **Facts stay as generated.** Timestamps, chapters and BPM are derived; do not
  round or re-word them into being wrong.
- **A second-language block is a mirror, not a translation.** Same image, said
  natively. If you are not confident, leave it blank and say so.
- **Never invent a credit or a handle.** Ask.
- Keep the pinned comment pointing at the real detected moment.

## Then

Show the artist a diff-style summary of what you changed and why, and leave the
generated pack alongside your rewrite so they can compare.
