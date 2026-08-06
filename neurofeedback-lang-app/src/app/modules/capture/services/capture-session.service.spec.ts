import { BehaviorSubject } from 'rxjs';
import { CaptureSessionService } from './capture-session.service';
import { CognitiveStateService } from '../../../core/neurofeedback/services/cognitive-state.service';
import { FlowDetectorService } from '../../../core/neurofeedback/services/flow-detector.service';
import { BrainDevice } from '../../../core/neurofeedback/brain-device';
import { ImuService } from './imu.service';
import { VideoRecorderService } from './video-recorder.service';
import { CaptureUploadService } from './capture-upload.service';
import { SupabaseCaptureService } from './supabase-capture.service';
import { Store } from '@ngxs/store';
import { EegBufferService } from './eeg-buffer.service';

function makeService(
  inFlow$: BehaviorSubject<boolean>,
  focus$: BehaviorSubject<number | null>,
  calm$: BehaviorSubject<number | null>,
  eegBufferOverride?: Partial<EegBufferService>,
): CaptureSessionService {
  return new CaptureSessionService(
    { dispatch: jasmine.createSpy() } as unknown as Store,
    jasmine.createSpyObj<SupabaseCaptureService>('SupabaseCaptureService', [
      'startSession', 'updateSession', 'writeEegTick', 'uploadFile', 'deleteSession',
    ]),
    { focus$, calm$, rawEeg$: undefined } as unknown as BrainDevice,
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue({ left: new Float32Array(), right: new Float32Array() }),
    } as unknown as ImuService,
    { startRecording: jasmine.createSpy() } as unknown as VideoRecorderService,
    { progress$: new BehaviorSubject(0) } as unknown as CaptureUploadService,
    { inFlow$ } as unknown as FlowDetectorService,
    jasmine.createSpyObj<CognitiveStateService>('CognitiveStateService', ['startSession', 'endSession'], {
      load$: new BehaviorSubject<number | null>(null),
      fatigue$: new BehaviorSubject<number | null>(null),
      signalOk$: new BehaviorSubject<boolean>(false),
    }),
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue(null),
      ...eegBufferOverride,
    } as unknown as EegBufferService,
  );
}

describe('CaptureSessionService — FlowDetectorService wiring', () => {
  let inFlow$: BehaviorSubject<boolean>;
  let focus$: BehaviorSubject<number | null>;
  let calm$: BehaviorSubject<number | null>;
  let service: CaptureSessionService;
  let writeEegTickSpy: jasmine.Spy;

  beforeEach(() => {
    inFlow$ = new BehaviorSubject<boolean>(false);
    focus$ = new BehaviorSubject<number | null>(null);
    calm$ = new BehaviorSubject<number | null>(null);
    service = makeService(inFlow$, focus$, calm$);
    writeEegTickSpy = spyOn(service as any, 'writeEegTick');
  });

  it('passes inFlow: false when flow detector emits false', () => {
    (service as any).startEegSubscription('session-1');
    focus$.next(0.9);
    calm$.next(0.6);
    expect(writeEegTickSpy).toHaveBeenCalledWith('session-1', 0.9, 0.6, false, null, null, false);
  });

  it('passes inFlow: true when flow detector emits true', () => {
    inFlow$.next(true);
    (service as any).startEegSubscription('session-1');
    focus$.next(0.9);
    calm$.next(0.6);
    expect(writeEegTickSpy).toHaveBeenCalledWith('session-1', 0.9, 0.6, true, null, null, false);
  });

  it('does not write a tick when focus is null', () => {
    (service as any).startEegSubscription('session-1');
    calm$.next(0.6);
    expect(writeEegTickSpy).not.toHaveBeenCalled();
  });
});

describe('CaptureSessionService — EegBufferService wiring', () => {
  it('does not start eeg buffer when rawEeg$ is undefined', async () => {
    const inFlow$ = new BehaviorSubject<boolean>(false);
    const focus$ = new BehaviorSubject<number | null>(null);
    const calm$ = new BehaviorSubject<number | null>(null);
    const startSpy = jasmine.createSpy();
    const svc = makeService(inFlow$, focus$, calm$, { startRecording: startSpy });
    spyOn(svc['supabaseCapture'], 'startSession').and.returnValue(Promise.resolve('sess-1'));
    await svc.startSession('w', 'task', 'label', 'shop');
    expect(startSpy).not.toHaveBeenCalled();
  });
});
