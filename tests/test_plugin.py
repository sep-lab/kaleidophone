"""
The Claude Code plugin manifest.

Nothing here talks to Claude Code -- it validates the structure the loader
requires, so a typo in a manifest fails in CI rather than at
`/plugin install` time on someone else's machine.

Why this file exists at all: `docs/PRIOR-ART.md` names the project's own
biggest risk as needing a user who "is comfortable in a terminal". The plugin
is the answer to that, which makes these manifests load-bearing for adoption
rather than a nicety.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
MARKET = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
COMMANDS = sorted((ROOT / "commands").glob("*.md"))
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path.name} has no YAML frontmatter"
    return yaml.safe_load(text.split("---", 2)[1])


# --------------------------------------------------------------------------
# manifests
# --------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["name", "description", "version"])
def test_plugin_manifest_has_the_required_fields(field):
    assert PLUGIN.get(field), f"plugin.json is missing {field}"


def test_the_plugin_name_is_kebab_case_and_matches_the_package():
    """The name is **immutable once published** -- it is how existing installs
    resolve. Renaming later orphans everyone who already installed it."""
    assert PLUGIN["name"] == "kaleidophone"
    assert re.fullmatch(r"[a-z0-9-]+", PLUGIN["name"])


def test_the_marketplace_lists_this_plugin_from_the_repo_root():
    assert MARKET["name"] and MARKET["owner"]["name"]
    entries = {p["name"]: p for p in MARKET["plugins"]}
    assert PLUGIN["name"] in entries, "the marketplace does not list its own plugin"
    assert entries[PLUGIN["name"]]["source"] == ".", "repo root is the plugin source"


def test_the_marketplace_name_is_not_reserved():
    """Names that impersonate an official Anthropic source are refused at load
    time, and a marketplace that stops loading is indistinguishable from a
    broken one."""
    reserved = {
        "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
        "claude-plugins-community", "claude-community", "anthropic-marketplace",
        "anthropic-plugins", "agent-skills", "anthropic-agent-skills",
        "knowledge-work-plugins", "first-party-plugins", "healthcare",
    }
    assert MARKET["name"] not in reserved
    assert "anthropic" not in MARKET["name"] and "official" not in MARKET["name"]


def test_the_plugin_version_matches_the_package_version():
    """Two version numbers that drift are worse than one, because the mismatch
    is invisible until someone reports a bug against the wrong one."""
    import kaleidophone
    assert PLUGIN["version"] == kaleidophone.__version__
    entry = next(p for p in MARKET["plugins"] if p["name"] == PLUGIN["name"])
    assert entry["version"] == kaleidophone.__version__


# --------------------------------------------------------------------------
# the prefix the commands answer to
# --------------------------------------------------------------------------
# Claude Code namespaces a plugin's commands and skills by the plugin's name. Measured 2026-10-07
# with `claude --plugin-dir .` (Claude Code 2.1.289): the session listed `kaleidophone:brief` ...
# `kaleidophone:release` and `kaleidophone:kaleidophone-<skill>`. The docs said `/kaleido:` until
# then, which no installed copy ever answered to.
PREFIX = "/kaleidophone:"


def test_the_documented_prefix_is_the_plugin_name():
    """Renaming the plugin would change every command; this makes that loud."""
    assert PREFIX == f"/{PLUGIN['name']}:"


def namespaced(text: str) -> set[tuple[str, str]]:
    """Every `/<namespace>:<name>` in a text, outside URLs and paths."""
    return set(re.findall(r"(?<![\w/.:-])/([a-z][a-z0-9-]*):([a-z][a-z0-9-]*)", text))


def test_every_documented_command_uses_the_prefix_and_exists():
    from tests.repo_files import live_lines, tracked_markdown

    names = {p.stem for p in COMMANDS} | {p.parent.name for p in SKILLS}
    wrong = []
    for path in tracked_markdown():
        text = "\n".join(line for _, line in live_lines(path, path.read_text(encoding="utf-8")))
        for ns, name in sorted(namespaced(text)):
            if ns != PLUGIN["name"] and name in names:
                wrong.append(f"{path.relative_to(ROOT)}: /{ns}:{name} -- Claude Code shows it as {PREFIX}{name}")
            elif ns == PLUGIN["name"] and name not in names:
                wrong.append(f"{path.relative_to(ROOT)}: {PREFIX}{name} -- no such command or skill")
    assert not wrong, "\n".join(wrong)


def test_the_prefix_scan_reads_commands_and_leaves_urls_alone():
    text = "Run `/kaleido:direct`, then /kaleidophone:piece; see https://example.com/a:b and C:/x:y."
    assert namespaced(text) == {("kaleido", "direct"), ("kaleidophone", "piece")}


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def test_there_are_commands_at_all():
    assert COMMANDS, "commands/ is empty -- the plugin would install and do nothing"


# Claude Code's model aliases (code.claude.com/docs/en/model-config, checked 2026-10-01). A command
# that pins one of these runs on it when the account has it; when it doesn't, Claude Code ignores
# the pin and the command runs on the session's model -- so a pin is a recommendation, not a lock.
MODEL_ALIASES = {"default", "best", "fable", "opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]", "opusplan"}


@pytest.mark.parametrize("path", COMMANDS, ids=lambda p: p.stem)
def test_a_pinned_model_is_an_alias_not_a_dated_model_id(path):
    """An alias keeps working when the next model ships; a full model ID would pin this plugin to
    one model forever, and a typo would silently fall back to the session model."""
    model = frontmatter(path).get("model")
    if model is not None:
        assert model in MODEL_ALIASES, f"{path.name} pins model {model!r}; use one of {sorted(MODEL_ALIASES)}"


def test_the_long_creative_commands_ask_for_the_best_model():
    """Directing an edit, building a canvas piece and running a whole release are the hours-long,
    many-tool jobs; README.md "Which model" says why they ask for `best`."""
    pinned = {p.stem: frontmatter(p).get("model") for p in COMMANDS}
    assert {k for k, v in pinned.items() if v == "best"} == {"direct", "piece", "release"}


@pytest.mark.parametrize("path", COMMANDS, ids=lambda p: p.stem)
def test_every_command_has_a_description(path):
    """The description is what a user sees in the command list; without one the
    command is undiscoverable even once installed."""
    fm = frontmatter(path)
    assert fm.get("description"), f"{path.name} has no description"
    assert len(fm["description"]) < 200, "keep it to one line"


@pytest.mark.parametrize("path", COMMANDS, ids=lambda p: p.stem)
def test_no_command_promises_to_post_anything(path):
    """ADR-0006 draws the line at generating files. A command that told Claude
    to publish would route around a boundary the code cannot enforce on prose."""
    body = path.read_text().lower()
    for phrase in ("post it to", "upload to instagram", "publish to", "tweet"):
        assert phrase not in body, f"{path.name} appears to promise posting: {phrase!r}"


def subcommands_in(text: str) -> set[str]:
    """Every `kaleidophone <sub>` named in a file's code spans and fenced blocks.

    Only code is scanned: the plugin's prose says things like "kaleidophone
    generates release files", and treating that as a subcommand reference is a
    false positive, not a finding. Subcommands can be hyphenated
    (`master-check`), so a name runs on through hyphens -- `\\w+` alone read
    `kaleidophone master-check` as `master` and failed a correct command. It
    must start with a word character, so `kaleidophone --version` is a flag,
    not a subcommand called `--version`."""
    code = "\n".join(
        re.findall(r"^```.*?^```", text, re.S | re.M) + re.findall(r"`([^`\n]+)`", text)
    )
    return set(re.findall(r"\bkaleidophone (\w[\w-]*)", code))


@pytest.mark.parametrize("path", COMMANDS + SKILLS, ids=lambda p: p.stem if p.stem != "SKILL" else p.parent.name)
def test_every_command_references_a_real_cli_subcommand(path):
    """Commands and skills are prose, so nothing else catches an invented
    subcommand -- and a skill that names one is followed just as literally."""
    from kaleidophone.cli import _build_parser
    known = set(_build_parser()._subparsers._group_actions[0].choices)
    unknown = subcommands_in(path.read_text()) - known
    assert not unknown, f"{path.name} references non-existent subcommands: {sorted(unknown)}"


def test_the_subcommand_scan_reads_a_hyphenated_name_whole():
    text = "Check first: `kaleidophone master-check old.wav new.wav`, then `kaleidophone --version`."
    assert subcommands_in(text) == {"master-check"}


# --------------------------------------------------------------------------
# skills
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_has_name_and_description_frontmatter(path):
    fm = frontmatter(path)
    assert fm.get("name") == path.parent.name, "skill name must match its directory"
    assert fm.get("description"), f"{path.parent.name} has no description"


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_description_says_when_to_use_it(path):
    """A description that only says what a skill *is* does not trigger. The
    ones here are meant to say when to reach for them."""
    d = frontmatter(path)["description"].lower()
    assert "use " in d or "when " in d, f"{path.parent.name}'s description has no trigger"


def test_the_creative_direction_skill_carries_the_text_rule():
    """It is the rule most likely to be got wrong, and the one that separates
    this from a slideshow generator."""
    body = (ROOT / "skills" / "kaleidophone-creative-direction" / "SKILL.md").read_text()
    assert "describe nothing, inhabit something" in body.lower()
    assert "diegetic" in body.lower()
