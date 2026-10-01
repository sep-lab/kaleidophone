"""Caption drafts from a model running on this machine -- for working with no tokens and no network.

Optional and off by default: ``kaleidophone kit ... --llm ollama:<model>``. The release pack's
facts (timestamps, chapters, credits, the posting order) are always the tool's own; what a model
can add is a *voice*, so that is all this asks it for: one caption per surface, in the primary
language and, when the brief has one, a second-language mirror.

The request goes to an Ollama server on this machine (``http://127.0.0.1:11434`` unless the
caller says otherwise) through its ``/api/chat`` endpoint, with a JSON schema as ``format`` so
the reply is structured and a fixed seed so the same pack asks the same question the same way.
Nothing here imports a third-party client: the standard library speaks HTTP well enough, and an
optional feature should not add a dependency. Nothing leaves the machine unless ``host`` points
somewhere else -- which the CLI warns about. The request goes straight to ``host``, never
through a proxy (``urlopen`` would send it to ``http_proxy`` or ``ALL_PROXY``, even for
127.0.0.1, unless ``no_proxy`` lists it); ``host`` is http or https and nothing else (a
``file://`` one would read a file on this machine), and the reply is read to 4 MB at most.

What comes back is a draft to rewrite, never copy to post: a small local model writes Persian
idiom less well than English, and none of them know what the song is about beyond the one line
in ``release.concept``. The pack says so above the drafts, and under any draft that breaks the
rules the model was given (an emoji, a hashtag, an @handle, an exclamation mark, a link) says
which -- flagged, not removed. A Persian draft is written the way Persian is: Arabic yeh and kaf
become Persian's own, and a Latin title in it ("SHOULD I ?") is isolated so its question mark
stays where it belongs in right-to-left text.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_S = 300.0  # a cold 8B model on a laptop can take a minute to load
MAX_REPLY_BYTES = 4_000_000  # a reply of captions is a few kB; one of 4 MB isn't one
SEED = 7

# What each surface is for, and how long a caption there should be. Character counts are the
# point where each surface starts truncating in the feed (inferred from how they display today),
# used as a ceiling for the model, never to cut what it wrote.
SURFACES: dict[str, str] = {
    "soundcloud": "the track description on SoundCloud: two to four short lines, the image first",
    "youtube": "the first two lines of the YouTube description (everything after them is hidden "
    "behind 'more'): one or two short lines",
    "instagram": "the Instagram reel caption: one to three short lines; the first line must stand "
    "alone, because the feed cuts it after about 125 characters",
    "story": "one line of story sticker text, under 40 characters",
}

LANGUAGE_NAMES = {
    "en": "English",
    "fa": "Persian (Farsi), in Persian script",
    "es": "Spanish",
    "ca": "Catalan",
    "fr": "French",
    "de": "German",
}

SYSTEM = (
    "You write short release captions for an independent musician. Write in the artist's "
    "voice: plain, specific, unhurried; no hype words (no 'banger', 'fire', 'vibes', "
    "'masterpiece'), no exclamation marks, no emojis, no hashtags, no links, no @handles, no "
    "lyrics, and never invent facts (dates, places, people, numbers) that are not in the brief. "
    "Write the title and the artist name exactly as given, in their original script; never "
    "translate or transliterate them. "
    "Build every caption around the one-line concept you are given. When asked for a second "
    "language, write a mirror, not a translation: the same image, said the way a native speaker "
    "would say it. Reply with JSON only, matching the schema."
)


class LocalModelError(RuntimeError):
    """The local model could not be reached or did not answer usefully. The message says what to do."""


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider} · {self.model}"


def parse_model_spec(spec: str) -> ModelSpec:
    """``ollama:qwen3:8b`` -> provider ``ollama``, model ``qwen3:8b`` (model names keep their colons)."""
    provider, sep, model = spec.partition(":")
    if not sep or not model.strip():
        raise ValueError(f"--llm wants provider:model, e.g. ollama:qwen3:8b (got {spec!r})")
    provider = provider.strip().lower()
    if provider != "ollama":
        raise ValueError(f"--llm supports the 'ollama' provider only (got {provider!r})")
    return ModelSpec(provider, model.strip())


def check_host(host: str) -> str:
    """``host`` as requests go to it -- http or https, with a host name and a port that is one
    -- or a ValueError. Nothing else is an Ollama server, and a ``file://`` URL would read a file
    on this machine into the error."""
    url = host.strip().rstrip("/")
    try:
        parts = urlparse(url)
        valid = parts.scheme.lower() in ("http", "https") and bool(parts.hostname) and parts.port != 0
    except ValueError:  # an unclosed [ipv6 address, a port that isn't a number or is past 65535
        valid = False
    if not valid:
        raise ValueError(f"--llm-host wants an http:// or https:// URL, like {DEFAULT_HOST} (got {host!r})")
    return url


def is_local(host: str) -> bool:
    """True when ``host`` is this machine -- the only place a draft should be written by default."""
    name = (urlparse(host).hostname or "").lower()
    return name in {"127.0.0.1", "localhost", "::1"}


def _language(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower(), code)


def caption_schema(surfaces: list[str], secondary: bool) -> dict:
    """The JSON schema handed to the model as ``format``: one object per surface."""
    keys = ["primary", "secondary"] if secondary else ["primary"]
    per_surface = {
        "type": "object",
        "properties": {k: {"type": "string"} for k in keys},
        "required": keys,
    }
    return {
        "type": "object",
        "properties": dict.fromkeys(surfaces, per_surface),
        "required": list(surfaces),
    }


def build_prompt(
    *,
    title: str,
    artist: str | None,
    concept: str | None,
    mood: str,
    facts: list[str],
    surfaces: list[str],
    primary_language: str,
    secondary_language: str | None,
) -> str:
    """The user message: what the record is, the facts the tool knows, and what to write where."""
    lines = [f"Song: {title}" + (f" — by {artist}" if artist else "")]
    lines.append(f"Concept (the one line every caption is built around): {concept or '(none given)'}")
    if mood:
        lines.append(f"Mood words: {mood}")
    if facts:
        lines.append("Facts you may use (use none of them if they don't help):")
        lines += [f"- {f}" for f in facts]
    lines.append("")
    lines.append("Write, for each surface below:")
    for s in surfaces:
        lines.append(f"- {s}: {SURFACES[s]}")
    lines.append("")
    lines.append(f"Write 'primary' in {_language(primary_language)}.")
    if secondary_language:
        lines.append(f"Write 'secondary' in {_language(secondary_language)}, as a mirror of 'primary'.")
    return "\n".join(lines)


def request_body(model: str, prompt: str, schema: dict) -> dict:
    """The ``/api/chat`` request: non-streaming, schema-constrained, seeded."""
    return {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.7, "seed": SEED},
    }


def _open(req: urllib.request.Request, timeout: float):
    """Send ``req`` straight to its host, through an opener whose proxy handler has no proxies.
    urlopen's own reads http_proxy, https_proxy and ALL_PROXY -- for 127.0.0.1 too, unless
    no_proxy lists it -- and would hand the brief's concept to whatever they name. The person
    chose the host."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)


