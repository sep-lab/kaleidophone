#!/usr/bin/env bash
#
# The system font a canvas piece can fall back on, pinned, for the golden frames.
#
# WHY
#   A piece draws with the fonts it inlines, with one exception: HAMECHI MANZOR
#   DARE's credit line asks for ui-monospace, which Chromium on Linux resolves
#   through fontconfig's "monospace". Which font that is moves pixels -- DejaVu
#   Sans Mono to Liberation Mono changed 454 pixels of one 1080x1920 frame
#   (measured: canvas/README.md, "Verified against what shipped") -- and the
#   golden frames are exact (canvas/tools/golden.mjs). So the package is pinned,
#   and a runner where "monospace" means anything else stops here instead of
#   failing the goldens for a reason no diff would show.
#
# Runs after `npx playwright-core install --with-deps chromium`, which pulls in
# other fonts (fonts-liberation among them); fontconfig still prefers DejaVu
# Sans Mono for "monospace" when it is there. It refreshes apt's lists itself,
# and installs from them (canvas-env's ffmpeg step relies on that too).
#
# USAGE
#   .github/workflows/scripts/pin_canvas_fonts.sh     (Ubuntu 24.04 runners; needs sudo)
set -euo pipefail

FONTS_DEJAVU_CORE="2.37-8"   # Ubuntu 24.04 (noble)

sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends --allow-downgrades "fonts-dejavu-core=${FONTS_DEJAVU_CORE}"

have="$(fc-match -f '%{family[0]}' monospace)"
if [ "$have" != "DejaVu Sans Mono" ]; then
  echo "::error::fontconfig resolves \"monospace\" to \"$have\", not DejaVu Sans Mono, the font the golden frames were recorded with. Find what changed in the runner image (fc-match -s monospace, below) before re-recording anything."
  fc-match -s monospace | head -n 5
  exit 1
fi
# ${Version} is dpkg-query's format field, not a shell variable:
# shellcheck disable=SC2016
echo "monospace: $have (fonts-dejavu-core $(dpkg-query -W -f='${Version}' fonts-dejavu-core))"
