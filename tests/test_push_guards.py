"""
The two checks that read the commits being pushed, in CI and in the pre-push
hook: the private deny list (check_deny_list.py) and Claude Code session URLs
(check_no_session_urls.py).

Each test builds a throwaway git repository with a seeded fake name or a fake
session trailer in it. The deny list here is invented for the test -- the real
one is a secret, and these tests never read it: they run with an empty HOME
and no KP_DENY_LIST from the environment.

The property that matters most is the negative one: a term is found, and the
output never contains it -- not in a message, a path, an annotation or an
error -- because the CI log of this repository is public.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "workflows" / "scripts"
DENY = SCRIPTS / "check_deny_list.py"
URLS = SCRIPTS / "check_no_session_urls.py"
sys.path.insert(0, str(SCRIPTS))

import check_deny_list as cdl  # noqa: E402
import check_no_session_urls as csu  # noqa: E402
import gitrange  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

# A made-up place, and four more made-up terms so the list clears the default --min-terms 5.
FAKE = "Quillmere Fenwick"
LIST = "\n".join(
    [
        "# a comment line, ignored",
        FAKE,
        "word:Ivo",
        "re:zz[0-9]{6}qq",
        "Vandermoss",
        "کوچه‌باغ",  # Persian, with a zero-width non-joiner in it
        "",
    ]
)
ZERO = "0" * 40


def leaked(output: str) -> list[str]:
    """Every list term, in any spelling the checker would have matched, that the output repeats."""
    norm = cdl.normalize(output)
    return [t for t in ("quillmere", "fenwick", "vandermoss", "کوچه", "باغ") if t in norm] + (
        ["Ivo"] if re.search(r"(?<!\w)ivo(?!\w)", norm) else []
    )


@pytest.fixture
def env(tmp_path):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("KP_DENY_LIST", "GITHUB_", "GIT_"))}
    home = tmp_path / "home"
    home.mkdir()
    e.update(
        HOME=str(home),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
        PYTHONDONTWRITEBYTECODE="1",
    )
    return e


class Repo:
    def __init__(self, path: Path, env: dict):
        self.path, self.env = path, env
        path.mkdir()
        self.git("init", "-q", "-b", "main")
        self.commit({"README.md": "a clean start\n"}, "start")

    def git(self, *args: str, input: str | None = None) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.path, env=self.env, input=input, capture_output=True, text=True, check=True
        ).stdout.strip()

    def commit(self, files: dict, message: str) -> str:
        for name, text in files.items():
            f = self.path / name
            if text is None:
                f.unlink()
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run(self, script: Path, *args: str, stdin: str = "", deny: str | None = LIST, **extra) -> subprocess.CompletedProcess:
        env = dict(self.env, **extra)
        if deny is not None:
            env["KP_DENY_LIST"] = deny
        return subprocess.run(
            [sys.executable, str(script), *args], cwd=self.path, env=env, input=stdin, capture_output=True, text=True
        )


@pytest.fixture
def repo(tmp_path, env):
    return Repo(tmp_path / "repo", env)


def hashes(repo: Repo) -> dict[int, str]:
    """list line -> term hash, from the checker's own --list-hashes."""
    out = repo.run(DENY, "--list-hashes").stdout
    return {int(n): h for h, n in re.findall(r"#([0-9a-f]{10})\s+list line (\d+)", out)}


# --------------------------------------------------------------------------
# the deny list: found, and never printed
# --------------------------------------------------------------------------
def test_a_seeded_name_is_found_by_file_and_line_and_never_printed(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"docs/notes.md": "line one\nline two\nwe met at Quillmere Fenwick, after dark\n"}, "add notes")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "docs/notes.md:3" in r.stdout
    assert f"term #{hashes(repo)[2]}" in r.stdout  # list line 2 is FAKE
    assert leaked(r.stdout + r.stderr) == []
    assert "after dark" not in r.stdout, "the matching line itself must not be echoed"


