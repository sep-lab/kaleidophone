"""CreativeBrief/SectionConfig validation and YAML round-tripping.

See docs/decisions/0001-version-the-brief-not-the-render.md -- the brief is
the one file a person hand-authors, so its validation errors need to be
clear and its serialization needs to actually work (see the mode="json"
note on test_model_dump_json_mode_is_yaml_safe below).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from factories import make_brief, make_section, make_station
from pydantic import ValidationError

from mvideo.timeline.schema import CreativeBrief

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_section_end_equal_to_start_is_rejected():
    with pytest.raises(ValidationError):
        make_section(start=10.0, end=10.0)


def test_section_end_before_start_is_rejected():
    with pytest.raises(ValidationError):
        make_section(start=10.0, end=5.0)


def test_section_end_after_start_is_accepted():
    section = make_section(start=0.0, end=10.0)
    assert section.end > section.start


def test_brief_rejects_a_section_referencing_an_unknown_station():
    station = make_station(name="known")
    bad_section = make_section(name="X", station="unknown")
    with pytest.raises(ValidationError, match="unknown"):
        make_brief(stations=[station], sections=[bad_section])


def test_brief_accepts_a_section_matching_a_defined_station():
    station = make_station(name="known")
    section = make_section(station="known")
    brief = make_brief(stations=[station], sections=[section])
    assert brief.sections[0].station == "known"


def test_output_and_promo_defaults():
    brief = make_brief()
    assert brief.output.resolution == (1280, 720)
    assert brief.output.fps == 24
    assert brief.promo is None  # promo is opt-in, not required to render anything


def test_from_yaml_parses_the_love_case_study_brief():
    """examples/love/brief.yaml is a real structural reconstruction (see
    docs/case-studies/love.md) -- a genuinely worked 7-section, 4-station
    brief, not a toy fixture, so it's worth parsing directly rather than
    only ever testing synthetic minimal briefs."""
    brief = CreativeBrief.from_yaml(REPO_ROOT / "examples" / "love" / "brief.yaml")

    assert len(brief.stations) == 4
    assert len(brief.sections) == 7
    assert {s.name for s in brief.stations} == {"amber-room", "noir-crush", "gold-hour", "fire-leak"}
    assert max(s.end for s in brief.sections) == pytest.approx(655.0)  # the real song's length, ~10:55
    assert brief.song.bpm == pytest.approx(129.0)
    assert brief.promo.handles == []  # scrubbed -- see AGENTS.md, never a real handle in this repo


def test_model_dump_json_mode_is_yaml_safe():
    """`_write_yaml_brief()` (cli.py) uses model_dump(mode="json") specifically
    so tuple fields serialize as plain lists -- yaml.safe_dump cannot
    represent a raw Python tuple. Pin that contract directly."""
    brief = make_brief()
    data = brief.model_dump(exclude_none=True, mode="json")
    assert isinstance(data["output"]["resolution"], list)
    assert isinstance(data["stations"][0]["duotone"], list)
    yaml.safe_dump(data, sort_keys=False)  # must not raise


def test_brief_round_trips_through_yaml(tmp_path):
    brief = make_brief()
    data = brief.model_dump(exclude_none=True, mode="json")
    out = tmp_path / "brief.yaml"
    out.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    reloaded = CreativeBrief.from_yaml(out)

    assert reloaded == brief
