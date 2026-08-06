# Parked & On-Hold Features

Features that are paused, awaiting external input, or maintenance-only. Preserved here for context when touching related code.

## Inplace Editing (Parked POC — maintenance only)

**Status:** Not for new features. Existing risk-profile code (GeneralInformation, RiskAssessment, StandardsCertifications, ExclusionsAndDefinitions) maintained as-is.

**Why parked:** Confirmed by user — won't be adopted. New features use slide-panel + uwwb-form + AsyncState<T>.

### Architecture (reference only)

**Dual state pattern:**
```typescript
interface XxxStateModel {
    saved?: Resource | null;   // last persisted server response
    edited?: Resource | null;  // validate-only response (carries messages)
}
```
- GET: sets both saved + edited
- UPDATE with onlyValidate=true: sets only edited
- UPDATE with onlyValidate=false: sets both
- RESET: `ctx.patchState({ edited: state.saved })`

**validateAndSave pattern:** Component dispatches validate (true) → checks messages → dispatches save (false). `hasErrorMessage` util in `risk-profile-view/src/lib/inplace-validation.util.ts`.

**Postactions:** Every inplace state needs `XxxPostactions` (@Injectable), registered in routes.ts providers alongside state.

**Label convention:** `uwwb-label-field` and `uwwb-inplace-field` append `.LABEL` internally. Model labels must NOT include `.LABEL`. Exception: `CollapsibleGroupModel` uses `| translate` directly.

**Alignment fix:** Read-only fields need 8px padding-left via `::ng-deep uwwb-inplace-card div.p-2 > uwwb-label-field > div { padding-left: 8px; }` in feature SCSS.

### Known issues
- Risk-profile states pass offerNumber in action payload (should read from AppSelectors)
- hasErrorMessage util duplicated in cyber-program-coverage-view
- Risk-profile states don't use AsyncState<T>

## Odin Migration — Option C

**Status:** Awaiting feedback from system architect + Odin team.

**Plan:** Incremental CDK-based migration: Slide Panel → Form → Toast → Card → Table. Preferred location: inside Odin repo (contributing directly to hdi-components).

**8 P0 blockers remain:** Table, Form, Slide Panel, Toast, Editor, Card, Skeleton, Tree Table.

**Key decisions:**
- Use Angular CDK (already v21.2.8 in deps) + Odin design tokens as foundation
- Keep same public API as uwwb-components (drop-in replacement per feature)
- Coexistence: both libraries side-by-side during transition

**Impression:** Odin team delivers "website" components, not "enterprise app" components. May need architecture-level escalation.

## Exclusions & Definitions Review Rework

**Status:** Full DOR available, not yet started.

**Scope:** Frontend-only. Replaces dropdown (SELECT) with checkbox for exclusion status. Adds colored status badges (INCLUDED=green, EXCLUDED=red, NA=gray).

**Key decisions:**
- Badge component moves from property domain to uwwb-components (Nx boundary fix)
- Overview stays in CardModel pattern with `type: 'template'` + templateRef
- Edit panel: FormControlType.CHECKBOX. NA rows → disabled. Transform boolean↔IdAndLabel at view boundary.
- Data model: `IdAndLabelResourceEventExclusion.IdEnum` = `'INCLUDED' | 'EXCLUDED' | 'NA'`

## Coverage Table Data Flow Review

**Status:** 10 findings documented. Two HIGH items first.

**Priority list:**
1. (HIGH) No ngxsOnInit — option change does not re-load coverage data
2. (HIGH) GetCyberContract should read offerNumber/optionIndex from state, not action payload
3. (MEDIUM) `depth` field on CyberCoverageResource belongs on CoverageNodeModel, not domain type
4. (MEDIUM) Missing debounce on coverage search input
5. (MEDIUM) `editingContractHasValidationErrors` hardcodes field paths — brittle on API change
6. (MEDIUM) `filterSelectedCoverageNodes`/`filterCoverageNodesByName` in wrong file (selectors, not utilities)
7. (MEDIUM) `as unknown as` type assertion at component/table boundary
8. (LOW) `callbackValidationMessages` dead code
9. (LOW) Duplicate dispatch pattern in postactions success handlers
10. (LOW) Sync-only actions misleadingly included in error handler

See `docs/reviews/coverage-table-data-flow-review.md` for full details.
