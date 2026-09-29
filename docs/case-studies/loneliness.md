# Case study: Loneliness

**Loneliness** · Sep The Concept · August 2026 · an instrumental track
fitted to a collaborator's finished short film

The sixth release in the series, and a different corner of the problem. The
picture already existed and could not be touched: it was a collaborator's
finished short film. So the whole job was fitting the music to it, bar by
bar. Every other release here cuts the picture to the song; this one cuts
the song to the picture.

What it proves for the framework: `bar_fit`
([#3](../TECHNIQUES.md#3-bar-fit)) is a genuinely new mode, an existing film
with a fitted track. It is also where segment-then-concat was arrived at for
a third distinct reason. The first was iteration cost, the second was
memory; this time it was wall-clock limits on the only machine that could
render ([#5](../TECHNIQUES.md#5-on-device-rendering)).

**What's scrubbed and why:** the filmmaker is not named, and neither are any
handles. The film is their work, so its shots are referred to here by their
times and by what the music does there, not by what they show. The reference
artwork the covers answered to isn't named. File hashes are omitted. Numbers
are **measured on the release** unless marked otherwise.

## The rule: the film is untouchable

Not one frame of the cut changed; the only addition was a credit card at the
end. So the music moves and the picture doesn't:

- the track is cut into **two bar-aligned segments**, joined with 10 ms
  fades and no silence between them;
- the track's structural beats land on the film's cuts and on its black
  holes. The fit was agreed in one line: the breakdown carries the black;
- the film's own sound is kept at both ends, where it is noise rather than
  music.

## The fit

**The track:** 226.20 s, 48 kHz / 24-bit, instrumental. 85.00 BPM, verified
with a comb filter, bar 2.823529 s. The drop is bar 0, at 39.215 s into the
track. **The film:** 1920×1080, 25p, 145.87 s, with a temp soundtrack and
the filmmaker's own noise effects at both ends.

| Segment | Track (s) | Placed at film (s) | What lands where |
|---|---|---|---|
| S1 | 0 → 73.097 (the start of bar 12) | 7.343 | the kick and bass enter (bar −8) at 23.97, a second into the shot after the first black · the fill (bar −1) · **the drop at 46.56**, 0.44 s into the shot that starts at 46.12 · groove, bars 0–11 · it ends exactly on the **cut to black at 80.44** |
| S2 | 163.45 (bar 44: the breakdown, hats out) → end | 80.44 | bass only under the film's title card (83.24–86.88) · bar 47 returns at 88.91 ≈ a cut at 89.2 · bar 52 at 103.0 · bar 58 at 119.97 ≈ a cut at 119.68 · **bar 61 at 128.44 = the film's 3.4 s black hole, exactly, and the track's own hat dropout sits there** · the last hit, bar 64, at 136.9 · the track is silent by ~142.5 |

Bars 12–44 of the track (73.1–163.45 s) are skipped. Every anchor is one
line of arithmetic:

```
track time = 39.215 + 2.823529 × bar
film time  = placement + (track time − segment start)
```

**The film's own sound** is kept at ×0.7 for 0–12.0 s: noise and a crackle
hit, faded over 12.0–12.6 s before the temp music starts. It is kept again
from 138.0 s to the end: a noise coda. The temp music is tonal until ~137 s,
so nothing earlier was usable. A ×0.35 tail of it (139.5–145.8 s) runs under
the end card. The master peaks at −0.3 dB, with no clipping.

**The sync map.** Every alignment above went into a small README shipped
with the release: a table of bar → film event, plus how to re-render it.
That README is the part of this release most worth generalizing into
`bar_fit`.

## How it was built: on the machine that holds the files

The film (185 MB) and the WAV (65 MB) couldn't practically move to a cloud
machine that day; the connection ran at 0.1–0.2 MB/s. So everything rendered
where the files were: a local 4-core VM with ffmpeg
([#5](../TECHNIQUES.md#5-on-device-rendering)). **Measured:** 1080p x264 at
preset `fast`, CRF 17, ran at ≈ 1.3× realtime, and the 9:16 cuts the same.
Every command there had to finish in under ~45 s, and background processes
died with the command. So the render was segment-per-command (≤ 26 s of
video each), then the concat demuxer, then the mux. Outputs landed straight
in the project folder. All judging happened on proxies: a 360p film (5.9
MB), a 160k m4a (4.6 MB), and 320×180 check renders (~2 MB).

**9:16 from 16:9, with drift** ([#4](../TECHNIQUES.md#4-crop-drift)). Each
shot gets its own crop center, and some drift inside the shot, all in one
per-frame crop expression before a lanczos upscale:

```
crop=608:1080:x='clip((between(t+S,a,b)*c + …)*1920-304,0,1312)':y=0
```

Two gotchas. Nudge each `between()` end by −0.001 so the boundaries don't
double-count. And `t` restarts at 0 after an input `-ss`, hence `t+S`, where
S is the segment's start. Four shots pan inside the crop: .55 → .36, .22 →
.52, .42 → .32 and .72 → .50 of the width. Black and title segments are
letterboxed instead (scaled to 1080×608 and padded), so the film's title
stays whole.

**The end card** uses the film's own title lettering, lifted from its
title-card frame (84.8 s), plus a two-line credit (film by / music by) in
Space Grotesk. The 9:16 variant adds a pointer to the full film.

**Covers.** Each is a 3-stop gradient map over a lifted luminance:
`curve(lift, gamma)`, because the sources are very dark (median L
0.03–0.10). Grain and paper noise go on top, with a 6 px inset frame. The
artist's name sits top-left and the title bottom-right, both outside the
frame.

## Delivery

| Cut | What it is |
|---|---|
| film, 2:33.04 | the untouched film plus a 7.2 s end card. CRF 17, AAC 320k |
| reel, 60.0 s, 9:16 | film 43.73 → 99.88 plus a 3.85 s card |
| story, 60.0 s, 9:16 | film 83.27 → 143.27, no card |
| covers | nine at 3000² |
| copy | captions (lowercase, deadpan, with Persian lines) and the sync-map README |

## What went wrong

- **`-shortest` trimmed the end card.** With audio shorter than the video,
  `-shortest` cut the video off where the audio ended. The fix: `-af apad`
  plus `-shortest`, so the audio is padded out to the picture.
- **A fit shortens the music; it can't lengthen the film.** The track is
  3:46 and the film is 2:26, so 32 bars of the track are gone. A full-length
  version would need the film extended with holds or slow motion, which
  means touching the picture, and that was never an option here.
- **The link decided the architecture.** Nothing larger than ~5 MB could
  cross the connection that day. Rendering where the files lived, and
  judging on proxies, was the only design that worked. The same move came
  back later: keep the big files still and bring the work to them. MIKONAMET
  did it for the whole render, and all four canvas pieces did it for the
  mux.

## What it contributed

New:

- [#3 Bar fit](../TECHNIQUES.md#3-bar-fit)
- [#4 Crop drift](../TECHNIQUES.md#4-crop-drift)
- [#5 On-device rendering](../TECHNIQUES.md#5-on-device-rendering)

Re-derived, not new: segment-then-concat, this time for a third reason,
wall-clock limits (see the [index](README.md)); bar-snapped structure; and
check renders before the final.
