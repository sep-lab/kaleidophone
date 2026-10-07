#!/usr/bin/env python3
"""
Guardrail: no name on the private deny list reaches this public repository.

WHY A LIST, AND WHY PRIVATE
    The other guardrails catch shapes: a media file, a home-directory path, a
    song pack. A private name has no shape. An unreleased song's title, a
    collaborator, a real place a piece was drawn from: each is an ordinary
    word that only its owner knows is private. So the owner keeps the list, out
    of the repository, and this check reads it -- in CI from the KP_DENY_LIST
    secret, and in the pre-push hook (.githooks/pre-push) from a file on the
    machine, before anything leaves it.

WHAT IT READS
    Every commit being pushed: its message, and every path and file it adds or
    changes, as committed (so a name added in one commit and removed in the
    next is still caught -- both commits are published). Then the whole tree at
    the tip, an annotated tag's message, and in CI a pull request's title and
    body (a squash merge can make them main's commit message). History before
    the range is not read: it is public already, and it is not rewritten (tags
    and the artist site's sha256s depend on it).

WHAT IT PRINTS
    Where, never what: `file:line` (or a commit and its message line) and a
    short keyed hash of the term, `#3f9a0c1b2d`. Never the term, never the line
    it is on, and never a path that itself contains a term. The repository is
    public and so are its CI logs. The hash is an HMAC keyed by the whole list,
    so it can't be reversed by hashing guesses; `--list-hashes` maps each hash
    to its line in your copy of the list, still without printing a term.

FAIL CLOSED
    No list, a list shorter than --min-terms, a pattern that won't compile, a
    range that won't resolve, a crash: all exit non-zero. The one
    exception: GitHub gives no repository secrets to a pull request from a fork
    or from Dependabot, so `--github` skips those with a visible notice. That is
    decided from the event, never from the secret being empty -- an unset secret
    on main, or on a pull request from this repository, fails.

THE LIST
    One term per line; blank lines and lines starting with `#` are ignored. The
    format is the artist site's, so one file can serve both:
        Some Name        anywhere, any case; the words may be joined by any run of
                         spaces, punctuation, underscores or line breaks, or by
                         nothing (Some_Name, some-name, SomeName, "Some\\nName")
        word:Ali         a whole word only (so is any term of 4 characters or fewer)
        case:Name        a whole word, with its capitals as written: for a name
                         that is also an ordinary word (this repository's own
                         addition; the site's check reads it as a plain term)
        re:pattern       a Python regular expression, matched case-insensitively
                         against the normalised text; ^ and $ anchor lines, as
                         they do in the site's line-by-line check
    Both the text and the terms are normalised first: NFKC, Arabic yeh and kaf
    folded to Persian, zero-width characters and soft hyphens removed, case
    folded. Every file is read as UTF-8 text, binary ones included.

USAGE
    check_deny_list.py [--range A..B]... [--commit REV]... [--tree REV]...
    check_deny_list.py --github         CI: the range from the Actions event
    check_deny_list.py --pre-push       the hook: git's pre-push lines on stdin
    check_deny_list.py --fingerprint    the list's size and fingerprint (compare CI and local)
    check_deny_list.py --list-hashes    each term's hash and its line in your list
    With no range, commit or tree, it reads HEAD's tree.

    The list is $KP_DENY_LIST (the text itself), else --list-file, else
    $KP_DENY_LIST_FILE, else ~/.kaleidophone-private/deny-list.txt.

    Exit 0 clean; 1 a term was found; 2 the check could not run.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import sys
import traceback
import unicodedata
from bisect import bisect_right
from typing import Dict, List, Optional, Tuple

import gitrange

DEFAULT_LIST = os.path.join("~", ".kaleidophone-private", "deny-list.txt")
MIN_TERMS = 5  # the artist site's floor in CI: a list this short was probably truncated
SHORT = 4  # terms this short only match whole words (the site's rule)
GITLINK = "160000"

FOLD = {ord("ي"): "ی", ord("ى"): "ی", ord("ك"): "ک"}  # ي ى -> ی, ك -> ک
FOLD.update({ord(c): None for c in "​‌‍⁠﻿­"})  # ZWSP ZWNJ ZWJ WJ BOM SHY


class ListError(Exception):
    """The list can't be used. Messages name list line numbers, never terms."""


def normalize(text: str, keep_case: bool = False) -> str:
    text = unicodedata.normalize("NFKC", text).translate(FOLD)
    return text if keep_case else text.casefold()


