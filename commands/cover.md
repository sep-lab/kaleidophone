---
description: Generate cover art from a brief, and be honest about what the generator can and cannot do.
argument-hint: "[brief.yaml]"
---

# Cover art

```
kaleidophone cover $ARGUMENTS -o cover.jpg
```

Draws a "frequency stack" from the song's own energy envelope, in the palette
of whichever station holds the loudest moment (or `output.cover_station`).
Tunable via `output.cover_size`, and via the station's `duotone`, `grain` and
`vignette`.

## Be straight about the limits

This is a procedural, abstract cover. It is genuinely derived from the song,
and it is **not** a designed, typographic, photograph-based cover.

If the artist wants type on a photograph, a duotone screen-print, a negative,
or anything with a concept behind it — say that the cover templates for those
are on the roadmap and not built
(<https://github.com/sep-lab/kaleidophone/issues/21>), and offer to design one
by hand with Pillow instead. Do not describe the procedural output as though it
were the thing they asked for.

If you do design one by hand, use `src/kaleidophone/overlay/typography.py` —
the bundled fonts, the tracked-text helper, and the shadow are already there,
and Persian and Arabic shape correctly through it.

## Sizes

3000×3000 is the distribution master. Every other size a platform asks for --
Spotify, Apple, your distributor, SoundCloud and its header, the YouTube thumbnails,
the Instagram Reel cover and what the profile grid shows of it -- comes from
it through the delivery sheet's `covers` (`docs/CONFIG-SCHEMA.md`, "Covers";
the sizes are in `docs/PLATFORMS.md`): never enlarged, sRGB with no embedded
profile, each under its platform's file limit.
