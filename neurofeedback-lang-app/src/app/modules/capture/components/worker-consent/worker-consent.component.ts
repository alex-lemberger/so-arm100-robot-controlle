// src/app/modules/capture/components/worker-consent/worker-consent.component.ts
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { WorkerTokenService } from '../../services/worker-token.service';
import { CaptureActions } from '../../state/capture.actions';
import { CONSENT_VERSION } from '../../models/capture-session.model';
import { SupabaseClientService } from '../../../../core/supabase/supabase-client.service';
import { CaptureModeService } from '../../services/capture-mode.service';

@Component({
  selector: 'app-worker-consent',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="consent-card">
      <div class="mock-toggle" (click)="mode.toggle()">
        <span class="mock-dot" [class.mock-dot--on]="mode.isMock()"></span>
        Mock{{ mode.isMock() ? ' ON' : ' OFF' }}
      </div>
      <h1 class="consent-title">Datenerfassung — Einwilligung</h1>
      <p class="consent-body">
        Diese App erfasst EEG-Gehirnsignale, IMU-Handbewegungsdaten und Videoaufnahmen
        während Ihrer Arbeitstätigkeit. Alle Daten werden anonymisiert gespeichert —
        Ihr Name und Ihre persönlichen Daten werden nicht erhoben. Die Daten werden
        ausschließlich für die Entwicklung von KI-Modellen im Bereich Robotik verwendet.
        Sie können Ihre Einwilligung jederzeit widerrufen und die Löschung Ihrer Daten
        verlangen.
      </p>
      <label class="consent-check">
        <input type="checkbox" [checked]="agreed()" (change)="agreed.set(!agreed())" />
        Ich stimme der Erfassung und Verarbeitung meiner Daten zu (Version {{ version }}).
      </label>
      <button class="consent-btn" [disabled]="!agreed() || saving()" (click)="accept()">
        {{ saving() ? 'Wird gespeichert…' : 'Weiter' }}
      </button>
      @if (error()) {
        <p class="consent-error">{{ error() }}</p>
      }
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; }
    .consent-card {
      background: #1a2535; border-radius: 16px; padding: 40px;
      width: 100%; max-width: 560px; margin: 0 auto; box-sizing: border-box; color: #e8edf5;
    }
    .consent-title { font-family: 'DM Sans', sans-serif; font-size: 22px; margin-bottom: 20px; }
    .consent-body { font-size: 14px; line-height: 1.7; color: #9aa8c4; margin-bottom: 24px; }
    .consent-check { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; margin-bottom: 28px; cursor: pointer; }
    .consent-btn {
      width: 100%; padding: 14px; border-radius: 10px; border: none;
      background: #1976D2; color: #fff; font-size: 16px; cursor: pointer;
    }
    .consent-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .consent-error { color: #ef5350; font-size: 13px; margin-top: 12px; }
    .mock-toggle {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 11px; font-family: 'DM Mono', monospace;
      color: #9aa8c4; cursor: pointer; margin-bottom: 16px;
      padding: 4px 10px; border-radius: 20px; background: #2a3545;
      user-select: none;
    }
    .mock-dot { width: 8px; height: 8px; border-radius: 50%; background: #4a5568; }
    .mock-dot--on { background: #48bb78; }
  `],
})
export class WorkerConsentComponent {
  private store = inject(Store);
  private tokenService = inject(WorkerTokenService);
  private supabase = inject(SupabaseClientService);
  protected mode = inject(CaptureModeService);

  protected version = CONSENT_VERSION;
  protected agreed = signal(false);
  protected saving = signal(false);
  protected error = signal<string | null>(null);

  async accept(): Promise<void> {
    this.saving.set(true);
    this.error.set(null);
    try {
      const workerToken = this.tokenService.getOrCreate();
      if (!this.mode.isMock()) {
        await this.supabase.client.from('workers').upsert({
          id: workerToken,
          consent_timestamp: new Date().toISOString(),
          consent_version: CONSENT_VERSION,
          skill_tags: [],
          session_count: 0,
        });
      }
      this.store.dispatch([
        new CaptureActions.SetWorker(workerToken),
        new CaptureActions.StartSetup(),
      ]);
    } catch (e) {
      this.error.set('Fehler beim Speichern. Bitte erneut versuchen.');
    } finally {
      this.saving.set(false);
    }
  }
}