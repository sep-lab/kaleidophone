"""assets/stations.py: the built-in presets and preset()'s copy semantics."""

from __future__ import annotations

import pytest

from mvideo.assets.stations import PRESETS, preset


def test_every_preset_key_matches_its_own_station_name():
    for name, station in PRESETS.items():
        assert station.name == name


def test_preset_returns_an_independent_deep_copy():
    a = preset("amber-room")
    a.media_dir = "/somewhere/only/a/points/at"
    a.duotone = ("#000000", "#ffffff")

    b = preset("amber-room")

    assert b.media_dir is None
    assert b.duotone == ("#1a0f06", "#f2b25c")
    assert PRESETS["amber-room"].media_dir is None  # the module-level preset itself must stay untouched


def test_preset_unknown_name_raises_a_helpful_key_error():
    with pytest.raises(KeyError, match="amber-room"):
        preset("not-a-real-station")


def test_every_preset_has_its_own_duotone():
    """A preset with no duotone falls back to assets/curation.py's coarse
    warm/cool guess (_target_hue()), which two or more presets can easily
    share -- exactly the mechanism ADR-0004 documents. fire-leak used to be
    the one preset with duotone=None, and collapsed onto amber-room's target
    hue in practice; see CHANGELOG.md and tests/test_curation.py."""
    for name, station in PRESETS.items():
        assert station.duotone is not None, f"{name} has no duotone -- see _target_hue()'s fallback"


def test_no_two_presets_share_the_exact_same_duotone():
    duotones = [s.duotone for s in PRESETS.values()]
    assert len(duotones) == len(set(duotones))
