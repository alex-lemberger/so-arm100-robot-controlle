import { ExerciseType } from "./exercise.model";

export interface ExerciseCategory {
  name: string;
  icon: string;
  route: string;
  type: ExerciseType;
}
