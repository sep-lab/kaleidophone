# Roadmap

The ordering principle: **be excellent for one person cutting one song
before being mediocre for everyone.** kaleidophone already does the whole
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
- [x] Zero-config default mode (`kaleidophone auto`) with a heuristic-curation bug
      found and fixed against real (synthetic) fixtures — see
      [ADR-0004](decisions/0004-default-mode-and-auto-curation.md).
- [x] A no-ffmpeg contact-sheet preview (`kaleidophone preview`) for the
      confirm-before-you-render workflow.
- [x] Five ADRs, `AGENTS.md`/`CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`,
      the CI privacy/size guardrails, and the reference case study
      (`docs/case-studies/love.md`).
- [x] A fully synthetic, zero-personal-data end-to-end demo
      (`examples/demo/`) with real, measured timings in
      `docs/ARCHITECTURE.md`.

## Phase 1 — Prove it on a second real song ✅ complete, twelve times over

**Goal: confirm the framework generalizes past the one project it was
extracted from.** It did, and not only as a footage engine: twelve real
releases, built independently, kept re-deriving the same architecture — the
envelope, the silent segmented render, the mux at the end — across footage,
frame programs and drawn canvas pieces. See the
[case studies](case-studies/README.md) and
[ADR-0007](decisions/0007-three-engines-one-contract.md).

