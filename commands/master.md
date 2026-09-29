---
description: A new master arrived for a finished video. Check it against the one the picture was cut to — then remux, shift silent_start, re-render the changed bars, or re-plan.
argument-hint: "[old master] [new master]"
---

# A new master arrived

The picture was cut to the old master's grid. Before touching anything, find
out what the new one costs. Arguments: `$ARGUMENTS` (the master the picture
was cut to, then the new one; ask if either is missing — the old one is the
one that matters). Read `skills/kaleidophone-master-swap/SKILL.md`; `#N` is a
technique in `docs/TECHNIQUES.md`.

## 1. Make sure it has finished arriving

A file that is still being copied grows between two looks. Check its size
twice, a few seconds apart, then note its duration, format and sha256. Keep
the old master.

## 2. Check it

```
kaleidophone master-check <old> <new> --bpm <the edit's tempo> --downbeat <bar 1, s> \
    --silent-start <the delivery sheet's silent_start> --json check.json
```

Give it the grid the picture was cut to (the piece's `piece.json` `grid`, or
the brief) rather than an estimate, and the current sheet's `silent_start`
(0 if it has none). If you know which envelopes the piece reads, pass them
(`--envelopes voc,mid,rms`): a change in the others doesn't touch the
picture. Then report the verdict in plain words, with the bars and the
mm:ss.ss times it names, and read the notes too — "past the old one's end"
means the new master goes on after the picture ends, "vocal moved" means the
beat held but the voice (and every cue cut to it) shifted:

- **remux** (exit 0): same grid, nothing changed. Point the delivery sheet at
  the new master and run `/kaleido:deliver` again. A shift inside the
  tolerance (half a frame at 24 fps) is still a remux; the report gives the
  `silent_start` that makes it exact.
- **offset** (exit 5): the same material, starting earlier or later — a
  trimmed or padded head, an MP3's decoder delay, a plugin's latency. Set the
  sheet's `silent_start` to the value the report prints (the current one
  plus the shift; negative when the new master starts earlier), point `audio:`
  at the new master and deliver. Nothing is re-rendered.
- **rerender** (exit 3): same grid, some bars changed. The report names them,
  with their times and which envelopes changed. Listen to those bars, say
  what the new master added, propose what the picture does there, and once
  the artist agrees, re-render only those windows. If the report also gives
  a new `silent_start`, set it as for an offset.
- **new grid** (exit 4): something moved. Say what the diagnosis shows — an
  insertion or a cut at the head, the same material a few percent faster or
  slower, material moved from some point on — then run `kaleidophone
  envelope` on the new master and re-plan the cuts.

## 3. Re-measure the gain

Whatever the verdict, deliver with `gain: {mode: auto}` (a float pre-master:
`mode: loudness`). The gain that kept the last master under the ceiling is
not this one's (#50).

## 4. Say what changed

Exactly what was reused, what was re-rendered and why, and the new report's
numbers. Nothing ships until the artist has seen it.
