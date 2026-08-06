// src/app/modules/capture/models/capture-session.model.ts
export type CaptureSessionStatus =
  | 'recording'
  | 'uploading'
  | 'complete'
  | 'failed';

export interface CaptureSession {
  sessionId: string;
  workerId: string;
  taskType: string;
  taskLabel: string;
  startTime: string;
  endTime?: string;
  status: CaptureSessionStatus;
  videoPath?: string;
  imuLeftPath?: string;
  imuRightPath?: string;
  eegTickCount: number;
  consentVersion: string;
  shopId: string;
}

export interface CaptureRow {
  id: string;
  worker_id: string;
  task_type: string;
  task_label: string;
  shop_id: string;
  status: CaptureSessionStatus | 'uploading';
  created_at: string;
  ended_at: string | null;
  eeg_tick_count: number;
  video_path: string | null;
  imu_left_path: string | null;
  imu_right_path: string | null;
  eeg_path: string | null;
}

export interface EegTick {
  t: string;
  focus: number;
  calm: number;
  inFlow: boolean;
  load: number | null;
  fatigue: number | null;
  signalOk: boolean | null;
}

export interface ImuFrame {
  t: number;
  ax: number; ay: number; az: number;
  gx: number; gy: number; gz: number;
}

export const TASK_TYPES: string[] = [
  'engine_assembly',
  'electrical_repair',
  'plumbing_installation',
  'hvac_service',
  'brake_replacement',
  'welding',
  'carpentry',
  'other',
];

export const CONSENT_VERSION = '1.0';