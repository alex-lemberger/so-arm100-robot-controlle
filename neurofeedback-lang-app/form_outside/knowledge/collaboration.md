# Collaboration Rules

## Shared Components Policy

**Rule:** Do NOT edit shared libraries (`libs/uwwb-components`, `libs/styles/overrides/*`) unless explicitly asked. Default to feature-local workaround even when slightly less elegant.

**Why:** These libs are consumed by multiple teams. Any change requires cross-team defense in review (2+ teams), which significantly slows work.

**How to apply:**
- Fix could go in shared primitive OR feature → always pick feature
- Acceptable local patterns: helper component with ViewEncapsulation.None + local SCSS, `:has()` selectors, Renderer2 style injection
- Before editing anything under `libs/uwwb-components/` or `libs/styles/` → stop, propose local alternative first
- If shared edit is genuinely the only option → flag explicitly and ask before touching

**Example:** Turnover-split slide-panel width fix — solved with local `risk-profile-turnover-split-panel-style` helper component using `:has()` selector, instead of rewriting `_sidebar.scss`.

## Self-Improvement Loop

**Principle:** The self-improvement loop (capture → apply → prune) is the most important meta-aspect of this project's development process.

**Why:** Every PR, architectural decision, and recurring mistake is a learning signal. Without systematic capture, guidelines go stale and sessions repeat mistakes.

**How to apply:** At the end of any significant session, PR, or after receiving code review feedback — proactively update knowledge catalog or CLAUDE.md. Don't wait to be asked.

### Triggers (capture immediately)
- PR feedback that required a code change → update relevant knowledge file
- A pattern appearing in 3+ places that isn't documented → add to patterns-and-gotchas.md
- A bug whose root cause was an architectural violation → add as a hard stop or gotcha
- A guideline that caused confusion → clarify or remove it

### Prune regularly
- Rule not triggered in 3+ months → remove or collapse
- Two rules that contradict → resolve, document the winner
- Section never consulted → dead weight, cut it

## Code Review Standards

(Detailed conventions live in AGENTS.md — this section captures accumulated review learnings)

- Guard all edit actions with `AppSelectors.readOnlyMode` in every new view
- Never skip the failing-test step in TDD — even for "obvious" implementations
- Prefer `selectSignal` over `select` + async pipe in new components
- Always check if feature state is lazy-loaded — selectors need `?.` optional chaining
- When touching cyber-program-coverage, check the 10-item priority list in coverage-table-review-pending first
- Postactions must always be paired with state — never register one without the other
- Feature-local SCSS workarounds are preferred over shared lib edits, even if less elegant