class Term:
    def __init__(self, raw: str, line: int):
        self.raw, self.line, self.hash, self.cased = raw, line, "", raw.startswith("case:")
        if raw.startswith("re:"):
            try:
                self.pattern = re.compile(raw[3:], re.IGNORECASE | re.MULTILINE)
            except re.error:
                raise ListError(f"list line {line}: its re: pattern doesn't compile as a Python regular expression") from None
            if self.pattern.search(""):
                raise ListError(f"list line {line}: its re: pattern matches empty text, so it would match everywhere")
            return
        whole_word = raw.startswith(("word:", "case:"))
        # a ZWNJ inside a term is a word break: the same name is written with a space or with nothing
        text = normalize((raw[5:] if whole_word else raw).replace("\u200c", " "), keep_case=self.cased).strip()
        if not text:
            raise ListError(f"list line {line}: a prefix with no term after it")
        parts = [p for p in re.split(r"[\W_]+", text) if p]
        body = r"[\W_]*".join(re.escape(p) for p in parts) if parts else re.escape(text)
        if whole_word or len(text) <= SHORT:
            body = rf"(?<!\w){body}(?!\w)"
        self.pattern = re.compile(body)


def parse_list(text: str) -> List[Term]:
    terms = []
    for n, raw in enumerate(text.splitlines(), 1):
        raw = raw.strip()
        if raw and not raw.startswith("#"):
            terms.append(Term(raw, n))
    joined = "\n".join(sorted(t.raw for t in terms)).encode("utf-8")
    key = hashlib.sha256(b"kaleidophone deny-list key\0" + joined).digest()
    for t in terms:
        t.hash = hmac.new(key, t.raw.encode("utf-8"), hashlib.sha256).hexdigest()[:10]
    return terms


def fingerprint(terms: List[Term]) -> str:
    joined = "\n".join(sorted(t.raw for t in terms)).encode("utf-8")
    return hashlib.sha256(b"kaleidophone deny-list fingerprint\0" + joined).hexdigest()[:8]


def read_list(list_file: Optional[str]) -> Tuple[str, str]:
    """(the list's text, where it came from). Empty text if there is none."""
    env = os.environ.get("KP_DENY_LIST", "")
    if env.strip():
        return env, "$KP_DENY_LIST"
    path = list_file or os.environ.get("KP_DENY_LIST_FILE") or DEFAULT_LIST
    full = os.path.expanduser(path)
    if not os.path.isfile(full):
        return "", path
    with open(full, encoding="utf-8") as fh:
        return fh.read(), path


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
def find(text: str, terms: List[Term]) -> List[Tuple[int, str]]:
    """(line, term hash) for every term in a text, first hit per term per line."""
    hits = set()
    for cased in (False, True):
        group = [t for t in terms if t.cased is cased]
        if not group:
            continue
        norm = normalize(text, keep_case=cased)
        newlines = [m.start() for m in re.finditer("\n", norm)]
        for t in group:
            for m in t.pattern.finditer(norm):
                hits.add((bisect_right(newlines, m.start() - 1) + 1, t.hash))
    return sorted(hits)


def matches(text: str, terms: List[Term]) -> List[str]:
    return sorted({h for _, h in find(text, terms)})


# --------------------------------------------------------------------------
# reading git
# --------------------------------------------------------------------------
def read_objects(shas: List[str]) -> Dict[str, bytes]:
    if not shas:
        return {}
    out = gitrange.git("cat-file", "--batch", input=("\n".join(shas) + "\n").encode())
    objs, pos = {}, 0
    for sha in shas:
        nl = out.index(b"\n", pos)
        header = out[pos:nl].split()
        if len(header) < 3:
            raise gitrange.RangeError(f"object {sha[:12]} is missing from this clone")
        size = int(header[2])
        objs[sha] = out[nl + 1 : nl + 1 + size]
        pos = nl + 1 + size + 1
    return objs


def tree_entries(rev: str) -> List[Tuple[str, str]]:
    """(path, blob sha) for every file in a commit's tree."""
    out = gitrange.git("ls-tree", "-r", "-z", "--full-tree", rev)
    entries = []
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        mode, _type, sha = meta.decode().split()
        if mode != GITLINK:
            entries.append((path.decode("utf-8", "replace"), sha))
    return entries


def changed_entries(commit: str) -> List[Tuple[str, str]]:
    """(path, blob sha) for every file a commit adds or changes (against each parent)."""
    out = gitrange.git("diff-tree", "-r", "-m", "--root", "--no-commit-id", "--no-renames", "-z", commit)
    fields = out.split(b"\0")
    entries, i = [], 0
    while i + 1 < len(fields) and fields[i].startswith(b":"):
        _m1, mode, _s1, sha, status = fields[i][1:].decode().split()
        path = fields[i + 1].decode("utf-8", "replace")
        if status != "D" and mode != GITLINK:
            entries.append((path, sha))
        i += 2
    if any(fields[i:]):  # output this parser doesn't know: never skip what it says
        raise gitrange.RangeError(f"unexpected `git diff-tree` output for commit {commit[:12]}")
    return entries


