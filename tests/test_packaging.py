"""
What actually ends up in the built distribution.

Everything else in this suite tests the source tree. This tests the *artifact*,
because the two differ in exactly one dangerous way: a data file present on
disk and absent from `package-data` works perfectly in development and is
missing for every person who installs from PyPI.

Building a wheel takes a few seconds, so this is one test, run once.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel_contents(tmp_path_factory) -> set[str]:
    out = tmp_path_factory.mktemp("dist")
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "-o", str(out), str(ROOT)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"could not build a wheel here: {proc.stderr.strip()[-300:]}")
    wheels = list(out.glob("*.whl"))
    assert wheels, "build reported success but produced no wheel"
    return set(zipfile.ZipFile(wheels[0]).namelist())


def test_the_bundled_fonts_ship_in_the_wheel(wheel_contents):
    """The bug this exists for: fonts on disk but not in package-data. Every
    overlay role resolves to a file inside the package, so a wheel without them
    installs an engine that raises the first time anyone renders a card -- and
    it works fine from a checkout, so nothing local catches it."""
    fonts = {n for n in wheel_contents if n.endswith(".ttf")}
    assert len(fonts) >= 5, f"expected the bundled fonts, found {sorted(fonts)}"
    for expected in ("Vazirmatn", "SpaceGrotesk", "SpaceMono", "CourierPrime"):
        assert any(expected in f for f in fonts), f"{expected} missing from the wheel"


def test_the_font_licences_ship_with_the_fonts(wheel_contents):
    """SIL OFL requires the licence to travel with the font."""
    licences = {n for n in wheel_contents if "licenses/OFL" in n}
    assert len(licences) >= 4, f"expected an OFL text per family, found {sorted(licences)}"


def test_py_typed_still_ships(wheel_contents):
    """PEP 561: without it, the annotations are invisible downstream."""
    assert any(n.endswith("py.typed") for n in wheel_contents)


def test_no_media_slipped_into_the_distribution(wheel_contents):
    """The repo guardrails check the git tree. This checks the artifact, which
    is what actually reaches other people."""
    media = {".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mov", ".wav", ".mp3"}
    found = [n for n in wheel_contents if Path(n).suffix.lower() in media]
    assert not found, f"media in the wheel: {found}"


def test_the_canvas_engine_carries_the_package_version():
    """The Python package and the canvas engine release together, and every
    canvas render's sidecar (<out>.json) records canvas/package.json's version
    as the tool that made it -- so the two numbers must be the same one. No
    wheel needed: this reads the source tree."""
    import json

    from kaleidophone import __version__

    canvas = json.loads((ROOT / "canvas" / "package.json").read_text(encoding="utf-8"))
    assert canvas["version"] == __version__, (
        f"canvas/package.json is {canvas['version']}, kaleidophone.__version__ is {__version__}: "
        "bump both when releasing"
    )
