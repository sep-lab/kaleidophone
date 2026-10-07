"""The demo's edit stays byte for byte what it is: ADR-0001's "same brief, same edit, every re-render".

The demo (examples/demo/) is the one brief every checkout can rebuild. This test generates its synthetic
fixtures, runs the real `kaleidophone run --preview-only` on them (analyse, curate, compose: everything
that decides the edit, and no ffmpeg), and compares the edl.json it writes with
tests/golden/demo_edl.json. The fixture folder's path is the one thing replaced, by "<fixtures>".

A change here changes the edit of every brief like it. If that is meant -- a fix with a measured
before/after, or new behaviour behind a brief field the demo doesn't set -- re-record the golden with

    python tests/test_golden_edl.py --update

and say why in the PR. A change that moves existing briefs' edits with no opt-in in the brief is what this
test exists to stop.
"""

from __future__ import annotations

import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "demo_edl.json"
FIXTURES = "<fixtures>"


def demo_edl(where: Path) -> str:
    """The demo's edl.json, as `kaleidophone run` writes it, with the fixture folder named <fixtures>."""
    from kaleidophone import cli

    subprocess.run(
        [sys.executable, str(ROOT / "examples" / "demo" / "generate_fixtures.py"), "--out", str(where)],
        check=True,
        capture_output=True,
    )
    out = where / "out"
    assert cli.main(["run", str(where / "brief.yaml"), "-o", str(out), "--preview-only"]) == 0
    return (out / "edl.json").read_text(encoding="utf-8").replace(str(where), FIXTURES)


def test_the_demo_edit_is_byte_for_byte_the_golden_one(tmp_path):
    got = demo_edl(tmp_path)
    want = GOLDEN.read_text(encoding="utf-8")
    if got != want:
        diff = "".join(
            difflib.unified_diff(
                want.splitlines(keepends=True), got.splitlines(keepends=True), "golden", "now", n=2
            )
        )
        raise AssertionError(
            "the demo's edit changed: every brief like it now cuts differently (ADR-0001). If that is meant, "
            "re-record with `python tests/test_golden_edl.py --update` and say why in the PR.\n" + diff[:4000]
        )


def test_the_golden_names_no_real_path():
    text = GOLDEN.read_text(encoding="utf-8")
    assert f'"audio_path": "{FIXTURES}/song.wav"' in text
    assert '"/' not in text.replace(f'"{FIXTURES}/', "")


if __name__ == "__main__":
    if sys.argv[1:] != ["--update"]:
        sys.exit("usage: python tests/test_golden_edl.py --update   (re-records tests/golden/demo_edl.json)")
    with tempfile.TemporaryDirectory(prefix="kp-golden-edl-") as d:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(demo_edl(Path(d)), encoding="utf-8")
    print(f"wrote {GOLDEN.relative_to(ROOT)}")
