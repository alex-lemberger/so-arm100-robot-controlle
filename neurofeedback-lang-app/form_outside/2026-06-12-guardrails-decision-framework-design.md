# Guardrails Decision Framework — Design Spec

**Date:** 2026-06-12  
**Goal:** Create a `guardrails.md` file that constrains a local LLM (20B-32B) to make correct decisions when coding in the HDI UWWB codebase — minimizing hallucination, pattern invention, scope creep, and convention drift through purely prompt-based, self-enforced rules.

## Problem

A local model loaded with BUNDLE.md has *knowledge* (what exists, what happened) but not *judgment* (how to decide when something isn't explicitly covered). Without guardrails, it will:
- Hallucinate import paths, API methods, component selectors that don't exist
- Invent new patterns instead of copying existing ones
- Edit shared code or modify files outside its scope
- Drift from naming conventions, file structure, and state management patterns

## Solution

A single `knowledge/guardrails.md` file — a cognitive prosthetic for a simpler brain. Five progressively-layered sections that a mechanistic reasoner can follow without needing taste or experience.

## Design Philosophy

1. **Every decision is binary.** Yes/no. Never "choose the best."
2. **Copy over create.** The model's job is imitation, not innovation.
3. **Fail safe.** When uncertain → STOP. Never guess.
4. **Progressive depth.** A model that reads only section 1-2 still avoids catastrophe. All 5 sections → conformant code.
5. **No judgment required.** Each rule is a factual check, not a quality assessment.

## File Location

`knowledge/guardrails.md` — included in BUNDLE.md via bundle.sh (appended after collaboration.md).

## Structure

### Section 1: Preamble (3 lines)

Sets operating posture: "You are a constrained executor. You copy, you don't invent. When you can't find a pattern, you stop."

### Section 2: Hard Stops (10 absolute prohibitions)

Binary conditions. If true → action is forbidden. No exceptions, no "unless."

| # | Prevents |
|---|----------|
| 1 | Editing shared libs (uwwb-components, styles) |
| 2 | Hallucinated imports |
| 3 | Pattern invention |
| 4 | Unnecessary file creation |
| 5 | Dependency addition |
| 6 | Scope violation (out-of-feature edits) |
| 7 | Type escape hatches (any, as unknown as) |
| 8 | Guessed selector/action/interface names |
| 9 | Deleting code without understanding it |
| 10 | Unrelated refactoring |

### Section 3: Decision Trees (6 binary trees)

Common coding forks resolved through yes/no questions:

1. **Async data** → where state goes, which helper to use
2. **New component** → modify existing vs create, shared vs local
3. **Imports** → verify existence, use aliases, STOP if not found
4. **Editing existing files** → scope check, shared lib check, size check
5. **User-visible text** → i18n key lookup, format convention
6. **Error handling** → propagate vs copy existing pattern vs console.warn

Each tree terminates in either a concrete action or STOP.

### Section 4: Pattern Templates (6 copy-paste shapes)

Actual code shapes for the most common things the model produces:
- New action (namespace pattern)
- State handler - query (queryAsyncState)
- State handler - mutation (mutateAsyncState)
- Selectors (createAsyncSelectors)
- Component (standalone, OnPush, signals)
- Postactions (@Injectable, ofActionSuccessful)
- Route registration (providers array)

Model's job: find template → substitute names. No creativity required.

### Section 5: Verification Gates (5 gates, ~20 checks)

Pre-completion checklist:
1. **Imports** — all paths exist, aliases used, no new deps
2. **File discipline** — no duplicates, naming matches neighbors, scope respected
3. **Pattern conformance** — AsyncState, standalone, namespace actions, createAsyncSelectors
4. **No invention** — no new patterns, no unnecessary abstractions
5. **Completeness** — i18n, readOnlyMode guards, postactions paired with state

## Integration with Knowledge Catalog

- `_index.md` gets a new row in the Contents table
- `bundle.sh` includes `guardrails.md` in the concatenation loop (after `collaboration.md`)
- BUNDLE.md regenerated to include guardrails

## Success Criteria

1. A 20B-32B model following guardrails.md produces code that passes the verification gates without human intervention
2. Zero hallucinated imports (the model either finds the real path or STOPs)
3. Zero new patterns introduced — all code matches existing codebase shapes
4. No edits to shared libraries or out-of-scope files
5. A human reviewing the output finds it "boring" — indistinguishable from the rest of the codebase
