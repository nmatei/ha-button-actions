#!/bin/bash
# Keeps CLAUDE.md and .github/copilot-instructions.md in sync.
# The file passed as $1 is the source of truth; the other is overwritten to match.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE="$ROOT/CLAUDE.md"
COPILOT="$ROOT/.github/copilot-instructions.md"

CHANGED="${1:-}"

case "$CHANGED" in
  *CLAUDE.md)              SOURCE="$CLAUDE" ;;
  *copilot-instructions*)  SOURCE="$COPILOT" ;;
  *)
    echo "sync-rules: unknown changed file '$CHANGED', skipping sync" >&2
    exit 0
    ;;
esac

if [ ! -f "$SOURCE" ]; then
  echo "sync-rules: source file not found: $SOURCE" >&2
  exit 1
fi

for TARGET in "$CLAUDE" "$COPILOT"; do
  if [ "$TARGET" != "$SOURCE" ]; then
    mkdir -p "$(dirname "$TARGET")"
    cp "$SOURCE" "$TARGET"
    echo "sync-rules: synced $(basename "$SOURCE") → $TARGET"
  fi
done
