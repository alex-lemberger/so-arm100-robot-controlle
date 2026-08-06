# NGXS to Signal Store Migration Plan

## Overview
This document outlines the migration strategy for transitioning from NGXS state management to Angular's Signal Store in the neurofeedback language learning application.

## Current State
The application uses three NGXS stores:
- `ExerciseState` (complex async operations)
- `CaptureState` (simple state machine)  
- `DashboardState` (moderate complexity async data)

## Migration Strategy

### Phase 1: Preparation
1. Review all store actions and state patterns in existing NGXS stores
2. Identify dependencies between stores and components
3. Document current selector usage and observable patterns

### Phase 2: Store Migration
1. Convert each NGXS store to Signal Store pattern:
   - Define signals for state properties
   - Implement store methods as functions returning signals
   - Handle async operations using Angular's signal patterns

### Phase 3: Component Updates
1. Replace `toSignal()` usage with adapted patterns (if needed)
2. Update template references to state properties
3. Remove NGXS-related imports and providers

### Phase 4: Testing & Verification
1. Run existing tests to ensure functionality preserved
2. Verify all state transitions work correctly
3. Confirm performance improvements

## Timeline
- Phase 1: 2 hours
- Phase 2: 4 hours  
- Phase 3: 2 hours
- Phase 4: 2 hours
Total: ~10 hours for complete migration

## Risk Assessment
- Low risk due to simple store structure (only 3 stores)
- Minimal breaking changes expected
- Components already use signal-based consumption patterns