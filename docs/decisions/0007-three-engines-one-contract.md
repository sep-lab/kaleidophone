# ADR-0007: Three engines, one contract

- **Status:** Accepted
- **Date:** 2026-09-29
- **Amends:** [ADR-0002](0002-deterministic-edit-engine.md) (who draws the pixels),
  [ADR-0003](0003-public-framework-private-assets.md) (what a song pack is, and where the gallery lives)

## Context

ADR-0002 said the pixels come from `ffmpeg` filter graphs over your own media,
and the tagline followed: *Claude directs. ffmpeg draws every pixel.* That was
true of the reference project and of the releases that followed it. It stopped
being the whole truth after 0.2.0. Of the seven releases built since, sorted by
what drew their pixels (the seventh, LONELINESS, fitted a track to someone else's
finished film with plain ffmpeg):

- **Two needed per-pixel, stateful effects over footage** that no filter graph
  can say — a canvas that forgets its own footage block by block, photocopies of
  photocopies, a slit-scan ring buffer, one hue surviving a drained grade. Both
  hand-built the same thing: decode frames to numpy, process, encode through
  ffmpeg, in resumable workers (MIKONAMET, AHANGE AROOSI).
- **Four had no source footage at all.** Each was one self-contained HTML
  canvas file that plays live against a dropped track, renders its own film
  frame by frame in headless Chromium, and draws its own covers (HAMECHI MANZOR
  DARE, ( - ), SAME AS YOU, SHOULD I ?). These are the releases the artist now
  makes most.

None of them used a generative model, and none needed to. What they shared,
built independently each time and with no code shared between them, was a
**contract** — the same one the filter-graph engine already follows:

1. The song is analysed once into an **envelope pack**: 100 Hz band energies,
   flux, the beat grid. Every visual reacts to that, never to the audio stream.
2. The picture is a **deterministic function** of time and that pack (seeded,
   never `Math.random()` in the render path), so the same inputs give the same
   frames, and a window renders on its own.
3. The render is **silent**, split into independent segments joined by the
   concat demuxer; the audio is **muxed afterwards**, where the master lives.
4. What is versioned is the **source** — a brief, a frame program, a piece — not
   the render (ADR-0001).

## Decision

**kaleidophone has three engines, chosen by what the picture needs, and one
contract they all keep.**

| Engine | Where | Use it when |
|---|---|---|
| Filter graphs | `src/kaleidophone/render/` | Your photos and clips, cut on the beat and graded — anything ffmpeg's filter language can say. The default. |
| Frame programs | `src/kaleidophone/frames/` | Footage that needs per-pixel, stateful effects. Numpy in the loop; ffmpeg still decodes and encodes; renders are resumable. |
| Canvas pieces | `canvas/` | No footage: the picture is drawn. One self-contained HTML file per piece — live, render and cover modes. |

The contract, concretely: the song pack (`kaleidophone envelope`), the silent
render (`kaleidophone silent`, `kaleidophone.frames.run_job`,
`canvas/tools/render.mjs`), and one delivery step for all three
(`kaleidophone deliver`: cuts from one render, the audio muxed, loudness and
true peak measured on the delivered file).

ADR-0002's boundary does not move: **no pixel is model-generated in any
engine.** The tagline becomes *Claude directs. Deterministic code draws every
pixel.*

For ADR-0003, two clarifications:

- **A real song pack is private**, exactly like the audio it was derived from:
  its envelopes and onsets come from an unreleased master. The repository holds
  only **synthetic twins** — the song's tempo, first downbeat and per-section
  levels and peaks (rounded to 0.05), with every hit and wobble generated
  (`canvas/tools/synth.mjs`); CI refuses any tracked pack not marked synthetic.
  That is enough to run, test and show a piece, and says nothing about the audio.
- **The gallery is built, not committed.** The README shows the pieces through
  clips, posters and covers that CI renders from the synthetic twins on every
  push to `main` and publishes with GitHub Pages (`.github/workflows/pages.yml`).
  The repository still contains no image, video or audio file.

## Consequences

**Good**

- The four canvas pieces and both footage engines are in the repository as
  runnable, tested code instead of living in each release's scratch folder, and
  the next piece starts from `canvas/pieces/template` and `canvas/lib/` instead
  of from a blank file. (Measured: the repository's ports reproduce the delivered
  films — see [canvas/README.md](../../canvas/README.md), "Verified against what
  shipped".)
- One delivery path for everything: the AAC true-peak guard, frame-exact
  stream-copy cuts and the card concat are tested once, not re-typed per release.
- The claim the project makes — that the architecture generalises — is now
  backed by three media, not one.

**Bad, and accepted**

- A second toolchain: the canvas engine needs Node and a Chromium (Playwright's).
  It is isolated in `canvas/` with its own lockfile and CI job; the Python
  package does not depend on it.
- The shipped pieces are kept byte-for-byte as they shipped (comments aside), so
  they don't share the lib's code. That duplication is the price of being able to
  re-render a release exactly; new pieces use the lib.
- Frame programs are slow (~8.7 fps per worker at 1080p on a 4-core ARM VM,
  measured on a real release) — for the passages that need them, not the default.

## What would overturn this

- A piece that needs model-generated pixels to exist at all. That is ADR-0002's
  question, not this one's, and the answer would need its own ADR.
- A fourth medium that doesn't fit the contract (for example, a piece whose
  picture cannot be a function of time and an envelope). Then the contract, not
  just the engine list, needs revisiting.
- If the canvas toolchain's weight in CI or for contributors outgrows its use,
  `canvas/` could move to its own repository — the contract would stay the same.

## Related

[ADR-0001](0001-version-the-brief-not-the-render.md),
[ADR-0002](0002-deterministic-edit-engine.md),
[ADR-0003](0003-public-framework-private-assets.md),
[docs/ARCHITECTURE.md](../ARCHITECTURE.md), "Three engines",
[docs/TECHNIQUES.md](../TECHNIQUES.md), [canvas/README.md](../../canvas/README.md),
[docs/case-studies/](../case-studies/README.md).
