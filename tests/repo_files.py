"""
The repository's own files, for the tests that read the docs as text
(test_doc_drift, test_doc_links, test_plugin).

"The repository" is what git tracks, not what is on disk: a link to a
git-ignored file, or a count of an untracked folder, is wrong for everyone who
clones it.
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@cache
def tracked() -> frozenset[str]:
    """Every tracked path, relative to the root, with forward slashes."""
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:  # pragma: no cover - CI always has git
        pytest.skip(f"not a git checkout: {e}", allow_module_level=True)
    return frozenset(f for f in out.split("\0") if f)


@cache
def tracked_dirs() -> frozenset[str]:
    dirs = set()
    for f in tracked():
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return frozenset(dirs)


def tracked_markdown() -> list[Path]:
    return [ROOT / f for f in sorted(tracked()) if f.endswith(".md")]


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
