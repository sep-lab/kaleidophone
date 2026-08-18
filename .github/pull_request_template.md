## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

From [CONTRIBUTING.md](https://github.com/sep-lab/kaleidophone/blob/main/CONTRIBUTING.md):

- [ ] The relevant doc is updated in this same PR — undocumented behavior is a bug here.
- [ ] If this touches the render pipeline, I ran `bash examples/demo/run_demo.sh`
      and mentioned the result below. `ruff` and `pytest` alone never call ffmpeg.
- [ ] If this changes a number in `docs/`, the command that produced it is included.
- [ ] Numeric claims are labelled **measured**, **cited**, or **inferred** — not blurred.
- [ ] No real photo, audio, or video is added, and no absolute personal path
      (`/Users/...`, `/home/...`) appears in any file. CI enforces both.

## Demo run

<!-- If you touched render/: paste the result. Otherwise write "not applicable". -->
