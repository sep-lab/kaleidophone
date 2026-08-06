"""render/preview.py: the no-ffmpeg contact sheet -- the 'confirm before you
render' half of the workflow (see the mvideo-render skill)."""

from __future__ import annotations

import pytest
from PIL import Image

from mvideo.render.preview import generate_contact_sheet
from mvideo.timeline.model import EDL, Cut

CELL = 160


def _cut(index: int, start: float, end: float, source_path: str, **overrides) -> Cut:
    fields = {"station": "s", "section": "SEC", "effects": ()}
    fields.update(overrides)
    return Cut(index=index, start=start, end=end, source_path=source_path, **fields)


def test_generate_contact_sheet_raises_on_an_empty_edl(tmp_path):
    edl = EDL(song_title="t", audio_path="a.wav", duration=0.0, fps=24, resolution=(1280, 720), cuts=())
    with pytest.raises(ValueError, match="no cuts"):
        generate_contact_sheet(edl, str(tmp_path / "sheet.jpg"))


def test_generate_contact_sheet_sizes_the_grid_to_cuts_and_columns(tmp_path):
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (40, 40), (200, 100, 50)).save(photo)

    cuts = tuple(_cut(i, float(i), float(i + 1), str(photo)) for i in range(3))
    edl = EDL(song_title="t", audio_path="a.wav", duration=3.0, fps=24, resolution=(1280, 720), cuts=cuts)
    out = tmp_path / "sheet.jpg"

    generate_contact_sheet(edl, str(out), columns=2)

    with Image.open(out) as img:
        # 3 cuts at 2 columns -> 2 rows
        assert img.size == (2 * CELL, 2 * (CELL + 24))


def test_generate_contact_sheet_falls_back_to_a_placeholder_tile_for_an_unreadable_source(tmp_path):
    # A missing/corrupt source must render a visible placeholder, not crash
    # the whole preview over one bad path.
    cuts = (_cut(0, 0.0, 1.0, str(tmp_path / "does-not-exist.jpg")),)
    edl = EDL(song_title="t", audio_path="a.wav", duration=1.0, fps=24, resolution=(1280, 720), cuts=cuts)
    out = tmp_path / "sheet.jpg"

    generate_contact_sheet(edl, str(out), columns=1)

    with Image.open(out) as img:
        assert img.size == (CELL, CELL + 24)
