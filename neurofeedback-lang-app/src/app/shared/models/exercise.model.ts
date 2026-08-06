// src/app/shared/models/exercise.model.ts
export interface ExerciseBase {
  id: string;
  title: string;
  type: ExerciseType;
  duration: number;
  progress: {
    current: number;
    total: number;
  };

  focusLevel: number;
  status?: 'active' | 'paused' | 'completed';
  lastPausedAt?: Date;
  focusMetrics?: any;
}

export enum ExerciseType {
  SPEAKING = 'speaking',
  LISTENING = 'listening',
  GRAMMAR = 'grammar',
  VOCABULARY = 'vocabulary'
}

export interface SpeakingExercise extends ExerciseBase {
  phrase: string;
  audioUrl?: string;
}

export interface ListeningExercise extends ExerciseBase {
  audioUrl: string;
  question: string;
  options: string[];
  remainingPlays: number;
  duration: number;
}

export interface GrammarExercise extends ExerciseBase {
  sentence: string;
  options: string[];
  verb: string;
}

export interface VocabularyExercise extends ExerciseBase {
  word: string;
  options: string[];
}
