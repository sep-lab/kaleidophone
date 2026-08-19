# AGENTS.md — instructions for AI coding agents working on kaleidophone

This file is the canonical brief for any AI agent contributing to this
repository. `CLAUDE.md` points here. Read this before changing anything.

## What this project is

kaleidophone turns a song plus your own photos/clips into a beat-synced,
station-graded, loopish music video — plus cover art and a promo/captions
pack from the same brief. It is **a deterministic edit-and-render engine**,
not a generative-video product and not a hosting/publishing platform. If a
task seems to require either of those, stop and ask.

See `skills/` for the full per-stage methodology and `docs/CREATIVE-GUIDE.md`
for the visual/sonic design language this implements.

## The one thing you must not get wrong

**kaleidophone versions the brief, not the render.** The `CreativeBrief` (a YAML
file a person can read and edit) is the source of truth. The EDL, the silent
video, the muxed master, teasers, thumbnails, and cover art are all derived,
rebuildable artifacts — see
[ADR-0001](docs/decisions/0001-version-the-brief-not-the-render.md).

Concretely: if a task involves changing something about a *rendered video*,
the fix belongs in the brief or the code that derives from it, not in a
script that post-processes an MP4. And the render pipeline is deliberately
split into an expensive step (`render_silent`) and a cheap one (`mux_audio`)
so that re-syncing audio never re-runs the expensive one — don't collapse
that split back into one function "for simplicity."

## The second thing you must not get wrong

**No real photo, video, or audio file — anyone's, including test fixtures —
is ever committed to this repository.** `.gitignore` blocks the common
extensions; CI (`check_no_media.sh`, `check_no_personal_paths.py`) refuses
the commit even if `.gitignore` is bypassed locally. See
[ADR-0003](docs/decisions/0003-public-framework-private-assets.md). Test
fixtures are *generated in code* (`examples/demo/generate_fixtures.py`,
`tests/factories/`) for exactly this reason — follow that pattern for any
new fixture, don't add a real file "just this once."

## Rules for claims and numbers

This repository's docs quote real measured numbers (render times, file
sizes, detected BPM accuracy) from `examples/demo/`. If you add or change a
number in `docs/` or an ADR:

- **Never invent a benchmark figure.** Run the command that produced it and
  say what it was measured on (`examples/demo/`'s synthetic fixtures are not
  representative of a real song's beat-tracking accuracy — say so if that's
  what you're citing).
- Label claims **measured**, **cited** (with a source), or **inferred**.
  Don't blur these.
- If a number in this repo turns out wrong, correct it and say so in the PR.
  That's welcome, not embarrassing — see Wit's `AGENTS.md`, which this
  project's whole documentation ethic is borrowed from.

## Rules for handling user data

- **Never commit media.** Not test fixtures, not "a small sample." Generate
  synthetic fixtures instead (see `examples/demo/generate_fixtures.py` for
  the pattern: real WAV/JPG files, entirely procedural content).
- **Never write outside a run's own output directory** without being asked.
  `kaleidophone`'s commands take an explicit `-o/--out`; don't add a code path
  that writes into a user's media folder.
- Briefs and case studies may reference real people (collaborators, artist
  names, social handles). Keep those out of anything committed —
  `docs/case-studies/love.md` documents what was scrubbed from that one and
  why; match that bar for any new case study.

## Code conventions

- The render engine shells out to the system `ffmpeg` binary
  (`render/_ffmpeg_util.py`) rather than depending on a Python video library
  — see [ADR-0002](docs/decisions/0002-deterministic-edit-engine.md). Don't
  add `moviepy` or similar; if ffmpeg genuinely can't do something, that's
  worth a conversation, not a silent extra dependency.
- Effects that are simple single-input/output filters go in
  `render/effects.py`'s `LINEAR_EFFECT_BUILDERS`; effects that split the
  frame into multiple pads (kaleidoscope, halation) go in
  `GRAPH_EFFECT_BUILDERS` and get their own `-filter_complex` pass — see the
  module docstring for why these can't share one code path.
- Prefer extending the `CreativeBrief` schema (`timeline/schema.py`) over
  adding a parallel config mechanism. It's the one file a person authors by
  hand; keep it that way.

## Things that are settled — do not relitigate without new evidence

| Decision | Where |
|---|---|
| Version the brief, not the render | ADR-0001 |
| Deterministic edit engine, not AI-generated video/frames | ADR-0002 |
| Public framework, private assets, CI-enforced | ADR-0003 |
| Default mode (`kaleidophone auto`) writes a normal editable brief, not a black box | ADR-0004 |
| The project is named `kaleidophone`, lowercase throughout | ADR-0005 |
| The release pack is in scope; posting to a platform is not | ADR-0006 |

Each ADR lists what evidence would overturn it. Bring that evidence, or
leave them alone.

## Testing

`tests/` holds unit tests for the pure-logic pieces (schema validation, EDL
composition, auto-sectioning, curation scoring) using synthetic in-code
fixtures (`tests/factories/`) — never real media, per the rule above.
Run with `python3 -m pytest tests/ -q`.

`examples/demo/run_demo.sh` is the closest thing to an integration test:
generates fully synthetic fixtures and runs the real CLI (`analyze` through
`run`) end to end. If you change the render pipeline, run it — it's the
only thing in this repo that actually calls `ffmpeg`.

## When to stop and ask

- The task would commit or require real media (photos/audio/video) to this
  repository.
- The task pushes scope toward **posting**: an account system, an OAuth
  flow, a scheduler, or any API client for a social/streaming platform.
  kaleidophone generates release *files* — captions, packs, deliverables — and
  stops there. See [ADR-0006](docs/decisions/0006-the-release-pack.md); the
  no-network rule is what makes that boundary checkable rather than a matter
  of restraint.
- You're about to make a claim in docs you haven't actually measured.
- The task wants AI-generated video frames or cover art added to the
  *default* path rather than as an opt-in extension — see ADR-0002's "What
  would overturn this".
