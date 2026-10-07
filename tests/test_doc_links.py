"""
Every relative link in the docs goes somewhere.

The docs cross-reference each other heavily (TECHNIQUES.md entries by anchor,
ADRs by file name, case studies from three places), and a renamed heading or a
moved file breaks those links silently: GitHub renders a dead link exactly
like a live one. This walks every tracked Markdown file and checks that each
relative link, `href` and `src` names a file or folder that is in the
repository, and that a `#fragment` names a heading (or an explicit anchor)
in its target.

Links to the web are not fetched: the tests never touch the network
(ADR-0006).
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from functools import cache
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]


@cache
def tracked() -> frozenset[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:  # pragma: no cover - CI always has git
        pytest.skip(f"not a git checkout: {e}")
    return frozenset(f for f in out.split("\0") if f)


def tracked_dirs() -> set[str]:
    dirs = set()
    for f in tracked():
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return dirs


DOCS = sorted(f for f in tracked() if f.endswith(".md")) if (ROOT / ".git").exists() else []


def without_fences(text: str) -> str:
    """The text with fenced code blocks blanked, line numbers kept."""
    return re.sub(r"^(```|~~~).*?^\1[^\n]*$", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S | re.M)


def without_code(text: str) -> str:
    """The text with fenced blocks and inline code blanked, line numbers kept:
    a link inside code is an example, not a link."""
    return re.sub(r"`[^`\n]*`", "", without_fences(text))


LINK = re.compile(
    r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)"  # [text](target "title")
    r"|^\s*\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)"  # [ref]: target
    r"|\b(?:href|src)=\"([^\"]+)\"",  # raw HTML
    re.M,
)


def links(text: str):
    """(line number, target) for every link in a Markdown text."""
    for m in LINK.finditer(without_code(text)):
        target = next(g for g in m.groups() if g is not None)
        yield text.count("\n", 0, m.start()) + 1, target


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: the rendered text, lower-cased, with
    punctuation and symbols dropped and each space made a hyphen."""
    h = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # [text](url) -> text
    h = re.sub(r"<[^>]+>", "", h).replace("`", "").strip().lower()
    h = re.sub(r"(?<!\w)[*_]+|[*_]+(?!\w)", "", h)  # emphasis markers, not snake_case
    return "".join(c for c in h if c in " -_" or unicodedata.category(c)[0] in "LNM").replace(" ", "-")


@cache
def anchors(rel: str) -> frozenset[str]:
    """Every anchor a Markdown file defines: its headings' slugs (repeats get
    -1, -2, ... as on GitHub) and any explicit id= / name=."""
    text = without_fences((ROOT / rel).read_text(encoding="utf-8"))  # a heading's `code` is in its slug
    seen: dict[str, int] = {}
    out = set()
    for h in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        s = slug(h)
        n = seen.get(s, 0)
        out.add(s if n == 0 else f"{s}-{n}")
        seen[s] = n + 1
    out.update(re.findall(r"<a\s+(?:id|name)=\"([^\"]+)\"", text))
    return frozenset(out)


def problem(doc: str, target: str) -> str | None:
    """Why a link from `doc` to `target` is broken, or None if it isn't."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("//"):
        return None  # http:, https:, mailto: -- not ours to check
    path, _, frag = target.partition("#")
    path = unquote(path.split("?", 1)[0])
    if path.startswith("/"):
        return "an absolute path: GitHub resolves it against the site, not the repository; make it relative"
    if path:
        resolved = (ROOT / doc).parent.joinpath(path).resolve()
        try:
            rel = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            return "points outside the repository"
        if rel not in tracked() and rel not in tracked_dirs():
            return f"{rel} is not in the repository"
    else:
        rel = doc
    if frag and rel.endswith(".md") and unquote(frag).lower() not in anchors(rel):
        return f"{rel} has no heading or anchor #{frag}"
    return None


@pytest.mark.parametrize("doc", DOCS)
def test_every_relative_link_resolves(doc):
    text = (ROOT / doc).read_text(encoding="utf-8")
    broken = [f"{doc}:{no}: {target} -- {why}" for no, target in links(text) if (why := problem(doc, target))]
    assert not broken, "broken links:\n" + "\n".join(broken)


def test_there_are_docs_to_check():
    assert "README.md" in DOCS and "docs/TECHNIQUES.md" in DOCS


# --------------------------------------------------------------------------
# the checker itself
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("1. Window reveal", "1-window-reveal"),
        ("55. Session in: MIDI and stems", "55-session-in-midi-and-stems"),
        ("Private pieces: `KALEIDOPHONE_PIECES`", "private-pieces-kaleidophone_pieces"),
        ("What's **not** in it", "whats-not-in-it"),
        ("The [ADR](x.md) index", "the-adr-index"),
    ],
)
def test_headings_slug_the_way_github_does(heading, anchor):
    assert slug(heading) == anchor


def test_the_checker_finds_each_kind_of_broken_link():
    text = (
        "[gone](docs/no-such-file.md) and [anchor](docs/TECHNIQUES.md#999-no-such-technique)\n"
        '<img src="docs/missing.png"> [up](../outside.md) [abs](/docs/TECHNIQUES.md)\n'
        "[ref]: docs/also-missing.md\n"
        "`[in code](nope.md)` and the web: [w](https://example.invalid/x.md)\n"
    )
    found = {target: problem("README.md", target) for _, target in links(text)}
    assert set(found) == {
        "docs/no-such-file.md",
        "docs/TECHNIQUES.md#999-no-such-technique",
        "docs/missing.png",
        "../outside.md",
        "/docs/TECHNIQUES.md",
        "docs/also-missing.md",
        "https://example.invalid/x.md",
    }
    assert found.pop("https://example.invalid/x.md") is None
    assert all(found.values()), found


def test_the_checker_passes_a_good_link():
    assert problem("README.md", "docs/TECHNIQUES.md#1-window-reveal") is None
    assert problem("docs/case-studies/README.md", "../TECHNIQUES.md") is None
    assert problem("README.md", "canvas/") is None
    assert problem("README.md", "#documentation") is None
