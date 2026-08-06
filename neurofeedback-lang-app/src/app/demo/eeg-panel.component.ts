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
