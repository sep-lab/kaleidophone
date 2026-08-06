#!/usr/bin/env bash
#
# Guardrail: no real audio, video, or image file may ever enter this
# repository -- not a photo, not a song, not "just one small sample".
#
# WHY
#   kaleidophone's whole job is to operate on someone's real, private media. A repo
#   full of committed media would be self-refuting (see docs/decisions/0003)
#   and a real privacy/copyright problem: real photos and songs are other
#   people's likenesses and other people's copyrighted work. See AGENTS.md,
#   "Rules for handling user data".
#
# WHAT IT CHECKS
#   1. extension blocklist   -- the formats .gitignore already refuses
#   2. per-file size ceiling -- because a format nobody thought to blocklist
#                                will still be big; a blocklist only catches
#                                what someone already thought of
#
# USAGE
#   .github/workflows/scripts/check_no_media.sh [max_file_bytes]

set -euo pipefail

MAX_FILE_BYTES="${1:-2097152}"   # 2 MiB. Nothing in this repo's own source is bigger.

fail=0

# --- 1. extensions -----------------------------------------------------
# Deliberately the same list as .gitignore, checked again here: .gitignore
# only stops a file from being *added* by someone who has it in their
# working tree; this stops it from landing in a commit at all (e.g. a
# forced `git add -f`), and runs on every PR regardless of whose machine
# made the commit.
audio='\.(wav|aif|aiff|flac|mp3|m4a|ogg|opus)$'
video='\.(mp4|mov|mkv|avi|webm)$'
image='\.(jpg|jpeg|png|heic|heif|tiff|tif|bmp|gif|webp|psd)$'

matches="$(git ls-files | grep -Ei "${audio}|${video}|${image}" || true)"
if [ -n "$matches" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    echo "::error file=${f}::Real media must never be committed. See .gitignore and AGENTS.md."
    echo "  refused: $f"
  done <<EOF
$matches
EOF
  cat <<'EOF'

  kaleidophone never commits audio, video, or image files -- not as fixtures, not
  as "a small sample". Tests and the demo generate fully synthetic media at
  run time instead; see examples/demo/generate_fixtures.py for the pattern,
  and CONTRIBUTING.md ("Test fixtures") for what to contribute instead.
EOF
  fail=1
fi

# --- 2. per-file size ceiling -------------------------------------------
while IFS= read -r f; do
  [ -f "$f" ] || continue
  size=$(wc -c < "$f" | tr -d ' ')
  if [ "$size" -gt "$MAX_FILE_BYTES" ]; then
    echo "::error file=${f}::${f} is $((size / 1024)) KB, over the $((MAX_FILE_BYTES / 1024)) KB per-file limit."
    cat <<EOF

  ${f} is $((size / 1024)) KB.

  Nothing in this framework repo should exceed $((MAX_FILE_BYTES / 1024)) KB. If it is
  audio/video/image it cannot go in at all (see above). If it's something
  else that genuinely belongs here, raise MAX_FILE_BYTES in this script in
  the same PR and say why in the commit message.
EOF
    fail=1
  fi
done < <(git ls-files)

if [ "$fail" -eq 0 ]; then
  echo "clean: no media files, nothing over $((MAX_FILE_BYTES / 1024)) KB"
fi
exit "$fail"
