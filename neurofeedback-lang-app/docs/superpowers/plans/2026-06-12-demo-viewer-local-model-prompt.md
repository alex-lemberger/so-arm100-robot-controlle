# Local Model Execution Prompt — Demo Viewer

Copy the block below verbatim as your first message to the local model.

---

```
You are implementing a new feature in an Angular 19 app at:
/Users/alexanderlemberger/neurofeedback-lang-app

## Your task

Implement the Handwerk Capture Demo Viewer feature exactly as specified in:
  docs/superpowers/plans/2026-06-12-demo-viewer.md

Read that file first. Then follow it task by task.

## Critical rules

1. DO NOT commit unless a plan step explicitly says "Commit". The repo owner
   runs a local model on the same branch — unauthorized commits cause conflicts.

2. After every TypeScript change run:
     npx tsc --noEmit
   Fix any type errors before proceeding. DO NOT skip this step.

3. DO NOT run `ng test` — it is broken project-wide (Neurosity SDK / Karma
   conflict). TypeScript compile + `ng build --configuration development` are
   the only valid verification tools.

4. Three.js is already installed. Import named symbols from 'three' and
   'three/addons/controls/OrbitControls.js'. Do not install any new packages.

5. Follow existing Angular patterns:
   - Standalone components only (no NgModule)
   - Signals + effect() for reactive state
   - afterNextRender() for DOM-dependent Three.js init (not ngAfterViewInit)
   - SCSS component styles inline in the @Component decorator

6. The existing RobotViewerComponent at:
     src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts
   is a working reference for Three.js scene setup, RAF loop, ResizeObserver,
   and material disposal patterns. Read it if unsure about any pattern.

7. After the smoke test in Task 7, apply visual tuning corrections by
   inspection. The "Visual Tuning Reference" table at the end of the plan
   lists the exact fixes for common axis-convention issues.

8. DO NOT modify any file outside the plan's File Map unless a compile error
   forces it. The plan lists every file to touch.

## How to proceed

Read the plan. Execute Task 1 through Task 7 in order. Mark each checkbox
as you complete it. Stop after Task 7 Step 4 (the final commit).

If you hit a TypeScript error not covered by the plan, fix it minimally —
do not refactor surrounding code. If you hit an Angular compile error in
`ng build`, check that all imports are correct and the lazy route path
matches the actual file path.

Start now by reading the plan file.
```
