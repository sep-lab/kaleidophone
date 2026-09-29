---
name: kaleidophone-master-swap
description: Decide what a new or final master costs when the video is already rendered (remux, a new silent_start, re-render some bars, or re-analyse) with kaleidophone master-check, then deliver it with a re-measured AAC guard. Use when a new mix or master arrives for a picture cut to an earlier one, before re-muxing or re-rendering anything.
---

# kaleidophone: a new master for a finished picture

The master will change — a re-limit, a mix note, a new last line — usually
after the picture is done, often the same night. The picture was cut to one
master's grid, and a stream-copy remux onto a master whose grid moved desyncs
every cut after the move without an error anywhere: the reference project's
replacement master moved its switch ~5 s (`docs/case-studies/love.md`). So
check before touching anything (#49). `#N` is a technique in
`docs/TECHNIQUES.md`.

## 0. Has the file finished arriving?

A master that is still being copied grows between two looks, and a partial
file analyses into a confident, wrong answer. Wait until the size stops
changing, then record what you're about to compare:

```bash
ls -l new.wav; sleep 5; ls -l new.wav      # the same size twice
ffprobe -v error -show_entries format=duration:stream=codec_name,sample_fmt,sample_rate,channels -of default=nw=1 new.wav
shasum -a 256 old.wav new.wav
```

Keep the old master. The check compares against the one the picture was cut
to, not whichever one arrived last.

## 1. Check

```bash
kaleidophone master-check old.wav new.wav --bpm 120 --downbeat 0.255 --silent-start 0 --json check.json
```

Give it the grid the picture was cut to — the piece's `makeGrid` and
`piece.json` `grid`, or the brief's tempo and section times — instead of
letting it estimate one from the old master. An estimated downbeat can land a
beat off, and every bar number in the report moves with it; when it estimates,
the report says how sure it is and notes a close tempo-octave call. Give it
the delivery sheet's current `silent_start` too, and, if you know them, the
envelopes the piece reads (`--envelopes voc,mid,rms`). The answer comes in
words and as the exit code:

| Verdict | Exit | Means | Next |
|---|---|---|---|
| remux | 0 | same grid, no bar changed | deliver the new master under the same picture (step 2) |
| offset | 5 | the same material, starting earlier or later | set the printed `silent_start`, then deliver (step 2) |
| rerender | 3 | same grid, some bars changed | redraw those bars, reuse the rest (step 3) |
| new grid | 4 | something moved | find out what (step 4) |

1 and 2 mean the check didn't run (bad usage, an error), which is not a "no".
A delivery script can stop itself on anything but a remux:
`kaleidophone master-check old.wav new.wav --bpm B --downbeat D && kaleidophone deliver delivery.yaml`
— exit 5 stops it too, until the sheet has the new `silent_start`.

How it decides (#49, #52): the local lag from log-envelope cross-correlation
in 8 s windows every 4 s, and one alignment of the whole song (a loop lines up
with itself a bar later; a whole song doesn't), refined to the millisecond.
One shift inside half a frame at 24 fps (`--tolerance-ms`, ~21 ms) is the same
grid; beyond it, it's an offset — unless the new master has new music before
the old one's first note (an insertion: new grid). Lags that grow with time,
or a master that lines up only once stretched a few percent, are a tempo
change. Then, bar by bar, what a piece would read differently: the song-pack
envelopes on the old master's scale, the flux envelopes as rhythm per 16th,
and the share of new sound in the vocal band. SHOULD I ?'s first final master
read 0.00 s everywhere with 0.65–0.95 vocal-band correlation, although the
arrangement after the drop had changed (full-mix 0.2–0.6): a remux, zero
re-render — its choreography followed the voice. Today a changed drum part
flags the bars whose drum envelopes changed; `--envelopes voc,mid` asks only
about the voice.

**Read the notes, not only the verdict.** "Runs x s past the old one's end"
means the new master goes on after the picture stops: those bars are
flagged, and the picture needs extending or the audio a fade. "Vocal moved
+x s" means the beat held but the vocal band — and every cue cut to it —
lines up x s away. "Vocal-band r under 0.65 while the mix holds" means
perhaps a different take; the band is the full mix's (it hears guitars and
keys too), so listen before recutting. "The arrangement changed … around a
steady vocal band" means a piece following the voice still fits.

## 2. remux or offset: deliver it again

Point the delivery sheet's `audio:` at the new master — for an offset, set
its `silent_start` to the value the report printed (the current one plus the
shift; negative when the new master starts earlier, and the head of the
picture then plays over the silence before the song) — and run `kaleidophone
deliver` (`kaleidophone-release-kit`). For a filter-graph film,
`kaleidophone remux silent.mp4 new.wav` swaps the audio too, but it applies
no gain, measures nothing and takes no offset — a hot master needs
`deliver`'s guard (step 5), and an offset needs the sheet.

## 3. rerender: redraw only what changed

The report lists the changed bars as ranges, with their times (mm:ss.ss) and
the envelopes that changed in them — "bars 13-14 (00:36.51-00:42.51): mid,
voc, lowmid changed; new voice 0.15" — and `--json` has every bar's numbers:
each envelope's mean change and shape r, and `new voice` (the share of the
bar where the new master sounds and the old one didn't).

1. **Find out what the new master added.** Listen to those bars. If you need
   the words, run ASR on the changed bars only (#52), and ask the artist
   before anything goes on screen. SHOULD I ?'s last master turned out to add
   a spoken passage over the darkroom and a new last line.
2. **Decide what the picture does there.** It's a creative call, not a
   patch: SHOULD I ?'s new last line became a 37th frame on a 36-frame roll
   (#53), and SAME AS YOU's new breath before the climax became, on the
   artist's idea, the drawing un-drawing itself (#43). Propose, then wait for
   a yes.
3. **Re-render only those windows.** A pure function of time (#30) makes this
   exact: render the changed stretch with `render.mjs --t0 <a keyframe> --dur …`
   (or `--from`/`--to` frames), and join it to the untouched parts at a
   keyframe with the concat demuxer, same encoder settings. SHOULD I ? kept
   0–90 s as it was, because a keyframe had been forced at 90 s, and
   re-rendered only the rest; SAME AS YOU redrew four passages and every other
   frame came out identical.
   - A stateful canvas piece re-renders its window from a warm-up (#21); its
     state won't match across the join, so join at a cut.
   - A frame program re-runs the `RenderJob`s covering those frames; a
     stateful effect starts fresh at a job boundary, so start at a cut.
   - The filter-graph engine has no partial re-render: edit the brief and run
     `kaleidophone silent` again.
4. **Deliver the new picture with the new master**, and re-measure the gain.

The thresholds are starting points, measured only on synthetic masters: tune
them per song (`--max-delta`, default 0.15, an envelope's mean change on the
old master's 0..1 scale; `--min-r`, default 0.75, its shape; `--max-new-voice`,
default 0.10), and narrow `--envelopes` to what the piece reads.

## 4. new grid: find out what moved

The verdict line says how, and it decides the size of the job:

- **"an insertion at the head"** — new music before the old master's first
  note (a new intro bar, a riser), everything after it shifted by the printed
  amount. The picture needs a new opening; after it, the old cut holds at the
  shift. **"a cut at the head"** is the reverse: the old opening's music is
  gone.
- **"the same material N% faster/slower, X BPM"** — a varispeed or a
  time-stretch: a new grid under everything. `kaleidophone envelope new.wav`,
  re-plan the cuts, re-render.
- **"the tempo differs"** — lags that drift steadily: the same, from the
  windows alone.
- **"material moved inside the song"** — nothing before the first moved
  window changed; from there on, the edit needs re-planning.
- **"none of N windows matched confidently"** (or "only N of M") — the grid
  can't be confirmed, so treat it as moved.

Whichever it is, it's a new render: a new song pack, new cut points, new
keyframes. When the grid does hold, the refit is cheap — ( - )'s demo and its
final master shared a grid, the day grew from five scenes to eight and a
coda, and it cost one constants edit and one render.

## 5. Re-measure the AAC guard, every master (#50)

The gain that kept one master under the ceiling is not the next one's answer:
−2.5 dB was enough for two masters, a busier one still delivered −0.2 dBTP at
−2.5 and needed −3.5 dB, and its successor shipped at −3.0. Deliver with
`gain: {mode: auto}` (a float pre-master: `mode: loudness`) and read the true
peak off the report: it is measured on the delivered file, the only one that
ships (#18).

## What this doesn't do

It compares envelopes, not arrangements: it tells you which bars sound
different, never what changed musically — that's listening. It re-renders
nothing, and it never replaces the old master; keep both until the new
delivery is checked.
