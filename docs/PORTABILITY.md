# No tokens, no network, another agent

kaleidophone's engines are deterministic code; an AI agent directs them. So
when the tokens run out, the network goes, or you use a different agent, most
of a release still gets made — the part that needs taste or new code is what
changes hands. This page says exactly which part, and how to run the rest.

Facts about other tools and models were checked on 2026-10-01 against their own
documentation (linked); they change, so check before relying on one.

## What runs with no AI at all

Everything below is a command, not a conversation. It runs on your machine,
needs no account and, once installed, no network.

| Job | Command | What you get |
|---|---|---|
| Analyse a song | `kaleidophone envelope Song.wav -o song.songpack.json` (`--midi`, `--stem` for a session) | the song pack every engine reads |
| A new master? | `kaleidophone master-check old.wav new.wav` | remux / offset / re-render these bars / new grid |
| A video from footage | `kaleidophone auto Song.wav ./photos -o out/` | a brief written for you, a contact sheet, the render, a cover, a promo pack |
| A drawn piece | `node tools/render.mjs <piece> --song song.songpack.json …` (in `canvas/`) | any shipped piece or the template, rendered to a new song; `--endings` for every ending |
| Covers | `kaleidophone cover brief.yaml`, `node tools/still.mjs <piece> --cover all` | a procedural cover, or a piece's own covers |
| Every platform's file | `kaleidophone deliver delivery.yaml` (`platforms:`, `covers:`) | reels, stories, Shorts, the Canvas, the YouTube cut, every cover size, a manifest |
| Captions | `kaleidophone kit brief.yaml` or `kaleidophone kit --song Song.wav --title "…" --concept "…" --lang en,fa` | every chapter, timestamp, credit and posting step — with the voice left for you |

What still needs someone with taste — you, or an agent:

- **The concept**, and a **new canvas piece** (code). Without an agent, start
  from `canvas/pieces/template` or render an existing piece to the new song.
- **The voice of the captions.** `kit` writes the facts and leaves the voice
  blank on purpose. A local model can draft it (next section).
- **Judgement calls** — which ending, which cover, whether a crop works.

## Captions from a model on your own machine

