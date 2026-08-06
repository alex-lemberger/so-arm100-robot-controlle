# Architecture

## Key Decisions

- **Editing pattern:** slide-panel + uwwb-form + AsyncState<T> (not inplace editing — that's a parked POC, maintenance only)
- **Feature scaffolding:** mandatory 3-layer pattern (openapi / domain / view)
- **State management:** NGXS with AsyncState<T>, queryAsyncState, mutateAsyncState, createAsyncSelectors
- **Shared libs policy:** Do not edit uwwb-components or libs/styles without cross-team approval; prefer feature-local workarounds

## Data Flow

Frontend (Angular 21) → liability-application (Spring Boot BFF) → liability-ios (FaktorZehn IOS engine)
External: Pricing service, Partner service (both via Feign)

## Key File Locations

- Global style overrides: `libs/styles/overrides/` (imported via `libs/styles/styles.scss`)
- Risk profile views: `libs/feature/cyber/risk-profile/risk-profile-view/src/lib/`
- App-level state: `libs/global-domain/` (`@liability/domain`)
- Global OpenAPI client: `libs/openapi-liability/` (`@liability/openapi`)
- Utilities: `libs/utils/` (`@liability/utils`)
- Shell/routes: `@shell`
- Default status list: `libs/global-domain/src/assets/default-status-list.json`

## State Pattern (per feature)

4 files per domain: actions, state, selectors, postactions.
- Actions: top-level imports, minimal payloads
- State: AsyncState<T>, queryAsyncState/mutateAsyncState
- Selectors: createAsyncSelectors(State, 'key') → { loading, error, data, asyncState, mutationStatus, mutationError }
- Postactions: @Injectable() service handling UI side effects (notifications, panels, blockUI, navigation)

## Feature Status / Nav Progress

- `AppSelectors.featureStatus(name)` reads `state.statusList[name].valid`
- Populated by `AppStateActions.GetStatus` → `progressController.getStatus(offerNumber, optionIndex)`
- `RefreshWorkspace` dispatches `GetStatus` + `GetHeaderInformation`

## Shared Notification Components

- `UwwbCalculationNotificationBannerComponent` (`libs/uwwb-components/src/lib/calculation-notification-banner/`) — inputs: type, title, message, showCancelButton, cancelButtonLabel
- `UwwbCalculationErrorToastComponent` (`libs/uwwb-components/src/lib/calculation-error-toast/`) — inputs: mailtoHref, title, subtitle, reportButtonLabel; fixed bottom-right overlay
- Submit banner: SummaryState manages submitBannerType, wires to SelectOfferActions.UpdateStatus lifecycle via NGXS Actions stream

## Read-Only Mode Guard

Any view with edit actions must guard with `AppSelectors.readOnlyMode` from `@liability/domain`:
- Action buttons: `[readOnly]` on uwwb-actionelement
- Controls: checkboxes/toggles → `[disabled]`
- Cards: `[readonly]` on cardClick
- Tables: conditionally omit edit column or guard callback
- Add buttons: `[disabled]`