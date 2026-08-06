# Architecture

How kaleidophone turns a brief into a video, cover, and promo pack — and why the
pipeline is split where it's split.

---

## 1. The pipeline

```mermaid
flowchart LR
    B["CreativeBrief\n(brief.yaml)"] --> A["analyze()\naudio/analysis.py"]
    B --> C["scan_media() + curate\nassets/curation.py"]
    A --> CM["compose()\ntimeline/compose.py"]
    C --> CM
    CM --> EDL["EDL\n(edl.json)"]
    EDL --> PV["preview()\nno ffmpeg, ~1s"]
    EDL --> RS["render_silent()\nffmpeg, expensive"]
    RS --> SIL["silent.mp4"]
    SIL --> MX["mux_audio()\nffmpeg, ~1s"]
    A --> MX
    MX --> OUT["master.mp4"]
    SIL --> VAR["variants.py\nteasers + thumbnails"]
    A --> COV["cover/generate.py"]
    A --> PROMO["promo/plan.py"]

    style EDL fill:#d1faf3,stroke:#0f766e,color:#134e4a
    style RS fill:#fde2e1,stroke:#b91210,color:#7f1d1d
    style MX fill:#ede9fe,stroke:#7c3aed,color:#4c1d95
```

Everything downstream of the brief is derived and rebuildable — see
[ADR-0001](decisions/0001-version-the-brief-not-the-render.md). The two
colored stages are the ones worth knowing the cost of: `render_silent`
(red) is the expensive one; `mux_audio` (purple) is the cheap one that
reuses its output.

## 2. Data flow, in order

1. **`CreativeBrief`** (`timeline/schema.py`, pydantic) — the one
   hand-authored file. Song, stations (a look), sections (a stretch of the
   song, a station, a cut density, an effect list), output config.
   `kaleidophone auto` can generate one; either way it's the same schema.

