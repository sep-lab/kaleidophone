"""release/local_llm.py and `kaleidophone kit --llm`: caption drafts from a model on this machine.

No model and no network here: the module's opener (`_open`) is replaced by a fake server that
records the request and answers like Ollama's /api/chat does -- except where what's under test
is the opener itself, against real HTTP servers on 127.0.0.1: that a proxy the environment names
is never used. What's under test is the request (schema-constrained, seeded, non-streaming,
straight to the host, nothing invented), the refusal of incomplete or misshapen replies, the
errors a person can act on -- every one a LocalModelError, so `kit` still writes the pack --
and how the drafts land in it: Persian written as Persian, rule breaks flagged.
"""

from __future__ import annotations

import http.client
import http.server
import io
import json
import threading
import urllib.error
import urllib.request

import pytest
import yaml
from factories import make_analysis, make_brief, make_section, make_station

from kaleidophone import cli
from kaleidophone.audio.analysis import EnergyJump
from kaleidophone.release import generate_release_pack, minimal_brief, release_facts
from kaleidophone.release import local_llm as llm
from kaleidophone.timeline.schema import ReleaseConfig

SURFACES = ["soundcloud", "youtube", "instagram", "story"]


def reply_for(surfaces, secondary=True, **override):
    body = {s: {"primary": f"{s} line", **({"secondary": f"{s} آینه"} if secondary else {})} for s in surfaces}
    body.update(override)
    return {"message": {"role": "assistant", "content": json.dumps(body, ensure_ascii=False)}}


class Reply(io.BytesIO):
    """A response body that records how much was asked of it."""

    def __init__(self, data, reads):
        super().__init__(data)
        self.reads = reads

    def read(self, size=-1):
        self.reads.append(size)
        return super().read(size)


class FakeServer:
    """Stands in for the opener: records each request, answers with `reply` or raises `error`."""

    def __init__(self, reply=None, error=None, raw=None):
        self.reply, self.error, self.raw, self.requests, self.reads = reply, error, raw, [], []

    def __call__(self, req, timeout=None):
        self.requests.append({"url": req.full_url, "body": json.loads(req.data), "timeout": timeout})
        if self.error is not None:
            raise self.error
        data = self.raw if self.raw is not None else json.dumps(self.reply).encode()
        return Reply(data, self.reads)


@pytest.fixture
def server(monkeypatch):
    def install(**kw):
        fake = FakeServer(**kw)
        monkeypatch.setattr(llm, "_open", fake)
        return fake

    return install


@pytest.fixture
def loopback():
    """Real HTTP servers on 127.0.0.1: each answers every POST with `reply` and records it."""
    servers = []

    def start(reply):
        hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append((self.path, self.rfile.read(int(self.headers.get("Content-Length", 0)))))
                body = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_port}", hits

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


# --------------------------------------------------------------------------- parsing and helpers
def test_a_model_spec_keeps_the_colons_in_the_model_name():
    spec = llm.parse_model_spec("ollama:qwen3:8b")
    assert (spec.provider, spec.model, spec.label) == ("ollama", "qwen3:8b", "ollama · qwen3:8b")


@pytest.mark.parametrize("bad", ["qwen3", "ollama:", "ollama:  ", "openai:gpt-x", ":model"])
def test_a_model_spec_that_isnt_ollama_provider_model_is_refused(bad):
    with pytest.raises(ValueError):
        llm.parse_model_spec(bad)


@pytest.mark.parametrize(
    ("host", "local"),
    [
        ("http://127.0.0.1:11434", True),
        ("http://localhost:11434", True),
        ("http://[::1]:11434", True),
        ("http://studio-mac.local:11434", False),
        ("https://example.com", False),
    ],
)
def test_only_this_machine_counts_as_local(host, local):
    assert llm.is_local(host) is local


