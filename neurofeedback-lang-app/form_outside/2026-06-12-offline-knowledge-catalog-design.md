# Offline Knowledge Catalog — Design Spec

**Date:** 2026-06-12  
**Goal:** Consolidate scattered ~/.claude/ memory into a structured, reviewable, portable knowledge catalog anchored to AGENTS.md. Single monolith file (`BUNDLE.md`) enables instant LLM ingestion for offline/local model use.

## Problem

Knowledge is scattered across 5+ locations:
- `~/.claude/projects/.../memory/` (29 files + MEMORY.md index)
- `~/.claude/docs/` (specs, plans, reviews)
- `~/.claude/markdowns/` (analysis docs)
- `~/.claude/cyber-coverage/` (handover docs)
- MEMORY.md inline content (Marine/CaTa conventions)

This sprawl is:
- Not reviewable by teammates
- Not portable to local models
- Not version-controlled in the repo
- Hard to maintain (duplicated, outdated entries)

## Solution

A `knowledge/` directory in the liability repo root with 7 themed domain files + auto-generated bundle.

## Directory Structure

```
liability/
  AGENTS.md                          # existing — conventions/architecture
  knowledge/
    _index.md                        # TOC + usage instructions
    architecture.md                  # data flow, layer rules, key decisions
    features-active.md               # current WIP features
    features-parked.md               # on-hold/archived features
    patterns-and-gotchas.md          # PrimeNG, NGXS, readonly, race conditions
    tooling.md                       # dev setup, mocking, Azure DevOps, grep
    marine-cata.md                   # CaTa prototype, UI, calc spec, strategy
    collaboration.md                 # shared component rules, PR standards
    BUNDLE.md                        # auto-generated monolith for LLM ingestion
    bundle.sh                        # concat script to regenerate BUNDLE.md
```

## File Specifications

### _index.md

Catalog table of contents with:
- One-liner summary per file
- Usage instructions (Claude Code, local model, team review)
- Last-bundled timestamp

### Domain Files (7 files, each ~2-5K words)

| File | Sources Consolidated |
|------|---------------------|
| `architecture.md` | MEMORY.md Architecture Decisions, inplace_editing_architecture.md, Key File Locations, DATA_FLOW.md, FE_STRUCTURE.md |
| `features-active.md` | offer-table-enrichment.md, coverage-detail-redesign.md, broker_data_card_feature.md, dms_integration.md, coverage-table-optimization-plan.md, coverage-table-review-pending.md |
| `features-parked.md` | project_inplace_editing_status.md, odin_migration_option_c.md, exclusions-and-definitions-rework.md, inplace_*.md files, coverage-table-readonly-fix.md |
| `patterns-and-gotchas.md` | primeng_21_migration.md, primeng_dropdown_*.md, viewport_fix_nested_slide_panel.md, grep_coverage_gitignore_blindspot.md, inplace_label_field_alignment.md |
| `tooling.md` | generic_app_dev_setup.md, dev_mock_patterns.md, azure_devops_api.md |
| `marine-cata.md` | marine_workflow_figma_first.md, MEMORY.md Marine section, CaTa conventions from CLAUDE.md, strategic direction notes |
| `collaboration.md` | feedback_shared_components.md, feedback_self_improvement_loop.md |

### BUNDLE.md

Auto-generated concatenation of all catalog files in deterministic order:
1. _index.md
2. architecture.md
3. features-active.md
4. features-parked.md
5. patterns-and-gotchas.md
6. tooling.md
7. marine-cata.md
8. collaboration.md

Header includes generation timestamp and "do not edit" warning.

### bundle.sh

```bash
#!/bin/bash
cd "$(dirname "$0")"
echo "# UWWB Knowledge Bundle" > BUNDLE.md
echo "> Auto-generated $(date +%Y-%m-%d). Do not edit — edit source files instead." >> BUNDLE.md
echo "" >> BUNDLE.md
for f in _index.md architecture.md features-active.md features-parked.md \
         patterns-and-gotchas.md tooling.md marine-cata.md collaboration.md; do
  echo "---" >> BUNDLE.md
  echo "" >> BUNDLE.md
  cat "$f" >> BUNDLE.md
  echo "" >> BUNDLE.md
done
echo "Bundle generated: BUNDLE.md"
```

## AGENTS.md Integration

Add after the Repository Overview section:

```markdown
## Knowledge Catalog

Accumulated project knowledge lives in `knowledge/`. For full offline context, use `knowledge/BUNDLE.md`.

See [`knowledge/_index.md`](knowledge/_index.md) for the catalog index.
```

## Coexistence Strategy

- Old `~/.claude/.../memory/` files remain untouched during transition
- `knowledge/` is the new authoritative source
- MEMORY.md can later become a thin pointer or be retired
- New learnings go into appropriate `knowledge/*.md` file
- Run `bundle.sh` before handing to local model

## Usage Scenarios

| Scenario | Action |
|----------|--------|
| Claude Code session | AGENTS.md auto-loads; knowledge/ read on-demand |
| Local model (Ollama, LM Studio) | Feed `BUNDLE.md` as system prompt |
| Team review | Open individual files in browser/PR |
| Onboarding new dev/AI | Hand them AGENTS.md + BUNDLE.md |
| Offline continuity | BUNDLE.md has everything needed to resume |

## Success Criteria

1. All valuable content from ~/.claude/ memory files exists in knowledge/
2. BUNDLE.md is under 200K characters (fits most model context windows)
3. Any team member can read a single domain file and understand that topic
4. A local model given only BUNDLE.md can answer questions about the project
5. No duplication between AGENTS.md and knowledge/ (conventions stay in AGENTS.md, accumulated knowledge in knowledge/)