`kaleidophone kit … --llm ollama:<model>` asks a model running on your computer
([Ollama](https://docs.ollama.com/api/chat)) for one caption per platform, in your
primary language and, with `--lang en,fa` or `release.secondary_language`, a mirror
in the second. Nothing leaves the machine, and no tokens are spent: it talks to
`127.0.0.1:11434` unless you pass `--llm-host` (an `http://` or `https://` URL; it
says so on stderr when that is another machine), and goes straight there — never
through a proxy your environment names (Python's own `urlopen` would use one even for
`127.0.0.1`, unless `no_proxy` lists it). The request is seeded and schema-constrained,
and gives the model the concept, the mood words, the chapters, the biggest change and
the date — not the length or the tempo, which only invite filler. The drafts land in
the pack under their own heading, labelled as drafts:

- the model is told to keep the title and the artist name exactly as given, in their
  own script;
- a draft that breaks its rules anyway — an emoji, a `#`, an `@`, an exclamation
  mark, a link — is flagged under it, not removed;
- a Persian draft has Arabic `ي`/`ك` written as Persian `ی`/`ک`, and each run of
  Latin script in it isolated (U+2068 … U+2069), so a title like "SHOULD I ?" keeps
  its question mark where it belongs in right-to-left text.

If the server is missing, isn't Ollama or answers with something else, the pack is
written without drafts and `kit` says why in one line.

```bash
# once: install Ollama from https://ollama.com, then
ollama pull qwen3:8b
kaleidophone kit --song Song.wav --title "SONG" --concept "the one line it's about" \
  --lang en,fa --llm ollama:qwen3:8b -o release_pack.md
```

Which model, for Persian and English — there is no benchmark for short creative
Persian writing, so try two or three on your own captions:

| Model | Size to download | Persian | Licence |
|---|---|---|---|
| [`qwen3:8b`](https://ollama.com/library/qwen3) | 5.2 GB | listed among its 119 languages ([Qwen](https://qwenlm.github.io/blog/qwen3/)) | Apache 2.0 |
| [`gemma3:12b`](https://ollama.com/library/gemma3) | 8.1 GB | "140+ languages", Persian not named | Gemma terms |
| [`aya-expanse:8b`](https://ollama.com/library/aya-expanse) | 5.1 GB | listed among its languages | CC-BY-NC: non-commercial only |
| [`partai/dorna-llama3:8b-instruct-q4_0`](https://ollama.com/partai/dorna-llama3:8b-instruct-q4_0) | 4.7 GB | a Persian fine-tune | Llama licence |

On published Persian benchmarks the open models sit well behind the frontier ones
([2025 study](https://arxiv.org/abs/2510.12807),
[NAACL 2025](https://aclanthology.org/2025.findings-naacl.147.pdf)), so read every
Persian line aloud before posting. Ollama's own guidance is about 8 GB of RAM for a
7B model and 16 GB for 13B ([README](https://github.com/ollama/ollama/blob/v0.5.7/README.md)).

## Another agent

The repository is written for any coding agent, not only Claude Code:

- **[AGENTS.md](../AGENTS.md)** is the brief. It is read directly by
  [Codex](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
  [GitHub Copilot](https://docs.github.com/en/copilot/reference/custom-instructions-support)
  (the cloud agent, the CLI and VS Code), [Cursor](https://cursor.com/docs/rules) and
  [Jules](https://jules.google/docs/), among [others](https://agents.md/).
  [Gemini CLI](https://geminicli.com/docs/cli/gemini-md/) reads `GEMINI.md` by default;
  the repository's `.gemini/settings.json` points it at `AGENTS.md`.
  [Aider](https://aider.chat/docs/usage/conventions.html): `aider --read AGENTS.md`.
- **The skills** (`skills/<name>/SKILL.md`) follow the open
  [Agent Skills](https://agentskills.io/) format and use only its portable fields
  (`name`, `description`). `.agents/skills` links to them, which is where
  [Codex](https://learn.chatgpt.com/docs/build-skills),
  [Gemini CLI](https://geminicli.com/docs/cli/skills/),
  [Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) and
  [Cursor](https://cursor.com/docs/context/skills) look; Claude Code loads them through
  the plugin.
- **The slash commands** (`/kaleidophone:piece`, `/kaleidophone:deliver`, …) are Claude Code's.
  Elsewhere, ask in words: "follow `skills/kaleidophone-canvas-piece` to make a piece
  for Song.wav" does the same job, because the commands only point at the skills.

## A fully local agent

An agent can run on a local model too, for when the work is a re-run rather than
new code:

- **Claude Code** against a local model: Ollama's Anthropic-compatible API
  (`ollama launch claude`, [docs](https://docs.ollama.com/integrations/claude-code)) or
  any endpoint through `ANTHROPIC_BASE_URL`
  ([docs](https://code.claude.com/docs/en/env-vars)).
- **Codex CLI**: `codex --oss --local-provider ollama -m <model>`
  ([docs](https://docs.ollama.com/integrations/codex); it wants a 64k context).
- **Aider**: `aider --model ollama_chat/<model>` ([docs](https://aider.chat/docs/llms/ollama.html)).
- **Gemini CLI** can't yet: a local model only handles its model-routing step
  ([docs](https://geminicli.com/docs/cli/model-routing/)).

A local 8–20B model can drive the commands in the first table and draft captions.
Inferred, not measured: it won't write a new canvas piece or run a three-seat review
the way the frontier models do — keep those for when the tokens are back.

## Which model, when there are tokens

See [README.md, "Which model"](../README.md#which-model). In short: the long creative
commands (`/kaleidophone:direct`, `/kaleidophone:piece`, `/kaleidophone:release`) ask Claude Code for
`best`, which is Fable where your plan has it and Opus otherwise; everything else runs
on the model you chose, and re-runs are fine on Sonnet.
