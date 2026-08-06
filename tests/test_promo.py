"""promo/plan.py: the templated promo-pack generator.

See the kaleidophone-promo-pack skill -- templated from structured facts, not
free-form generated text, so its output is safe to assert on directly.
"""

from __future__ import annotations

from factories import make_analysis, make_brief, make_section, make_station

from kaleidophone.audio.analysis import EnergyJump
from kaleidophone.promo.plan import generate_promo_pack
from kaleidophone.timeline.schema import PromoConfig


def test_promo_pack_includes_a_chapter_per_section():
    stations = [make_station(name="s")]
    sections = [
        make_section(name="INTRO", start=0.0, end=10.0, station="s"),
        make_section(name="DROP", start=10.0, end=20.0, station="s"),
    ]
    brief = make_brief(stations=stations, sections=sections)
    analysis = make_analysis(duration=20.0)

    pack = generate_promo_pack(brief, analysis)

    assert "INTRO" in pack
    assert "DROP" in pack
    assert "0:00" in pack  # INTRO's start, formatted by _fmt_time


def test_promo_pack_omits_the_pinned_comment_section_with_no_energy_jump():
    brief = make_brief()
    analysis = make_analysis(duration=10.0, energy_jumps=())

    pack = generate_promo_pack(brief, analysis)

    assert "pinned comment" not in pack.lower()


def test_promo_pack_pinned_comment_uses_the_strongest_jump_not_just_any_jump():
    brief = make_brief()
    analysis = make_analysis(
        duration=10.0,
        energy_jumps=(
            EnergyJump(time=2.0, onset_strength=0.5, z_score=2.1),
            EnergyJump(time=7.0, onset_strength=0.9, z_score=4.5),  # the strongest
        ),
    )

    pack = generate_promo_pack(brief, analysis)

    assert "0:07" in pack
    assert "0:02" not in pack


def test_promo_pack_never_shows_collaborators_unless_promo_config_sets_handles():
    brief = make_brief()  # promo=None by default
    analysis = make_analysis(duration=10.0)

    assert "Collaborators" not in generate_promo_pack(brief, analysis)


def test_promo_pack_lists_configured_handles():
    brief = make_brief(promo=PromoConfig(handles=["@example"], teaser_cadence_days=[-7]))
    analysis = make_analysis(duration=10.0)

    pack = generate_promo_pack(brief, analysis)

    assert "@example" in pack
    assert "T-7" in pack
