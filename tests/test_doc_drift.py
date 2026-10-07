"""
Counts the docs repeat, checked against the things they count.

A number in prose -- "55 techniques", "#1–#54", "the four shipped pieces" -- is
right the day it is written and wrong the day the next release lands. The docs
mostly say these things without a count now; where one does give a count, this
file holds it to the truth, and every table that lists the pieces to the
folders in `canvas/pieces/`.

History is exempt. A released CHANGELOG section and a checked-off ROADMAP item
say what was true then, and rewriting them would be the drift.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TECHNIQUES = ROOT / "docs" / "TECHNIQUES.md"
PIECES = ROOT / "canvas" / "pieces"
DECISIONS = ROOT / "docs" / "decisions"

WORDS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
NUMBER = r"(\d+|" + "|".join(WORDS) + r")"


def as_int(word: str) -> int:
    return int(word) if word.isdigit() else WORDS[word.lower()]


def tracked_markdown() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:  # pragma: no cover - CI always has git
        pytest.skip(f"not a git checkout: {e}")
    return [ROOT / f for f in out.split("\0") if f]


def live_lines(path: Path, text: str):
    """(line number, line) for every line that describes the present.

    Skipped: CHANGELOG.md from its first released section on, and any
    checked-off list item (`- [x] ...`), which records what shipped."""
    for no, line in enumerate(text.splitlines(), 1):
        if path.name == "CHANGELOG.md" and re.match(r"## \[\d", line):
            return
        if re.match(r"\s*[-*] \[x\]", line, re.I):
            continue
        yield no, line


def live_text_of_every_doc():
    for path in tracked_markdown():
        yield path, list(live_lines(path, path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# TECHNIQUES.md
# --------------------------------------------------------------------------
def technique_numbers() -> list[int]:
    return [int(n) for n in re.findall(r"^#{2,4} (\d+)\. ", TECHNIQUES.read_text(encoding="utf-8"), re.M)]


def technique_drift(line: str, count: int) -> list[str]:
    """What in one line of prose disagrees with TECHNIQUES.md's count.

    Two shapes: a range from the first technique ("#1–#54", "#1-54",
    "#1 to #54", on a line about techniques -- "#2–#4" Dependabot PRs aren't),
    and a count on a line that names the file ("[TECHNIQUES.md] -- 55
    techniques"); "this release taught three techniques" is a different count."""
    found = []
    if re.search(r"techni", line, re.I):
        for m in re.finditer(r"(?<![\w#])#1\s*(?:[–—-]|to)\s*#?(\d+)\b", line):
            if int(m.group(1)) != count:
                found.append(f"{m.group(0)!r} but TECHNIQUES.md numbers #1–#{count}")
    for m in re.finditer(rf"\b{NUMBER} techniques\b", line, re.I):
        if "TECHNIQUES" in line and as_int(m.group(1)) != count:
            found.append(f"{m.group(0)!r} but TECHNIQUES.md has {count}")
    return found


def test_techniques_are_numbered_once_each_with_no_gap():
    """The case studies and release notes cite techniques by number, so a
    number used twice or skipped breaks every citation after it."""
    nums = technique_numbers()
    assert nums, "no '### N. Title' headings found in docs/TECHNIQUES.md"
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    assert not dupes, f"technique numbers used twice: {dupes}"
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
    assert not missing, f"technique numbers skipped: {missing}"


def test_every_count_of_the_techniques_matches_the_headings():
    count = len(technique_numbers())
    stale = [
        f"{path.relative_to(ROOT)}:{no}: {msg}"
        for path, lines in live_text_of_every_doc()
        for no, line in lines
        for msg in technique_drift(line, count)
    ]
    assert not stale, "a doc counts the techniques wrong (say it without a count, or fix it):\n" + "\n".join(stale)


@pytest.mark.parametrize(
    "line",
    [
        "Technique numbers (#1–#99) refer to TECHNIQUES.md.",
        "techniques #1-#99",
        "See the techniques, #1 to #99.",
        "[docs/TECHNIQUES.md](docs/TECHNIQUES.md) — 99 techniques from real releases,",
        "TECHNIQUES.md: twelve techniques, numbered",
    ],
)
def test_the_drift_check_catches_a_wrong_count(line):
    """The check itself, on a count no doc will ever reach."""
    assert technique_drift(line, 55)


@pytest.mark.parametrize(
    "line",
    [
        "Technique numbers (#N) refer to TECHNIQUES.md.",
        "Actions bumped (Dependabot #2–#4).",
        "[#6](../TECHNIQUES.md#6-red-thread-grade)–[#11](../TECHNIQUES.md#11-outro-splice)",
        "see [window reveal](../TECHNIQUES.md#1-window-reveal), a technique",
        "TECHNIQUES.md has 55 techniques",
        "the release taught three techniques",
    ],
)
def test_the_drift_check_leaves_the_right_ones_alone(line):
    assert technique_drift(line, 55) == []


def test_history_is_exempt_from_the_count(tmp_path):
    log = tmp_path / "CHANGELOG.md"
    log.write_text("# Changelog\n\n## [Unreleased]\n\nnow\n\n## [0.3.0]\n\n- 54 techniques\n")
    assert [line for _, line in live_lines(log, log.read_text())] == ["# Changelog", "", "## [Unreleased]", "", "now", ""]
    roadmap = tmp_path / "ROADMAP.md"
    assert list(live_lines(roadmap, "- [x] Five ADRs\n- [ ] Eight ADRs\n")) == [(2, "- [ ] Eight ADRs")]


# --------------------------------------------------------------------------
# the pieces
# --------------------------------------------------------------------------
def pieces() -> dict[str, dict]:
    return {
        d.name: json.loads((d / "piece.json").read_text(encoding="utf-8"))
        for d in sorted(PIECES.iterdir())
        if (d / "piece.json").is_file()
    }


def works() -> dict[str, dict]:
    """The pieces that are releases, not templates to start from."""
    return {k: v for k, v in pieces().items() if (v.get("gallery") or {}).get("role", "piece") != "template"}


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"no '## {heading}' section"
    return m.group(1)


def test_the_canvas_readme_has_a_row_for_every_piece_and_no_other():
    rows = re.findall(
        r"^\|\s*\[[^\]]+\]\(pieces/([\w-]+)/?\)",
        section((ROOT / "canvas" / "README.md").read_text(encoding="utf-8"), "The pieces"),
        re.M,
    )
    assert sorted(rows) == sorted(pieces()), (
        f"canvas/README.md 'The pieces' lists {sorted(rows)}; canvas/pieces/ holds {sorted(pieces())}"
    )


def test_the_readme_gallery_shows_every_work_with_its_own_alt_text():
    """canvas/README.md: "The README's table of clips repeats each `alt`:
    change both together." This is what holds them together."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cells = dict(
        re.findall(r'href="https://sep-lab\.github\.io/kaleidophone/pieces/([\w-]+)\.html".*?alt="([^"]*)"', readme)
    )
    assert sorted(cells) == sorted(works()), f"README.md's clips show {sorted(cells)}; the works are {sorted(works())}"
    for pid, spec in works().items():
        alt = (spec.get("gallery") or {}).get("alt")
        assert html.unescape(cells[pid]) == alt, f"README.md's alt for {pid} differs from its piece.json gallery.alt"


def test_every_count_of_the_shipped_pieces_matches_the_folders():
    count = len(works())
    stale = [
        f"{path.relative_to(ROOT)}:{no}: {m.group(0)!r}, but canvas/pieces/ holds {count}"
        for path, lines in live_text_of_every_doc()
        for no, line in lines
        # "the four shipped pieces" counts all of them; "three shipped pieces put text outside it" doesn't
        for m in re.finditer(rf"\b(?:the|all) {NUMBER} (?:shipped|frozen) (?:canvas )?pieces\b", line, re.I)
        if as_int(m.group(1)) != count
    ]
    assert not stale, "a doc counts the shipped pieces wrong (say it without a count):\n" + "\n".join(stale)


# --------------------------------------------------------------------------
# the ADRs
# --------------------------------------------------------------------------
def adrs() -> list[Path]:
    return sorted(DECISIONS.glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_the_decisions_index_lists_every_adr():
    index = (DECISIONS / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in adrs() if f"]({p.name})" not in index]
    assert not missing, f"docs/decisions/README.md has no row for {missing}"


def test_every_count_of_the_adrs_matches_the_folder():
    count = len(adrs())
    stale = [
        f"{path.relative_to(ROOT)}:{no}: {m.group(0)!r}, but docs/decisions/ holds {count}"
        for path, lines in live_text_of_every_doc()
        for no, line in lines
        for m in re.finditer(rf"\b{NUMBER} ADRs\b", line, re.I)
        if as_int(m.group(1)) != count
    ]
    assert not stale, "a doc counts the ADRs wrong (say it without a count):\n" + "\n".join(stale)