@pytest.mark.parametrize(
    "text",
    [
        "QUILLMERE FENWICK",
        "quillmere-fenwick",
        "Quillmere_Fenwick.wav",
        "QuillmereFenwick",
        "we met at Quillmere\nFenwick, after dark",  # a doc wrapped mid-name
        "# Quillmere\n# Fenwick",  # a comment wrapped mid-name
        "Ｑｕｉｌｌｍｅｒｅ Ｆｅｎｗｉｃｋ",  # fullwidth letters (NFKC)
        "Quill­mere Fen​wick",  # a soft hyphen and a zero-width space hiding it
        "Vandermosses",  # a long term matches inside a word
        "the guide said: Ivo.",  # a short one only as a whole word
        "code zz123456qq here",  # re:
        "کوچهباغ",  # the Persian term without its ZWNJ
        "کوچه باغ",  # or with a space for it
        "كوچه‌باغ",  # with an Arabic kaf
    ],
)
def test_the_spellings_a_name_hides_in_are_caught(text):
    assert cdl.find(text, cdl.parse_list(LIST)), f"{text!r} was not caught"


@pytest.mark.parametrize("text", ["Ivory and Ivonne", "a quill, a mere fen", "zz12345qq", "Vander moss"])
def test_near_misses_pass(text):
    assert cdl.find(text, cdl.parse_list(LIST)) == []


@pytest.mark.parametrize(("text", "hit"), [("Dunewell", True), ("the Dunewell mix", True), ("a dunewell", False), ("Dunewells", False)])
def test_case_keeps_a_name_that_is_also_a_word_apart_from_the_word(text, hit):
    assert bool(cdl.find(text, cdl.parse_list("case:Dunewell\n"))) is hit


def test_re_anchors_a_line_as_the_site_does():
    """The site's check tests each regex line by line, so ^ and $ mean a line."""
    terms = cdl.parse_list("re:^zz secret line$\n")
    assert cdl.find("first\nzz secret line\nlast\n", terms) == [(2, terms[0].hash)]


def test_a_hit_is_on_the_line_the_name_starts_on():
    text = "one\ntwo Quillmere\nFenwick three\nVandermoss\n"
    terms = {t.line: t.hash for t in cdl.parse_list(LIST)}
    assert cdl.find(text, cdl.parse_list(LIST)) == sorted([(2, terms[2]), (4, terms[5])])


def test_a_name_in_a_path_is_reported_without_the_path(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"pieces/quillmere-fenwick/piece.json": "{}\n", "pieces/ok/note.txt": "Vandermoss\n"}, "a piece")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 1
    assert "path" in r.stdout and "pieces/ok/note.txt:1" in r.stdout
    assert leaked(r.stdout + r.stderr) == []


def test_a_file_under_a_private_path_hides_the_path_in_its_hits_too(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"Vandermoss/notes.md": "x\nIvo\n"}, "private folder")
    r = repo.run(DENY, "--range", f"{base}..{head}", GITHUB_ACTIONS="true")
    assert r.returncode == 1
    assert ":2" in r.stdout and leaked(r.stdout + r.stderr) == []


def test_a_name_in_a_commit_message_is_found(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.txt": "fine\n"}, "fix: the bridge at\n\nquillmere fenwick")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 1
    assert f"commit {head[:12]} message, line 3" in r.stdout
    assert leaked(r.stdout + r.stderr) == []


def test_a_name_added_and_removed_inside_the_push_is_still_caught(repo):
    """Both commits are published; only the tip is clean."""
    base = repo.git("rev-parse", "HEAD")
    repo.commit({"a.txt": "Vandermoss\n"}, "add")
    head = repo.commit({"a.txt": "clean\n"}, "remove")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 1 and "a.txt:1 (in commit " in r.stdout
    assert leaked(r.stdout + r.stderr) == []


def test_a_name_only_a_merge_brings_in_is_caught(repo):
    """An evil merge: the conflict resolution adds the name, the next commit
    removes it, so neither branch's commits nor the tip hold it -- only the
    merge's own diff does."""
    base = repo.commit({"a.txt": "one\n"}, "base")
    repo.git("checkout", "-q", "-b", "side")
    repo.commit({"a.txt": "side\n"}, "side")
    repo.git("checkout", "-q", "main")
    repo.commit({"a.txt": "main\n"}, "main")
    subprocess.run(["git", "merge", "-q", "side"], cwd=repo.path, env=repo.env, capture_output=True)
    merge = repo.commit({"a.txt": "resolved by Vandermoss\n"}, "merge side")
    assert len(repo.git("rev-list", "--parents", "-n1", merge).split()) == 3, "not a merge"
    head = repo.commit({"a.txt": "clean\n"}, "reword")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 1 and f"a.txt:1 (in commit {merge[:12]})" in r.stdout


def test_diff_tree_output_the_parser_doesnt_know_fails_closed(monkeypatch):
    monkeypatch.setattr(cdl.gitrange, "git", lambda *a, **k: b":100644 100644 aa bb M\0a.txt\0something else\0")
    with pytest.raises(gitrange.RangeError):
        cdl.changed_entries("f" * 40)


def test_the_whole_tree_at_the_tip_is_read_not_only_the_new_commits(repo):
    repo.commit({"old.txt": "Vandermoss\n"}, "already on main")
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"new.txt": "clean\n"}, "clean change")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 1 and "old.txt:1" in r.stdout


