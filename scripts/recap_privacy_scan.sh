#!/usr/bin/env bash
set -euo pipefail

target="${1:-tasks/wren_distribution_recap_package}"

if [[ ! -d "$target" ]]; then
  echo "recap privacy scan skipped: $target not found"
  exit 0
fi

common_globs=(
  -g '!**/*.png'
  -g '!**/*.jpg'
  -g '!**/*.jpeg'
  -g '!**/*.webp'
  -g '!**/*.mp4'
  -g '!**/*.mov'
  -g '!**/*.gif'
  -g '!**/.DS_Store'
)

status=0

echo "== recap privacy scan: login/token keywords =="
if rg -n -i "${common_globs[@]}" \
  -e 'Login code|Do not give this code|TELEGRAM_BOT_TOKEN|WREN_API_KEY|Authorization|Bearer' \
  "$target"; then
  status=1
fi

scan_roots=()
[[ -d "$target/raw_evidence" ]] && scan_roots+=("$target/raw_evidence")
[[ -d "$target/story_visuals" ]] && scan_roots+=("$target/story_visuals")

if [[ ${#scan_roots[@]} -gt 0 ]]; then
  echo "== recap privacy scan: raw chat identifiers =="
  if rg -n "${common_globs[@]}" \
    -e '/data/users/[0-9]{6,12}\b|(^|[[:space:]])[0-9]{6,12}([[:space:]]|$)|\b[0-9a-f]{16}\b' \
    "${scan_roots[@]}"; then
    status=1
  fi
fi

if [[ "$status" -ne 0 ]]; then
  echo "recap privacy scan failed: redact the matches above or move private raw evidence out of the deliverable package" >&2
  exit "$status"
fi

echo "recap privacy scan passed"