def test_the_schema_asks_for_every_surface_and_only_the_languages_in_play():
    with_mirror = llm.caption_schema(["instagram", "story"], secondary=True)
    assert with_mirror["required"] == ["instagram", "story"]
    assert with_mirror["properties"]["story"]["required"] == ["primary", "secondary"]
    alone = llm.caption_schema(["youtube"], secondary=False)
    assert alone["properties"]["youtube"]["required"] == ["primary"]


def test_the_prompt_carries_the_concept_the_facts_and_the_languages():
    prompt = llm.build_prompt(
        title="SONG",
        artist="the artist",
        concept="the line everything grows from",
        mood="warm, slow",
        facts=["release date 2026-10-01"],
        surfaces=["instagram"],
        primary_language="en",
        secondary_language="fa",
    )
    assert "SONG — by the artist" in prompt and "the line everything grows from" in prompt
    assert "Mood words: warm, slow" in prompt and "- release date 2026-10-01" in prompt
    assert "Persian (Farsi)" in prompt and "mirror" in prompt
    bare = llm.build_prompt(
        title="S",
        artist=None,
        concept=None,
        mood="",
        facts=[],
        surfaces=["story"],
        primary_language="xx",
        secondary_language=None,
    )
    assert "(none given)" in bare and "Mood words" not in bare and "Facts" not in bare and "in xx" in bare


def test_the_request_is_seeded_non_streaming_and_schema_constrained():
    body = llm.request_body("qwen3:8b", "hi", {"type": "object"})
    assert body["stream"] is False and body["format"] == {"type": "object"}
    assert body["options"]["seed"] == llm.SEED
    assert body["messages"][0]["role"] == "system" and "no hashtags" in body["messages"][0]["content"]


def test_the_model_is_told_to_keep_the_names_as_they_are():
    assert (
        "Write the title and the artist name exactly as given, in their original script; never translate or "
        "transliterate them." in llm.SYSTEM
    )


@pytest.mark.parametrize(
    ("host", "url"),
    [
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        (" https://studio.local:11434/ ", "https://studio.local:11434"),
        ("HTTP://[::1]:11434", "HTTP://[::1]:11434"),
    ],
)
def test_a_model_server_is_an_http_or_https_url(host, url):
    assert llm.check_host(host) == url


@pytest.mark.parametrize(
    "host",
    ["file:///etc/hostname#", "ftp://127.0.0.1/", "127.0.0.1:11434", "http://", "http://127.0.0.1:99999",
     "http://127.0.0.1:port", "http://[::1", "http://127.0.0.1:0"],
)
def test_anything_else_is_refused_before_a_byte_is_sent(server, host):
    """A file:// "server" would read a file on this machine into the error message."""
    fake = server(reply=reply_for(["youtube"], secondary=False))
    with pytest.raises(ValueError, match=r"--llm-host wants an http:// or https:// URL, like http://127\.0\.0\.1:11434"):
        llm.check_host(host)
    with pytest.raises(llm.LocalModelError, match="wants an http:// or https:// URL"):
        llm.chat(host, {"model": "x"})
    assert fake.requests == []


# --------------------------------------------------------------------------- talking to the server
def test_drafts_come_back_per_surface_from_one_local_request(server):
    fake = server(reply=reply_for(["instagram", "story"]))
    drafts = llm.draft_captions(
        llm.parse_model_spec("ollama:qwen3:8b"),
        title="SONG",
        artist=None,
        concept="c",
        mood="",
        facts=[],
        surfaces=["instagram", "story", "tiktok"],  # an unknown surface is dropped, not sent
        primary_language="en",
        secondary_language="fa",
        timeout=12,
    )
    assert drafts == {  # the Persian mirrors as Persian is written: the Latin word isolated
        "instagram": {"primary": "instagram line", "secondary": f"{llm.FSI}instagram{llm.PDI} آینه"},
        "story": {"primary": "story line", "secondary": f"{llm.FSI}story{llm.PDI} آینه"},
    }
    (req,) = fake.requests
    assert req["url"] == "http://127.0.0.1:11434/api/chat" and req["timeout"] == 12
    assert req["body"]["model"] == "qwen3:8b"
    assert req["body"]["format"]["required"] == ["instagram", "story"]