def test_a_clean_push_passes(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.txt": "nothing private\n"}, "clean")
    r = repo.run(DENY, "--range", f"{base}..{head}")
    assert r.returncode == 0, r.stdout
    assert "clean" in r.stdout


def test_a_path_cant_inject_a_workflow_command_or_break_an_annotation(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"x\n::warning::y.txt": "Vandermoss\n", "a,b:c.md": "Vandermoss, again\n"}, "odd names")
    r = repo.run(DENY, "--range", f"{base}..{head}", GITHUB_ACTIONS="true")
    assert r.returncode == 1
    assert not [line for line in r.stdout.splitlines() if line.startswith("::warning")]
    assert "x\\x0a::warning::y.txt:1" in r.stdout
    assert "file=a%2Cb%3Ac.md,line=1::" in r.stdout


def test_github_annotations_name_the_file_and_line_but_not_the_term(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.md": "\nVandermoss\n"}, "add")
    r = repo.run(DENY, "--range", f"{base}..{head}", GITHUB_ACTIONS="true")
    assert "::error file=a.md,line=2::" in r.stdout
    assert leaked(r.stdout + r.stderr) == []


# --------------------------------------------------------------------------
# the hash
# --------------------------------------------------------------------------
def test_the_hash_is_keyed_by_the_whole_list_so_a_guess_cant_be_checked():
    """sha256(term) of a short name is a dictionary lookup away; an HMAC keyed by
    the list is not, and the same term hashes differently under another list."""
    a = {t.raw: t.hash for t in cdl.parse_list(LIST)}
    b = {t.raw: t.hash for t in cdl.parse_list(LIST + "\nAnother Term\n")}
    import hashlib

    assert a[FAKE] != b[FAKE]
    assert a[FAKE] not in hashlib.sha256(FAKE.encode()).hexdigest()
    assert a[FAKE] not in hashlib.sha256(cdl.normalize(FAKE).encode()).hexdigest()
    assert len(set(a.values())) == len(a)


def test_list_hashes_and_fingerprint_print_no_term(repo):
    for flag in ("--list-hashes", "--fingerprint"):
        r = repo.run(DENY, flag)
        assert r.returncode == 0 and leaked(r.stdout + r.stderr) == []
    assert sorted(hashes(repo)) == [2, 3, 4, 5, 6]


# --------------------------------------------------------------------------
# fail closed
# --------------------------------------------------------------------------
def test_no_list_fails_closed(repo):
    r = repo.run(DENY, deny=None)
    assert r.returncode == 2 and "fails closed" in r.stdout


def test_an_empty_secret_fails_closed_in_ci(repo):
    r = repo.run(DENY, deny="\n  \n", GITHUB_ACTIONS="true")
    assert r.returncode == 2 and "KP_DENY_LIST repository secret is not set" in r.stdout


def test_a_short_list_fails_closed(repo):
    r = repo.run(DENY, deny="Vandermoss\nIvo\n")
    assert r.returncode == 2 and "truncated" in r.stdout
    assert repo.run(DENY, "--min-terms", "1", deny="Vandermoss\n").returncode == 0


def test_the_list_file_is_read_when_the_secret_is_unset(repo, tmp_path):
    f = tmp_path / "deny.txt"
    f.write_text(LIST, encoding="utf-8")
    repo.commit({"a.txt": "Vandermoss\n"}, "add")
    assert repo.run(DENY, "--list-file", str(f), deny=None).returncode == 1
    assert repo.run(DENY, deny=None, KP_DENY_LIST_FILE=str(f)).returncode == 1
    default = Path(repo.env["HOME"]) / ".kaleidophone-private" / "deny-list.txt"
    default.parent.mkdir()
    default.write_text(LIST, encoding="utf-8")
    assert repo.run(DENY, deny=None).returncode == 1


@pytest.mark.parametrize("bad", ["re:(unclosed", "re:x*", "word:"])
def test_a_bad_list_line_fails_closed_and_names_the_line_not_the_term(repo, bad):
    r = repo.run(DENY, deny=LIST + bad + "\n")
    assert r.returncode == 2
    assert "list line 7" in r.stdout and bad not in r.stdout


def test_an_unresolvable_range_fails_closed(repo):
    r = repo.run(DENY, "--range", f"{'1' * 40}..HEAD")
    assert r.returncode == 2 and "Failing closed" in r.stdout


def test_a_crash_fails_closed_naming_only_the_exception_type(repo, monkeypatch, capsys):
    """An exception's message could carry a term (a KeyError on one, say), so the
    catch-all prints the exception's type and nothing else."""
    def boom(*_a, **_k):
        raise KeyError("Vandermoss")

    monkeypatch.chdir(repo.path)
    monkeypatch.setenv("KP_DENY_LIST", LIST)
    monkeypatch.delenv("KP_DENY_LIST_DEBUG", raising=False)
    monkeypatch.setattr(cdl, "scan", boom)
    assert cdl.run([]) == 2
    out = capsys.readouterr()
    assert "KeyError" in out.out and leaked(out.out + out.err) == []


# --------------------------------------------------------------------------
# GitHub: who may skip
# --------------------------------------------------------------------------
def pr_event(head_repo="sep-lab/kaleidophone", user="sep", base="b" * 40, head="c" * 40):
    return {
        "pull_request": {
            "base": {"sha": base, "repo": {"full_name": "sep-lab/kaleidophone"}},
            "head": {"sha": head, "repo": {"full_name": head_repo}},
            "user": {"login": user},
        }
    }


@pytest.mark.parametrize(
    ("event", "payload", "withheld"),
    [
        ("pull_request", pr_event(), False),
        ("pull_request", pr_event(head_repo="someone/kaleidophone"), True),
        ("pull_request", pr_event(user="dependabot[bot]"), True),
        ("pull_request", {"pull_request": {}}, False),  # malformed is no reason to skip: fail closed
        ("push", {"before": "a" * 40, "after": "b" * 40}, False),
        ("workflow_dispatch", {}, False),
    ],
)
def test_only_fork_and_dependabot_pull_requests_go_without_secrets(event, payload, withheld):
    assert gitrange.secrets_withheld(event, payload) is withheld


def github_run(repo: Repo, script: Path, event: str, payload: dict, tmp_path: Path, deny: str | None):
    p = tmp_path / "event.json"
    p.write_text(json.dumps(payload))
    return repo.run(script, "--github", deny=deny, GITHUB_ACTIONS="true", GITHUB_EVENT_NAME=event, GITHUB_EVENT_PATH=str(p))


def test_a_fork_pull_request_skips_with_a_visible_notice(repo, tmp_path):
    r = github_run(repo, DENY, "pull_request", pr_event(head_repo="someone/kaleidophone"), tmp_path, deny="")
    assert r.returncode == 0 and "::notice title=Deny list not checked::" in r.stdout


def test_a_same_repo_pull_request_without_the_secret_fails(repo, tmp_path):
    head = repo.git("rev-parse", "HEAD")
    r = github_run(repo, DENY, "pull_request", pr_event(base=head, head=head), tmp_path, deny="")
    assert r.returncode == 2 and "::error::" in r.stdout


def test_a_push_to_main_without_the_secret_fails(repo, tmp_path):
    head = repo.git("rev-parse", "HEAD")
    r = github_run(repo, DENY, "push", {"before": ZERO, "after": head}, tmp_path, deny="")
    assert r.returncode == 2


def test_a_pull_request_is_read_from_base_to_head(repo, tmp_path):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.txt": "Vandermoss\n"}, "add")
    r = github_run(repo, DENY, "pull_request", pr_event(base=base, head=head), tmp_path, deny=LIST)
    assert r.returncode == 1 and "a.txt:1" in r.stdout
    assert leaked(r.stdout + r.stderr) == []


def test_a_pull_request_without_shas_fails_closed(repo, tmp_path):
    r = github_run(repo, DENY, "pull_request", {"pull_request": {"base": {}, "head": {}}}, tmp_path, deny=LIST)
    assert r.returncode == 2


def test_a_pull_requests_title_and_body_are_read(repo, tmp_path):
    """A squash merge can make them main's commit message."""
    head = repo.git("rev-parse", "HEAD")
    event = pr_event(base=head, head=head)
    event["pull_request"].update(title="fix: clean", body="notes\n\nfrom the Quillmere Fenwick session")
    r = github_run(repo, DENY, "pull_request", event, tmp_path, deny=LIST)
    assert r.returncode == 1 and "the pull request body, line 3" in r.stdout
    assert leaked(r.stdout + r.stderr) == []
    event["pull_request"].update(body=None)  # an empty description is null in the payload
    assert github_run(repo, DENY, "pull_request", event, tmp_path, deny=LIST).returncode == 0


def test_a_push_with_an_unknown_before_reads_the_pushed_commit_and_says_so(repo, tmp_path):
    head = repo.commit({"a.txt": "clean\n"}, "clean")
    r = github_run(repo, DENY, "push", {"before": ZERO, "after": head}, tmp_path, deny=LIST)
    assert r.returncode == 0 and "::notice::" in r.stdout and "1 commit(s)" in r.stdout


# --------------------------------------------------------------------------
# the pre-push hook
# --------------------------------------------------------------------------
def test_pre_push_reads_what_git_says_it_is_pushing(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.txt": "Vandermoss\n"}, "add")
    line = f"refs/heads/main {head} refs/heads/main {base}\n"
    assert repo.run(DENY, "--pre-push", stdin=line).returncode == 1
    deletion = f"(delete) {ZERO} refs/heads/old {base}\n"
    assert repo.run(DENY, "--pre-push", stdin=deletion).returncode == 0


def test_pre_push_reads_an_annotated_tags_own_message(repo):
    head = repo.git("rev-parse", "HEAD")
    repo.git("tag", "-a", "v9", "-m", "release notes\n\nrecorded near Vandermoss")
    tag = repo.git("rev-parse", "v9")
    assert tag != head
    r = repo.run(DENY, "--pre-push", stdin=f"refs/tags/v9 {tag} refs/tags/v9 {ZERO}\n")
    assert r.returncode == 1 and f"tag {tag[:12]} message, line 3" in r.stdout
    assert leaked(r.stdout + r.stderr) == []


def test_pre_push_refuses_a_branch_named_after_a_term(repo):
    head = repo.git("rev-parse", "HEAD")
    r = repo.run(DENY, "--pre-push", stdin=f"refs/heads/x {head} refs/heads/vandermoss-draft {ZERO}\n")
    assert r.returncode == 1 and "branch or tag" in r.stdout
    assert leaked(r.stdout + r.stderr) == []


def test_the_hook_blocks_a_real_push_and_lets_a_clean_one_through(repo, tmp_path):
    """End to end: the committed hook, git's own pre-push call, a bare remote."""
    for rel in (".githooks/pre-push", *(f".github/workflows/scripts/{n}" for n in ("gitrange.py", DENY.name, URLS.name))):
        dst = repo.path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    repo.commit({}, "the hooks")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, env=repo.env)
    repo.git("remote", "add", "origin", str(remote))
    repo.git("config", "core.hooksPath", ".githooks")
    env = dict(repo.env, KP_DENY_LIST=LIST)

    def push():
        return subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repo.path, env=env, capture_output=True, text=True)

    ok = push()
    assert ok.returncode == 0, ok.stdout + ok.stderr
    repo.commit({"a.txt": "Vandermoss\n"}, "a private name")
    blocked = push()
    assert blocked.returncode != 0 and "term #" in blocked.stdout + blocked.stderr
    assert leaked(blocked.stdout + blocked.stderr) == []
    repo.commit({"a.txt": "fine\n"}, "fix: reword")
    assert push().returncode != 0, "the earlier commit is still in the push"
    repo.git("reset", "-q", "--hard", "HEAD~2")
    repo.commit({"b.txt": "fine\n"}, "clean")
    assert push().returncode == 0


