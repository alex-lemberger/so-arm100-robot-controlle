// src/app/modules/language-learning/services/exercise.service.ts
import { Injectable } from '@angular/core';
import { from, Observable, of, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { ExerciseBase, SpeakingExercise, ExerciseType } from '../../../shared/models/exercise.model';
import { ExerciseSource } from './exercise-source.interface';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';

@Injectable({ providedIn: 'root' })
export class ExerciseService implements ExerciseSource {
  constructor(private readonly supabase: SupabaseClientService) {}

  getExercises(): Observable<ExerciseBase[]> {
    return from(
      this.supabase.client.from('exercises').select('*').then(({ data, error }) => {
        if (error) throw new Error(error.message);
        return (data ?? []) as ExerciseBase[];
      }),
    ).pipe(catchError(this.handleError<ExerciseBase[]>('getExercises', [])));
  }

  getExercise(id: string): Observable<ExerciseBase> {
    return from(
      this.supabase.client.from('exercises').select('*').eq('id', id).single()
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          if (!data) throw new Error(`Exercise with id ${id} not found`);
          return data as ExerciseBase;
        }),
    ).pipe(
      catchError(error => {
        console.error(`getExercise failed for id ${id}:`, error);
        return throwError(() => error);
      }),
    );
  }

  getExercisesByType(type: ExerciseType): Observable<ExerciseBase[]> {
    return from(
      this.supabase.client.from('exercises').select('*').eq('type', type)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as ExerciseBase[];
        }),
    ).pipe(catchError(this.handleError<ExerciseBase[]>('getExercisesByType', [])));
  }

  getSpeakingExercises(): Observable<SpeakingExercise[]> {
    return from(
      this.supabase.client.from('exercises').select('*').eq('type', ExerciseType.SPEAKING)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as SpeakingExercise[];
        }),
    ).pipe(catchError(this.handleError<SpeakingExercise[]>('getSpeakingExercises', [])));
  }

  getCollection(collectionPath: string): Observable<ExerciseBase[]> {
    return this.getExercises();
  }

  pauseExercise(exerciseId: string): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ status: 'paused', last_paused_at: new Date().toISOString() })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  resumeExercise(exerciseId: string): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ status: 'active' })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  navigateToPrevious(exerciseId: string, exercises: ExerciseBase[]): Observable<string | null> {
    if (!exercises?.length) return of(null);
    const sorted = [...exercises].sort((a, b) => a.title.localeCompare(b.title));
    const idx = sorted.findIndex(ex => ex.id === exerciseId);
    if (idx === -1) return of(null);
    return of(idx > 0 ? sorted[idx - 1].id : sorted[sorted.length - 1].id);
  }

  navigateToNext(exerciseId: string, exercises: ExerciseBase[]): Observable<string | null> {
    if (!exercises?.length) return of(null);
    const sorted = [...exercises].sort((a, b) => a.title.localeCompare(b.title));
    const idx = sorted.findIndex(ex => ex.id === exerciseId);
    if (idx === -1) return of(null);
    return of(idx < sorted.length - 1 ? sorted[idx + 1].id : sorted[0].id);
  }

  updateProgress(exerciseId: string, progress: number): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ progress_current: progress })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  updateFocusMetrics(exerciseId: string, metrics: any): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ focus_metrics: metrics })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  private handleError<T>(operation = 'operation', result?: T) {
    return (error: any): Observable<T> => {
      console.error(`${operation} failed:`, error.message);
      return result !== undefined ? of(result as T) : throwError(() => new Error(error));
    };
  }
}