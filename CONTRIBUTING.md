# Contributing to kaleidophone

Thanks for being here. This project turns a song and your own photos/clips
into a music video, cover art, and a promo pack — see the README for the
pitch and `AGENTS.md` for the ground rules (read that one regardless of
whether you're a person or an agent; it applies to both).

## Get oriented in 10 minutes

1. **[README.md](README.md)** — the pitch, the quick start, real numbers
   from the bundled demo.
2. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how a brief becomes a
   video: the pipeline stages and why the render step is split in two.
3. **[docs/decisions/](docs/decisions/)** — the five ADRs. Read
   [0001](docs/decisions/0001-version-the-brief-not-the-render.md) and
   [0002](docs/decisions/0002-deterministic-edit-engine.md) first; they
   explain the two choices everything else follows from.
4. **[docs/CREATIVE-GUIDE.md](docs/CREATIVE-GUIDE.md)** — the visual/sonic
   language (stations, effects, the AM/FM structure) in
   `docs/case-studies/love.md` this framework generalizes from.
5. **[docs/CONFIG-SCHEMA.md](docs/CONFIG-SCHEMA.md)** — the brief format, if
   you're about to write or edit one.

## Set up and run something real

```bash
git clone https://github.com/sep-lab/kaleidophone && cd kaleidophone
pip install -e ".[dev]"
```

Needs a system `ffmpeg` on PATH (`brew install ffmpeg` / `apt install
ffmpeg`) — kaleidophone shells out to it rather than depending on a Python video
library; see [ADR-0002](docs/decisions/0002-deterministic-edit-engine.md).

**See the whole pipeline run, no real media required:**

```bash
bash examples/demo/run_demo.sh
```

Generates a synthetic song and synthetic placeholder photos, then runs
`analyze -> compose -> preview -> render -> promo` for real. **Measured**
(24s @ 640x360, 37 cuts, Apple M1 Pro / macOS 15.7 / ffmpeg 7.1): 18.1s end
to end; **inferred** for a CI runner: roughly 30-60s. Note which of those two
is which -- the range is a guess, and this file's own rules say to say so.
This is the fastest way to find out whether a change broke anything that
touches `ffmpeg` -- `pytest` alone never calls it.

**Try it on your own song and photos** (never commit either — see
`AGENTS.md`):

```bash
kaleidophone auto ~/Music/your_song.mp3 ~/Pictures/some_folder -o /tmp/kaleidophone_out --preview-only
open /tmp/kaleidophone_out/preview_contact_sheet.jpg   # sanity-check the edit
kaleidophone run /tmp/kaleidophone_out/generated_brief.yaml -o /tmp/kaleidophone_out   # then render for real
```

## Ways to contribute that we especially want

**1. More effects.** `render/effects.py` is deliberately small, composable
filter-string builders — a new effect is one function plus a registry entry,
not a rewrite. See the module docstring for the linear-vs-graph-filter
split before adding one that uses `split`/named pads.

**2. Better auto-curation.** `assets/curation.py`'s hue/saturation/brightness
scorer is a first pass, honestly described as one in
[ADR-0004](docs/decisions/0004-default-mode-and-auto-curation.md). If you
have a photo library it curates badly, a failing test case built from
synthetic fixtures reproducing the failure mode is extremely welcome.

**3. A second worked case study.** `docs/case-studies/love.md` is the only
one so far. A second real project, written up with the same care taken to
scrub identifying details (see that doc's own notes on what was removed and
why), would do more to prove this framework generalizes than anything else
on the roadmap.

**4. Smarter auto-sectioning.** `timeline/autobrief.py`'s boundary picker
falls back to even slicing when a song hands back too many or too few
candidate boundaries — see its docstring and ROADMAP.md. Keeping the
*strongest* detected boundaries instead of discarding all of them is real,
tractable work.

**5. Adversarial review of the privacy guardrails.** If you can get a real
path or a media file past `check_no_personal_paths.py` /
`check_no_media.sh`, that's a report we want — see
[ADR-0003](docs/decisions/0003-public-framework-private-assets.md).

## Ground rules for claims

Like its sibling project [Wit](https://github.com/sep-lab/Wit), this repo's
docs make numeric claims (render times, file sizes, detection accuracy).
They must be reproducible:

- State how you measured a number and on what material — `examples/demo/`'s
  synthetic fixtures, or your own (never committed).
- Label **measured** / **cited** / **inferred**, and don't blur them.
- "Should be about" is inferred, not measured.

## Pull requests

1. Open an issue first for anything non-trivial.
2. Update the relevant doc in the same PR — undocumented behavior is a bug
   here, same as Wit.
3. If your change touches the render pipeline, run
   `bash examples/demo/run_demo.sh` and mention the result in the PR; `ruff`
   and `pytest` alone don't exercise `ffmpeg`.
4. If you change a number in `docs/`, include the command that produced it.

## Reporting bugs

Include your OS, ffmpeg version (`ffmpeg -version`), and Python version.
Never attach real media to an issue — describe it, or build a minimal
synthetic reproduction using `tests/factories/` or
`examples/demo/generate_fixtures.py`'s pattern.

## Security

Please don't open public issues for security problems — see
[SECURITY.md](SECURITY.md).

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

Contributions are licensed under [Apache 2.0](LICENSE), matching the
project.
