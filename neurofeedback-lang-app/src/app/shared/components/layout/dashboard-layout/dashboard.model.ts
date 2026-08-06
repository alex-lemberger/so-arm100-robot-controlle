export interface BrainMetrics {
  value: number;
  changePercentage: number;
  previousValue: number;
}

export interface SessionData {
  focus: number;
  meditation: number; // Maps to calm in your data
  flow: number;      // Calculated from focus and calm
}

export interface CorrelationData {
  date: string;
  current: number;   // Focus value
  previous: number;  // Calm value
}

export interface FocusDataPoint {
  date: string;
  focus: number;
  calm: number;
}

export interface DashboardStateModel {
  brainMetrics: BrainMetrics | null;
  sessionData: SessionData | null;
  correlationData: CorrelationData[];
  focusData: FocusDataPoint[];
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
}

export interface Analytics {
  averageFocus: number;
  averageCalm: number;
  totalSessions: number;
}

export interface SessionState {
  isActive: boolean;
  sessionId: string | null;
  currentFocus: number;
  currentCalm: number;
  averageFocus: number;
  averageCalm: number;
  duration: number;
}

export interface DataPoint {
  focus: number;
  calm: number;
  timestamp: Date;
}

