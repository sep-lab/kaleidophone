# Creative guide

The visual and sonic language kaleidophone implements, distilled from
`docs/case-studies/love.md` into rules general enough to point at a
different song and folder of photos. If `docs/CONFIG-SCHEMA.md` is the
grammar, this is the style guide.

---

## The core bet: structure over polish

The project brief this framework was built from is explicit: *"we don't
wanna keep it high quality, we want it minimal and fast but at the same
time journey."* Read literally, that's a claim about priority order, not
about carelessness — **the song's own structure carries the video; the
video's job is to track it faithfully, not to look expensive.** A cut that
lands exactly on a beat, in the right station's palette, at the right point
in the song's arc, does more work than a technically fancier cut that
doesn't. Everything below follows from taking that seriously.

## Stations: a vocabulary of looks, not a folder of files

A "station" (`StationConfig`) is a *treatment* — temperature, saturation,
contrast, grain, vignette, an optional duotone — deliberately decoupled
from any specific set of photos. The reference case study's four:

| Station | Feel | Used for |
|---|---|---|
| **ROOM** (amber duotone) | warm interiors, instruments, lamplight | the intimate, home-recorded parts of the song |
| **CITY** (noir B&W, crushed + grain + scanlines) | street/documentary energy | verses, motion, the outside world |
| **SUN** (gold, slow) | backlit, golden hour | quiet or held moments — a hush, a breath |
| **FIRE** (boosted native color, light-leak) | hot, saturated, chaotic | the loudest, most physical moment |

`assets/stations.py` ships these as presets (`amber-room`, `noir-crush`,
`gold-hour`, `fire-leak`) precisely so a new project can reuse the *look*
without inheriting the specific photos — see
[ADR-0002](decisions/0002-deterministic-edit-engine.md) on why curation
against these presets is a cheap heuristic, not a vision-model call.

Designing a new station: pick one clear feeling, then set parameters that
actually diverge from the presets already in play — two "warm" stations
that only differ by 0.1 in temperature will curate almost identically (this
is a real bug we hit and fixed; see
[ADR-0004](decisions/0004-default-mode-and-auto-curation.md)). A distinct
duotone is the strongest, cheapest way to make two warm stations separable,
both visually and for the curation heuristic.

## Structure: let the song tell you where the cuts are

`audio/analysis.py` surfaces three things worth building sections around:

- **The beat grid** — `cut_density` (`every_beat` through `every_4_bars`,
  or `static`) sets how often a section cuts, in musical units, not
  seconds. A section that never cuts (`static`) is a real choice for a
  held moment, not a fallback.
- **Quiet passages** (RMS below a threshold for 1.5s+) — a natural home for
  a `static` or `every_4_bars` section, a station change, or the start of a
  buildup. The reference case study's "the hush" (3:10-3:28) is exactly
  this: SUN station, slow, static building toward the switch.
  ([ADR-0004](decisions/0004-default-mode-and-auto-curation.md)'s
  auto-sectioning uses these as candidate boundaries directly.)
- **Energy jumps** (a sharp rise in onset strength) — the moment a section
  should change station entirely, ideally with a hard visual break (a
  strobe, an invert flash, a static-noise burst) landing on the same beat.
  The reference case study's "the switch" (3:28.3) does this: FIRE station,
  strobe on every onset, starting the instant the jump is detected.

A section's `effects` list is where a *moment* becomes visible: `strobe`
and `freeze_on_peak` only actually fire on cuts that contain a detected
onset/energy-jump (see `timeline/compose.py`'s `_effects_for_cut`) — listing
them doesn't mean "always on," it means "on when the song does something."
`kaleidoscope` is deliberately rarer (every 7th cut in the reference
section that uses it) — a texture that reads as *a* moment loses its charge
if every cut has it.

## Effect vocabulary and what it's for

| Effect | Reads as | Best for |
|---|---|---|
| `grain`, `vignette`, `halation` | analog, filmic, a constant texture | almost every section — this is the baseline "vintage" look, not a special occasion |
| `scanlines` | CRT/broadcast, slightly degraded | CITY-style noir sections, archive-footage feelings |
| `zoom_breathe` | slow, alive, non-static | a `static`/held section that shouldn't feel frozen |
| `strobe` | a hit landing | onset-timed accents in a loud section — see above, it's conditional |
| `invert_flash` | a hard break | the exact cut where a station/section changes |
| `freeze_on_peak` | a beat held | the strongest single moment in a section — "hero freezes" |
| `kaleidoscope` | psychedelic, disorienting | rare, structural punctuation, not a texture |
| `duotone` | a station's whole color identity | set on the station, not per-cut |

Text is not in this table. It lives in `overlays` — see
[docs/CONFIG-SCHEMA.md](CONFIG-SCHEMA.md). Cards are for the diegetic
machine fiction described below, for lyric or poem lines, and for credits.
They are not for labelling what the viewer is already hearing.

## Learned in the field: describe nothing, inhabit something

Iteration 2 of the reference case study (`docs/case-studies/love.md`)
removed every on-screen *data* element from the edit — station labels,
timers, dials, frame counters — after the artist called them what they
were: cheesy. The replacement was an oscilloscope of the actual waveform,
its color and amplitude following the section. The rule this distilled to:
an overlay should never be a **readout of data about the song**. A dial
showing a frequency, a counter counting frames, a label naming the section:
these describe the track from outside it, and they read as decoration
because that is what they are.

Two things pass that test, though, not one.

**Overlays driven by the song** — a scope of the actual waveform, a pulse,
a punch-in on the beat. These are the song, drawn.

**Diegetic machine fiction** — a VHS transport readout reading `PLAY ▶` and
later `REW ◀`, a DVD scene-selection menu, a radio dial sweeping `AM 549`
through static to `FM 108.0`, film-edge codes running down the side of a
frame. These are not data about the song, and they are not neutral either:
they assert that the song is playing inside some machine, and that machine
is a character. A DVD menu is a world, not a label.

The distinction that matters is **describing versus inhabiting**. `BPM 129`
describes. `TITLE 01   CHAPTER --` inhabits. The first is a caption on a
song; the second is a fiction the song is happening inside.

A sharper test than the original one: *would this element exist if the song
were playing and nobody had analysed it?* A frame counter would not —
something had to measure the video to draw it. A tape readout would; tapes
have them whether or not anyone is watching.

## Default mode vs. authored briefs

`kaleidophone auto` exists so nobody has to learn this vocabulary before seeing a
result — see
[ADR-0004](decisions/0004-default-mode-and-auto-curation.md). It picks
real, working defaults (a cycling subset of the four presets above, effects
chosen by whether a section is quiet or loud) and writes out the brief it
used. That generated brief is a normal, fully-editable `CreativeBrief` —
reading this guide is what turns "edit the generated brief" into a creative
choice instead of trial and error.

## What this vocabulary is not

It's specific to kaleidophone's actual mechanism: real photos/clips, cut and
graded by ffmpeg. It is not a general "psychedelic video" prompt vocabulary
for a generative model — see
[ADR-0002](decisions/0002-deterministic-edit-engine.md) for why that's a
deliberate boundary, not an oversight.