- [x] Worked case studies, scrubbed the way `love.md` was — seven new ones in
      0.3 ([#41](https://github.com/sep-lab/kaleidophone/issues/41),
      [#42](https://github.com/sep-lab/kaleidophone/issues/42)).
- [x] What those runs broke, fixed and written up: the drift guard, the AAC
      true-peak guard, frame-exact cuts, the delivery sheet ([TECHNIQUES.md](TECHNIQUES.md)).
- [ ] Real-world beat-tracking accuracy measured against real songs, for both
      `analyze` (librosa) and `envelope` (comb search) — the release notes
      have the real grids to compare against
      ([#49](https://github.com/sep-lab/kaleidophone/issues/49)).
- [ ] A case study from someone else's release. Twelve releases by one artist
      prove the architecture repeats, not that it travels.

## Phase 2 — Quality and cost tuning

- [ ] **Grain/file-size tradeoff.** The 720p demo run is ~182MB for 24
      seconds with grain on most cuts (measured, `docs/ARCHITECTURE.md`).
      Worth a documented set of "look" presets (e.g. `grain: 0.1` vs. `0.3`)
      with their real measured size/quality tradeoff, rather than one
      unexamined default. Iteration 2 of the reference project added
      real-project data points (raw grain vs. temporal-denoise-then-encode
      at 720p) — see the measured numbers at the end of
      `docs/case-studies/love.md`.
- [x] **Remux landmark-drift guard** — `kaleidophone master-check` (0.3,
      [#18](https://github.com/sep-lab/kaleidophone/issues/18)). Next: have
      `remux` run it and refuse a `new grid` verdict without a force flag.
- [ ] **Forced keyframes in `kaleidophone silent`**, so a filter-graph render
      can be cut by `deliver` with `-c:v copy` like the other two engines (its
      concat pass re-encodes today).
- [ ] **Three field-proven effect candidates** from the same iteration
      (`feedback_echo` and `punch_zoom` exist as frame-program effects since
      0.3; the filter-graph versions are still open):
      `scope_overlay` (a waveform oscilloscope with per-section
      color/amplitude), `feedback_echo` (previous-frame zoom-blend — cuts
      become morphs; the cheapest hypnosis dial found so far), and
      `punch_zoom` (beat/onset-triggered decaying zoom kick). Parameters
      and when-to-use notes are in the case study; `scope_overlay` and
      `feedback_echo` are graph effects, `punch_zoom` is linear.
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

## Phase 2b — The canvas engine (0.3 →)

- [x] The four shipped canvas pieces in the repository, verified against the
      delivered films; `canvas/lib/`; a template; synthetic twins; the gallery
      ([#43](https://github.com/sep-lab/kaleidophone/issues/43)).
- [ ] More of the pieces' techniques as lib modules: the torn-page mirror
      compositor, chromatography blooms, the pressure-ring swarm, the mask
      state machine, sprite fire, the contact-sheet cover family.
- [ ] A loop-seam check for reels meant to repeat: compare a cut's last frame
      with its first on the delivered file
      ([#19](https://github.com/sep-lab/kaleidophone/issues/19)).
- [x] A silent cut in `deliver` for a Spotify Canvas: `audio: none` on a cut
      writes it with no audio stream, and a sheet whose every cut is silent
      needs no master (0.3.0).
- [ ] The Canvas loop itself (8 s, crossfaded) as a render mode of the
      canvas harness; SAME AS YOU's came from a state of its own in the piece
      (`canvasState()`).
- [x] `render.mjs` writes the `silent_start` it snapped to, with the forced
      keyframes, in a JSON sidecar next to every render (0.3.0).
- [ ] `deliver` from that sidecar in one step, instead of copying
      `silent_start` into the sheet by hand.
- [ ] Check the AAC encoder's coder on real masters: on one heavily limited
      synthetic master, ffmpeg's default AAC coder left short pops that
      `-aac_coder fast` mostly removed (see CHANGELOG 0.3.0, "Known").

## Phase 2c — The session, every platform, every ending (0.4) ✅

- [x] **Session engine** — MIDI and stems from the DAW session into the song
      pack: exact events, chords, the session's grid, aligned stems, `voc`
      from the vocal stem; event helpers in the canvas lib
      ([#56](https://github.com/sep-lab/kaleidophone/issues/56)).
- [x] **One piece, every platform** — the platform table, delivery presets,
      reframes, one naming convention, a manifest, the covers matrix
      ([#57](https://github.com/sep-lab/kaleidophone/issues/57); folds in #27,
      #30, #34).
- [x] **Endings as variants** — one body, N endings, joined by stream copy,
      with a contact sheet to choose
      ([#58](https://github.com/sep-lab/kaleidophone/issues/58)).
- [x] **No tokens, another agent** — the no-AI path, local caption drafts,
      `AGENTS.md` and the skills for other agents, which model for what
      ([docs/PORTABILITY.md](PORTABILITY.md)).

## Phase 2d — The next engines and features

Filed after 0.3.0 from what the releases keep asking for; each issue has the
idea, why, and the first pieces.

- [ ] **Darkroom engine** — a shot list for a 36-exposure roll from the song,
      the scans back in, film physics on the drop
      ([#59](https://github.com/sep-lab/kaleidophone/issues/59)).
- [ ] **Stage engine** — the pieces as a live set on the drum machine's
      clock, every show re-rendered afterwards
      ([#60](https://github.com/sep-lab/kaleidophone/issues/60)).
- [ ] **Shader engine** — GPU fragment shaders under the same contract
      ([#61](https://github.com/sep-lab/kaleidophone/issues/61)).
- [ ] **Foley engine** — the picture's events as a sound-effects stem
      ([#62](https://github.com/sep-lab/kaleidophone/issues/62)).
- [ ] **Endless reels** — loop points found in the song, seamless loops
      ([#63](https://github.com/sep-lab/kaleidophone/issues/63)).
- [ ] **Rotoscope rig** — a phone video of you moving drives the ink figure
      ([#64](https://github.com/sep-lab/kaleidophone/issues/64)).
- [ ] **Nastaliq draw-on** — Persian titles written stroke by stroke
      ([#65](https://github.com/sep-lab/kaleidophone/issues/65)).
- [ ] **Overnight concepts** — three rules and three animatics by morning
      ([#66](https://github.com/sep-lab/kaleidophone/issues/66)).
- [ ] **Fan editions** — numbered, seeded covers as two-ink prints
      ([#67](https://github.com/sep-lab/kaleidophone/issues/67)).
- [ ] Moonshots: every song as a repo
      ([#68](https://github.com/sep-lab/kaleidophone/issues/68)), a visual
      album ([#69](https://github.com/sep-lab/kaleidophone/issues/69)), analog
      round-trip covers ([#70](https://github.com/sep-lab/kaleidophone/issues/70)),
      release day on autopilot
      ([#71](https://github.com/sep-lab/kaleidophone/issues/71)).

## Phase 2e — Never the same twice (0.5 → 0.10)

The last six releases are all canvas pieces on one scaffold, and they have
started to look alike; release night is still hand-made. This arc makes
sameness something CI can measure and refuse, makes the Mac the studio, and
lands what the releases since 0.4.0 taught. Each milestone ends in something
to watch or click; its tracking issue says what. Engineering comes first; new
songs wait for the release lane to reopen at v0.6.0
([milestones](https://github.com/sep-lab/kaleidophone/milestones)).

- [x] **M0 · Truth-up and privacy first** — the deny-list and session-URL
      checks, doc counts that can't drift, the milestones re-homed, the night
      clock's baseline ([NIGHT-CLOCK.md](NIGHT-CLOCK.md)).
- [ ] **M1 · The Mac is the studio** — benchmarks, `doctor`, the frozen-piece
      contract and golden frames ([#74](https://github.com/sep-lab/kaleidophone/issues/74)).
- [ ] **M2 · Six pieces** — Setareh and ⛈️ STORM land; the Lib Lab (v0.5.0,
      [#75](https://github.com/sep-lab/kaleidophone/issues/75)).
- [ ] **M3 · STORM, the whole night** — deliver v2, the full film, no
      hand-written mux (v0.6.0, [#76](https://github.com/sep-lab/kaleidophone/issues/76)).
- [ ] **M4 · The Atlas and the Deck** — the catalogue as computed; cards dealt
      from its empty regions ([#77](https://github.com/sep-lab/kaleidophone/issues/77)).
- [ ] **M5 · Loops and editions** — Canvas loops, boards, seeded editions
      (v0.7.0, [#78](https://github.com/sep-lab/kaleidophone/issues/78)).
- [ ] **M6 · Never the same twice** — the style genome, the signature card,
      new template families, the B-side (v0.7.0, [#79](https://github.com/sep-lab/kaleidophone/issues/79)).
- [ ] **M7 · One tag plays every piece** — `<kp-piece>`, `envelope.js`,
      manifest v2 (v0.8.0, [#80](https://github.com/sep-lab/kaleidophone/issues/80)).
- [ ] **M8 · Song in, kit out by morning** — markers, `kaleidophone night`,
      kit v2 (v0.9.0, [#81](https://github.com/sep-lab/kaleidophone/issues/81)).
- [ ] **M9 · New worlds, the artist's hand** — analog and opt-in generated
      inputs, the world template (v0.10.0, [#82](https://github.com/sep-lab/kaleidophone/issues/82)).

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
      (0.4 did this for the release pack with a *local* model:
      `kaleidophone kit --llm ollama:<model>`.)

## Phase 4 — Ready to be someone else's tool

- [x] Decide [ADR-0005](decisions/0005-project-naming.md) and do the rename
      pass (package dir, `pyproject.toml`, imports, docs) — landed as
      `kaleidophone`.
- [x] Publish: a public GitHub repo (0.1.0), a Claude Code plugin (0.2.0).
- [ ] PyPI: the release workflow is ready; it needs the trusted publisher on
      PyPI's side and the repository variable `PYPI_TRUSTED_PUBLISHING=true`
      (see `.github/workflows/release.yml`).
- [ ] Submit the plugin to the official Claude Code plugin directory
      ([#39](https://github.com/sep-lab/kaleidophone/issues/39)).
- [x] `docs/PRIOR-ART.md` — a fair look at existing "photo slideshow to
      music" and AI-music-video tools, what they actually do differently,
      and what risk (if any) remains unanswered here. Wit's own
      `docs/PRIOR-ART.md` is the template.
- [x] A demo people can actually watch, without committing media: the
      [gallery](https://sep-lab.github.io/kaleidophone/), rendered in CI from
      synthetic twins (0.3).

## Explicitly not planned

- **Hosting or publishing videos.** kaleidophone produces files; where they go is
  yours — see `AGENTS.md`, "When to stop and ask".
- **A GUI.** The CLI + editable-YAML-brief loop is the interface; a GUI
  would be a different, much larger project layered on top, not a near-term
  goal.
- **Cross-platform video-generation-model support as the default engine.**
  See [ADR-0002](decisions/0002-deterministic-edit-engine.md) — this is a
  deliberate, documented boundary, not a gap waiting to be filled.
