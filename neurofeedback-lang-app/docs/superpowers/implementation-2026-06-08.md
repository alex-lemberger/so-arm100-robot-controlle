# Muse 2 Signal Quality Check Implementation Summary

## Overview
Implemented the Muse 2 signal quality check as specified in the plan document. This feature blocks the hardware-setup wizard's EEG step until ≥3/4 Muse 2 electrodes hold good contact for 3 continuous seconds, preventing bad-data capture sessions.

## Implementation Details

### 1. EegSignalQualityService (`src/app/modules/capture/services/eeg-signal-quality.service.ts`)
- **Purpose**: Derives per-electrode quality from raw EEG variance
- **Functionality**:
  - Classifies electrode contact as 'unknown', 'poor', or 'good' based on variance calculations
  - Uses a sliding window buffer of 256 samples to calculate variance
  - Implements a 3-second gate that opens only when ≥3/4 electrodes are good for 3 continuous seconds
  - Handles edge cases like NaN values and insufficient sample sizes

### 2. MockNeurosityService Enhancement (`src/app/core/neurofeedback/services/mock-neurosity.service.ts`)
- **Purpose**: Provides a simulated rawEeg$ stream for testing without hardware
- **Implementation**:
  - Replaced `rawEeg$ = undefined` with a simulated Observable stream
  - Simulates the full quality onboarding animation:
    - Phase 1 (0–1.5 seconds): Flat samples (variance = 0 → 'poor')
    - Phase 2 (1.5+ seconds): Sinusoidal samples (variance ≈ 200 µV² → 'good')
  - Gate opens after 3 seconds of phase 2 (≈4.5 seconds total from monitoring start)

### 3. HardwareSetupComponent Integration (`src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts`)
- **Purpose**: Displays electrode quality and gates the "Weiter" button
- **Features**:
  - Added electrode dot visualization showing contact quality (red = poor, green = good, gray = unknown)
  - Added status label indicating "Elektroden prüfen", "Stabilisierung...", or "Signal bereit ✓"
  - Integrated with `EegSignalQualityService` using Angular's `effect()` to start/stop monitoring
  - Gate the "Weiter" button on `eegGateOpen()` signal
  - Added proper cleanup in `ngOnDestroy()`

## Key Features Implemented

1. **Variance-based Classification**: 
   - Calculates variance from EEG samples using a sliding window of 256 samples
   - Classifies as 'poor' if variance < 5 µV² or > 2000 µV²  
   - Classifies as 'good' for variance in range [5, 2000] µV²

2. **Signal Quality Monitoring**:
   - Continuous monitoring of raw EEG data
   - 3-second timer that resets when electrode quality drops
   - Gate opens only after ≥3/4 electrodes remain good for 3 seconds

3. **Mock Testing Support**:
   - Simulated EEG stream that mimics real-world signal quality progression
   - Full end-to-end testing without hardware required

## Files Changed

1. `src/app/modules/capture/services/eeg-signal-quality.service.ts` - New service implementation
2. `src/app/modules/capture/services/eeg-signal-quality.service.spec.ts` - Unit tests for the service  
3. `src/app/core/neurofeedback/services/mock-neurosity.service.ts` - Enhanced mock with simulated stream
4. `src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts` - Component integration

## Verification

- All unit tests pass (9/9) — verified 2026-06-08
- Full compilation successful (`ng build --configuration development`)
- Mock mode testing shows proper electrode quality progression:
  - Initial flat phase (red dots)
  - Stabilization phase (amber label)
  - Good signal phase (green dots, "Signal bereit ✓" label)
  - "Weiter" button enabled only when gate opens

### Bug found and fixed during post-implementation verification

`jasmine.clock().install()` alone does **not** mock `Date.now()` — only `setTimeout`/`setInterval`. The service uses `Date.now()` to measure the 3-second gate, so the gate-timer test (`opens gate after 3 s of ≥3/4 good`) failed with `Expected false to be true`.

Fix: add `jasmine.clock().mockDate(new Date())` immediately after `jasmine.clock().install()` in `beforeEach`. Applied to `eeg-signal-quality.service.spec.ts`.

## Usage

With `environment.ts` set to `device: 'mock'`, users can test the complete signal quality workflow without hardware. In real device mode, the actual Muse headset's raw EEG data will be processed through this service.