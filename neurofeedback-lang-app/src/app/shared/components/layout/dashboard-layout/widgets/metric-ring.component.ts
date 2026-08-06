import { Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * Bespoke arc-ring gauge for a single 0–1 biometric (focus / calm).
 * Pure SVG; breathes subtly when the value is high to signal "live" without
 * gamification. Renders a loading placeholder while the stream is null.
 */
@Component({
  selector: 'app-metric-ring',
  standalone: true,
  imports: [MatIconModule],
  template: `
    <div class="ring" [class.ring--breathe]="breathing()">
      <div class="ring__plot" [style.width.px]="size()" [style.height.px]="size()">
        <svg [attr.width]="size()" [attr.height]="size()"
             [attr.viewBox]="'0 0 ' + size() + ' ' + size()"
             role="img" [attr.aria-label]="ariaLabel()">
          <circle [attr.cx]="c()" [attr.cy]="c()" [attr.r]="r()" fill="none"
                  [attr.stroke]="paleColor()" stroke-width="6.5"/>
          <circle [attr.cx]="c()" [attr.cy]="c()" [attr.r]="r()" fill="none"
                  [attr.stroke]="color()" stroke-width="6.5" stroke-linecap="round"
                  [attr.stroke-dasharray]="circ() + ' ' + circ()"
                  [attr.stroke-dashoffset]="offset()"
                  [attr.transform]="'rotate(-90 ' + c() + ' ' + c() + ')'"
                  class="ring__arc"/>
        </svg>
        <div class="ring__center">
          <mat-icon [style.color]="color()">{{ icon() }}</mat-icon>
          <span class="ring__value">{{ display() }}</span>
        </div>
      </div>
      <span class="ring__label">{{ label() }}</span>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .ring { display: flex; flex-direction: column; align-items: center; gap: 5px; }
    .ring--breathe .ring__plot { animation: ring-breathe 3.6s ease-in-out infinite; }
    .ring__plot { position: relative; display: grid; place-items: center; }
    .ring__arc { transition: stroke-dashoffset .9s cubic-bezier(.4,0,.2,1); }
    .ring__center {
      position: absolute; inset: 0;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 1px; pointer-events: none;
    }
    .ring__center mat-icon {
      font-size: 15px; width: 15px; height: 15px; line-height: 15px;
    }
    .ring__value {
      font-family: var(--c-mono, 'DM Mono', monospace);
      font-size: 17px; font-weight: 500; letter-spacing: -.5px;
      color: var(--c-text-1, #18253F);
    }
    .ring__label {
      font-size: 10px; font-weight: 600; letter-spacing: .07em;
      text-transform: uppercase; color: var(--c-text-3, #9AA8C4);
    }
    @keyframes ring-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.018); } }
    @media (prefers-reduced-motion: reduce) {
      .ring--breathe .ring__plot { animation: none; }
      .ring__arc { transition: none; }
    }
  `]
})
export class MetricRingComponent {
  readonly value = input<number | null>(null);
  readonly label = input('');
  readonly icon = input('');
  readonly color = input('#1976D2');
  readonly paleColor = input('#E3F2FD');
  readonly size = input(108);

  protected readonly r = computed(() => this.size() / 2 - 10);
  protected readonly c = computed(() => this.size() / 2);
  protected readonly circ = computed(() => 2 * Math.PI * this.r());
  protected readonly offset = computed(() => this.circ() * (1 - (this.value() ?? 0)));
  protected readonly breathing = computed(() => (this.value() ?? 0) > 0.72);
  protected readonly display = computed(() => {
    const v = this.value();
    return v == null ? '–' : v.toFixed(2);
  });
  protected readonly ariaLabel = computed(() => {
    const v = this.value();
    return v == null
      ? `${this.label()}: awaiting signal`
      : `${this.label()}: ${Math.round(v * 100)}%`;
  });
}