2. **`AudioAnalysis`** (`audio/analysis.py`, librosa) — BPM, beat grid,
   onset times/strength, RMS envelope, plus two heuristics derived from RMS
   and onset strength: quiet passages ("the hush") and energy jumps ("the
   switch"). Deterministic given the same audio file.

3. **Curated assets** (`assets/curation.py`) — each station's `media_dir`
   scanned and (for `kaleidophone auto`/`kaleidophone curate`) scored against the
   station's palette. A `dict[station_name, list[MediaAsset]]`.

4. **`EDL`** (`timeline/model.py` + `compose()`) — the resolved,
   frame-accurate timeline: every cut's start/end, which asset fills it,
   which effects fire. `compose()` is a pure function of
   `(brief, analysis, station_assets)` and a per-section seed, so the same
   inputs always produce the same edit — see
   [ADR-0001](decisions/0001-version-the-brief-not-the-render.md) on why
   that matters for re-renders.

5. **Render** (`render/ffmpeg_pipeline.py`) — see "Why segment-then-concat"
   below.

6. **Variants, cover, promo** — `render/variants.py` (teasers/thumbnails
   from the rendered master), `cover/generate.py` (a procedural cover from
   the same `AudioAnalysis`, independent of the video render), `promo/plan.py`
   (chapters/caption/teaser-cadence markdown from the brief + analysis).
   None of these three depend on each other; all three can run in any order
   once `AudioAnalysis` exists.

## 3. Why segment-then-concat, not one filter_complex graph

`render_silent()` renders every `Cut` as its own short ffmpeg call (scale,
crop, color grade, effects), writes it to a temp file, then concatenates all
of them and muxes audio on separately. The alternative — one giant
`filter_complex` graph for the whole video — would avoid re-encoding at
concat boundaries and could well be faster.

We didn't build that first version because a broken cut, in the segment
model, is a five-second re-render with an ffmpeg error that names the one
command that failed. In one filter-graph-for-everything, it's a few-hundred-
line graph to bisect. For a project whose whole reason to exist is being
fast to iterate on, "fast to debug when it breaks" outweighed "marginally
faster when it doesn't," at least for v0.1. A single-pass filter_complex
renderer is tracked in [ROADMAP.md](ROADMAP.md) as a real, worthwhile
optimization once the segment model has enough real usage to know which
effects are common enough to be worth optimizing for.

## 4. Effects: linear vs. graph filters

ffmpeg's filter language has two shapes, and `render/effects.py` splits
along that line:

| | Shape | Examples | Applied via |
|---|---|---|---|
| **Linear** | single input, single output | color grade, strobe, grain, scanlines, vignette, zoom | one comma-joined `-vf` chain |
| **Graph** | splits the frame into multiple named pads | kaleidoscope, halation | its own `-filter_complex` pass, chained after the linear pass |

`ffmpeg_pipeline._render_segment()` builds the linear chain once, runs it,
then runs one additional ffmpeg pass per graph effect on the previous
stage's output. N graph effects on one cut means N+1 total ffmpeg calls for
that segment — rare in practice, since most sections use zero or one graph
effect.

## 5. Cost, measured

From `examples/demo/` (24s synthetic song, 28 cuts, hand-authored 3-section
brief unless noted). Not a benchmark suite — one data point, on one
machine, cited here as **measured**, not a general performance claim; see
CONTRIBUTING.md, "Ground rules for claims" for how to reproduce these.

| Stage | Resolution | Time |
|---|---|---|
| Full `kaleidophone run` (analyze -> render -> promo) | 640x360 | 25.7s |
| Full `kaleidophone auto` (default 720p, 42 photos, 5 sections) | 1280x720 | 1m27s |
| `render_silent` alone | 640x360 | 17.4s |
| `mux_audio` alone (re-sync audio, no re-render) | 640x360 | 0.8s |
| `render_silent` alone | 1280x720 | 55.4s |
| `mux_audio` alone (re-sync audio, no re-render) | 1280x720 | 0.8s |

`mux_audio` is a near-fixed cost (a stream-copy plus one audio re-encode)
that barely moves with resolution; `render_silent` scales with pixel count.
That's why the remux speedup itself isn't a single constant — it's ~22x at
640x360 and ~68x at 1280x720 on this same demo, and grows further at higher
resolutions still. See [ADR-0001](decisions/0001-version-the-brief-not-the-render.md).

Grain/noise-heavy effects measurably inflate output size, and that scales
with resolution too: the same 28-cut EDL rendered at 640x360 is 31.4MB;
rendered at 1280x720 (identical cuts and effects, resolution changed only)
it's 123.3MB — a 3.9x size increase for a 4x pixel-count increase, since
noise resists h264 compression almost regardless of scale. The 720p `auto`
run above (more sections, more cuts, more photos) is 185MB for the same 24
seconds. This is a real tradeoff between the "vintage, grainy" look this
project's whole aesthetic calls for and output file size, not a bug. If
size matters more than grain for a given project, turn down
`StationConfig.grain` and drop the `grain` effect from section effect
lists. See CHANGELOG.md's "Known limitations".

BPM detection on the demo's synthetic click track (programmed at exactly
120.0 BPM) comes back as **117.5** — a reminder that beat tracking is a
heuristic first pass even on a clean signal, not just on a real
performance; see `SongConfig.bpm` to override it and the
`kaleidophone-audio-analysis` skill.

## 6. Why 1280x720 by default, not higher

The project this framework generalizes from was delivered at 1280x720 —
see `docs/case-studies/love.md`. Combined with the measured cost above and
this project's own stated priority ("efficient token... minimal and fast,"
not maximum resolution), `OutputConfig.resolution` defaults to 720p rather
than 1080p or 4K. Nothing stops a brief from requesting higher — it's a
plain tuple in the schema — but it isn't the default, and doubling
resolution roughly quadruples pixel count and render time for a look this
project's whole aesthetic (grain, scanlines, vignette) doesn't especially
reward.