def message_of(raw_commit: bytes) -> str:
    _headers, _, message = raw_commit.partition(b"\n\n")
    return message.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# the check
# --------------------------------------------------------------------------
def shown(path: str) -> str:
    """A path as it is printed: a control character in a file name (git allows a
    newline) must not start a new output line, which Actions could read as a
    workflow command."""
    return re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\x{ord(m.group()):02x}", path)


def escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


class Report:
    def __init__(self, annotate: bool):
        self.annotate, self.lines = annotate, []

    def hit(self, at: str, term: str, file: Optional[str] = None, line: Optional[int] = None) -> None:
        self.lines.append(f"  {at}  term #{term}")
        if self.annotate:
            loc = f" file={escape_property(file)},line={line}" if file and line else ""
            print(f"::error{loc}::{escape_data(f'deny-list term #{term} at {at}')} (the term is not printed: this repository is public)")


def scan(
    specs: List[gitrange.Spec],
    trees: List[str],
    refs: List[str],
    terms: List[Term],
    report: Report,
    texts: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[int, int]:
    blobs: Dict[str, List[Tuple[str, str]]] = {}  # blob sha -> (path, "" or the commit it is only in)
    paths: Dict[str, List[str]] = {}  # path -> which tree or commit it is in
    commits: Dict[str, None] = {}  # ordered, and a set
    for spec in specs:
        for c in gitrange.commits(spec):
            if c not in commits:
                commits[c] = None
                for path, sha in changed_entries(c):
                    blobs.setdefault(sha, []).append((path, c[:12]))
                    paths.setdefault(path, []).append(f"commit {c[:12]}")
        trees.append(gitrange.tip(spec))
    for rev in dict.fromkeys(trees):
        for path, sha in tree_entries(rev):
            blobs.setdefault(sha, []).insert(0, (path, ""))  # the tip's own path reads best
            paths.setdefault(path, []).insert(0, f"the tree at {rev[:12]}")

    private_paths: Dict[str, str] = {}
    path_hits: Dict[Tuple[str, str], int] = {}
    for path, where in sorted(paths.items()):
        for h in matches(path, terms):
            private_paths[path] = h
            path_hits[(where[0], h)] = path_hits.get((where[0], h), 0) + 1
    for (where, h), n in sorted(path_hits.items()):
        report.hit(f"{n} path{'s' * (n > 1)} in {where} (not printed: the path itself holds the term)", h)
    for ref in refs:
        for h in matches(ref, terms):
            report.hit("the name of a branch or tag being pushed (not printed)", h)
    for what, text in texts or []:
        for line, h in find(text, terms):
            report.hit(f"{what}, line {line}", h)
    for sha, message in gitrange.tag_messages(specs).items():
        for line, h in find(message, terms):
            report.hit(f"tag {sha[:12]} message, line {line}", h)

    for c, raw in read_objects(list(commits)).items():
        for line, h in find(message_of(raw), terms):
            report.hit(f"commit {c[:12]} message, line {line}", h)

    for sha, text in read_objects(sorted(blobs)).items():
        found = find(text.decode("utf-8", "replace"), terms)
        if not found:
            continue
        path, only_in = blobs[sha][0]
        public = None if path in private_paths else path
        others = len({p for p, _ in blobs[sha]} - {path})  # other paths holding the same file
        for line, h in found:
            at = f"{shown(public)}:{line}" if public else f"<a path holding term #{private_paths[path]}>:{line}"
            if only_in:
                at += f" (in commit {only_in})"
            if others:
                at += f" (and at {others} more path{'s' * (others > 1)})"
            report.hit(at, h, file=public, line=line)
    return len(commits), len(blobs)


HOW_TO_FIX = """
  A name on the private deny list is in what is about to be published.
  Which name: `python3 .github/workflows/scripts/check_deny_list.py --list-hashes`
  prints the line of your list each hash stands for. Remove or reword it, then
  amend or rebase the commit that added it -- a commit message counts, and so
  does a commit that is undone later in the same push.
  Never paste the term into an issue, a pull request or a commit message to ask
  about it: that publishes it.
"""


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Refuse names on the private deny list (prints hashes, never terms)")
    ap.add_argument("--range", action="append", default=[], metavar="A..B", help="commits in A..B, and B's tree")
    ap.add_argument("--commit", action="append", default=[], metavar="REV", help="one commit, and its tree")
    ap.add_argument("--tree", action="append", default=[], metavar="REV", help="every file in REV's tree")
    ap.add_argument("--github", action="store_true", help="read the range from the GitHub Actions event")
    ap.add_argument("--pre-push", action="store_true", help="read git's pre-push lines from stdin")
    ap.add_argument("--list-file", help=f"the deny list (default $KP_DENY_LIST_FILE or {DEFAULT_LIST})")
    ap.add_argument("--min-terms", type=int, default=MIN_TERMS, help=f"refuse a shorter list (default {MIN_TERMS})")
    ap.add_argument("--fingerprint", action="store_true", help="print the list's size and fingerprint, then exit")
    ap.add_argument("--list-hashes", action="store_true", help="print each term's hash and list line, then exit")
    args = ap.parse_args(argv)
    gha = os.environ.get("GITHUB_ACTIONS") == "true"

    withheld, notices, event, payload = False, [], "", {}
    if args.github:
        try:
            event, payload = gitrange.github_event()
        except gitrange.RangeError as e:
            print(f"::error::check_deny_list --github: {e}; failing closed.")
            return 2
        withheld = gitrange.secrets_withheld(event, payload)

    text, source = read_list(args.list_file)
    if not text.strip():
        if withheld:
            print(
                "::notice title=Deny list not checked::GitHub gives no secrets to a pull request from a fork or "
                "from Dependabot, so KP_DENY_LIST is empty here and the deny list was not checked. It runs, "
                "and is required, on every push to main and on pull requests from this repository."
            )
            return 0
        where = "the KP_DENY_LIST repository secret is not set" if gha else f"no deny list at {source} and $KP_DENY_LIST is empty"
        print(
            f"{'::error::' if gha else ''}check_deny_list: {where}. This check fails closed: without the list, "
            "private names can't be checked.\n"
            "  CI: Settings > Secrets and variables > Actions > New repository secret KP_DENY_LIST, one term per line.\n"
            f"  Here: one term per line in {DEFAULT_LIST} (outside the repository), or point $KP_DENY_LIST_FILE at it.\n"
            "  See CONTRIBUTING.md, \"The deny list\"."
        )
        return 2
    try:
        terms = parse_list(text)
    except ListError as e:
        print(f"{'::error::' if gha else ''}check_deny_list: {e} (in {source}). Fix the list; failing closed.")
        return 2
    if len(terms) < args.min_terms:
        print(
            f"{'::error::' if gha else ''}check_deny_list: {source} has {len(terms)} term(s), fewer than "
            f"--min-terms {args.min_terms}: it looks truncated, so this check fails closed."
        )
        return 2
    print(f"deny list: {len(terms)} terms from {source}, fingerprint {fingerprint(terms)}")
    if args.fingerprint:
        return 0
    if args.list_hashes:
        for t in sorted(terms, key=lambda t: t.line):
            print(f"  #{t.hash}  list line {t.line}")
        return 0

    specs: List[gitrange.Spec] = []
    refs: List[str] = []
    trees = list(args.tree)
    try:
        if args.github:
            specs, notices = gitrange.from_github(event, payload)
        if args.pre_push:
            specs, refs = gitrange.pre_push(sys.stdin.read().splitlines())
            if not specs:
                print("deny list: nothing to push, nothing to check")
                return 0
        specs += [gitrange.parse_range(r) for r in args.range] + [("commit", c) for c in args.commit]
        if not specs and not trees:
            trees = ["HEAD"]
        for n in notices:
            print(f"::notice::{n}" if gha else f"note: {n}")
        report = Report(annotate=gha)
        n_commits, n_files = scan(specs, trees, refs, terms, report, texts=gitrange.pull_request_texts(event, payload))
    except gitrange.RangeError as e:
        print(f"{'::error::' if gha else ''}check_deny_list: {e}. Failing closed.")
        return 2

    if report.lines:
        print(f"\ndeny list: {len(report.lines)} hit(s) in {n_commits} commit(s) and {n_files} file(s):")
        print("\n".join(report.lines))
        print(HOW_TO_FIX)
        return 1
    print(f"deny list: clean -- {n_commits} commit(s), {n_files} file(s), {len(terms)} terms")
    return 0


def run(argv: Optional[List[str]] = None) -> int:
    try:
        return main(argv)
    except Exception as e:  # never let a message carry a term out: name the error type only
        if os.environ.get("KP_DENY_LIST_DEBUG") == "1":
            traceback.print_exc()
        print(f"check_deny_list: unexpected {type(e).__name__}; failing closed (KP_DENY_LIST_DEBUG=1 shows the traceback, locally only).")
        return 2


if __name__ == "__main__":
    sys.exit(run())
