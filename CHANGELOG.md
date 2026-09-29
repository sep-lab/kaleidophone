# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.3.0] — 2026-09-29

**Three engines, one contract.** 0.2 cut your footage into a release. The
releases since then drew theirs: four of the last six had no footage at all,
and two needed per-pixel effects no filter graph can say. 0.3 brings both into
the repository as engines, and gives all three one way in (the song pack) and
one way out (`deliver`). See
[ADR-0007](docs/decisions/0007-three-engines-one-contract.md).

Before it shipped, 0.3 was reviewed from three seats — a principal musician, a
visualiser/art director and a staff engineer — and every finding they ranked
P0 or P1 is fixed below, measured before and after.

### Added — the canvas engine (`canvas/`)

- **Four shipped pieces, runnable from the repository**: HAMECHI MANZOR DARE,
  ( - ), SAME AS YOU, SHOULD I ? — each one self-contained HTML file with live,
  render and cover modes. Kept as they shipped and verified against it: SAME AS
  YOU built byte-identical to its release; SHOULD I ? renders 20/20 test frames
  and 8/8 covers PNG-identical; against frames decoded from the delivered
  films, 37.0–44.0 dB PSNR (adjacent frames: 21–25 dB). HAMECHI MANZOR DARE's
  released reel is *not* reproducible — the one-off harness that rendered it
  wasn't kept — and the docs say so.
- **`canvas/lib/`** — what the pieces had in common, for new pieces: `core`
  (math, keyframes, hashes, the grid, the envelope sampler, sprites), `live`
  (the three modes; a live analyser scaled from a pre-scan of the dropped
  track, delayed by the output latency, with the song pack's `voc`; a
  just-tuned fallback pad that goes half-time below 90 BPM; the 9:16 safe frame
  drawn with `?qa=1`), `ink` (boil on twos, the envelope held on twos,
  draw-on and erase, contact QA, a hand-lettered alphabet with per-glyph
  widths and a title fitter), `rig` (rig v2: IK, seated bodies built from the
  floor up, chairs built from the body, planted walks), `recursion` (vector
  droste and kaleidoscope), `viewfinder`.
- **`canvas/pieces/template`** — the starting point for a new piece: an 8-bar
  loop that exercises the lib. Both planted feet at 0 px for all 96 frames of
  its walk at 24 fps, the pose on twos, a title fitted to 78 % of the frame
  and held a full second, a lamp whose light no longer rings dark.
- **Tools**: `build.mjs` (one file, fonts inlined from pinned npm packages with
  a credit comment each — no font binaries in git; refuses a lib listed out of
  order and any piece that redeclares a lib name, naming both lines;
  `--reserved` prints the 146 names), `render.mjs` (deterministic silent
  render from its own build of the piece, parallel workers, forced keyframes by
  frame or `--key-times`, signature cards, stateful warm-up and resume, a JSON
  sidecar with the snapped `t0` and `silent_start`; a page error or any network
  request fails the run), `still.mjs` (QA stills with `--qa`, every cover),
  `synth.mjs` (synthetic twins, `--twin … --piece` to re-measure one in place),
  `gallery.mjs` (the public gallery). Every tool rejects a misspelled flag.
- **Synthetic twins.** Real song packs are private like the audio (ADR-0007);
  each piece ships the spec of a synthetic twin — the real tempo, first
  downbeat and section boundaries, each section's `[mean, p95, max]` per
  envelope rounded to 0.05, every hit generated. Measured against the real
  packs, the worst per-section gap is 0.02–0.05 (was 0.52–0.96 at the p95), so
  HAMECHI MANZOR DARE's masks now crack in the gallery as they do on the song.
- **The gallery**, rendered in CI and published with GitHub Pages
  (`.github/workflows/pages.yml`): animated WebP clips (0.39–1.25 MB each),
  posters for reduced motion, covers, the live pieces, a link preview image and
  the font licences. Nothing is committed. Closes #43.

### Added — frame programs (`kaleidophone.frames`)

- Per-pixel, stateful effects over footage, from two releases: `MemoryCanvas`
  (the video forgets its own footage), `generation_loss` (photocopies of
  photocopies, getting paler), `SlitScan`, `red_thread_grade`, `KaleidoBloom`,
  `GrainBank`, `feedback_echo`, `punch_zoom`, `mean_face`.
