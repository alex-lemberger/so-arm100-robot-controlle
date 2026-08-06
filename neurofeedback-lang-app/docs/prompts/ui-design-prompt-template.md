# UI / Frontend Design Prompt Template

A reusable prompt for asking Claude to design and generate UI for **this** app
(NeurofeedbackLangApp). Copy the **PROMPT** block below, fill the `{{slots}}`,
delete the guidance comments, and paste it into Claude.

- Keep the **Stack & conventions** and **Quality bar** sections as-is — they are
  pre-filled for this repo and rarely change.
- Fill **Task**, **Screen/component**, **Content & data**, and **Style direction**
  per request.
- Leave a slot blank only if you truly have no preference; an empty slot tells
  Claude to choose and explain.

---

## PROMPT (copy from here ↓)

```
You are designing a production-grade UI for an existing Angular application.
Match the codebase's conventions exactly; do not introduce a new framework,
component library, or styling system. Avoid generic "AI dashboard" aesthetics —
aim for a distinctive, considered interface with real visual hierarchy.

## Stack & conventions (fixed — obey these)
- Angular 19, **standalone components** (no NgModules). Selector prefix `app`.
- Styling: **SCSS** component styles + **Tailwind** utility classes. Angular
  Material (prebuilt theme `azure-blue`) for complex widgets (dialogs, tables,
  snackbars, icons). Prefer Material for behavior, Tailwind for layout/spacing,
  SCSS for bespoke visuals.
- State: NGXS stores; components consume state via `toSignal()` and Angular
  Signals (not the `async` pipe) for new work.
- Charts: **d3** (v7) — there are existing chart components (focus/bar/pie/
  scatter) under `core/visualisations/charts`. Reuse their pattern for any new
  data viz; don't add a charting library.
- Reactive data arrives as RxJS `Observable`/`BehaviorSubject` (e.g. live
  focus/calm metrics 0–1, null until data). Handle the null/loading state.
- App domain: neurofeedback (live EEG focus/calm) paired with language-learning
  exercises. Tone: calm, focused, clinical-but-warm — not gamified-loud.

## Task
{{What to design. e.g. "Redesign the dashboard landing view" /
"New component: session summary card" / "Empty + loading states for the
exercises list".}}

## Screen / component
- Name & route (if known): {{e.g. DashboardComponent, /dashboard}}
- Type: {{full page | layout shell | single component | state (empty/loading/error)}}
- Where it lives: {{e.g. shared/components/layout/... | modules/language-learning/...}}

## Content & data
- Key elements to show: {{list the real content — metrics, lists, controls, CTAs}}
- Data shape / source: {{e.g. focus$/calm$ streams; ExerciseBase[] from NGXS;
  CorrelationData[]}}
- Primary user action: {{the one thing the user is here to do}}
- States to cover: {{loading / empty / error / populated — pick the ones that apply}}

## Style direction
- Mood / adjectives: {{3–5 words, e.g. "calm, precise, data-forward, spacious"}}
- Density: {{airy | balanced | dense/information-rich}}
- Dark mode: {{required | nice-to-have | not now}}
- Inspiration / anti-patterns: {{optional refs or "avoid X"}}
- Color: lead with the existing Material azure-blue accent unless told otherwise;
  propose any additional accent and justify it.

## Constraints
- Responsive: {{desktop-first | mobile-first | both — and key breakpoints}}
- Accessibility: WCAG AA — keyboard reachable, visible focus, labelled controls,
  color contrast ≥ 4.5:1, and don't encode meaning in color alone (relevant for
  focus/calm viz). {{add any extra}}
- Performance / scope limits: {{e.g. "no new npm deps", "≤ 2 new components"}}

## Deliverables (in this order)
1. **Design rationale** — 4–8 sentences: the core layout idea, visual hierarchy,
   and why it fits the neurofeedback domain. Call out one or two distinctive
   choices (not generic).
2. **Layout sketch** — ASCII/wireframe of the structure and responsive behavior.
3. **Component plan** — files to create/modify (exact paths), each component's
   one-line responsibility, inputs/outputs (signals), and which existing pieces
   (Material widgets, chart components, NGXS selectors) it reuses.
4. **Code** — standalone Angular component(s): `.ts` (+ inline or separate
   `.html`/`.scss` matching the file's neighbors), Tailwind in the template,
   SCSS for bespoke styling, Signals for state. Production-quality, typed, with
   loading/empty/error states wired. No placeholder `// TODO` in the happy path.
5. **Tokens & states** — the spacing/color/typography choices used, and how
   interactive states (hover/focus/active/disabled) look.

## Quality bar
- Distinctive, not template-generic: deliberate hierarchy, intentional spacing
  rhythm, real empty/loading states — not a grid of identical gray cards.
- Internally consistent with the existing app (spacing scale, radius, elevation,
  the azure-blue accent) — a new screen should look like it belongs.
- Every interactive element has hover/focus/active/disabled states.
- Accessible by construction (see Constraints), not bolted on.
- If a requirement is ambiguous, state your assumption in one line and proceed —
  don't stall.
```

## (end copy ↑)

---

## Quick-fill example

> **Task:** New component — live "Focus & Calm" panel for the dashboard.
> **Screen/component:** `FocusCalmPanelComponent`, single component, lives in
> `shared/components/layout/dashboard-layout/`.
> **Content & data:** two live gauges (focus, calm, 0–1) from `focus$`/`calm$`,
> a 50-point rolling scatter (reuse `scatter-plot` pattern), a connect/disconnect
> control. States: disconnected (no data), connecting, streaming.
> **Style direction:** calm, precise, data-forward; balanced density; dark mode
> nice-to-have.
> **Constraints:** desktop-first (≥1024) + graceful ≤768; no new deps.

## Tips

- One screen/flow per prompt. Splitting big requests yields sharper output.
- For revisions, paste the prior code back and describe the delta — don't restart.
- Want options? Add: "Give 2 distinct directions before coding; I'll pick one."
  (Pairs well with the project's brainstorming flow.)
- To push past generic results, name a concrete reference or an explicit
  anti-pattern in **Style direction**.
