# Case studies

kaleidophone's central claim is that its architecture generalizes. It says
the same few answers keep coming back whatever the video is made of: version
the brief, not the render; drive the picture from the song's own envelope;
render in segments and concatenate; render silent and mux the audio where it
lives; look at frames before paying for the expensive step. A framework
extracted from one project can't prove that about itself. The releases below
were each built as their own project, from notes rather than a shared
codebase, by Sep The Concept, the artist this framework was extracted from.
Each one is a data point: either it re-derived those answers on its own, or
it found where they break. The case studies are the evidence, so they record
the failures as carefully as the techniques.

**How to read them.** Numbers are labeled. **Measured on the release** means
measured during the real build. The audio and footage behind them are
private and never enter this repository
([ADR-0003](../decisions/0003-public-framework-private-assets.md)), so those
numbers can't be re-run from here. **Measured on the port** means measured
against the code in `canvas/pieces/`, which you can run. Anything inferred
says so. Technique numbers (#N) refer to
[TECHNIQUES.md](../TECHNIQUES.md).

**What's scrubbed, everywhere.** Song titles are real and credited to Sep
The Concept. Left out: lyrics (never quoted, paraphrased or translated),
collaborators' and third parties' names and handles, the people in any
footage, personal paths, file hashes and posting plans. No real frame, audio
or envelope pack enters this repository. Each case study says what it left
out and why, the way [love.md](love.md) does.

## The releases

Rows 1–12 are the original tally of twelve, in order, and the releases since
carry it on. Harja shipped in the same stretch as the first twelve and is
listed too, unnumbered, because that tally didn't count it.

| # | Release | Built | Medium | Re-derived | New | Case study |
|---|---|---|---|---|---|---|
| 1 | **LOVE** | Aug 2026 | ~400 film-scan photos cut and graded by ffmpeg; an 11-minute two-part track | — this is the origin the framework was extracted from: segment-then-concat, the cheap remux | stations as looks, "the switch"; in iteration 2, a scope overlay, feedback echo and punch zoom, and the finding that a new master can silently break a remux | [love.md](love.md) |
| 2 | **pole bala hakim** and **LOST** | before the framework | pole bala hakim: a cover of another artist's song, re-produced from scratch, with renders driven by the bass envelope. LOST: a collaborative release, an analog/lo-fi visualizer built from standalone scripts | both, independently: segment-then-concat (versioned chunk folders and concat lists) and a manual frame check (exported check frames and cover candidates) | pole bala hakim's round trip: the second half of the video is the first half played in reverse, under a synchronized rewind visual | not yet written |
| 3 | **Gole Sang** | Aug 2026 | fully procedural, no photos: one unbroken 4:37 shot of a car on a desert highway | an envelope-driven render, segment renders run as parallel jobs, check frames | the road's center line *is* the track's waveform, scrolling toward the car, so every hit is visible ~2.5 s before it lands; focal length tied to frame height so portrait renders don't break; features computed from the WAV, since an MP3 adds a 24–48 ms codec offset | — |
| 4 | **Factor** | Aug 2026 | HTML/CSS documents screenshotted in a headless browser, then animated with ffmpeg | a beat grid driving the motion (a receipt strip printing upward in 2-beat steps); the reel and the story from one system at different step sizes | the concept "the receipt": the song is the delivery, the cover is the paperwork; the browser shapes Persian correctly, sidestepping the reshaper bug; deadpan, concept-first covers, because decoration read as corny | — |
| — | **Harja Gashtam Naboodi** | Aug 2026 | a walk film; a collaboration, with the artist's vocal on another producer's track | segment-then-concat (one body render plus swappable endings, stream-copy concat, identical encoder settings); audio swaps as a `-c:v copy` remux after a cross-correlation alignment check | the film resolves into the cover photograph; five alternate endings, each re-authored in about a minute without re-rendering the body; ambience-first sound, with the song crossfading in over a real ambience, a tape-stop and a reversed rewind bed | — |
| 5 | **The Night Track Talks** | Aug 2026 | the artist's own night footage (1080p50) under a track that carries a recorded recitation of a Persian poem | segment-then-concat the hard way: a single ffmpeg filtergraph with 10+ trim branches was OOM-killed on a 2-core machine. The fix was per-segment renders with uniform settings, the concat demuxer, and one finish pass | [window reveal](../TECHNIQUES.md#1-window-reveal): quiet passages play inside a small window and the finale blasts it full-frame; [audio-timed bilingual subtitles](../TECHNIQUES.md#2-audio-timed-subtitles) | — |
| 6 | **Loneliness** | Aug 2026 | a collaborator's finished short film, untouched, with the track fitted to it | segment-then-concat, this time because of per-command time limits on the only machine that could render | [bar fit](../TECHNIQUES.md#3-bar-fit), [crop drift](../TECHNIQUES.md#4-crop-drift), [on-device rendering](../TECHNIQUES.md#5-on-device-rendering) | [loneliness.md](loneliness.md) |
| 7 | **AHANGE AROOSI** | Aug 2026 | found wedding footage through a python float-RGB frame engine | envelope-driven effects, beat-snapped EDLs, stride-parallel segment workers → concat → a finish pass, check-frame QA boards | [#6](../TECHNIQUES.md#6-red-thread-grade)–[#11](../TECHNIQUES.md#11-outro-splice): the red-thread grade, slit-scan, kaleido bloom, the tracked-overlay inpaint, a grain bank, the outro splice | [ahange-aroosi.md](ahange-aroosi.md) |
| 8 | **MIKONAMET YEROZI KHOB FARAMOOSH** | Sep 2026 | the artist's own performance footage through a python frame engine running on the machine that holds it | envelope-driven effects, a beat-snapped EDL, segment renders, check-frame boards | [#12](../TECHNIQUES.md#12-memory-canvas)–[#18](../TECHNIQUES.md#18-aac-true-peak-guard): a stateful memory canvas and the checkpointed workers it forced, generation loss, the mean face, RTL title erosion, the signature card, a lip-sync test, the AAC true-peak guard | [mikonamet.md](mikonamet.md) |
| 9 | **HAMECHI MANZOR DARE** | Sep 2026 | a live audio-reactive browser canvas: one HTML file with three modes | envelope-driven visuals, beat-snapped cut starts, a planned per-phrase schedule, a silent render muxed where the audio lives | the canvas medium itself, [#19](../TECHNIQUES.md#19-three-mode-piece)–[#27](../TECHNIQUES.md#27-jpeg-capture): the three-mode piece, the render harness, stroke scaling, sprite fire, JPEG capture | [hamechi-manzor-dare.md](hamechi-manzor-dare.md) |
| 10 | **( - )** | Sep 2026 | a canvas ink cartoon on twos | the envelope pack, a silent render, bar-snapped windows, a signature card, the mux where the audio lives | [#28](../TECHNIQUES.md#28-paper-cut-out)–[#32](../TECHNIQUES.md#32-rig-primitives): the paper cut-out, twos and boil, the pure function of time, the square cover crop | [minus.md](minus.md) |
| 11 | **SAME AS YOU** | Sep 2026 | a canvas ink cartoon on one page torn in two | all of the above | [#33](../TECHNIQUES.md#33-floor-up-seating)–[#43](../TECHNIQUES.md#43-inhale-erase-splash): rig v2 and contact QA, the torn-page mirror, vector droste and kaleidoscope, loop clocks, forced keyframes, the float pre-master check, the inhale erase | [same-as-you.md](same-as-you.md) |
| 12 | **SHOULD I ?** | Sep 2026 | canvas photography, seen through a film camera's viewfinder | all of the above | [#44](../TECHNIQUES.md#44-viewfinder-compositor)–[#54](../TECHNIQUES.md#54-cover-variant-family): the viewfinder compositor, split-image sync, grid arithmetic, the lyric map, two master-swap checks, the 37th frame, the cover family | [should-i.md](should-i.md) |
| 14 | **⛈️** | Oct 2026 | a top-down pixel city at night, drawn like a console game: one small storm that follows him | the three-mode piece, a pure function of time, the signature card, song-pack events with grid fallbacks; and the whole piece built and rendered by this repository's own tools while it was private (`KALEIDOPHONE_PIECES`) | [#63](../TECHNIQUES.md#63-console-pixel-pipeline)–[#71](../TECHNIQUES.md#71-puddle-sky-and-drying-trail): the console pixel pipeline and its dither, deferred 2D lighting, screen-door alpha, light before sound, split clocks, a landmark-pinned path, a game-time HUD, a world-anchored city, the puddle sky and the drying trail | [storm.md](storm.md) |

The four canvas pieces (9–12) together close
[#42](https://github.com/sep-lab/kaleidophone/issues/42), a fully procedural
video with no source footage. MIKONAMET closes
[#41](https://github.com/sep-lab/kaleidophone/issues/41), a camera-sourced
vertical release.

## What the releases show

- **Segment-then-concat, arrived at for five different reasons.** The first
  was iteration cost: LOVE, and independently pole bala hakim and LOST. The
  second was memory, when The Night Track Talks' one big filtergraph was
  OOM-killed. The third was wall-clock limits, in Loneliness. The fourth was
  parallel stride workers writing independent segment files, in AHANGE
  AROOSI. The fifth was a stateful effect under a per-command time limit,
  which forced checkpointed workers in MIKONAMET. The canvas pieces split a
  window across browser pages and join the parts with the concat demuxer
  (`canvas/tools/render.mjs`). This is the field version of
  [ARCHITECTURE.md](../ARCHITECTURE.md)'s "why segment-then-concat": don't
  let the graph grow unbounded.
- **One envelope pack drives everything.** From AHANGE AROOSI on, every
  release computes an envelope pack from the WAV and drives every effect
  from it. For AHANGE AROOSI and the canvas pieces that meant band levels,
  rms and flux at 100 Hz, plus beats, and sometimes onsets or a vocal
  envelope. There is no on-screen data about the song: label nothing, react
  to everything. That is the rule LOVE's iteration 2 reached after its dials
  and counters read as kitsch ([CREATIVE-GUIDE.md](../CREATIVE-GUIDE.md),
  "Learned in the field").
- **Render silent, and mux where the audio lives.** It is the cheap re-mux
  of [ADR-0001](../decisions/0001-version-the-brief-not-the-render.md),
  re-derived. Harja swaps audio with a stream-copy remux once a
  cross-correlation check shows alignment. From HAMECHI MANZOR DARE on, the
  WAV never moves: the silent video travels to it.
- **The master will change, so check before re-rendering.** LOVE's new
  master moved its landmarks by ~5 s, so a remux would have desynced every
  cut. ( - )'s kept the grid, and it cost one constants edit. SAME AS YOU's
  changed four passages, and only those bars were redrawn. SHOULD I ?'s
  first new master changed nothing that mattered, so it was a re-mux
  ([#49](../TECHNIQUES.md#49-master-drop-in-check)); its second added a
  voice, and a per-bar stem diff found exactly where
  ([#52](../TECHNIQUES.md#52-what-the-new-master-added)). The AAC true-peak
  guard needed re-measuring for each master
  ([#18](../TECHNIQUES.md#18-aac-true-peak-guard),
  [#50](../TECHNIQUES.md#50-aac-guard-per-master)).
- **Look at frames first.** There were exported check JPEGs (pole bala
  hakim, LOST), check frames (Gole Sang), QA boards (AHANGE AROOSI,
  MIKONAMET), a contact-QA overlay (SAME AS YOU) and a list of QA timestamps
  (SHOULD I ?). They are all the same step that `kaleidophone preview`'s
  contact sheet exists to make routine.
- **A different medium, the same answers.** The canvas pieces aren't
  python or ffmpeg frame engines at all. They are browser canvases driven by
  a harness, and they still re-derived every point above.

## What's in this repository, and what isn't

The canvas pieces are here as source: `canvas/pieces/<id>/` holds the
modules, a template, `piece.json` (grid, render settings, cut windows,
covers), a `driver.mjs`, and a `synthetic.json`. They are built and rendered
with `canvas/tools/` (`build.mjs`, `synth.mjs`, `render.mjs`, `still.mjs`).
Real song packs are derived from unreleased audio, so they stay private.
Each piece ships a synthetic twin instead, which keeps the grid and the
rounded section levels and generates the rest, so everything runs on a stranger's
machine. The python engines of the earlier releases are not in the
repository. Their techniques are written up in
[TECHNIQUES.md](../TECHNIQUES.md). [ROADMAP.md](../ROADMAP.md) Phase 2
tracks the remux landmark-drift guard, which SHOULD I ?'s drop-in check
([#49](../TECHNIQUES.md#49-master-drop-in-check)) is a working prototype of.

## Adding one

A case study run by someone other than the artist this framework came from
would do more for the "it generalizes" claim than anything else on the
roadmap ([CONTRIBUTING.md](../../CONTRIBUTING.md)). Match the bar these set:
real structure, timings and measured numbers; nothing personal; and an
honest account of what broke.
