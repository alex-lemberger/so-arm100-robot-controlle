// src/app/modules/capture/state/capture.state.ts
import { Injectable } from '@angular/core';
import { State, Action, StateContext, Selector } from '@ngxs/store';
import { CaptureStateModel, CaptureStatus } from './capture.model';
import { CaptureActions } from './capture.actions';

const DEFAULTS: CaptureStateModel = {
  workerToken: null,
  taskType: null,
  taskLabel: null,
  sessionId: null,
  status: 'idle',
  uploadProgress: 0,
  error: null,
};

@State<CaptureStateModel>({
  name: 'capture',
  defaults: DEFAULTS,
})
@Injectable()
export class CaptureState {
  @Selector()
  static status(state: CaptureStateModel): CaptureStatus {
    return state.status;
  }

  @Selector()
  static sessionId(state: CaptureStateModel): string | null {
    return state.sessionId;
  }

  @Selector()
  static workerToken(state: CaptureStateModel): string | null {
    return state.workerToken;
  }

  @Selector()
  static uploadProgress(state: CaptureStateModel): number {
    return state.uploadProgress;
  }

  @Selector()
  static error(state: CaptureStateModel): string | null {
    return state.error;
  }

  @Selector()
  static taskType(state: CaptureStateModel): string | null {
    return state.taskType;
  }

  @Selector()
  static taskLabel(state: CaptureStateModel): string | null {
    return state.taskLabel;
  }

  @Action(CaptureActions.StartSetup)
  startSetup({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'setup', error: null });
  }

  @Action(CaptureActions.SetWorker)
  setWorker({ patchState }: StateContext<CaptureStateModel>, { workerToken }: CaptureActions.SetWorker) {
    patchState({ workerToken });
  }

  @Action(CaptureActions.SetTask)
  setTask({ patchState }: StateContext<CaptureStateModel>, { taskType, taskLabel }: CaptureActions.SetTask) {
    patchState({ taskType, taskLabel });
  }

  @Action(CaptureActions.StartRecording)
  startRecording({ patchState }: StateContext<CaptureStateModel>, { sessionId }: CaptureActions.StartRecording) {
    patchState({ status: 'recording', sessionId, uploadProgress: 0 });
  }

  @Action(CaptureActions.StopRecording)
  stopRecording({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'uploading' });
  }

  @Action(CaptureActions.UploadProgress)
  uploadProgress({ patchState }: StateContext<CaptureStateModel>, { progress }: CaptureActions.UploadProgress) {
    patchState({ uploadProgress: progress });
  }

  @Action(CaptureActions.UploadComplete)
  uploadComplete({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'done', uploadProgress: 100 });
  }

  @Action(CaptureActions.UploadFailed)
  uploadFailed({ patchState }: StateContext<CaptureStateModel>, { error }: CaptureActions.UploadFailed) {
    patchState({ status: 'error', error });
  }

  @Action(CaptureActions.Reset)
  reset({ setState }: StateContext<CaptureStateModel>) {
    setState(DEFAULTS);
  }

  @Action(CaptureActions.AdvanceToTask)
  advanceToTask({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'task' });
  }
}