# --------------------------------------------------------------------------
# session URLs
# --------------------------------------------------------------------------
SESSION = "Claude-Session: https://claude.ai/code/session_01AbCdEfGhIjKlMnOpQrStUv"


def test_a_seeded_session_trailer_fails_and_its_url_is_not_printed(repo):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.txt": "x\n"}, f"feat: something\n\nbody\n\n{SESSION}")
    r = repo.run(URLS, "--range", f"{base}..{head}", deny=None)
    assert r.returncode == 1
    assert f"commit {head[:12]}, message line 5" in r.stdout
    assert "session_01AbCd" not in r.stdout


def test_session_urls_in_older_history_are_left_alone(repo):
    repo.commit({"a.txt": "x\n"}, f"old\n\n{SESSION}")
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"b.txt": "y\n"}, "fix: clean")
    assert repo.run(URLS, "--range", f"{base}..{head}", deny=None).returncode == 0


def test_session_urls_are_read_from_the_github_event(repo, tmp_path):
    base = repo.git("rev-parse", "HEAD")
    head = repo.commit({"a.txt": "x\n"}, f"feat: x\n\n{SESSION.upper()}")
    r = github_run(repo, URLS, "pull_request", pr_event(base=base, head=head), tmp_path, deny=None)
    assert r.returncode == 1 and "::error::" in r.stdout
    r = github_run(repo, URLS, "pull_request", pr_event(base=head, head=head), tmp_path, deny=None)
    assert r.returncode == 0


