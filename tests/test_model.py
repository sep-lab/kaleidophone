"""EDL/Cut: overlap validation and JSON round-tripping.

See docs/decisions/0001-version-the-brief-not-the-render.md -- the EDL is a
derived build artifact (regenerate it, don't hand-edit it), but it does get
written to and read back from edl.json between `mvideo compose` and
`mvideo silent`, so the round trip has to be exact.
"""

from __future__ import annotations

import pytest

from mvideo.timeline.model import EDL, Cut


def _cut(index: int, start: float, end: float, **overrides) -> Cut:
    fields = {"source_path": f"/media/{index}.jpg", "station": "s", "section": "SEC"}
    fields.update(overrides)
    return Cut(index=index, start=start, end=end, **fields)


def test_cut_duration_is_end_minus_start():
    assert _cut(0, 1.0, 3.5).duration == pytest.approx(2.5)


def test_edl_accepts_back_to_back_cuts_that_touch_but_dont_overlap():
    edl = EDL(
        song_title="t",
        audio_path="a.wav",
        duration=10.0,
        fps=24,
        resolution=(1280, 720),
        cuts=(_cut(0, 0.0, 5.0), _cut(1, 5.0, 10.0)),
    )
    assert len(edl.cuts) == 2


def test_edl_rejects_overlapping_cuts():
    with pytest.raises(ValueError, match="overlap"):
        EDL(
            song_title="t",
            audio_path="a.wav",
            duration=10.0,
            fps=24,
            resolution=(1280, 720),
            cuts=(_cut(0, 0.0, 5.0), _cut(1, 4.0, 10.0)),
        )


def test_edl_to_dict_from_dict_round_trips_exactly():
    edl = EDL(
        song_title="t",
        audio_path="a.wav",
        duration=10.0,
        fps=24,
        resolution=(1280, 720),
        cuts=(
            _cut(0, 0.0, 5.0, effects=("grain", "vignette"), is_beat_aligned=False),
            _cut(1, 5.0, 10.0),
        ),
    )
    restored = EDL.from_dict(edl.to_dict())
    assert restored == edl


def test_to_dict_resolution_is_a_json_safe_list():
    edl = EDL(song_title="t", audio_path="a.wav", duration=1.0, fps=24, resolution=(1280, 720), cuts=())
    assert edl.to_dict()["resolution"] == [1280, 720]
