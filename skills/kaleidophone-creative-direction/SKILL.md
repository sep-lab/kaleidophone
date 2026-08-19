---
name: kaleidophone-creative-direction
description: How to make the creative calls in a kaleidophone project — reading a song's structure, choosing stations, deciding when a moment deserves an effect, and what text is allowed to be. Use when directing a video, designing a station, or deciding whether an overlay earns its place, rather than when running a specific pipeline stage.
---

# kaleidophone: creative direction

The other skills describe *how the stages work*. This one is about the calls
that make an edit good rather than merely correct — the ones a person would
otherwise have to develop taste for over several projects.

The single sentence this all descends from: **the song's structure carries the
video; the video's job is to track it faithfully, not to look expensive.**

## Read the song before you have an opinion

Run `analyze` and look at the wave map *before* proposing anything. You are
looking for three things, and they map directly onto decisions:

| What the analysis found | What it means for the edit |
|---|---|
| A quiet passage (RMS below threshold, 1.5s+) | A held moment. `static` or `every_4_bars`, often a station change, often the start of a build. |
| An energy jump (sharp rise in onset strength) | The song changed rooms. Change station *on that beat*, with a hard break — an invert flash, a static burst. |
| A dense run of onsets | Somewhere `strobe` or `punch_zoom` will actually fire, because both are conditional on real onsets. |

Then say what you found out loud, in musical language, before proposing a
treatment. The artist knows the song incomparably better than the analysis
does; handing them the landmarks lets them correct you in one sentence instead
of after a render.

## Cut density is a musical unit, not a speed

`every_beat` through `every_4_bars` are in *bars and beats*, so an edit stays
locked to the song at any tempo. `static` is a real choice — a section that
never cuts reads as held breath, not as a mistake — and it pairs with
`zoom_breathe` when it needs to stay alive rather than frozen.

The common error is uniform density. A video that cuts every two beats for four
minutes has no dynamics, however good each cut is. Density is how you build
tension: open slow, tighten toward the switch, hold after it.

## Designing a station

A station is a *treatment*, not a folder. Four rules that are all learned the
hard way:

1. **One clear feeling per station.** If you cannot say what it is in three
   words, it is not a station yet.
2. **Make them actually diverge.** Two "warm" stations 0.1 apart in temperature
   will curate almost identically and starve each other of media — this is a
   real bug that shipped once (`ADR-0004`). A distinct `duotone` is the
   cheapest, strongest way to separate them, visually and for the curation
   heuristic.
3. **Write `description` as short evocative prose.** It pays twice: once as
   your own reference, once as the mood words in the release pack.
4. **Grain and vignette are the baseline, not an occasion.** They are on
   almost everywhere. That is the house look.

## Effects: a moment, not a texture

Listing an effect does not mean "always on". `strobe` and `freeze_on_peak` fire
only on cuts containing a real onset or energy jump. `kaleidoscope` fires every
7th cut. This is deliberate: **a texture that reads as *a* moment loses its
charge if every cut has it.**

The judgement call, each time: *is this effect marking something the song
actually does?* If it would look the same over a different track, it is
decoration.

## Text: describe nothing, inhabit something

The rule that took a whole iteration to learn, and the one most likely to be
got wrong.

**Never a readout of data about the song.** A dial showing a frequency, a
counter counting frames, a label naming the section. These describe the track
from outside it and read as decoration, because that is what they are. An
earlier version of the reference project had all of them and they were cut.

**Two things pass, not one:**

- *Driven by the song* — a scope of the actual waveform, a pulse, a punch-in on
  the beat. This is the song, drawn.
- *Diegetic machine fiction* — a tape transport reading `PLAY ▶` and later
  `REW ◀`, a DVD scene-selection menu, a radio dial sweeping AM to FM, film
  edge codes down the side of a frame. These are not data about the song. They
  assert that the song is playing inside some machine, and that machine is a
  character.

The test: *would this element exist if the song were playing and nobody had
analysed it?* A frame counter would not — something had to measure the video to
draw it. A tape readout would; tapes have them whether or not anyone is
watching.

Lyric and poem lines are a third, simpler case: they are the song, literally.
Give them room and a shadow, and let them be legible.

## What you are not for

You direct. You do not generate pixels — every frame is the artist's own
material, cut and graded (`ADR-0002`). And you do not write the concept: one
line about what the record *is* comes from the artist, and every caption is
built around it. An energy envelope does not know what a song is about.

When a creative call is genuinely ambiguous, make it and say you made it.
"I put the switch on the 3:28 jump and went to fire-leak there — tell me if
that's early" is more useful than a question, because it is something to react
to.
