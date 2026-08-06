# Spec: Cognitive-State Labels for Capture Sessions

**Date:** 2026-06-09 · **Status:** Approved design (pre-plan) · **Vertical:** Handwerk capture (`modules/capture/`)

## 1. Goal

Label every capture session with per-tick **cognitive state** derived from the Muse EEG — **focus**, **cognitive load**, and a relative **fatigue** trend — so the captured skill dataset carries cognitive context alongside motion (IMU) and video. Primary value: a richer, partially self-cleaning dataset for the skill/robot thesis. Secondary, near-free: a basis for live readouts and post-session insight later.

Fidelity stance: **honest heuristic proxies, clearly labeled — not clinical metrics.** Same framing as the existing `focus`/`calm`.

## 2. Non-goals (Phase 1)

- Live UI gauges / alerts in the capture flow.
- Stored segment flags (computed on read instead).
- Validated/clinical fatigue or load metrics.
- Multi-electrode continuous signal quality (the adapter derives bands from one electrode; see §8).

## 3. Signals & definitions

All derived from `BrainDevice.extras$`, which the Muse adapter **already emits** as normalized fractions `{ theta, alpha, beta }` (each = band / (theta+alpha+beta)). Ratios below are normalization-invariant. Pure functions, all nullable.

- **Load** `= theta / (theta + alpha)` → naturally bounded [0,1]; ↑theta vs alpha ⇒ higher load. `null` if `theta+alpha == 0`.
- **Fatigue** — relative drift, not absolute:
  - per-tick index `I = (theta + alpha) / beta` (`null` if `beta == 0`).
  - **baseline** `I₀` = mean `I` over the first `BASELINE_MS = 30000` of the session.
  - `fatigue = clamp01( (I / I₀ − 1) / FATIGUE_SPAN )`, `FATIGUE_SPAN = 1.0` (a doubling of the index ⇒ fatigue ≈ 1.0). `null` until baseline established.
- **signal_ok** (per tick, boolean): Phase-1 = a lightweight liveness flag derived **in `CognitiveStateService`/`stepCognitive`** (band powers present and finite) — no adapter change. The wizard's ≥3/4-electrode check still gates **fit before capture starts**; robust continuous multi-electrode quality is future work (§8).

Constants (`BASELINE_MS`, `FATIGUE_SPAN`, load formula) live with the pure functions and are tunable.

## 4. Architecture & data flow

```
Muse raw EEG ─► muse-eeg-utils.bandPowers() ─► BrainDevice.extras$ { theta, alpha, beta, signalOk }
                                                       │ (already emitted; today unused)
                                          CognitiveStateService (new, root)
                                            • subscribes extras$
                                            • holds session baseline I₀
                                            • load$, fatigue$, signalOk$
                                                       │
CaptureSessionService  ── per tick ──► writeEegTick(sessionId, focus, calm, inFlow, load, fatigue, signalOk)
                                                       │
                                                  eeg_ticks  (+ load, fatigue, signal_ok)
```

Mirrors the existing `FlowDetectorService` pattern (stream in → derived state out). No new infrastructure.

**Cadence & transport (verified):** the Muse adapter emits `extras$` at **~4 Hz** — a 256-sample (1 s) sliding window over electrode **AF7 (left frontal)**, recomputed every 64 samples (0.25 s, 75 % overlap). `CognitiveStateService` inherits ~4 Hz; `CaptureSessionService` **downsamples** to the existing per-tick write rate. Transport is **Web Bluetooth (BLE)**, same as the IMU gloves (HTTPS + Chrome/Android); one device pairs with Muse + both gloves at once — confirm 3-peripheral stability in the field.

## 5. Components

- **`core/neurofeedback/cognitive-metrics.ts`** (new, pure): `loadFromBands(theta, alpha)`, `fatigueIndex(theta, alpha, beta)` → `(theta+alpha)/beta`, `fatigueFromIndex(index, baseline)`, constants. No Angular/SDK imports → unit-testable without Karma.
- **`CognitiveStateService`** (new, `providedIn: 'root'`, mirrors `FlowDetectorService`): subscribes `extras$`; maintains baseline state; exposes `load$`, `fatigue$`, `signalOk$`; `startSession()` resets baseline, `endSession()` clears.
- **Muse adapter** (`muse-device.service.ts`): **no change** — it already emits normalized `{theta, alpha, beta}` on `extras$`; `signal_ok` is derived downstream.
- **`SupabaseCaptureService.writeEegTick`**: extend signature → `(sessionId, focus, calm, inFlow, load, fatigue, signalOk)`; insert the new columns.
- **`CaptureSessionService`**: call `CognitiveStateService.startSession()` on session start; per tick read `load`/`fatigue`/`signalOk` and pass to `writeEegTick`.
- **`EegTick` model**: add `load: number | null`, `fatigue: number | null`, `signalOk: boolean | null`.
- **DB migration**: `eeg_ticks` add `load real`, `fatigue real`, `signal_ok boolean` — all **nullable** (backward-compatible; existing rows stay valid).
- **Segment flags** ("fatigued" / "low-signal" runs): **computed on read** (dashboard/query), not stored.

## 6. Error handling & edge cases

- Non-Muse device / mock / empty `extras$` → `load`/`fatigue`/`signalOk` = `null`; nullable columns absorb it.
- Baseline window not yet filled → `fatigue = null`.
- Division by zero / NaN in any ratio → guarded → `null`.
- `writeEegTick` failure → already logged (`console.error`); a failed tick must not abort the capture session.

## 7. Testing

- `cognitive-metrics.ts` pure functions → unit tests, verified via `node` + `npx tsc -p tsconfig.spec.json --noEmit` (Karma broken repo-wide — Principle #13; do not claim a Karma pass).
- Baseline/drift logic → tested on a synthetic band-power sequence (rising theta+alpha ⇒ rising fatigue; flat ⇒ ~0).
- Cases per metric: bounds (0/1), null paths (zero denom, pre-baseline), monotonicity.

## 8. Known limitations (state them, don't hide them)

- **Single-electrode bands (AF7, left frontal):** the adapter computes bands from one electrode, not a montage. AF7 is *well-suited* here — frontal theta tracks mental effort — so the single-channel limit is less severe for load/fatigue than it would be for motor tasks. A multi-electrode upgrade is future work.
- **Heuristic, relative:** fatigue is drift-vs-baseline within a session, not an absolute or cross-session measure. Not clinical.
- **`signal_ok` is coarse** in Phase 1 (single-electrode liveness); the strong fit guarantee is the pre-capture wizard gate.

## 9. Verification before "done"

- `ng build --configuration development` green.
- Pure-fn tests pass via node + typecheck via tsc spec config.
- Runtime: a mock-mode capture writes ticks with `load`/`fatigue` populated (or null where expected); confirm `eeg_ticks` rows.

## 10. Open items for the plan

- Confirm the exact `eeg_ticks` migration path (SQL applied to the live Frankfurt project).
- Decide where the per-tick cadence comes from today (reuse the existing tick interval in `CaptureSessionService`).
- (Door-open, not Phase 1) raw EEG retention via `eeg_path` would allow reprocessing if metrics evolve — confirm separately.
