"""assets/curation.py: the scoring heuristic, its target-hue fix, and the
starved-station failure mode it doesn't fully eliminate (see
docs/decisions/0004-default-mode-and-auto-curation.md and the
kaleidophone-asset-curation skill).
"""

from __future__ import annotations

import colorsys

import pytest
from factories import make_media_asset, make_station
from PIL import Image

from kaleidophone.assets.curation import _target_hue, scan_media, score_for_station, suggest_stations


def _expected_hue(highlight_hex: str) -> float:
    """The same formula _target_hue() itself documents: hue*180 to match
    OpenCV's 0..180 hue range. Used to pin the *value*, not just show two
    stations differ."""
    h = highlight_hex.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    hue, _sat, _val = colorsys.rgb_to_hsv(r, g, b)
    return hue * 180.0


def test_target_hue_prefers_the_duotone_highlight_over_the_temperature_guess():
    # temperature alone (>= 0) would give the coarse warm guess of 15.0 --
    # a real duotone must override that with the highlight's actual hue.
    station = make_station(temperature=0.55, duotone=("#1a0f06", "#f2b25c"))
    hue = _target_hue(station)
    assert hue == pytest.approx(_expected_hue("#f2b25c"))
    assert hue != pytest.approx(15.0)


def test_target_hue_falls_back_to_the_coarse_temperature_guess_with_no_duotone():
    warm = make_station(temperature=0.5, duotone=None)
    cool = make_station(temperature=-0.5, duotone=None)
    assert _target_hue(warm) == 15.0
    assert _target_hue(cool) == 100.0


def test_two_stations_without_duotone_collapse_onto_the_same_target_hue():
    """This is the exact mechanism behind the bug ADR-0004 documents: without
    a duotone, every warm station (regardless of exact temperature) shares
    one coarse target hue and can't be told apart by the scorer."""
    a = make_station(name="a", temperature=0.5, duotone=None)
    b = make_station(name="b", temperature=0.9, duotone=None)
    assert _target_hue(a) == _target_hue(b)


def test_distinct_duotones_prevent_the_collapse():
    a = make_station(name="a", temperature=0.5, duotone=("#1a0f06", "#f2b25c"))
    b = make_station(name="b", temperature=0.9, duotone=("#050505", "#e8e8e8"))
    assert _target_hue(a) != _target_hue(b)


def test_score_for_station_prefers_a_closer_hue_match():
    station = make_station(duotone=("#1a0f06", "#f2b25c"))
    target = _target_hue(station)
    close = make_media_asset("close.jpg", hue=target, saturation=0.5, brightness=0.55)
    far = make_media_asset("far.jpg", hue=(target + 90) % 180, saturation=0.5, brightness=0.55)
    assert score_for_station(close, station) > score_for_station(far, station)


def test_suggest_stations_assigns_each_asset_to_its_best_scoring_station():
    warm = make_station(name="warm", duotone=("#1a0f06", "#f2b25c"))
    cool = make_station(name="cool", duotone=("#050505", "#e8e8e8"))
    warm_asset = make_media_asset("warm.jpg", hue=_target_hue(warm))
    cool_asset = make_media_asset("cool.jpg", hue=_target_hue(cool))

    buckets = suggest_stations([warm_asset, cool_asset], [warm, cool])

    assert buckets["warm"] == [warm_asset]
    assert buckets["cool"] == [cool_asset]


def test_suggest_stations_can_starve_a_station_when_two_share_a_target_hue():
    """Documents the real failure mode rather than just avoiding it -- see
    the kaleidophone-asset-curation skill, 'why the heuristic sometimes gets it
    visibly wrong'. This is exactly what build_default_brief() (see
    tests/test_autobrief.py) has to defend against downstream."""
    a = make_station(name="a", temperature=0.5, duotone=None)
    b = make_station(name="b", temperature=0.9, duotone=None)
    assets = [make_media_asset(f"{i}.jpg", hue=15.0) for i in range(5)]

    buckets = suggest_stations(assets, [a, b])

    assert sum(len(v) for v in buckets.values()) == 5
    assert len(buckets["a"]) == 0 or len(buckets["b"]) == 0


def test_scan_media_scores_synthetic_images_in_deterministic_order(tmp_path):
    # Tiny procedurally-generated images -- same pattern as
    # examples/demo/generate_fixtures.py. Never real photos; see AGENTS.md.
    Image.new("RGB", (32, 32), (240, 180, 90)).save(tmp_path / "b.jpg")
    Image.new("RGB", (32, 32), (20, 30, 200)).save(tmp_path / "a.jpg")

    assets = scan_media(str(tmp_path))

    assert [a.path for a in assets] == sorted(a.path for a in assets)
    assert all(a.kind == "image" for a in assets)
    assert all(0.0 <= a.mean_saturation <= 1.0 for a in assets)