def chat(host: str, body: dict, timeout: float = DEFAULT_TIMEOUT_S) -> object:
    """POST ``body`` to ``host``/api/chat -- never through a proxy -- and return the decoded
    JSON reply, read to MAX_REPLY_BYTES at most. Every way that fails is a LocalModelError."""
    try:
        url = check_host(host) + "/api/chat"
    except ValueError as e:
        raise LocalModelError(str(e)) from None
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with _open(req, timeout) as resp:
            payload = resp.read(MAX_REPLY_BYTES + 1)
    except urllib.error.HTTPError as e:
        detail = e.read(2000).decode("utf-8", "replace")[:300]
        if e.code == 404 and "not found" in detail.lower():
            raise LocalModelError(
                f"the local model server has no model {body['model']!r}: run `ollama pull {body['model']}` first"
            ) from e
        raise LocalModelError(f"the local model server answered HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise LocalModelError(
            f"no local model server at {host} ({reason}). Install Ollama (https://ollama.com), "
            f"`ollama pull <model>`, make sure it is running, or leave out --llm."
        ) from e
    except (http.client.HTTPException, ValueError) as e:
        # Something is there, but it doesn't speak HTTP the way Ollama does (an SSH banner,
        # a broken response), or the host name can't be looked up at all.
        raise LocalModelError(
            f"{host} didn't answer as an Ollama server does ({type(e).__name__}: {str(e).strip()[:120]}) "
            f"-- check --llm-host, or leave out --llm."
        ) from e
    if len(payload) > MAX_REPLY_BYTES:
        raise LocalModelError(
            f"the local model server sent more than {MAX_REPLY_BYTES / 1e6:g} MB: that isn't a reply of captions"
        )
    try:
        return json.loads(payload)
    except (ValueError, RecursionError) as e:
        raise LocalModelError(
            f"the local model server sent something that isn't JSON: {payload[:200]!r}"
        ) from e