def test_no_known_surface_means_no_request(server):
    fake = server(reply=reply_for([]))
    spec = llm.parse_model_spec("ollama:m")
    kw = {"artist": None, "concept": None, "mood": "", "facts": [], "primary_language": "en"}
    assert llm.draft_captions(spec, title="S", surfaces=["tiktok"], secondary_language=None, **kw) == {}
    assert fake.requests == []


@pytest.mark.parametrize(
    ("error", "says"),
    [
        (urllib.error.URLError(ConnectionRefusedError(61, "refused")), "no local model server"),
        (TimeoutError("slow"), "no local model server"),
        (
            urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b'{"error":"model \'x\' not found"}')),
            "ollama pull",
        ),
        (urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"oops")), "HTTP 500"),
        # Something on the port that isn't Ollama: an SSH banner where a status line should be.
        (http.client.BadStatusLine("SSH-2.0-OpenSSH_9.6\r\n"),
         r"didn't answer as an Ollama server does \(BadStatusLine: SSH-2\.0-OpenSSH_9\.6\) -- check --llm-host"),
        (http.client.IncompleteRead(b"{"), "didn't answer as an Ollama server does"),
        (UnicodeError("label empty or too long"), "UnicodeError: label empty or too long"),
    ],
)
def test_server_failures_say_what_to_do(server, error, says):
    server(error=error)
    with pytest.raises(llm.LocalModelError, match=says):
        llm.chat("http://127.0.0.1:11434", {"model": "x"})


@pytest.mark.parametrize("raw", [b"<html>proxy</html>", b"[" * 100_000, b"\xff\xfe\x00"])
def test_a_reply_that_isnt_json_is_refused(server, raw):
    server(raw=raw)
    with pytest.raises(llm.LocalModelError, match="isn't JSON"):
        llm.chat("http://127.0.0.1:11434", {"model": "x"})


def test_the_reply_is_read_to_a_bound(server, monkeypatch):
    assert llm.MAX_REPLY_BYTES == 4_000_000  # a reply of captions is a few kB
    monkeypatch.setattr(llm, "MAX_REPLY_BYTES", 100)
    fake = server(raw=b" " * 90 + b'{"a": 1}')
    assert llm.chat("http://127.0.0.1:11434", {"model": "x"}) == {"a": 1}
    fake = server(raw=b" " * 95 + b'{"a": 1}')
    with pytest.raises(llm.LocalModelError, match=r"sent more than .* MB: that isn't a reply of captions"):
        llm.chat("http://127.0.0.1:11434", {"model": "x"})
    assert fake.reads == [101]  # never more than the bound and the one byte that says it's over


def test_the_request_never_goes_through_a_proxy(loopback, monkeypatch):
    """urlopen sends a request for 127.0.0.1 to http_proxy when no_proxy doesn't list it: the
    brief's concept would leave the machine. The module's opener goes straight to the host."""
    ollama, asked = loopback(reply_for(["youtube"], secondary=False))
    proxy, proxied = loopback({"error": "this is the proxy"})
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, proxy)
    with urllib.request.urlopen(urllib.request.Request(ollama + "/api/chat", data=b"{}"), timeout=10) as resp:
        assert json.load(resp) == {"error": "this is the proxy"}  # what urlopen does
    assert [path for path, _ in proxied] == [ollama + "/api/chat"] and asked == []
    body = llm.request_body("m", "Concept: an unreleased song", llm.caption_schema(["youtube"], False))
    reply = llm.chat(ollama, body, timeout=10)
    assert llm.parse_reply(reply, ["youtube"], secondary=False) == {"youtube": {"primary": "youtube line"}}
    assert [path for path, _ in asked] == ["/api/chat"] and b"an unreleased song" in asked[0][1]
    assert len(proxied) == 1  # the proxy saw nothing of it


