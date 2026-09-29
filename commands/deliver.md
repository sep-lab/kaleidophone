---
description: Cut the whole release from one silent render — full film, reel, stories, covers, captions — with the audio muxed and measured where the master lives.
argument-hint: "[silent render] [master WAV]"
---

# Deliver the release

One silent render, keyframed at every planned cut, becomes every deliverable:
stream-copied slices with the master muxed under each, measured on the files
themselves. Arguments: `$ARGUMENTS` (the silent render and the master; if
there is no render yet, this is where its cut points get planned). Read
`skills/kaleidophone-release-kit/SKILL.md` for the why behind each step;
`#N` is a technique in `docs/TECHNIQUES.md`.

## 1. The matrix, in bars

Agree the deliverables with the artist and write each one as a window on the
grid: the full film; the reel (the song pack's `loudest` is a starting point
— does it loop on its own first frame?); stories as whole phrases; covers
and their variants; a carousel; captions. The reel's first frame is its
cover, so it opens on a signature card, not on text over a face (#16).

## 2. The delivery sheet, before anything renders

Write `delivery.yaml` next to the master (`docs/CONFIG-SCHEMA.md`, "The
delivery sheet"). Measure the master and choose the gain mode from what it
is — the mode sets one gain for the whole master, so every cut keeps the
song's own dynamics:

- a 32-bit float pre-master, or over 0 dBTP: `gain: {mode: loudness}`
- a finished, limited master: `gain: {mode: auto}`, which steps the gain
  down until every delivered file is under the ceiling (#18, #50)

The true peak is measured on every delivered file in every mode. The
ceiling (`ceiling_dbtp: auto`) is −1 dBTP, or −2 dBTP for a delivery louder
than −14 LUFS — Spotify's figures; Instagram and TikTok document no
normalisation, so a loud master stays loud there. Every cut gets 5 ms / 15 ms
click-guard fades unless the sheet sets its own; a fade of 0 is checked
against the master and warned about unless that edge is silent. A Spotify
Canvas is its own render and its own sheet, with `audio: none` on the cut.

```
kaleidophone deliver delivery.yaml --dry-run
```

validates the sheet without the render or the WAV, and its header is the
`-force_key_frames` list. No render yet: render it with those keyframes (a
canvas piece: seconds × fps into `render.mjs --keys`). `t0` is on the
render's clock: a render that doesn't start at song time 0 says where it
does with `silent_start` — negative when it starts before the song, as when
`kaleidophone master-check` finds a new master sitting earlier (its `offset`
verdict prints the value to use). A render already exists: `deliver` checks
its keyframes and says which are missing.

## 3. Deliver where the master lives

```
kaleidophone deliver delivery.yaml
```

on the machine that has the WAV. Move the silent render there, never the
master across a slow link, and compare sha256 on both ends of every big
transfer. Where kaleidophone can't run,
`kaleidophone deliver delivery.yaml --dry-run > deliver.sh` is the same
delivery as a POSIX script; run it from the project folder.

## 4. Read the report

First the master: its loudness and true peak, the one gain every cut got,
and the ceiling. Then frames counted against frames expected, duration, LUFS,
true peak, size and the gain (and limiter) used — measured on each delivered
file. `!frames`, `!peak`, a guard that ran out of steps or a `fixed` gain over
the ceiling is a finding: fix it before anything ships. So is a warning about
an unfaded edge that isn't silent.

## 5. Covers, carousel, captions

- Covers and carousel stills come from the piece's own draw code
  (`still.mjs --cover all`), the frame program's stills, or
  `kaleidophone cover` for a brief.
- Captions: the copy pack, `kaleidophone kit <brief>`, then
  `/kaleido:caption`. A canvas or frame-program release needs only a
  copy-only brief (see the skill).

## 6. Hand it over

Every file with its line from the report; what still needs a human — the
captions' voice, a second-language mirror, tags; and what changed since the
last delivery. kaleidophone makes the files and stops there: posting them is
the artist's (`docs/decisions/0006-the-release-pack.md`).
