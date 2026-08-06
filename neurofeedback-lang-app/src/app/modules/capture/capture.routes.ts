// src/app/modules/capture/capture.routes.ts
import { Routes } from '@angular/router';
import { CaptureShellComponent } from './components/capture-shell/capture-shell.component';

export const CAPTURE_ROUTES: Routes = [
  {
    path: '',
    component: CaptureShellComponent,
  },
];