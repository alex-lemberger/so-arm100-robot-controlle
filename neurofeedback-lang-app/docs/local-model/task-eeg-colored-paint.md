# Local Model Task — EEG-Colored Paint Dabs

Paste the block below as your first message to opencode.

---

```
You are adding EEG-colored paint dabs to an existing Angular 19 Three.js demo at:
/Users/alexanderlemberger/neurofeedback-lang-app

Read the file fully before writing any code.

## File to change (ONLY this one)

1. src/app/demo/demo.component.ts

---

## What to change

Currently all paint dabs share a single static `paintMaterial` (grey, `0x94a3b8`).
Change each dab to capture the current EEG focus color at the moment it is painted —
so the wall accumulates a permanent color trail that shows focus history over time.

### Color mapping (same scale as arm color)

```typescript
private dabColor(focus: number): number {
  if (focus <= 0.4)  return 0x93c5fd;  // blue
  if (focus <= 0.65) {
    const t = (focus - 0.4) / 0.25;
    // lerp blue→amber in hex: interpolate r/g/b
    const r = Math.round(0x93 + t * (0xf5 - 0x93));
    const g = Math.round(0xc5 + t * (0x9e - 0xc5));
    const b = Math.round(0xfd + t * (0x0b - 0xfd));
    return (r << 16) | (g << 8) | b;
  }
  const t = Math.min(1, (focus - 0.65) / 0.2);
  const r = Math.round(0xf5 + t * (0xef - 0xf5));
  const g = Math.round(0x9e + t * (0x44 - 0x9e));
  const b = Math.round(0x0b + t * (0x44 - 0x0b));
  return (r << 16) | (g << 8) | b;
}
```

Add this private method to DemoComponent.

### Track per-dab materials for disposal

Add a field:
```typescript
private dabMaterials: MeshPhongMaterial[] = [];
```

### Update addPaintDab — accept focus param

Change signature to:
```typescript
private addPaintDab(x: number, y: number, _z: number, focus: number): void
```

Inside, replace `this.paintMaterial` with a new per-dab material:
```typescript
const color = this.dabColor(focus);
const mat = new MeshPhongMaterial({ color, emissive: color, emissiveIntensity: 0.3 });
this.dabMaterials.push(mat);
const dab = new Mesh(new PlaneGeometry(0.04, 0.015), mat);
```

### Update addPaintDabLeft — accept focus param

Same change: signature becomes `addPaintDabLeft(x: number, y: number, _z: number, focus: number)`,
replace `this.paintMaterial` with the same per-dab pattern as above.

### Update RAF loop call sites

In the RAF loop, both `addPaintDab` and `addPaintDabLeft` calls must pass the current focus:

```typescript
this.addPaintDab(tip[0], tip[1], tip[2], this.eeg.focus());
this.addPaintDabLeft(tipL[0], tipL[1], tipL[2], this.eeg.focus());
```

### Update ngOnDestroy — dispose per-dab materials

After `this.paintMaterial?.dispose();`, add:
```typescript
this.dabMaterials.forEach(m => m.dispose());
```

### Remove paintMaterial from buildSkeleton

The `this.paintMaterial` field is no longer used in dabs. Remove the line:
```typescript
this.paintMaterial = new MeshPhongMaterial({ color: 0x94a3b8, emissive: 0x64748b });
```
and remove the `paintMaterial` field declaration and its `?.dispose()` call in ngOnDestroy.

---

## Constraints

- DO NOT edit any file not listed above
- DO NOT add npm packages
- DO NOT use `any`, `as unknown as`, or `@ts-ignore`
- DO NOT commit
- After every change: npx tsc --noEmit
- Final: ng build --configuration development

## Verification

1. `npx tsc --noEmit` → zero errors
2. `ng build --configuration development` → succeeds
3. Navigate to http://localhost:4200/demo:
   - Wall accumulates paint dabs that are blue when focus is low, amber mid, red when focus peaks
   - Both left and right arm paint trails are colored independently by EEG at time of stroke
   - Color matches the arm color at that moment (they share the same focus signal)
```
