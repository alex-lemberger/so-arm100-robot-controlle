# Memory Leak Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed `calm$` subscription leak in `LearningSessionService` where the subscription is created but never stored or cleaned up.

**Architecture:** Single-file fix. `startMetricsCollection()` creates two subscriptions but only assigns one to `this.metricsSubscription`. Use `new Subscription()` + `.add()` to collect both into the existing field so `endSession()` and `interruptSession()` clean up both automatically — no other changes required.

**Tech Stack:** Angular 19, RxJS (`Subscription` — already imported)

---

## Audit corrections

Two findings from the design spec were invalidated by reading the actual code:

- **Fix 1 (shareReplay on NeurosityService)** — false positive. `focus$` and `calm$` are `BehaviorSubject`s (lines 17–18). The `new Observable()` wrappers inside `setupSubscriptions()` subscribe to the Neurosity SDK **once** and push values into those subjects. All consumers subscribe to the `BehaviorSubject`, not the SDK stream. No `shareReplay` needed.
- **Fix 3 (DashboardComponent timer)** — already implemented. `ngOnDestroy()` at line 205 already calls `stopTimer()` unconditionally.

Only Fix 2 requires a code change.

---

## Files

| Action | Path | Lines |
|--------|------|-------|
| Modify | `src/app/core/neurofeedback/services/learning-session.service.ts` | 59–70 |

---

## Task 1: Fix `calm$` subscription leak in `LearningSessionService`

**File:** `src/app/core/neurofeedback/services/learning-session.service.ts`

> **Test environment note:** Karma/Jasmine tests are currently broken app-wide (`parcelRequire is not defined` from `@neurosity/sdk` — documented in CLAUDE.md). Verification is done via compilation check + code review.

**Current broken code (lines 59–70):**

```typescript
private startMetricsCollection(sessionId: string): void {
  this.metricsSubscription = this.device.focus$.subscribe(focus => {
    if (focus !== null) {
      this.updateMetrics(sessionId, focus, this._sessionState.value.currentCalm);
    }
  });
  this.device.calm$.subscribe(calm => {       // ← result discarded, never unsubscribed
    if (calm !== null) {
      this.updateMetrics(sessionId, this._sessionState.value.currentFocus, calm);
    }
  });
}
```

**Why it leaks:** `this.metricsSubscription` holds only the `focus$` subscription. The `calm$` subscription is discarded. When `endSession()` or `interruptSession()` calls `this.metricsSubscription?.unsubscribe()`, the `calm$` subscription keeps running until the service is destroyed.

- [ ] **Step 1: Apply the fix**

Replace lines 59–70 in `src/app/core/neurofeedback/services/learning-session.service.ts`:

```typescript
private startMetricsCollection(sessionId: string): void {
  this.metricsSubscription = new Subscription();
  this.metricsSubscription.add(
    this.device.focus$.subscribe(focus => {
      if (focus !== null) {
        this.updateMetrics(sessionId, focus, this._sessionState.value.currentCalm);
      }
    })
  );
  this.metricsSubscription.add(
    this.device.calm$.subscribe(calm => {
      if (calm !== null) {
        this.updateMetrics(sessionId, this._sessionState.value.currentFocus, calm);
      }
    })
  );
}
```

`Subscription` is already imported on line 3 — no import changes needed.

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds with no TypeScript errors. If errors appear, check that `Subscription` import on line 3 still reads `import { BehaviorSubject, Subject, Subscription, interval } from 'rxjs';`.

- [ ] **Step 3: Review cleanup sites**

Confirm `endSession()` (line 127) and `interruptSession()` (line 145) still read:
```typescript
this.metricsSubscription?.unsubscribe();
```
No change needed — `Subscription.unsubscribe()` propagates to all children added via `.add()`.

- [ ] **Step 4: Commit**

```bash
git add src/app/core/neurofeedback/services/learning-session.service.ts
git commit -m "fix(session): store calm\$ subscription to prevent leak on session end"
```

---

## Post-implementation note

Update `docs/superpowers/specs/2026-06-08-memory-leak-fixes-design.md` to mark Fix 1 and Fix 3 as invalidated (false positives), so future readers don't re-investigate. This is optional — the spec is already committed and this plan file captures the correction.
