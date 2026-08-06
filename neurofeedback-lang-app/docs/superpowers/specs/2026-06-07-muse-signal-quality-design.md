# Muse 2 Signal Quality Check — Design Spec

**Date:** 2026-06-07  
**Status:** Approved  
**Goal:** Gate the hardware-setup wizard's EEG step on real electrode contact quality before a capture session starts, preventing bad data from entering the annotation pipeline.

---

## Context

`muse-js` exposes no native `signalQuality` API. Quality must be derived from raw EEG samples via `MuseDeviceService.rawEeg$`. The capture wizard (`HardwareSetupComponent`) currently allows workers to advance past the EEG step as soon as the headset is connected, regardless of electrode contact.

**Gate rule:** ≥3/4 electrodes must hold `'good'` state for 3 consecutive seconds before "Weiter" enables. Workers are non-technical — warning-only would be ignored and bad sessions would result.

---

## Types

```typescript
// src/app/modules/capture/services/eeg-signal-quality.service.ts
export type ContactState = 'unknown' | 'poor' | 'good';

export interface ElectrodeQuality {
  electrode: number;   // 0–3 → TP9, AF7, AF8, TP10
  name: string;
  state: ContactState;
}
```

---

## EegSignalQualityService

**Location:** `src/app/modules/capture/services/eeg-signal-quality.service.ts`  
**Spec:** `src/app/modules/capture/services/eeg-signal-quality.service.spec.ts`  
**DI:** `providedIn: 'root'`

### API

```typescript
startMonitoring(rawEeg$: Observable<EegReading> | undefined): void
stopMonitoring(): void
readonly quality$: Observable<ElectrodeQuality[]>   // 4 entries, updated per window
readonly gateOpen$: Observable<boolean>             // true when gate condition holds
```

### Quality algorithm

Per-electrode rolling buffer of the last **256 samples** (~1 s at 256 Hz):

| Condition | State |
|-----------|-------|
| Buffer < 128 samples | `'unknown'` |
| Any sample is `NaN` in window | `'poor'` |
| Variance < `MIN_VARIANCE` (5 µV²) | `'poor'` — flat / no contact |
| Variance > `MAX_VARIANCE` (2000 µV²) | `'poor'` — excessive noise / artifact |
| Otherwise | `'good'` |

`MIN_VARIANCE` and `MAX_VARIANCE` are named constants at the top of the file. Tunable after hardware testing without touching logic.

Variance formula: `Σ(xᵢ − x̄)² / N`

### Gate logic

`gateOpen$` emits `true` when ≥3 of 4 electrodes are `'good'` for **3 continuous seconds** (configurable `GATE_DURATION_MS = 3000`). The timer resets the moment quality drops below threshold.

### Behaviour when `rawEeg$` is `undefined`

When the active device is Mock or Neurosity (`rawEeg$ = undefined`), `startMonitoring` is a no-op. `gateOpen$` emits `true` immediately. No electrode UI is shown in the wizard. The wizard behaves exactly as today for non-Muse devices.

---

## HardwareSetupComponent changes

### Trigger points

| Event | Action |
|-------|--------|
| `eegOk()` flips `true` | `eegQualityService.startMonitoring(brainDevice.rawEeg$)` |
| User taps "Zurück" from EEG step | `eegQualityService.stopMonitoring()` |
| `ngOnDestroy` | `eegQualityService.stopMonitoring()` |

### EEG step UI (Muse only — when `rawEeg$` is defined)

Below the "✓ Verbunden" chip, show 4 electrode indicators in a row:

```
TP9 [●]   AF7 [●]   AF8 [●]   TP10 [●]
```

Dot colours: grey = `'unknown'`, amber = `'poor'`, green = `'good'`.

Below the dots, a stabilisation label:
- While gate not open: `"Elektroden prüfen…"`
- While gate counting: `"Signal stabil seit N s"` (increments each second, resets on drop)
- Gate open: `"Signal bereit ✓"`

### Gate wiring

`canContinue()` for `'eeg'` case:

```typescript
case 'eeg':
  return this.eegOk() && this.eegGateOpen();
```

`eegGateOpen` = `toSignal(eegQualityService.gateOpen$, { initialValue: false })`.

For non-Muse devices, `gateOpen$` emits `true` immediately → no behavioural change.

---

## File map

| Action | Path |
|--------|------|
| Create | `src/app/modules/capture/services/eeg-signal-quality.service.ts` |
| Create | `src/app/modules/capture/services/eeg-signal-quality.service.spec.ts` |
| Modify | `src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts` |

---

## Test cases (`eeg-signal-quality.service.spec.ts`)

1. Emits `'unknown'` for all electrodes before 128 samples accumulated
2. Emits `'good'` for variance in range (5–2000 µV²)
3. Emits `'poor'` for flat signal (all-zero samples)
4. Emits `'poor'` for noisy signal (samples ±5000 µV)
5. NaN sample in window → `'poor'`
6. `gateOpen$` emits `true` after 3 s of ≥3/4 `'good'`
7. `gateOpen$` resets to `false` when quality drops mid-count
8. `rawEeg$` = `undefined` → `gateOpen$` emits `true` immediately
9. `stopMonitoring()` unsubscribes; further emissions have no effect

---

## Out of scope

- Electrode impedance display (requires hardware support not in `muse-js`)
- Signal quality during an active capture session (post-MVP)
- Neurosity signal quality (separate API, different device)
