#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-9227}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.cache/web-agent-wp-chrome}"
URL="${URL:-about:blank}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/start_wp_chrome.ps1" -Port "$PORT" -Url "$URL"
    exit 0
    ;;
esac

for browser in google-chrome google-chrome-stable chromium chromium-browser brave-browser brave microsoft-edge; do
  if command -v "$browser" >/dev/null 2>&1; then
    "$browser" \
      --remote-debugging-port="$PORT" \
      --user-data-dir="$PROFILE_DIR" \
      --new-window \
      "$URL" >/dev/null 2>&1 &
    exit 0
  fi
done

echo "Khong tim thay Chrome/Brave/Edge." >&2
exit 1