@pytest.mark.parametrize(
    ("reply", "says"),
    [
        ({"message": {"content": ""}}, "empty reply"),
        ({}, "empty reply"),
        ({"message": {"content": "not json"}}, "isn't the JSON"),
        ({"message": {"content": json.dumps([1, 2])}}, "no 'story' block"),
        ({"message": {"content": "[" * 100_000}}, "isn't the JSON"),
        ([], r"isn't an Ollama chat reply: \[\]"),
        ({"message": "x"}, r"isn't an Ollama chat reply: \{\"message\": \"x\"\}"),
        ("text", "isn't an Ollama chat reply"),
        (reply_for(["story"], secondary=False), r"story\.secondary empty"),
        (reply_for(["story"], story={"primary": "  ", "secondary": "x"}), r"story\.primary empty"),
    ],
)
def test_an_incomplete_reply_is_refused_not_half_used(reply, says):
    with pytest.raises(llm.LocalModelError, match=says):
        llm.parse_reply(reply, ["story"], secondary=True)


# --------------------------------------------------------------------------- what comes back
@pytest.mark.parametrize(
    ("text", "names", "written"),
    [
        # Arabic yeh and kaf become Persian's own.
        ("كتاب يك", (), "کتاب یک"),
        # A Latin title is isolated whole, its question mark with it.
        ("آهنگ SHOULD I ? را بشنو", (), "آهنگ \u2068SHOULD I ?\u2069 را بشنو"),
        ("SHOULD I ?", (), "\u2068SHOULD I ?\u2069"),
        # A full stop or a comma after a Latin run is the Persian sentence's.
        ("از Sep The Concept.", (), "از \u2068Sep The Concept\u2069."),
        ("Minus EP، تازه", (), "\u2068Minus EP\u2069، تازه"),
        ("سال 2026", (), "سال 2026"),  # digits alone are left alone
        ("Side A & B: Part 2!", (), "\u2068Side A & B: Part 2!\u2069"),
        # The title and the artist are kept exactly as given, Arabic letters and all.
        ("علي و علي‌اکبر يك", ("علي", None), "علي و علي‌اکبر یک"),
    ],
)
def test_a_persian_draft_is_written_as_persian(text, names, written):
    assert llm.persian(text, names) == written


@pytest.mark.parametrize(("primary", "secondary"), [("fa", "en"), ("en", "fa-IR")])
def test_only_the_persian_drafts_are_normalised(server, primary, secondary):
    server(reply={"message": {"content": json.dumps({"story": {"primary": "SONG يك", "secondary": "SONG يك"}})}})
    kw = {"artist": "Sep The Concept", "concept": "c", "mood": "", "facts": []}
    drafts = llm.draft_captions(llm.parse_model_spec("ollama:m"), title="SONG", surfaces=["story"],
                                primary_language=primary, secondary_language=secondary, **kw)
    persian = f"{llm.FSI}SONG{llm.PDI} یک"
    assert drafts["story"] == {"primary": persian if primary == "fa" else "SONG يك",
                               "secondary": persian if secondary != "en" else "SONG يك"}


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("the long way home", []),
        ("out now! 🔥", ["an emoji", "an exclamation mark"]),
        ("#newmusic with @someone", ["a #", "an @"]),
        ("listen: https://soundcloud.com/x", ["a link"]),
        ("soundcloud.com/x or www.example.org", ["a link"]),
        ("¡Escúchala ya", ["an exclamation mark"]),
        ("بشنوید! ❤️", ["an emoji", "an exclamation mark"]),
    ],
)
def test_a_draft_that_breaks_the_rules_says_which(text, found):
    assert llm.rule_breaks(text) == found


def test_a_rule_break_is_flagged_under_its_draft_not_removed():
    drafts = {"instagram": {"primary": "out now! #song", "secondary": "بشنوید 🔥"}, "story": {"primary": "quiet"}}
    lines = llm.render_drafts(drafts, llm.parse_model_spec("ollama:m"), "en", "fa")
    rules = "(no emoji, hashtags, @handles, exclamation marks or links). Flagged, not removed -- rewrite it."
    first = lines.index("out now! #song")  # the draft as the model wrote it
    assert lines[first + 1 : first + 4] == [
        "```", "", f"> **Breaks the rules it was given:** it has a # and an exclamation mark {rules}",
    ]
    mirror = lines.index("بشنوید 🔥")
    assert lines[mirror + 1 : mirror + 4] == ["```", "", f"> **Breaks the rules it was given:** it has an emoji {rules}"]
    assert not any(line.startswith("> **Breaks") for line in lines[lines.index("quiet") :])


