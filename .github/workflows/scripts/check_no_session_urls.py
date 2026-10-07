#!/usr/bin/env python3
"""
Guardrail: no Claude Code session URL in a commit message.

WHY
    A `Claude-Session: https://claude.ai/code/session_...` trailer links a
    public commit to a private working session -- its transcript, the paths
    and names that came up in it. The project decided to strip them; three
    commits from before that decision still carry one, and stay, because
    history is not rewritten here (tags and the artist site's sha256s depend
    on it). This keeps the count at three: it reads only the commits being
    pushed -- a pull request's own commits, or a push's new ones -- and names
    those three, so a push that can't tell what the remote has (a clone with
    no remote-tracking refs reads its whole history) doesn't trip on them. In
    CI it also reads a pull request's title and body, which a squash merge can
    make main's commit message, and the hook an annotated tag's message.

WHAT IT PRINTS
    The commit and the message line, never the URL.

USAGE
    check_no_session_urls.py [--range A..B]... [--commit REV]...
    check_no_session_urls.py --github      CI: the range from the Actions event
    check_no_session_urls.py --pre-push    the hook: git's pre-push lines on stdin

    Exit 0 clean; 1 a session URL was found; 2 the range could not be read.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

import gitrange

MARKER = "claude.ai/code/session_"
# On main from before the rule (v0.3.0, its numba fix, v0.4.0). They stay: history isn't rewritten.
BEFORE_THE_RULE = {
    "0e9316e4d4cbc53b156b2bd18207660435a900a8",
    "09c27aba9fe69ce78fa4d41547dd832c8f71d54d",
    "7d450609aa30a4c745e70a63315078800adcc73f",
}


def offending_lines(message: str) -> List[int]:
    return [n for n, line in enumerate(message.splitlines(), 1) if MARKER in line.lower()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Refuse Claude Code session URLs in the commits being pushed")
    ap.add_argument("--range", action="append", default=[], metavar="A..B")
    ap.add_argument("--commit", action="append", default=[], metavar="REV")
    ap.add_argument("--github", action="store_true", help="read the range from the GitHub Actions event")
    ap.add_argument("--pre-push", action="store_true", help="read git's pre-push lines from stdin")
    args = ap.parse_args(argv)
    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    err = "::error::" if gha else ""

    specs: List[gitrange.Spec] = []
    found: List[str] = []
    try:
        if args.github:
            event, payload = gitrange.github_event()
            specs, notices = gitrange.from_github(event, payload)
            for n in notices:
                print(f"::notice::{n}" if gha else f"note: {n}")
            for what, text in gitrange.pull_request_texts(event, payload):
                found += [f"{what}, line {n}" for n in offending_lines(text)]
        if args.pre_push:
            specs += gitrange.pre_push(sys.stdin.read().splitlines())[0]
        specs += [gitrange.parse_range(r) for r in args.range] + [("commit", c) for c in args.commit]
        commits = [c for c in dict.fromkeys(c for spec in specs for c in gitrange.commits(spec)) if c not in BEFORE_THE_RULE]
        for c in commits:
            message = gitrange.git("log", "-1", "--format=%B", c).decode("utf-8", "replace")
            found += [f"commit {c[:12]}, message line {n}" for n in offending_lines(message)]
        for sha, message in gitrange.tag_messages(specs).items():
            found += [f"tag {sha[:12]}, message line {n}" for n in offending_lines(message)]
    except gitrange.RangeError as e:
        print(f"{err}check_no_session_urls: {e}. Failing closed.")
        return 2

    if found:
        for where in found:
            print(f"{err}{where}: a Claude Code session URL ({MARKER}...)")
        print(
            "\n  Session URLs stay out of commit messages: they point a public commit at a\n"
            "  private session. Drop the trailer -- `git commit --amend` for the last\n"
            "  commit, `git rebase -i` for an earlier one -- and push again. This only reads\n"
            "  the commits being pushed; main's history is not rewritten."
        )
        return 1
    print(f"session URLs: clean -- {len(commits)} commit(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
