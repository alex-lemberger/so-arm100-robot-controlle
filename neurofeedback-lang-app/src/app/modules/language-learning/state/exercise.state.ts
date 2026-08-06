import { Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { Action, Selector, State, StateContext } from '@ngxs/store';
import { Observable, of } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import {
  ExerciseBase,
  SpeakingExercise,
  ExerciseType,
} from '../../../shared/models/exercise.model';
import { ExerciseService } from '../services/exercise.service';
import { MockExerciseService } from '../services/mock-exercise.service';
import { WpExerciseSourceService } from '../services/wp-exercise-source.service';
import { environment } from '../../../environments/environment';
import { ExerciseSource } from '../services/exercise-source.interface';
import { EngagementSource } from '../../../core/engagement/engagement-source';

// --- ACTIONS ---
export namespace ExerciseActions {
  export class FetchAll {
    static readonly type = '[Exercise] Fetch All';
  }

  export class FetchByType {
    static readonly type = '[Exercise] Fetch By Type';
    constructor(public exerciseType: ExerciseType) {}
  }

  export class FetchById {
    static readonly type = '[Exercise] Fetch By Id';
    constructor(public id: string) {}
  }

  export class SetCurrent {
    static readonly type = '[Exercise] Set Current';
    constructor(public exercise: ExerciseBase) {}
  }

  export class Pause {
    static readonly type = '[Exercise] Pause';
    constructor(public id: string) {}
  }

  export class Resume {
    static readonly type = '[Exercise] Resume';
    constructor(public id: string) {}
  }

  export class NavigateToPrevious {
    static readonly type = '[Exercise] Navigate To Previous';
    constructor(public id: string) {}
  }

  export class NavigateToNext {
    static readonly type = '[Exercise] Navigate To Next';
    constructor(public id: string) {}
  }

  export class UpdateProgress {
    static readonly type = '[Exercise] Update Progress';
    constructor(public id: string, public progress: number) {}
  }

  export class UpdateFocusMetrics {
    static readonly type = '[Exercise] Update Focus Metrics';
    constructor(public id: string, public metrics: any) {}
  }
}

// --- STATE MODEL ---
export interface ExerciseStateModel {
  exercises: ExerciseBase[];
  currentExercise: ExerciseBase | null;
  loading: boolean;
  error: string | null;
}

// --- STATE ---
@State<ExerciseStateModel>({
  name: 'exercises',
  defaults: {
    exercises: [],
    currentExercise: null,
    loading: false,
    error: null,
  },
})
@Injectable()
export class ExerciseState {
  private exerciseSource: ExerciseSource;
  private readonly isMock = environment.useMockData;

  constructor(
    private router: Router,
    private exerciseService: ExerciseService,
    private mockExerciseService: MockExerciseService,
    private wpExerciseSourceService: WpExerciseSourceService,
    private engagementSource: EngagementSource
  ) {
    this.exerciseSource = environment.useMockData ? this.mockExerciseService : this.wpExerciseSourceService;
  }

  // --- SELECTORS ---
  @Selector()
  static exercises(state: ExerciseStateModel): ExerciseBase[] {
    return state.exercises;
  }

  @Selector()
  static currentExercise(state: ExerciseStateModel): ExerciseBase | null {
    return state.currentExercise;
  }

  @Selector()
  static speakingExercise(state: ExerciseStateModel): SpeakingExercise | null {
    const { currentExercise } = state;
    // This is a type assertion. For full type safety, a type guard would be more robust.
    if (currentExercise && currentExercise.type === ExerciseType.SPEAKING) {
      return currentExercise as SpeakingExercise;
    }
    return null;
  }

  @Selector()
  static isLoading(state: ExerciseStateModel): boolean {
    return state.loading;
  }

  @Selector()
  static error(state: ExerciseStateModel): string | null {
    return state.error;
  }

  @Selector([ExerciseState.exercises])
  static recentExercises(exercises: ExerciseBase[]): (ExerciseBase & { progressPercentage: number })[] {
    return exercises.slice(0, 8).map(exercise => ({
      ...exercise,
      progressPercentage:
        exercise.progress && exercise.progress.total > 0
          ? (exercise.progress.current / exercise.progress.total) * 100
          : 0,
    }));
  }

  // --- ACTION HANDLERS ---
  @Action(ExerciseActions.FetchAll)
  fetchAll(ctx: StateContext<ExerciseStateModel>) {
    ctx.patchState({ loading: true, error: null });
    return this.exerciseSource.getExercises().pipe(
      tap(exercises => ctx.setState({ ...ctx.getState(), exercises, loading: false })),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.FetchByType)
  fetchByType(ctx: StateContext<ExerciseStateModel>, { exerciseType }: ExerciseActions.FetchByType) {
    ctx.patchState({ loading: true, error: null });
    return this.exerciseSource.getExercisesByType(exerciseType).pipe(
      tap(exercises => ctx.setState({ ...ctx.getState(), exercises, loading: false })),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.FetchById)
  fetchById(ctx: StateContext<ExerciseStateModel>, { id }: ExerciseActions.FetchById) {
    ctx.patchState({ loading: true, error: null });
    return this.exerciseSource.getExercise(id).pipe(
      tap(currentExercise => ctx.setState({ ...ctx.getState(), currentExercise, loading: false })),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.SetCurrent)
  setCurrent(ctx: StateContext<ExerciseStateModel>, { exercise }: ExerciseActions.SetCurrent) {
    ctx.patchState({ currentExercise: exercise });
  }

  @Action(ExerciseActions.Pause)
  pause(ctx: StateContext<ExerciseStateModel>, { id }: ExerciseActions.Pause) {
    return this.mockGuard(this.exerciseService.pauseExercise(id)).pipe(
      tap(() => {
        const currentExercise = { ...ctx.getState().currentExercise, status: 'paused', lastPausedAt: new Date() } as ExerciseBase;
        ctx.patchState({ currentExercise });
      }),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.Resume)
  resume(ctx: StateContext<ExerciseStateModel>, { id }: ExerciseActions.Resume) {
    return this.mockGuard(this.exerciseService.resumeExercise(id)).pipe(
      tap(() => {
        const currentExercise = { ...ctx.getState().currentExercise, status: 'active' } as ExerciseBase;
        ctx.patchState({ currentExercise });
      }),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.NavigateToNext)
  navigateToNext(ctx: StateContext<ExerciseStateModel>, { id }: ExerciseActions.NavigateToNext) {
    this.engagementSource.recordInteraction({ type: 'response', timestamp: Date.now() });
    const currentExercises = ctx.getState().exercises;
    return this.exerciseService.navigateToNext(id, currentExercises).pipe(
      tap((nextId) => {
        if (nextId) {
          this.router.navigate(['/exercises', 'speaking', nextId]);
        }
      }),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.NavigateToPrevious)
  navigateToPrevious(ctx: StateContext<ExerciseStateModel>, { id }: ExerciseActions.NavigateToPrevious) {
    this.engagementSource.recordInteraction({ type: 'response', timestamp: Date.now() });
    const currentExercises = ctx.getState().exercises;
    return this.exerciseService.navigateToPrevious(id, currentExercises).pipe(
      tap((prevId) => {
        if (prevId) {
          this.router.navigate(['/exercises', 'speaking', prevId]);
        }
      }),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.UpdateProgress)
  updateProgress(ctx: StateContext<ExerciseStateModel>, { id, progress }: ExerciseActions.UpdateProgress) {
    this.engagementSource.recordInteraction({ type: 'response', timestamp: Date.now() });
    return this.mockGuard(this.exerciseService.updateProgress(id, progress)).pipe(
      tap(() => {
        const currentExercise = ctx.getState().currentExercise;
        if (currentExercise && currentExercise.progress) {
          const newProgress = { ...currentExercise.progress, current: progress };
          ctx.patchState({ currentExercise: { ...currentExercise, progress: newProgress } });
        }
      }),
      catchError(error => this.handleError(ctx, error))
    );
  }

  @Action(ExerciseActions.UpdateFocusMetrics)
  updateFocusMetrics(ctx: StateContext<ExerciseStateModel>, { id, metrics }: ExerciseActions.UpdateFocusMetrics) {
    return this.mockGuard(this.exerciseService.updateFocusMetrics(id, metrics)).pipe(
      tap(() => {
        const currentExercise = { ...ctx.getState().currentExercise, focusMetrics: metrics } as ExerciseBase;
        ctx.patchState({ currentExercise });
      }),
      catchError(error => this.handleError(ctx, error))
    );
  }

  /** Skip Supabase writes in mock mode; local state update in tap() still fires. */
  private mockGuard<T>(real$: Observable<T>): Observable<T | null> {
    return this.isMock ? of(null) : real$;
  }

  private handleError(ctx: StateContext<ExerciseStateModel>, error: any) {
    ctx.patchState({ loading: false, error: error.message });
    return of(null);
  }
}