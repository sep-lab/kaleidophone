# Case study: the reference project

This is the project mvideo was extracted from — the first proof that the
approach in [ADR-0001](../decisions/0001-version-the-brief-not-the-render.md)
and [ADR-0002](../decisions/0002-deterministic-edit-engine.md) works on a
real song, not just in theory. It's referenced throughout the rest of the
docs as "the reference case study."

**What's scrubbed and why:** real collaborator handles, the specific
artist/label naming, and every local file path have been removed or
genericized. What's kept — the song's actual structure, BPM, timestamps,
station design, and effect choices — isn't personal data; it's the
technique, which is the entire point of writing this up. See
[ADR-0003](../decisions/0003-public-framework-private-assets.md).

## The brief

A ~11-minute two-part track, ~129 BPM. Structurally: a quiet first half, a
hush, a hard switch into a louder second half, and a long descent back out.
The creative concept — **"two rooms, one frequency"** — cast the two halves
as two radio stations: Part I is an AM station (piano, a single voice, an
intimate room), Part II hijacks the signal as an overdriven FM station. The
mvideo project brief's own language ("fm/am minimal vibe") is a direct
descendant of this concept, generalized past one song.

## Asset curation

~400 photos, shot by the artist over time, reviewed down to a smaller set of
selects and sorted into four "stations" — this is the direct ancestor of
`assets/stations.py`'s presets:

| Station (original) | mvideo preset | Look | Used for |
|---|---|---|---|
| ROOM | `amber-room` | warm interiors, instruments, lamplight | Part I's piano sections and the outro |
| CITY | `noir-crush` | B&W, crushed blacks, grain, scanlines | Part I's verse/vocal sections |
| SUN | `gold-hour` | gold, slow | the hush |
| FIRE | `fire-leak` | boosted native color, light-leak | Part II |

Unifying "DNA" across all four: film grain, vignette, subtle scanlines,
halation — this is exactly `StationConfig`'s `grain`/`vignette` fields plus
the `halation` effect, present on nearly every section rather than reserved
for one.

## Structure (real timestamps, the actual edit)

| Time | Section | Station | Notes |
|---|---|---|---|
| 0:00-1:01 | PENDULUM (amber) | amber-room | cuts every 2 beats, slow zoom, kaleidoscope every 7th cut |
| 1:01-3:10 | PENDULUM (noir) | noir-crush | denser cutting toward the peak at 2:00-2:20 |
| 3:10-3:28 | HUSH | gold-hour | slow, static builds in from 3:26, a dial-spin motif |
| 3:28 | THE SWITCH | fire-leak | a hard static flash, then strobe on every onset |
| 5:30-7:30 | STROBE ARCHIVE | fire-leak / noir-crush | archive-footage texture (sprockets, frame counters), invert flashes, held "hero" freezes |
| 7:30-9:48 | DEEP WAVES | fire-leak / noir-crush | alternating 12-cut blocks, a single gold frame on the strongest hits |
| 9:48-end | DESCENT | amber-room | back to the amber room, static rises, fades out |

Every effect name in that table — `kaleidoscope`, `strobe`,
`invert_flash`, `freeze_on_peak`, `static_noise` — is a real entry in
`render/effects.py`'s vocabulary, chosen to match what this edit actually
did, not the other way around.

## What was actually delivered

Cover art, a full video, three vertical (9:16) teasers, three thumbnails, a
captions/promo pack, and a wave-map image — the direct ancestors of
`mvideo run`'s `cover.jpg`, `master.mp4`, `teasers/`, `thumb_*.jpg`,
`promo_pack.md`, and `wavemap.png`. The promo plan used a staged teaser
cadence (roughly T-7 / T-3 / T-1 before release) and chapter markers at each
structural beat — the direct ancestor of `OutputConfig.teasers` and
`promo/plan.py`'s chapters section.

## What this framework doesn't yet reproduce

This edit was hand-directed by a person, start to finish — the station
choices, the exact switch timing, the strobe-archive texture, are all
specific creative decisions, not something `mvideo auto` would currently
arrive at on its own (see
[ADR-0004](../decisions/0004-default-mode-and-auto-curation.md)'s honest
caveat on auto-mode's limits). `examples/love/brief.yaml` reconstructs this
project's *structure* as a runnable brief — real timestamps, real station
design — so it's a genuine worked example of hand-authoring at this level of
detail, not a claim that the automated defaults would produce the same
result unassisted.
