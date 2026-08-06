# ADR-0005: Project naming

- **Status:** Proposed — open, see "Open question" below
- **Date:** 2026-08-06

## Context

The working name `mvideo` was chosen when the scope looked like "generate a
music video." It no longer fits what the pipeline actually produces: a
music video, cover art, and a promo/captions pack from one brief and one
audio analysis (`cli.py`'s `run`/`auto` commands write all three). A name
that only says "video" undersells the rest, and undersells it specifically
to someone deciding whether to look closer.

## Decision

Not yet made. This ADR exists to hold the shortlist and the reasoning so the
choice is a recorded decision, not a chat message that evaporates — same
reason every other choice in this repo gets an ADR.

## Candidates considered

| Name | Reads as | Note |
|---|---|---|
| **Sideband** | An actual AM/FM engineering term | Directly matches the project brief's "fm/am minimal vibe" and the reference case study's whole AM549/FM108 concept. Sounds like a tool built by someone who knows audio, not a generic "-cast" name. |
| **Wavecast** | wave (audio + the wavemap) + broadcast | Friendly, on-theme, easy to say out loud. Less distinctive than Sideband. |
| **Frequency Stack** | The reference case study's own cover-art name | Poetic, and ties the suite name directly to the flagship case study and to `cover/generate.py`'s literal "stack of the song's own energy" mechanic. Longer; would likely shorten to "fstack" or similar for a package/CLI name. |
| **AM/FM** (`amfm`) | Maximally literal from the project brief's own words | Short, memorable, easy to mistype/confuse as an acronym in prose. |
| **mvideo** (current) | Plain, descriptive, undersells scope | Safe, already the package/import name everywhere in this repo — keeping it costs nothing; changing it costs a rename pass (see below). |

Not shortlisted, and why: **Signal**, **Broadcast**, **Waveform** are all
real words strong enough that they're already crowded (dev tools, other
music software, a messaging app); **Station** collides with this project's
own `StationConfig` vocabulary in a confusing way; anything built from
"Sep" reads as a personal brand name, not a tool other people would install.

## Open question

Which of the above — or another name entirely — actually ships. Renaming
after the fact means one mechanical pass (package directory, `pyproject.toml`,
imports, docs, this ADR's Status line) rather than something to avoid, so
this is genuinely open, not a placeholder for "we're keeping mvideo."

## What would overturn this

Resolves itself the moment a name is picked: flip Status to Accepted, do the
rename pass, and record what was rejected and why (the table above already
does the second part).

## Related

`pyproject.toml`, `docs/ROADMAP.md`.
