# Knowledge Catalog

> Offline-first knowledge base for the HDI UWWB workspace.
> Hand `BUNDLE.md` to any LLM for full context in one prompt.

Last bundled: 2026-06-12

## Contents

| File | Domain | Summary |
|------|--------|---------|
| architecture.md | System design | Data flow, 3-layer pattern, key file locations, state management decisions |
| features-active.md | Current work | Offer list enrichment, coverage detail redesign, broker card, DMS integration |
| features-parked.md | On hold | Inplace editing (parked POC), Odin migration, exclusions rework, coverage table review |
| patterns-and-gotchas.md | Lessons learned | PrimeNG fixes, readonly guards, NGXS race conditions, viewport directive |
| tooling.md | Dev environment | Local startup, mocking, Azure DevOps API, grep blindspot |
| marine-cata.md | Marine product | CaTa prototype, UI conventions, calc spec, strategic direction |
| collaboration.md | Team rules | Shared component policy, self-improvement loop, PR standards |
| guardrails.md | Decision framework | Hard stops, binary decision trees, pattern templates, verification gates |

## Usage

### Claude Code (daily driver)

You change nothing. It already works:

1. Start in `~/liability/`
2. AGENTS.md auto-loads → includes the Knowledge Catalog pointer
3. Knowledge files are read on-demand when a topic becomes relevant
4. After a significant session → relevant knowledge file gets updated, then `./bundle.sh`

### Local Model (OpenCode, Aider, LM Studio, Ollama)

**Setup (OpenCode):** Already configured via `opencode.json` — loads `guardrails-slim.md` automatically. Knowledge files available on-demand via `@knowledge/filename.md`.

**Setup (Aider):**
```bash
cd ~/liability
aider --read knowledge/guardrails-slim.md
```

**Setup (LM Studio / Ollama chat):**
```bash
cat knowledge/guardrails-slim.md | pbcopy
# Paste into system prompt field
```

### How to Prompt the Local Model (Critical)

Local models (20B-32B) follow guardrails for pattern conformance but **cannot refuse explicit file-path instructions**. They lack the reasoning to override a direct task with a system rule. Adapt your prompts accordingly:

**DO — scoped, feature-local, explicit boundaries:**
```
Add a GetRiskScores action and state handler in the cyber risk-profile domain.
Follow the existing queryAsyncState pattern.
```
```
The dropdown renders too wide in turnover-split-overview.
Fix with a feature-local workaround in risk-profile-view. Do NOT edit shared libs.
```

**DON'T — naming shared-lib files as targets (model will comply blindly):**
```
Fix libs/uwwb-components/src/lib/form/form.component.ts
```

**Rule of thumb:** Never mention a file path you don't want the model to touch. Describe the problem + scope instead.

### What Local Models Are Good At

- ✅ Scaffolding (new components, actions, selectors, state, postactions)
- ✅ Pattern replication (given a template, produce conformant code)
- ✅ Mechanical edits (rename, add fields, extend existing patterns)
- ✅ Following explicit instructions within a named feature

### What Local Models Cannot Do (Use Claude Code Instead)

- ❌ Judgment calls ("where should this fix go?")
- ❌ Self-restraint (refusing to edit a file you mentioned)
- ❌ Architecture decisions (new patterns, cross-feature changes)
- ❌ Debugging complex issues (race conditions, state lifecycle)

### Team Review

Open individual domain files in browser or PR. Each file is self-contained and reviewable independently.

### Onboarding (new dev or AI)

Hand them: AGENTS.md (conventions) + BUNDLE.md (accumulated knowledge) + guardrails.md (decision rules).

## Keeping It Fresh

| When | Do |
|------|-----|
| After a significant Claude Code session | Update the relevant knowledge file |
| Before handing off to local model | Run `cd knowledge && ./bundle.sh` |
| After a PR with new learnings | Add to patterns-and-gotchas.md or features-active.md |
| Feature moves active → parked | Move entry between files |
| Feature completed & shipped | Remove from features-active.md |

## Regenerating BUNDLE.md

```bash
cd knowledge && ./bundle.sh
```

Run this before handing off to a local model or after editing any catalog file.

## Expanding for New Backends

The catalog covers the shared Angular frontend + cross-cutting knowledge. When backend-specific knowledge grows:

1. Create `backend-{product}.md` (e.g. `backend-marine.md`)
2. Add it to `bundle.sh`'s for-loop
3. Add a row to the Contents table above
4. Run `./bundle.sh`

Current products: liability, property, cyber, marine (upcoming).
OpenCode always starts from `~/liability/` (workspace root) — `opencode.json` catches everything.

## Quick Reference

```
~/liability/
  AGENTS.md                    ← Claude Code + OpenCode read this automatically
  opencode.json                ← loads guardrails-slim.md into OpenCode context
  knowledge/
    guardrails-slim.md         ← always loaded (2KB, fits in attention)
    guardrails.md              ← full version (for Claude Code / frontier models)
    BUNDLE.md                  ← full knowledge bundle (for frontier models or manual lookup)
    bundle.sh                  ← run after edits: ./bundle.sh
    [domain files]             ← edit these, not BUNDLE.md; local model reads via @file
```
