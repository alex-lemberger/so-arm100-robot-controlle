import { ComponentFixture, TestBed } from '@angular/core/testing';
import { BehaviorSubject } from 'rxjs';
import { Store } from '@ngxs/store';
import { HardwareSetupComponent } from './hardware-setup.component';
import { ImuService } from '../../services/imu.service';
import { VideoRecorderService } from '../../services/video-recorder.service';
import { BrainDevice, DeviceState, DeviceStatus } from '../../../../core/neurofeedback/brain-device';
import { CaptureActions } from '../../state/capture.actions';

class FakeImuService {
  isSupported = true;
  leftConnected  = new BehaviorSubject(false);
  rightConnected = new BehaviorSubject(false);
  leftConnected$  = this.leftConnected.asObservable();
  rightConnected$ = this.rightConnected.asObservable();
  error$ = new BehaviorSubject<Partial<Record<'left' | 'right', string | null>>>({});
  connectCalls: string[] = [];

  async connect(hand: 'left' | 'right'): Promise<void> {
    this.connectCalls.push(hand);
  }

  disconnect = jasmine.createSpy('disconnect').and.returnValue(Promise.resolve());
  startRecording = jasmine.createSpy('startRecording');
  stopRecording  = jasmine.createSpy('stopRecording').and.returnValue({ left: new Float32Array(), right: new Float32Array() });
}

class FakeVideoRecorderService {
  cameraReady = new BehaviorSubject(false);
  cameraReady$ = this.cameraReady.asObservable();
  requestCameraCalls = 0;

  async requestCamera(): Promise<void> {
    this.requestCameraCalls += 1;
  }
}

class FakeBrainDevice extends BrainDevice {
  focus$ = new BehaviorSubject<number | null>(null).asObservable();
  calm$ = new BehaviorSubject<number | null>(null).asObservable();
  state = new BehaviorSubject<DeviceState>({ isLoggedIn: false, error: null });
  state$ = this.state.asObservable();
  extras$ = new BehaviorSubject<Record<string, number>>({}).asObservable();
  rawEeg$ = undefined;
  connectCalls = 0;

  async connect(): Promise<void> {
    this.connectCalls += 1;
  }

  async disconnect(): Promise<void> {}

  async getStatus(): Promise<DeviceStatus> {
    return { state: 'offline' };
  }
}

describe('HardwareSetupComponent', () => {
  let fixture: ComponentFixture<HardwareSetupComponent>;
  let imu: FakeImuService;
  let video: FakeVideoRecorderService;
  let brainDevice: FakeBrainDevice;
  let store: { dispatch: jasmine.Spy };

  beforeEach(async () => {
    imu = new FakeImuService();
    video = new FakeVideoRecorderService();
    brainDevice = new FakeBrainDevice();
    store = { dispatch: jasmine.createSpy('dispatch') };

    await TestBed.configureTestingModule({
      imports: [HardwareSetupComponent],
      providers: [
        { provide: ImuService, useValue: imu },
        { provide: VideoRecorderService, useValue: video },
        { provide: BrainDevice, useValue: brainDevice },
        { provide: Store, useValue: store },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(HardwareSetupComponent);
    fixture.detectChanges();
  });

  it('starts with a preparation step before individual hardware connections', () => {
    expect(text()).toContain('Schritt 1 von 6');
    expect(text()).toContain('Sitzung vorbereiten');
    expect(text()).toContain('Weiter');
  });

  it('gates each connection step until the current device is ready', async () => {
    clickButton('Weiter');
    fixture.detectChanges();

    expect(text()).toContain('Schritt 2 von 6');
    expect(text()).toContain('Linken Handschuh verbinden');
    expect(button('Weiter').disabled).toBeTrue();

    clickButton('Linken Handschuh verbinden');
    await fixture.whenStable();
    expect(imu.connectCalls).toEqual(['left']);

    imu.leftConnected.next(true);
    fixture.detectChanges();
    expect(button('Weiter').disabled).toBeFalse();

    clickButton('Weiter');
    fixture.detectChanges();
    expect(text()).toContain('Schritt 3 von 6');
    expect(text()).toContain('Rechten Handschuh verbinden');
  });

  it('dispatches AdvanceToTask only from the readiness summary', () => {
    clickButton('Weiter');
    imu.leftConnected.next(true);
    fixture.detectChanges();
    clickButton('Weiter');
    imu.rightConnected.next(true);
    fixture.detectChanges();
    clickButton('Weiter');
    video.cameraReady.next(true);
    fixture.detectChanges();
    clickButton('Weiter');
    brainDevice.state.next({ isLoggedIn: true, error: null });
    fixture.detectChanges();
    clickButton('Weiter');
    fixture.detectChanges();

    expect(text()).toContain('Bereit für Aufgabenwahl');
    clickButton('Zur Aufgabenwahl');

    expect(store.dispatch).toHaveBeenCalledOnceWith(jasmine.any(CaptureActions.AdvanceToTask));
  });

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function button(label: string): HTMLButtonElement {
    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    const match = buttons.find((candidate) => candidate.textContent?.trim() === label);
    if (!match) throw new Error(`Button "${label}" not found`);
    return match;
  }

  function clickButton(label: string): void {
    button(label).click();
  }
});
