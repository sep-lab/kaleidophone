# Security Policy

## Reporting a vulnerability

Please report security issues privately, **not** as a public issue. Use
GitHub's private vulnerability reporting on this repository (Security ->
Advisories -> Report a vulnerability). Include what the issue is, how to
reproduce it, and what an attacker could achieve.

## Scope

kaleidophone runs `ffmpeg` as a subprocess with filter graphs it constructs from a
`CreativeBrief` and reads/writes files under a run's output directory. The
attack surface that matters:

- **Command / filter-graph injection.** Anything from a brief (station
  names, media paths, effect names) that ends up inside an ffmpeg filter
  string must be validated or escaped, not interpolated blindly. If you find
  a brief field that reaches `subprocess` without going through
  `render/_ffmpeg_util.run()`'s argument-list form (never a shell string),
  that's a bug.
- **Path traversal on output.** Every command takes an explicit
  `-o/--out`; nothing should let a crafted brief write outside the
  directory the user asked for.
- **Untrusted media.** kaleidophone decodes photos/video/audio with Pillow
  and librosa/soundfile, and calls `ffmpeg` on them. A malformed
  file causing a crash or hang in any of those is a real bug — kaleidophone is
  meant to run on your own media, but "your own" doesn't mean "never
  malformed."
- **The generated brief / promo pack.** `kaleidophone auto` and `kaleidophone promo`
  write files that may later be pasted into a public description or
  caption. They should never echo a raw filesystem path from the run
  environment into that output.

## Explicitly out of scope

- Anything in `examples/demo/` — synthetic, local-only, not part of any
  release artifact.
- Resource exhaustion from deliberately pointing kaleidophone at a pathological
  file of your own making (e.g. a multi-hour audio file with `--out` on a
  full disk). Real bug reports about *unexpected* resource use on normal
  media are welcome as ordinary issues.
- ffmpeg's own security surface — report those upstream. kaleidophone's
  responsibility is what it passes to ffmpeg, not ffmpeg's decoders.

## A note on your media

kaleidophone is local-first: it never uploads or transmits your photos, audio, or
video anywhere. If that ever changes, it will be opt-in, documented here,
and announced in the changelog — not enabled by default. See
[ADR-0003](docs/decisions/0003-public-framework-private-assets.md).

## Supported versions

Pre-release. Only `main` receives fixes.
