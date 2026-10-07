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
- There are three engines (ADR-0007): filter graphs (`src/kaleidophone/render/`),
  frame programs (`src/kaleidophone/frames/`), canvas pieces (`canvas/`, see
  `canvas/README.md`). One contract: song pack in (`kaleidophone envelope`),
  deterministic silent render, audio muxed and measured last
  (`kaleidophone deliver`); `kaleidophone master-check` before re-rendering for
  a new master.
- `docs/TECHNIQUES.md` numbers every technique the real releases taught and
  says where it lives. Read it before inventing something.
- `skills/` holds one `SKILL.md` per stage: audio analysis, asset curation,
  timeline composition, render, cover art, promo pack, creative direction, and
  (0.3) canvas piece, release kit, master swap, footage effects. Read the
  relevant one before working on that stage, whether you're a person or an
  agent.
- The shipped canvas pieces are frozen (verified against their releases);
  new canvas work starts from `canvas/pieces/template` and `canvas/lib/`. Real
  song packs, lyrics and collaborator names never enter the repository.
- Every number in `docs/` must be reproducible. Label claims measured /
  cited / inferred, per AGENTS.md.
