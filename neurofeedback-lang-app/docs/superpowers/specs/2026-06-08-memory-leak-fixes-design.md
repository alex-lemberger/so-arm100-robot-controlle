# Memory Leak Fixes — Design Spec

**Date:** 2026-06-08  
**Scope:** Surgical — 3 files, ~10 lines changed  
**Approach:** Fix confirmed leaks only; no idiom migration, no restructuring

---

## Problem

Three confirmed memory leaks found during audit:

1. `NeurosityService` hot observables (`focus$`, `calm$`, `rawEeg$`) are cold-wrapped — each subscriber opens a new SDK connection to the Neurosity device.
2. `LearningSessionService.startMetricsCollection()` creates two subscriptions but only stores one; `calm$` subscription is never unsubscribed.
3. `DashboardComponent.ngOnDestroy()` may skip `stopTimer()` if a session was never started, leaving a live `setInterval` after component destroy.

---

## Fix 1 — `shareReplay` on hot observables

**File:** `src/app/core/neurofeedback/services/neurosity.service.ts`

Add `shareReplay({ bufferSize: 1, refCount: true })` to `focus$`, `calm$`, and `rawEeg$` observables before the `takeUntil(this.destroy$)` operator.

- `bufferSize: 1` — late subscribers get the last emitted value immediately (same as current BehaviorSubject-like behavior)
- `refCount: true` — shared subscription tears down when all consumers unsubscribe; no phantom subscriptions in tests or after navigation

**No change to consumers** — `toSignal()`, `subscribe()` callers unaffected.

---

## Fix 2 — Store + unsubscribe both session subscriptions

**File:** `src/app/core/neurofeedback/services/learning-session.service.ts`

Replace two separate subscription assignments with a single `Subscription` container using `.add()`:

```typescript
this.metricsSubscription = new Subscription();
this.metricsSubscription.add(this.device.focus$.subscribe(...));
this.metricsSubscription.add(this.device.calm$.subscribe(...));
```

`endSession()` and `interruptSession()` already call `this.metricsSubscription?.unsubscribe()` — both subscriptions are now cleaned up by existing code with no further changes.

---

## Fix 3 — Unconditional `stopTimer()` in `ngOnDestroy`

**File:** `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts`

Call `this.stopTimer()` as the first statement in `ngOnDestroy()`, unconditionally. `stopTimer()` already guards internally with `clearInterval(this.timerId)` — safe when timer was never started.

---

## Out of scope

- `takeUntilDestroyed` migration (separate pass)
- `inject()` idiom migration (separate pass)
- Bundle / lazy-loading (separate pass)
- D3 chart change detection (separate pass)
- `MockNeurosityService.rawEeg$` interval (low priority; only affects mock mode)

---

## Success criteria

- No new SDK subscriptions opened on each consumer subscribe
- `calm$` subscription cleaned up on `endSession()` and `interruptSession()`
- No live `setInterval` after `DashboardComponent` is destroyed
- All existing behavior unchanged on happy path
