#!/bin/bash
# Regenerate BUNDLE.md from catalog files
# Run: cd knowledge && ./bundle.sh
cd "$(dirname "$0")"

echo "# UWWB Knowledge Bundle" > BUNDLE.md
echo "" >> BUNDLE.md
echo "> Auto-generated $(date +%Y-%m-%d). Do not edit directly — edit the source files instead." >> BUNDLE.md
echo "> Covers: architecture, active features, parked features, patterns, tooling, marine/CaTa, collaboration." >> BUNDLE.md
echo "" >> BUNDLE.md

for f in _index.md architecture.md features-active.md features-parked.md \
         patterns-and-gotchas.md tooling.md marine-cata.md collaboration.md guardrails.md; do
  echo "---" >> BUNDLE.md
  echo "" >> BUNDLE.md
  cat "$f" >> BUNDLE.md
  echo "" >> BUNDLE.md
done

echo "✓ Bundle generated: knowledge/BUNDLE.md ($(wc -c < BUNDLE.md | tr -d ' ') bytes)"