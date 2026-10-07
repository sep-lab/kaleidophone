"""
Which commits a check should read: shared by check_deny_list.py and
check_no_session_urls.py, so CI and the pre-push hook agree on what "the
commits being pushed" means.

Three sources, one shape. A *spec* is ("range", a, b), ("new", b) or
("commit", c); `commits()` turns it into commit SHAs and `tip()` into the
commit whose tree is checked whole.

- `pre_push(stdin)` reads git's pre-push lines
  (`<local ref> <local sha> <remote ref> <remote sha>`). A deletion pushes
  nothing; a new branch pushes the commits no remote has yet.
- `from_github(event_name, payload)` reads the Actions event: a pull request
  is its base..head, a push its before..after. A push whose `before` is
  unknown (a new branch, a force-push past it) falls back to the pushed
  commit alone, and says so -- it never widens to the whole history, which
  can't be rewritten (tags and the site's sha256s depend on it).
- `secrets_withheld(event_name, payload)` is the one case a secret-reading
  check may skip: GitHub gives no repository secrets to a pull request from
  a fork or from Dependabot. It is decided from the event, never from the
  secret being empty -- an unset secret on main must fail, not pass.
- `pull_request_texts(event_name, payload)`: a pull request's title and body,
  which a squash merge can turn into the commit message on main. Checked
  before the merge, not after it is history.
- `tag_messages(specs)`: an annotated tag pushed carries a message of its own,
  published with it.

Standard library only, Python 3.9+ (macOS's /usr/bin/python3 runs the hook).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Dict, Iterable, List, Optional, Tuple

Spec = Tuple[str, ...]
ZERO = re.compile(r"^0+$")


class RangeError(Exception):
    """A range that can't be resolved. Callers fail closed on it."""


def git(*args: str, input: Optional[bytes] = None) -> bytes:
    proc = subprocess.run(["git", *args], input=input, capture_output=True)
    if proc.returncode != 0:
        raise RangeError(f"git {args[0]} failed (exit {proc.returncode})")
    return proc.stdout


def is_commit(rev: str) -> bool:
    if not rev or ZERO.match(rev):
        return False
    return subprocess.run(["git", "cat-file", "-e", f"{rev}^{{commit}}"], capture_output=True).returncode == 0


def pre_push(lines: Iterable[str]) -> Tuple[List[Spec], List[str]]:
    """(specs, remote ref names) for git's pre-push stdin."""
    specs: List[Spec] = []
    refs: List[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, remote_sha = parts
        if ZERO.match(local_sha):
            continue  # a deletion pushes no content
        refs.append(remote_ref)
        if ZERO.match(remote_sha) or not is_commit(remote_sha):
            specs.append(("new", local_sha))  # new branch, or a remote tip we haven't fetched
        else:
            specs.append(("range", remote_sha, local_sha))
    return specs, refs


def github_event() -> Tuple[str, dict]:
    """(event name, payload) of the running Actions job. RangeError if there is none."""
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as fh:
            return os.environ.get("GITHUB_EVENT_NAME", ""), json.load(fh)
    except (KeyError, OSError, ValueError):
        raise RangeError("no readable GITHUB_EVENT_PATH (is this a GitHub Actions job?)") from None


def pull_request_texts(event_name: str, payload: dict) -> List[Tuple[str, str]]:
    """(what, text) for a pull request's title and body; empty for other events."""
    if event_name != "pull_request":
        return []
    pr = payload.get("pull_request") or {}
    return [(what, pr.get(key) or "") for what, key in (("the pull request title", "title"), ("the pull request body", "body"))]


def tag_messages(specs: List[Spec]) -> Dict[str, str]:
    """tag object sha -> message, for every annotated tag among the pushed tips."""
    out = {}
    for spec in specs:
        sha = tip(spec)
        kind = subprocess.run(["git", "cat-file", "-t", sha], capture_output=True, text=True).stdout.strip()
        if kind == "tag":
            raw = git("cat-file", "tag", sha)
            out[sha] = raw.partition(b"\n\n")[2].decode("utf-8", "replace")
    return out


def from_github(event_name: str, payload: dict) -> Tuple[List[Spec], List[str]]:
    """(specs, notices) for a GitHub Actions event."""
    notices: List[str] = []
    if event_name == "pull_request":
        pr = payload.get("pull_request") or {}
        base, head = (pr.get("base") or {}).get("sha"), (pr.get("head") or {}).get("sha")
        if not (base and head):
            raise RangeError("the pull_request event has no base/head sha")
        return [("range", base, head)], notices
    if event_name == "push":
        before, after = payload.get("before") or "", payload.get("after") or ""
        if not after or ZERO.match(after):
            return [], ["the push deleted a ref: nothing to check"]
        if is_commit(before):
            return [("range", before, after)], notices
        notices.append("the push's previous tip is unknown here (a new branch or a force-push): checking the pushed commit and its tree only")
        return [("commit", after)], notices
    notices.append(f"a {event_name or 'manual'} run has no commit range: checking HEAD, its tree and its message only")
    return [("commit", "HEAD")], notices


def secrets_withheld(event_name: str, payload: dict) -> bool:
    if event_name != "pull_request":
        return False
    pr = payload.get("pull_request") or {}
    head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    base_repo = ((pr.get("base") or {}).get("repo") or {}).get("full_name")
    author = (pr.get("user") or {}).get("login")
    return head_repo != base_repo or author == "dependabot[bot]"


def commits(spec: Spec) -> List[str]:
    kind = spec[0]
    if kind == "range":
        a, b = spec[1], spec[2]
        for rev in (a, b):
            if not is_commit(rev):
                raise RangeError(f"{rev[:12]} is not a commit in this clone (fetch with full history)")
        out = git("rev-list", f"{a}..{b}")
    elif kind == "new":
        if not is_commit(spec[1]):
            raise RangeError(f"{spec[1][:12]} is not a commit in this clone")
        out = git("rev-list", spec[1], "--not", "--remotes")
    elif kind == "commit":
        if not is_commit(spec[1]):
            raise RangeError(f"{spec[1][:12]} is not a commit in this clone")
        out = git("rev-parse", f"{spec[1]}^{{commit}}")
    else:  # pragma: no cover - internal
        raise RangeError(f"unknown spec {kind}")
    return out.decode().split()


def tip(spec: Spec) -> str:
    return spec[-1]


def parse_range(text: str) -> Spec:
    """`A..B` from the command line."""
    a, sep, b = text.partition("..")
    if not sep or not a or not b or b.startswith("."):
        raise RangeError(f"--range wants A..B, got {text!r}")
    return ("range", a, b)
