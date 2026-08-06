import { Component, OnInit, Signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { RouterModule } from '@angular/router';
import { Store } from '@ngxs/store';

import { ExerciseState, ExerciseActions } from '../../state/exercise.state';
import { ExerciseBase } from '../../../../shared/models/exercise.model';
import { MatProgressBarModule } from '@angular/material/progress-bar';

@Component({
  selector: 'app-exercises-overview',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatIconModule,
    RouterModule,
    MatProgressBarModule
  ],
  templateUrl: './exercises-overview.component.html',
  styleUrls: ['./exercises-overview.component.scss']
})
export class ExercisesOverviewComponent implements OnInit {
  recentExercises: Signal<(ExerciseBase & { progressPercentage: number })[]>;
  loading: Signal<boolean>;
  error: Signal<string | null>;

  displayedColumns: string[] = ['title', 'type', 'progress', 'focusLevel'];

  constructor(private store: Store) {
    this.recentExercises = toSignal(this.store.select(ExerciseState.recentExercises), { initialValue: [] });
    this.loading = toSignal(this.store.select(ExerciseState.isLoading), { initialValue: false });
    this.error = toSignal(this.store.select(ExerciseState.error), { initialValue: null });
  }

  ngOnInit() {
    this.store.dispatch(new ExerciseActions.FetchAll());
  }

  getFocusLevelText(focusLevel: number): string {
    if (focusLevel >= 80) return 'Excellent';
    if (focusLevel >= 60) return 'Good';
    if (focusLevel >= 40) return 'Intermediate';
    if (focusLevel >= 20) return 'Fair';
    return 'Poor';
  }
}
