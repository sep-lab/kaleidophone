"""
The release pack: per-platform copy, timed comments, and a posting order.

Files only. kaleidophone never posts, never authenticates, never touches a
platform API -- see docs/decisions/0006-the-release-pack.md. What comes out is
markdown you read, edit, and paste.

Everything here is templated from facts the brief and the audio analysis
already carry: chapters from `sections[]`, the pinned-comment timestamp from
the strongest detected energy jump, mood words from station descriptions,
credits and links from `release`. It is a scaffold with every number right and
the voice left open -- deliberately, because a caption is writing, and a
template that tried to be writing would produce the thing everyone can smell.

The one exception is opt-in and local: `kaleidophone kit --llm ollama:<model>` asks a model
running on this machine for caption *drafts* (`local_llm.py`), labelled as drafts, so a release
can still get written with no tokens and no network.
"""

from kaleidophone.release.copy import generate_release_pack, minimal_brief, mood_line, release_facts

__all__ = ["generate_release_pack", "minimal_brief", "mood_line", "release_facts"]
