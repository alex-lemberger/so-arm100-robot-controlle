import { Subject, BehaviorSubject } from 'rxjs';
import { MuseClient, EEGReading, TelemetryData } from 'muse-js';
import { MuseDeviceService } from './muse-device.service';

class FakeMuseClient {
  readonly eegReadings = new Subject<EEGReading>();
  readonly telemetryData = new Subject<TelemetryData>();
  readonly connectionStatus = new BehaviorSubject<boolean>(false);
  connect = jasmine.createSpy('connect').and.returnValue(Promise.resolve());
  start   = jasmine.createSpy('start').and.returnValue(Promise.resolve());
  disconnect = jasmine.createSpy('disconnect').and.returnValue(Promise.resolve());
}

/** Build a minimal EEGReading for the AF7 electrode (index 1). */
function eegPacket(samples: number[], electrode = 1): EEGReading {
  return { electrode, index: 0, timestamp: Date.now(), samples };
}

describe('MuseDeviceService — lifecycle', () => {
  let fake: FakeMuseClient;
  let service: MuseDeviceService;

  beforeEach(() => {
    fake = new FakeMuseClient();
    service = new MuseDeviceService(fake as unknown as MuseClient);
  });

  afterEach(async () => {
    await service.disconnect();
  });

  it('state$ starts disconnected with no error', () => {
    const s = service.state$.value;
    expect(s.isLoggedIn).toBe(false);
    expect(s.error).toBeNull();
  });

  it('connect() calls client.connect() and client.start()', async () => {
    await service.connect();
    expect(fake.connect).toHaveBeenCalledTimes(1);
    expect(fake.start).toHaveBeenCalledTimes(1);
  });

  it('connect() sets state$ to isLoggedIn=true on success', async () => {
    await service.connect();
    expect(service.state$.value.isLoggedIn).toBe(true);
    expect(service.state$.value.error).toBeNull();
  });

  it('connect() is a no-op if already connected', async () => {
    await service.connect();
    await service.connect();
    expect(fake.connect).toHaveBeenCalledTimes(1);
  });

  it('connect() sets state$.error and rethrows on client failure', async () => {
    fake.connect.and.returnValue(Promise.reject(new Error('BT unavailable')));
    await expectAsync(service.connect()).toBeRejected();
    expect(service.state$.value.error).toBe('BT unavailable');
    expect(service.state$.value.isLoggedIn).toBe(false);
  });

  it('disconnect() calls client.disconnect()', async () => {
    await service.connect();
    await service.disconnect();
    expect(fake.disconnect).toHaveBeenCalledTimes(1);
  });

  it('disconnect() nulls focus$ and calm$, resets state$', async () => {
    await service.connect();
    await service.disconnect();
    expect(service.focus$.value).toBeNull();
    expect(service.calm$.value).toBeNull();
    expect(service.state$.value.isLoggedIn).toBe(false);
  });

  it('getStatus() resolves with battery from first telemetry packet', async () => {
    await service.connect();
    const statusPromise = service.getStatus();
    fake.telemetryData.next({ sequenceId: 1, batteryLevel: 75, fuelGaugeVoltage: 0, temperature: 0 });
    const status = await statusPromise;
    expect(status.battery?.level).toBeCloseTo(0.75);
    expect(status.state).toBe('online');
  });
});

describe('MuseDeviceService — EEG pipeline', () => {
  let fake: FakeMuseClient;
  let service: MuseDeviceService;

  beforeEach(async () => {
    fake = new FakeMuseClient();
    service = new MuseDeviceService(fake as unknown as MuseClient);
    await service.connect();
  });

  afterEach(async () => {
    await service.disconnect();
  });

  function pushSamples(value: number, count: number): void {
    const PACKET = 12;
    for (let sent = 0; sent < count; sent += PACKET) {
      const chunk = Math.min(PACKET, count - sent);
      fake.eegReadings.next(eegPacket(new Array(chunk).fill(value), 1));
    }
  }

  it('focus$ and calm$ are null before any samples arrive', () => {
    expect(service.focus$.value).toBeNull();
    expect(service.calm$.value).toBeNull();
  });

  it('focus$ and calm$ remain null until WINDOW (256) samples are buffered', () => {
    pushSamples(0.5, 255);
    expect(service.focus$.value).toBeNull();
  });

  it('emits focus$ and calm$ after 256 samples fill the window', () => {
    pushSamples(0.5, 256);
    expect(service.focus$.value).not.toBeNull();
    expect(service.calm$.value).not.toBeNull();
  });

  it('emitted focus$ and calm$ are within [0, 1]', () => {
    pushSamples(0.5, 256);
    expect(service.focus$.value!).toBeGreaterThanOrEqual(0);
    expect(service.focus$.value!).toBeLessThanOrEqual(1);
    expect(service.calm$.value!).toBeGreaterThanOrEqual(0);
    expect(service.calm$.value!).toBeLessThanOrEqual(1);
  });

  it('extras$ contains alpha, beta, theta keys after first emission', () => {
    pushSamples(0.5, 256);
    const extras = service.extras$.value;
    expect(extras['alpha']).toBeDefined();
    expect(extras['beta']).toBeDefined();
    expect(extras['theta']).toBeDefined();
  });

  it('extras$ band fractions sum to ~1.0', () => {
    pushSamples(0.5, 256);
    const e = service.extras$.value;
    expect(e['alpha'] + e['beta'] + e['theta']).toBeCloseTo(1.0, 5);
  });

  it('emits again every STEP (64) new samples', () => {
    pushSamples(0.5, 256);
    pushSamples(1.0, 64);
    expect(service.focus$.value).not.toBeNull();
    expect(service.calm$.value).not.toBeNull();
  });

  it('ignores samples from non-AF7 electrodes', () => {
    for (let sent = 0; sent < 256; sent += 12) {
      fake.eegReadings.next(eegPacket(new Array(12).fill(0.5), 0));
    }
    expect(service.focus$.value).toBeNull();
  });
});