import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';
import { provideAnimations } from '@angular/platform-browser/animations';
import { importProvidersFrom, DestroyRef } from '@angular/core';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { environment } from './app/environments/environment';
import { provideRouter } from '@angular/router';
import { routes } from './app/app.routes';
import { MockNeurosityService } from './app/core/neurofeedback/services/mock-neurosity.service';
import { NeurosityService } from './app/core/neurofeedback/services/neurosity.service';
import { MuseDeviceService } from './app/core/neurofeedback/services/muse-device.service';
import { BrainDevice } from './app/core/neurofeedback/brain-device';
import { SupabaseClientService } from './app/core/supabase/supabase-client.service';
import { EngagementSource } from './app/core/engagement/engagement-source';
import { EEGEngagementSource } from './app/core/engagement/eeg-engagement-source';
import { InteractionEngagementSource } from './app/core/engagement/interaction-engagement-source';
import { provideStore } from '@ngxs/store';
import { withNgxsReduxDevtoolsPlugin } from '@ngxs/devtools-plugin';
import { withNgxsLoggerPlugin } from '@ngxs/logger-plugin';
import { ExerciseState } from './app/modules/language-learning/state/exercise.state';
import { CaptureState } from './app/modules/capture/state/capture.state';
import { provideHttpClient } from '@angular/common/http';

bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes),
    provideAnimations(),
    provideHttpClient(),
    importProvidersFrom(
      MatSnackBarModule,
      MatDialogModule,
      MatIconModule,
      MatTableModule,
    ),
    provideStore([ExerciseState, CaptureState], withNgxsReduxDevtoolsPlugin(), withNgxsLoggerPlugin()),
    {
      provide: BrainDevice,
      useFactory: (destroyRef: DestroyRef) => {
        if (environment.device === 'muse') {
          const svc = new MuseDeviceService();
          destroyRef.onDestroy(() => svc.ngOnDestroy());
          return svc;
        }
        if (environment.device === 'neurosity') return new NeurosityService();
        return new MockNeurosityService();
      },
      deps: [DestroyRef],
    },
    {
      provide: SupabaseClientService,
      useFactory: () => new SupabaseClientService(),
    },
    {
      provide: EngagementSource,
      useFactory: (device: BrainDevice) => {
        if (environment.engagementTier === 'premium') {
          return new EEGEngagementSource(device);
        }
        return new InteractionEngagementSource();
      },
      deps: [BrainDevice],
    },
  ],
}).catch(err => console.error(err));
