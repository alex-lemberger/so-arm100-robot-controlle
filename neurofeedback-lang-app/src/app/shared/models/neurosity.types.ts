import { Observable } from 'rxjs';

export interface NotionMetric {
  probability: number;
  metric?: string;
  timestamp: number;
}

export interface NotionStatus {
  state: 'online' | 'offline';
  battery?: {
    level: number;
    charging: boolean;
  };
  sampling?: {
    rate: number;
  };
}

export interface ServiceState {
  isLoggedIn: boolean;
  error: string | null;
}