def parse_reply(reply: object, surfaces: list[str], secondary: bool) -> dict[str, dict[str, str]]:
    """Pull the captions out of an ``/api/chat`` reply, refusing anything incomplete -- and
    anything that isn't shaped like one: an object whose ``message`` is an object."""
    message = reply.get("message") if isinstance(reply, dict) else None
    if not isinstance(reply, dict) or not isinstance(message, (dict, type(None))):
        raise LocalModelError(f"the local model server's reply isn't an Ollama chat reply: {_clip(reply)}")
    content = (message or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise LocalModelError("the local model returned an empty reply")
    try:
        data = json.loads(content)
    except (ValueError, RecursionError) as e:
        raise LocalModelError(f"the local model's reply isn't the JSON asked for: {content[:200]!r}") from e
    keys = ["primary", "secondary"] if secondary else ["primary"]
    out: dict[str, dict[str, str]] = {}
    for s in surfaces:
        block = data.get(s) if isinstance(data, dict) else None
        if not isinstance(block, dict):
            raise LocalModelError(f"the local model's reply has no {s!r} block")
        texts = {}
        for k in keys:
            v = block.get(k)
            if not isinstance(v, str) or not v.strip():
                raise LocalModelError(f"the local model left {s}.{k} empty")
            texts[k] = v.strip()
        out[s] = texts
    return out


def _clip(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)[:200]


# --------------------------------------------------------------------------- what comes back
# Persian is written with its own yeh and kaf; a model trained on Arabic text often writes
# Arabic's. Both look alike in the middle of a word and differ at its end.
_PERSIAN_LETTERS = str.maketrans({"\u064a": "\u06cc", "\u0643": "\u06a9"})  # ي -> ی, ك -> ک
FSI, PDI = "\u2068", "\u2069"  # first-strong isolate, pop directional isolate
_LATIN = "A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff"
# A run of Latin script: words joined by spaces and the punctuation inside a title, ending on a
# letter or a digit -- and a question or exclamation mark right after it, which is the title's
# ("SHOULD I ?"). A full stop or a comma after the run is the sentence's, and stays outside.
_LATIN_RUN = re.compile(rf"[0-9]*[{_LATIN}](?:[{_LATIN}0-9'\u2019&.:/\- ]*[{_LATIN}0-9])?(?: ?[?!]+)?")


def persian(text: str, names: tuple[str | None, ...] = ()) -> str:
    """A Persian draft as it should be written: Arabic yeh and kaf (ي ك) as Persian's own
    (ی ک) -- except inside ``names``, the title and the artist as given, which are kept exactly
    -- and every run of Latin script inside first-strong isolates (U+2068 ... U+2069), so a
    Latin title's "?" stays with it in right-to-left text instead of jumping to its other end."""
    kept = sorted({n for n in names if n}, key=len, reverse=True)
    parts = re.split(f"({'|'.join(map(re.escape, kept))})", text) if kept else [text]
    text = "".join(part if i % 2 else part.translate(_PERSIAN_LETTERS) for i, part in enumerate(parts))
    return _LATIN_RUN.sub(lambda m: f"{FSI}{m.group(0)}{PDI}", text)


def _is_persian(code: str | None) -> bool:
    return bool(code) and re.split(r"[-_]", code.lower())[0] == "fa"


# The rules in SYSTEM that a draft can be checked against. A draft that breaks one is flagged in
# the pack, never edited: the person rewriting it decides.
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("an emoji", re.compile("[\U0001f000-\U0001faff\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\ufe0f]")),
    ("a #", re.compile("[#\uff03]")),
    ("an @", re.compile("[@\uff20]")),
    ("an exclamation mark", re.compile("[!\u00a1\uff01]")),
    ("a link", re.compile(
        r"(?i)https?://|\bwww\.|\b[\w-]+\.(?:com|net|org|io|fm|me|ly|ee|link|app|co|to|be|tv)\b"
    )),
)


