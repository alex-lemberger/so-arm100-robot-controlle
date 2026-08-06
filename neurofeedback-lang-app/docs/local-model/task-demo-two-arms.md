# Local Model Task — Demo Viewer: Add Second Arm

Copy the block below verbatim as your first message to the local model.

---

```
You are adding a second robot arm to an existing Angular 19 Three.js demo at:
/Users/alexanderlemberger/neurofeedback-lang-app

## Task

Add a mirrored left arm to the demo viewer so the scene shows two arms
working in parallel — right arm traces the right half of the wall, left arm
traces the left half, both using boustrophedon paths.

## Files to change (ONLY these two)

1. src/app/demo/demo-motion.service.ts
2. src/app/demo/demo.component.ts

## Changes required

### demo-motion.service.ts

The current service has a single boustrophedon path across the full wall width
(PATH_W = 0.50, x range −0.25 to +0.25).

Split into two half-width paths:
- Right arm: x range 0.0 to +0.25 (right half)
- Left arm:  x range −0.25 to 0.0  (left half)

Add a second `DemoMotionState` class (or duplicate the state fields with a
`_left` suffix) so both arms have independent waypoint indices and progress.

Rename the existing `tick()` to `tickRight()`.
Add a new `tickLeft()` that returns a MotionFrame for the left arm.

`tickLeft()` must:
- Use a separate waypoint set built with x range −0.25 to 0.0
- Use a separate waypointIndex and progress so left/right are independent
- Mirror the shoulder pan: return `shoulderPan` negated
  (left shoulder is at negative X, so pan must be negated relative to right)
- Use the same focus / fingerCurl / state logic as the right arm

Add `currentToolTipLeft(frame: MotionFrame)` mirroring `currentToolTip`
with shoulder X negated: `const px = -SHOULDER.x + ...`

Keep SHOULDER.x = 0 so both arms share the same Y/Z origin but differ in
their pan direction.

### demo.component.ts

Add a second set of skeleton joint fields with `_L` suffix:
  private shoulderPan_L!: Object3D;
  private shoulderTilt_L!: Object3D;
  private elbowPivot_L!: Object3D;
  private wristPivot_L!: Object3D;
  private fingerProximal_L: Object3D[] = [];
  private fingerMedial_L: Object3D[] = [];

Add `buildSkeletonLeft(scene: Scene)` — copy of `buildSkeleton()` but:
- Shoulder base pedestal position: x = −0.55 (mirror of right arm at x = 0,
  but offset left to avoid overlap — check existing base position in buildSkeleton)
- shoulderPan positioned at x = −0.55 (or wherever the left shoulder sits)
- Assign joints to the `_L` fields instead of the original fields
- Use the same armMaterial (shared, already created in buildSkeleton)

Call `buildSkeletonLeft(scene)` in `initScene()` immediately after
`this.buildSkeleton(scene)`.

In the RAF loop, after the existing `motion.tick` call:
  const frameL = this.motion.tickLeft(dt, this.eeg.focus());
  this.applyPoseLeft(frameL);
  const tipL = this.motion.currentToolTipLeft(frameL);
  this.addPaintDabLeft(tipL[0], tipL[1], tipL[2]);

Add `applyPoseLeft(frame: MotionFrame)` — exact copy of `applyPose` but
targeting the `_L` joints.

Add `addPaintDabLeft(x, y, _z)` — exact copy of `addPaintDab` but:
- Use a separate `lastPaintX_L = -99` field
- Paint dabs at the same z = −0.435

In `ngOnDestroy()` — no changes needed (renderer.dispose() covers all meshes).

## Constraints (from guardrails)

- DO NOT edit any file not listed above
- DO NOT add any npm packages
- DO NOT use `any`, `as unknown as`, or `@ts-ignore`
- DO NOT commit
- After every TypeScript change run: npx tsc --noEmit
- Final check: ng build --configuration development

## Verification

After implementation:
1. npx tsc --noEmit → zero errors
2. ng build --configuration development → build succeeds
3. Navigate to http://localhost:4200/demo — two arms should be visible, each
   tracing its half of the wall, paint dabs appearing on both sides

Start by reading both files, then implement. Do not start coding until you
have read the current source.
```