def test_drafts_render_as_a_labelled_section_with_both_languages():
    lines = llm.render_drafts(
        {"youtube": {"primary": "p", "secondary": "s"}}, llm.parse_model_spec("ollama:m"), "en", "fa"
    )
    text = "\n".join(lines)
    assert text.startswith("## Drafts from a local model (ollama · m)")
    assert "not copy to post" in text and "### YouTube" in text
    assert "**English**" in text and "**Persian (Farsi), in Persian script**" in text
    alone = "\n".join(llm.render_drafts({"story": {"primary": "p"}}, llm.parse_model_spec("ollama:m"), "en", None))
    assert "Persian" not in alone


# --------------------------------------------------------------------------- the pack
def test_drafts_sit_after_the_posting_order_and_before_the_notes():
    brief = make_brief(release=ReleaseConfig(concept="c"))
    text = generate_release_pack(brief, make_analysis(), ["## Drafts from a local model (x)", ""])
    assert text.index("## Posting order") < text.index("## Drafts from a local model") < text.index("## Notes")


def test_a_brief_for_a_release_with_no_footage_covers_the_whole_song():
    brief = minimal_brief("song.wav", "TITLE", 183.5, artist="A", concept="c", secondary_language="fa")
    assert brief.song.title == "TITLE" and brief.song.audio_path == "song.wav"
    assert [(s.start, s.end) for s in brief.sections] == [(0.0, 183.5)]
    assert brief.release.secondary_language == "fa" and brief.release.concept == "c"


def test_release_facts_are_only_what_the_tool_knows():
    brief = make_brief(
        stations=[make_station(name="s")],
        sections=[make_section(name="intro", start=0, end=30, station="s"), make_section(name="drop", start=30, end=60, station="s")],
        release=ReleaseConfig(date="2026-10-01"),
    )
    facts = release_facts(brief, make_analysis(duration=60.0, bpm=96.0))
    assert facts == ["chapters: 0:00 intro, 0:30 drop", "release date 2026-10-01"]


def test_release_facts_leave_out_the_length_and_the_tempo():
    """True, and an invitation to a filler line ("three minutes at 96 BPM")."""
    analysis = make_analysis(duration=200.0, bpm=96.0, energy_jumps=(EnergyJump(time=72.0, onset_strength=1.0, z_score=3.0),))
    facts = release_facts(make_brief(release=ReleaseConfig()), analysis)
    assert facts == ["the biggest change in the song comes at 1:12"]
    assert not any("BPM" in f or "length" in f or "3:20" in f for f in facts)


# --------------------------------------------------------------------------- the CLI
@pytest.fixture
def quiet_analysis(monkeypatch):
    monkeypatch.setattr(cli, "analyze", lambda *a, **k: make_analysis(duration=60.0))


@pytest.fixture
def brief_file(tmp_path):
    brief = make_brief(
        stations=[make_station(name="s")],
        sections=[make_section(name="A", start=0.0, end=60.0, station="s")],
        release=ReleaseConfig(concept="the line", secondary_language="fa", platforms=["instagram", "story"]),
    )
    path = tmp_path / "brief.yaml"
    path.write_text(yaml.safe_dump(brief.model_dump(exclude_none=True, mode="json"), sort_keys=False))
    return path


def test_kit_from_a_song_alone_needs_no_brief(tmp_path, quiet_analysis):
    out = tmp_path / "pack.md"
    code = cli.main(["kit", "--song", "s.wav", "--title", "TITLE", "--concept", "c", "--lang", "en,fa", "-o", str(out)])
    assert code == 0
    text = out.read_text()
    assert text.startswith("# TITLE — release pack") and "Description — fa" in text


