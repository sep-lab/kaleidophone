# CLAUDE.md

See [AGENTS.md](AGENTS.md) — it is the canonical brief for AI agents working
on this repository, and it applies to Claude Code (and to a Claude session
in Cowork) as well.

Quick orientation:

- kaleidophone versions the **brief** (a YAML `CreativeBrief`), never the
  **render**. The EDL, silent video, master, teasers, thumbnails, and cover
  art are all derived and rebuildable — see
  [docs/decisions/0001-version-the-brief-not-the-render.md](docs/decisions/0001-version-the-brief-not-the-render.md).
- No real photo, video, or audio file is ever committed here — not as a test
  fixture, not "just one". Generate synthetic fixtures instead; see
  `examples/demo/generate_fixtures.py` for the pattern.
- `skills/` holds one `SKILL.md` per pipeline stage (audio analysis, asset
  curation, timeline composition, render, cover art, promo pack) — read the
  relevant one before working on that stage, whether you're a person or an
  agent.
- Every number in `docs/` must be reproducible. Label claims measured /
  cited / inferred, per AGENTS.md.
