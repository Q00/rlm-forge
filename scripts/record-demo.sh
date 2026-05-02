#!/usr/bin/env bash
# Record a self-contained asciinema demo of the RLM integration artifact.
#
# Two modes:
#   ./scripts/record-demo.sh replay   - no Hermes, ~10s, safe for any environment
#   ./scripts/record-demo.sh live     - real Hermes truncation benchmark, ~60s
#
# Output: demo-replay.cast or demo-live.cast in repo root.
# Upload with:  asciinema upload demo-replay.cast

set -euo pipefail

MODE="${1:-replay}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

case "$MODE" in
  replay)
    OUTPUT="demo-replay.cast"
    SCRIPT="scripts/_demo_replay.sh"
    ;;
  live)
    OUTPUT="demo-live.cast"
    SCRIPT="scripts/_demo_live.sh"
    ;;
  *)
    echo "usage: $0 {replay|live}" >&2
    exit 2
    ;;
esac

if ! command -v asciinema >/dev/null 2>&1; then
  echo "error: asciinema not installed. brew install asciinema" >&2
  exit 1
fi

rm -f "$OUTPUT"
asciinema rec \
  --title "RLM-FORGE ($MODE demo)" \
  --command "bash $SCRIPT" \
  --idle-time-limit 1.5 \
  "$OUTPUT"

echo
echo "Recorded: $OUTPUT"
echo "Preview:  asciinema play $OUTPUT"
echo "Upload:   asciinema upload $OUTPUT"
