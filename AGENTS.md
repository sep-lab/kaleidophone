# AGENTS.md — instructions for AI coding agents working on kaleidophone

This file is the canonical brief for any AI agent contributing to this
repository. `CLAUDE.md` points here. Read this before changing anything.

## What this project is

kaleidophone turns a song into a release — the music video, its vertical
cuts, cover art and a promo/captions pack — either from your own photos and
clips or drawn from nothing but the song. It is **a deterministic
edit-and-render framework with three engines** (ADR-0007):

| Engine | Where | For |
|---|---|---|
| filter graphs | `src/kaleidophone/render/` | footage, cut and graded by ffmpeg (the default) |
| frame programs | `src/kaleidophone/frames/` | footage needing per-pixel, stateful effects (numpy, resumable) |
| canvas pieces | `canvas/` (Node) | no footage: one self-contained HTML file per piece |

It is not a generative-video product and not a hosting/publishing platform.
If a task seems to require either of those, stop and ask.

See `skills/` for the full per-stage methodology, `docs/CREATIVE-GUIDE.md`
for the visual/sonic design language, and **`docs/TECHNIQUES.md` for every
technique the releases taught, numbered, with where it lives** — check it
before inventing something a release already solved.

## Whichever agent you are

This brief is for any coding agent — Claude Code, Codex, Copilot, Cursor, Gemini
CLI (via `.gemini/settings.json`), Jules, Aider. The stage-by-stage skills are in
`skills/` in the open Agent Skills format, linked from `.agents/skills`; the
`commands/` are Claude Code slash commands that only point at those skills, so
elsewhere, follow the skill by name. If the person is out of tokens or offline,
almost everything still runs as plain commands — say which ones
([docs/PORTABILITY.md](docs/PORTABILITY.md)) rather than stopping. The long
creative jobs (a new canvas piece, directing an edit, a whole release, the
review before one) want the strongest model available; README.md, "Which
model", says which.

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

## The third thing you must not get wrong

**All three engines keep one contract** (ADR-0007): the song is analysed once
into a song pack (`kaleidophone envelope`); the picture is a deterministic
function of time and that pack — seeded, never `Math.random()` or an unseeded
generator in a render path; the render is silent and segmented; the audio is
muxed last (`kaleidophone deliver`), and loudness and true peak are measured on
the **delivered** file. Before re-rendering anything for a new master, run
`kaleidophone master-check`.

For `canvas/` specifically:

- **Every shipped piece in `canvas/pieces/` is frozen** — all of them but
  the templates; [canvas/README.md](canvas/README.md) lists them. They are
  kept as they shipped and verified against the delivered films; a change to
  their drawing code makes the release unreproducible. Fix a real bug only
  with a measured before/after, and record it (see how ( - )'s grain seeding
  is documented). New work goes in `canvas/lib/` or a new piece started from
  `canvas/pieces/template`. CI holds each frozen piece to its release: its
  page byte for byte (`canvas/test/contract.test.mjs`) and what it draws
  pixel for pixel (golden frames), and a piece built on the lib pins the
  version it shipped with (`"libVersion"`) —
  [canvas/README.md, "Frozen pieces"](canvas/README.md#frozen-pieces).
- **Prefer a pure function of time.** State carried between frames means
  warm-ups, one worker, and renders that can't be split (TECHNIQUES #30).
- **A real song pack is private**, like the audio it came from: never commit
  one, not even "a small excerpt". `.gitignore` refuses `*songpack*.json`, and
  CI (`check_no_real_songpacks.py`) refuses a tracked pack under any name,
  tagged `songpack/1` or just shaped like one, unless it is marked
  `"synthetic": true`. Pieces in the repository ship a `synthetic.json` twin
  (`node tools/synth.mjs --twin`) instead. It holds the tempo, the first
  downbeat, rounded section levels and peaks, and, for a piece that needs them,
  the timing windows it is choreographed to (SHOULD I ?'s vocal and stutter
  windows, to the millisecond). Nothing else derived from the audio goes in.
  The pack `synth.mjs` makes from a twin plays its own drums, written as MIDI
  (`events.midi`), and, when the twin asks, a chord progression
  (`events.chords`) and stems — all invented for the twin, never the song's
  own notes, harmony or parts.
- **Never commit a render** — clip, still, cover or built HTML. The gallery is
  built by `.github/workflows/pages.yml`.
- **Lyrics, collaborator names and stems never enter the repository**, not in
  code comments either. Real song titles are fine; they're credited.
- Run `cd canvas && npm ci && npm test && node tools/build.mjs --all && node
  tools/golden.mjs --check` before pushing a canvas change; CI also renders one
  second of every piece and compares the frozen pieces' golden frames.

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
- **Private names are checked against a private list.** An unreleased song's
  title, a collaborator, a real place: CI's deny-list job and the pre-push hook
  (`git config core.hooksPath .githooks`) refuse any name on it, printing only
  `file:line` and a hash — [CONTRIBUTING.md](CONTRIBUTING.md#the-deny-list).
  In anything public (issues, PRs, docs), an unreleased song is "the next
  release" and a private folder is described, never named.
- **No `Claude-Session:` trailer** (or any `claude.ai/code/session_` URL) in a
  commit message; CI refuses one in the commits being pushed.

## Code conventions

- The render engine shells out to the system `ffmpeg` binary
  (`render/_ffmpeg_util.py`) rather than depending on a Python video library
  — see [ADR-0002](docs/decisions/0002-deterministic-edit-engine.md). Don't
  add `moviepy` or similar; if ffmpeg genuinely can't do something, that's
  worth a conversation, not a silent extra dependency.
- Frame programs (`kaleidophone.frames`) are for what a filter graph can't
  say; if ffmpeg's filter language can express an effect, it belongs in
  `render/effects.py`. Every stateful effect implements
  `state_dict()`/`load_state_dict()` and resumes bit-identically.
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
| Three engines (filter graphs, frame programs, canvas pieces), one contract; real song packs are private | ADR-0007 |

Each ADR lists what evidence would overturn it. Bring that evidence, or
leave them alone.

## Testing

`tests/` holds unit tests for the pure-logic pieces (schema validation, EDL
composition, auto-sectioning, curation scoring) using synthetic in-code
fixtures (`tests/factories/`) — never real media, per the rule above.
Run with `python3 -m pytest tests/ -q`.

`canvas/` has its own suite: `cd canvas && npm test` (the lib's math, the rig,
the glyphs, the synthetic twins, and that every piece builds into one
self-contained file with no network references and no personal paths).

`examples/demo/run_demo.sh` is the closest thing to an integration test:
generates fully synthetic fixtures and runs the real CLI (`analyze` through
`run`) end to end. If you change the render pipeline, run it — it's the
only thing in this repo that actually calls `ffmpeg`.

## When to stop and ask

- The task would commit or require real media (photos/audio/video), a real
  song pack, lyrics or a render to this repository.
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
