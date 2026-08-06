import { Observable } from 'rxjs';
import { ExerciseBase, ExerciseType } from '../../../shared/models/exercise.model';

export interface ExerciseSource {
  getExercises(): Observable<ExerciseBase[]>;
  getExercisesByType(type: ExerciseType): Observable<ExerciseBase[]>;
  getExercise(id: string): Observable<ExerciseBase | null>;
}
