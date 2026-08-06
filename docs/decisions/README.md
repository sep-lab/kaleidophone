# Architecture decision records

One file per decision: the context, the decision, the consequences, and —
importantly — **what evidence would overturn it.**

| # | Decision | Status |
|---|---|---|
| [0001](0001-version-the-brief-not-the-render.md) | Version the brief, not the render | Accepted |
| [0002](0002-deterministic-edit-engine.md) | A deterministic edit engine, not AI-generated pixels | Accepted |
| [0003](0003-public-framework-private-assets.md) | Public framework, private assets, CI-enforced | Accepted |
| [0004](0004-default-mode-and-auto-curation.md) | A default mode backed by heuristic curation, not a wizard | Accepted |
| [0005](0005-project-naming.md) | Project naming | Proposed |

These are settled except where marked otherwise. Reopening one is welcome, but
bring the evidence its "What would overturn this" section asks for — that is
what the section is for.

New ADRs: copy the structure of an existing one, take the next number, and
link it here and from [AGENTS.md](../../AGENTS.md) if it constrains how
agents should work.
