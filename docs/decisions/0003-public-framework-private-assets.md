# ADR-0003: Public framework, private assets, CI-enforced

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

This repository is meant to go public. It also exists specifically to
process someone's personal photos, home videos, and unreleased music —
about as sensitive a category of "your own data" as there is. Those two
facts have to coexist without relying on anyone remembering to be careful
by hand, on every commit, forever.

[Wit](https://github.com/sep-lab/Wit), this project's sibling, faced the
same shape of problem for DAW projects and solved it with policy plus CI
enforcement rather than policy alone. This ADR adopts the same approach.

## Decision

**The framework — code, skills, docs, schemas, tests, the CLI — is public.
Nobody's actual photos, video, audio, or release plans ever enter the
repository, and CI refuses commits that would violate that, not just the
`.gitignore`.**

Concretely:

1. `.gitignore` blocklists every audio/video/image extension mvideo works
   with, plus `private/`, `local/`, `*.local.yaml` for real briefs that
   point at real folders.
2. `examples/` ships only two kinds of brief: fully synthetic
   (`examples/demo/`, generated at run time, never committed) and
   genericized case studies with identifying details removed
   (`examples/love/` — see `docs/case-studies/love.md` for what was scrubbed
   and why).
3. CI (`.github/workflows/ci.yml`, job `guardrails`) runs
   `check_no_media.sh` (extension + size blocklist, adapted from Wit's
   `check_no_binaries.sh`) and `check_no_personal_paths.py` (refuses
   absolute home-directory paths in any tracked file, reused from Wit
   almost verbatim — the risk it guards against, a real path leaking a real
   username and folder structure, isn't specific to DAW files).
4. Docs and briefs use placeholders (`/path/to/your/photos`, `~/Music/...`)
   never a real path from anyone's machine.

## Consequences

**Good**

- "Did we just commit someone's vacation photos" stops being a
  code-review judgment call and becomes a CI failure with a specific,
  actionable error message.
- Case studies can be genuinely detailed (real BPM, real timestamps, real
  station structure) without carrying real names, handles, or file paths —
  the technique is the shareable part, not the personal content it was
  demonstrated on.

**Bad, and accepted**

- Every contributor's test fixtures have to be synthetic (see
  `examples/demo/generate_fixtures.py`), which is more setup than "just
  commit a sample photo" would be.
- The size/extension blocklist needs updating if mvideo starts reading a
  new media format — a blocklist only catches what someone thought to list
  (mirrors the same tradeoff Wit's `check_no_binaries.sh` documents).

## What would overturn this

- If mvideo ever needs a *repository* of shared, non-personal sample media
  (e.g. licensed stock footage for a public demo), that's a deliberate,
  reviewed exception with its own storage decision — not a reason to loosen
  this policy generally.

## Related

`.gitignore`, `.github/workflows/scripts/check_no_media.sh`,
`.github/workflows/scripts/check_no_personal_paths.py`, `AGENTS.md`,
`docs/case-studies/love.md`.
