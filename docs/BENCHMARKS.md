# Benchmarks

How fast kaleidophone renders and delivers, on which toolchain, and how
a speed number earns the word **measured** here.

> **Status: no numbers yet.** This page is the method and the empty
> tables. The first baseline is a gated overnight run on the reference
> Mac (Apple M1 Pro), under its current x86_64-under-Rosetta toolchain. Then
> it is run again on a native arm64 toolchain. Until a result file in
> `benchmarks/results/` backs a cell, the cell stays empty. Nothing here is
> estimated to fill a gap.

## Why this page exists

Before the harness, the only speeds this repository had measured were
`render_silent` on the demo (README, "Cost, measured";
[ARCHITECTURE.md §6](ARCHITECTURE.md)), a few canvas and frame-program
rates from real releases (the [case studies](case-studies/README.md)), and
the CLI's import time. Each was one data point on one machine. Every
speed-up anyone proposed was **inferred**: more canvas workers, a native
toolchain instead of Rosetta 2, AudioToolbox AAC, parallel delivery. The
harness measures before anything is changed, so each change can be judged
against a number.

## Labels

Every number in this file and in any doc that cites it carries one of three
labels (AGENTS.md, "Rules for claims and numbers"):

| Label | What it means here |
|---|---|
| **measured** | The median of N runs in one `kp-bench/1` result file in `benchmarks/results/`. The run passed `kaleidophone doctor --bench-gate`, and the file is named next to the number. |
| **cited** | Measured somewhere else (a case study, a CI log, a vendor's documentation). The source is linked, and it is not re-measured here. |
| **inferred** | Derived, not observed: an extrapolation (the long-form render), a ratio of two measured numbers taken on different runs, a projection. The derivation is written next to it. |

Two rules on top of those:

- **A result with `"gate": {"overridden": true}` backs nothing.** That is
  the `--ungated` smoke test. Its label says `measured, ungated: not a
  baseline`, and it stays out of `benchmarks/results/`.
- **Rosetta and native numbers come from separate result files**, each with
  its own `toolchain` block. A speed-up is the ratio of two medians from two
  files, and it is labelled **inferred**, with both file names.

## Running it

```bash
kaleidophone doctor                                  # what each tool is, and what it runs as
kaleidophone doctor --bench-gate                     # exit 8 unless the Mac is quiet and on AC power
python benchmarks/run.py --suite quick               # every suite in miniature: a smoke test
python benchmarks/run.py --suite all --runs 3        # the baseline: hours, overnight
python benchmarks/run.py --suite canvas-knee --workers 1,2,4,6,8,10
python benchmarks/run.py --suite aac-vs-aac_at --private-master ~/path/to/masters
python benchmarks/run.py --suite loop-seam --private-reel ~/path/to/reel.mp4
```

`run.py` asks `kaleidophone doctor --bench-gate` first, and refuses (exit 8)
when the 1-minute load average is above 1, the Mac is on battery, or a check
fails. `--wait-quiet MINUTES` asks again every minute while the refusal is
load or battery: right after everything else is closed, the 1-minute average
takes a few minutes to fall. A failing check isn't waited on. `--ungated`
runs anyway for a smoke test (see the labels above), and its result goes to
the system's temporary folder unless `--out` says otherwise. A suite that
fails, or is interrupted with Ctrl-C, costs only that suite: the cases
already recorded are written. Mistyped `--private-master` and
`--private-reel` paths are refused before anything runs. The
code under test is the checkout `run.py` sits in: its `src/` is put first on
`PYTHONPATH`, and its `canvas/` tools are used. Fixtures are generated into a
temporary folder outside the repository and removed afterwards (`--work DIR
--keep` keeps them).

Before the first canvas run, the Chromium revision that `canvas/`'s
`playwright-core` launches must be installed (`kaleidophone doctor` says
whether it is): `cd canvas && npm ci && npx playwright-core install
chromium`. `KALEIDOPHONE_CHROMIUM` overrides it for a smoke test. A baseline
uses the pinned revision, the one CI and the gallery render with.

## `kaleidophone doctor`

`src/kaleidophone/doctor.py`. The doctor reads the CPU architecture from
each binary's own header (Mach-O or ELF), not from its name. It reads
`sysctl.proc_translated` for itself: under Rosetta 2, Python's
`platform.machine()` reports x86_64 on an arm64 Mac. It checks:

| Check | What it says |
|---|---|
| host | chip, performance and efficiency cores, memory, OS |
| python, ffmpeg, ffprobe, node | version, architecture, whether translated, which install (by prefix: `/opt/homebrew`, `/usr/local`, …) |
| path | whether `/usr/local/bin` comes before `/opt/homebrew/bin` (Intel tools shadowing native ones), and every copy of each tool on PATH |
| encoders | libx264 and aac (required), aac_at and h264_videotoolbox (reported) |
| node_modules, chromium | the Chromium revision `playwright-core` launches, whether it is installed, its architecture; `KALEIDOPHONE_CHROMIUM` if set |
| disk, write, filenames | free space, a write-fsync-unlink test, and whether `?` may be in a file name (one release title ends in one) |
| wav #N (`--wav`) | a master's size holds still for `--wav-wait` s and matches its RIFF/RF64/AIFF header: it isn't still being bounced or synced |
| power, load | AC or battery; the 1-minute load average |

Exit 0 means ready (warnings allowed), 2 means a check failed, and 8 means
the bench gate refused. `--json` holds no path, no host name and no user
name. WAVs are reported by number only (`wav #1`, not the file name).

## The suites

Each case is run `--runs` times (default 3). The result keeps every run, the
median of every number, and the profile of the median run.

### canvas-knee

**Asks:** how many workers before a canvas render stops getting faster, and
what each worker costs in memory on 16 GB.

Each frozen piece's synthetic twin, plus the template, renders 10 s at
1080x1920 from its `gallery.t0`, at `--workers` 1 to 10. The run order is
runs outermost, so drift over the night falls on every worker count alike.
A stateful piece renders in one worker whatever it is asked, and its other
counts are skipped and say why. Fields:

- `fps`: frames over the whole process, Chromium's start and the build
  included.
- `fps_render`: render.mjs's own rate, from Chromium's start.
- `peak_rss_mb`: node, Chromium and ffmpeg together, sampled once a second
  and never below the process's own kernel count. The sampler runs `ps`,
  which costs about 26 ms of CPU a sample on the reference Mac (measured). At
  4 Hz it took a tenth of a core from the render being measured. `rss_per_worker_mb` is that peak
  divided by the workers used.
- `draw_ms`, `capture_ms`, `sink_wait_ms`: per-frame means from `render.mjs
  --profile`.

The **knee** is the fewest workers within 5% of the best median fps (a
`derived` case). The default worker count in `render.mjs` (2) should be
changed to it, not to a guess.

### footage

**Asks:** what the filter-graph engine costs per resolution, what camera
photos add, and where a frame program spends its time.

- `examples/demo`'s edit (37 cuts; the case notes it if that changes) as
  `kaleidophone silent`, at 640x360 and 1280x720.
- The same edit with every photo replaced by a procedural 6000x4000 JPEG. A
  still is decoded for every frame it is on screen, so this case shows
  whether pre-fitting photos is worth it. That has only been inferred so far.
- A frame program (MemoryCanvas, GrainBank, feedback_echo) over the 720p
  render through `frames.engine.run_workers` at 1, 2 and 4 workers. Fields:
  `fps_render`, and `read_ms` / `program_ms` / `write_ms` per frame from the
  engine's own timings.

Every silent render runs with `KALEIDOPHONE_PROFILE`, so the case shows
which ffmpeg passes (by kind: `loop|vf|scale|noise|v=libx264`,
`filter_complex|…`, `concat|…`) take the time.

### deliver

**Asks:** what a release's delivery costs.

A synthetic master goes through `kaleidophone deliver`. It is generated, and
measured with ffmpeg 7.1's `ebur128` on three seeds of the 60 s fixture: -13.6
LUFS, sample peak -0.3 to -0.7 dBFS, and +0.5 to +0.8 dBTP once encoded to
AAC at 256k (measured). That is a hot master, so the true-peak guard has to
step. The delivery is one cut with 2 endings, to Instagram Reels, TikTok and
YouTube Shorts (6 files), at `gain: auto`. Fields:

- `wall_s`.
- `guard_rounds`: how many times the true-peak guard encoded everything.
- `audio_encode_ms` and `measure_ms`, from the profile.
- The delivered `true_peak_dbtp_max`, `lufs_mean` and `gain_db`, from the
  delivery's own manifest.

### aac-vs-aac_at

**Asks:** whether AudioToolbox's `aac_at` should replace ffmpeg's `aac`, on
time and on what is delivered.

The same delivery is run twice, once with each encoder: a film-length cut of
a synthetic master, plus every `--private-master`. `deliver.py` hard-codes
`-c:a aac` until deliver v2 makes the codec a setting, so for this suite only
the harness runs `deliver` through `suites.py deliver-codec`. That helper
swaps the codec in the encode argv and fails loudly if the argv no longer
reads `-c:a aac`. Fields: wall time, guard rounds, encode ms, and delivered
LUFS and true peak per codec. A `derived` case gives aac_at minus aac.

Private masters are linked into the work folder as `private-N.<ext>` before
anything reads them. A result names them only by number and keeps only
numbers (their length is rounded to 0.1 min). A failure on one records that
it failed, not why: the reason is printed to the terminal.

### loop-seam

**Asks:** what SSIM between a loop's last frame and its first tells a good
seam from a bad one. The answer sets the threshold for the loop check
planned for deliveries.

Four synthetic loops at 720x1280, 192 frames:

- `seamless`: the period is the loop.
- `drift`: 3% off.
- `cut`: a hard cut.
- `xfade`: drift with a 12-frame cross-fade.

Each `--private-reel` is measured the same way. Fields: `seam_ssim` (last
frame against the first), `interior_ssim` (the median of three ordinary
frame-to-frame steps), and `seam_over_interior`. Loops are deterministic,
so each is run once.

### long-form

**Asks:** whether a 23-minute song is just a longer 4-minute one.

- A 23-minute synthetic master through `kaleidophone envelope`: wall time,
  and peak RSS of the process and of the tree (the ffmpeg decode included).
- 60 s of the template rendered from that pack, at today's default of 2
  workers. Its `full_length_s` is **inferred**: the median wall time times
  23 min / 60 s.
- The delivery of the full 23 minutes against a 1080x1920 picture (a 10 s
  clip stream-copied to length): the guard loop at full length.

### quick

Every suite above in miniature: the template at 1 and 2 workers for 2 s,
the demo at 360p, 3 photos, a 20 s master, 2 loops, a 2-minute long form.
It runs once each, in under five minutes. It is a smoke test of the harness,
never a baseline.

## The result file: `kp-bench/1`

```text
schema          "kp-bench/1"
suite           the suite run ("all", "quick", ...)
created_utc     when, to the second
label           "measured", or "measured, ungated: not a baseline"
statistic       "median"; runs_per_case: N
kaleidophone    version, commit, dirty
toolchain_tag   "rosetta" if any tool runs translated, else the host's arch
toolchain       doctor's report: host, python, ffmpeg (with encoders), ffprobe, node, chromium
gate            doctor's bench gate, and whether it was overridden
cases[]         suite, case, label, params, runs[], median{}, profile_of_median_run, derived, notes
skipped[]       suite, case, reason
failed[]        suite, case, error (scrubbed)
wall_s          the whole run
```

**Hygiene.** Before a result is written, every string in it is checked.
That includes every key, so a profile keyed by something odd is caught too.
The check refuses an absolute, home-relative or Windows path, a relative
path two folders deep, the name of a media, data or sheet file (which can be
a song's), this machine's host names, the user name and the home folder.
Failure messages are scrubbed of the same things before they are recorded. The install
prefixes doctor names a tool by (`/opt/homebrew`, `/usr/local`, `/usr`) are
the only path-shaped strings allowed. A result that fails is not written:
`run.py` exits 3 and leaves it in the kept work folder to be fixed by hand.
`tests/test_benchmarks.py` tests the check, and the doctor's JSON is held to
the same rule (`tests/test_doctor.py`).

## The profiling hooks

They are useful outside the harness too:

- **`KALEIDOPHONE_PROFILE=run.jsonl kaleidophone …`**: every
  `run()`, `run_measure()` and `decode_f32le()` call in
  `render/_ffmpeg_util.py` appends `{"call", "kind", "wall_ms", "exit",
  "pid", "ts"}`. The `kind` is built from flags, codec names and a fixed
  list of filter names, never from a path or a title.
- **`node tools/render.mjs … --profile`**: the sidecar gains `profile`, with
  every frame's `[frame, draw, capture, sink_wait]` in ms and each column's
  mean, p50, p95 and max.
- **The frame engine's run log**: each part's log line ends `read X /
  program Y / write Z ms a frame`. `RenderResult` carries `read_s`,
  `program_s` and `write_s`.

## Tables

Every cell stays empty until a gated result fills it. Each filled row names
its result file.

### Toolchains

| | Rosetta 2 baseline | native arm64 |
|---|---|---|
| Result file | — | — |
| ffmpeg | — | — |
| Python | — | — |
| node | — | — |
| Chromium (playwright-core's) | — | — |

### Headline rows

| Suite | Case | Rosetta 2 | native | Ratio (inferred) |
|---|---|---|---|---|
| canvas-knee | knee, per piece (workers) | — | — | — |
| canvas-knee | fps at the knee, per piece | — | — | — |
| canvas-knee | peak RSS per worker | — | — | — |
| footage | demo 640x360 `silent` | — | — | — |
| footage | demo 1280x720 `silent` | — | — | — |
| footage | 24 MP photos 1280x720 `silent` | — | — | — |
| footage | frame program, fps at 1 / 2 / 4 workers | — | — | — |
| deliver | 3 platforms x 2 endings | — | — | — |
| aac-vs-aac_at | encode time, aac_at / aac | — | — | — |
| aac-vs-aac_at | delivered LUFS and dBTP, aac_at − aac | — | — | — |
| loop-seam | seam SSIM: seamless / drift / cut / xfade | — | — | — |
| long-form | `envelope`, 23 min: wall, peak RSS | — | — | — |
| long-form | 23 min render (inferred from 60 s) | — | — | — |
| long-form | deliver guard, 23 min | — | — | — |

The native switch must not move a picture or a level. Golden frames are
compared exactly on Linux CI. The Mac compares the picture by framemd5, and
compares the delivered LUFS and dBTP between the two baselines. The
difference across the switch goes here, measured, with both files named.
