export interface LearningSession {
  id: string;
  userId: string;
  startTime: string;
  endTime?: string;
  averageFocus: number;
  averageCalm: number;
  status: 'active' | 'completed' | 'interrupted';
  brainMetrics: BrainMetricSnapshot[];
}

export interface BrainMetricSnapshot {
  timestamp: string;
  focus: number;
  calm: number;
}