def test_session_urls_fail_closed_on_a_bad_range(repo):
    assert repo.run(URLS, "--range", "nope..HEAD", deny=None).returncode == 2


def test_session_urls_in_a_pull_request_or_a_tag_are_found(repo, tmp_path):
    head = repo.git("rev-parse", "HEAD")
    event = pr_event(base=head, head=head)
    event["pull_request"].update(title="feat: x", body=f"summary\n\n{SESSION}")
    r = github_run(repo, URLS, "pull_request", event, tmp_path, deny=None)
    assert r.returncode == 1 and "the pull request body, line 3" in r.stdout and "session_01AbCd" not in r.stdout
    repo.git("tag", "-a", "v9", "-m", f"notes\n\n{SESSION}")
    tag = repo.git("rev-parse", "v9")
    r = repo.run(URLS, "--pre-push", stdin=f"refs/tags/v9 {tag} refs/tags/v9 {ZERO}\n", deny=None)
    assert r.returncode == 1 and f"tag {tag[:12]}, message line 3" in r.stdout


def test_the_three_commits_from_before_the_rule_are_named_and_skipped(monkeypatch, capsys):
    """A clone with no remote-tracking refs reads its whole history on a push;
    the three historic trailers on main must not block it."""
    assert len(csu.BEFORE_THE_RULE) == 3 and all(re.fullmatch(r"[0-9a-f]{40}", c) for c in csu.BEFORE_THE_RULE)
    old, new = sorted(csu.BEFORE_THE_RULE)[0], "f" * 40
    monkeypatch.setattr(csu.gitrange, "commits", lambda spec: [old, new])
    monkeypatch.setattr(csu.gitrange, "tag_messages", lambda specs: {})
    monkeypatch.setattr(csu.gitrange, "git", lambda *a, **k: SESSION.encode())
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert csu.main(["--range", "a..b"]) == 1
    out = capsys.readouterr().out
    assert f"commit {new[:12]}" in out and old[:12] not in out
