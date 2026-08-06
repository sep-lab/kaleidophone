"""render/effects.py: filter-string builders.

Pure string logic, no ffmpeg subprocess call and no real media -- see the
kaleidophone-render skill for the render pipeline this feeds into. A few of these
tests pin the specific bugs called out in the project history (see
CHANGELOG.md / this session's fixes) so they can't silently come back.
"""

from __future__ import annotations

import typing

from factories import make_station

from kaleidophone.render.effects import (
    GRAPH_EFFECT_BUILDERS,
    LINEAR_EFFECT_BUILDERS,
    color_grade,
    halation,
    kaleidoscope,
    scanlines,
    strobe,
)
from kaleidophone.timeline.schema import EffectName


def test_every_schema_effect_name_has_exactly_one_builder():
    linear = set(LINEAR_EFFECT_BUILDERS)
    graph = set(GRAPH_EFFECT_BUILDERS)
    assert linear.isdisjoint(graph)
    assert linear | graph == set(typing.get_args(EffectName))


def test_graph_effects_are_explicitly_bound_to_input_0():
    # An unbound pad in a multi-pass filter_complex chain is ambiguous about
    # which input feeds it -- every graph effect must open with [0:v].
    assert kaleidoscope().startswith("[0:v]")
    assert halation().startswith("[0:v]")


def test_strobe_never_drops_a_frame():
    # A `select`-based strobe would drop frames, shortening the segment and
    # desyncing audio. Must stay a per-frame `eq` brightness pulse.
    assert "select" not in strobe()
    assert "eq" in strobe()


def test_scanlines_avoids_a_per_pixel_geq_expression():
    # geq needs manual comma-escaping for its per-pixel expression; drawgrid
    # doesn't. See render/effects.py's own module docstring.
    assert "geq" not in scanlines()
    assert "drawgrid" in scanlines()


def test_color_grade_includes_duotone_curves_only_when_the_station_has_one():
    with_duotone = make_station(duotone=("#1a0f06", "#f2b25c"))
    without_duotone = make_station(duotone=None)
    assert "curves=" in color_grade(with_duotone)
    assert "curves=" not in color_grade(without_duotone)


def test_color_grade_omits_vignette_and_grain_filters_when_zero():
    flat = make_station(duotone=None, vignette=0.0, grain=0.0)
    grade = color_grade(flat)
    assert "vignette=" not in grade
    assert "noise=" not in grade


def test_color_grade_includes_vignette_and_grain_filters_when_set():
    textured = make_station(duotone=None, vignette=0.3, grain=0.2)
    grade = color_grade(textured)
    assert "vignette=" in grade
    assert "noise=" in grade
