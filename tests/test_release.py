"""
The release pack: per-platform copy templated from facts the brief already has.

What these tests protect is not prose quality -- it is that every *number* in
the pack is derived rather than invented, and that the pack says so wherever it
is guessing.
"""

from __future__ import annotations

import pytest

from kaleidophone.audio.analysis import EnergyJump
from kaleidophone.release.copy import (
    MIN_DURATION_FOR_PINNED_COMMENT,
    MIN_PINNED_COMMENT_TIME,
    generate_release_pack,
)
from kaleidophone.timeline.schema import Credit, ReleaseConfig
from tests.factories import make_analysis, make_brief, make_section, make_station


def pack(*, release=None, sections=None, analysis=None, **brief_kw) -> str:
    stations = [make_station("s", description="Warm interiors, lamplight")]
    sections = sections or [make_section(station="s", start=0.0, end=60.0)]
    brief = make_brief(stations=stations, sections=sections, release=release, **brief_kw)
    return generate_release_pack(brief, analysis or make_analysis(duration=60.0))


def test_the_pack_says_up_front_that_the_voice_is_not_derived():
    """A pack that read as finished copy would get pasted as finished copy."""
    out = pack()
    assert "scaffold to rewrite" in out
    assert "The voice is not" in out


def test_chapters_come_from_the_sections():
    out = pack(sections=[
        make_section(name="PENDULUM", station="s", start=0.0, end=30.0),
        make_section(name="THE SWITCH", station="s", start=30.0, end=60.0),
    ])
    assert "0:00 PENDULUM" in out
    assert "0:30 THE SWITCH" in out


def test_timed_comments_skip_the_opening_section():
    """A timed comment at 0:00 is not a comment on a moment."""
    out = pack(sections=[
        make_section(name="INTRO", station="s", start=0.0, end=30.0),
        make_section(name="THE HUSH", station="s", start=30.0, end=60.0),
    ])
    block = out.split("## Timed comments")[1]
    assert "THE HUSH" in block and "INTRO" not in block


# --------------------------------------------------------------------------
# the pinned comment, which is the one number most likely to be wrong
# --------------------------------------------------------------------------
def test_a_real_mid_song_jump_becomes_a_pinned_comment():
    analysis = make_analysis(duration=200.0, energy_jumps=(EnergyJump(time=128.4, z_score=4.2, onset_strength=3.0),))
    assert "the switch is at 2:08" in pack(analysis=analysis)


def test_a_jump_in_the_opening_seconds_is_not_a_switch():
    """It is the track starting. Suggesting `the switch is at 0:00` reads as the
    tool not having listened, which costs more than saying nothing."""
    analysis = make_analysis(
        duration=200.0, energy_jumps=(EnergyJump(time=0.53, z_score=9.9, onset_strength=9.0),)
    )
    out = pack(analysis=analysis)
    assert "Pinned comment" not in out
    assert "the song starting" in out, "and it should explain why there isn't one"


def test_the_strongest_qualifying_jump_wins_not_the_strongest_overall():
    analysis = make_analysis(duration=200.0, energy_jumps=(
        EnergyJump(time=1.0, z_score=9.9, onset_strength=9.0),      # louder, but it is the intro
        EnergyJump(time=95.0, z_score=3.1, onset_strength=2.0),
    ))
    assert "the switch is at 1:35" in pack(analysis=analysis)


def test_a_short_track_gets_no_pinned_comment():
    analysis = make_analysis(
        duration=MIN_DURATION_FOR_PINNED_COMMENT - 1,
        energy_jumps=(EnergyJump(time=MIN_PINNED_COMMENT_TIME + 5, z_score=5.0, onset_strength=4.0),),
    )
    assert "Pinned comment" not in pack(analysis=analysis)


# --------------------------------------------------------------------------
# what it knows it doesn't know
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "release,expected",
    [
        (None, "No `release.concept` set"),
        (ReleaseConfig(concept="x"), "No credits in the brief"),
        (ReleaseConfig(concept="x"), "No tags set"),
        (ReleaseConfig(concept="x"), "No links set"),
        (ReleaseConfig(concept="x", secondary_language="fa"), "written, not translated"),
    ],
)
def test_the_notes_section_names_each_gap(release, expected):
    """The gaps are exactly where a person's attention is worth most, so a pack
    that only produced confident-looking output would be worse."""
    assert expected in pack(release=release)


def test_a_second_language_block_is_left_blank_on_purpose():
    out = pack(release=ReleaseConfig(secondary_language="fa"))
    assert "Description — fa" in out
    assert "mirror" in out, "and it should say to write it, not translate it"


def test_credits_render_with_handles_only_where_there_is_one():
    out = pack(release=ReleaseConfig(
        credits=[Credit(role="mix", name="A", handle="@a"), Credit(role="mpc", name="B")]
    ))
    assert "mix: A (@a)" in out
    assert "mpc: B\n" in out


# --------------------------------------------------------------------------
# platforms
# --------------------------------------------------------------------------
def test_only_the_requested_platforms_appear():
    out = pack(release=ReleaseConfig(platforms=["soundcloud"]))
    assert "## SoundCloud" in out
    assert "## YouTube" not in out and "## Story" not in out


def test_the_posting_order_puts_the_link_destination_before_what_points_at_it():
    out = pack(release=ReleaseConfig(platforms=["story", "soundcloud", "instagram"]))
    block = out.split("## Posting order")[1]
    assert block.index("soundcloud") < block.index("instagram") < block.index("story")


def test_a_story_gets_a_layout_not_a_caption():
    """It is a placement problem, not a writing one."""
    out = pack(release=ReleaseConfig(platforms=["story"]))
    assert "Sticker text" in out and "Placement" in out


def test_the_concept_line_leads_every_platform_block():
    out = pack(release=ReleaseConfig(concept="the flower that grows where nothing should"))
    assert out.count("the flower that grows where nothing should") >= 3


def test_no_release_block_still_produces_a_usable_pack():
    """A brief that never mentions `release` should not crash -- it should
    produce the derived half and say what is missing."""
    out = pack(release=None)
    assert "## SoundCloud" in out
    assert "Notes for you" in out
