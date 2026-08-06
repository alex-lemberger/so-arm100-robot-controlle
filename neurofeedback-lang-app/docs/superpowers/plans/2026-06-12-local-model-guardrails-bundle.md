# Local Model Guardrails + BUNDLE.md — Intent Plan

**Goal:** Make local model handoffs more reliable and self-contained. Two deliverables: a `guardrails.md` that constrains the local model to copy over invent, and a `BUNDLE.md` that packages all context into one file.

**Inspiration:** `form_outside/` — guardrails design spec + offline knowledge catalog pattern from the HDI UWWB work project.

---

## Deliverable 1: `docs/local-model/guardrails.md`

Adapted from `form_outside/2026-06-12-guardrails-decision-framework-design.md`. Five sections:

**1. Preamble (3 lines)**
Operating posture: constrained executor, copy don't invent, STOP when uncertain.

**2. Hard Stops (10 prohibitions)**
Adapted for this codebase:
- No editing `main.ts` / `app.routes.ts` outside explicit plan scope
- No hallucinated imports — verify path exists or STOP
- No new npm packages
- No touching `src/app/core/` shared services unless plan says so
- No guessing Angular Material / NGXS selector names
- No out-of-scope file edits (if plan says `demo/`, stay in `demo/`)
- No `any` casts, no `as unknown as`
- No deleting code not explicitly listed in the plan
- No unrelated refactoring
- No commits unless plan step explicitly says "Commit"

**3. Decision Trees (5 trees)**
- Async data → which service/state to use
- New component → modify existing vs create new
- Imports → verify alias exists, check CLAUDE.md, STOP if not found
- File editing → scope check, shared service check
- Compile error → fix minimally, never refactor surrounding code

**4. Pattern Templates**
Copy-paste shapes for this codebase:
- Angular standalone component (signals, `inject()`, `afterNextRender`)
- NGXS action handler (RxJS stream, `tap`, `catchError`)
- Three.js scene init (RAF loop, ResizeObserver, ngOnDestroy cleanup)
- Service with `providedIn: 'root'` and signal state

**5. Verification Gates**
Before claiming done:
- `npx tsc --noEmit` — zero errors in changed files
- `ng build --configuration development` — build succeeds
- All plan checkboxes ticked
- No files modified outside the plan's File Map
- No new imports that weren't in the plan

---

## Deliverable 2: `docs/local-model/bundle.sh` + `BUNDLE.md`

Shell script that concatenates into one file for local model ingestion:

```
BUNDLE.md = CLAUDE.md + guardrails.md + [feature spec] + [implementation plan]
```

Bundle order:
1. `CLAUDE.md` — codebase architecture, conventions, commands
2. `docs/local-model/guardrails.md` — constraints
3. Feature spec (passed as arg) — what to build
4. Implementation plan (passed as arg) — how to build it

Usage before each handoff:
```bash
cd docs/local-model
./bundle.sh \
  ../../docs/superpowers/specs/YYYY-MM-DD-feature-design.md \
  ../../docs/superpowers/plans/YYYY-MM-DD-feature.md
```

Outputs `docs/local-model/BUNDLE.md` — hand this to local model as system prompt.

---

## Integration with Existing Workflow

Current handoff: local model prompt file per feature (e.g. `2026-06-12-demo-viewer-local-model-prompt.md`)

New handoff: `BUNDLE.md` (regenerated before each handoff) replaces the per-feature prompt file. The per-feature prompt becomes the last section of BUNDLE.md automatically.

---

## Files to Create

| File | Purpose |
|------|---------|
| `docs/local-model/guardrails.md` | Constraints doc — binary rules, decision trees, templates, gates |
| `docs/local-model/bundle.sh` | Concat script |
| `docs/local-model/BUNDLE.md` | Generated output — gitignored or committed before handoff |

---

## Out of Scope

- Full knowledge catalog (7 domain files) — overkill for this repo size
- Automated CI regeneration of BUNDLE.md
- Per-session memory consolidation (existing memory system stays as-is)
