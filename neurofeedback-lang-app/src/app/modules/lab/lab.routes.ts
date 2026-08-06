import { Routes } from '@angular/router';

export const LAB_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/lab-shell/lab-shell.component').then(m => m.LabShellComponent),
  },
];
