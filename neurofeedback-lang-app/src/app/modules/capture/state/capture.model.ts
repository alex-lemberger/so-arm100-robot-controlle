// src/app/modules/capture/state/capture.model.ts
export type CaptureStatus =
  | 'idle'
  | 'setup'
  | 'task'
  | 'recording'
  | 'uploading'
  | 'done'
  | 'error';

export interface CaptureStateModel {
  workerToken: string | null;
  taskType: string | null;
  taskLabel: string | null;
  sessionId: string | null;
  status: CaptureStatus;
  uploadProgress: number;
  error: string | null;
}