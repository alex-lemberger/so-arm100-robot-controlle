#!/usr/bin/env bash
# Usage: ./bundle.sh <spec.md> <plan.md>
# Outputs: docs/local-model/BUNDLE.md
# Concatenates CLAUDE.md + guardrails.md + feature spec + implementation plan
# into a single context file for local model ingestion.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT="$SCRIPT_DIR/BUNDLE.md"

CLAUDE_MD="$REPO_ROOT/CLAUDE.md"
GUARDRAILS="$SCRIPT_DIR/guardrails.md"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <spec.md> <plan.md>" >&2
  exit 1
fi

SPEC="$1"
PLAN="$2"

for f in "$CLAUDE_MD" "$GUARDRAILS" "$SPEC" "$PLAN"; do
  if [[ ! -f "$f" ]]; then
    echo "Error: file not found: $f" >&2
    exit 1
  fi
done

{
  echo "# LOCAL MODEL CONTEXT BUNDLE"
  echo "# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# Spec:  $SPEC"
  echo "# Plan:  $PLAN"
  echo ""
  echo "---"
  echo ""

  echo "<!-- SECTION: CLAUDE.md -->"
  cat "$CLAUDE_MD"
  echo ""
  echo "---"
  echo ""

  echo "<!-- SECTION: guardrails.md -->"
  cat "$GUARDRAILS"
  echo ""
  echo "---"
  echo ""

  echo "<!-- SECTION: feature spec -->"
  cat "$SPEC"
  echo ""
  echo "---"
  echo ""

  echo "<!-- SECTION: implementation plan -->"
  cat "$PLAN"
  echo ""
} > "$OUT"

echo "Bundle written to: $OUT"
wc -l "$OUT" | awk '{print "Lines: " $1}'
