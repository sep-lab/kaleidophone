# Case study: the reference project

This is the project kaleidophone was extracted from — the first proof that the
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
kaleidophone project brief's own language ("fm/am minimal vibe") is a direct
descendant of this concept, generalized past one song.

## Asset curation

~400 photos, shot by the artist over time, reviewed down to a smaller set of
selects and sorted into four "stations" — this is the direct ancestor of
`assets/stations.py`'s presets:

| Station (original) | kaleidophone preset | Look | Used for |
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
`kaleidophone run`'s `cover.jpg`, `master.mp4`, `teasers/`, `thumb_*.jpg`,
`promo_pack.md`, and `wavemap.png`. The promo plan used a staged teaser
cadence (roughly T-7 / T-3 / T-1 before release) and chapter markers at each
structural beat — the direct ancestor of `OutputConfig.teasers` and
`promo/plan.py`'s chapters section.

## What this framework doesn't yet reproduce

This edit was hand-directed by a person, start to finish — the station
choices, the exact switch timing, the strobe-archive texture, are all
specific creative decisions, not something `kaleidophone auto` would currently
arrive at on its own (see
[ADR-0004](../decisions/0004-default-mode-and-auto-curation.md)'s honest
caveat on auto-mode's limits). `examples/love/brief.yaml` reconstructs this
project's *structure* as a runnable brief — real timestamps, real station
design — so it's a genuine worked example of hand-authoring at this level of
detail, not a claim that the automated defaults would produce the same
result unassisted.

## Iteration 2: the polish pass (what a real second round looks like)

The artist came back after living with the first full render: the mix got a
new master, and the notes were "more hypnotic, more synced to the waves,
more story — and the on-screen data looks cheesy." That round produced
three lessons this framework should carry.

**1. A new master can silently invalidate `remux`.** The replacement master
was +4.7s longer and its structural landmarks moved — the switch landed
~5s earlier on the clock (3:28.3 → 3:23.4). The cheap `mux_audio` path
assumes the timing still matches; here it didn't, and a stream-copy remux
would have desynced every cut after the first section without raising any
error. The fix was re-running analysis on the new audio and re-rendering
(the re-render also re-derived section boundaries from the new analysis —
the first station change moved from 1:01 to 0:46.8). The generalizable
feature is tracked in `docs/ROADMAP.md` Phase 2: re-detect landmarks on
replacement audio and warn loudly (or refuse without a force flag) when
they drift beyond a cut's tolerance.

**2. Data overlays read as kitsch; diegetic overlays don't.** The first
render carried the radio concept as literal UI — station labels, a tuning
dial, timers, frame counters. The artist's reaction was immediate
("cheesy"). The replacement kept the concept but made it diegetic: a live
oscilloscope of the actual waveform, a thin line whose color and amplitude
follow the section — warm and small in the quiet half, gold in the hush,
red in the loud half, flatlining as the song dies. Same signal, no text.
The distilled rule now lives in `docs/CREATIVE-GUIDE.md` ("Learned in the
field").

**3. Three effects earned a place in the vocabulary** (candidates — not
yet in `render/effects.py`; tracked in `docs/ROADMAP.md` Phase 2):

- `scope_overlay` — the oscilloscope above; per-section color/amplitude.
- `feedback_echo` — blend a slightly-zoomed copy of the previous *output*
  frame into the current one (analog video feedback). Cuts become morphs;
  at higher strength this was the single cheapest "hypnosis" dial the
  project found. Strength varied per section: strong in the quiet half and
  the descent, low during strobe sections so hits stay sharp.
- `punch_zoom` — a decaying zoom kick (scale += a·e^(−k·Δt)) triggered on
  every beat in quiet sections and on strong onsets in loud ones. This is
  what "react to the waves" turned out to mean in practice.

Also proven again from the story side: a recurring hero object — the same
image opening the film, flashing inverted for a single beat right before
the switch, and closing the film — gives an abstract edit a narrative
spine for nearly zero render cost, as does bringing Part I's subjects back
as brief inverted "ghosts" on Part II's strongest hits.

**Measured on this project** (660s, 1280×720@24fps, x264 `veryfast`; real
project, not `examples/demo/`): per-frame gaussian grain at σ≈0.05 is
nearly incompressible — CRF 24 produced a ~2.0GB file, and a re-encode
with temporal denoise (`hqdn3d=3:2:9:6`) at CRF 30 brought it to ~225MB
with the grain texture intact. The second-iteration render applied denoise
in-loop (per chunk, CRF 28) and concatenated to ~754MB; a final CRF 30
pass landed at ~512MB — the feedback-echo trails and the moving scope
line roughly double the achievable file size versus the first render's
harder cuts. Grain belongs at the end of the chain, and temporal denoise
before x264 is what makes it affordable.

