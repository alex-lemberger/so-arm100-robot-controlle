import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { map } from 'rxjs/operators';
import { ExerciseBase, SpeakingExercise, ExerciseType } from '../../../shared/models/exercise.model';
import { ExerciseSource } from './exercise-source.interface';

@Injectable({
  providedIn: 'root'
})
export class MockExerciseService implements ExerciseSource {
  private mockExercises: SpeakingExercise[] = [
    {
      id: 'german-greeting-1',
      title: 'German Greeting',
      type: ExerciseType.SPEAKING,
      duration: 300,
      progress: { current: 1, total: 5 },
      focusLevel: 85,
      phrase: "Hallo, wie geht es dir?",
      audioUrl: '/assets/audio/german/greetings/hello.mp3',
      status: 'active'
    },
    {
      id: 'german-greeting-2',
      title: 'German Farewell',
      type: ExerciseType.SPEAKING,
      duration: 300,
      progress: { current: 2, total: 5 },
      focusLevel: 80,
      phrase: "Auf Wiedersehen!",
      audioUrl: '/assets/audio/german/greetings/goodbye.mp3',
      status: 'active'
    },
    {
      id: 'german-phrase-1',
      title: 'Ordering Coffee',
      type: ExerciseType.SPEAKING,
      duration: 600,
      progress: { current: 1, total: 8 },
      focusLevel: 75,
      phrase: "Ich möchte einen Kaffee, bitte.",
      audioUrl: '/assets/audio/german/phrases/coffee-order.mp3',
      status: 'active'
    },
    {
      id: 'german-phrase-2',
      title: 'Asking for Directions',
      type: ExerciseType.SPEAKING,
      duration: 600,
      progress: { current: 3, total: 8 },
      focusLevel: 70,
      phrase: "Wo ist der Bahnhof?",
      audioUrl: '/assets/audio/german/phrases/directions.mp3',
      status: 'active'
    },
    {
      id: 'spanish-greeting-1',
      title: 'Spanish Greeting',
      type: ExerciseType.SPEAKING,
      duration: 300,
      progress: { current: 1, total: 5 },
      focusLevel: 90,
      phrase: "Hola, ¿cómo estás?",
      audioUrl: '/assets/audio/spanish/greetings/hello.mp3',
      status: 'active'
    }
  ];

  getExercises(): Observable<ExerciseBase[]> {
    return of(this.mockExercises);
  }

  getExercisesByType(type: ExerciseType): Observable<ExerciseBase[]> {
    return of(this.mockExercises.filter(ex => ex.type === type));
  }

  getExercise(id: string): Observable<ExerciseBase | null> {
    const exercise = this.mockExercises.find(ex => ex.id === id) || null;
    return of(exercise);
  }

  // For backwards compatibility
  getMockSpeakingExercises(): Observable<SpeakingExercise[]> {
    return of(this.mockExercises);
  }
}