@pytest.mark.parametrize(
    "argv",
    [
        ["kit"],
        ["kit", "--song", "s.wav"],
        ["kit", "brief.yaml", "--title", "T"],
        ["kit", "--song", "s.wav", "--title", "T", "--llm", "qwen3"],
    ],
)
def test_kit_usage_errors_exit_2(argv, quiet_analysis, capsys):
    assert cli.main(argv) == 2
    assert capsys.readouterr().err.startswith("kit:")


def test_kit_with_a_local_model_adds_its_drafts(tmp_path, brief_file, quiet_analysis, server, capsys):
    fake = server(reply=reply_for(["instagram", "story"]))
    out = tmp_path / "pack.md"
    assert cli.main(["kit", str(brief_file), "--llm", "ollama:qwen3:8b", "-o", str(out)]) == 0
    text = out.read_text()
    assert "## Drafts from a local model (ollama · qwen3:8b)" in text and f"{llm.FSI}instagram{llm.PDI} آینه" in text
    body = fake.requests[0]["body"]
    assert "the line" in body["messages"][1]["content"] and body["format"]["required"] == ["instagram", "story"]
    assert "caption drafts from ollama · qwen3:8b" in capsys.readouterr().out


def test_kit_still_writes_the_pack_when_the_local_model_is_missing(tmp_path, brief_file, quiet_analysis, server, capsys):
    server(error=urllib.error.URLError(ConnectionRefusedError(61, "refused")))
    out = tmp_path / "pack.md"
    assert cli.main(["kit", str(brief_file), "--llm", "ollama:qwen3:8b", "-o", str(out)]) == 1
    assert "## Drafts" not in out.read_text() and out.read_text().startswith("# ")
    assert "without drafts: no local model server" in capsys.readouterr().err


def test_kit_says_so_when_the_model_server_is_another_machine(tmp_path, brief_file, quiet_analysis, server, capsys):
    server(reply=reply_for(["instagram", "story"]))
    out = tmp_path / "pack.md"
    argv = ["kit", str(brief_file), "--llm", "ollama:m", "--llm-host", "http://studio.local:11434", "-o", str(out)]
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == (
        "kit: note -- http://studio.local:11434 is not this machine, so the brief's concept and facts go there.\n"
    )
    assert "is not this machine" not in captured.out and captured.out.startswith("wrote ")


def test_kit_refuses_a_model_server_that_isnt_an_http_url(tmp_path, brief_file, quiet_analysis, server, capsys):
    fake = server(reply=reply_for(["instagram", "story"]))
    out = tmp_path / "pack.md"
    argv = ["kit", str(brief_file), "--llm", "ollama:m", "--llm-host", "file:///etc/hostname#", "-o", str(out)]
    assert cli.main(argv) == 2
    assert capsys.readouterr().err.startswith("kit: --llm-host wants an http:// or https:// URL")
    assert fake.requests == [] and not out.exists()


@pytest.mark.parametrize(
    ("answer", "says"),
    [
        ({"reply": []}, "isn't an Ollama chat reply"),
        ({"reply": {"message": "x"}}, "isn't an Ollama chat reply"),
        ({"error": http.client.BadStatusLine("SSH-2.0-OpenSSH_9.6")}, "didn't answer as an Ollama server does"),
        ({"raw": b"[" * 100_000}, "isn't JSON"),
    ],
)
def test_kit_writes_the_pack_without_drafts_whatever_the_server_answers(
    tmp_path, brief_file, quiet_analysis, server, capsys, answer, says
):
    server(**answer)
    out = tmp_path / "pack.md"
    assert cli.main(["kit", str(brief_file), "--llm", "ollama:m", "-o", str(out)]) == 1
    assert out.read_text(encoding="utf-8").startswith("# ") and "## Drafts" not in out.read_text(encoding="utf-8")
    err = capsys.readouterr().err
    assert err.startswith("kit: the pack is written, without drafts: ") and says in err and "Traceback" not in err
