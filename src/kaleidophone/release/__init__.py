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
"""

from kaleidophone.release.copy import generate_release_pack

__all__ = ["generate_release_pack"]
