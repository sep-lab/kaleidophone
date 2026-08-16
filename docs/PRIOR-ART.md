# Prior art

"A song plus your photos becomes a video" is not a new idea. This document
is an honest look at what already exists, what those tools do that
kaleidophone doesn't, and where the remaining risk to this project's premise
sits. Same template as [Wit](https://github.com/sep-lab/Wit)'s own
`docs/PRIOR-ART.md`.

**How to read the claims here.** Everything below is **cited** (from a
tool's own public documentation or marketing) or **inferred** (a judgement
from its documented feature set). Nothing here is a **measured** side-by-side
benchmark — running one fairly would mean putting the same song and the same
photo library through each tool, and that hasn't been done. Treat this as a
map of the landscape, not a scoreboard. If something here is wrong or out of
date, that's a bug: please open an issue.

---

## The four categories

### 1. Consumer slideshow makers

iMovie, Canva, CapCut, Animoto, Google Photos "Memories", and every
phone-gallery montage feature.

**What they do well:** genuinely zero-friction. Pick photos, pick a song,
get a shareable video in under a minute, on a device you already own, with a
visual editor and no install step. For most people making most montages,
this is the correct tool and kaleidophone is not a serious alternative.

**Where they differ:** the output is a *file*, not a *recipe*. Changing one
decision means going back into a GUI timeline and doing it by hand — and
swapping a draft mix for the mastered one generally means re-exporting the
whole thing. Beat sync, where offered, is usually a fixed "sync to beat"
toggle rather than an addressable structure you can point different
treatments at. There's no equivalent of a `CreativeBrief` you can diff,
version, or hand to someone else.

### 2. Professional NLEs

Premiere Pro, DaVinci Resolve, Final Cut Pro.

**What they do well:** everything, better. Resolve's color tooling alone is
beyond anything in `render/effects.py`, and Premiere has had beat-detection
markers for years.

**Where they differ:** the interaction model. These are hours-long manual
edits by design, and the project file is a proprietary binary that doesn't
diff usefully in git. kaleidophone is not competing on capability here — it's
a different premise: *describe the edit in a small text file, regenerate the
video whenever anything changes.* An NLE is what you graduate to when you
want to place every cut yourself. (Resolve is scriptable via Python, which
narrows this gap considerably for anyone willing to write against its API —
a fair argument that this niche is smaller than it first looks.)

### 3. AI music-video / text-to-video generators

Runway, Pika, Sora, Kaiber, and the "turn your track into a video" services
built on top of them.

**What they do well:** produce imagery that doesn't exist. If you don't have
footage, or want something impossible to shoot, this is the only category
that can help.

**Where they differ:** it's not your material. The reference case study this
framework was extracted from is 400+ photos the artist actually shot, and
the entire point was that it's a real record of a real time — a
plausible-looking substitute would have defeated the purpose. Generation is
also expensive and slow per frame at multi-minute lengths, and typically
non-deterministic, which is incompatible with the cheap-resync workflow in
[ADR-0001](decisions/0001-version-the-brief-not-the-render.md). See
[ADR-0002](decisions/0002-deterministic-edit-engine.md) for the full
argument, including what evidence would overturn it.

### 4. Programmatic / code-driven video

MoviePy, Remotion, FFmpeg scripts people write by hand, Blender's VSE,
`ffmpeg-python`.

**This is the closest neighbourhood, and the honest comparison.**

- **MoviePy** — a Python video library. More general than kaleidophone, and
  the obvious thing to build this on. kaleidophone deliberately doesn't
  (see [ADR-0002](decisions/0002-deterministic-edit-engine.md)): it shells
  out to the `ffmpeg` binary instead. That's a real tradeoff — a Python API
  is nicer to compose against than argv strings.
- **Remotion** — React components as video frames, with a genuinely
  excellent preview story. Closest in spirit to "the video is derived from
  source you version." Different ecosystem (Node/React), and aimed more at
  programmatic/data-driven video than at cutting a photo library to a song.
- **Hand-rolled ffmpeg scripts** — what most people in this space actually
  do, and what kaleidophone effectively is a structured version of. The
  honest framing: this project is one person's ffmpeg pipeline, given a
  schema, a beat-aware timeline model, and privacy guardrails.

---

## What kaleidophone actually claims to add

Narrowly, and only against category 4:

1. **A versionable brief as the single source of truth**, with everything
   else — EDL, video, teasers, thumbnails, cover art, promo pack — derived
   and rebuildable ([ADR-0001](decisions/0001-version-the-brief-not-the-render.md)).
2. **An explicit cheap/expensive split.** Approving the edit and re-syncing
   audio are different operations, and the second doesn't re-run the first.
   This exists because the workflow it serves (draft mp3 → approve edit →
   mastered wave) is the actual working pattern it was extracted from.
3. **Frame-accurate beat sync that is tested rather than asserted** — see
   `docs/ARCHITECTURE.md`, "Frame-accurate cuts", including the drift this
   project shipped with before it was measured.
4. **Cover art and a promo pack from the same audio analysis**, so one
   analysis pass feeds three outputs.
5. **Privacy as an enforced property, not a policy.** No real media or
   personal path can enter the repo; CI refuses it
   ([ADR-0003](decisions/0003-public-framework-private-assets.md)).

## Risks to this project's premise that remain unanswered

Stated plainly, because a prior-art doc that only flatters its own project
is worthless:

- **The niche may be genuinely small.** "Wants a beat-synced video from
  their own photos, is comfortable in a terminal, and wants it reproducible"
  is a narrow intersection. Categories 1 and 2 cover most people.
- **Proven on one project.** Everything here generalizes from a single case
  study. A second independent one is the highest-value contribution on the
  roadmap for exactly this reason.
- **Resolve's Python API is a real alternative** for the scripting-inclined,
  with vastly better rendering behind it.
- **The aesthetic is opinionated by default.** Vintage/grainy/loopish is the
  starting point, not a preset. That's deliberate
  ([docs/CREATIVE-GUIDE.md](CREATIVE-GUIDE.md)) and it will be wrong for
  plenty of songs.
- **No GUI, ever** — a documented boundary
  ([ROADMAP.md](ROADMAP.md), "Explicitly not planned"), and a real ceiling
  on who this can serve.