def rule_breaks(text: str) -> list[str]:
    """What in a draft breaks the rules the model was given, in RULES' order."""
    return [what for what, pattern in RULES if pattern.search(text)]


def draft_captions(
    spec: ModelSpec,
    *,
    title: str,
    artist: str | None,
    concept: str | None,
    mood: str,
    facts: list[str],
    surfaces: list[str],
    primary_language: str,
    secondary_language: str | None,
    host: str = DEFAULT_HOST,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, dict[str, str]]:
    """Ask the local model for one caption per surface (and a mirror when there's a second language)."""
    surfaces = [s for s in surfaces if s in SURFACES]
    if not surfaces:
        return {}
    secondary = bool(secondary_language)
    prompt = build_prompt(
        title=title,
        artist=artist,
        concept=concept,
        mood=mood,
        facts=facts,
        surfaces=surfaces,
        primary_language=primary_language,
        secondary_language=secondary_language,
    )
    reply = chat(host, request_body(spec.model, prompt, caption_schema(surfaces, secondary)), timeout)
    drafts = parse_reply(reply, surfaces, secondary)
    languages = {"primary": primary_language, "secondary": secondary_language}
    return {
        s: {k: persian(v, (title, artist)) if _is_persian(languages[k]) else v for k, v in texts.items()}
        for s, texts in drafts.items()
    }


def render_drafts(
    drafts: dict[str, dict[str, str]],
    spec: ModelSpec,
    primary_language: str,
    secondary_language: str | None,
) -> list[str]:
    """The markdown section appended to the release pack."""
    names = {"soundcloud": "SoundCloud", "youtube": "YouTube", "instagram": "Instagram", "story": "Story"}
    o = [
        f"## Drafts from a local model ({spec.label})",
        "",
        "> Written on this machine by a local model, from the concept line and the facts above.",
        "> A draft to rewrite, not copy to post: read every line aloud, and check the",
        "> second language with someone who speaks it — small models get idiom wrong.",
        "",
    ]
    for surface, texts in drafts.items():
        o += [f"### {names.get(surface, surface)}", "", f"**{_language(primary_language)}**", "", "```"]
        o += [texts["primary"], "```", "", *_flagged(texts["primary"])]
        if secondary_language and "secondary" in texts:
            o += [f"**{_language(secondary_language)}**", "", "```", texts["secondary"], "```", ""]
            o += _flagged(texts["secondary"])
    return o


def _flagged(text: str) -> list[str]:
    """The line under a draft that breaks the rules the model was given, saying which."""
    found = rule_breaks(text)
    if not found:
        return []
    listed = found[0] if len(found) == 1 else f"{', '.join(found[:-1])} and {found[-1]}"
    return [
        f"> **Breaks the rules it was given:** it has {listed} (no emoji, hashtags, @handles, "
        f"exclamation marks or links). Flagged, not removed -- rewrite it.",
        "",
    ]
