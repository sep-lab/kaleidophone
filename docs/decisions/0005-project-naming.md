# ADR-0005: Project naming

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

The working name `mvideo` was chosen when the scope looked like "generate a
music video." It no longer fit what the pipeline actually produces: a music
video, cover art, and a promo/captions pack from one brief and one audio
analysis (`cli.py`'s `run`/`auto` commands write all three). A name that
only says "video" undersold the rest, and undersold it specifically to
someone deciding whether to look closer.

## Decision

**`kaleidophone`.**

The kaleidophone was an 1827 device built by Charles Wheatstone: a
vibrating rod with a reflective tip, spun so that sound's own vibration
traced a visible pattern. That is, as literally as a single word gets, what
this project does — audio analysis (BPM, beats, quiet passages, energy
jumps) drives what the video does. It is real, it is obscure enough to
carry no baggage, and nothing in software currently uses it (checked
against PyPI directly and a GitHub/web search — see "How we got here"
below). The rename pass this ADR describes is complete: package directory,
`pyproject.toml`, the CLI entry point, imports, and every doc now say
`kaleidophone`, all lowercase throughout, matching how `mvideo` was written
everywhere it appeared (title included) rather than introducing a new
capitalization convention partway through the project's life.

## How we got here

First pass picked **Sideband** as the top recommendation (see the original
table below) on the strength of it being a real AM/FM engineering term that
matched this project's own "two rooms, one frequency" concept. It turned
out to already be in use elsewhere by the time it came back for a final
decision — found out from the person running this project, not from a
search I ran myself, which was the actual problem: I hadn't checked.

Second pass fixed that methodology gap by checking every candidate against
a web search for existing PyPI packages and GitHub repos *before* proposing
it, not after. That search is not a substitute for the authoritative
registries — see "What would overturn this" — but it caught real conflicts
early. Most of the good radio/tape jargon turned out to be spoken for:
**Baseband** and **Heterodyne** are both real Python radio-astronomy
packages, **Lissajous** is published on PyPI, **Duotone** and **Flicker**
are crowded developer-tool names (the latter a real, moderately popular
PyPI package), **Deadband** and **Dead Air** are both real GitHub projects
(one of them is, a little on the nose, *also* a late-night-radio-DJ
concept), **Cathode** is a well-known CRT terminal emulator app, **Skywave**
is a whole satellite-IoT company, and **Warble**, **Aircheck**, **Sidetone**,
**Kinescope**, and **Telecine** are all taken too, some of them directly on
PyPI. Four names survived that pass clean; `kaleidophone` was the strongest
of the four on fit, not just on availability. Before committing, it was
also checked directly against `pypi.org/project/kaleidophone/` (404 — free)
rather than relying on search alone, which is exactly the step that would
have caught Sideband.

## Candidates considered

### First pass

| Name | Reads as | Note |
|---|---|---|
| **Sideband** | An actual AM/FM engineering term | The original top pick. Already taken by the time it came back for a final decision — see "How we got here." |
| **Wavecast** | wave (audio + the wavemap) + broadcast | Friendly, on-theme, easy to say out loud. Less distinctive than Sideband was. |
| **Frequency Stack** | The reference case study's own cover-art name | Poetic, ties the suite name to `cover/generate.py`'s literal "stack of the song's own energy" mechanic. Longer; would likely shorten to "fstack" or similar. |
| **AM/FM** (`amfm`) | Maximally literal from the project brief's own words | Short, memorable, easy to mistype/confuse as an acronym in prose. |
| **mvideo** (original) | Plain, descriptive, undersold scope | Safe, cost nothing to keep — but "video" undersold cover art and promo pack, which is the whole reason this ADR exists. |

Not shortlisted in the first pass, and why: **Signal**, **Broadcast**,
**Waveform** are all real words strong enough that they're already crowded
(dev tools, other music software, a messaging app); **Station** collides
with this project's own `StationConfig` vocabulary in a confusing way;
anything built from "Sep" reads as a personal brand name, not a tool other
people would install.

### Second pass

| Name | Reads as | Note |
|---|---|---|
| **kaleidophone** ✅ | 1827 device that made sound vibrations visible | Accepted — see "Decision" above. |
| Wowflutter | Real tape-engineering term for playback pitch wobble | Strong runner-up — matches the psychedelic/loopish vibe directly, checked clean. More "cute" than "precision tool," and shares vocabulary with two unrelated hobbyist audio-test repos (different purpose, low real confusion risk). |
| Squelch | Radio term for muting a receiver below a signal threshold | Mirrors the project's own quiet-passage/energy-jump detection almost exactly. Shortest and punchiest option; also the most generic as a bare English word, so the least ownable as a brand. |
| Halation | Vintage-film glow around highlights | Already a real effect name in this codebase (`render/effects.py`'s `halation()`) — same self-referential quality Sideband had. One small, unrelated repo (an EXIF-tagging tool) uses the exact name; low but nonzero collision risk. |

Ruled out on collision, grouped rather than one row each since the reason
is the same shape every time — a real, existing PyPI package or GitHub
project already uses the name: **Baseband**, **Heterodyne**, **Lissajous**,
**Duotone**, **Flicker**, **Deadband**, **Dead Air**, **Cathode**,
**Skywave**, **Warble**, **Aircheck**, **Sidetone**, **Kinescope**,
**Telecine**. Full detail on what each collides with is in "How we got
here" above rather than repeated per-row.

## What would overturn this

Very little at this point — the rename is done and nothing has shipped
under the name publicly yet, so the cost of being wrong is still low, but
it would take an actual reason. A confirmed trademark conflict (not just a
same-named side project) found once this goes public would be the one
thing that reopens this ADR; a direct registry check
(`pypi.org/project/kaleidophone/`, a GitHub search, and — before any real
release — an actual USPTO/trademark search, none of which this ADR's
web-search-based methodology is a substitute for) is the recommended gate
before that public release, not just before picking the name.

## Related

`pyproject.toml`, `docs/ROADMAP.md` (Phase 4), `CHANGELOG.md`.
