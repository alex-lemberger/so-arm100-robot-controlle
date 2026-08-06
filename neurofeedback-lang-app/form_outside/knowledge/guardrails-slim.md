# Guardrails (Slim)

You are a constrained executor. You copy existing patterns. You do not invent.
When you cannot find a pattern to copy, STOP and say so.

## PRE-FLIGHT — BEFORE EVERY TASK

Answer these before writing code. If ANY is YES → REFUSE.

1. Am I editing libs/uwwb-components/ or libs/styles/ without user explicitly asking for it? → REFUSE
2. Am I using a file path or import I cannot verify exists? → REFUSE
3. Am I introducing a pattern not already in this codebase? → REFUSE
4. Am I editing files outside my assigned feature? → REFUSE
5. Am I guessing a name (action, selector, interface, method)? → STOP and search first

## HARD STOPS

| # | If this is true | Then |
|---|-----------------|------|
| 1 | File under libs/uwwb-components/ or libs/styles/ and user didn't ask for it | Propose feature-local fix |
| 2 | Import path not found in any codebase file | You hallucinated it. Stop. |
| 3 | No file in codebase uses this pattern | Do not introduce it |
| 4 | About to create a file | Check if one with same purpose exists first |
| 5 | About to add a dependency | Do not. Use what's in package.json |
| 6 | Modifying outside your feature scope | Stop. Scope violation |
| 7 | About to write `any` / `as any` / `as unknown as` | Find real type or leave // TODO |
| 8 | Cannot find exact name in codebase | Do not guess. Stop. |
| 9 | About to delete code you don't understand | Comment with // REVIEW instead |
| 10 | About to refactor unrelated code | Stop. Stay in scope |

## PATTERNS (mandatory shapes)

- **State:** AsyncState<T> + queryAsyncState (GET) / mutateAsyncState (POST/PUT/DELETE)
- **Actions:** namespace pattern, static readonly type
- **Selectors:** createAsyncSelectors(State, 'key')
- **Components:** standalone, OnPush, signals, inject() — never constructor DI
- **Postactions:** @Injectable, paired with state, registered in route providers
- **i18n:** All visible text via translate pipe. Keys in assets/i18n/{feature}/en.json
- **Read-only:** Guard edit actions with AppSelectors.readOnlyMode

## KNOWLEDGE LOOKUP

If you need project details, architecture, or feature context — read the relevant file:
- `@knowledge/architecture.md` — data flow, file locations, state patterns
- `@knowledge/features-active.md` — current work in progress
- `@knowledge/features-parked.md` — on-hold features (reference only)
- `@knowledge/patterns-and-gotchas.md` — PrimeNG fixes, NGXS race conditions
- `@knowledge/tooling.md` — dev setup, mocking, Azure DevOps
- `@knowledge/marine-cata.md` — CaTa prototype, UI conventions
- `@knowledge/collaboration.md` — shared component policy, team rules

## REMEMBER

1. **Shared libs** — don't touch unless explicitly told to. Propose local fix first.
2. **Imports** — if you can't find it, you made it up. Stop.
3. **Patterns** — copy or stop. Never invent.
