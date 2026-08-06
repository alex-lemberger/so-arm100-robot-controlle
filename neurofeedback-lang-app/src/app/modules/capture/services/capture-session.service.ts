// src/app/modules/capture/services/capture-session.service.ts
import { Injectable, OnDestroy, inject } from '@angular/core';
import { Store } from '@ngxs/store';
import { Subscription, combineLatest } from 'rxjs';
import { filter, withLatestFrom } from 'rxjs/operators';
import { BrainDevice } from '../../../core/neurofeedback/brain-device';
import { CognitiveStateService } from '../../../core/neurofeedback/services/cognitive-state.service';
import { FlowDetectorService } from '../../../core/neurofeedback/services/flow-detector.service';
import { ImuService } from './imu.service';
import { VideoRecorderService } from './video-recorder.service';
import { CaptureUploadService } from './capture-upload.service';
import { SupabaseCaptureService } from './supabase-capture.service';
import { EegBufferService } from './eeg-buffer.service';
import { CaptureActions } from '../state/capture.actions';
import { CONSENT_VERSION } from '../models/capture-session.model';
import { CaptureModeService } from './capture-mode.service';
import { CaptureHistoryService } from './capture-history.service';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class CaptureSessionService implements OnDestroy {
  private eegSub: Subscription | null = null;
  private uploadSub: Subscription | null = null;
  private currentSessionId: string | null = null;
  private eegTickCount = 0;
  private sessionStart = 0;
  private workerToken = '';
  private taskType = '';
  private taskLabel = '';
  private shopId = '';

  private mode = inject(CaptureModeService);
  private historyService = inject(CaptureHistoryService);

  constructor(
    private store: Store,
    private supabaseCapture: SupabaseCaptureService,
    private brainDevice: BrainDevice,
    private imuService: ImuService,
    private videoService: VideoRecorderService,
    private uploadService: CaptureUploadService,
    private flowDetector: FlowDetectorService,
    private cognitiveState: CognitiveStateService,
    private eegBuffer: EegBufferService,
  ) {}

  async startSession(
    workerToken: string,
    taskType: string,
    taskLabel: string,
    shopId: string,
  ): Promise<string> {
    this.eegTickCount = 0;
    this.cognitiveState.startSession();
    try {
      const sessionId = this.mode.isMock()
        ? crypto.randomUUID()
        : await this.supabaseCapture.startSession(
            workerToken, taskType, taskLabel, shopId, CONSENT_VERSION,
          );
      this.currentSessionId = sessionId;
      this.sessionStart = Date.now();
      this.workerToken = workerToken;
      this.taskType = taskType;
      this.taskLabel = taskLabel;
      this.shopId = shopId;
      this.imuService.startRecording(this.sessionStart);
      this.videoService.startRecording();
      if (this.brainDevice.rawEeg$) {
        this.eegBuffer.startRecording(this.brainDevice.rawEeg$);
      }
      this.eegSub = this.startEegSubscription(sessionId);
      this.store.dispatch(new CaptureActions.StartRecording(sessionId));
      return sessionId;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.cleanupRecordingState();
      this.store.dispatch(new CaptureActions.UploadFailed(message));
      throw err;
    }
  }

  async stopSession(): Promise<void> {
    if (!this.currentSessionId) return;
    const sessionId = this.currentSessionId;

    this.store.dispatch(new CaptureActions.StopRecording());
    this.uploadSub?.unsubscribe();
    this.uploadSub = this.uploadService.progress$.subscribe(progress => {
      this.store.dispatch(new CaptureActions.UploadProgress(progress));
    });

    try {
      this.eegSub?.unsubscribe();
      this.eegSub = null;
      this.cognitiveState.endSession();

      const imuBuffers = this.imuService.stopRecording();
      const videoBlob = await this.videoService.stopRecording();
      const eegData = this.eegBuffer.stopRecording();

      if (this.mode.isMock()) {
        this.historyService.addMockSession({
          id: sessionId,
          worker_id: this.workerToken,
          task_type: this.taskType,
          task_label: this.taskLabel,
          shop_id: this.shopId,
          status: 'complete',
          created_at: new Date(this.sessionStart).toISOString(),
          ended_at: new Date().toISOString(),
          eeg_tick_count: this.eegTickCount,
          video_path: null,
          imu_left_path: null,
          imu_right_path: null,
          eeg_path: null,
        });
        this.store.dispatch(new CaptureActions.UploadComplete());
        return;
      }

      await this.supabaseCapture.updateSession(sessionId, {
        status: 'uploading',
        ended_at: new Date().toISOString(),
        eeg_tick_count: this.eegTickCount,
      });

      const paths = await this.uploadService.uploadSession(
        sessionId, videoBlob, imuBuffers.left, imuBuffers.right, eegData,
      );

      await this.supabaseCapture.updateSession(sessionId, {
        status: 'complete',
        video_path: paths.videoPath,
        imu_left_path: paths.imuLeftPath,
        imu_right_path: paths.imuRightPath,
        eeg_path: paths.eegPath,
      });

      this.store.dispatch(new CaptureActions.UploadComplete());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.supabaseCapture.updateSession(sessionId, {
        status: 'failed',
        ended_at: new Date().toISOString(),
        eeg_tick_count: this.eegTickCount,
      }).catch(console.error);
      this.store.dispatch(new CaptureActions.UploadFailed(message));
    } finally {
      this.uploadSub?.unsubscribe();
      this.uploadSub = null;
      this.currentSessionId = null;
    }
  }

  protected startEegSubscription(sessionId: string): Subscription {
    return combineLatest([this.brainDevice.focus$, this.brainDevice.calm$])
      .pipe(
        filter(([f, c]) => f !== null && c !== null),
        withLatestFrom(
          this.flowDetector.inFlow$,
          this.cognitiveState.load$,
          this.cognitiveState.fatigue$,
          this.cognitiveState.signalOk$,
        ),
      )
      .subscribe(([[focus, calm], inFlow, load, fatigue, signalOk]) => {
        this.writeEegTick(sessionId, focus!, calm!, inFlow, load, fatigue, signalOk);
      });
  }

  private writeEegTick(
    sessionId: string,
    focus: number,
    calm: number,
    inFlow: boolean,
    load: number | null,
    fatigue: number | null,
    signalOk: boolean | null,
  ): void {
    this.eegTickCount++;
    if (!this.mode.isMock()) {
      this.supabaseCapture.writeEegTick(sessionId, focus, calm, inFlow, load, fatigue, signalOk);
    }
  }

  ngOnDestroy(): void {
    this.cleanupRecordingState();
  }

  private cleanupRecordingState(): void {
    this.eegSub?.unsubscribe();
    this.eegSub = null;
    this.uploadSub?.unsubscribe();
    this.uploadSub = null;
    this.eegBuffer.stopRecording();
    this.imuService.stopRecording();
    this.currentSessionId = null;
  }
}
