import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { map } from 'rxjs/operators';
import { ExerciseSource } from './exercise-source.interface';
import { ExerciseBase, ExerciseType, SpeakingExercise } from '../../../shared/models/exercise.model';
import { WpContentService } from './wp-content.service';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class WpExerciseSourceService implements ExerciseSource {

  constructor(private wpContentService: WpContentService) { }

  getExercises(): Observable<ExerciseBase[]> {
    // Assuming all WP content can be treated as exercises for now.
    // In a real app, you'd likely have specific WP categories/post types for exercises.
    return this.wpContentService.getWpContent(environment.wordpressApiUrl).pipe(
      map(wpContent => this.transformWpContentToExercises(wpContent || []))
    );
  }

  getExercisesByType(type: ExerciseType): Observable<ExerciseBase[]> {
    // This is a simplified implementation. In a real scenario, you might filter
    // WordPress content based on tags, categories, or custom fields that map to ExerciseType.
    return this.getExercises().pipe(
      map(exercises => exercises.filter(exercise => exercise.type === type))
    );
  }

  getExercise(id: string): Observable<ExerciseBase | null> {
    return this.getExercises().pipe(
      map(exercises => exercises.find(exercise => exercise.id === id) || null)
    );
  }

  private transformWpContentToExercises(wpContent: any[]): ExerciseBase[] {
    return wpContent.map(item => {
      // This is a basic mapping. You'll need to adjust this based on how your
      // WordPress content maps to different ExerciseBase properties and types.
      // For example, if a WP post title is the exercise phrase, and content is instructions.
      // You might also need to parse custom fields from WordPress for more complex exercise types.

      // Default to SPEAKING exercise for simplicity, assuming title is phrase.
      const exerciseType = ExerciseType.SPEAKING;
      const phrase = item.title; // Assuming title is the phrase for speaking exercise

      return {
        id: String(item.id), // WordPress ID as exercise ID
        title: item.title,
        type: exerciseType,
        duration: 60, // Placeholder duration
        progress: { current: 0, total: 1 }, // Placeholder progress
        focusLevel: 0, // Placeholder focus level
        // Specific properties for SpeakingExercise
        phrase: phrase,
        audioUrl: `assets/audio/german/phrases/${item.id}.mp3` // Example audio URL
      } as SpeakingExercise; // Cast to SpeakingExercise as we are defaulting to it
    });
  }
}