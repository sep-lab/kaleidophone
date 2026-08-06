# ADR-0001: Version the brief, not the render

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

The same question this project's sibling, [Wit](https://github.com/sep-lab/Wit),
asked about DAW projects applies here: what's the *source of truth* — the
finished MP4, or the thing that describes how to produce it?

Treating the rendered video as the source of truth means every tweak —
swap a photo, nudge a cut, try a different color grade, replace the draft
mp3 with the mastered one — means re-editing or re-rendering the whole
thing by hand. That's exactly the workflow this project exists to avoid
(see the project brief: "efficient token", "fast", not "high quality" for
its own sake).

## Decision

**mvideo versions the creative brief (`CreativeBrief`) and treats every
other artifact — the EDL, the silent cut, the muxed master, teasers,
thumbnails, cover art — as a derived, rebuildable build artifact.**

Concretely, the pipeline has an explicit cheap/expensive split:

| Stage | Cost (measured, 24s demo, 28 cuts, 1280x720) | Rebuild trigger |
|---|---|---|
| `analyze` | a few seconds | never — deterministic on the same file |
| `compose` (brief -> EDL) | < 1s, pure logic | edit the brief, re-run |
| `preview` (EDL -> contact sheet) | < 1s, no ffmpeg | after every compose, before rendering |
| `silent` (EDL -> silent video) | **55.4s** | change a cut, effect, or color grade |
| `remux` (silent + audio -> master) | **0.8s** | swap the audio file — draft mp3 -> mastered wave |

That last row is the concrete answer to "we upload an mp3 draft, everyone
confirms the edit, then we want the final wave on it without re-rendering
the video": `mvideo silent` once, `mvideo remux` as many times as the audio
changes. Measured on the bundled synthetic demo (`examples/demo/`, 28 cuts,
24s @ 1280x720): the remux is **~68x** faster than the silent render it
reuses, because it's one ffmpeg stream-copy on the video side, not a
re-run of every cut's effect chain. At 640x360 the same comparison is 17.4s
vs 0.8s (**~22x**) — the gap widens at higher resolution because `remux`'s
cost is dominated by a fixed stream-copy/audio-encode overhead that barely
grows with pixel count, while `silent`'s cost scales with it. Re-measure
with `bash examples/demo/run_demo.sh` plus `time mvideo silent`/`time
mvideo remux` on its output — see CONTRIBUTING.md, "Ground rules for
claims".

## Consequences

**Good**

- Re-syncing audio, regenerating a teaser at a different aspect, or trying a
  new cover-art palette never re-touches the expensive per-cut render.
- The brief is small, diffable, and safe to put in git (see
  [ADR-0003](0003-public-framework-private-assets.md)) — the media it points
  at is not.
- `mvideo auto` can write out the brief it generated
  (`generated_brief.yaml`) as a normal, editable artifact rather than a
  black box: the "recipe" is always inspectable.

**Bad, and accepted**

- Two extra pipeline stages (`silent`, `remux`) beyond the obvious
  brief-in/video-out shape, and two extra concepts a new user has to learn if
  they go looking for them (though `mvideo run` still does the obvious thing
  by default — see [ADR-0004](0004-default-mode-and-auto-curation.md)).
- The silent video is a real intermediate file someone has to manage
  (`render()`'s convenience path deletes it; `mvideo silent` keeps it on
  purpose). It is not free disk space.

## What would overturn this

- If re-rendering the full effect chain turns out to be cheap enough (e.g. a
  future single-pass filter_complex implementation, see ROADMAP.md) that the
  cheap/expensive split stops mattering, the two-stage CLI is unnecessary
  complexity and should collapse back into one `render` step.
- If most real usage turns out to re-edit visuals far more often than audio,
  the audio-swap case this ADR optimizes for isn't the common one, and the
  effort belongs elsewhere (faster full re-renders, not a cheap remux path).

## Related

[ADR-0002](0002-deterministic-edit-engine.md), `src/mvideo/render/ffmpeg_pipeline.py`.
