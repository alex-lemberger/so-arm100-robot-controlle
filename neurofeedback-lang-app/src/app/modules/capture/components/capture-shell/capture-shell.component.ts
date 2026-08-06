// src/app/modules/capture/components/capture-shell/capture-shell.component.ts
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureState } from '../../state/capture.state';
import { CaptureStatus } from '../../state/capture.model';
import { WorkerConsentComponent } from '../worker-consent/worker-consent.component';
import { HardwareSetupComponent } from '../hardware-setup/hardware-setup.component';
import { TaskSelectorComponent } from '../task-selector/task-selector.component';
import { LiveCaptureComponent } from '../live-capture/live-capture.component';
import { UploadProgressComponent } from '../upload-progress/upload-progress.component';

@Component({
  selector: 'app-capture-shell',
  standalone: true,
  imports: [
    CommonModule,
    WorkerConsentComponent,
    HardwareSetupComponent,
    TaskSelectorComponent,
    LiveCaptureComponent,
    UploadProgressComponent,
  ],
  template: `
    <div class="capture-shell">
      @switch (status()) {
        @case ('idle') { <app-worker-consent /> }
        @case ('setup') { <app-hardware-setup /> }
        @case ('task') { <app-task-selector /> }
        @case ('recording') { <app-live-capture /> }
        @case ('uploading') { <app-upload-progress /> }
        @case ('done') { <app-upload-progress /> }
        @case ('error') { <app-upload-progress /> }
        @default { <app-worker-consent /> }
      }
    </div>
  `,
  styles: [`
    .capture-shell {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: calc(100vh - 104px);
      background: #0f1923;
      padding: 24px;
      border-radius: 12px;
    }
  `],
})
export class CaptureShellComponent {
  private store = inject(Store);
  protected status = toSignal(this.store.select(CaptureState.status), { initialValue: 'idle' as CaptureStatus });
}