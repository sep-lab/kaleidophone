# ADR-0006: The release pack — one brief, the whole release

- **Status:** Accepted
- **Date:** 2026-08-19
- **Supersedes:** the scope boundary stated in `AGENTS.md`, "not a
  hosting/publishing platform" — narrowed rather than removed, see below.

## Context

kaleidophone was scoped as a video engine: a song plus photos becomes a
beat-synced, station-graded video, and `AGENTS.md` said plainly that the
project "produces files; what you do with them is yours."

That boundary was drawn to keep a rendering tool from drifting into being a
social-media product, which remains the right instinct. But it drew the line
in the wrong place, and running the pipeline against real projects made that
obvious.

The evidence: across the projects this framework generalises from, the video
was rarely the expensive part. The expensive part was everything downstream of
it — five cover concepts per release, a bilingual caption document written from
scratch each time, a chapter list transcribed by hand into three separate
places (the render script, the README, the YouTube description), a timed-comment
plan, and a posting order reconstructed from memory at 2am. Two of those
projects produced near-identical caption documents four days apart, written
independently, because there was nothing to reuse.

Every fact in those documents already exists in the brief and the audio
analysis. Chapters *are* `sections[]`. The pinned-comment timestamp *is* the
strongest detected energy jump. The mood words *are* the station descriptions.
Regenerating them by hand, per release, is exactly the kind of derived work
[ADR-0001](0001-version-the-brief-not-the-render.md) exists to eliminate — it
is the same argument as "don't hand-edit the rendered MP4", applied one step
further out.

`docs/PRIOR-ART.md` also names the honest risk to this project: "wants a
beat-synced video from their own photos, is comfortable in a terminal, and
wants it reproducible" is a narrow intersection. Owning the release rather than
just the render widens the job to one far more people actually have.

## Decision

**The `CreativeBrief` gains a `release` block, and kaleidophone generates the
release copy pack from it. kaleidophone still never posts anything.**

The line moves from *"we stop at the video"* to *"we stop at the file"*, and
that second line is enforced by what the code is allowed to contain:

1. **No network calls to any platform.** No API clients, no OAuth, no tokens,
   no scheduling, no "connect your account". A dependency that talks to a
   social platform is out of scope by construction, not by convention.
2. **Output is markdown a person reads, edits, and pastes.** Not a queued post.
3. **The facts are derived; the voice is not.** The pack is templated from
   structured data — chapters, timestamps, credits, mood words — and says so
   at the top. It ships a "Notes for you (not for the caption)" section naming
   everything it could not know, because a pack that produced only
   confident-looking output would be worse than one that flags its gaps.
4. **`release.concept` is the artist's line, and nothing invents it.** An
   energy envelope does not know what a song is about. If it is unset, the pack
   says every caption is missing its spine.

The optional LLM rewrite that Phase 3 of the roadmap describes is *not* part of
this. The deterministic pack is the scaffold; improving the prose is the job of
an agent reading it, through the Claude Code plugin, with the artist present.
That split is deliberate: the machine that knows the timestamps and the machine
that knows the voice are not the same machine, and pretending otherwise is how
you get captions that everyone can smell.

## Consequences

**Good**

- One source of truth for the release, not four hand-synced copies of the
  chapter list.
- Every timestamp in the copy is derived, so it cannot drift from the edit.
  Change a section boundary and the chapters follow.
- The gaps are explicit. A generated pack tells you what it does not know
  instead of quietly guessing.
- Bilingual releases stop being a per-project rewrite: the structure is
  generated, the second language is left blank *on purpose*, with a note that
  it should be mirrored rather than translated.

**Bad, and accepted**

- The schema grows. `release` is the fifth top-level block, and
  `CreativeBrief` is meant to stay a file a person can read in one sitting.
  Mitigated by `release` being wholly optional — a brief that omits it still
  renders and still gets a pack, with the notes section explaining what is
  thin.
- Copy templates carry taste, and taste dates. The posting-order advice and
  the story placement notes are opinions about platforms that will change.
  They live in one module and are meant to be edited.
- It invites the next request, which is scheduling and posting. The answer is
  no, and rule 1 above is what makes that answer checkable rather than a
  matter of will.

## What would overturn this

- **Nobody edits the generated pack.** If real use shows people pasting it
  unchanged, the "scaffold, not copy" framing has failed and the honest move is
  either to make it genuinely good writing or to cut it back to chapters and
  timestamps.
- **Platform conventions churn faster than the repo.** If the per-platform
  blocks are wrong more often than right, they should collapse to one generic
  block plus a spec table.
- **The no-posting line stops being tenable** — for instance if a platform
  makes pasted metadata materially worse than API-submitted metadata. That
  would be a real argument, and it would deserve its own ADR rather than a
  quiet dependency.

## Update, 2026-10-01

0.4 adds one opt-in exception to "improving the prose is the job of an agent":
`kaleidophone kit … --llm ollama:<model>` asks a model running on the artist's
own machine for caption drafts (`src/kaleidophone/release/local_llm.py`). The
case for it is the one this ADR didn't consider — no tokens, or no network,
on release day — and it keeps all four rules:

1. It talks to a model server (`127.0.0.1` unless `--llm-host` names another,
   which it says on stderr), never to a platform, through the standard library
   — no client dependency, no proxy, no credentials.
2. The output is still markdown: the drafts go under their own heading, after
   the posting order, labelled as drafts.
3. The facts stay derived. The model is asked for a voice and nothing else;
   the chapters, timestamps and credits are the tool's own, and a draft that
   breaks the caption rules is flagged, not quietly fixed.
4. The concept is still the artist's line: the model is given it, or told
   there is none — it isn't asked to find one.

Without `--llm`, the pack is the same, byte for byte. If the drafts turn out to
be pasted unchanged, the first bullet of "What would overturn this" applies to
them first: cut them back before the scaffold.

## Related

- [ADR-0001](0001-version-the-brief-not-the-render.md) — the same "derive it,
  don't maintain it by hand" argument, one step earlier in the pipeline.
- [ADR-0002](0002-deterministic-edit-engine.md) — why the caption is templated
  from facts rather than generated, and where an AI pass legitimately fits.
- [ADR-0003](0003-public-framework-private-assets.md) — `release.credits` and
  `release.links` name real people and real accounts, so they fall under the
  same never-commit-a-real-brief rule as `media_dir`.
