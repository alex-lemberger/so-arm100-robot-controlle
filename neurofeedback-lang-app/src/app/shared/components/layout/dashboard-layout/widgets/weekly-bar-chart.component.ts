import { Component, computed, input } from '@angular/core';

export interface WeeklyBar {
  day: string;
  focus: number; // 0–1
  calm: number;  // 0–1
}

interface RenderBar {
  day: string; x: number; fy: number; fh: number; cy: number; ch: number;
  opacity: number; today: boolean;
}

/**
 * Compact paired bar chart of the week's focus/calm averages. Past days dim,
 * today highlighted, future days ghosted — the temporal hierarchy lives in
 * opacity + a bold label, never colour alone.
 */
@Component({
  selector: 'app-weekly-bar-chart',
  standalone: true,
  template: `
    <svg width="100%" [attr.viewBox]="'0 0 ' + w() + ' ' + (H + 20)"
         class="bars" role="img"
         aria-label="Weekly focus and calm averages by day">
      @for (b of bars(); track $index) {
        <g [attr.transform]="'translate(' + b.x + ',0)'">
          <rect [attr.x]="0" [attr.y]="b.fy" [attr.width]="BW" [attr.height]="b.fh"
                rx="2.5" fill="#1976D2" [attr.opacity]="b.opacity"/>
          <rect [attr.x]="BW + GAP" [attr.y]="b.cy" [attr.width]="BW" [attr.height]="b.ch"
                rx="2.5" [attr.fill]="calmColor()" [attr.opacity]="b.opacity"/>
          <text [attr.x]="BW" [attr.y]="H + 14" text-anchor="middle"
                class="bars__label" [class.bars__label--today]="b.today">{{ b.day }}</text>
        </g>
      }
    </svg>
  `,
  styles: [`
    :host { display: block; }
    .bars { overflow: visible; }
    .bars__label {
      font-family: 'DM Sans', sans-serif; font-size: 10px; font-weight: 400;
      fill: var(--c-text-3, #9AA8C4);
    }
    .bars__label--today { font-weight: 600; fill: var(--c-text-1, #18253F); }
  `]
})
export class WeeklyBarChartComponent {
  readonly data = input<WeeklyBar[]>([]);
  readonly todayIndex = input(-1);
  readonly calmColor = input('#2E9E85');

  protected readonly BW = 9;
  protected readonly GAP = 4;
  protected readonly H = 58;
  private readonly SLOT = this.BW * 2 + this.GAP + 8;

  protected readonly w = computed(() => this.data().length * this.SLOT);
  protected readonly bars = computed<RenderBar[]>(() => {
    const today = this.todayIndex();
    return this.data().map((d, i) => {
      const fh = d.focus * this.H;
      const ch = d.calm * this.H;
      const isToday = i === today;
      const opacity = isToday ? 1 : i < today ? .68 : .22;
      return {
        day: d.day, x: i * this.SLOT,
        fy: this.H - fh, fh: fh || 2,
        cy: this.H - ch, ch: ch || 2,
        opacity, today: isToday,
      };
    });
  });
}
