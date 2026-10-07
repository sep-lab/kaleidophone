# The lib, pinned

Each folder here is the lib as a release had it, byte for byte: `0.4.0/` holds v0.4.0's `core.js` and
`live.js`. A piece that shipped built on the lib sets `"libVersion"` in its `piece.json`, and
`tools/build.mjs` inlines these files instead of `canvas/lib/`, so later lib work can't move the bytes
of a released page. A folder is written once and never edited: fix the lib in `canvas/lib/`.
`canvas/test/contract.test.mjs` holds every file's sha256. See
[canvas/README.md, "The lib pin"](../../README.md#the-lib-pin).
