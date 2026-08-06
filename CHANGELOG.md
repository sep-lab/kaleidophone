# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- Initial public scaffold: `src/mvideo` package (audio analysis, station
  presets + curation, timeline/EDL compose, ffmpeg render pipeline,
  procedural cover art, promo-pack generation, CLI).
- `mvideo auto` — zero-config default mode: one song + one media folder to a
  full result, writing out the `CreativeBrief` it generated.
- `mvideo preview` — no-ffmpeg contact-sheet sanity check before rendering.
- `mvideo silent` / `mvideo remux` — split the expensive per-cut render from
  the cheap audio-sync step (see ADR-0001).
- `examples/demo/` — a fully synthetic, zero-personal-data end-to-end demo
  (`run_demo.sh`).
- Five ADRs (`docs/decisions/`), five `skills/` briefs, and the governance
  docs (`AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`).
- `docs/case-studies/love.md` — the reference case study this framework
  generalizes from.
- `tests/` — a pure-logic unit test suite (schema validation, cut-boundary
  and effect-conditional logic, auto-curation's empty-station guard, the
  target-hue curation fix, effect filter-string builders). Synthetic
  fixtures only, built in `tests/factories/` directly from numbers — no
  audio decode, no ffmpeg, no real media, same rule as `examples/demo/`.

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
