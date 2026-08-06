# Local Model Task — Extract EEG Panel into Standalone Component


---

```
You are extracting the EEG panel overlay from DemoComponent into its own
standalone Angular child component, at:
/Users/alexanderlemberger/neurofeedback-lang-app

Read all listed files fully before writing any code.

## File Map (ONLY these two)

1. src/app/demo/eeg-panel.component.ts  ← CREATE (new file)
2. src/app/demo/demo.component.ts       ← MODIFY

---

## Change 1: Create EegPanelComponent

Create `src/app/demo/eeg-panel.component.ts`:

```typescript
import { Component, OnDestroy, input } from '@angular/core';

@Component({
  selector: 'app-eeg-panel',
  standalone: true,
  template: `
    <div class="eeg-panel">
      <div class="eeg-row">
        <span class="dot" [style.background]="dotColor()"></span>
        <span class="eeg-label">FOCUS</span>
        <div class="bar"><div class="fill" [style.width.%]="focusPct()"></div></div>
        <span class="eeg-val">{{ focusVal() }}</span>
      </div>
      <div class="eeg-row">
        <span class="dot calm"></span>
        <span class="eeg-label">CALM</span>
        <div class="bar calm-bar"><div class="fill calm-fill" [style.width.%]="calmPct()"></div></div>
        <span class="eeg-val">{{ calmVal() }}</span>
      </div>
    </div>
  `,
  styles: [`
    .eeg-panel {
      position: absolute; bottom: 24px; left: 24px;
      background: rgba(15,23,42,0.75); backdrop-filter: blur(6px);
      border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
      padding: 12px 16px; display: flex; flex-direction: column; gap: 8px;
    }
    .eeg-row { display: flex; align-items: center; gap: 10px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot.calm { background: #60a5fa; }
    .eeg-label {
      font-family: 'DM Mono', monospace; font-size: 11px; color: rgba(255,255,255,0.5);
      width: 38px;
    }
    .bar {
      width: 100px; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px;
    }
    .fill { height: 100%; border-radius: 2px; background: #93c5fd; transition: width .1s; }
    .calm-fill { background: #60a5fa; }
    .eeg-val {
      font-family: 'DM Mono', monospace; font-size: 11px; color: rgba(255,255,255,0.7);
      width: 32px; text-align: right;
    }
  `],
})
export class EegPanelComponent implements OnDestroy {
  readonly dotColor  = input.required<string>();
  readonly focusPct  = input.required<number>();
  readonly calmPct   = input.required<number>();
  readonly focusVal  = input.required<string>();
  readonly calmVal   = input.required<string>();

  ngOnDestroy(): void {}
}
```

---

## Change 2: Update DemoComponent

### 2a: Add import

In the `import { ... } from '@angular/core'` block, no changes needed.

Add a new import line after the existing imports:
```typescript
import { EegPanelComponent } from './eeg-panel.component';
```

### 2b: Add to imports array

In the @Component decorator, add `EegPanelComponent` to the `imports` array:
```typescript
imports: [EegPanelComponent],
```

### 2c: Replace inline EEG panel in template

Remove the entire `.eeg-panel` div from the template:
```html
      <div class="eeg-panel">
        <div class="eeg-row">
          ...
        </div>
        <div class="eeg-row">
          ...
        </div>
      </div>
```

Replace with:
```html
      <app-eeg-panel
        [dotColor]="dotColor"
        [focusPct]="focusPct"
        [calmPct]="calmPct"
        [focusVal]="focusVal"
        [calmVal]="calmVal"
      />
```

### 2d: Remove eeg-panel styles from DemoComponent

Remove these style blocks from the component's `styles` array — they now live in EegPanelComponent:
- `.eeg-panel { ... }`
- `.eeg-row { ... }`
- `.dot { ... }`
- `.dot.calm { ... }`
- `.eeg-label { ... }`
- `.bar { ... }`
- `.fill { ... }`
- `.calm-fill { ... }`
- `.eeg-val { ... }`

Keep all other styles (`:host`, `.demo-wrap`, `canvas`, `.title-badge`, `.rec-badge`, `.rec-dot`, `@keyframes pulse`).

### 2e: Keep all 5 fields and updateOverlay() unchanged

Do NOT remove `dotColor`, `focusPct`, `calmPct`, `focusVal`, `calmVal` fields or `updateOverlay()` — they drive the child component via property binding.

---

## Constraints

- DO NOT edit any file not listed in the File Map
- DO NOT add npm packages
- DO NOT use `any`, `as unknown as`, or `@ts-ignore`
- DO NOT commit
- After every change: npx tsc --noEmit
- Final: ng build --configuration development

## Verification

1. `npx tsc --noEmit` → zero errors
2. `ng build --configuration development` → succeeds
3. Navigate to http://localhost:4200/demo:
   - EEG panel visible bottom-left, unchanged in appearance
   - FOCUS and CALM bars animate as before
   - Dot color shifts with EEG signal
```
