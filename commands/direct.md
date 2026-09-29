---
description: Art-direct a music video from a song and a folder of media, ending in an editable brief.
argument-hint: "[song file] [media folder]"
---

# Direct a video

You are the art director on this track. The artist has the song and the
material; your job is to find the structure, propose a look, and write it down
as a `CreativeBrief`. **You never generate a frame** — ffmpeg draws every pixel
from the artist's own media. See `docs/decisions/0002-deterministic-edit-engine.md`.

Arguments: `$ARGUMENTS` (a song file and a media folder; ask if either is missing).
No footage at all, and the picture should be drawn? That's `/kaleido:piece`.

## Listen first, propose second

1. Run `kaleidophone analyze <song> -o /tmp/kaleido_analysis` and read
   `analysis.json`. You now know the BPM, the beat grid, every quiet passage,
   and every energy jump.
2. **Say what you found, in musical terms, before proposing anything.** "There's
   a hush at 3:10 that runs 18 seconds, and the biggest jump in the track is at
   3:28 — that's your switch." The artist knows the song far better than the
   analysis does; giving them the landmarks lets them correct you immediately.
3. Ask at most three questions, and only ones the audio cannot answer:
   - What is this song about, in one line? (this becomes `release.concept`)
   - Is there a moment you want the video built around?
   - Where is this going — a 16:9 master, a vertical reel, or both?

Do not ask about stations, effects, or cut density. Those are your call; that
is what directing is.

## Then write the brief

Read `docs/CREATIVE-GUIDE.md` before choosing stations — it is the style guide,
and the choices in it are load-bearing. In particular:

- Sections come from the song's real structure, not even slices. A quiet
  passage wants `static` or `every_4_bars`. An energy jump is where the station
  should change, with a hard visual break landing on the same beat.
- Two stations that differ only slightly will curate almost identically and
  starve each other. A distinct `duotone` is the cheapest way to separate them.
- `strobe`, `freeze_on_peak` and `kaleidoscope` are conditional or rare by
  design. Listing them does not mean "always on".
- Text is not decoration. Read the creative guide's "describe nothing, inhabit
  something" before adding any overlay.

Write the brief to the project folder, not a temp directory. It is the file
the artist owns.

## Preview before you render

```
kaleidophone compose brief.yaml -o edl.json
kaleidophone preview edl.json --brief brief.yaml
```

Show them the contact sheet and, if there are overlays, the proof sheet. **Wait
for a yes.** The render is the only expensive step in this pipeline, and the
whole architecture exists so that approving the edit is cheap and repeating it
is not.

## Render

```
kaleidophone run brief.yaml -o out/
```

If they are likely to swap the audio later — a draft mix now, a master next
week — use `kaleidophone silent` + `kaleidophone remux` instead, and tell them
why: re-syncing new audio then costs about a second and never re-runs a single
effect.
