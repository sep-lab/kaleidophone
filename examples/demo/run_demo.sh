#!/usr/bin/env bash
# See it in ten seconds: a synthetic song + synthetic photos, through the
# real analyze -> compose -> render -> promo pipeline. No real media, nothing
# to connect, nothing to ask permission for.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$HERE/generate_fixtures.py"
mvideo run "$HERE/_fixtures/brief.yaml" -o "$HERE/_fixtures/out"

echo
echo "Done -- see $HERE/_fixtures/out/master.mp4"
