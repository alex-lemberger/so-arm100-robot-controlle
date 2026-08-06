import { Routes } from '@angular/router';
import { CAPTURE_ROUTES } from './modules/capture/capture.routes';
import { LAB_ROUTES } from './modules/lab/lab.routes';
import { DashboardLayoutComponent } from './shared/components/layout/dashboard-layout/dashboard-layout.component';
import { DashboardComponent } from './shared/components/layout/dashboard-layout/dashboard.component';
import { ExercisesOverviewComponent } from './modules/language-learning/components/exercises-overview/exercises-overview.component';
import { SpeakingExerciseComponent } from './modules/language-learning/components/speaking-exercise/speaking-exercise.component';

export const routes: Routes = [
  {
    path: '',
    component: DashboardLayoutComponent,
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      { path: 'dashboard', component: DashboardComponent },
      { path: 'lab', children: LAB_ROUTES },
      { path: 'capture', children: CAPTURE_ROUTES },
      {
        path: 'demo',
        loadComponent: () =>
          import('./demo/demo.component').then(m => m.DemoComponent),
      },
      {
        path: 'exercises',
        children: [
          { path: '', component: ExercisesOverviewComponent },
          {
            path: 'speaking',
            children: [
              { path: '', component: ExercisesOverviewComponent },
              { path: ':id', component: SpeakingExerciseComponent },
            ],
          },
        ],
      },
    ],
  },
  {
    path: '**',
    redirectTo: 'dashboard',
  },
];
