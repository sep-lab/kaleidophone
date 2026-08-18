# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **`output.aspect`** — compose natively at `16:9`, `9:16`, `1:1` or `4:5`
  instead of centre-cropping an already-rendered 16:9 master. Setting it alone
  picks the canonical resolution for that shape.
- **`sections[].framing`** — how a source frame is fitted into a
  differently-shaped output frame: `fill` (the previous behaviour), `crop` at a
  chosen `x` in source pixels, or `window`, which shrinks the frame and pads it
  onto black. Which slice of a wide frame survives a vertical crop is a
  creative decision, and until now there was nowhere to put it.
- **`output.window`** — render only a stretch of the song, rebased to start at
  zero, so one brief produces both the full master and a cutdown instead of two
  briefs that drift apart. `mux_audio()` seeks the audio to match.
- **`output.encode`** — CRF, preset, a bitrate ceiling (`maxrate`/`bufsize`),
  colour tagging (`bt709`/`bt601`/`bt2020`), and audio bitrate/sample rate.
  Every default reproduces the previously-hardcoded settings exactly, so adding
  the block is opt-in and omitting it changes nothing.

### Fixed

- `SECURITY.md` named OpenCV as a decode path; it was removed as a dependency
  in 0.1.0.
- Four issue/PR-template links used `../blob/main/...`, which resolves outside
  the repository once GitHub inlines a template into an issue body.
- `cli.py`'s module docstring — what `kaleidophone --help` prints — listed 6 of
  the 11 subcommands.
- `_WorkDirectory`'s docstring cited a `--keep` CLI flag that has never
  existed; the real control is the `keep_work_dir=` keyword argument.

Nothing yet.

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
