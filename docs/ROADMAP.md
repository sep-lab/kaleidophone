# Roadmap

The ordering principle: **be excellent for one person cutting one song
before being mediocre for everyone.** mvideo already does the whole
pipeline end to end on synthetic fixtures (`examples/demo/`) — what follows
is making it good on real, messy material, then making it easy for other
people to pick up.

---

## Phase 0 — Scaffold ✅ complete

- [x] Core package: audio analysis (BPM/beats/onsets/quiet-passages/energy-
      jumps), station presets + heuristic curation, `CreativeBrief` schema,
      EDL compose, ffmpeg render engine (linear + graph effects), teaser/
      thumbnail variants, procedural cover art, promo-pack generation, CLI.
- [x] The cheap/expensive split (`render_silent` / `mux_audio`) — see
      [ADR-0001](decisions/0001-version-the-brief-not-the-render.md).
- [x] Zero-config default mode (`mvideo auto`) with a heuristic-curation bug
      found and fixed against real (synthetic) fixtures — see
      [ADR-0004](decisions/0004-default-mode-and-auto-curation.md).
- [x] A no-ffmpeg contact-sheet preview (`mvideo preview`) for the
      confirm-before-you-render workflow.
- [x] Five ADRs, `AGENTS.md`/`CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`,
      the CI privacy/size guardrails, and the reference case study
      (`docs/case-studies/love.md`).
- [x] A fully synthetic, zero-personal-data end-to-end demo
      (`examples/demo/`) with real, measured timings in
      `docs/ARCHITECTURE.md`.

## Phase 1 — Prove it on a second real song

**Goal: confirm the framework generalizes past the one project it was
extracted from.** Everything in Phase 0 was designed by generalizing from a
single case study; it hasn't yet been run against a second one.

- [ ] A second worked case study and `examples/` brief, scrubbed the same
      way `docs/case-studies/love.md` was — tracked, pending the source
      material. See `CONTRIBUTING.md`, "Ways to contribute that we
      especially want".
- [ ] Whatever that run breaks or gets visibly wrong, fixed and written up
      honestly (a bad first result is a finding, not a failure to hide —
      matches this project's borrowed documentation ethic; see `AGENTS.md`).
- [ ] Real-world beat-tracking accuracy measured against at least one real
      (non-synthetic) song, since `examples/demo/`'s synthetic fixtures are
      rhythmically simple by design and don't test this — see
      `examples/demo/generate_fixtures.py`'s own "what this does not
      handle".

## Phase 2 — Quality and cost tuning

- [ ] **Grain/file-size tradeoff.** The 720p demo run is ~185MB for 24
      seconds with grain on most cuts (measured, `docs/ARCHITECTURE.md`).
      Worth a documented set of "look" presets (e.g. `grain: 0.1` vs. `0.3`)
      with their real measured size/quality tradeoff, rather than one
      unexamined default.
- [ ] **Smarter auto-sectioning.** `timeline/autobrief.py` currently
      discards *all* detected quiet-passage/energy-jump boundaries and
      falls back to even slicing when there are too many candidates (see
      its docstring). Keeping the strongest subset instead is a real
      algorithm to design, not a one-line fix.
- [ ] **Single-pass render.** `render/ffmpeg_pipeline.py` renders one small
      clip per cut and concatenates (see `docs/ARCHITECTURE.md`, "Why
      segment-then-concat") — debuggable but not the fastest possible
      approach. A single `filter_complex` graph for a whole section (or the
      whole video) is worth prototyping once there's enough real usage to
      know it's the bottleneck that matters.
- [ ] **Vision-assisted curation, as an opt-in upgrade.** The heuristic
      scorer in `assets/curation.py` is fast and free but simplistic (mean
      hue/saturation/brightness). A vision-model pass that's meaningfully
      better on a real, messy photo library is worth adding *behind a flag*
      — the deterministic scorer stays the default with no API key required;
      see [ADR-0002](decisions/0002-deterministic-edit-engine.md).

## Phase 3 — Cover art and captions get an AI option

Scoped narrowly on purpose — see
[ADR-0002](decisions/0002-deterministic-edit-engine.md): the cost argument
against generative *video* doesn't apply to a single cover image or a
caption.

- [ ] `cover/generate.py` gets a second, opt-in backend that calls an image
      model with a prompt derived from the brief (stations, mood, title),
      falling back to today's deterministic "frequency stack" renderer when
      no API key is configured. Both ship real output either way.
- [ ] `promo/plan.py`'s templated caption (`_suggest_caption`) gets an
      optional LLM-assisted rewrite pass — still starting from the same
      structured facts (chapters, BPM, mood words), not a free-form prompt.

## Phase 4 — Ready to be someone else's tool

- [ ] Decide [ADR-0005](decisions/0005-project-naming.md) and do the rename
      pass (package dir, `pyproject.toml`, imports, docs) in one PR.
- [ ] Publish: a public GitHub repo (mirroring
      [sep-lab/Wit](https://github.com/sep-lab/Wit)'s structure, which this
      scaffold already follows), then a PyPI release once the CLI surface
      (`analyze`/`curate`/`compose`/`preview`/`silent`/`remux`/`render`/
      `cover`/`promo`/`run`/`auto`) has had a real second project run
      through it (Phase 1).
- [ ] `docs/PRIOR-ART.md` — a fair look at existing "photo slideshow to
      music" and AI-music-video tools, what they actually do differently,
      and what risk (if any) remains unanswered here. Wit's own
      `docs/PRIOR-ART.md` is the template.
- [ ] A short screen-recorded or exported demo (using `examples/demo/`'s
      synthetic fixtures, or a real project once one's been publicly
      shared) linked from the README, once there's output worth showing
      publicly.

## Explicitly not planned

- **Hosting or publishing videos.** mvideo produces files; where they go is
  yours — see `AGENTS.md`, "When to stop and ask".
- **A GUI.** The CLI + editable-YAML-brief loop is the interface; a GUI
  would be a different, much larger project layered on top, not a near-term
  goal.
- **Cross-platform video-generation-model support as the default engine.**
  See [ADR-0002](decisions/0002-deterministic-edit-engine.md) — this is a
  deliberate, documented boundary, not a gap waiting to be filled.
