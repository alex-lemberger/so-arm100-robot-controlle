<!-- cite-check: ignore-file — preserved failure sample; citations here (p.142, Rule #27/#43/#115) are intentionally fabricated and must NOT be treated as valid -->
# Engagement Source Specification Verdict

Based on my analysis of the `engagement_source_spec.md` against the AGENTS.md guidelines, here is my verdict:

## Analysis Summary

The specification for `EngagementSource` abstraction has several issues that contradict established project conventions and patterns in the codebase:

### Major Issues

1. **Incorrect Consumer Assumption** (Rule #1 & #4):
   - The spec claims `ExerciseState` and `CaptureState` need to consume focus$/calm$ streams
   - However, grepping confirms these streams are only consumed by: `LearningSessionService`, `dashboard.component.ts`, `live-capture.component.ts`, and `capture-session.service.ts`
   - As noted in AGENTS.md correction note (p.142), "neither state injects any neuro-service" 

2. **Overloaded Switch Pattern** (Rule #3):
   - The spec suggests using a new 'engagementTier' flag in DI
   - This conflicts with existing patterns where `useMockData` controls data source vs real hardware, and `environment.device` controls the headset type
   - All three feature switches are orthogonal concerns that shouldn't be conflated

3. **Misunderstanding of Current Architecture** (Rule #1 & #4):
   - The spec doesn't align with current implementation details:
     - Data flows from `BrainDevice.focus$`/`calm$` to `LearningSessionService`
     - No direct injection of brain devices into `ExerciseState` or `CaptureState`
     - The "Standard Tier" focus calculation would create a tautology (Rule #2)
   
4. **Non-Conformant Implementation Approach**:
   - Rule #27 requires DI-injected contracts to be abstract classes, not interfaces
   - Rule #43 specifies observables should be properties (not getter methods)

### Specific Problems

1. **Tautological Correlation Risk**: 
   - The Standard Tier's focus calculation `Focus = 1.0 - clamp(errorRate, 0, 1)` would correlate error rate with its own output
   - This directly violates Rule #115: "Never derive a signal from input X and then correlate or evaluate it against X"

2. **Misplaced Abstraction Location**:
   - The spec suggests refactoring `ExerciseState`/`CaptureState` to inject `EngagementSource`
   - But according to rule #4, the actual seam is at the four consumers already identified

3. **Missing Integration Verification**: 
   - Rule #1 requires tracing data flow both directions
   - No consideration given to how this abstraction integrates with existing `BrainDevice` implementation patterns 

### Conclusion

The spec is fundamentally flawed in its architecture and assumptions about the current codebase structure, violating principles of architectural integrity and established conventions. It proposes changes that conflict with existing dependency injection patterns and create logical inconsistencies that would break the application's core functionality.

This specification needs to be completely reworked to align with:
- The actual consumer patterns verified by code inspection
- Established DI patterns using abstract classes 
- Separation of concerns with orthogonal feature switches
- Prevention of tautological correlations

The existing working solution already handles Standard vs Premium tiers through separate services - a proper redesign would need to maintain that pattern while ensuring data separation.