---
name: kaleidophone-release-kit
description: Cut a release's whole deliverable set (full film, reel, stories, covers, carousel, captions) from one silent render, with a delivery sheet and kaleidophone deliver. Use when a picture is rendered by any engine and the release needs its files, when planning cut points and keyframes before a render, or when writing or debugging a delivery sheet.
---

# kaleidophone: the release kit

A release is one picture and many files. Render the film **once**, silent,
with a keyframe forced at every planned cut. Every deliverable is then a
stream-copied slice of it with its window of the master muxed underneath: no
second encode of the picture, frame-identical to the film (#41). The same
delivery step closes all three engines (ADR-0007), and it runs where the
master lives. `#N` is a technique in `docs/TECHNIQUES.md`.

## The matrix

Agree it with the artist before anything renders — it decides where the
keyframes go.

| Deliverable | Comes from | Get right |
|---|---|---|
| Full film | a cut from 0 to the end | it ends on the song's real ending |
| Reel | a cut; the loudest minute is in the song pack (`loudest`) | its first frame is its cover, so it opens on a signature card, not text over a face (#16). Decide whether it loops (below) |
| Stories | shorter cuts, whole phrases | SAME AS YOU: three 8-bar stories, 16 s each at 120 BPM |
| Spotify Canvas (optional) | its own short render, delivered silent by a sheet of its own (`audio: none` on the cut; that sheet needs no `audio`) | SAME AS YOU's: an 8 s crossfaded loop of a separate state, 608×1080. Check the platform's current spec; the repo doesn't encode it |
| Covers | the piece's own draw code (`still.mjs --cover all`), a frame-program still (a mean face, a slit-scan with the face held), or `kaleidophone cover` for a brief | square and portrait masters, an avatar, variants (#31, #51, #54) |
| Carousel | stills from the same draw code | the frame's own aspect, or a crop band in the cover code (#31) |
| Captions | the copy pack, `kaleidophone kit`, then `/kaleido:caption` | the facts derived, the voice the artist's (ADR-0006) |

**A reel that loops** ends on its own first frame, and the piece has to be
built for it: SAME AS YOU runs its rain and ink clocks on the reel's end clock
before bar 1, and on the delivered reel frame 0 ≡ frame 1733 (#40). Its audio
wants click guards only — `deliver`'s defaults, 5 ms in and 15 ms out: an
unfaded story ended on a −22 dBFS step, a click on every loop. A reel that
doesn't loop wants a real fade-out: ( - ) and MIKONAMET faded 1.5 s.

**The signature card** (#16) is 1.6–2.4 s of title over the resting subject.
Instagram takes a reel's first frame as its cover, so the card is the cover.
Render it as its own short segment and let `deliver` put it in front of the
film, so the full film never carries a mid-film title — SHOULD I ?'s was a
48-frame segment (51–53 s) in front of the film from its keyframe at 53 s.

## Cut points: on the bar, on the frame, on a keyframe

- **Bars first.** A cut that starts on a downbeat starts where the music
  does; windows are `downbeat + k × bar` from the song pack.
- **Frames second.** Every `t0` and `video_from` has to be a whole frame at the
  sheet's `fps`. 26.25 s is frame 630 at 24 fps; 26.26 s isn't a frame, and
  `deliver` refuses it and names the two nearest.
- **Keyframes third.** A stream-copied cut can only start on a keyframe, and
  should end on one: `-frames:v` counts packets in decode order, so a cut that
  ends mid-GOP can come out with its last frame out of order.
- **The render has its own clock.** `t0`, `dur` and `video_from` are on it;
  the audio is read from `silent_start + t0`. A render from song time 0
  needs no `silent_start`. A windowed one (a stateful piece's reel, a brief's
  `output.window`) gives the song time of its first frame, and one that
  starts *before* the song gives a negative `silent_start` and gets a silent
  head. When `kaleidophone master-check` finds a new master is the same
  material sitting earlier or later (its `offset` verdict, exit 5), it prints
  the `silent_start` to use instead of re-rendering — negative when the new
  master sits earlier.

Write the sheet before the render. `--dry-run` needs neither the picture nor
the WAV, and its header is the keyframe list:

```bash
kaleidophone deliver delivery.yaml --dry-run | grep force_key_frames
#   -force_key_frames 0,51,53,114,129,182
```

| Engine | How it gets keyframes at those points |
|---|---|
| Canvas | `render.mjs --keys`, in frame numbers of the render window (seconds × fps from `--t0`): 53 s → 1272 at 24 fps. Record them in `piece.json` `keyframes` |
| Frame programs | start a `RenderJob` at each point: every part is its own encode and opens on a keyframe, and `job_parts()` joins jobs that tile |
| Filter graphs | `kaleidophone silent` doesn't force keyframes. Render each vertical as its own windowed brief (`output.window`, as `/kaleido:release` does), or re-encode the silent render once with the printed list |

`deliver` checks every keyframe with ffprobe before a minute of encoding is
spent, and prints the list to re-render with if one is missing.

## The delivery sheet

Its own YAML file, not a block in the brief: it describes cuts of a finished
silent render, which may not have come from a brief at all. Every field,
default and rule is in `docs/CONFIG-SCHEMA.md`, "The delivery sheet".

```yaml
silent: _work/full_silent.mp4        # the one render -- this one from song time 0 (else silent_start)
audio: Song.wav                      # the master; relative paths resolve against this file's folder
fps: 24
gain: {mode: auto, start_db: -2.5}   # a limited master -- see "Gain"
cuts:
  - {out: SONG_full.mp4,  t0: 0,   dur: 182}
  - {out: SONG_reel.mp4,  t0: 51,  dur: 131, card: _work/card_silent.mp4, video_from: 53}
  - {out: SONG_story.mp4, t0: 114, dur: 15,  fade_out: 1.5}
```

The card segment is a render of its own window, made with the same tool and
settings as the film so the two concatenate without a re-encode — for a
canvas piece, `render.mjs <id> --song … --t0 51 --dur 2 --card --out _work/card_silent.mp4`.
Its frame count must be `(video_from − t0) × fps`, 48 here; `deliver` refuses
one that isn't, because the film would land off its audio.

Then, on the machine that has the master:

```bash
kaleidophone deliver delivery.yaml               # cut, gain, mux, measure
kaleidophone deliver delivery.yaml -o release/   # the same, written somewhere else
```

What it does, each rule paid for on a release (the measurements are in
`src/kaleidophone/render/deliver.py`'s docstring):

- the picture stream-copied and bounded by `-frames:v N`, never `-t`: with
  `-t`, a stream-copy cut kept 2 extra frames even with a keyframe at `t0`;
- `-dn -sn -map_metadata -1 -map_chapters -1`, or a WAV's chapter track rides
  along into the MP4;
- no `-avoid_negative_ts make_zero` on a cut that starts on a keyframe: it
  delayed the audio by the AAC encoder's priming, +21 ms measured;
- seek times exact to the microsecond, floored, never rounded up;
- a card cut is the film's tail from the keyframe at `video_from`,
  stream-concatenated behind the card, then muxed like any other cut;
- one gain for the whole master, measured once, so every cut keeps the
  song's dynamics: gaining each cut's own window to −14 LUFS lifted a sparse
  intro story +10.85 dB while the film got −5.39 (the 0.3.0 review, on a
  synthetic master);
- the true peak measured on every delivered file, in every mode, after the
  limiter too — a window limited to −2.0 dBTP came out of AAC at −0.1;
- the limiter's 4 ms lookahead delay taken back (`latency=1` on ffmpeg 5.1+,
  the same trim by hand before it), or the audio lands 4.0 ms late;
- 5 ms / 15 ms click-guard fades unless the sheet sets its own.

## Gain: measure the master, then pick the mode

```bash
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_fmt -of default=nw=1 Song.wav
ffmpeg -hide_banner -nostats -i Song.wav -af ebur128=peak=true -f null - 2>&1 | tail -n 12
```

| The master | Mode | Why |
|---|---|---|
| 32-bit float (`pcm_f32le`, `flt`) or over 0 dBTP | `loudness`: the master to −14 LUFS, then a 4×-oversampled limiter at −2 dBFS (release 200 ms) | a float pre-master can sit above 0 dBFS — SAME AS YOU's measured +6.05 dBTP, and gain to −14 LUFS still left it at about +2.65 (#42). If a delivered file is still over the ceiling, the guard lowers the limiter, not the gain |
| finished and limited (the last masters peaked at −0.3 dBFS) | `auto` | AAC overshoots a hot master's transients: MIKONAMET's, −0.3 dBFS sample peak, was delivered at +1.7 dBTP (#18). The guard encodes with clean gain, measures every delivered file, and steps the one gain down until all are under the ceiling |
| the same master again, gain known | `fixed` | clean gain, no limiter: a second limiter on a finished master is a second master. Measured all the same: a file over the ceiling is an error |

Whatever the mode, the gain is the master's, not the cut's: one measurement
of the whole master, one gain for every cut, so the stories sit where they
sit in the song. And every delivered file is held to the ceiling.

**The ceiling.** `ceiling_dbtp: auto`, the default, is −1 dBTP, or −2 dBTP
when the delivery is louder than −14 LUFS — which a finished master in `auto`
mode usually is. Spotify normalises to −14 LUFS and asks masters louder than
that for a true peak under −2 dBTP, because loud tracks distort more in lossy
encoding ([Spotify](https://support.spotify.com/us/artists/article/loudness-normalization/)).
Instagram and TikTok document no loudness normalisation (nothing in their
help centres as of September 2026): a loud master stays loud there, and they
transcode it all the same.

The right gain belongs to the master, not the project (#50): against a −1
dBTP ceiling, −2.5 dB was enough for two masters, a busier one still
delivered −0.2 dBTP at −2.5 and needed −3.5, and its successor shipped at
−3.0; a −2 dBTP ceiling will ask for about a dB more (inferred: it is a dB
lower, and clean gain moves a delivered true peak about dB for dB). `auto`
may step up to 6 dB (`max_steps: 12` of 0.5). Start it at the last master's
answer to save encodes; never carry a gain to a new master without
measuring.

## The report

It opens with the master: its loudness and true peak, the gain every cut
got, and the ceiling. With `check: true`, the default, every file is then
measured as written: frames counted (not the header's claim) against the
frames expected, duration, integrated LUFS, true peak, size and the gain (and
limiter) used. `!frames` or `!peak` on a row is a finding; so is a guard that
ran out of steps or a `fixed` gain over the ceiling, which `deliver` reports
as an error after writing the files, and a warning that an unfaded edge isn't
silent. Keep the table with the release notes — it's the record of what
shipped.

## Where things run

- **Render where the cores are; mux where the master lives.** The silent
  render travels to the WAV. The master doesn't travel.
- **Never move a master across a slow link.** Move the silent render, proxies
  and stills, and judge on those.
- **Verify every big transfer**: `shasum -a 256` (or `sha256sum`) on both
  ends. A transfer can arrive corrupt and still decode without a word; only
  the hash says it's the same file.
- **If kaleidophone can't run where the master is**,
  `kaleidophone deliver delivery.yaml --dry-run > deliver.sh` is the whole
  delivery as a POSIX sh script, loudness measurement and the true-peak loop
  included, needing only ffmpeg, ffprobe and a shell there. Run it from the
  project folder; from a relative sheet path it holds no absolute paths.
- **Re-check the master right before the mux** — size, modification time,
  hash. SAME AS YOU's WAV was replaced in place mid-build and the mux used a
  different file from the one analysed; a file still being copied grows
  between two looks (`kaleidophone-master-swap`).

## Captions

`kaleidophone kit` reads a `CreativeBrief`. A canvas or frame-program release
has no edit brief, so write a copy-only one — the song, one placeholder
station, sections named for the song's parts (they become the chapters), and
the `release` block — and run it from the folder the song path is relative to.
Then `/kaleido:caption`. The concept line is the artist's; nothing invents it.

```yaml
song: {title: SONG, artist: Artist, audio_path: Song.wav}
stations: [{name: copy-only}]
sections:
  - {name: intro, start: 0, end: 54, station: copy-only}
  - {name: the drop, start: 54, end: 182, station: copy-only}
release: {concept: "one line, from the artist"}
```

## Hand it over

Every file with its line from the report; what's still the artist's (the
captions' voice, a second-language mirror, tags); what changed since the last
delivery. kaleidophone makes the files and stops there — posting them is the
artist's (ADR-0006).
