import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { LabState } from '../../state/lab.state';

const JOB_KINDS = ['gen-demos', 'synth', 'train-policy', 'eval-policy'] as const;

@Component({
  selector: 'app-lab-shell',
  standalone: true,
  template: `
    <div class="lab">
      <header class="lab__head">
        <h1>Robot Lab</h1>
        <span class="lab__conn" [class.lab__conn--on]="state.connection() === 'online'">
          @switch (state.connection()) {
            @case ('online') { server online }
            @case ('unknown') { connecting… }
            @default { server offline }
          }
        </span>
        @if (state.connection() !== 'online') {
          <button
            class="lab__launch"
            (click)="state.startServer()"
            [disabled]="state.launching()"
            title="Runs uv sync --extra serve then htdp serve via the local launcher (needs npm run dev)">
            {{ state.launching() ? 'starting… (first run installs deps)' : 'Start server' }}
          </button>
        }
      </header>

      @if (state.status(); as s) {
        <section class="lab__tiles">
          <div class="tile"><span class="tile__n">{{ s.tiers.raw.count }}</span><span class="tile__l">raw</span></div>
          <div class="tile"><span class="tile__n">{{ s.tiers.processed.count }}</span><span class="tile__l">processed</span></div>
          <div class="tile"><span class="tile__n">{{ s.tiers.releases.count }}</span><span class="tile__l">releases</span></div>
          <div class="tile"><span class="tile__n">{{ s.demos?.count ?? 0 }}</span><span class="tile__l">demos</span></div>
          <div class="tile"><span class="tile__n">{{ s.policy.present ? 'yes' : 'no' }}</span><span class="tile__l">policy</span></div>
        </section>
      }

      <section class="lab__run">
        <label>Run job
          <select [value]="kind()" (change)="kind.set($any($event.target).value)">
            @for (k of kinds; track k) { <option [value]="k">{{ k }}</option> }
          </select>
        </label>
        <button (click)="run()" [disabled]="state.connection() !== 'online'">Run</button>
        @if (state.watchedJobStatus(); as js) { <span class="lab__jobstatus">{{ js }}</span> }
      </section>

      @if (state.progress(); as p) {
        <div class="lab__bar"><div class="lab__bar-fill" [style.width.%]="p.total > 0 ? (p.current / p.total) * 100 : 0"></div></div>
      }

      <pre class="lab__logs">{{ state.logLines().join('\n') }}</pre>
    </div>
  `,
  styles: [`
    :host { display: block; font-family: 'DM Sans', sans-serif; }
    .lab__head { display: flex; align-items: baseline; gap: 16px; }
    .lab__conn { font-family: 'DM Mono', monospace; font-size: 12px; color: #ef4444; }
    .lab__conn--on { color: #10b981; }
    .lab__launch {
      font-family: 'DM Sans', sans-serif; font-size: 12px; font-weight: 600;
      padding: 5px 12px; border: none; border-radius: 8px; cursor: pointer;
      background: #6366f1; color: #fff;
    }
    .lab__launch:disabled { opacity: .6; cursor: default; }
    .lab__tiles { display: flex; gap: 12px; margin: 20px 0; flex-wrap: wrap; }
    .tile { display: flex; flex-direction: column; padding: 14px 20px; border-radius: 10px; background: #f1f5f9; min-width: 84px; }
    .tile__n { font-family: 'DM Mono', monospace; font-size: 24px; font-weight: 600; }
    .tile__l { font-size: 12px; color: #64748b; }
    .lab__run { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .lab__bar { height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-bottom: 12px; }
    .lab__bar-fill { height: 100%; background: #6366f1; transition: width .2s; }
    .lab__logs { background: #0f172a; color: #cbd5e1; font-family: 'DM Mono', monospace; font-size: 12px; padding: 14px; border-radius: 10px; height: 300px; overflow: auto; white-space: pre-wrap; }
  `],
})
export class LabShellComponent implements OnInit, OnDestroy {
  protected readonly state = inject(LabState);
  protected readonly kinds = JOB_KINDS;
  protected readonly kind = signal<(typeof JOB_KINDS)[number]>('gen-demos');

  ngOnInit(): void { this.state.startPolling(); }
  ngOnDestroy(): void { this.state.stopPolling(); }

  run(): void {
    const args = this.kind() === 'gen-demos' ? { n_train: 20, n_test: 4 } : {};
    void this.state.run(this.kind(), args);
  }
}