- A resumable runner: budgeted calls, checkpoints that resume bit-identically
  (no pickle), parts joined by the concat demuxer, worker planning that snaps
  boundaries to cuts.

### Added — commands

- **`kaleidophone envelope`** — the song pack: 100 Hz band energies, flux,
  centroid, a centre-channel vocal-band envelope, the beat grid, bar 1 and the
  loudest minute (snapped to a bar). It prints the other tempo octave with its
  score and warns when the call is close; fits the grid to the music every
  8 bars and warns when a live take drifts off it; estimates bar 1 from bass
  onsets and harmony changes, with a confidence and a runner-up
  (`--downbeat`, `--beats-per-bar` to overrule it). All of it lands in the
  pack's `grid_check`. numpy only; no librosa on this path.
- **`kaleidophone master-check`** — the remux landmark-drift guard from the
  roadmap (#18). Verdicts `remux` (0), `rerender bars …` (3), `new grid` (4)
  and `offset` (5, with the `silent_start` to deliver at). Within half a frame
  at 24 fps (`--tolerance-ms`) counts as aligned; every envelope a piece reads
  is compared bar by bar, so a master without its hi-hats says which bars and
  which bands; a vocal moved on an unchanged beat, a varispeed master and an
  added outro are each named for what they are; times in mm:ss next to bars.
- **`kaleidophone deliver`** — the delivery sheet: every cut from one silent
  render by stream copy (`-frames:v`, never `-t`), a signature-card segment
  concatenated in front, the master muxed with `loudness`, `fixed` or `auto`
  gain — one gain per master, so a story from a quiet intro stays as quiet as
  the song made it — and loudness and true peak measured on the delivered
  files, with the true-peak guard run after the limiter and the AAC encoder in
  every mode. The ceiling is −1 dBTP, or −2 for masters louder than −14 LUFS
  (Spotify's published guidance). Fades default to 5 ms in / 15 ms out; a
  negative `silent_start` pads the head; `audio: none` makes a silent cut
  (Spotify Canvas); `--dry-run` emits the same thing as a shell script for the
  machine that holds the master, with every path quoted against expansion.

### Added — the plugin

- Skills: `kaleidophone-canvas-piece`, `kaleidophone-release-kit`,
  `kaleidophone-master-swap`, `kaleidophone-footage-effects`; the
  creative-direction skill gains the concept lessons.
- Commands: `/kaleido:piece`, `/kaleido:deliver`, `/kaleido:master`.

### Added — docs

- **`docs/TECHNIQUES.md`** — 54 techniques from real releases, numbered, each
  with where it came from and where it lives in the code.
- **Seven case studies** (`docs/case-studies/`) and an index of all twelve
  releases. Closes #41, #42.
- ADR-0007; ARCHITECTURE §8 "Three engines"; CREATIVE-GUIDE "Drawn pieces: the
  concept is a rule" and "The frame, in numbers" (the 9:16 safe frame, the
  palette, stroke weights, minimum text size, frame rates, cover sizes);
  CONFIG-SCHEMA for the delivery sheet, the song pack and the synthetic twin.

### Changed

- The tagline: *Claude directs. Deterministic code draws every pixel.*
- CI gains a `canvas` job (92 node tests, every piece built from its synthetic
  twin, one second of each rendered in real Chromium with two workers and
  forced keyframes, every cover drawn, a page that reaches for the network
  shown failing) and a guardrail that refuses any tracked song pack not marked
  synthetic (`*songpack*.json` is ignored as well). Python: 816 tests at 96 %
  coverage (0.2.0: 143 at ~89 %); the floor rises from 80 to 92.
- Every ffmpeg call goes through `render/_ffmpeg_util.py` (the only module that
  imports `subprocess`, now a test) with `-nostdin` and no terminal stdin, so a
  `while read` loop around `deliver` no longer loses its input.
- Actions on checkout 7.0.1, upload-artifact 7.0.1 and download-artifact 8.0.1
  (Dependabot #2–#4), with every new workflow pinned the same way. Dependabot's
  numba PR (#5) changed only the comment above the Intel-Mac pin, so that it
  contradicted the pin; the comment is restored. `numba<0.63` is what keeps
  llvmlite below 0.46, the last line with x86_64 macOS wheels, and it stays.
- The PyPI publish job waits for a repository variable, and says so when it
  skips, so a tag no longer produces a red run before the trusted publisher
  exists (v0.2.0's did). The README installs from GitHub until then.
- ( - )'s paper grain is seeded; as shipped it used `Math.random()`, so no two
  renders of a frame matched.
- Live mode in ( - ), SAME AS YOU and SHOULD I ?: the click-to-play beat no
  longer stops after one kick, and the fallback pad stops when a track is
  dropped. Render mode is untouched (29/29 frames and covers PNG-identical
  before and after).

### Known

- `kaleidophone silent` can't force keyframes yet (its concat pass
  re-encodes), so a filter-graph render is cut by `deliver` only after a
  re-encode.
- ffmpeg's native AAC encoder (6.1/7.0, default coder) put short pops 14–20 dB
  above the local level into one heavily limited *synthetic* master;
  `-aac_coder fast` brought them to 4–8 dB. Not changed until it's checked on a
  real master.
- On ffmpeg 4.2, `-frames:v` drops the audio's last AAC frame, and with it the
  15 ms fade-out.
- Bar 1 is an estimate: `kaleidophone envelope` prints its confidence; check
  it by ear and pass `--downbeat` when it's low.
- HAMECHI MANZOR DARE draws its credit line in the system monospace font, so
  its frames differ slightly between machines.

## [0.2.0] — 2026-08-19

**Deliverables, not just a render.** 0.1 produced a 16:9 video. 0.2 produces
the things a release actually needs: vertical cutdowns framed on purpose,
burned-in bilingual text, and the per-platform copy — all from the same brief.

### Added — the plugin

- **kaleidophone installs as a Claude Code plugin.** `/plugin marketplace add
  sep-lab/kaleidophone`, then talk to it. Five commands — `/kaleido:direct`,
  `/kaleido:release`, `/kaleido:caption`, `/kaleido:cover`, `/kaleido:brief` —
  plus a new `kaleidophone-creative-direction` skill carrying the taste the
  per-stage skills don't. `docs/PRIOR-ART.md` named "is comfortable in a
  terminal" as a real limit on who this can serve; this is the answer to it.

### Added — text

- **`overlays`** — timed cards burned into the render: titles, lyric lines,
  credits, end cards. Composited in the single finishing pass rather than baked
  into each segment, so a card spanning a cut doesn't restart at the boundary.
- **Right-to-left shaping via libraqm.** Direction is detected from the text's
  own script. Rendering RTL without raqm raises rather than quietly emitting
  disconnected letterforms — output that looks like text to anyone who can't
  read the script and is plainly broken to anyone who can.
- **Five bundled SIL OFL fonts** (676 KB): Vazirmatn, Space Grotesk, Space
  Mono, Courier Prime. Addressed by role, not filename. A font resolved from a
  system path renders differently on every machine.
- **An overlay proof sheet** in `preview`, because cards are otherwise drawn
  blind and a line that overflows is found by watching the finished render.

### Added — delivery

- **`output.aspect`** — compose natively at `9:16`/`1:1`/`4:5` instead of
  centre-cropping a finished master.
- **`sections[].framing`** — `fill`, `crop` at an `x` in source pixels, or
  `window` (shrink and pad onto black). Which slice of a wide frame survives a
  vertical crop is a creative decision, and there was nowhere to put it.
- **`output.window`** — render a stretch of the song, rebased to zero, so one
  brief produces the master *and* the cutdown instead of two that drift.
- **`output.encode`** — CRF, preset, bitrate ceiling, colour tagging, audio
  bitrate and sample rate.
- **`kaleidophone kit`** and a `release` block — per-platform captions,
  chapters, timed comments, a pinned comment, a posting order. Facts derived,
  voice deliberately left open. See
  [ADR-0006](docs/decisions/0006-the-release-pack.md).
- `kaleidophone auto --aspect`.

### Fixed

- **Colour tags never reached the H.264 SPS.** Measured on ffmpeg 7.1, the
  `-color_primaries`/`-color_trc` flags set the container's `colr` box and
  leave the VUI empty, so `ffprobe` reported primaries and transfer as
  `unknown`. Now also passed via `-x264-params`, with x264's own names per
  standard.
- **A windowed render warned that the audio was longer than the video**, which
  is exactly what a window is for. Only the picture outlasting the song is
  reported now.
- **The release pack suggested pinning "the switch is at 0:00"** from a jump at
  0.53s. That's the track starting, not a moment.
- `SECURITY.md` named OpenCV as a decode path; it was removed in 0.1.0.
- Four issue/PR-template links used `../blob/main/...`, which resolves outside
  the repository.
- `cli.py`'s module docstring — what `--help` prints — listed 6 of 11
  subcommands.
- `_WorkDirectory`'s docstring cited a `--keep` flag that never existed.

### Changed

- `docs/CREATIVE-GUIDE.md`'s "label nothing" rule is now **describe nothing,
  inhabit something**. The original was learned from cutting genuinely cheesy
  data overlays and is right about those, but taken literally it forbids a
  tape readout or a DVD menu — which are not data about the song but a fiction
  the song plays inside.
- Test suite 143 → 281; coverage 89% → 90%.

## [0.1.0] — 2026-08-16

First public release.

### Fixed — correctness

- **Cuts now land on whole frames, and the render no longer drifts against
  its own audio.** `compose()` snaps every boundary onto the `1/fps` grid
  and `render_silent()` bounds each segment with `-frames:v N` instead of a
  duration in seconds. Because segments are concatenated, ffmpeg's
  truncation of a fractional frame accumulated on every cut, always in the
  same direction. Measured on a 300s/129 BPM synthetic track: 640 cuts, none
  on the frame grid, the render finishing **3.25s (78 frames) short** of the
  audio. After: 640/640 on the grid, 0.00s drift. See
  `docs/ARCHITECTURE.md`, "Frame-accurate cuts".
- **`_cut_boundaries()` used a hardcoded `1/24`** as its minimum cut length
  regardless of the brief's own `output.fps`.
- **A section with no detected beats silently became one static shot.**
  librosa returns no beats at all for a quiet passage — none in the first 11
  of 24 seconds on this repo's own demo song — so a section asking for
  `every_2_beats` got a single 8-second still with nothing said about it. It
  now falls back to a grid derived from the detected BPM and prints a note.
  The bundled demo goes from 28 cuts to 37 as a result.
- **`EDL` now refuses gaps and a non-zero start.** Under concatenation those
  don't render as gaps; they slide the entire edit off the audio.
- **`mux_audio()` warns before `-shortest` truncates** a longer stream —
  the first half of ROADMAP's remux landmark-drift guard.
- **16:9 teasers no longer hardcode 1280x720**, which silently downscaled
  the teaser of any brief rendering at 1080p or above.
- **ffmpeg's concat list now escapes apostrophes** in the work-directory
  path (e.g. a TMPDIR under `/Users/me/Dad's scratch`).

### Fixed — interface

- **The CLI reports errors as one actionable line and exits 2**, instead of
  a raw traceback that buried the carefully written message underneath. Add
  `--traceback` (or `KALEIDOPHONE_DEBUG=1`) for the full trace.
- **`kaleidophone --version`.**
- **Stations sharing one `media_dir` are scanned once**, not once per
  station — `kaleidophone auto` writes exactly that brief, so the documented
  next step used to decode every photo four times.

### Changed

- **OpenCV is no longer a dependency.** It was a ~90MB wheel used only to
  average a 64x64 thumbnail and read one video frame; Pillow and the ffmpeg
  already required now do both. Asset hue stays on the 0..180 scale the
  station presets and ADR-0004 are written against.
- **`StationConfig.duotone` is validated as `#RRGGBB`.** Those values are
  interpolated into an ffmpeg `curves=` filter string, and SECURITY.md names
  filter-graph injection as in scope.
- **Packaging is release-ready:** PyPI classifiers and project URLs, PEP 639
  license metadata, a `py.typed` marker, and a single-sourced version read
  from `kaleidophone.__version__`.
- **`numba<0.63` is pinned on x86_64 macOS only.** llvmlite ≥0.46 ships
  arm64-only macOS wheels, so on an x86_64 interpreter (a genuine Intel Mac,
  or an x86_64 Python under Rosetta) pip fell back to building LLVM from
  source and `pip install kaleidophone` failed outright.
- **Test suite: 81 → 143 tests, coverage 61% → 89%**, with the CI floor
  raised from 55 to 80. `cli.py`, `ffmpeg_pipeline.py`, `variants.py`, and
  `_ffmpeg_util.py` were all near 0%; they are now covered by asserting on
  the argv they build. pytest still never invokes ffmpeg.
- **CI actually runs.** It triggered on `main` while the only branch was
  `master`. Also adds Python 3.13 and a macOS leg for the render path.
- **GitHub Actions are pinned to commit SHAs**, with Dependabot to update
  them, plus issue/PR templates and CODEOWNERS.
- Documentation: every measured number re-measured after these changes and
  reported with the machine it was measured on; `docs/PRIOR-ART.md` added.

### Added

- `docs/case-studies/love.md` — "Iteration 2" section documenting the real
  second production round on the reference project: a replacement master
  whose landmarks drifted ~5s (why `remux` alone is unsafe there), the
  data-overlay-reads-as-kitsch lesson, three field-proven effect
  candidates (`scope_overlay`, `feedback_echo`, `punch_zoom`), and
  measured grain/denoise/CRF file-size numbers at 720p. With matching
  ROADMAP Phase 2 items and a CREATIVE-GUIDE "Learned in the field" rule.
- Initial public scaffold: `src/kaleidophone` package (audio analysis, station
  presets + curation, timeline/EDL compose, ffmpeg render pipeline,
  procedural cover art, promo-pack generation, CLI).
- `kaleidophone auto` — zero-config default mode: one song + one media folder to a
  full result, writing out the `CreativeBrief` it generated.
- `kaleidophone preview` — no-ffmpeg contact-sheet sanity check before rendering.
- `kaleidophone silent` / `kaleidophone remux` — split the expensive per-cut render from
  the cheap audio-sync step (see ADR-0001).
- `examples/demo/` — a fully synthetic, zero-personal-data end-to-end demo
  (`run_demo.sh`).
- Five ADRs (`docs/decisions/`), six `skills/` briefs, and the governance
  docs (`AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`).
- `docs/case-studies/love.md` — the reference case study this framework
  generalizes from.
- `tests/` — a pure-logic unit test suite (schema validation, cut-boundary
  and effect-conditional logic, auto-curation's empty-station guard, the
  target-hue curation fix, effect filter-string builders). Synthetic
  fixtures only, built in `tests/factories/` directly from numbers — no
  audio decode, no ffmpeg, no real media, same rule as `examples/demo/`.

### Changed

- Renamed the project from `mvideo` to `kaleidophone` — package directory,
  PyPI/CLI name, imports, and every doc, all lowercase throughout matching
  the original style. `mvideo` undersold the scope (cover art and a promo
  pack, not just a video); `kaleidophone` — Wheatstone's 1827 device that
  made sound vibrations visible — says what the pipeline actually does.
  See [ADR-0005](docs/decisions/0005-project-naming.md) for the full
  naming search, including the first pick (Sideband) turning out to
  already be taken.

### Fixed

- `timeline/compose.py`'s `_cut_boundaries()` could silently drop a
  section's true end when the last beat-derived boundary landed within one
  video frame of it, truncating the section by a fraction of a frame. Found
  writing `tests/test_compose.py`, not in a real render. Now snaps the last
  boundary back onto the section's end instead of dropping it.
- `assets/stations.py`'s `fire-leak` preset had no `duotone`, so it fell
  back to `_target_hue()`'s coarse warm-temperature guess (`15.0`) -- within
  ~2-5 hue units of `amber-room`'s and `gold-hour`'s actual duotone-derived
  hues, i.e. the same starved-station failure mode ADR-0004 already fixed
  once, recurring for a fourth preset the first fix didn't touch. Found
  writing `tests/test_stations.py`. `fire-leak` now has its own hot
  red-orange duotone.

### Known limitations (see ROADMAP.md for planned work)

- Heavy film-grain effects inflate output file size substantially at the
  default CRF (measured: a 24s/720p demo clip with grain on most cuts is
  ~185MB — see `docs/ARCHITECTURE.md`). Worth tuning per-project.
- Auto-mode's section boundaries and station cycling are simple heuristics,
  not a claim of good taste — see ADR-0004.
- Cover art and captions are deterministic/templated; AI-assisted
  alternatives are a documented, not-yet-built extension point (ADR-0002).
