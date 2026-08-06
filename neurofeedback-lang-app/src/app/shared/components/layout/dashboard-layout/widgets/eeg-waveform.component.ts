import {
  Component, OnDestroy, OnInit, computed, input, signal,
} from '@angular/core';

/**
 * Scrolling EEG alpha-band trace. Decorative ambience that makes the live
 * session feel alive — a synthetic multi-sine wave plus jitter, scrolled left
 * to right. aria-hidden: the numeric rings carry the real, accessible signal.
 */
@Component({
  selector: 'app-eeg-waveform',
  standalone: true,
  template: `
    <svg [attr.width]="width()" [attr.height]="height()" class="wave" aria-hidden="true">
      <defs>
        <linearGradient [attr.id]="gradId" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" [attr.stop-color]="color()" stop-opacity="0"/>
          <stop offset="15%" [attr.stop-color]="color()" stop-opacity=".45"/>
          <stop offset="70%" [attr.stop-color]="color()" stop-opacity=".6"/>
          <stop offset="100%" [attr.stop-color]="color()" stop-opacity=".9"/>
        </linearGradient>
      </defs>
      @if (points()) {
        <polyline [attr.points]="points()" fill="none"
                  [attr.stroke]="'url(#' + gradId + ')'"
                  stroke-width="1.6" stroke-linejoin="round"/>
      }
    </svg>
  `,
  styles: [`
    :host { display: block; }
    .wave { display: block; overflow: visible; }
  `]
})
export class EegWaveformComponent implements OnInit, OnDestroy {
  readonly color = input('#1976D2');
  readonly width = input(210);
  readonly height = input(50);

  private static seq = 0;
  protected readonly gradId =
    `eeg-grad-${EegWaveformComponent.seq++}`;

  private readonly N = 85;
  private buf: number[] = Array(this.N).fill(this.height() / 2);
  private t = 0;
  private timer?: ReturnType<typeof setInterval>;
  private readonly raw = signal('');
  protected readonly points = computed(() => this.raw());

  ngOnInit(): void {
    this.buf = Array(this.N).fill(this.height() / 2);
    this.timer = setInterval(() => this.advance(), 90);
  }

  ngOnDestroy(): void {
    if (this.timer) { clearInterval(this.timer); }
  }

  private advance(): void {
    this.t++;
    const h = this.height();
    const w = this.width();
    const s = Math.sin(this.t * .41) * .38
            + Math.sin(this.t * 1.08) * .22
            + Math.sin(this.t * 2.29) * .10
            + (Math.random() - .5) * .14;
    const y = h * .5 - s * h * .32;
    this.buf = [...this.buf.slice(1), y];
    this.raw.set(
      this.buf.map((yv, i) => `${(i / (this.N - 1)) * w},${yv.toFixed(1)}`).join(' ')
    );
  }
}
